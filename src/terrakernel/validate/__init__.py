"""Validate stage: check the compiled repository and record a report.

Static checks (no model calls)
- OKF v0.2 conformance of ``knowledge/`` (frontmatter, required ``type``, reserved files,
  ``okf_version`` only in the root index, actor convention, source ids used by footnotes).
- Markdown links in AGENTS.md, knowledge documents and skills resolve.
- SKILL.md frontmatter follows the Agent Skills specification (six keys, name rules,
  name equals directory, description length), and ``.claude/skills`` mirrors
  ``.agents/skills`` byte for byte.
- Skill code snippets call only functions that exist; registry entries import.
- Config files reference existing knowledge objects; every knowledge object cited by an
  artifact still exists.
- The MCP server starts and lists the verified tools.

Tool checks
- The repository's own pytest suite passes.

Task checks (optional, ``--with-tasks``)
- The built-in agent completes each task with the full repository (see ``terrakernel.agent``).

Passing structural checks does not mean the research conclusions are correct; the
report keeps "verified" (tested against quoted reference values) separate from
"generated".
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from terrakernel.compile.tools import python_env, run_pytest
from terrakernel.llm.client import LLMClient
from terrakernel.plan import RUNTIME_TOOLS, load_spec
from terrakernel.project import Project
from terrakernel.util import now_iso

LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
FOOTNOTE_REF_RE = re.compile(r"\[\^([^\]\s]+)\](?!:)")
SKILL_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
ACTOR_RE = re.compile(r"^(human:|process:)?[^\s]+(/[^\s]+)?$")


class Report:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def add(self, group: str, target: str, check: str, ok: bool | None, detail: str = "") -> None:
        status = "skip" if ok is None else ("pass" if ok else "fail")
        self.checks.append({"group": group, "target": target, "check": check, "status": status, "detail": detail})

    def warn(self, group: str, target: str, check: str, detail: str) -> None:
        self.checks.append({"group": group, "target": target, "check": check, "status": "warn", "detail": detail})

    def summary(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self.checks:
            out[c["status"]] = out.get(c["status"], 0) + 1
        return out


def split_frontmatter(text: str) -> tuple[dict[str, Any] | None, str]:
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---", 4)
    if end < 0:
        return None, text
    try:
        fm = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        return None, text
    return (fm if isinstance(fm, dict) else None), text[end + 4:]


def _check_links(report: Report, repo: Path, path: Path, text: str, group: str) -> None:
    broken = []
    for target in LINK_RE.findall(text):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        t = target.split("#")[0]
        if not t:
            continue
        base = repo / "knowledge" if t.startswith("/") and "knowledge" in path.parts else path.parent
        resolved = (base / t.lstrip("/")).resolve() if t.startswith("/") else (path.parent / t).resolve()
        if not resolved.exists():
            broken.append(target)
    report.add(group, str(path.relative_to(repo)), "links_resolve", not broken,
               f"broken: {broken[:5]}" if broken else "")


def check_okf(report: Report, repo: Path) -> None:
    kroot = repo / "knowledge"
    if not kroot.exists():
        report.add("okf", "knowledge/", "bundle_exists", False)
        return
    for path in sorted(kroot.rglob("*.md")):
        rel = str(path.relative_to(repo))
        text = path.read_text(encoding="utf-8")
        fm, body = split_frontmatter(text)
        if path.name == "index.md":
            is_root = path.parent == kroot
            ok = fm is None or (is_root and set(fm) <= {"okf_version"})
            report.add("okf", rel, "index_frontmatter", ok, "" if ok else "index.md may carry only okf_version (root)")
            _check_links(report, repo, path, text, "okf")
            continue
        if path.name == "log.md":
            dates = re.findall(r"^## (\S+)", text, flags=re.M)
            ok = all(re.match(r"^\d{4}-\d{2}-\d{2}$", d) for d in dates)
            report.add("okf", rel, "log_dates_iso", ok)
            continue
        if fm is None:
            report.add("okf", rel, "parseable_frontmatter", False)
            continue
        report.add("okf", rel, "type_present", bool(str(fm.get("type", "")).strip()))
        gen = fm.get("generated")
        if gen is not None:
            report.add("okf", rel, "generated_actor", isinstance(gen, dict) and bool(ACTOR_RE.match(str(gen.get("by", "")))))
        ver = fm.get("verified")
        if ver is not None:
            items = ver if isinstance(ver, list) else [ver]
            report.add("okf", rel, "verified_entries", all(isinstance(v, dict) and v.get("by") and v.get("at") for v in items))
        if fm.get("status") is not None:
            report.add("okf", rel, "status_value", fm["status"] in ("draft", "stable", "deprecated"))
        xt = fm.get("x-terrakernel") or {}
        if isinstance(xt, dict) and xt.get("evidence"):
            ev_file = repo / str(xt["evidence"])
            report.add("okf", rel, "evidence_file_exists", ev_file.exists(), str(xt["evidence"]))
        source_ids = {str(s.get("id")) for s in fm.get("sources", []) if isinstance(s, dict) and s.get("id")}
        missing_res = [s for s in fm.get("sources", []) if not isinstance(s, dict) or not s.get("resource")]
        report.add("okf", rel, "sources_have_resource", not missing_res)
        refs = set(FOOTNOTE_REF_RE.findall(body))
        undefined = sorted(r for r in refs if r not in source_ids)
        report.add("okf", rel, "footnotes_keyed_to_sources", not undefined,
                   f"footnote labels without a sources entry: {undefined[:5]}" if undefined else "")
        if fm.get("type") == "Attested Computation":
            report.add("okf", rel, "computation_runtime", bool(fm.get("runtime")))
            comp = fm.get("computation")
            report.add("okf", rel, "computation_file_exists", bool(comp) and (path.parent / comp).exists())
            att = (fm.get("attester") or {}).get("resource")
            report.add("okf", rel, "attester_exists", bool(att) and (path.parent / att).exists())
        if fm.get("status") == "draft":
            report.warn("okf", rel, "draft_document", "document is marked draft (attribution or review problems)")
        _check_links(report, repo, path, text, "okf")


def check_skills(report: Report, repo: Path, allowed_calls: set[str]) -> None:
    sroot = repo / ".agents" / "skills"
    if not sroot.exists():
        report.add("skills", ".agents/skills", "exists", False)
        return
    for skill_md in sorted(sroot.glob("*/SKILL.md")):
        rel = str(skill_md.relative_to(repo))
        text = skill_md.read_text(encoding="utf-8")
        fm, body = split_frontmatter(text)
        if fm is None:
            report.add("skills", rel, "frontmatter", False)
            continue
        name = str(fm.get("name", ""))
        report.add("skills", rel, "only_spec_keys", set(fm) <= SKILL_KEYS, f"extra keys: {sorted(set(fm) - SKILL_KEYS)}"
                   if set(fm) - SKILL_KEYS else "")
        report.add("skills", rel, "name_rules", bool(SKILL_NAME_RE.match(name)) and len(name) <= 64
                   and "claude" not in name and "anthropic" not in name)
        report.add("skills", rel, "name_matches_directory", name == skill_md.parent.name)
        desc = str(fm.get("description", ""))
        report.add("skills", rel, "description_length", 1 <= len(desc) <= 1024)
        meta = fm.get("metadata", {})
        report.add("skills", rel, "metadata_strings", isinstance(meta, dict) and all(isinstance(v, str) for v in meta.values()))
        if "compatibility" in fm:
            report.add("skills", rel, "compatibility_length", 1 <= len(str(fm["compatibility"])) <= 500)
        report.add("skills", rel, "under_500_lines", len(text.splitlines()) < 500)
        calls = set(re.findall(r"\brt\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", body))
        unknown = sorted(calls - allowed_calls)
        report.add("skills", rel, "calls_existing_tools", not unknown, f"unknown: {unknown}" if unknown else "")
        _check_links(report, repo, skill_md, text, "skills")
        mirror = repo / ".claude" / "skills" / skill_md.parent.name / "SKILL.md"
        report.add("skills", rel, "claude_mirror_identical", mirror.exists() and mirror.read_bytes() == skill_md.read_bytes())


def check_registry_and_mcp(report: Report, repo: Path) -> set[str]:
    reg_path = repo / "tools" / "research_tools" / "registry.json"
    if not reg_path.exists():
        report.add("tools", "registry.json", "exists", False)
        return set(RUNTIME_TOOLS)
    registry = json.loads(reg_path.read_text())
    usable = {t["name"] for t in registry.get("tools", []) if t.get("status") in ("verified", "tested")}
    verified = sorted(t["name"] for t in registry.get("tools", []) if t.get("status") == "verified")
    script = ("import json, research_tools as rt\n"
              f"names = {sorted(usable | set(RUNTIME_TOOLS))!r}\n"
              "print(json.dumps({n: callable(getattr(rt, n, None)) for n in names}))")
    proc = subprocess.run([sys.executable, "-c", script], cwd=repo, env=python_env(repo), capture_output=True, text=True,
                          timeout=120)
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        missing = [k for k, v in result.items() if not v]
        report.add("tools", "research_tools", "registry_importable", not missing, f"missing: {missing}" if missing else "")
    except (IndexError, json.JSONDecodeError):
        report.add("tools", "research_tools", "registry_importable", False, proc.stderr[-800:])
    mcp_check = textwrap_mcp(verified)
    proc = subprocess.run([sys.executable, "-c", mcp_check], cwd=repo, env=python_env(repo), capture_output=True,
                          text=True, timeout=180)
    out = proc.stdout.strip().splitlines()
    try:
        listed = set(json.loads(out[-1]))
        missing = sorted(set(verified) - listed)
        report.add("tools", "tools/mcp_server.py", "mcp_lists_verified_tools", not missing,
                   f"listed {sorted(listed)}" + (f"; missing {missing}" if missing else ""))
    except (IndexError, json.JSONDecodeError):
        report.add("tools", "tools/mcp_server.py", "mcp_lists_verified_tools", False, proc.stderr[-800:])
    return usable | set(RUNTIME_TOOLS)


def textwrap_mcp(verified: list[str]) -> str:
    return (
        "import asyncio, json, runpy, sys\n"
        "sys.argv = ['mcp_server.py']\n"
        "ns = runpy.run_path('tools/mcp_server.py', run_name='terrakernel_check')\n"
        "server = ns['server']\n"
        "async def main():\n"
        "    tools = await server.list_tools()\n"
        "    print(json.dumps([t.name for t in tools]))\n"
        "asyncio.run(main())\n"
    )


def check_config_refs(report: Report, project: Project) -> None:
    ids = {o.id for o in project.kb.objects()}
    cfg_dir = project.repo / "tools" / "research_tools" / "config"
    for name in ("datasets", "parameters", "conventions"):
        path = cfg_dir / f"{name}.yaml"
        if not path.exists():
            report.add("config", f"config/{name}.yaml", "exists", False)
            continue
        text = path.read_text()
        refs = set(re.findall(r"\b(?:concept|claim|method|dataset|constraint|capability):[\w./\-]+", text))
        unknown = sorted(refs - ids)
        report.add("config", f"config/{name}.yaml", "evidence_objects_exist", not unknown,
                   f"unknown: {unknown[:5]}" if unknown else f"{len(refs)} references")


def check_lineage(report: Report, project: Project) -> None:
    if not project.lineage_path.exists():
        report.add("lineage", "lineage.json", "exists", False)
        return
    lineage = json.loads(project.lineage_path.read_text())
    ids = {o.id for o in project.kb.objects()}
    missing = sorted({oid for a in lineage["artifacts"].values() for oid in a.get("objects", [])} - ids)
    report.add("lineage", "lineage.json", "artifact_objects_exist", not missing, f"missing: {missing[:5]}" if missing else "")
    ungrounded = [oid for oid, o in lineage["objects"].items() if not o["evidence"] and not o.get("derived_from")]
    report.add("lineage", "lineage.json", "objects_grounded", not ungrounded,
               f"objects without evidence: {ungrounded[:5]}" if ungrounded else "")


def run_validate(project: Project, llm: LLMClient | None = None, force: bool = False, with_tasks: bool = False,
                 **_: Any) -> dict[str, Any]:
    repo = project.repo
    report = Report()
    allowed = check_registry_and_mcp(report, repo)
    check_okf(report, repo)
    check_skills(report, repo, allowed)
    check_config_refs(report, project)
    check_lineage(report, project)
    agents = repo / "AGENTS.md"
    if agents.exists():
        _check_links(report, repo, agents, agents.read_text(), "entry")
        report.add("entry", "AGENTS.md", "under_32KiB", agents.stat().st_size < 32 * 1024)
    claude = repo / "CLAUDE.md"
    report.add("entry", "CLAUDE.md", "imports_agents_md", claude.exists() and "@AGENTS.md" in claude.read_text())
    tests = run_pytest(repo, "tests", timeout=900)
    report.add("tests", "tests/", "pytest", tests["returncode"] == 0 and tests["failed"] == 0 and tests["errors"] == 0,
               f"{tests['passed']} passed, {tests['failed']} failed, {tests['errors']} errors")
    spec = load_spec(project)
    statuses: dict[str, int] = {}
    for a in spec.artifacts:
        statuses[a.status] = statuses.get(a.status, 0) + 1
    task_results = None
    if with_tasks and llm is not None:
        from terrakernel.agent.evaluate import run_task_checks

        task_results = run_task_checks(project, llm)
        for r in task_results:
            report.add("tasks", r["task"], "agent_task_passes", r["passed"], r["summary"])
    summary = report.summary()
    result = {"at": now_iso(), "summary": summary, "artifact_status": statuses, "checks": report.checks,
              "tests": {k: tests[k] for k in ("passed", "failed", "errors")}, "tasks": task_results,
              "note": "Structural checks passing means the repository is well-formed and its tools pass their tests; "
                      "it does not mean research conclusions are proven."}
    project.validation_path.write_text(json.dumps(result, indent=1, ensure_ascii=False))
    failed = [c for c in report.checks if c["status"] == "fail"]
    for c in failed[:20]:
        project.emit("validate", "warning", f"FAIL {c['group']}/{c['check']} {c['target']} {c['detail']}")
    project.emit("validate", "item", f"checks: {summary}")
    return {"pass": summary.get("pass", 0), "fail": summary.get("fail", 0), "warn": summary.get("warn", 0),
            "tests": f"{tests['passed']} passed, {tests['failed'] + tests['errors']} failed"}
