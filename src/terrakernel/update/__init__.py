"""Update: keep a generated repository in sync when its materials change.

1. Ingest again and diff evidence by stable IDs (added / changed / removed units).
2. Patch-extract: only objects grounded in changed evidence are re-examined; the model
   decides per object whether the change matters (keep / update / remove), and new
   evidence can add objects. Unaffected objects stay byte-identical. Tables are
   re-profiled; new sources are extracted in full.
3. Patch-reconcile: relations and gap resolutions that involve changed objects are
   re-checked (keep / update / remove; reopen gaps).
4. Patch-plan: dataset, parameter, convention and skill plan items that depend on changed
   objects are updated; everything else in the plan is kept.
5. Recompile. Model calls are cached by request content, so artifacts whose inputs did not
   change are rebuilt from cache and their files are not touched.
6. Validate, and write an impact report: predicted impact from the lineage graph versus
   the files that actually changed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from terrakernel.builtin import skill_body
from terrakernel.extract import (
    _capability_facts,
    _format_evidence,
    _IdAllocator,
    _parse_value,
    extract_source,
    profile_table_source,
)
from terrakernel.extract.grounding import check_refs
from terrakernel.extract.schemas import ExtractedGap, ExtractedObject
from terrakernel.lineage import impacted_artifacts, load_lineage
from terrakernel.llm.client import LLMClient
from terrakernel.models import (
    Basis,
    EvidenceLink,
    Gap,
    KnowledgeObject,
    LinkRole,
    ObjectStatus,
    ObjectType,
    Relation,
    Severity,
    SourceKind,
)
from terrakernel.plan import load_spec, save_spec, validate_plan
from terrakernel.plan.spec import ConventionsPlan, DatasetPlan, ParameterPlan, SkillPlan, ToolPlan
from terrakernel.project import Project
from terrakernel.reconcile import catalog_entry, reconcile_added, reopen_gaps_resolved_by
from terrakernel.util import normalize_name, now_iso, slugify

TRACKED_DIRS = ("knowledge", ".agents", ".claude", "tools", "tests")
TRACKED_FILES = ("AGENTS.md", "CLAUDE.md", ".mcp.json", ".codex/config.toml", "pyproject.toml")


# ============================================================== snapshots and diffs
def semantic_fingerprint(o: KnowledgeObject) -> str:
    payload = json.dumps({"type": o.type.value, "name": o.name, "attributes": o.attributes, "basis": o.basis.value,
                          "status": o.status.value}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def snapshot_objects(project: Project) -> dict[str, KnowledgeObject]:
    return {o.id: o for o in project.kb.objects()}


def snapshot_files(repo: Path) -> dict[str, str]:
    from terrakernel.util import _normalize_volatile

    out = {}
    paths = [repo / f for f in TRACKED_FILES if (repo / f).exists()]
    for d in TRACKED_DIRS:
        if (repo / d).exists():
            paths += [p for p in (repo / d).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = p.read_bytes().hex()
        out[p.relative_to(repo).as_posix()] = hashlib.sha256(_normalize_volatile(text).encode()).hexdigest()
    return out


def diff_files(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    return {
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "changed": sorted(k for k in set(before) & set(after) if before[k] != after[k]),
    }


def attribute_diff(old: KnowledgeObject, new: KnowledgeObject) -> list[str]:
    fields = []
    for k in sorted(set(old.attributes) | set(new.attributes)):
        if json.dumps(old.attributes.get(k), sort_keys=True, default=str) != json.dumps(new.attributes.get(k),
                                                                                         sort_keys=True, default=str):
            fields.append(k)
    if old.name != new.name:
        fields.append("name")
    if old.status != new.status:
        fields.append("status")
    return fields


# ============================================================== patch extraction
class ObjectUpdate(BaseModel):
    id: str
    action: Literal["keep", "update", "remove"]
    reason: str
    object: ExtractedObject | None = Field(default=None, description="The full updated object when action is update")


class PatchResult(BaseModel):
    updates: list[ObjectUpdate]
    added: list[ExtractedObject] = Field(default_factory=list)
    gaps: list[ExtractedGap] = Field(default_factory=list, description="Complete list of open gaps about the affected and added objects")


PATCH_INSTRUCTIONS = """
# Update mode

The source changed after the knowledge below was extracted. You are given the affected
objects (as previously extracted), the changed evidence units (old and new text), and the
current evidence of the source.

For each affected object return exactly one update:
- `keep`: the change does not alter this object's meaning, attributes or grounding.
- `update`: return the complete corrected object (same type; keep the name unless the source
  renamed it). Ground it in the current evidence, with verbatim quotes.
- `remove`: the source no longer supports the object.

Add new objects only for information that appears in added or changed evidence and is not
already covered. Return the complete list of open gaps about the affected and added
objects (gaps answered by the new text must not be returned).
"""


def patch_source(project: Project, llm: LLMClient, source_id: str, old_evidence: dict[str, str],
                 diff: dict[str, list[str]], model: str) -> dict[str, Any]:
    kb = project.kb
    cfg = project.config
    source = kb.source(source_id)
    evidence = kb.evidence(source_id)
    ev_map = {e.id: e for e in evidence}
    touched = set(diff.get("changed", [])) | set(diff.get("removed", []))
    affected = [o for o in kb.objects() if source_id in o.source_ids and o.source_ids == [source_id]
                and any(lk.evidence_id in touched for lk in kb.links(o.id))]
    if source.kind in (SourceKind.table, SourceKind.array):
        old = [o for o in kb.objects() if o.source_ids == [source_id]]
        kb.delete_objects([o.id for o in old])
        objs, links = profile_table_source(source, evidence, cfg.actor)
        kb.upsert_objects(objs)
        kb.add_links(links)
        return {"source": source_id, "mode": "reprofiled", "affected": [o.id for o in old]}
    if not affected and not diff.get("added"):
        return {"source": source_id, "mode": "no_affected_objects", "affected": []}

    changed_units = []
    for eid in sorted(touched | set(diff.get("added", []))):
        old_text = old_evidence.get(eid)
        new = ev_map.get(eid)
        changed_units.append({"id": eid, "status": "removed" if new is None else ("added" if old_text is None else "changed"),
                              "old": old_text, "new": new.content if new else None})
    prompt = [
        f"Project goal: {cfg.goal}", f"Source: {source.path}", "",
        "Affected objects (previous extraction):",
        *[json.dumps({**catalog_entry(o), "attributes": o.attributes}, ensure_ascii=False, default=str) for o in affected],
        "", "Changed evidence units:", *[json.dumps(u, ensure_ascii=False) for u in changed_units], "",
        "Current evidence of the source:", *[_format_evidence(e) for e in evidence],
    ]
    result = llm.structured("\n".join(prompt), PatchResult, system=skill_body("extract-knowledge") + PATCH_INSTRUCTIONS,
                            model=model, max_tokens=16000, tool_name="submit_patch",
                            tool_description="Submit object updates, added objects and gaps.")
    actor = f"{cfg.actor}+{model}"
    affected_ids = {o.id for o in affected}
    applied: dict[str, list[str]] = {"kept": [], "updated": [], "removed": [], "added": [], "rejected": []}
    alloc = _IdAllocator(o.id for o in kb.objects())
    seen = set()
    for up in result.updates:
        if up.id not in affected_ids or up.id in seen:
            continue
        seen.add(up.id)
        if up.action == "keep":
            applied["kept"].append(up.id)
            continue
        if up.action == "remove":
            kb.delete_objects([up.id])
            applied["removed"].append(up.id)
            continue
        eo = up.object
        if eo is None:
            applied["rejected"].append(f"{up.id}: update without object")
            continue
        rep = check_refs([(r.evidence_id, r.quote) for r in eo.evidence], ev_map)
        if not rep.ok:
            applied["rejected"].append(f"{up.id}: {'; '.join(rep.problems[:3])}")
            continue
        _store_object(project, up.id, eo, rep.accepted, source, actor)
        applied["updated"].append(up.id)
    for oid in affected_ids - seen:  # the model did not mention it: keep, but flag for review
        applied["kept"].append(oid)
    for eo in result.added:
        rep = check_refs([(r.evidence_id, r.quote) for r in eo.evidence], ev_map)
        if not rep.ok:
            applied["rejected"].append(f"new {eo.name}: {'; '.join(rep.problems[:3])}")
            continue
        oid = alloc.new(eo.type, source_id, eo.name)
        _store_object(project, oid, eo, rep.accepted, source, actor)
        applied["added"].append(oid)
    # gaps about affected/added objects are replaced by the returned list
    scope = (affected_ids | set(applied["added"])) - set(applied["removed"])
    current = {o.id: o for o in kb.objects() if o.id in scope}
    with kb.tx() as c:
        for oid in affected_ids | set(applied["added"]):
            c.execute("DELETE FROM gaps WHERE subject_id=? AND resolved_by IS NULL", (oid,))
    new_gaps = []
    for g in result.gaps:
        subject = next((o.id for o in current.values() if normalize_name(o.name) == normalize_name(g.subject)), None)
        gid = f"gap:{source_id}/{slugify(g.subject + ' ' + (g.field or '') + ' ' + g.description, 70)}"
        new_gaps.append(Gap(id=gid, subject_id=subject, field=g.field,
                            description=g.description if subject else f"{g.subject}: {g.description}",
                            severity=Severity(g.severity), suggestion=g.suggestion,
                            evidence_ids=[e for e in g.evidence_ids if e in ev_map]))
    kb.upsert_gaps(new_gaps)
    return {"source": source_id, "mode": "patched", "affected": sorted(affected_ids), **applied}


def _store_object(project: Project, oid: str, eo: ExtractedObject, accepted: list[tuple[str, float]], source: Any,
                  actor: str) -> None:
    kb = project.kb
    attrs = {a.key: _parse_value(a.value) for a in eo.attributes}
    attrs["_evidence_ids"] = [eid for eid, _ in accepted]
    obj = KnowledgeObject(id=oid, type=ObjectType(eo.type), name=eo.name.strip(), summary=eo.summary.strip(),
                          aliases=[a for a in eo.aliases if a and a != eo.name], attributes=attrs, basis=Basis(eo.basis),
                          basis_note=eo.basis_note, status=ObjectStatus.active, source_ids=[source.id],
                          produced_by=actor)
    if obj.type == ObjectType.capability:
        _capability_facts(obj, {e.id: e for e in kb.evidence(source.id)}, source)
    obj.attributes.pop("_evidence_ids", None)
    with kb.tx() as c:
        c.execute("DELETE FROM evidence_links WHERE object_id=?", (oid,))
    kb.upsert_objects([obj])
    quotes = {r.evidence_id: r.quote for r in eo.evidence}
    role = LinkRole.implements if obj.type == ObjectType.capability else (
        LinkRole.defines if obj.type in (ObjectType.method, ObjectType.concept) else LinkRole.supports)
    kb.add_links([EvidenceLink(object_id=oid, evidence_id=eid, role=role, quote=quotes.get(eid, ""),
                               match_score=round(score, 1)) for eid, score in accepted])


# ============================================================== patch reconcile
class RelationUpdate(BaseModel):
    id: str
    action: Literal["keep", "update", "remove"]
    note: str = ""


class GapUpdate(BaseModel):
    id: str
    action: Literal["keep", "reopen", "update"]
    resolution: str = ""


class ReconcilePatch(BaseModel):
    relations: list[RelationUpdate]
    gaps: list[GapUpdate]


VALUE_TOKEN_RE = None


def removed_value_tokens(old: dict[str, KnowledgeObject], new: dict[str, KnowledgeObject], changed: set[str]) -> set[str]:
    """Dates and numbers that changed objects stated before the update but no longer state."""
    import re

    global VALUE_TOKEN_RE
    if VALUE_TOKEN_RE is None:
        VALUE_TOKEN_RE = re.compile(r"\d{4}-\d{2}-\d{2}|\d+(?:\.\d+)?")

    def tokens(o: KnowledgeObject) -> set[str]:
        text = json.dumps(o.attributes, default=str) + " " + o.summary
        return {t for t in VALUE_TOKEN_RE.findall(text) if len(t) >= 3}

    out: set[str] = set()
    for oid in changed:
        if oid in old and oid in new:
            out |= tokens(old[oid]) - tokens(new[oid])
    return out


def patch_reconcile(project: Project, llm: LLMClient, changed: set[str], model: str,
                    stale_tokens: set[str] | None = None) -> dict[str, Any]:
    kb = project.kb
    stale_tokens = stale_tokens or set()
    # A relation is affected when an endpoint changed, or when its note talks about a changed
    # object's content (notes often restate facts from a third object, e.g. a schedule date).
    objs_all = {o.id: o for o in kb.objects()}
    changed_terms = set()
    for oid in changed:
        o = objs_all.get(oid)
        if o:
            changed_terms |= {normalize_name(o.name), *(normalize_name(a) for a in o.aliases)}
    rels = [r for r in kb.relations() if r.src in changed or r.dst in changed
            or any(t and t in normalize_name(r.note) for t in changed_terms if len(t) > 6)
            or any(tok in r.note for tok in stale_tokens)]
    neighbours = {r.src for r in rels} | {r.dst for r in rels}
    rels += [r for r in kb.relations() if r not in rels and (r.src in neighbours and r.dst in neighbours)]
    gaps = [g for g in kb.gaps() if g.resolved_by and (any(c in g.resolved_by for c in changed)
                                                         or any(tok in (g.resolution or "") for tok in stale_tokens))]
    if not rels and not gaps:
        return {"relations": 0, "gaps": 0}
    objs = {o.id: o for o in kb.objects()}
    involved = sorted({r.src for r in rels} | {r.dst for r in rels} | changed)
    prompt = [
        "Some knowledge objects changed (marked CHANGED). Re-check the relations and gap resolutions below.",
        "For each relation: keep it, update its note (same type and endpoints), or remove it if it no longer holds.",
        "A note must be updated when it restates a fact (a date, value, unit or rule) that a CHANGED object now states "
        "differently, even if the relation's endpoints did not change.",
        "For each resolved gap: keep the resolution, update its explanation, or reopen the gap if it is no longer answered.",
        "", "Objects:",
        *[json.dumps({**catalog_entry(objs[i]), "attributes": objs[i].attributes, "CHANGED": i in changed},
                     ensure_ascii=False, default=str) for i in involved if i in objs],
        "", "Relations:", *[json.dumps({"id": r.id, "type": r.type.value, "src": r.src, "dst": r.dst, "note": r.note})
                            for r in rels],
        "", "Resolved gaps:", *[json.dumps({"id": g.id, "description": g.description, "resolved_by": g.resolved_by,
                                            "resolution": g.resolution}) for g in gaps],
    ]
    res = llm.structured("\n".join(prompt), ReconcilePatch, system=skill_body("reconcile-knowledge"), model=model,
                         max_tokens=8000, tool_name="submit_reconcile_patch",
                         tool_description="Submit relation and gap updates.")
    by_id = {r.id: r for r in rels}
    counts = {"kept": 0, "updated": 0, "removed": 0, "reopened": 0, "gap_updated": 0}
    keep: list[Relation] = []
    for u in res.relations:
        r = by_id.get(u.id)
        if r is None:
            continue
        if u.action == "remove":
            with kb.tx() as c:
                c.execute("DELETE FROM relations WHERE id=?", (r.id,))
            counts["removed"] += 1
        elif u.action == "update" and u.note:
            r.note = u.note
            keep.append(r)
            counts["updated"] += 1
        else:
            counts["kept"] += 1
    kb.upsert_relations(keep)
    gmap = {g.id: g for g in gaps}
    upd = []
    for u in res.gaps:
        g = gmap.get(u.id)
        if g is None:
            continue
        if u.action == "reopen":
            g.resolved_by, g.resolution = None, None
            counts["reopened"] += 1
            upd.append(g)
        elif u.action == "update" and u.resolution:
            g.resolution = u.resolution
            counts["gap_updated"] += 1
            upd.append(g)
    kb.upsert_gaps(upd, keep_resolution=False)
    return counts


# ============================================================== patch plan
class PlanPatch(BaseModel):
    summary: str | None = Field(default=None, description="Updated repository summary, or null if unchanged")
    tools: list[ToolPlan] = Field(default_factory=list)
    datasets: list[DatasetPlan] = Field(default_factory=list)
    parameters: list[ParameterPlan] = Field(default_factory=list)
    conventions: ConventionsPlan | None = None
    skills: list[SkillPlan] = Field(default_factory=list)


def patch_plan(project: Project, llm: LLMClient, changed: set[str], model: str,
               stale_tokens: set[str] | None = None) -> dict[str, Any]:
    spec = load_spec(project)
    plan = spec.plan
    stale_tokens = stale_tokens or set()

    def hit(ids: list[str]) -> bool:
        return bool(set(ids) & changed)

    datasets = [d for d in plan.datasets if hit([d.profile_object_id, *d.evidence_object_ids,
                                                 *[x for c in d.value_columns for x in c.evidence_object_ids]])]
    params = [p for p in plan.parameters if hit(p.evidence_object_ids)]
    conv = plan.conventions if hit(plan.conventions.evidence_object_ids) else None
    skill_objs = {a.id.removeprefix("skill:"): a.objects for a in spec.artifacts if a.kind == "skill"}
    skills = [s for s in plan.skills if hit(skill_objs.get(s.name, []))]
    tools = [t for t in plan.tools if any(tok in t.model_dump_json() for tok in stale_tokens)]
    if not (datasets or params or conv or skills or tools):
        return {"patched": []}
    objs = {o.id: o for o in project.kb.objects()}
    prompt = [
        "The knowledge objects marked CHANGED were updated after the repository plan was made. Return updated "
        "versions of ONLY the plan items listed below, changed only where the CHANGED objects require it. Keep names "
        "and everything else identical. Return the summary only if it states something the change made wrong.",
        "", "Changed objects:", *[json.dumps({**catalog_entry(objs[i]), "attributes": objs[i].attributes},
                                             ensure_ascii=False, default=str) for i in sorted(changed) if i in objs],
        "", f"Current summary: {plan.summary}",
        "", "Plan items to review:",
        *[f"dataset: {d.model_dump_json()}" for d in datasets], *[f"parameter: {p.model_dump_json()}" for p in params],
        *([f"conventions: {conv.model_dump_json()}"] if conv else []), *[f"skill: {s.model_dump_json()}" for s in skills],
        *[f"tool (its text restates a value the change removed: {sorted(stale_tokens)}; make it generic): "
          f"{t.model_dump_json()}" for t in tools],
    ]
    before, _ = validate_plan(plan, project)
    patch = llm.structured("\n".join(prompt), PlanPatch, system=skill_body("plan-repository"), model=model,
                           max_tokens=16000, tool_name="submit_plan_patch", tool_description="Submit updated plan items.")
    result = _apply_patch_once(project, spec, plan, patch, datasets, params, conv, skills, before, tools)
    if result.get("rejected"):
        repair = prompt + ["", "Your previous patch introduced these problems:", *result["rejected"],
                           "", "Previous patch:", patch.model_dump_json(), "", "Return the corrected patch."]
        patch = llm.structured("\n".join(repair), PlanPatch, system=skill_body("plan-repository"), model=model,
                               max_tokens=16000, tool_name="submit_plan_patch",
                               tool_description="Submit updated plan items.")
        result = _apply_patch_once(project, spec, plan, patch, datasets, params, conv, skills, before, tools)
    return result


def _apply_patch_once(project: Project, spec: Any, plan: Any, patch: PlanPatch, datasets: list, params: list,
                      conv: Any, skills: list, before: list[str], tools: list | None = None) -> dict[str, Any]:
    candidate = plan.model_copy(deep=True)
    patched = []
    for t in patch.tools:
        for i, old in enumerate(candidate.tools):
            if old.name == t.name and old in (tools or []) and t.strategy == old.strategy:
                candidate.tools[i] = t
                patched.append(f"tool:{t.name}")
    for d in patch.datasets:
        for i, old in enumerate(candidate.datasets):
            if old.name == d.name and old in datasets:
                candidate.datasets[i] = d
                patched.append(f"dataset:{d.name}")
    for p in patch.parameters:
        for i, old in enumerate(candidate.parameters):
            if old.name == p.name and old in params:
                candidate.parameters[i] = p
                patched.append(f"parameter:{p.name}")
    if patch.conventions and conv:
        candidate.conventions = patch.conventions
        patched.append("conventions")
    for s_ in patch.skills:
        for i, old in enumerate(candidate.skills):
            if old.name == s_.name and old in skills:
                candidate.skills[i] = s_
                patched.append(f"skill:{s_.name}")
    if patch.summary:
        candidate.summary = patch.summary
        patched.append("summary")
    fix, _ = validate_plan(candidate, project)
    new_issues = [f for f in fix if f not in before]
    if new_issues:
        return {"patched": [], "rejected": new_issues[:10]}
    from terrakernel.plan import build_spec

    refreshed = build_spec(candidate, project, spec.issues, spec.generated_by)
    save_spec(project, refreshed)
    return {"patched": patched}


# ============================================================== orchestration
def attach_answers_to_docs(project: Project, answer_objects: list[KnowledgeObject]) -> list[str]:
    """Document each answer wherever the question's subject is documented (deterministic rule)."""
    if not answer_objects:
        return []
    spec = load_spec(project)
    gaps = {g.id: g for g in project.kb.gaps()}
    touched = []
    for o in answer_objects:
        gap = gaps.get(o.attributes.get("answers_gap") or "")
        subject = gap.subject_id if gap else None
        targets = [d for d in spec.plan.docs if subject and subject in d.object_ids] or (
            [d for d in spec.plan.docs if d.okf_type.lower() == "convention"][:1])
        for d in targets:
            if o.id not in d.object_ids:
                d.object_ids.append(o.id)
                touched.append(d.path)
    if touched:
        from terrakernel.plan import build_spec

        refreshed = build_spec(spec.plan, project, spec.issues, spec.generated_by)
        save_spec(project, refreshed)
    return sorted(set(touched))


def run_update(project: Project, llm: LLMClient, related_objects: set[str] | None = None) -> dict[str, Any]:
    from terrakernel.compile import run_compile
    from terrakernel.runner import run_ingest
    from terrakernel.validate import run_validate

    kb = project.kb
    model = project.config.model
    report: dict[str, Any] = {"started": now_iso()}
    usage_before = llm.usage.as_dict()
    old_objects = snapshot_objects(project)
    old_fp = {i: semantic_fingerprint(o) for i, o in old_objects.items()}
    old_evidence = {e.id: e.content for e in kb.evidence()}
    files_before = snapshot_files(project.repo)
    lineage = load_lineage(project)

    project.emit("update", "progress", "re-reading materials")
    ingest = run_ingest(project, llm)
    diff = kb.get_meta("last_ingest_diff", {})
    report["sources"] = {"changed": ingest["changed"], "removed": ingest["removed"]}
    report["evidence"] = {sid: {k: v for k, v in d.items() if v} for sid, d in diff.items()}
    if not diff and not project.load_state().get("pending_update_objects"):
        report["result"] = "no changes in the materials"
        project.emit("update", "item", "no changes in the materials")
        return report

    patches = []
    for sid, d in diff.items():
        if d.get("new_source"):
            project.emit("update", "progress", f"extracting new source {sid}")
            patches.append({"source": sid, "mode": "new_source", **extract_source(project, llm, kb.source(sid), model)})
        elif d.get("removed") == ["*"]:
            patches.append({"source": sid, "mode": "source_removed"})
        else:
            project.emit("update", "progress", f"re-examining objects affected by changes in {sid}")
            patches.append(patch_source(project, llm, sid, old_evidence, d, model))
    report["patch_extract"] = patches

    new_objects = snapshot_objects(project)
    changed = {i for i in set(old_fp) & set(new_objects) if semantic_fingerprint(new_objects[i]) != old_fp[i]}
    added = set(new_objects) - set(old_fp)
    removed = set(old_fp) - set(new_objects)
    report["objects"] = {
        "changed": [{"id": i, "fields": attribute_diff(old_objects[i], new_objects[i])} for i in sorted(changed)],
        "added": sorted(added), "removed": sorted(removed),
        "unchanged": len(set(old_fp) & set(new_objects)) - len(changed),
    }
    for c in report["objects"]["changed"]:
        project.emit("update", "item", f"object changed: {c['id']} ({', '.join(c['fields']) or 'summary'})")

    if added or removed:
        project.emit("update", "progress", f"relating {len(added)} new object(s) to the catalog")
        report["reconcile"] = {"mode": "incremental", "reopened_gaps": reopen_gaps_resolved_by(project, removed),
                               **reconcile_added(project, llm, added)}
    if changed:
        stale = removed_value_tokens(old_objects, new_objects, changed)
        report["stale_values"] = sorted(stale)
        report["reconcile_patch"] = patch_reconcile(project, llm, changed, model, stale)

    touched = changed | added | removed | (related_objects or set())
    answers = [new_objects[i] for i in added if new_objects[i].basis == Basis.human_confirmed]
    if answers:
        report["answers"] = [{"object": o.id, "answers_gap": o.attributes.get("answers_gap")} for o in answers]
        touched |= {g.subject_id for g in kb.gaps() if g.subject_id and any(
            o.attributes.get("answers_gap") == g.id for o in answers)}
    state = project.load_state()
    pending = set(state.get("pending_update_objects", [])) & set(new_objects) | (
        set(state.get("pending_update_objects", [])) - set(new_objects))
    if pending:
        report["resumed_pending"] = sorted(pending)
        touched |= pending
    if lineage:
        predicted = impacted_artifacts(lineage, touched)
        report["predicted_impact"] = {aid: reasons for aid, reasons in sorted(predicted.items())}
    if touched:
        report["plan"] = patch_plan(project, llm, touched, model, set(report.get("stale_values", [])))
        report["docs_with_answers"] = attach_answers_to_docs(project, answers)
        project.emit("update", "item", f"plan items updated: {report['plan'].get('patched')}")
        project.emit("update", "progress", "recompiling (unchanged artifacts come from the build cache)")
        state = project.load_state()
        state["pending_update_objects"] = sorted(touched)
        project.save_state(state)
        report["compile"] = run_compile(project, llm)
        report["validate"] = run_validate(project, llm)
        if not report["plan"].get("rejected"):
            state = project.load_state()
            state.pop("pending_update_objects", None)
            project.save_state(state)
    files_after = snapshot_files(project.repo)
    report["files"] = diff_files(files_before, files_after)
    usage_after = llm.usage.as_dict()
    report["model_calls"] = usage_after["calls"] - usage_before["calls"]
    report["cost_usd_estimate"] = round(usage_after["cost_usd_estimate"] - usage_before["cost_usd_estimate"], 4)
    project.add_model_cost(report["model_calls"], report["cost_usd_estimate"])
    report["finished"] = now_iso()
    updates_dir = project.state / "updates"
    updates_dir.mkdir(parents=True, exist_ok=True)
    (updates_dir / f"{report['finished'].replace(':', '')}.json").write_text(json.dumps(report, indent=1, default=str))
    if touched:
        from terrakernel.compile.knowledge import append_log

        changed_docs = [f for f in report["files"]["changed"] if f.startswith("knowledge/") and not f.endswith(("index.md", "log.md"))]
        append_log(project, [f"**Update**: sources {', '.join(report['sources']['changed']) or '-'} changed; "
                             f"{len(changed)} object(s) updated, {len(added)} added, {len(removed)} removed; "
                             f"documents revised: {', '.join(changed_docs) or 'none'}."])
    return report


def format_report(report: dict[str, Any]) -> str:
    lines = ["# Update report", ""]
    if report.get("result"):
        return "\n".join(lines + [report["result"]])
    lines.append(f"Sources changed: {', '.join(report['sources']['changed']) or 'none'}")
    for sid, d in report.get("evidence", {}).items():
        lines.append(f"- {sid}: " + ", ".join(f"{len(v)} {k}" for k, v in d.items()))
    o = report.get("objects", {})
    lines += ["", f"Knowledge objects: {len(o.get('changed', []))} changed, {len(o.get('added', []))} added, "
                  f"{len(o.get('removed', []))} removed, {o.get('unchanged', 0)} unchanged"]
    lines += [f"- changed {c['id']} ({', '.join(c['fields']) or 'summary only'})" for c in o.get("changed", [])]
    if report.get("predicted_impact"):
        lines += ["", "Dependency check (lineage; conservative, every artifact here was re-checked):"]
        lines += [f"- {a}: {'; '.join(r[:2])}" for a, r in report["predicted_impact"].items()]
    if report.get("plan"):
        lines += ["", f"Plan items updated: {', '.join(report['plan'].get('patched', [])) or 'none'}"]
        if report["plan"].get("rejected"):
            lines += ["Plan patch REJECTED (changes kept pending for the next update):"]
            lines += [f"- {r}" for r in report["plan"]["rejected"]]
    f = report.get("files", {})
    lines += ["", f"Files changed: {len(f.get('changed', []))}, added: {len(f.get('added', []))}, "
                  f"removed: {len(f.get('removed', []))}"]
    lines += [f"- {p}" for p in f.get("changed", []) + f.get("added", [])]
    if report.get("validate"):
        lines += ["", f"Validation: {report['validate']}"]
    return "\n".join(lines)
