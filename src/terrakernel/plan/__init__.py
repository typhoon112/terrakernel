"""Plan stage: knowledge base + tasks -> Repository Spec.

The model proposes a plan with the ``plan-repository`` builder skill. Code then checks
it against the knowledge base and the data files (IDs exist, columns exist, units are
known, conventions are not guessed, tools have what their strategy needs, skills
reference planned tools and documents). Problems are sent back for repair; whatever
cannot be repaired is dropped or marked blocked, never silently accepted.
"""

from __future__ import annotations

import json
import keyword
import re
from typing import Any

import pandas as pd

from terrakernel.builtin import skill_body
from terrakernel.llm.client import LLMClient
from terrakernel.models import Basis, KnowledgeObject, ObjectType, Severity
from terrakernel.plan.spec import Artifact, RepositoryPlan, RepositorySpec
from terrakernel.project import Project
from terrakernel.reconcile import catalog_entry
from terrakernel.units import canonical_unit, dimension
from terrakernel.util import now_iso, short_hash

RUNTIME_TOOLS = ["list_datasets", "load_dataset", "load_series", "load_array", "common_valid_sample",
                 "parameter_series", "convert_units", "dataset_info"]
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DOC_PATH_RE = re.compile(r"^[a-z0-9][a-z0-9\-_/]*\.md$")
MAX_REPAIRS = 2


# ---------------------------------------------------------------- prompt
DIGEST_BUDGET = 160_000


def _digest(project: Project, level: int) -> str:
    kb = project.kb
    objects = kb.objects()
    lines = ["# Knowledge objects (JSON lines)"]
    lines += [json.dumps(catalog_entry(o, level), ensure_ascii=False) for o in objects]
    lines.append("\n# Relations")
    note_len = (220, 120, 80, 0)[level]
    for r in kb.relations():
        keep_note = note_len and (level < 2 or r.type.value in ("conflicts_with", "applies_to", "implements"))
        lines.append(f"{r.type.value}: {r.src} -> {r.dst}" + (f"  # {r.note[:note_len]}" if keep_note and r.note else ""))
    gaps = kb.gaps()
    open_gaps = [g for g in gaps if not g.resolved_by]
    lines.append("\n# Open gaps")
    lines += [f"- [{g.severity.value}] ({g.id}) {g.description}" for g in open_gaps] or ["- none"]
    resolved = [g for g in gaps if g.resolved_by]
    if resolved and level < 1:
        lines.append("\n# Gaps resolved across sources")
        lines += [f"- {g.description[:160]} -> {g.resolution[:200] if g.resolution else ''}" for g in resolved]
    elif resolved:
        lines.append(f"\n# {len(resolved)} gaps were resolved across sources (omitted for size)")
    return "\n".join(lines)


def kb_digest(project: Project, budget: int = DIGEST_BUDGET) -> str:
    """The knowledge base as planner input, compacted progressively to fit ``budget`` characters."""
    text = ""
    for level in range(4):
        text = _digest(project, level)
        if len(text) <= budget:
            if level:
                project.emit("plan", "warning", f"knowledge digest compacted to level {level} ({len(text)} chars)")
            return text
    project.emit("plan", "warning", f"knowledge digest is {len(text)} chars even at maximum compaction")
    return text


def plan_prompt(project: Project, issues: list[str] | None = None, previous: RepositoryPlan | None = None) -> str:
    cfg = project.config
    parts = [f"Repository name: {cfg.name}", f"Research goal: {cfg.goal}", "", "# Research tasks"]
    for t in cfg.tasks:
        parts.append(f"## {t.id}: {t.title}\n{t.prompt}")
        if t.acceptance:
            parts.append("Acceptance criteria:\n" + "\n".join(f"- {a}" for a in t.acceptance))
    if not cfg.tasks:
        parts.append("(no explicit tasks: plan documentation and reusable tools for the goal)")
    parts.append(f"\nTarget agent environments: {', '.join(cfg.target_agents)}")
    parts.append(f"Generic runtime tools already provided: {', '.join(RUNTIME_TOOLS)}")
    parts.append("\n" + kb_digest(project))
    if issues and previous is not None:
        parts.append("\n# Your previous plan failed these checks\n" + "\n".join(f"- {i}" for i in issues))
        parts.append("\nPrevious plan:\n" + previous.model_dump_json())
        parts.append("\nReturn the complete corrected plan.")
    else:
        parts.append("\nProduce the repository plan.")
    return "\n".join(parts)


# ---------------------------------------------------------------- validation
def _profile_columns(obj: KnowledgeObject) -> list[str]:
    return [f.get("column") for f in obj.attributes.get("fields", []) if isinstance(f, dict)]


def validate_plan(plan: RepositoryPlan, project: Project) -> tuple[list[str], list[str]]:
    """Return (fixable issues, accepted gaps). Fixable issues are sent back for repair."""
    kb = project.kb
    objects = {o.id: o for o in kb.objects()}
    tasks = {t.id for t in project.config.tasks}
    fix: list[str] = []
    gaps: list[str] = []

    def check_ids(ids: list[str], where: str) -> None:
        for i in ids:
            if i not in objects:
                fix.append(f"{where}: unknown object id {i!r}")

    # docs
    seen_paths: set[str] = set()
    covered: set[str] = set()
    for d in plan.docs:
        if not DOC_PATH_RE.match(d.path) or ".." in d.path or d.path.rsplit("/", 1)[-1] in ("index.md", "log.md"):
            fix.append(f"doc {d.path!r}: path must be lowercase kebab-case ending in .md and not index.md/log.md")
        if d.path in seen_paths:
            fix.append(f"doc {d.path!r}: duplicate path")
        seen_paths.add(d.path)
        check_ids(d.object_ids, f"doc {d.path}")
        covered |= set(d.object_ids)
        for t in d.task_ids:
            if t not in tasks:
                fix.append(f"doc {d.path}: unknown task id {t!r}")
    # conventions
    canon: dict[str, str] = {}
    for u in plan.conventions.canonical_units:
        cu = canonical_unit(u.unit)
        if cu is None:
            fix.append(f"conventions: unknown unit {u.unit!r} for quantity {u.quantity!r}")
        elif u.quantity in canon and canon[u.quantity] != cu:
            fix.append(f"conventions: quantity {u.quantity!r} has two canonical units")
        else:
            canon[u.quantity] = cu
    check_ids(plan.conventions.evidence_object_ids, "conventions")
    # datasets
    names: set[str] = set()
    for ds in plan.datasets:
        where = f"dataset {ds.name}"
        if not ds.name.isidentifier() or ds.name != ds.name.lower():
            fix.append(f"{where}: name must be a snake_case identifier")
        if ds.name in names:
            fix.append(f"{where}: duplicate dataset name")
        names.add(ds.name)
        prof = objects.get(ds.profile_object_id)
        if prof is None or prof.type != ObjectType.dataset or prof.basis != Basis.measured:
            fix.append(f"{where}: profile_object_id must be a profiled (measured) dataset object")
            continue
        if str(prof.attributes.get("file")) != ds.file:
            fix.append(f"{where}: file {ds.file!r} does not match the profiled file {prof.attributes.get('file')!r}")
        if prof.attributes.get("sheet") is not None and ds.sheet != prof.attributes.get("sheet"):
            fix.append(f"{where}: sheet must be {prof.attributes.get('sheet')!r} for this profile")
        if (prof.attributes.get("format") == "netcdf") != (ds.format == "netcdf"):
            fix.append(f"{where}: format must be {'netcdf' if prof.attributes.get('format') == 'netcdf' else 'table'}")
        cols = _profile_columns(prof)
        if ds.time_column and ds.time_column not in cols:
            fix.append(f"{where}: time column {ds.time_column!r} not in file columns {cols}")
        if ds.time_column and ds.time_convention == "unknown":
            gaps.append(f"{where}: timestamp convention is not documented")
        if ds.resolution:
            try:
                pd.tseries.frequencies.to_offset(ds.resolution)
            except ValueError:
                fix.append(f"{where}: resolution {ds.resolution!r} is not a pandas offset alias")
        for c in ds.value_columns:
            if c.column not in cols:
                fix.append(f"{where}: value column {c.column!r} not in file columns {cols}")
            if c.unit is None:
                gaps.append(f"{where}: unit of column {c.column!r} is not documented")
                continue
            cu = canonical_unit(c.unit)
            if cu is None:
                fix.append(f"{where}: unknown unit {c.unit!r} for column {c.column!r} (use a plain symbol like kW)")
            elif c.quantity in canon and dimension(cu) != dimension(canon[c.quantity]):
                fix.append(f"{where}: unit {c.unit} of column {c.column!r} is incompatible with canonical "
                           f"{canon[c.quantity]} for {c.quantity!r}")
            elif c.quantity not in canon:
                fix.append(f"{where}: quantity {c.quantity!r} of column {c.column!r} has no canonical unit in conventions")
            check_ids(c.evidence_object_ids, f"{where}.{c.column}")
        check_ids(ds.evidence_object_ids, where)
    # parameters
    pnames: set[str] = set()
    for p in plan.parameters:
        where = f"parameter {p.name}"
        if not p.name.isidentifier() or p.name in pnames:
            fix.append(f"{where}: name must be a unique snake_case identifier")
        pnames.add(p.name)
        if canonical_unit(p.unit) is None:
            fix.append(f"{where}: unknown unit {p.unit!r}")
        if not p.schedule:
            fix.append(f"{where}: empty schedule")
        try:
            stamps = [pd.Timestamp(e.valid_from) for e in p.schedule]
            if any(s.tzinfo is None for s in stamps):
                fix.append(f"{where}: valid_from values need an explicit timezone")
            elif stamps != sorted(stamps):
                fix.append(f"{where}: schedule must be sorted by valid_from")
        except ValueError as e:
            fix.append(f"{where}: bad valid_from ({e})")
        if p.lookup == "unknown":
            gaps.append(f"{where}: the materials do not say at which point of an interval the value applies")
        check_ids(p.evidence_object_ids, where)
    # tools
    tnames: set[str] = set()
    for t in plan.tools:
        where = f"tool {t.name}"
        if not t.name.isidentifier() or keyword.iskeyword(t.name) or t.name != t.name.lower():
            fix.append(f"{where}: name must be a snake_case Python identifier")
        if t.name in tnames or t.name in RUNTIME_TOOLS:
            fix.append(f"{where}: duplicate or collides with a runtime tool")
        tnames.add(t.name)
        check_ids(t.method_ids, where)
        check_ids(t.test_object_ids, where)
        if t.strategy == "wrap_existing":
            cap = objects.get(t.capability_id or "")
            if cap is None or cap.type != ObjectType.capability or not cap.attributes.get("symbol"):
                fix.append(f"{where}: wrap_existing needs capability_id of a code capability with a symbol")
        if t.strategy == "candidate":
            if not any(objects.get(m) and objects[m].type == ObjectType.method for m in t.method_ids):
                fix.append(f"{where}: candidate needs at least one method object in method_ids")
            if not t.test_object_ids:
                gaps.append(f"{where}: no independent reference values in the materials; it can only be property-tested")
        for i in t.inputs:
            if not i.name.isidentifier():
                fix.append(f"{where}: input name {i.name!r} is not an identifier")
            if i.unit and canonical_unit(i.unit) is None:
                fix.append(f"{where}: unknown unit {i.unit!r} for input {i.name}")
    # skills
    snames: set[str] = set()
    doc_paths = {d.path for d in plan.docs}
    available_tools = tnames | set(RUNTIME_TOOLS)
    for s in plan.skills:
        where = f"skill {s.name}"
        if not SKILL_NAME_RE.match(s.name) or len(s.name) > 64 or "claude" in s.name or "anthropic" in s.name:
            fix.append(f"{where}: name must be lowercase kebab-case, at most 64 chars, without 'claude'/'anthropic'")
        if s.name in snames:
            fix.append(f"{where}: duplicate skill name")
        snames.add(s.name)
        if s.task_id not in tasks:
            fix.append(f"{where}: unknown task id {s.task_id!r}")
        for t in s.tools:
            if t not in available_tools:
                fix.append(f"{where}: tool {t!r} is neither planned nor a runtime tool")
        for d in s.docs:
            if d not in doc_paths:
                fix.append(f"{where}: document {d!r} is not a planned document path")
        if len(s.description) > 1024:
            fix.append(f"{where}: description longer than 1024 characters")
        if not s.description.strip().lower().startswith("use this skill when"):
            fix.append(f"{where}: description must start with 'Use this skill when'")
    for t in tasks - {s.task_id for s in plan.skills}:
        fix.append(f"task {t!r} has no skill")
    # coverage of task-relevant objects (warnings only)
    relevant = {o.id for o in objects.values() if o.type in (ObjectType.method, ObjectType.constraint, ObjectType.dataset)}
    missing = sorted(relevant - covered)
    if missing:
        gaps.append(f"objects not covered by any document: {', '.join(missing[:20])}")
    return fix, gaps


def _drop_invalid(plan: RepositoryPlan, project: Project) -> list[str]:
    """Last resort after repairs: remove items that still fail hard checks."""
    dropped: list[str] = []
    objects = {o.id for o in project.kb.objects()}
    for d in plan.docs:
        d.object_ids = [i for i in d.object_ids if i in objects]
    fix, _ = validate_plan(plan, project)
    bad_tools = {m.split()[1] for m in fix if m.startswith("tool ")}
    bad_datasets = {m.split()[1].rstrip(":") for m in fix if m.startswith("dataset ")}
    bad_docs = {m.split("'")[1] for m in fix if m.startswith("doc '")}
    if bad_tools:
        plan.tools = [t for t in plan.tools if t.name not in bad_tools]
        dropped += [f"tool {t}" for t in bad_tools]
    if bad_datasets:
        plan.datasets = [d for d in plan.datasets if d.name not in bad_datasets]
        dropped += [f"dataset {d}" for d in bad_datasets]
    if bad_docs:
        plan.docs = [d for d in plan.docs if d.path not in bad_docs]
        dropped += [f"doc {d}" for d in bad_docs]
    tool_names = {t.name for t in plan.tools} | set(RUNTIME_TOOLS)
    doc_paths = {d.path for d in plan.docs}
    for s in plan.skills:
        s.tools = [t for t in s.tools if t in tool_names]
        s.docs = [d for d in s.docs if d in doc_paths]
    return dropped


# ---------------------------------------------------------------- spec
def build_spec(plan: RepositoryPlan, project: Project, issues: list[str], actor: str) -> RepositorySpec:
    arts: list[Artifact] = []
    gaps = project.kb.gaps()
    open_blocking = [g.id for g in gaps if not g.resolved_by and g.severity == Severity.blocking]

    ds_objects = sorted({i for d in plan.datasets for i in [d.profile_object_id, *d.evidence_object_ids,
                                                             *[x for c in d.value_columns for x in c.evidence_object_ids]]})
    par_objects = sorted({i for p in plan.parameters for i in p.evidence_object_ids})
    conv_objects = sorted(set(plan.conventions.evidence_object_ids))
    arts.append(Artifact(id="config:datasets", kind="config", path="tools/research_tools/config/datasets.yaml",
                         title="Dataset semantics", objects=ds_objects,
                         acceptance=["every configured file loads", "units convert to the canonical units"]))
    arts.append(Artifact(id="config:parameters", kind="config", path="tools/research_tools/config/parameters.yaml",
                         title="Time-varying parameters", objects=par_objects))
    arts.append(Artifact(id="config:conventions", kind="config", path="tools/research_tools/config/conventions.yaml",
                         title="Canonical units and time convention", objects=conv_objects))
    arts.append(Artifact(id="runtime", kind="runtime", path="tools/research_tools/_runtime.py",
                         title="Generic data runtime", strategy="template",
                         depends_on=["config:datasets", "config:parameters", "config:conventions"],
                         params={"tools": RUNTIME_TOOLS}))
    arts.append(Artifact(id="test:runtime", kind="test", path="tests/test_runtime.py", title="Runtime checks",
                         depends_on=["runtime"], objects=ds_objects + par_objects))
    for t in plan.tools:
        if t.strategy == "knowledge_only":
            continue
        objs = sorted(set(t.method_ids + t.test_object_ids + ([t.capability_id] if t.capability_id else [])))
        arts.append(Artifact(
            id=f"tool:{t.name}", kind="tool", path=f"tools/research_tools/tools/{t.name}.py", title=t.name,
            description=t.purpose, objects=objs, depends_on=["runtime"], strategy=t.strategy,
            acceptance=["independent reference tests pass" if t.test_object_ids else "property tests pass"],
            params={"plan": t.model_dump()},
        ))
        arts.append(Artifact(id=f"test:{t.name}", kind="test", path=f"tests/test_{t.name}.py", title=f"tests for {t.name}",
                             objects=objs, depends_on=[f"tool:{t.name}"]))
        arts.append(Artifact(id=f"computation:{t.name}", kind="computation_doc",
                             path=f"knowledge/computations/{t.name.replace('_', '-')}.md", title=t.name,
                             objects=objs, depends_on=[f"tool:{t.name}", f"test:{t.name}"]))
    for d in plan.docs:
        arts.append(Artifact(id=f"doc:{d.path}", kind="knowledge_doc", path=f"knowledge/{d.path}", title=d.title,
                             description=d.description, objects=sorted(set(d.object_ids)),
                             params={"okf_type": d.okf_type, "task_ids": d.task_ids}))
    for s in plan.skills:
        deps = [f"tool:{t}" for t in s.tools if t not in RUNTIME_TOOLS] + ["runtime"] + [f"doc:{d}" for d in s.docs]
        objs = sorted({o for a in arts if a.id in deps for o in a.objects})
        arts.append(Artifact(id=f"skill:{s.name}", kind="skill", path=f".agents/skills/{s.name}/SKILL.md", title=s.name,
                             description=s.description, objects=objs, depends_on=deps,
                             params={"plan": s.model_dump()}, blocked_by=[]))
    arts.append(Artifact(id="entry:agents", kind="entry", path="AGENTS.md", title="Repository entry",
                         depends_on=[a.id for a in arts if a.kind in ("skill", "knowledge_doc", "tool")],
                         params={"open_blocking_gaps": open_blocking}))
    arts.append(Artifact(id="entry:claude", kind="entry", path="CLAUDE.md", depends_on=["entry:agents"]))
    arts.append(Artifact(id="entry:knowledge-index", kind="entry", path="knowledge/index.md",
                         depends_on=[a.id for a in arts if a.kind in ("knowledge_doc", "computation_doc")]))
    arts.append(Artifact(id="adapter:mcp", kind="adapter", path="tools/mcp_server.py", depends_on=["runtime"]))
    arts.append(Artifact(id="adapter:claude-code", kind="adapter", path=".mcp.json", depends_on=["adapter:mcp"]))
    arts.append(Artifact(id="adapter:codex", kind="adapter", path=".codex/config.toml", depends_on=["adapter:mcp"]))
    arts.append(Artifact(id="sources", kind="source", path="sources/", title="Original materials"))
    return RepositorySpec(generated_at=now_iso(), generated_by=actor, summary=plan.summary, plan=plan, artifacts=arts,
                          issues=issues)


def save_spec(project: Project, spec: RepositorySpec) -> None:
    import yaml

    project.spec_path.write_text(yaml.safe_dump(spec.model_dump(mode="json"), sort_keys=False, allow_unicode=True,
                                                width=110))


def load_spec(project: Project) -> RepositorySpec:
    import yaml

    return RepositorySpec.model_validate(yaml.safe_load(project.spec_path.read_text()))


def run_plan(project: Project, llm: LLMClient, force: bool = False, **_: Any) -> dict[str, Any]:
    cfg = project.config
    model = cfg.model
    system = skill_body("plan-repository")
    project.emit("plan", "progress", "planning repository")
    plan = llm.structured(plan_prompt(project), RepositoryPlan, system=system, model=model, max_tokens=32000,
                          tool_name="submit_plan", tool_description="Submit the repository plan.")
    fix, accepted = validate_plan(plan, project)
    rounds = 0
    while fix and rounds < MAX_REPAIRS:
        rounds += 1
        project.emit("plan", "warning", f"plan check found {len(fix)} problem(s); repair round {rounds}",
                     problems=fix[:20])
        plan = llm.structured(plan_prompt(project, fix, plan), RepositoryPlan, system=system, model=model,
                              max_tokens=32000, tool_name="submit_plan", tool_description="Submit the repository plan.")
        fix, accepted = validate_plan(plan, project)
    dropped = _drop_invalid(plan, project) if fix else []
    fix, accepted = validate_plan(plan, project)
    issues = [f"accepted gap: {g}" for g in accepted] + [f"dropped after repairs: {d}" for d in dropped] + \
             [f"unresolved: {f}" for f in fix]
    spec = build_spec(plan, project, issues, f"{cfg.actor}+{model}")
    save_spec(project, spec)
    for i in issues:
        project.emit("plan", "warning", i)
    counts: dict[str, int] = {}
    for a in spec.artifacts:
        counts[a.kind] = counts.get(a.kind, 0) + 1
    project.emit("plan", "item", f"plan: {len(plan.docs)} docs, {len(plan.datasets)} datasets, "
                 f"{len(plan.parameters)} parameters, {len(plan.tools)} tools, {len(plan.skills)} skills")
    return {"docs": len(plan.docs), "datasets": len(plan.datasets), "parameters": len(plan.parameters),
            "tools": len(plan.tools), "skills": len(plan.skills), "artifacts": len(spec.artifacts),
            "artifacts_by_kind": counts, "repair_rounds": rounds, "issues": len(issues),
            "fingerprint": short_hash(spec.model_dump_json())}
