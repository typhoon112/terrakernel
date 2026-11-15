"""Reconcile stage: relate objects across sources, keep conflicts explicit, close answered gaps.

Deterministic part
- Documentation dataset objects are linked to profiled data files (``describes``) when
  they name the same file.
- Every relation, umbrella concept and gap resolution proposed by the model is checked:
  IDs must exist, types must be known, no self-loops. Invalid proposals are dropped and
  recorded as validation warnings.

Model part (``reconcile-knowledge`` builder skill)
- same/variant/conflict/implements/describes/applies_to/uses/depends_on relations;
- umbrella concepts grouping conflicting variants of one idea;
- which open gaps are answered by another source, and new cross-source gaps.

The catalog is sent in one request when it fits; larger catalogs are split into
overlapping groups by type and name similarity.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

from pydantic import BaseModel, Field

from terrakernel.builtin import skill_body
from terrakernel.llm.client import LLMClient
from terrakernel.models import (
    Basis,
    Gap,
    KnowledgeObject,
    ObjectStatus,
    ObjectType,
    Relation,
    RelationType,
    Severity,
    ValidationRecord,
)
from terrakernel.project import Project
from terrakernel.util import normalize_name, now_iso, short_hash, slugify

CATALOG_CHAR_BUDGET = 90_000
ATTR_KEYS_IN_CATALOG = (
    "formula", "definition", "statement", "rule", "unit", "file", "fields", "variables", "parameters",
    "valid_from", "valid_to", "missing_data_handling", "behavior_notes", "signature", "symbol", "implements",
    "time_semantics", "inputs", "outputs", "conditions", "applies_to", "time_columns", "subject",
)


class ProposedRelation(BaseModel):
    type: Literal["same_as", "possibly_same_as", "variant_of", "conflicts_with", "implements", "describes",
                  "applies_to", "uses", "depends_on"]
    src: str
    dst: str
    note: str = ""


class UmbrellaConcept(BaseModel):
    name: str
    summary: str
    member_ids: list[str]


class GapResolution(BaseModel):
    gap_id: str
    resolved_by: list[str] = Field(description="IDs of catalog objects that state the missing information")
    explanation: str


class NewGap(BaseModel):
    subject_id: str | None = None
    description: str
    severity: Literal["blocking", "warning"]
    suggestion: str = ""


class ReconcileResult(BaseModel):
    relations: list[ProposedRelation] = Field(default_factory=list)
    umbrella_concepts: list[UmbrellaConcept] = Field(default_factory=list)
    gap_resolutions: list[GapResolution] = Field(default_factory=list)
    new_gaps: list[NewGap] = Field(default_factory=list)


def _compact(value: Any, limit: int = 400) -> Any:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return value if len(text) <= limit else text[:limit] + "..."


def compact_fields(fields: list[Any]) -> list[str]:
    """One short line per data field: name, role, dims, unit and other stated attributes, key statistics."""
    out = []
    for f in fields:
        if not isinstance(f, dict):
            continue
        attrs = f.get("attributes") or {}
        parts = [str(f.get("column"))]
        if f.get("role"):
            parts.append(f["role"])
        if f.get("dims"):
            parts.append("dims=" + "x".join(map(str, f["dims"])))
        for k in ("units", "long_name", "standard_name", "cell_methods", "bounds", "calendar", "_FillValue"):
            if k in attrs:
                parts.append(f"{k}={attrs[k]}")
        if "unit_hint" in f:
            parts.append(f"name suggests unit {f['unit_hint']!r} (unconfirmed)")
        if "dtype" in f and not attrs:
            parts.append(f"dtype={f['dtype']}")
        dt = f.get("datetime")
        if dt:
            parts.append(f"time {dt.get('min')}..{dt.get('max')} step={dt.get('resolution', dt.get('resolution_seconds'))}")
        for k in ("missing", "missing_fraction", "min", "max"):
            if k in f and f[k] not in (None, 0, 0.0):
                v = f[k]
                parts.append(f"{k}={v:.6g}" if isinstance(v, float) else f"{k}={v}")
        out.append("; ".join(parts)[:300])
    return out


def catalog_entry(o: KnowledgeObject, level: int = 0) -> dict[str, Any]:
    """Compact description of an object for model prompts.

    ``level`` trades detail for size: 0 full; 1 claims/concepts lose attributes; 2 claims are
    reduced to id and name and concepts to a short summary; 3 every summary and attribute is cut.
    """
    limit = 400 if level < 3 else 160
    minor = o.type in (ObjectType.claim, ObjectType.concept)
    entry: dict[str, Any] = {"id": o.id, "type": o.type.value, "name": o.name}
    if level >= 2 and o.type == ObjectType.claim:
        return entry
    entry["source"] = ",".join(o.source_ids)
    summary = o.summary if level < 2 or not minor else o.summary[:120]
    entry["summary"] = summary if level < 3 else summary[:100]
    entry["basis"] = o.basis.value
    if o.aliases:
        entry["aliases"] = o.aliases
    if level >= 1 and minor:
        return entry
    attrs = {k: _compact(v, limit) for k, v in o.attributes.items()
             if k in ATTR_KEYS_IN_CATALOG and v not in (None, "", [], {}) and k != "fields"}
    if o.attributes.get("fields"):
        lines = compact_fields(o.attributes["fields"])
        attrs["fields"] = lines if level < 3 else [ln[:120] for ln in lines]
    for k in ("sheet", "format", "dims"):
        if o.attributes.get(k) not in (None, "", [], {}):
            attrs[k] = o.attributes[k]
    if attrs:
        entry["attributes"] = attrs
    return entry


def deterministic_relations(objects: list[KnowledgeObject]) -> list[Relation]:
    """Documentation dataset -> profiled file (``describes``) when they name the same file."""
    rels: list[Relation] = []
    profiled = [o for o in objects if o.type == ObjectType.dataset and o.basis == Basis.measured]
    docs = [o for o in objects if o.type == ObjectType.dataset and o.basis != Basis.measured]
    for d in docs:
        names = {normalize_name(d.name), normalize_name(str(d.attributes.get("file") or ""))}
        names |= {normalize_name(a) for a in d.aliases}
        for p in profiled:
            fname = str(p.attributes.get("file", p.name))
            if normalize_name(fname) in names or normalize_name(fname.rsplit("/", 1)[-1]) in names:
                rels.append(Relation(
                    id=f"rel:describes:{short_hash(d.id + p.id)}", type=RelationType.describes, src=d.id, dst=p.id,
                    basis=Basis.measured, note="documentation names this data file",
                ))
    return rels


def _groups(objects: list[KnowledgeObject], budget: int = CATALOG_CHAR_BUDGET) -> list[list[KnowledgeObject]]:
    """Split the catalog into overlapping groups that fit the prompt budget.

    Related types share groups (methods with code and concepts; datasets with constraints and
    concepts; claims with methods). Within a family, objects are ordered by normalized name so
    same-named objects from different sources land in the same group.
    """
    entries = [(o, json.dumps(catalog_entry(o), ensure_ascii=False)) for o in objects]
    if sum(len(t) for _, t in entries) <= budget:
        return [objects]
    # split by type families, keeping related types together
    families = [
        {ObjectType.method, ObjectType.capability, ObjectType.concept},
        {ObjectType.dataset, ObjectType.constraint, ObjectType.concept},
        {ObjectType.claim, ObjectType.method, ObjectType.concept},
    ]
    groups = []
    for fam in families:
        members = [o for o in objects if o.type in fam]
        chunk: list[KnowledgeObject] = []
        size = 0
        for o in sorted(members, key=lambda x: normalize_name(x.name)):
            n = len(json.dumps(catalog_entry(o), ensure_ascii=False))
            if chunk and size + n > budget:
                groups.append(chunk)
                chunk, size = [], 0
            chunk.append(o)
            size += n
        if chunk:
            groups.append(chunk)
    return groups


def _gap_entry(gap: Gap) -> dict[str, Any]:
    return {"gap_id": gap.id, "subject_id": gap.subject_id, "description": gap.description,
            "severity": gap.severity.value}


def _reconcile_groups(objects: list[KnowledgeObject], gaps: list[Gap], evidence_sources: dict[str, str],
                      budget: int = CATALOG_CHAR_BUDGET) -> list[tuple[list[KnowledgeObject], list[Gap]]]:
    """Keep object overlap, but send each gap once with relevant catalog context.

    Reserve space for gaps, then split overflowing gap lists into additional
    requests. Nothing is truncated or omitted, including gaps without a subject.
    """
    groups = _groups(objects, budget=max(1, budget * 3 // 4))
    object_groups: dict[str, set[int]] = {}
    source_groups: dict[str, set[int]] = {}
    for i, group in enumerate(groups):
        for obj in group:
            object_groups.setdefault(obj.id, set()).add(i)
            for source in obj.source_ids:
                source_groups.setdefault(source, set()).add(i)
    assigned: list[list[Gap]] = [[] for _ in groups]
    loads = [0] * len(groups)
    for gap in gaps:
        candidates = object_groups.get(gap.subject_id or "", set())
        if not candidates:
            sources = {evidence_sources[eid] for eid in gap.evidence_ids if eid in evidence_sources}
            sources.add(gap.id.removeprefix("gap:").split("/", 1)[0])
            candidates = {i for source in sources for i in source_groups.get(source, set())}
        index = min(candidates or range(len(groups)), key=lambda i: (loads[i], i))
        assigned[index].append(gap)
        loads[index] += len(json.dumps(_gap_entry(gap), ensure_ascii=False)) + 1

    jobs: list[tuple[list[KnowledgeObject], list[Gap]]] = []
    for group, group_gaps in zip(groups, assigned, strict=True):
        base_size = sum(len(json.dumps(catalog_entry(o), ensure_ascii=False)) + 1 for o in group)
        current: list[Gap] = []
        size = base_size
        emitted_group = False
        for gap in group_gaps:
            n = len(json.dumps(_gap_entry(gap), ensure_ascii=False)) + 1
            if current and size + n > budget:
                jobs.append((group, current))
                emitted_group = True
                current, size = [], base_size
            if base_size + n > budget:
                # An unusually long gap gets a separate request with as many
                # relevant objects as fit, while the full group is still sent.
                sources = {evidence_sources[eid] for eid in gap.evidence_ids if eid in evidence_sources}
                context: list[KnowledgeObject] = []
                context_size = n
                for obj in sorted(group, key=lambda o: o.id != gap.subject_id):
                    if obj.id != gap.subject_id and not sources.intersection(obj.source_ids):
                        continue
                    obj_size = len(json.dumps(catalog_entry(obj), ensure_ascii=False)) + 1
                    if context_size + obj_size <= budget:
                        context.append(obj)
                        context_size += obj_size
                jobs.append((context, [gap]))
            else:
                current.append(gap)
                size += n
        if current or not emitted_group:
            jobs.append((group, current))
    return jobs


def _prompt(project: Project, group: list[KnowledgeObject], gaps: list[Gap]) -> str:
    cfg = project.config
    lines = [f"Project goal: {cfg.goal}"]
    if cfg.tasks:
        lines.append("Research tasks:")
        lines += [f"- {t.title}: {t.prompt}" for t in cfg.tasks]
    lines.append("\nCatalog of knowledge objects (one JSON object per line):")
    lines += [json.dumps(catalog_entry(o), ensure_ascii=False) for o in group]
    if gaps:
        lines.append("\nOpen gaps reported during extraction:")
        lines += [json.dumps(_gap_entry(g), ensure_ascii=False) for g in gaps]
    lines.append("\nPropose relations, umbrella concepts, gap resolutions and new cross-source gaps.")
    return "\n".join(lines)


def run_reconcile(project: Project, llm: LLMClient, force: bool = False, **_: Any) -> dict[str, Any]:
    kb = project.kb
    cfg = project.config
    model = cfg.model
    actor = f"{cfg.actor}+{model}"

    # reset previous reconcile output (umbrella concepts, relations, reconcile gaps, resolutions)
    kb.delete_objects([o.id for o in kb.objects() if o.produced_by.endswith("+reconcile")])
    kb.clear_relations()
    kb.clear_validation("reconcile")
    with kb.tx() as c:
        c.execute("DELETE FROM gaps WHERE id LIKE 'gap:reconcile/%'")
        c.execute("UPDATE gaps SET resolved_by=NULL, resolution=NULL WHERE resolved_by LIKE 'reconcile:%'")

    objects = [o for o in kb.objects() if o.status == ObjectStatus.active]
    ids = {o.id for o in objects}
    open_gaps = [g for g in kb.gaps() if not g.resolved_by]
    gap_ids = {g.id for g in open_gaps}

    relations: dict[str, Relation] = {r.id: r for r in deterministic_relations(objects)}
    umbrellas: dict[str, KnowledgeObject] = {}
    resolutions: dict[str, tuple[list[str], str]] = {}
    new_gaps: list[Gap] = []
    records: list[ValidationRecord] = []
    system = skill_body("reconcile-knowledge")

    gap_evidence = kb.evidence_by_ids(eid for g in open_gaps for eid in g.evidence_ids)
    jobs = _reconcile_groups(objects, open_gaps, {eid: ev.source_id for eid, ev in gap_evidence.items()},
                             budget=max(1, CATALOG_CHAR_BUDGET - len(_prompt(project, [], [])) - 128))

    def request(job: tuple[list[KnowledgeObject], list[Gap]]) -> ReconcileResult:
        group, group_gaps = job
        project.emit("reconcile", "progress", f"relating {len(group)} objects and {len(group_gaps)} gaps")
        prompt = _prompt(project, group, group_gaps)
        if len(prompt) > CATALOG_CHAR_BUDGET:
            project.emit("reconcile", "warning", "A single catalog entry or gap exceeds the request budget; retained in full.")
        return llm.structured(prompt, ReconcileResult, system=system, model=model,
                              max_tokens=20000, tool_name="submit_reconciliation",
                              tool_description="Submit relations, umbrella concepts, gap resolutions and new gaps.")

    with ThreadPoolExecutor(max_workers=max(1, llm.settings.max_concurrency)) as pool:
        # map preserves group order, so overlapping proposals are applied
        # deterministically on the main thread after concurrent model calls.
        results = list(pool.map(request, jobs))
    for result in results:
        name_to_umbrella: dict[str, str] = {}
        for u in result.umbrella_concepts:
            members = sorted(set(u.member_ids))
            if len(members) < 2 or not set(members) <= ids:
                records.append(ValidationRecord(id=f"val:reconcile:umbrella:{slugify(u.name)}", stage="reconcile",
                                                target_id=u.name, check="umbrella_members", status="warn",
                                                detail="dropped: needs at least two active members and no inactive or unknown members",
                                                at=now_iso()))
                continue
            uid = f"concept:shared/{slugify(u.name, 50)}"
            name_to_umbrella[u.name] = uid
            src_ids = sorted({s for m in members for s in next(o for o in objects if o.id == m).source_ids})
            umbrellas[uid] = KnowledgeObject(
                id=uid, type=ObjectType.concept, name=u.name, summary=u.summary, basis=Basis.inferred,
                basis_note="Umbrella concept grouping variants found in several sources: " + ", ".join(members),
                source_ids=src_ids, produced_by=f"{actor}+reconcile", attributes={"members": members},
            )
            for m in members:
                rid = f"rel:variant_of:{short_hash(m + uid)}"
                relations[rid] = Relation(id=rid, type=RelationType.variant_of, src=m, dst=uid, basis=Basis.inferred,
                                          note="member of umbrella concept")
        known = ids | set(umbrellas)
        for r in result.relations:
            src = name_to_umbrella.get(r.src, r.src)
            dst = name_to_umbrella.get(r.dst, r.dst)
            if src not in known or dst not in known or src == dst:
                records.append(ValidationRecord(
                    id=f"val:reconcile:rel:{short_hash(r.type + r.src + r.dst)}", stage="reconcile",
                    target_id=f"{r.src}->{r.dst}", check="relation_ids", status="warn",
                    detail=f"dropped {r.type}: unknown or identical endpoints", at=now_iso()))
                continue
            if r.type in ("same_as", "possibly_same_as", "conflicts_with"):
                src, dst = sorted([src, dst])
            rid = f"rel:{r.type}:{short_hash(src + dst)}"
            prev = relations.get(rid)
            note = r.note if not prev or not prev.note or prev.basis == Basis.measured else prev.note
            relations[rid] = Relation(id=rid, type=RelationType(r.type), src=src, dst=dst, basis=Basis.inferred,
                                      note=note or (prev.note if prev else ""))
        for res in result.gap_resolutions:
            by = res.resolved_by
            if res.gap_id in gap_ids and by and set(by) <= known:
                resolutions[res.gap_id] = (by, res.explanation)
            else:
                records.append(ValidationRecord(
                    id=f"val:reconcile:gap:{short_hash(res.gap_id)}", stage="reconcile", target_id=res.gap_id,
                    check="gap_resolution", status="warn", detail="dropped: unknown gap or no existing resolving object",
                    at=now_iso()))
        for ng in result.new_gaps:
            subject = ng.subject_id if ng.subject_id in known else None
            gid = f"gap:reconcile/{slugify(ng.description, 70)}"
            new_gaps.append(Gap(id=gid, subject_id=subject, description=ng.description, severity=Severity(ng.severity),
                                suggestion=ng.suggestion))

    kb.upsert_objects(umbrellas.values())
    kb.upsert_relations(relations.values())
    kb.upsert_gaps(new_gaps)
    updated = []
    for g in kb.gaps():
        if g.id in resolutions:
            by, why = resolutions[g.id]
            g.resolved_by = "reconcile:" + ",".join(by)
            g.resolution = why
            updated.append(g)
    kb.upsert_gaps(updated)
    kb.add_validation(records)
    by_type: dict[str, int] = {}
    for r in relations.values():
        by_type[r.type.value] = by_type.get(r.type.value, 0) + 1
    open_after = [g for g in kb.gaps() if not g.resolved_by]
    project.emit("reconcile", "item", f"{len(relations)} relations, {len(umbrellas)} umbrella concepts, "
                 f"{len(updated)} gaps resolved, {len(new_gaps)} new gaps, {len(open_after)} open")
    return {"relations": len(relations), "relations_by_type": by_type, "umbrella_concepts": len(umbrellas),
            "gaps_resolved": len(updated), "new_gaps": len(new_gaps), "open_gaps": len(open_after),
            "open_blocking": sum(g.severity == Severity.blocking for g in open_after),
            "dropped_proposals": len(records)}



# ============================================================== incremental reconcile
INCREMENTAL_NOTE = """
# Incremental mode

Only the objects marked NEW were added since the catalog was last reconciled. Existing relations
stay as they are. Propose only relations that involve at least one NEW object, resolve open gaps
that a NEW object answers, and add new gaps only if a NEW object creates one. Do not propose
umbrella concepts unless a NEW object is a variant of an existing definition.
"""


def reconcile_added(project: Project, llm: LLMClient, new_ids: set[str]) -> dict[str, Any]:
    """Relate newly added objects to the existing catalog without re-deriving existing relations."""
    kb = project.kb
    model = project.config.model
    all_objects = kb.objects()
    objects = [o for o in all_objects if o.status == ObjectStatus.active]
    reopen_gaps_resolved_by(project, {o.id for o in all_objects if o.status != ObjectStatus.active})
    ids = {o.id for o in objects}
    new_ids = new_ids & ids
    if not new_ids:
        return {"relations_added": 0, "gaps_resolved": 0, "new_gaps": 0}
    open_gaps = [g for g in kb.gaps() if not g.resolved_by]
    lines = [f"Project goal: {project.config.goal}", "", "Catalog (NEW objects are marked):"]
    for o in objects:
        entry = catalog_entry(o)
        if o.id in new_ids:
            entry["NEW"] = True
        lines.append(json.dumps(entry, ensure_ascii=False))
    lines.append("\nOpen gaps:")
    lines += [json.dumps({"gap_id": g.id, "subject_id": g.subject_id, "description": g.description}, ensure_ascii=False)
              for g in open_gaps] or ["- none"]
    result = llm.structured("\n".join(lines), ReconcileResult, system=skill_body("reconcile-knowledge") + INCREMENTAL_NOTE,
                            model=model, max_tokens=12000, tool_name="submit_reconciliation",
                            tool_description="Submit relations, gap resolutions and new gaps for the new objects.")
    existing = {r.id for r in kb.relations()}
    added: list[Relation] = []
    for r in result.relations:
        if r.src not in ids or r.dst not in ids or r.src == r.dst or not ({r.src, r.dst} & new_ids):
            continue
        src, dst = (sorted([r.src, r.dst]) if r.type in ("same_as", "possibly_same_as", "conflicts_with")
                    else (r.src, r.dst))
        rid = f"rel:{r.type}:{short_hash(src + dst)}"
        if rid not in existing:
            added.append(Relation(id=rid, type=RelationType(r.type), src=src, dst=dst, basis=Basis.inferred, note=r.note))
    kb.upsert_relations(added)
    gap_ids = {g.id for g in open_gaps}
    resolved = []
    for res in result.gap_resolutions:
        by = res.resolved_by
        if res.gap_id in gap_ids and by and set(by) <= ids and set(by) & new_ids:
            g = next(x for x in open_gaps if x.id == res.gap_id)
            g.resolved_by, g.resolution = "reconcile:" + ",".join(by), res.explanation
            resolved.append(g)
    kb.upsert_gaps(resolved)
    new_gaps = []
    for ng in result.new_gaps:
        subject = ng.subject_id if ng.subject_id in ids else None
        new_gaps.append(Gap(id=f"gap:reconcile/{slugify(ng.description, 70)}", subject_id=subject,
                            description=ng.description, severity=Severity(ng.severity), suggestion=ng.suggestion))
    kb.upsert_gaps(new_gaps)
    return {"relations_added": len(added), "gaps_resolved": len(resolved), "new_gaps": len(new_gaps)}


def reopen_gaps_resolved_by(project: Project, removed_ids: set[str]) -> int:
    """Gaps whose resolution relied on a removed object become open again."""
    kb = project.kb
    reopened = []
    for g in kb.gaps():
        if g.resolved_by and g.resolved_by.startswith("reconcile:") and \
                set(g.resolved_by.removeprefix("reconcile:").split(",")) & removed_ids:
            g.resolved_by, g.resolution = None, None
            reopened.append(g)
    kb.upsert_gaps(reopened, keep_resolution=False)
    return len(reopened)
