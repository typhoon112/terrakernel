"""Run research tasks with the built-in agent in different workspace settings, and grade them.

Settings (the agent, model, prompt, tools and limits are identical; only the workspace differs):
- ``raw``: only the original materials (``sources/``), as a researcher would hand them over.
- ``knowledge``: the materials plus the compiled ``knowledge/`` bundle.
- ``full``: the complete generated repository (AGENTS.md as instructions, knowledge, skills,
  verified tools, tests).

Workspaces are fresh copies, so agents cannot see the knowledge base, the build plan,
expected answers or other runs.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from terrakernel.agent.grader import grade
from terrakernel.agent.loop import AgentRun
from terrakernel.config import resolve_model
from terrakernel.llm.client import LLMClient
from terrakernel.project import Project, TaskSpec
from terrakernel.util import now_iso, short_hash

SETTINGS = ("raw", "knowledge", "full")
FULL_EXCLUDE = {".terrakernel", "__pycache__", ".pytest_cache", ".venv", ".git"}


def prepare_workspace(project: Project, setting: str, dest: Path) -> Path:
    repo = project.repo
    dest.mkdir(parents=True, exist_ok=True)
    if setting == "raw":
        shutil.copytree(repo / "sources", dest, dirs_exist_ok=True)
    elif setting == "knowledge":
        shutil.copytree(repo / "sources", dest / "sources")
        shutil.copytree(repo / "knowledge", dest / "knowledge")
    elif setting == "full":
        for item in repo.iterdir():
            if item.name in FULL_EXCLUDE:
                continue
            if item.is_dir():
                shutil.copytree(item, dest / item.name, ignore=shutil.ignore_patterns(*FULL_EXCLUDE))
            else:
                shutil.copy2(item, dest / item.name)
    else:
        raise ValueError(f"unknown setting {setting!r}; choose from {SETTINGS}")
    return dest


def task_prompt(task: TaskSpec) -> str:
    lines = [task.prompt.strip()]
    if task.report_values:
        lines.append("\nReport these values in submit_answer.values, using exactly these names:")
        lines += [f"- {v.name}: {v.description}" + (f" [{v.unit}]" if v.unit else "") for v in task.report_values]
    return "\n".join(lines)


def run_task(project: Project, llm: LLMClient, task: TaskSpec, setting: str, model: str, repeat_index: int = 0,
             max_steps: int = 30, tag: str = "") -> dict[str, Any]:
    model = resolve_model(model)
    run_id = f"{task.id}-{setting}-{model.replace('claude-', '')}-{repeat_index}" + (f"-{tag}" if tag else "")
    with tempfile.TemporaryDirectory(prefix="tk-agent-") as tmp:
        ws = prepare_workspace(project, setting, Path(tmp) / "workspace")
        instructions = (ws / "AGENTS.md").read_text() if setting == "full" and (ws / "AGENTS.md").exists() else None
        agent = AgentRun(llm, ws, model, task_prompt(task), run_id, instructions=instructions, max_steps=max_steps)
        result = agent.run()
    result.update(task=task.id, setting=setting, repeat=repeat_index, tag=tag)
    if task.expected and Path(task.expected).exists():
        result["grade"] = grade(result["answer"], task.expected)
    project.runs_dir.mkdir(parents=True, exist_ok=True)
    (project.runs_dir / f"{run_id}.json").write_text(json.dumps(result, indent=1, ensure_ascii=False, default=str))
    return result


def run_matrix(project: Project, llm: LLMClient, settings: list[str], models: list[str], repeats: int,
               task_ids: list[str] | None = None, max_steps: int = 30, tag: str = "",
               on_result: Any = None) -> list[dict[str, Any]]:
    from concurrent.futures import ThreadPoolExecutor

    tasks = [t for t in project.config.tasks if not task_ids or t.id in task_ids]
    jobs = [(t, s, m, r) for t in tasks for m in models for s in settings for r in range(repeats)]

    def job(args):
        t, s, m, r = args
        res = run_task(project, llm, t, s, m, r, max_steps=max_steps, tag=tag)
        if on_result:
            on_result(res)
        return res

    with ThreadPoolExecutor(max_workers=max(1, llm.settings.max_concurrency)) as pool:
        return list(pool.map(job, jobs))


def regrade_runs(project: Project, tag: str | None = None) -> list[dict[str, Any]]:
    """Grade the saved runs again with the tasks' current expected answers (no model calls).

    Needed when the expected answer changes after the runs, for example because the materials
    changed and the reference solution was run again.
    """
    tasks = {t.id: t for t in project.config.tasks}
    out = []
    if not project.runs_dir.exists():
        return out
    for f in sorted(project.runs_dir.glob("*.json")):
        try:
            result = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        if tag and not (result.get("tag") == tag or f.stem.endswith(f"-{tag}")):
            continue
        task = tasks.get(result.get("task", ""))
        if task and task.expected and Path(task.expected).exists():
            result["grade"] = grade(result.get("answer"), task.expected)
            f.write_text(json.dumps(result, indent=1, ensure_ascii=False, default=str))
        out.append(result)
    return out


def summarize(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for r in results:
        groups.setdefault((r["task"], r["model"], r["setting"]), []).append(r)
    rows = []
    for (task, model, setting), rs in sorted(groups.items()):
        graded = [r for r in rs if r.get("grade")]
        n = len(rs)
        rows.append({
            "task": task, "model": model, "setting": setting, "runs": n,
            "answered": sum(r["status"] == "answered" for r in rs),
            "all_correct": sum(bool(r.get("grade", {}).get("all_correct")) for r in graded),
            "mean_score": round(sum(r["grade"]["score"] for r in graded) / len(graded), 3) if graded else None,
            "issues_reported": sum(r["grade"].get("open_issues_reported", 0) for r in graded),
            "issues_required": sum(r["grade"].get("open_issues_required", 0) for r in graded),
            "mistakes": sorted({m for r in graded for m in r["grade"].get("mistakes", [])}),
            "mean_steps": round(sum(r["steps"] for r in rs) / n, 1),
            "mean_tokens": round(sum(r["usage"]["input"] + r["usage"]["cache_read"] + r["usage"]["cache_write"]
                                     + r["usage"]["output"] for r in rs) / n),
            "mean_cost_usd": round(sum(r["usage"]["cost_usd"] for r in rs) / n, 4),
            "mean_seconds": round(sum(r["seconds"] for r in rs) / n, 1),
            "used_repository_tools": sum(bool(r.get("used_repository_tools")) for r in rs),
            "invalid_tool_calls": sum(r.get("invalid_tool_calls", 0) for r in rs),
        })
    return rows


def report_markdown(rows: list[dict[str, Any]], build_cost: float | None = None) -> str:
    lines = ["| Task | Model | Setting | Runs | All values correct | Mean score | Open issues | Typical mistakes | "
             "Steps | Tokens | Cost $ | Seconds |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| {r['task']} | {r['model'].replace('claude-', '')} | {r['setting']} | {r['runs']} | "
            f"{r['all_correct']}/{r['runs']} | {r['mean_score']} | {r['issues_reported']}/{r['issues_required']} | "
            f"{', '.join(r['mistakes']) or '-'} | {r['mean_steps']} | {r['mean_tokens']} | {r['mean_cost_usd']} | "
            f"{r['mean_seconds']} |")
    if build_cost is not None:
        lines.append(f"\nRepository build cost (model calls of all builds and updates so far): ${build_cost:.2f} (estimate).")
    return "\n".join(lines)


def run_task_checks(project: Project, llm: LLMClient) -> list[dict[str, Any]]:
    """Used by `validate --with-tasks`: one full-repository run per task with the build model."""
    out = []
    for task in project.config.tasks:
        r = run_task(project, llm, task, "full", project.config.model, tag=f"validate-{short_hash(now_iso(), 6)}")
        g = r.get("grade")
        passed = r["status"] == "answered" and (g is None or g["all_correct"])
        summary = f"status {r['status']}" + (f", {g['correct']}/{g['total']} values correct" if g else "")
        out.append({"task": task.id, "passed": passed, "summary": summary, "run_id": r["run_id"]})
    return out
