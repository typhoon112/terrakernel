"""Extract stage: evidence units -> grounded knowledge objects and gaps.

- Tables are profiled deterministically: one ``dataset`` object with ``basis=measured``;
  no model call (what a CSV *means* comes from its documentation, linked later).
- Every other source is sent to the model in batches together with the
  ``extract-knowledge`` builder skill. Each returned object must cite evidence from its
  batch with a verbatim quote; objects that fail the check are repaired once and
  otherwise kept as ``needs_review``.
- Facts that code can measure (symbol, signature, lines, data-handling operations) are
  attached to capabilities deterministically.

Object IDs are source-scoped (``method:paper_a/nrmse-cap``): the same name in two
sources stays two objects until the reconcile stage relates them.
"""

from __future__ import annotations

import base64
import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from terrakernel.builtin import skill_body
from terrakernel.extract.grounding import check_refs
from terrakernel.extract.schemas import ExtractedObject, ExtractionResult
from terrakernel.llm.client import LLMClient
from terrakernel.models import (
    Basis,
    Evidence,
    EvidenceKind,
    EvidenceLink,
    Gap,
    KnowledgeObject,
    LinkRole,
    ObjectStatus,
    ObjectType,
    Severity,
    Source,
    SourceKind,
    ValidationRecord,
)
from terrakernel.project import HUMAN_SOURCE_ID, Project
from terrakernel.util import normalize_name, now_iso, slugify

BATCH_CHAR_BUDGET = 36_000
MAX_IMAGES_PER_BATCH = 4


# ---------------------------------------------------------------- helpers
def _parse_value(value: str) -> Any:
    v = value.strip()
    if not v:
        return None
    if v[0] in "[{" or v in ("true", "false", "null") or v.replace(".", "", 1).lstrip("-").isdigit():
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return value
    return value


def _format_evidence(ev: Evidence) -> str:
    loc = ev.locator.short()
    attrs = f'id="{ev.id}" kind="{ev.kind.value}"' + (f' locator="{loc}"' if loc else "")
    return f"<evidence {attrs}>\n{ev.content}\n</evidence>" + _omml_context(ev)


def _omml_context(ev: Evidence) -> str:
    """Expose original equation structure without changing the text used for quote grounding."""
    fragments = ev.meta.get("omml")
    if not fragments:
        return ""
    if isinstance(fragments, str):
        fragments = [fragments]
    namespace = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"

    def compact(node: ET.Element) -> ET.Element | None:
        if not node.tag.startswith(namespace):
            return None  # Word run/font/language properties and bookmarks are not equation structure.
        tag = node.tag[len(namespace):]
        if tag in {"rPr", "ctrlPr"}:
            return None
        result = ET.Element(tag)
        value = node.get(namespace + "val")
        if value is not None:
            result.set("val", value)
        if node.text and (tag == "t" or node.text.strip()):
            result.text = node.text
        for child in node:
            kept = compact(child)
            if kept is not None:
                result.append(kept)
        if tag.endswith("Pr") and not len(result) and not result.attrib and not result.text:
            return None
        return result

    equations = []
    for index, fragment in enumerate(fragments, 1):
        try:
            tree = compact(ET.fromstring(fragment))
        except (ET.ParseError, TypeError, ValueError):
            tree = None
        if tree is None:
            equations.append(f"Equation {index}: original OMML could not be parsed; do not infer its formula.")
        else:
            equations.append(ET.tostring(tree, encoding="unicode", short_empty_elements=True))
    return (
        f'\n<source-math-structure evidence_id="{ev.id}">\n'
        "These equations retain the original Word OMML structure with short tags and val attributes; "
        "font and run-formatting properties are omitted. Use num/den, sub/sup, nary/chr and other "
        "structure to read mathematical relationships lost in the flattened text above. "
        "Citation quotes must still be copied verbatim from this evidence's original content above, "
        "not from this XML or explanatory note. Do not guess missing symbols or reconstruct unsupported OLE equations.\n"
        + "\n".join(equations)
        + "\n</source-math-structure>"
    )


def batches(evidence: list[Evidence], budget: int = BATCH_CHAR_BUDGET) -> list[list[Evidence]]:
    out: list[list[Evidence]] = []
    cur: list[Evidence] = []
    size = 0
    images = 0
    for ev in evidence:
        n = len(ev.content) + 120
        if ev.meta.get("omml"):
            n += len(_omml_context(ev))
        if cur and (size + n > budget or (ev.asset and images >= MAX_IMAGES_PER_BATCH)):
            out.append(cur)
            cur, size = [], 0
            images = 0
        cur.append(ev)
        size += n
        images += bool(ev.asset)
    if cur:
        out.append(cur)
    return out


class _IdAllocator:
    def __init__(self, taken: Iterable[str] = ()):
        self.taken = set(taken)

    def new(self, type_: str, source_id: str, name: str) -> str:
        base = f"{type_}:{source_id}/{slugify(name, 50)}"
        oid, n = base, 2
        while oid in self.taken:
            oid = f"{base}-{n}"
            n += 1
        self.taken.add(oid)
        return oid


# ---------------------------------------------------------------- tables (no model)
def profile_table_source(source: Source, evidence: list[Evidence], actor: str) -> tuple[list[KnowledgeObject], list[EvidenceLink]]:
    """Measured dataset objects for tabular and array files: one per sheet (or per file)."""
    profiles = [e for e in evidence if e.kind == EvidenceKind.dataset_profile]
    objects: list[KnowledgeObject] = []
    links: list[EvidenceLink] = []
    fname = Path(source.path).name
    for profile in profiles:
        sheet = profile.meta.get("sheet")
        col_ids = set(profile.related)
        columns = [e for e in evidence if e.id in col_ids]
        if profile.meta.get("format") == "netcdf":
            fields = profile.meta.get("fields", [])
            attributes = {"file": source.path, "format": "netcdf", "dims": profile.meta.get("dims"),
                          "fields": fields, "time_columns": profile.meta.get("time_columns", []),
                          "global_attributes": profile.meta.get("global_attributes", {})}
            stated_units = {f["column"]: f["attributes"].get("units") for f in fields
                            if f.get("role") == "variable" and f.get("attributes", {}).get("units")}
            summary = (f"NetCDF file {source.path} with dimensions "
                       + ", ".join(f"{k}={v}" for k, v in (profile.meta.get("dims") or {}).items())
                       + " and variables " + ", ".join(f["column"] for f in fields if f.get("role") == "variable") + ".")
            note = ("Profiled from the file by TerraKernel. Attributes such as units and cell_methods are stated by the "
                    "file itself" + (f" (units: {stated_units})" if stated_units else "") + ".")
        else:
            fields = []
            for col in columns:
                m = col.meta
                f = {k: m[k] for k in ("column", "dtype", "missing", "missing_fraction", "min", "max", "mean", "unit_hint")
                     if k in m}
                if "datetime" in m:
                    f["datetime"] = m["datetime"]
                fields.append(f)
            attributes = {"file": source.path, "rows": profile.meta.get("rows"), "fields": fields,
                          "time_columns": profile.meta.get("time_columns", [])}
            if sheet is not None:
                attributes["sheet"] = sheet
            summary = (f"Data file {source.path}" + (f" sheet {sheet!r}" if sheet is not None else "")
                       + f" with {profile.meta.get('rows')} rows and columns " + ", ".join(profile.meta.get("columns", [])) + ".")
            note = "Profiled from the file contents by TerraKernel; meanings and units must come from documentation."
        name = fname if sheet is None else f"{fname} [{sheet}]"
        oid = f"dataset:{source.id}/{slugify(name, 50)}"
        objects.append(KnowledgeObject(id=oid, type=ObjectType.dataset, name=name, summary=summary,
                                       attributes=attributes, basis=Basis.measured, basis_note=note,
                                       source_ids=[source.id], produced_by=f"{actor}+profiler"))
        links.append(EvidenceLink(object_id=oid, evidence_id=profile.id, role=LinkRole.measures,
                                  quote=profile.content.splitlines()[0], match_score=100.0))
        links += [EvidenceLink(object_id=oid, evidence_id=c.id, role=LinkRole.measures, quote=c.content.splitlines()[0],
                               match_score=100.0) for c in columns]
    return objects, links


# ---------------------------------------------------------------- human answers
GAP_IN_SECTION_RE = re.compile(r"(gap:[^\s>]+)")
ANSWER_META_RE = re.compile(r"Answered by:\s*(human:\S+)\s+on\s+(\S+)")


def mark_human(obj: KnowledgeObject, evidence: list[Evidence]) -> None:
    """Objects extracted from recorded answers are human-confirmed and remember the question they answer."""
    obj.basis = Basis.human_confirmed
    for ev in evidence:
        m = GAP_IN_SECTION_RE.search(ev.locator.section or "")
        if m:
            obj.attributes["answers_gap"] = m.group(1)
            break


def finalize_human(objects: list[KnowledgeObject], evidence: list[Evidence]) -> None:
    """Attach the answering person's actor ID (OKF actor convention) and the date to human objects."""
    meta_by_gap: dict[str, tuple[str, str]] = {}
    for ev in evidence:
        m = ANSWER_META_RE.search(ev.content)
        g = GAP_IN_SECTION_RE.search(ev.locator.section or "")
        if m and g:
            meta_by_gap[g.group(1)] = (m.group(1), m.group(2))
    for o in objects:
        if o.basis != Basis.human_confirmed:
            continue
        actor, when = meta_by_gap.get(o.attributes.get("answers_gap") or "", ("human:unknown", None))
        o.produced_by = actor
        o.basis_note = f"Answer recorded by {actor}" + (f" on {when}" if when else "") + (
            f" to open question {o.attributes.get('answers_gap')}" if o.attributes.get("answers_gap") else "")


# ---------------------------------------------------------------- model extraction
def _batch_prompt(project: Project, source: Source, batch: list[Evidence], index: int, total: int,
                  problems: list[str] | None = None, previous: ExtractionResult | None = None) -> list[dict[str, Any]]:
    cfg = project.config
    title = next((e.meta.get("doc_title") for e in batch if e.meta.get("doc_title")), None) or source.title
    header = [f"Project goal: {cfg.goal}"]
    if cfg.tasks:
        header.append("Research tasks the generated repository must support:")
        header += [f"- {t.title}: {t.prompt}" for t in cfg.tasks]
    header.append(f"\nSource: {source.path} (kind: {source.kind.value}) title: {title!r}")
    header.append(f"Batch {index} of {total}. Extract knowledge from the evidence units below.")
    content: list[dict[str, Any]] = [{"type": "text", "text": "\n".join(header)}]
    images = 0
    for ev in batch:
        if ev.asset and images < MAX_IMAGES_PER_BATCH:
            path = project.assets_dir / ev.asset
            if path.exists() and path.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                media = "image/png" if path.suffix.lower() == ".png" else f"image/{path.suffix.lower().lstrip('.')}"
                media = media.replace("jpg", "jpeg")
                content.append({"type": "text", "text": f"Image for evidence {ev.id}:"})
                content.append({"type": "image", "source": {"type": "base64", "media_type": media,
                                                            "data": base64.b64encode(path.read_bytes()).decode()}})
                images += 1
    content.append({"type": "text", "text": "\n\n".join(_format_evidence(e) for e in batch)})
    if problems and previous is not None:
        content.append({"type": "text", "text": (
            "Your previous extraction for this batch had grounding problems:\n- " + "\n- ".join(problems[:40])
            + "\n\nPrevious extraction:\n" + previous.model_dump_json()
            + "\n\nReturn the complete corrected extraction. Fix each evidence_id and copy each quote verbatim from "
              "the cited evidence unit; drop any object you cannot ground."
        )})
    return content


def _ground_objects(result: ExtractionResult, batch_map: dict[str, Evidence]) -> tuple[list[tuple[ExtractedObject, list]], list[tuple[ExtractedObject, list[str]]]]:
    ok, bad = [], []
    for obj in result.objects:
        rep = check_refs([(r.evidence_id, r.quote) for r in obj.evidence], batch_map)
        if rep.ok:
            ok.append((obj, rep.accepted))
        else:
            bad.append((obj, rep.problems))
    return ok, bad


def extract_batch(project: Project, llm: LLMClient, source: Source, batch: list[Evidence], index: int, total: int,
                  model: str) -> tuple[list[tuple[ExtractedObject, list, ObjectStatus]], list, list[str]]:
    """Returns (objects with accepted refs and status, gaps, problems)."""
    system = skill_body("extract-knowledge")
    batch_map = {e.id: e for e in batch}
    prompt = _batch_prompt(project, source, batch, index, total)
    result = llm.structured(prompt, ExtractionResult, system=system, model=model, max_tokens=16000,
                            tool_name="submit_extraction", tool_description="Submit the extracted knowledge objects and gaps.")
    ok, bad = _ground_objects(result, batch_map)
    problems: list[str] = []
    if bad:
        issues = [f"{o.type} {o.name!r}: {p}" for o, ps in bad for p in ps]
        repair_prompt = _batch_prompt(project, source, batch, index, total, problems=issues, previous=result)
        try:
            repaired = llm.structured(repair_prompt, ExtractionResult, system=system, model=model, max_tokens=16000,
                                      tool_name="submit_extraction",
                                      tool_description="Submit the corrected knowledge objects and gaps.")
            ok2, bad2 = _ground_objects(repaired, batch_map)
            result = repaired
            ok, bad = ok2, bad2
        except Exception as e:  # keep the first result if the repair call fails
            problems.append(f"repair call failed: {e}")
    out = [(o, acc, ObjectStatus.active) for o, acc in ok]
    for o, ps in bad:
        problems += [f"{o.type} {o.name!r}: {p}" for p in ps]
        # keep partially grounded objects for review rather than silently dropping them
        partial = check_refs([(r.evidence_id, r.quote) for r in o.evidence], batch_map, min_score=60.0).accepted
        out.append((o, partial, ObjectStatus.needs_review))
    return out, result.gaps, problems


def _capability_facts(obj: KnowledgeObject, evidence: dict[str, Evidence], source: Source) -> None:
    for link_eid in obj.attributes.get("_evidence_ids", []):
        ev = evidence.get(link_eid)
        if ev and ev.kind == EvidenceKind.code_symbol:
            m = ev.meta
            obj.attributes.update({
                "file": source.path,
                "symbol": m.get("symbol"),
                "signature": m.get("signature"),
                "lines": [ev.locator.line_start, ev.locator.line_end],
                "data_handling_ops": m.get("notable_ops", []),
                "uses_constants": m.get("uses_constants", []),
            })
            break


def extract_source(project: Project, llm: LLMClient, source: Source, model: str | None = None) -> dict[str, Any]:
    """(Re-)extract knowledge for one source and store it. Returns a small report."""
    kb = project.kb
    cfg = project.config
    model = model or cfg.extract_model or cfg.model
    actor = f"{cfg.actor}+{model}"
    evidence = kb.evidence(source.id)
    ev_map = {e.id: e for e in evidence}

    # remove previous extraction results of this source
    old = [o.id for o in kb.objects() if o.source_ids == [source.id]]
    kb.delete_objects(old)
    with kb.tx() as c:
        c.execute("DELETE FROM gaps WHERE id LIKE ? AND resolved_by IS NULL", (f"gap:{source.id}/%",))
        c.execute("DELETE FROM validation_records WHERE stage='extract' AND target_id LIKE ?", (f"%{source.id}%",))

    if source.kind in (SourceKind.table, SourceKind.array):
        objs, links = profile_table_source(source, evidence, cfg.actor)
        kb.upsert_objects(objs)
        kb.add_links(links)
        return {"source": source.id, "objects": len(objs), "gaps": 0, "problems": [], "model_calls": 0}

    if not evidence:
        return {"source": source.id, "objects": 0, "gaps": 0, "problems": ["no evidence units"], "model_calls": 0}

    groups = batches(evidence)
    results: list[Any] = [None] * len(groups)
    with ThreadPoolExecutor(max_workers=max(1, llm.settings.max_concurrency)) as pool:
        futures = {pool.submit(extract_batch, project, llm, source, g, i + 1, len(groups), model): i
                   for i, g in enumerate(groups)}
        for fut, i in futures.items():
            results[i] = fut.result()

    alloc = _IdAllocator(o.id for o in kb.objects())
    objects: list[KnowledgeObject] = []
    links: list[EvidenceLink] = []
    gaps: list[Gap] = []
    records: list[ValidationRecord] = []
    problems: list[str] = []
    for extracted, raw_gaps, batch_problems in results:
        problems += batch_problems
        for eo, accepted, status in extracted:
            oid = alloc.new(eo.type, source.id, eo.name)
            attrs = {a.key: _parse_value(a.value) for a in eo.attributes}
            quotes = {r.evidence_id: r.quote for r in eo.evidence}
            attrs["_evidence_ids"] = [eid for eid, _ in accepted]
            obj = KnowledgeObject(
                id=oid, type=ObjectType(eo.type), name=eo.name.strip(), summary=eo.summary.strip(),
                aliases=[a for a in eo.aliases if a and a != eo.name], attributes=attrs,
                basis=Basis(eo.basis), basis_note=eo.basis_note, status=status, source_ids=[source.id],
                produced_by=actor,
            )
            if obj.type == ObjectType.capability:
                _capability_facts(obj, ev_map, source)
            if source.id == HUMAN_SOURCE_ID:
                mark_human(obj, [ev_map[e] for e in obj.attributes.get("_evidence_ids", []) if e in ev_map])
            obj.attributes.pop("_evidence_ids", None)
            objects.append(obj)
            role = LinkRole.defines if obj.type in (ObjectType.method, ObjectType.concept) else LinkRole.supports
            if obj.type == ObjectType.capability:
                role = LinkRole.implements
            for eid, score in accepted:
                links.append(EvidenceLink(object_id=oid, evidence_id=eid, role=role, quote=quotes.get(eid, ""),
                                          match_score=round(score, 1)))
            records.append(ValidationRecord(
                id=f"val:extract:{oid}", stage="extract", target_id=oid, check="grounding",
                status="pass" if status == ObjectStatus.active else "fail",
                detail=f"{len(accepted)} grounded evidence reference(s)", at=now_iso(),
            ))
            if obj.basis == Basis.inferred and not obj.basis_note:
                records.append(ValidationRecord(id=f"val:extract:{oid}:basis", stage="extract", target_id=oid,
                                                check="inferred_has_note", status="warn",
                                                detail="inferred object without an explanation", at=now_iso()))
        for g in raw_gaps:
            subject = next((o.id for o in objects if normalize_name(o.name) == normalize_name(g.subject)
                            or normalize_name(g.subject) in {normalize_name(a) for a in o.aliases}), None)
            gid = f"gap:{source.id}/{slugify(g.subject + ' ' + (g.field or '') + ' ' + g.description, 70)}"
            gaps.append(Gap(
                id=gid, subject_id=subject, field=g.field, description=g.description if subject else
                f"{g.subject}: {g.description}", severity=Severity(g.severity), suggestion=g.suggestion,
                evidence_ids=[e for e in g.evidence_ids if e in ev_map],
            ))
    if source.id == HUMAN_SOURCE_ID:
        finalize_human(objects, evidence)
    kb.upsert_objects(objects)
    kb.add_links(links)
    kb.upsert_gaps(list({g.id: g for g in gaps}.values()))
    kb.add_validation(records)
    return {"source": source.id, "objects": len(objects), "gaps": len(gaps), "problems": problems,
            "batches": len(groups)}
