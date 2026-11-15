"""Compile stage: Repository Spec -> files of the AI-native research repository.

Order matters: tools first (their verification status decides what docs and skills may
reference), then knowledge documents and computation documents, then skills, then entry
files, adapters, registry and lineage.
"""

from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from terrakernel.compile.knowledge import append_log, compile_computation_doc, compile_doc, write_index
from terrakernel.compile.repo import compile_skill, write_adapters, write_agents_md, write_registry
from terrakernel.compile.tools import compile_tools
from terrakernel.lineage import build_lineage
from terrakernel.llm.client import LLMClient
from terrakernel.plan import load_spec, save_spec
from terrakernel.project import HUMAN_SOURCE_FILE, Project


def copy_sources(project: Project) -> list[str]:
    """Mirror the materials into sources/ (only changed files are copied). Returns changed paths."""
    dst = project.repo / "sources"
    src = project.materials_dir
    changed = []
    wanted = set()
    for f in sorted(p for p in src.rglob("*") if p.is_file()):
        rel = f.relative_to(src)
        if any(part.startswith(".") or part == "__pycache__" for part in rel.parts):
            continue
        wanted.add(rel.as_posix())
        target = dst / rel
        if not target.exists() or target.read_bytes() != f.read_bytes():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            changed.append(rel.as_posix())
    if project.answers_path.exists():
        wanted.add(HUMAN_SOURCE_FILE)
        target = dst / HUMAN_SOURCE_FILE
        if not target.exists() or target.read_bytes() != project.answers_path.read_bytes():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(project.answers_path, target)
            changed.append(HUMAN_SOURCE_FILE)
    if dst.exists():
        for f in sorted(p for p in dst.rglob("*") if p.is_file()):
            if f.relative_to(dst).as_posix() not in wanted:
                f.unlink()
                changed.append(f.relative_to(dst).as_posix())
    return changed


def remove_stale_outputs(project: Project, plan: Any) -> list[str]:
    """Delete generated knowledge documents and skills that the current plan no longer contains.

    Only files TerraKernel generated are removed: knowledge documents must carry the
    ``x-terrakernel`` frontmatter key, and skill folders must carry ``terrakernel-task`` metadata.
    """
    from terrakernel.validate import split_frontmatter

    repo = project.repo
    removed: list[str] = []
    planned_docs = {f"knowledge/{d.path}" for d in plan.docs}
    planned_docs |= {f"knowledge/evidence/{d.path.replace('/', '--')}" for d in plan.docs}
    kroot = repo / "knowledge"
    if kroot.exists():
        for f in sorted(kroot.rglob("*.md")):
            rel = f.relative_to(repo).as_posix()
            if f.name in ("index.md", "log.md") or rel.startswith("knowledge/computations/") or rel in planned_docs:
                continue
            fm, _ = split_frontmatter(f.read_text(encoding="utf-8"))
            if fm and "x-terrakernel" in fm:
                f.unlink()
                removed.append(rel)
        for d in sorted((p for p in kroot.rglob("*") if p.is_dir()), reverse=True):
            md = [p for p in d.iterdir() if p.suffix == ".md" and p.name != "index.md"]
            if not md and d != kroot / "computations":
                for p in d.iterdir():
                    p.unlink()
                d.rmdir()
    planned_skills = {s.name for s in plan.skills}
    for root in (repo / ".agents" / "skills", repo / ".claude" / "skills"):
        if not root.exists():
            continue
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            skill_md = d / "SKILL.md"
            if d.name in planned_skills or not skill_md.exists():
                continue
            fm, _ = split_frontmatter(skill_md.read_text(encoding="utf-8"))
            if fm and "terrakernel-task" in (fm.get("metadata") or {}):
                shutil.rmtree(d)
                removed.append(d.relative_to(repo).as_posix() + "/")
    return removed


def run_compile(project: Project, llm: LLMClient, force: bool = False, only: set[str] | None = None,
                **_: Any) -> dict[str, Any]:
    """Compile every artifact (``only`` restricts docs/tools/skills to the given artifact IDs)."""
    spec = load_spec(project)
    plan = spec.plan
    model = project.config.model
    repo = project.repo
    copy_sources(project)
    for rel in remove_stale_outputs(project, plan):
        project.emit("compile", "item", f"removed {rel} (no longer in the plan)")

    project.emit("compile", "progress", f"building {len([t for t in plan.tools if t.strategy != 'knowledge_only'])} tools")
    entries, runtime_result = compile_tools(repo, project, llm, plan, model)
    tool_status = {e["name"]: e["status"] for e in entries}

    project.emit("compile", "progress", f"writing {len(plan.docs)} knowledge documents")
    with ThreadPoolExecutor(max_workers=max(1, llm.settings.max_concurrency)) as pool:
        doc_results = list(pool.map(lambda d: compile_doc(project, llm, d, plan, tool_status, model), plan.docs))
    for r in doc_results:
        project.emit("compile", "item", f"{r['path']}: {r['status']} ({r['cited']} of {r['objects']} objects cited)")
        for p in r["problems"]:
            project.emit("compile", "warning", f"{r['path']}: {p}")
    computations = [c for c in (compile_computation_doc(project, e, plan) for e in entries) if c]
    write_index(project, plan, doc_results, computations)

    project.emit("compile", "progress", f"writing {len(plan.skills)} skills")
    with ThreadPoolExecutor(max_workers=max(1, llm.settings.max_concurrency)) as pool:
        skill_results = list(pool.map(lambda s: compile_skill(project, llm, s, plan, entries, model), plan.skills))
    for r in skill_results:
        project.emit("compile", "item", f"skill {r['name']}: tools {r['tools']}"
                     + (f", unavailable {r['unavailable_tools']}" if r["unavailable_tools"] else ""))
        for p in r["problems"]:
            project.emit("compile", "warning", f"skill {r['name']}: {p}")

    write_registry(project, plan, entries)
    write_agents_md(project, plan, entries, skill_results, doc_results)
    write_adapters(project)

    # record statuses in the spec and build the lineage graph
    status_by_id: dict[str, str] = {}
    for e in entries:
        status_by_id[f"tool:{e['name']}"] = "verified" if e["status"] == "verified" else (
            "candidate" if e["status"] == "tested" else "failed")
        status_by_id[f"test:{e['name']}"] = "generated"
        status_by_id[f"computation:{e['name']}"] = "generated" if e["status"] in ("verified", "tested") else "skipped"
    for r in doc_results:
        status_by_id[f"doc:{r['path'].removeprefix('knowledge/')}"] = "generated"
    for r in skill_results:
        status_by_id[f"skill:{r['name']}"] = "generated" if not r["unavailable_tools"] else "blocked"
    for a in spec.artifacts:
        if a.id in status_by_id:
            a.status = status_by_id[a.id]  # type: ignore[assignment]
        elif a.kind in ("config", "runtime", "entry", "adapter", "source"):
            a.status = "generated"
        if a.id == "test:runtime":
            a.status = "verified" if not (runtime_result["failed"] or runtime_result["errors"]) else "failed"
        if a.id == "runtime":
            a.status = "verified" if not (runtime_result["failed"] or runtime_result["errors"]) else "failed"
    save_spec(project, spec)
    build_lineage(project, spec)
    append_log(project, [f"**Build**: compiled {len(doc_results)} knowledge documents, {len(computations)} computations "
                         f"and {len(skill_results)} skills from {len(project.kb.sources())} sources."])
    return {
        "tools": {e["name"]: e["status"] for e in entries},
        "runtime_checks": f"{runtime_result['passed']} passed, {runtime_result['failed'] + runtime_result['errors']} failed",
        "docs": len(doc_results), "draft_docs": sum(r["status"] != "stable" for r in doc_results),
        "computations": len(computations), "skills": len(skill_results),
    }
