"""Export a built repository as a data bundle for the showcase web frontend (`terrakernel export-web`).

The bundle is everything the web app needs and nothing it must compute: identity and counts of the
build, the source inventory, the knowledge catalog, the compiled artifacts with their provenance
chains (artifact -> knowledge objects -> evidence -> source, with the verbatim quote and a page crop
for PDF evidence), a normalised build replay, and a layered graph.

Deliberately not exported: the full repository, full-text of every source, the LLM caches and the
builder state. The web app never reads the database and never calls a model.
"""

from __future__ import annotations

import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from terrakernel.project import Project
from terrakernel.site import LOCAL_PATH_RE, SECRET_RE
from terrakernel.site import assets as A

BUNDLE_VERSION = 1
STAGES = ["ingest", "extract", "reconcile", "plan", "compile", "validate"]
STAGE_INFO = {
    "ingest": {"zh": "资料导入", "en": "Ingest"},
    "extract": {"zh": "知识抽取", "en": "Extract"},
    "reconcile": {"zh": "跨资料关联", "en": "Reconcile"},
    "plan": {"zh": "仓库规划", "en": "Plan"},
    "compile": {"zh": "生成产物", "en": "Compile"},
    "validate": {"zh": "检查", "en": "Validate"},
}

# PDF evidence that gets a rendered page crop. Beyond this many the crop budget is spent on the
# artifacts that came first in the plan, and the rest still carry the verbatim quote + locator.
MAX_CROPS = 240


def _json(path: Path, data: Any) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    path.write_text(text, encoding="utf-8")
    return len(text.encode())


def _jsonl(path: Path, rows: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")
    return path.stat().st_size


def _short(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _load_spec(project: Project) -> dict[str, Any]:
    if not project.spec_path.exists():
        return {}
    return yaml.safe_load(project.spec_path.read_text(encoding="utf-8")) or {}


def _load_events(project: Project) -> list[dict[str, Any]]:
    out = []
    if not project.events_path.exists():
        return out
    for line in project.events_path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _registry(project: Project) -> dict[str, dict[str, Any]]:
    path = project.repo / "tools" / "research_tools" / "registry.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {t["name"]: t for t in data.get("tools", [])}


# ----------------------------------------------------------------------------- replay
PER_SOURCE_STAGES = ("ingest", "extract")


def _stage_attempts(events: list[dict[str, Any]]) -> dict[str, list[list[dict[str, Any]]]]:
    """Every run of every stage, in log order. A run starts at ``stage_start``.

    A run that was interrupted has no ``stage_end``; it is kept, because its results may have
    been kept too (a resumed extraction does not redo the sources that were already finished).
    """
    runs: dict[str, list[list[dict[str, Any]]]] = {}
    for e in events:
        stage = e.get("stage", "")
        if e.get("kind") == "stage_start" or stage not in runs:
            runs.setdefault(stage, []).append([])
        runs[stage][-1].append(e)
    return runs


def _attempt_status(attempt: list[dict[str, Any]]) -> str:
    last = attempt[-1]
    if last.get("kind") != "stage_end":
        return "interrupted"
    return (last.get("data") or {}).get("status") or "done"


def _final_attempts(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """The last successful run of each stage (or its last run, if none succeeded)."""
    out = {}
    for stage, attempts in _stage_attempts(events).items():
        ok = [a for a in attempts if _attempt_status(a) == "done"]
        out[stage] = ok[-1] if ok else attempts[-1]
    return out


def _item(stage: str, e: dict[str, Any], attempt: int) -> dict[str, Any]:
    d = e.get("data") or {}
    item: dict[str, Any] = {"t": e["at"], "a": attempt, "msg": _short(e.get("message") or "", 220)}
    if stage == "ingest" and d.get("source"):
        item |= {"source": d["source"], "evidence": d.get("evidence")}
    elif stage == "extract" and d.get("source"):
        item |= {"source": d["source"], "objects": d.get("objects"), "gaps": d.get("gaps")}
    elif stage == "compile" and d.get("tool"):
        item |= {"tool": d["tool"], "status": d["status"]}
    return item


def _replay(project: Project, events: list[dict[str, Any]], sources_by_id: dict[str, dict]) -> dict[str, Any]:
    """The build as the log recorded it, stage by stage, including runs that failed.

    ``seconds`` and ``model_calls`` of a stage are those of its last successful run. For the
    per-source stages the kept result of every source is reported with the run that produced
    it, because a resumed run only processes what earlier runs had not finished.
    """
    runs = _stage_attempts(events)
    stages = []
    for stage in STAGES:
        attempts = runs.get(stage)
        if not attempts:
            continue
        statuses = [_attempt_status(a) for a in attempts]
        done = [i for i, st in enumerate(statuses) if st == "done"]
        final_i = done[-1] if done else len(attempts) - 1
        final = attempts[final_i]
        items: list[dict[str, Any]] = []
        if stage in PER_SOURCE_STAGES:
            kept: dict[str, dict[str, Any]] = {}
            for i, attempt in enumerate(attempts):
                for e in attempt:
                    sid = (e.get("data") or {}).get("source")
                    if e.get("kind") == "item" and sid in sources_by_id:
                        kept[sid] = _item(stage, e, i)  # a later run replaces an earlier result
            items = sorted(kept.values(), key=lambda x: x["t"])
        else:
            items = [_item(stage, e, final_i) for e in final if e.get("kind") == "item"]
        used = {it["a"] for it in items} | {final_i}
        attempt_rows = []
        for i, attempt in enumerate(attempts):
            start, end = attempt[0]["at"], attempt[-1]["at"]
            error = next((_short(e.get("message") or "", 200) for e in reversed(attempt) if e.get("kind") == "error"), None)
            attempt_rows.append({
                "n": i, "start": start, "end": end, "seconds": round(_seconds_between(start, end), 1),
                "status": statuses[i], "kept_items": sum(1 for it in items if it["a"] == i),
                "used": i in used, "warnings": sum(1 for e in attempt if e.get("kind") == "warning"),
                "model_calls": (attempt[-1].get("data") or {}).get("model_calls"), "error": error,
            })
        last = final[-1]
        stages.append({
            "stage": stage, **STAGE_INFO[stage], "start": final[0]["at"], "end": last["at"],
            "seconds": round(_seconds_between(final[0]["at"], last["at"]), 1),
            "model_calls": (last.get("data") or {}).get("model_calls", 0),
            "warnings": sum(1 for e in final if e.get("kind") == "warning"),
            "summary": _short(last.get("message") or "", 200),
            "attempts": attempt_rows, "items": items,
        })
    reconcile = _final_attempts(events).get("reconcile") or []
    batches = [{"t": e["at"], "msg": _short(e.get("message") or "", 160)}
               for e in reconcile if e.get("kind") == "progress"]
    totals = [{"t": e["at"], "msg": _short(e.get("message") or "", 200)}
              for e in reconcile if e.get("kind") == "item"]
    stamps = [e["at"] for e in events if e.get("at")]
    return {
        "t0": min(stamps, default=""),
        "t1": max(stamps, default=""),
        "wall_seconds": round(_seconds_between(min(stamps), max(stamps)), 1) if stamps else 0,
        "stages": stages,
        "relate_batches": batches,
        "relate_totals": totals,
        "notes": [
            "Timestamps come from the build log; the viewer compresses them to a fixed duration.",
            "A stage's seconds and model calls are those of its last successful run; earlier runs are listed "
            "under attempts, and runs after a failure reuse cached results.",
            "Reconcile ran in batches; the log records batch sizes, not the order of individual relations.",
        ],
    }


def _seconds_between(a: str, b: str) -> float:
    from datetime import datetime

    fmt = "%Y-%m-%dT%H:%M:%SZ"
    try:
        return (datetime.strptime(b, fmt) - datetime.strptime(a, fmt)).total_seconds()
    except (TypeError, ValueError):
        return 0.0


# ----------------------------------------------------------------------------- bundle
def export_web(project: Project, out: str | Path, max_crops: int = MAX_CROPS) -> dict[str, Any]:
    """Write the web bundle into ``out`` and return a summary (sizes per file, leaks)."""
    out_dir = Path(out).resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    kb = project.kb
    spec = _load_spec(project)
    artifacts = spec.get("artifacts", [])
    sources = kb.sources()
    events = _load_events(project)
    registry = _registry(project)
    state = project.load_state()

    sources_out = {s.id: {"path": s.path, "kind": s.kind.value, "size": s.size,
                          "title": s.title or Path(s.path).stem} for s in sources}
    sizes: dict[str, int] = {}
    evidence_rows = _evidence_rows(project)

    # ---- meta
    cfg = project.config
    stage_times = {k: {"seconds": v.get("seconds"), "model_calls": v.get("model_calls"),
                       "cost": v.get("cost_usd_estimate")} for k, v in (state.get("stages") or {}).items()}
    validation = json.loads(project.validation_path.read_text()) if project.validation_path.exists() else {}
    meta = {
        "bundle_version": BUNDLE_VERSION,
        "name": cfg.name,
        "goal": cfg.goal,
        "model": cfg.model,
        "extract_model": cfg.extract_model,
        "tasks": [{"id": t.id, "title": t.title, "prompt": _short(t.prompt, 600), "acceptance": t.acceptance[:8]}
                  for t in cfg.tasks],
        "built_at": spec.get("generated_at") or "",
        "stages": stage_times,
        "cost_total": project.total_model_cost(),
        "validation": {"summary": validation.get("summary") or {},
                       "checks": _validation_by_group(project)},
        "counts": _counts(kb, artifacts, registry, len(evidence_rows)),
    }
    sizes["meta.json"] = _json(out_dir / "meta.json", meta)

    # ---- sources
    ev_per_source: dict[str, int] = defaultdict(int)
    for ev in evidence_rows:
        ev_per_source[ev["source_id"]] += 1
    obj_per_source: dict[str, int] = defaultdict(int)
    for o in kb.objects():
        for sid in o.source_ids:
            obj_per_source[sid] += 1
    used_sources = _sources_behind_artifacts(project, artifacts)
    sources_export = []
    for s in sources:
        d = sources_out[s.id] | {"evidence": ev_per_source.get(s.id, 0), "objects": obj_per_source.get(s.id, 0),
                                 "in_artifacts": used_sources.get(s.id, 0)}
        sources_export.append({"id": s.id} | d)
    sources_export.sort(key=lambda x: (-x["in_artifacts"], -x["evidence"], x["path"]))
    sizes["sources.json"] = _json(out_dir / "sources.json", sources_export)

    # ---- catalog (all knowledge objects)
    first: dict[str, tuple[str, int | None, str]] = {}
    for ev in _evidence_rows(project):
        cur = first.get(ev["id"])
        if cur is None:
            first[ev["id"]] = (ev["source_id"], ev["page"], ev["locator"].get("section") or "")
    links = kb.links()
    links_by_obj: dict[str, list] = defaultdict(list)
    for lk in links:
        links_by_obj[lk.object_id].append(lk)
    catalog = []
    for o in kb.objects():
        lks = links_by_obj.get(o.id, [])
        loc = None
        for lk in lks:
            f = first.get(lk.evidence_id)
            if f:
                loc = {"source": f[0], "page": f[1], "section": f[2]}
                break
        catalog.append({
            "id": o.id, "t": o.type.value, "n": _short(o.name, 160), "s": _short(o.summary, 320),
            "b": o.basis.value, "st": o.status.value,
            "src": o.source_ids[:6], "ev": len({lk.evidence_id for lk in lks}), "loc": loc,
        })
    catalog.sort(key=lambda x: x["id"])
    sizes["catalog.jsonl"] = _jsonl(out_dir / "catalog.jsonl", catalog)

    # ---- artifacts + provenance chains
    obj_by_id = {o.id: o for o in kb.objects()}
    source_by_id = {s.id: s for s in sources}
    art_out, chains = [], {}
    crops = 0
    for a in artifacts:
        oids = a.get("objects") or []
        entry = {"id": a["id"], "kind": a["kind"], "path": a.get("path"), "status": a.get("status"),
                 "depends_on": a.get("depends_on") or [], "title": a.get("title") or "",
                 "description": a.get("description") or "", "objects": oids}
        if a["kind"] == "tool":
            name = a["id"].split(":", 1)[1]
            reg = registry.get(name) or {}
            entry["tool"] = {"name": name, "status": reg.get("status"), "strategy": reg.get("strategy"),
                             "description": reg.get("description") or "",
                             "inputs": reg.get("inputs") or [], "output_description": reg.get("output_description"),
                             "output_unit": reg.get("output_unit"), "knowledge": reg.get("knowledge"),
                             "test_file": reg.get("test_file"), "tests": reg.get("tests"),
                             "reference_cases": reg.get("reference_cases"),
                             "problems": (reg.get("problems") or [])[:6],
                             "cases": _reference_cases(project, reg.get("test_file"))}
        if a["kind"] in ("skill", "knowledge_doc", "computation_doc") and a.get("path"):
            body = project.repo / a["path"]
            if body.exists():
                text = body.read_text(encoding="utf-8", errors="replace")
                entry["body"] = _strip_frontmatter(text)[:20000]
        art_out.append(entry)
        chain_objects, crops = _chain(project, out_dir, oids, obj_by_id, links_by_obj, source_by_id, crops,
                                      max_crops)
        chains[a["id"]] = chain_objects
    sizes["artifacts.json"] = _json(out_dir / "artifacts.json",
                                    {"artifacts": art_out, "plan_summary": spec.get("summary") or "",
                                     "issues": spec.get("issues") or []})
    sizes["chains.json"] = _json(out_dir / "chains.json", chains)

    # ---- graph (layered): sources -> artifacts, objects -> artifacts, conflicts/relations among objects
    graph = _graph(project, sources_export, art_out, catalog, obj_by_id)
    sizes["graph.json"] = _json(out_dir / "graph.json", graph)

    # ---- replay
    replay = _replay(project, events, sources_out)
    sizes["replay.json"] = _json(out_dir / "replay.json", replay)

    # ---- media
    media_files = sum(1 for f in (out_dir / "media").rglob("*") if f.is_file()) if (out_dir / "media").exists() else 0
    sizes["media"] = sum(f.stat().st_size for f in (out_dir / "media").rglob("*") if f.is_file()) \
        if (out_dir / "media").exists() else 0

    sizes["_total"] = sum(v for k, v in sizes.items() if k != "_total")
    # The summary is part of the published bundle: it must not name the local output directory.
    summary = {"sizes_mb": {k: round(v / 1e6, 2) for k, v in sorted(sizes.items())},
               "crops": crops, "media_files": media_files, "counts": meta["counts"]}
    _json(out_dir / "export-summary.json", summary | {"leaks": []})
    leaks = _check_leaks(out_dir)
    if leaks:
        _json(out_dir / "export-summary.json", summary | {"leaks": leaks})
    return summary | {"leaks": leaks, "out": str(out_dir)}


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 4)
    return text[end + 4:].lstrip("\n") if end > 0 else text


def _counts(kb: Any, artifacts: list[dict], registry: dict[str, dict], evidence_n: int) -> dict[str, Any]:
    objects = kb.objects()
    by_type: dict[str, int] = defaultdict(int)
    by_basis: dict[str, int] = defaultdict(int)
    by_status: dict[str, int] = defaultdict(int)
    for o in objects:
        by_type[o.type.value] += 1
        by_basis[o.basis.value] += 1
        by_status[o.status.value] += 1
    relations = kb.relations()
    rel_by_type: dict[str, int] = defaultdict(int)
    for r in relations:
        rel_by_type[r.type.value] += 1
    gaps = kb.gaps()
    return {
        "sources": len(kb.sources()),
        "evidence": evidence_n,
        "objects": len(objects),
        "objects_by_type": dict(by_type),
        "objects_by_basis": dict(by_basis),
        "objects_by_status": dict(by_status),
        "relations": len(relations),
        "relations_by_type": dict(rel_by_type),
        "gaps": len(gaps),
        "gaps_open": sum(1 for g in gaps if not g.resolved_by),
        "gaps_resolved": sum(1 for g in gaps if g.resolved_by),
        "artifacts": len(artifacts),
        "artifacts_by_kind": dict(_tally(a["kind"] for a in artifacts)),
        "tools": len(registry),
        "tools_by_status": dict(_tally(t.get("status") for t in registry.values())),
    }


def _tally(values: Any) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for v in values:
        out[str(v)] += 1
    return out


def _evidence_rows(project: Project) -> list[dict[str, Any]]:
    """Light per-evidence records (id, source, kind, page, locator), read once per export."""
    rows = []
    db = project.kb.conn
    for r in db.execute("SELECT id, source_id, kind, locator FROM evidence ORDER BY ord"):
        loc = json.loads(r[3]) if r[3] else {}
        rows.append({"id": r[0], "source_id": r[1], "kind": r[2], "page": loc.get("page"), "locator": loc})
    return rows


def _validation_by_group(project: Project) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for rec in project.kb.validation():
        out.setdefault(rec.stage, defaultdict(int))[rec.status] += 1
    return {k: dict(v) for k, v in out.items()}


def _sources_behind_artifacts(project: Project, artifacts: list[dict]) -> dict[str, int]:
    oids = {oid for a in artifacts for oid in (a.get("objects") or [])}
    if not oids:
        return {}
    counts: dict[str, int] = defaultdict(int)
    for oid in oids:
        for lk in project.kb.links(oid):
            ev = project.kb.evidence_by_ids([lk.evidence_id]).get(lk.evidence_id)
            if ev:
                counts[ev.source_id] += 1
    return counts


def _reference_cases(project: Project, test_file: str | None) -> list[dict[str, Any]]:
    """Reference cases quoted from the materials, read back from the generated test file."""
    if not test_file:
        return []
    path = project.repo / test_file
    if not path.exists():
        return []
    return parse_reference_cases(path.read_text(encoding="utf-8", errors="replace"))


def parse_reference_cases(source: str) -> list[dict[str, Any]]:
    """The ``REFERENCE_CASES`` literal of a generated test module, without importing the module."""
    import ast

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "REFERENCE_CASES" for t in node.targets):
            try:
                cases = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                return []
            out = []
            for c in cases if isinstance(cases, list) else []:
                if not isinstance(c, dict):
                    continue
                out.append({"id": str(c.get("id", "")), "quote": _short(str(c.get("quote", "")), 400),
                            "evidence": c.get("source"), "expected": c.get("expected"),
                            "inputs": c.get("inputs") if isinstance(c.get("inputs"), dict) else {}})
            return out[:8]
    return []


def _chain(project: Project, out_dir: Path, oids: list[str], obj_by_id: dict, links_by_obj: dict,
           source_by_id: dict, crops: int, max_crops: int) -> tuple[list[dict], int]:
    kb = project.kb
    out: list[dict[str, Any]] = []
    for oid in oids:
        o = obj_by_id.get(oid)
        if o is None:
            continue
        ev_entries = []
        for lk in links_by_obj.get(oid, []):
            ev = kb.evidence_by_ids([lk.evidence_id]).get(lk.evidence_id)
            if ev is None:
                continue
            item: dict[str, Any] = {"id": ev.id, "kind": ev.kind.value, "role": lk.role.value,
                                    "quote": _short(lk.quote or ev.content, 600),
                                    "loc": ev.locator.short() or "", "source": ev.source_id,
                                    "page": ev.locator.page}
            if ev.locator.page and crops < max_crops:
                src = source_by_id.get(ev.source_id)
                if src is not None and src.kind.value == "pdf":
                    file_path = project.repo / "sources" / src.path
                    if file_path.exists():
                        rel = A.pdf_region(project.repo, file_path, ev.locator.page, ev.locator.bbox,
                                           out_dir / "media")
                        if rel:
                            item["crop"] = f"media/{rel}"  # relative to the bundle root: media/pdf/<hash>.png
                            crops += 1
            ev_entries.append(item)
        out.append({"id": o.id, "t": o.type.value, "n": _short(o.name, 200), "s": _short(o.summary, 400),
                    "b": o.basis.value, "st": o.status.value, "evidence": ev_entries,
                    "attrs": _compact_attrs(o.attributes)})
    return out, crops


def _compact_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in (attrs or {}).items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = _short(v, 300) if isinstance(v, str) else v
        elif isinstance(v, list) and len(v) <= 8 and all(isinstance(x, (str, int, float)) for x in v):
            out[k] = [_short(x, 200) if isinstance(x, str) else x for x in v]
    return out


def _graph(project: Project, sources: list[dict], artifacts: list[dict], catalog: list[dict],
           obj_by_id: dict) -> dict[str, Any]:
    artifacts_by_obj: dict[str, list[str]] = defaultdict(list)
    for a in artifacts:
        if a["kind"] in ("source", "test", "config", "entry", "adapter", "runtime"):
            continue
        for oid in a["objects"]:
            artifacts_by_obj[oid].append(a["id"])
    nodes = []
    for s in sources:
        nodes.append({"id": "s:" + s["id"], "kind": "source", "label": _short(s["path"].split("/")[-1], 60),
                      "type": s["kind"], "w": s["evidence"], "used": s["in_artifacts"]})
    for oid in artifacts_by_obj:
        o = obj_by_id.get(oid)
        if o is None:
            continue
        nodes.append({"id": oid, "kind": "object", "label": _short(o.name, 70), "type": o.type.value,
                      "basis": o.basis.value, "w": len(artifacts_by_obj[oid])})
    for a in artifacts:
        if a["kind"] in ("source", "test", "config", "entry", "adapter", "runtime"):
            continue
        nodes.append({"id": a["id"], "kind": "artifact", "label": a["title"] or a["id"].split(":", 1)[1],
                      "type": a["kind"], "status": a["status"]})
    keep = {n["id"] for n in nodes}
    edges = []
    link_rows = project.kb.links()
    ev_source = {ev["id"]: ev["source_id"] for ev in _evidence_rows(project)}
    seen = set()
    for lk in link_rows:
        oid = lk.object_id
        if oid not in keep:
            continue
        sid = ev_source.get(lk.evidence_id)
        if sid:
            key = (oid, sid)
            if key not in seen:
                seen.add(key)
                edges.append({"s": "s:" + sid, "t": oid, "k": "supports", "n": 1})
    for oid, aids in artifacts_by_obj.items():
        for aid in aids:
            edges.append({"s": oid, "t": aid, "k": "in", "n": 1})
    rels = []
    for r in project.kb.relations():
        if r.src in keep and r.dst in keep and r.type.value in ("conflicts_with", "variant_of", "same_as",
                                                               "possibly_same_as", "implements", "uses"):
            rels.append({"s": r.src, "t": r.dst, "k": r.type.value, "note": _short(r.note, 200)})
    return {"nodes": nodes, "edges": edges, "relations": rels}


def _check_leaks(out_dir: Path) -> list[str]:
    problems = []
    for f in out_dir.rglob("*"):
        if not f.is_file() or f.suffix in (".png", ".webp", ".woff2"):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in SECRET_RE.finditer(text):
            problems.append(f"{f.relative_to(out_dir)}: secret-like {m.group(0)[:30]}")
        if f.suffix in (".json", ".jsonl"):
            for m in LOCAL_PATH_RE.finditer(text):
                problems.append(f"{f.relative_to(out_dir)}: local path {m.group(0)[:40]}")
    return problems[:40]
