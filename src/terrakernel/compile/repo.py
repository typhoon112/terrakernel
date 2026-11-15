"""Compile skills, entry files and agent adapters."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from terrakernel.builtin import skill_body
from terrakernel.compile.context import gap_context
from terrakernel.llm.client import LLMClient
from terrakernel.plan import RUNTIME_TOOLS
from terrakernel.plan.spec import RepositoryPlan, SkillPlan
from terrakernel.project import Project
from terrakernel.util import now_iso, write_text_stable

RUNTIME_SIGNATURES = {
    "list_datasets": "rt.list_datasets() -> list[str]  # list configured dataset names",
    "dataset_info": "rt.dataset_info(name) -> dict  # file, columns, units, timestamp convention, open issues",
    "load_dataset": "rt.load_dataset(name) -> DataFrame  # UTC index in the canonical convention, canonical units",
    "load_series": "rt.load_series(name, column=None) -> Series  # one canonical column; see .attrs['terrakernel']",
    "load_array": "rt.load_array(name, variable) -> xarray.DataArray  # NetCDF variable in its canonical unit",
    "common_valid_sample": "rt.common_valid_sample(**series) -> DataFrame  # rows where every series is present",
    "parameter_series": "rt.parameter_series(name, index) -> Series  # documented time-varying parameter per row",
    "convert_units": "rt.convert_units(values, from_unit, to_unit)  # convert values between units of the same dimension",
}
SKILL_LINK_RE = re.compile(r"\]\(([^)]+)\)")


def tool_signature(entry: dict[str, Any]) -> str:
    args = ", ".join(f"{i['name']}" for i in entry["inputs"])
    units = ", ".join(f"{i['name']} [{i['unit']}]" for i in entry["inputs"] if i.get("unit"))
    return f"rt.{entry['name']}({args}) -> {entry.get('output_unit') or 'value'}" + (f"  # inputs: {units}" if units else "")


def skill_prompt(project: Project, skill: SkillPlan, plan: RepositoryPlan, entries: list[dict[str, Any]],
                 issues: list[str] | None = None, previous: str | None = None) -> str:
    cfg = project.config
    task = next((t for t in cfg.tasks if t.id == skill.task_id), None)
    usable = {e["name"]: e for e in entries if e.get("status") in ("verified", "tested")}
    tools = [RUNTIME_SIGNATURES[t] for t in RUNTIME_TOOLS if t in RUNTIME_SIGNATURES]
    tools += [tool_signature(usable[t]) + f"  # {usable[t]['status']}: {usable[t]['description']}"
              for t in skill.tools if t in usable]
    missing = [t for t in skill.tools if t not in usable and t not in RUNTIME_TOOLS]
    docs = [f"- ../../../knowledge/{d.path}: {d.title} — {d.description}" for d in plan.docs if d.path in skill.docs]
    comps = [f"- ../../../{e['knowledge']}: how `{e['name']}` is defined and verified" for e in entries
             if e["name"] in usable and e["name"] in skill.tools]
    object_ids = {oid for doc in plan.docs if doc.path in skill.docs for oid in doc.object_ids}
    for tool in plan.tools:
        if tool.name in skill.tools:
            object_ids.update(tool.method_ids + tool.test_object_ids)
            if tool.capability_id:
                object_ids.add(tool.capability_id)
    task_text = f"{skill.name} {skill.description} {' '.join(skill.steps)}"
    if task:
        task_text += f" {task.title} {task.prompt} {' '.join(task.acceptance)}"
    gaps = gap_context(project, object_ids, task_text)
    docs.append("- ../../../knowledge/gaps.md: full register of open and resolved gaps")
    datasets = [f"- {d.name}: {d.file}; columns " + ", ".join(f"{c.column} [{c.unit}]" for c in d.value_columns)
                for d in plan.datasets]
    params = [f"- {p.name} [{p.unit}], lookup at {p.lookup}" for p in plan.parameters]
    parts = [f"Skill name: {skill.name}", f"Task: {task.title if task else skill.task_id}",
             f"Task prompt: {task.prompt if task else ''}",
             "Acceptance criteria:\n" + "\n".join(f"- {a}" for a in (task.acceptance if task else [])),
             "Planned steps (refine them):\n" + "\n".join(f"- {s}" for s in skill.steps),
             "Available functions (exact):\n" + "\n".join(f"- {t}" for t in tools),
             "Datasets:\n" + "\n".join(datasets), "Parameters:\n" + ("\n".join(params) or "- none"),
             "Knowledge documents (link with these paths):\n" + "\n".join(docs + comps),
             "Open gaps:\n" + gaps.text,
             "Planned tools that FAILED verification (do not use them; tell the agent to report this):\n"
             + ("\n".join(f"- {m}" for m in missing) or "- none")]
    if issues and previous:
        parts += ["Your previous draft had these problems:\n" + "\n".join(f"- {i}" for i in issues),
                  "Previous draft:\n" + previous, "Return the complete corrected body."]
    return "\n\n".join(parts)


def check_skill_body(body: str, skill_dir: Path, repo: Path, allowed_calls: set[str]) -> list[str]:
    problems = []
    for target in SKILL_LINK_RE.findall(body):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        path = (skill_dir / target.split("#")[0]).resolve()
        if not path.exists():
            problems.append(f"broken link: {target}")
    for call in set(re.findall(r"\brt\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", body)):
        if call not in allowed_calls:
            problems.append(f"calls rt.{call}, which does not exist")
    for section in ("## When to use", "## Procedure", "## Output"):
        if section not in body:
            problems.append(f"missing section {section!r}")
    if len(body.splitlines()) > 220:
        problems.append("too long; keep it under 150 lines")
    return problems


def compile_skill(project: Project, llm: LLMClient, skill: SkillPlan, plan: RepositoryPlan,
                  entries: list[dict[str, Any]], model: str) -> dict[str, Any]:
    repo = project.repo
    skill_dir = repo / ".agents" / "skills" / skill.name
    skill_dir.mkdir(parents=True, exist_ok=True)
    allowed = set(RUNTIME_TOOLS) | {e["name"] for e in entries if e.get("status") in ("verified", "tested")}
    system = skill_body("write-skills")
    body = llm.text(skill_prompt(project, skill, plan, entries), system=system, model=model, max_tokens=8000)
    problems = check_skill_body(body, skill_dir, repo, allowed)
    if problems:
        body = llm.text(skill_prompt(project, skill, plan, entries, problems, body), system=system, model=model,
                        max_tokens=8000)
        problems = check_skill_body(body, skill_dir, repo, allowed)
    body = re.sub(r"^---\n.*?\n---\n", "", body.strip(), flags=re.S)
    if body.startswith("# "):
        body = body.split("\n", 1)[1].lstrip()
    verified = sorted(t for t in skill.tools if t in allowed and t not in RUNTIME_TOOLS)
    unavailable = sorted(t for t in skill.tools if t not in allowed)
    desc = skill.description.strip()
    if not desc.lower().startswith("use this skill"):
        desc = "Use this skill to " + desc[0].lower() + desc[1:]
    fm = {
        "name": skill.name,
        "description": desc[:1024],
        "license": project.config.license,
        "compatibility": "Run from the repository root with Python 3.11+ and pandas, numpy, PyYAML (see pyproject.toml).",
        "metadata": {
            "terrakernel-task": skill.task_id,
            "terrakernel-tools": ",".join(verified),
            "terrakernel-unavailable-tools": ",".join(unavailable),
            "terrakernel-docs": ",".join(skill.docs),
            "terrakernel-generated": now_iso(),
        },
    }
    task = next((t for t in project.config.tasks if t.id == skill.task_id), None)
    title = task.title if task else skill.name.replace("-", " ").capitalize()
    text = "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=110).strip() + f"\n---\n\n# {title}\n\n{body.strip()}\n"
    write_text_stable(skill_dir / "SKILL.md", text)
    mirror = repo / ".claude" / "skills" / skill.name
    for f in sorted(p for p in skill_dir.rglob("*") if p.is_file()):
        write_text_stable(mirror / f.relative_to(skill_dir), f.read_text())
    return {"name": skill.name, "path": f".agents/skills/{skill.name}/SKILL.md", "problems": problems,
            "tools": verified, "unavailable_tools": unavailable}


# ============================================================== entry files
def write_agents_md(project: Project, plan: RepositoryPlan, entries: list[dict[str, Any]], skills: list[dict[str, Any]],
                    doc_results: list[dict[str, Any]]) -> None:
    repo = project.repo
    cfg = project.config
    kb = project.kb
    open_gaps = [g for g in kb.gaps() if not g.resolved_by]
    blocking = [g for g in open_gaps if g.severity.value == "blocking"]
    conflicts = [r for r in kb.relations() if r.type.value == "conflicts_with"]
    lines = [
        f"# {cfg.name}", "",
        plan.summary, "",
        "This repository was compiled by TerraKernel from the materials in [`sources/`](sources/). "
        "Knowledge is grounded in those materials. Tool status `verified` means tests against independent "
        "reference values quoted from the materials passed; `tested` means generic checks passed without "
        "an independent reference case. See each tool's status and tests.", "",
        "## Rules", "",
        "- Read [`knowledge/index.md`](knowledge/index.md) and the documents a skill lists before analysing data.",
        "- Load data only through `research_tools` (it applies the documented units, timestamp conventions and "
        "missing-value rules). Do not re-derive these by hand.",
        "- Use the repository's verified tools for computations they cover; do not reimplement documented formulas.",
        "- Never fill or invent missing information. If something the task needs is undocumented, say so "
        "(see Open questions below).",
        "- Cite knowledge documents (and their sources) for every definition or convention you rely on.",
        "- Do not use legacy code directly when a knowledge document says it deviates from the conventions.",
        "",
        "## Tasks and skills", "",
        "| Task | Skill |", "|---|---|",
    ]
    for s in plan.skills:
        task = next((t for t in cfg.tasks if t.id == s.task_id), None)
        lines.append(f"| {task.title if task else s.task_id} | [`{s.name}`](.agents/skills/{s.name}/SKILL.md) |")
    lines += ["", "## Tools", "",
              "Python, from the repository root:", "", "```python", "import sys; sys.path.insert(0, \"tools\")",
              "import research_tools as rt", "```", "",
              "| Function | Purpose | Status |", "|---|---|---|"]
    for name in RUNTIME_TOOLS:
        sig, _, purpose = RUNTIME_SIGNATURES[name].partition("#")
        call = sig.strip().split(" -> ")[0].replace("rt.", "")
        lines.append(f"| `{call}` | {purpose.strip()} | runtime |")
    for e in entries:
        doc = e.get("knowledge")
        status = e["status"]
        if status in ("verified", "tested"):
            lines.append(f"| `{e['name']}` | {e['description']} ([definition]({doc})) | {status} |")
        else:
            lines.append(f"| ~~`{e['name']}`~~ | {e['description']} | {status}: not available |")
    lines += ["", "The same tools are exposed over MCP by [`tools/mcp_server.py`](tools/mcp_server.py) "
              "(configured in `.mcp.json` and `.codex/config.toml`). Run `python -m research_tools` from `tools/` "
              "for an overview.", "",
              "## Data", "", "| Dataset | File | Time convention | Columns |", "|---|---|---|---|"]
    for d in plan.datasets:
        cols = ", ".join(f"`{c.column}` [{c.unit or 'unit unknown'}]" for c in d.value_columns)
        lines.append(f"| `{d.name}` | [{d.file}](sources/{d.file}) | {d.time_convention}, {d.timezone or 'tz unknown'}, "
                     f"{d.resolution or '?'} | {cols} |")
    lines += ["", "## Knowledge", ""]
    for r in doc_results:
        d = next(x for x in plan.docs if f"knowledge/{x.path}" == r["path"])
        lines.append(f"- [{d.title}]({r['path']}) - {d.description}" + ("" if r["status"] == "stable" else " (draft)"))
    if conflicts:
        lines += ["", "## Conflicts recorded in the materials", ""]
        for r in conflicts[:12]:
            a, b = kb.object(r.src), kb.object(r.dst)
            lines.append(f"- **{a.name if a else r.src}** vs **{b.name if b else r.dst}**: {r.note}")
    answered = [g for g in kb.gaps() if g.resolved_by and g.resolved_by.startswith("human:")]
    if answered:
        lines += ["", "## Answered by people", ""]
        for g in answered:
            lines.append(f"- {g.description} → {g.resolution} ({g.resolved_by}; recorded in "
                         "[sources/human_answers.md](sources/human_answers.md))")
    lines += ["", "## Open questions", ""]
    if plan.capability_gaps:
        lines += ["The current plan identifies these capability limitations for the requested tasks:", ""]
        for gap in plan.capability_gaps:
            lines.append(f"- [{gap.severity}] {gap.description}")
    else:
        lines.append("- The current plan records no additional capability limitations.")
    lines += ["", f"The full register contains {len(open_gaps)} open candidate reports "
              f"({len(blocking)} originally labelled blocking) from limited extraction or reconciliation contexts. "
              "These counts do not establish actual missing material or unavailable tools. "
              "Cross-check the current knowledge and tool status before treating a report as a limitation."]
    lines += ["", "All open and resolved questions: [gap register](knowledge/gaps.md) "
              "and [complete data](knowledge/gaps.jsonl)."]
    lines += ["", "## Provenance", "",
              "- `.terrakernel/` holds the source knowledge base (`kb.sqlite`), the build plan (`spec.yaml`), "
              "dependency lineage and validation results. Rebuild or update with `terrakernel build` / "
              "`terrakernel update`.", ""]
    write_text_stable(repo / "AGENTS.md", "\n".join(lines))
    write_text_stable(repo / "CLAUDE.md", 
        "@AGENTS.md\n\n## Claude Code\n\n- Skills are mirrored in `.claude/skills/` (same content as `.agents/skills/`).\n"
        "- Approve the MCP server from `.mcp.json` when prompted to call the research tools directly.\n")


def write_adapters(project: Project) -> None:
    repo = project.repo
    name = re.sub(r"[^a-z0-9_-]+", "-", project.config.name.lower()).strip("-") or "research-tools"
    mcp = {"mcpServers": {name: {"type": "stdio", "command": "uv",
                                 "args": ["run", "--directory", "${CLAUDE_PROJECT_DIR:-.}", "python",
                                          "tools/mcp_server.py"]}}}
    write_text_stable(repo / ".mcp.json", json.dumps(mcp, indent=2) + "\n")
    (repo / ".codex").mkdir(exist_ok=True)
    write_text_stable(repo / ".codex" / "config.toml", 
        f'[mcp_servers.{name}]\ncommand = "uv"\nargs = ["run", "--directory", ".", "python", "tools/mcp_server.py"]\n'
        "startup_timeout_sec = 60\ntool_timeout_sec = 120\n")
    write_text_stable(repo / "pyproject.toml", 
        f'[project]\nname = "{name}"\nversion = "0.1.0"\ndescription = "AI-native research repository compiled by '
        f'TerraKernel"\nrequires-python = ">=3.11"\ndependencies = ["pandas>=2.2", "numpy>=2", "pyyaml>=6", '
        f'"openpyxl>=3.1", "xlrd>=2", "pyarrow>=17", "xarray>=2024.6", "netcdf4>=1.7", "mcp>=2.3,<3"]\n\n[dependency-groups]\ndev = ["pytest>=8"]\n\n[tool.uv]\npackage = false\n\n'
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
    write_text_stable(repo / ".gitignore", "__pycache__/\n.venv/\n.pytest_cache/\n.terrakernel/llm-cache/\n")


def write_registry(project: Project, plan: RepositoryPlan, entries: list[dict[str, Any]]) -> None:
    registry = {
        "name": re.sub(r"[^a-z0-9_-]+", "-", project.config.name.lower()).strip("-") or "research-tools",
        "instructions": (plan.summary[:480] + " Load data with list_datasets/dataset_info; every tool aligns its "
                         "dataset inputs on a common valid sample and uses the documented units."),
        "generated_at": now_iso(),
        "tools": [{k: v for k, v in e.items() if k not in ("test_output",)} for e in entries],
    }
    write_text_stable(project.repo / "tools" / "research_tools" / "registry.json", json.dumps(registry, indent=2,
                                                                                        ensure_ascii=False))
