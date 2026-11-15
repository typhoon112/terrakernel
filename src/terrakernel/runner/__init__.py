"""Pipeline stages and the executor that runs them.

Stages run in a fixed order. Each records its status, timing and a short report in
``.terrakernel/state.json`` and emits progress events to ``events.jsonl``. Work inside a
stage is incremental where it is cheap to decide (per-source fingerprints), and model
responses are cached by request content, so re-running a build only pays for what
changed.
"""

from __future__ import annotations

import time
import traceback
from collections.abc import Callable
from typing import Any

from terrakernel.builtin import skill_version
from terrakernel.ingest import ingest_file, scan_materials
from terrakernel.llm.client import LLMClient
from terrakernel.models import Source, SourceKind
from terrakernel.project import HUMAN_SOURCE_FILE, HUMAN_SOURCE_ID, Project
from terrakernel.util import now_iso, sha256_file

STAGES = ["ingest", "extract", "reconcile", "plan", "compile", "validate"]


# ---------------------------------------------------------------- ingest
def run_ingest(project: Project, llm: LLMClient | None = None, **_: Any) -> dict[str, Any]:
    kb = project.kb
    sources, skipped = scan_materials(project.materials_dir)
    sources = [s for s in sources if s.id != HUMAN_SOURCE_ID]
    if project.answers_path.exists():
        sources.append(Source(id=HUMAN_SOURCE_ID, path=HUMAN_SOURCE_FILE, kind=SourceKind.markdown,
                              sha256=sha256_file(project.answers_path), size=project.answers_path.stat().st_size,
                              media_type="text/markdown", title="Answers recorded by people", meta={"managed": True}))
    existing = {s.id: s for s in kb.sources()}
    diff: dict[str, dict[str, list[str]]] = {}
    changed: list[str] = []
    for s in sources:
        old = existing.get(s.id)
        old_ev = {e.id: e.content_hash for e in kb.evidence(s.id)} if old else {}
        if old and old.sha256 == s.sha256 and old_ev:
            continue
        project.emit("ingest", "progress", f"parsing {s.path}")
        evs = ingest_file(s, project.source_file(s), project.assets_dir)
        kb.upsert_source(s)
        kb.replace_evidence(s.id, evs)
        new_ev = {e.id: e.content_hash for e in evs}
        diff[s.id] = {
            "added": sorted(set(new_ev) - set(old_ev)),
            "removed": sorted(set(old_ev) - set(new_ev)),
            "changed": sorted(k for k in set(new_ev) & set(old_ev) if new_ev[k] != old_ev[k]),
            "new_source": [] if old else [s.id],
        }
        changed.append(s.id)
        project.emit("ingest", "item", f"{s.path}: {len(evs)} evidence units", source=s.id, evidence=len(evs))
    current = {s.id for s in sources}
    removed = [sid for sid in existing if sid not in current]
    for sid in removed:
        kb.delete_objects([o.id for o in kb.objects() if o.source_ids == [sid]])
        kb.delete_source(sid)
        diff[sid] = {"added": [], "removed": ["*"], "changed": [], "new_source": []}
    kb.set_meta("last_ingest_diff", diff)
    stats = kb.stats()
    return {"sources": len(sources), "changed": changed, "removed": removed, "skipped": skipped,
            "evidence": stats["evidence"], "evidence_by_kind": stats["evidence_by_kind"]}


# ---------------------------------------------------------------- extract
def run_extract(project: Project, llm: LLMClient, force: bool = False, **_: Any) -> dict[str, Any]:
    from terrakernel.extract import extract_source

    kb = project.kb
    cfg = project.config
    model = cfg.extract_model or cfg.model
    state = project.load_state()
    fps: dict[str, str] = state.setdefault("extract_fingerprints", {})
    version = skill_version("extract-knowledge")
    reports = []
    for s in kb.sources():
        fp = f"{s.sha256}:{version}:{model}"
        has_objects = any(s.id in o.source_ids for o in kb.objects())
        if not force and fps.get(s.id) == fp and (has_objects or s.kind.value == "image"):
            continue
        project.emit("extract", "progress", f"extracting knowledge from {s.path}", source=s.id)
        rep = extract_source(project, llm, s, model=model)
        reports.append(rep)
        fps[s.id] = fp
        state = project.load_state() | {"extract_fingerprints": fps}
        project.save_state(state)
        project.emit("extract", "item", f"{s.path}: {rep['objects']} objects, {rep['gaps']} gaps", **rep)
        for p in rep.get("problems", [])[:10]:
            project.emit("extract", "warning", p, source=s.id)
    for sid in [k for k in fps if k not in {s.id for s in kb.sources()}]:
        fps.pop(sid)
    project.save_state(project.load_state() | {"extract_fingerprints": fps})
    stats = kb.stats()
    return {"extracted_sources": [r["source"] for r in reports], "objects": stats["objects"],
            "objects_by_type": stats["objects_by_type"], "gaps": stats["gaps"],
            "problems": sum(len(r.get("problems", [])) for r in reports)}


STAGE_FUNCS: dict[str, Callable[..., dict[str, Any]]] = {
    "ingest": run_ingest,
    "extract": run_extract,
}


def register_stage(name: str, fn: Callable[..., dict[str, Any]]) -> None:
    STAGE_FUNCS[name] = fn


def _load_optional_stages() -> None:
    """Import later stages lazily so early stages work while the package grows."""
    import importlib

    for name, mod in (("reconcile", "terrakernel.reconcile"), ("plan", "terrakernel.plan"),
                      ("compile", "terrakernel.compile"), ("validate", "terrakernel.validate")):
        if name in STAGE_FUNCS:
            continue
        try:
            m = importlib.import_module(mod)
        except ModuleNotFoundError:
            continue
        fn = getattr(m, f"run_{name}", None)
        if fn:
            STAGE_FUNCS[name] = fn


class Pipeline:
    def __init__(self, project: Project, llm: LLMClient):
        self.project = project
        self.llm = llm
        _load_optional_stages()

    def run(self, start: str | None = None, until: str | None = None, force: bool = False,
            only: list[str] | None = None) -> dict[str, Any]:
        names = [s for s in STAGES if s in STAGE_FUNCS]
        if only:
            names = [s for s in names if s in only]
        else:
            if start:
                names = names[names.index(start):]
            if until:
                names = names[: names.index(until) + 1]
        results: dict[str, Any] = {}
        for name in names:
            results[name] = self.run_stage(name, force=force)
            if results[name].get("status") == "failed":
                break
        return results

    def run_stage(self, name: str, force: bool = False) -> dict[str, Any]:
        project = self.project
        state = project.load_state()
        st = state.setdefault("stages", {}).setdefault(name, {})
        st.update({"status": "running", "started": now_iso()})
        project.save_state(state)
        project.emit(name, "stage_start", f"{name} started")
        usage_before = self.llm.usage.as_dict()
        t0 = time.time()
        try:
            report = STAGE_FUNCS[name](project, self.llm, force=force)
            status = "done"
            error = None
        except Exception as e:  # recorded and surfaced; the stage can be retried
            report = {}
            status = "failed"
            error = f"{type(e).__name__}: {e}"
            project.emit(name, "error", error, traceback=traceback.format_exc()[-4000:])
        elapsed = round(time.time() - t0, 2)
        usage_after = self.llm.usage.as_dict()
        calls = usage_after["calls"] - usage_before["calls"]
        cost = round(usage_after["cost_usd_estimate"] - usage_before["cost_usd_estimate"], 4)
        state = project.load_state()
        state.setdefault("stages", {})[name] = {
            "status": status, "finished": now_iso(), "seconds": elapsed, "report": report, "error": error,
            "model_calls": calls, "cost_usd_estimate": cost,
        }
        project.save_state(state)
        project.add_model_cost(calls, cost)
        project.emit(name, "stage_end", f"{name} {status} in {elapsed}s", status=status, model_calls=calls)
        return {"status": status, "seconds": elapsed, "report": report, "error": error, "model_calls": calls,
                "cost_usd_estimate": cost}
