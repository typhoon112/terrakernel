"""TerraKernel command line interface."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from terrakernel import __version__
from terrakernel.config import get_settings, resolve_model
from terrakernel.models import Gap
from terrakernel.project import Project, ProjectConfig, TaskSpec

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Compile research materials into an AI-native research repository.")
console = Console()


def _llm(project: Project | None = None, model: str | None = None):
    from terrakernel.llm.client import LLMClient

    settings = get_settings()
    if model:
        settings.model = resolve_model(model)
    cache = project.llm_cache_dir if project else None
    return LLMClient(settings, cache_dir=cache)


def _load_tasks(tasks_file: Path | None) -> list[TaskSpec]:
    if not tasks_file:
        return []
    try:
        data = yaml.safe_load(tasks_file.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise typer.BadParameter(f"Cannot read tasks file {tasks_file}: {exc}") from exc
    items = data.get("tasks", data) if isinstance(data, dict) else data
    if not isinstance(items, list) or any(not isinstance(t, dict) for t in items):
        raise typer.BadParameter("Tasks must be a YAML list, or a mapping containing a 'tasks' list.")
    tasks = []
    for t in items:
        t = dict(t)
        if t.get("expected"):
            t["expected"] = str((tasks_file.parent / t["expected"]).resolve())
        try:
            tasks.append(TaskSpec.model_validate(t))
        except ValueError as exc:
            raise typer.BadParameter(f"Invalid task in {tasks_file}: {exc}") from exc
    return tasks


def _create_project(materials: Path, output: Path, goal: str, tasks: Path | None,
                    name: str | None, model: str | None) -> Project:
    materials, output = materials.resolve(), output.resolve()
    if not materials.is_dir():
        raise typer.BadParameter(f"Materials directory does not exist: {materials}")
    if not goal.strip():
        raise typer.BadParameter("Provide a non-empty research goal with --goal.")
    if output == materials or materials in output.parents:
        raise typer.BadParameter("Choose an output directory outside the materials directory.")
    if (output / ".terrakernel" / "project.yaml").exists():
        raise typer.BadParameter(f"Repository already exists. Continue with: terrakernel build {shlex.quote(str(output))}")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise typer.BadParameter(f"Output is not an empty directory: {output}. Choose a new output directory.")
    research_tasks = _load_tasks(tasks) or [TaskSpec(id="research-goal", title="Research goal", prompt=goal.strip())]
    cfg = ProjectConfig(name=name or output.name, goal=goal.strip(), materials=str(materials),
                        tasks=research_tasks, model=resolve_model(model))
    return Project.create(output, cfg)


def _print_ingest_report(project: Project) -> None:
    path = project.state / "ingest-report.json"
    if not path.exists():
        return
    report = json.loads(path.read_text())
    table = Table(title="Imported materials")
    for col in ("file", "status", "evidence", "detail"):
        table.add_column(col)
    for item in report.get("files", []):
        table.add_row(escape(item["path"]), item["status"], str(item.get("evidence", "")),
                      escape(item.get("reason", "")))
    console.print(table)
    console.print(f"Import report: {path}", markup=False)


def _print_build_outcome(project: Project, results: dict) -> None:
    repo = shlex.quote(str(project.repo))
    failed = next((stage for stage, result in results.items() if result["status"] == "failed"), None)
    if failed:
        console.print(f"Build stopped at {failed}. Fix the reported issue, then retry:", markup=False)
        console.print(f"  terrakernel build {repo}", markup=False)
        if failed == "validate":
            console.print(f"Validation details: {project.validation_path}", markup=False)
        return
    if "validate" not in results:
        console.print("Selected stages finished. Continue the full build with:")
        console.print(f"  terrakernel build {repo}", markup=False)
        return
    console.print("[bold green]Repository ready[/]")
    console.print(f"Output: {project.repo}\nStart here: {project.repo / 'AGENTS.md'}", markup=False)
    console.print("Open this directory in your Agent and follow AGENTS.md to use its knowledge, tools and skills.")
    gaps = _open_gaps(project)
    console.print(f"Open questions: {len(gaps)}. Review with: terrakernel gaps {repo}", markup=False)
    console.print(f"After changing your materials: terrakernel update {repo}", markup=False)
    console.print(f"Export a preview: terrakernel site {repo}", markup=False)


def _print_stage_results(results: dict) -> None:
    table = Table(title="Pipeline")
    for col in ("stage", "status", "seconds", "model calls", "est. cost $", "summary"):
        table.add_column(col)
    for name, r in results.items():
        rep = r.get("report") or {}
        summary = ", ".join(f"{k}={v}" for k, v in rep.items() if isinstance(v, int | float | str) and k != "status")[:110]
        if r.get("error"):
            summary = r["error"][:110]
        table.add_row(name, r["status"], str(r["seconds"]), str(r.get("model_calls", 0)),
                      f"{r.get('cost_usd_estimate', 0):.3f}", summary)
    console.print(table)


@app.command()
def version() -> None:
    """Print the TerraKernel version."""
    console.print(__version__)


@app.command()
def init(
    materials: Annotated[Path, typer.Argument(help="Directory with the research materials")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Directory of the repository to create")],
    goal: Annotated[str, typer.Option(help="Research goal the repository should support")],
    tasks: Annotated[Path | None, typer.Option(help="YAML file with research tasks")] = None,
    name: Annotated[str | None, typer.Option(help="Repository name")] = None,
    model: Annotated[str | None, typer.Option(help="Model used for building (alias: opus|sonnet|haiku)")] = None,
) -> None:
    """Create a TerraKernel repository for a set of materials (no model calls)."""
    project = _create_project(materials, output, goal, tasks, name, model)
    console.print(f"Initialised {project.config.name} at {project.repo} ({len(project.config.tasks)} task(s)).",
                  markup=False)
    console.print(f"Next: terrakernel build {shlex.quote(str(project.repo))}", markup=False)


@app.command()
def build(
    repo: Annotated[Path, typer.Argument(help="Materials directory with --goal and --output, or an existing repository")],
    start: Annotated[str | None, typer.Option("--from", help="First stage to run")] = None,
    until: Annotated[str | None, typer.Option(help="Last stage to run")] = None,
    only: Annotated[str | None, typer.Option(help="Comma-separated stages to run")] = None,
    force: Annotated[bool, typer.Option(help="Ignore fingerprints and redo work")] = False,
    goal: Annotated[str | None, typer.Option(help="Research goal for a new repository")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="New repository directory")] = None,
    tasks: Annotated[Path | None, typer.Option(help="Optional YAML file with research tasks")] = None,
    name: Annotated[str | None, typer.Option(help="Name for a new repository")] = None,
    model: Annotated[str | None, typer.Option(help="Build model for a new repository (opus|sonnet|haiku or model ID)")] = None,
) -> None:
    """Build directly from materials, or continue building an existing repository."""
    from terrakernel.runner import STAGES, Pipeline

    selected = [s.strip() for s in only.split(",")] if only is not None else None
    requested = [s for s in (start, until) if s is not None] + (selected or [])
    if any(s not in STAGES for s in requested):
        raise typer.BadParameter(f"Unknown stage. Choose from: {', '.join(STAGES)}")
    if selected is not None and (start is not None or until is not None):
        raise typer.BadParameter("Use either --only or --from/--until.")
    if start and until and STAGES.index(start) > STAGES.index(until):
        raise typer.BadParameter("--from must not come after --until.")
    if output is not None:
        if goal is None:
            raise typer.BadParameter("Provide --goal when building from materials with --output.")
        if (start and start != "ingest") or (selected is not None and "ingest" not in selected):
            raise typer.BadParameter("A new repository must start with ingest.")
        project = _create_project(repo, output, goal, tasks, name, model)
        console.print(f"Creating repository: {project.repo}", markup=False)
    else:
        if any(value is not None for value in (goal, tasks, name, model)):
            raise typer.BadParameter("New repository options require --output. To continue, use: terrakernel build REPO")
        try:
            project = Project.open(repo)
        except FileNotFoundError as exc:
            raise typer.BadParameter("To build from materials, provide --goal TEXT --output REPO. "
                                     "Otherwise choose an existing TerraKernel repository.") from exc

    def show_progress(event: dict) -> None:
        if event["kind"] in ("stage_start", "item", "warning", "error", "stage_end"):
            console.print(f"[dim]{event['at'][11:19]}[/] [cyan]{event['stage']:<9}[/] {escape(event['message'])}")
        if event["stage"] == "ingest" and event["kind"] == "stage_end":
            _print_ingest_report(project)

    llm = _llm(project, project.config.model)
    project.add_listener(show_progress)
    try:
        results = Pipeline(project, llm).run(start=start, until=until, force=force, only=selected)
        _print_stage_results(results)
        usage = llm.usage.as_dict()
        console.print(f"model calls: {usage['calls']} (+{usage['cached_responses']} cached), "
                      f"tokens in/out: {usage['input_tokens'] + usage['cache_read_tokens'] + usage['cache_write_tokens']}/"
                      f"{usage['output_tokens']}, estimated cost: ${usage['cost_usd_estimate']:.3f}")
        _print_build_outcome(project, results)
    finally:
        project.close()
    if any(r["status"] == "failed" for r in results.values()):
        raise typer.Exit(1)


@app.command()
def status(repo: Annotated[Path, typer.Argument()]) -> None:
    """Show stage status and knowledge-base statistics."""
    project = Project.open(repo)
    state = project.load_state()
    table = Table(title=f"{project.config.name}")
    for col in ("stage", "status", "finished", "seconds", "model calls"):
        table.add_column(col)
    for name, st in state.get("stages", {}).items():
        table.add_row(name, st.get("status", ""), st.get("finished", ""), str(st.get("seconds", "")),
                      str(st.get("model_calls", "")))
    console.print(table)
    console.print_json(json.dumps(project.kb.stats()))


@app.command()
def kb(
    repo: Annotated[Path, typer.Argument()],
    type_: Annotated[str | None, typer.Option("--type", help="Filter by object type")] = None,
    gaps: Annotated[bool, typer.Option(help="Show gaps")] = False,
    relations: Annotated[bool, typer.Option(help="Show relations")] = False,
) -> None:
    """Inspect the source knowledge base."""
    project = Project.open(repo)
    store = project.kb
    if gaps:
        for g in store.gaps():
            console.print(f"[yellow]{g.severity.value:<8}[/] {g.id}\n          {g.description}")
        return
    if relations:
        for r in store.relations():
            console.print(f"{r.type.value:<16} {r.src}  ->  {r.dst}   [dim]{r.note[:100]}[/]")
        return
    for o in store.objects(type_):
        links = store.links(o.id)
        console.print(f"[bold]{o.id}[/] [dim]({o.basis.value}, {o.status.value}, {len(links)} evidence)[/]\n  {o.summary}")


@app.command()
def run_task(
    repo: Annotated[Path, typer.Argument()],
    task: Annotated[str, typer.Argument(help="Task id")],
    setting: Annotated[str, typer.Option(help="raw | knowledge | full")] = "full",
    model: Annotated[str | None, typer.Option(help="Model (alias: opus|sonnet|haiku)")] = None,
    max_steps: Annotated[int, typer.Option()] = 30,
) -> None:
    """Run one research task with the built-in agent and grade it."""
    from terrakernel.agent.evaluate import run_task as _run

    project = Project.open(repo)
    t = next((x for x in project.config.tasks if x.id == task), None)
    if t is None:
        raise typer.BadParameter(f"unknown task {task!r}")
    llm = _llm(project)
    r = _run(project, llm, t, setting, model or project.config.model, max_steps=max_steps, tag="cli")
    for step in r["trace"]:
        calls = ", ".join(c["name"] for c in step["tool_calls"]) or "-"
        console.print(f"[dim]step {step['step']:>2}[/] {calls:<40} {step['text'][:100]!r}")
    console.print_json(json.dumps({k: r.get(k) for k in ("status", "steps", "seconds", "usage", "answer", "grade",
                                                          "invalid_tool_calls", "used_repository_tools")}, default=str))


@app.command()
def eval(  # noqa: A001
    repo: Annotated[Path, typer.Argument()],
    settings: Annotated[str, typer.Option(help="Comma-separated settings")] = "raw,knowledge,full",
    models: Annotated[str, typer.Option(help="Comma-separated models")] = "opus",
    repeats: Annotated[int, typer.Option()] = 1,
    tasks: Annotated[str | None, typer.Option(help="Comma-separated task ids")] = None,
    max_steps: Annotated[int, typer.Option()] = 30,
    out: Annotated[Path | None, typer.Option(help="Directory for the report (JSON + Markdown)")] = None,
    tag: Annotated[str, typer.Option(help="Run tag (distinguishes repeated evaluations)")] = "eval",
    regrade: Annotated[bool, typer.Option(help="Grade the saved runs with this tag again; no model calls")] = False,
    expected: Annotated[Path | None, typer.Option(
        help="With --regrade: new expected-answer file for the task (one task, or use --tasks)")] = None,
) -> None:
    """Evaluate the repository: the same agent in raw / knowledge / full workspaces, graded."""
    from terrakernel.agent.evaluate import regrade_runs, report_markdown, run_matrix, summarize

    project = Project.open(repo)
    if regrade:
        if expected:
            cfg = project.config
            wanted = tasks.split(",") if tasks else [t.id for t in cfg.tasks]
            if len(wanted) != 1:
                raise typer.BadParameter("--expected applies to one task; name it with --tasks")
            for t in cfg.tasks:
                if t.id == wanted[0]:
                    t.expected = str(expected.resolve())
            project.save_config(cfg)
        results = [r for r in regrade_runs(project, tag) if not tasks or r.get("task") in tasks.split(",")]
        if not results:
            raise typer.BadParameter(f"no saved runs with tag {tag!r}")
    else:
        llm = _llm(project)
        model_list = [resolve_model(m) for m in models.split(",")]
        results = run_matrix(project, llm, settings.split(","), model_list, repeats,
                             task_ids=tasks.split(",") if tasks else None, max_steps=max_steps, tag=tag,
                             on_result=lambda r: console.print(
                                 f"{r['task']} {r['setting']:<9} {r['model']:<18} #{r['repeat']} {r['status']:<9} "
                                 f"score={r.get('grade', {}).get('score')} steps={r['steps']} "
                                 f"mistakes={r.get('grade', {}).get('mistakes')}"))
    rows = summarize(results)
    build_cost = project.total_model_cost()["cost_usd_estimate"]
    md = report_markdown(rows, build_cost)
    console.print(md)
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / "eval.json").write_text(json.dumps({"rows": rows, "runs": [
            {k: v for k, v in r.items() if k != "trace"} for r in results]}, indent=1, default=str))
        (out / "eval.md").write_text(md + "\n")
        console.print(f"report written to {out}")


@app.command()
def validate(
    repo: Annotated[Path, typer.Argument()],
    with_tasks: Annotated[bool, typer.Option(help="Also run each task once with the full repository")] = False,
) -> None:
    """Validate the generated repository (structure, OKF, skills, tools, tests; optionally tasks)."""
    from terrakernel.validate import run_validate

    project = Project.open(repo)
    llm = _llm(project) if with_tasks else None
    res = run_validate(project, llm, with_tasks=with_tasks)
    report = json.loads(project.validation_path.read_text())
    for c in report["checks"]:
        if c["status"] in ("fail", "warn"):
            console.print(f"[{'red' if c['status'] == 'fail' else 'yellow'}]{c['status']:<4}[/] {c['group']}/{c['check']} "
                          f"{c['target']} {c['detail']}")
    console.print(res)
    if res["fail"]:
        raise typer.Exit(1)


@app.command()
def update(
    repo: Annotated[Path, typer.Argument()],
    materials: Annotated[Path | None, typer.Option(help="Point the repository at a new materials directory")] = None,
) -> None:
    """Bring the repository in sync with changed materials and report the impact."""
    from terrakernel.runner import IngestError
    from terrakernel.update import format_report, run_update

    project = Project.open(repo)
    if materials:
        materials = materials.resolve()
        if not materials.is_dir():
            raise typer.BadParameter(f"Materials directory does not exist: {materials}")
        if materials == project.repo or materials in project.repo.parents:
            raise typer.BadParameter("The output repository must be outside the materials directory.")
        cfg = project.config
        cfg.materials = str(materials)
        project.save_config(cfg)
    llm = _llm(project)
    project.add_listener(lambda e: console.print(f"[dim]{e['at'][11:19]}[/] [cyan]{e['stage']:<9}[/] {e['message']}")
                         if e["kind"] in ("item", "warning", "error") else None)
    try:
        report = run_update(project, llm)
    except IngestError as exc:
        _print_ingest_report(project)
        console.print(f"Update stopped: {exc}", markup=False)
        console.print(f"Fix the files, then retry: terrakernel update {shlex.quote(str(project.repo))}", markup=False)
        raise typer.Exit(1) from exc
    finally:
        project.close()
    console.print(format_report(report))
    usage = llm.usage.as_dict()
    console.print(f"model calls: {usage['calls']} (+{usage['cached_responses']} cached), "
                  f"estimated cost: ${usage['cost_usd_estimate']:.3f}")


def record_answer(project: Project, gap: Gap, text: str, actor: str) -> None:
    """Append an answer to the managed answers file and mark the gap as resolved by ``actor``."""
    from terrakernel.util import now_iso

    path = project.answers_path
    header = "# Answers recorded by people\n\nEach section answers one open question found by TerraKernel.\n"
    existing = path.read_text() if path.exists() else header
    subject = project.kb.object(gap.subject_id) if gap.subject_id else None
    section = (f"\n## {gap.id}\n\nQuestion: {gap.description}" + (f" (about: {subject.name})" if subject else "")
               + f"\n\nAnswer: {text.strip()}\n\nAnswered by: {actor} on {now_iso()[:10]}\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(existing.rstrip("\n") + "\n" + section)
    gap.resolved_by, gap.resolution = actor, text.strip()
    project.kb.upsert_gaps([gap])


def _open_gaps(project: Project) -> list:
    order = {"blocking": 0, "warning": 1}
    return sorted([g for g in project.kb.gaps() if not g.resolved_by], key=lambda g: (order.get(g.severity.value, 2), g.id))


@app.command()
def site(
    repo: Annotated[Path, typer.Argument()],
    out: Annotated[Path | None, typer.Option(help="Output directory (default: <repo>/site)")] = None,
    config: Annotated[Path | None, typer.Option(help="Optional site.yaml with title and case ordering")] = None,
) -> None:
    """Export the repository as a static, bilingual showcase site."""
    from terrakernel.site import export_site

    project = Project.open(repo)
    result = export_site(project, out=out, site_config=config)
    if result["leaks"]:
        console.print("[red]possible secrets or local paths found in the site:[/]")
        for p in result["leaks"]:
            console.print(f"  {p}")
    console.print(result)


@app.command()
def gallery(
    repos: Annotated[list[Path], typer.Argument(help="Built repositories to show together")],
    out: Annotated[Path, typer.Option(help="Output directory")],
    config: Annotated[list[Path] | None, typer.Option(
        help="site.yaml for each repository, in the same order (optional)")] = None,
) -> None:
    """Export several repositories as one site with a common entry page."""
    from terrakernel.site import export_gallery

    configs: list[Path | None] = list(config or [])
    if configs and len(configs) != len(repos):
        raise typer.BadParameter("give one --config per repository, or none")
    configs = configs or [None] * len(repos)
    result = export_gallery(out, [(Project.open(r), c) for r, c in zip(repos, configs, strict=True)])
    if result["leaks"]:
        console.print("[red]possible secrets or local paths found in the site:[/]")
        for p in result["leaks"]:
            console.print(f"  {p}")
    console.print(result)


@app.command()
def serve(
    path: Annotated[Path, typer.Argument(help="Directory to serve (a site/ folder, or a repository)")],
    port: Annotated[int, typer.Option()] = 8765,
    host: Annotated[str, typer.Option(help="Bind address")] = "0.0.0.0",
) -> None:
    """Serve an exported site over HTTP (read-only, no directory listing)."""
    from terrakernel.site import SiteServer

    root = path / "site" if (path / "site" / "index.html").exists() else path
    if not (root / "index.html").exists():
        raise typer.BadParameter(f"{root} has no index.html; run `terrakernel site` first")
    SiteServer(root, host, port).serve_forever()


DEMO_ANSWERS = (
    (("issue time", "model b"), "Vendor B confirmed by email that forecasts are issued daily at 10:00 UTC for the "
     "following UTC calendar day, so model B is day-ahead with lead times of 14 to 38 hours, comparable to model A."),
    (("following day",), "Yes: model A's 'following day' is the UTC calendar day, and each hour is covered by exactly "
     "one issue (no overlapping issues)."),
)


@app.command()
def demo(
    out: Annotated[Path, typer.Option(help="Directory for the built showcases")] = Path("artifacts/demo"),
    models: Annotated[str, typer.Option(help="Models for the graded agent runs")] = "haiku",
    repeats: Annotated[int, typer.Option()] = 1,
    skip_eval: Annotated[bool, typer.Option(help="Build and export the sites without agent runs")] = False,
) -> None:
    """Build both example showcases end to end into ready-to-serve static sites (calls the model)."""
    import shutil

    from terrakernel.agent.evaluate import run_matrix
    from terrakernel.runner import Pipeline
    from terrakernel.site import export_gallery
    from terrakernel.update import run_update

    root = Path(__file__).resolve().parents[2]
    examples = root / "examples"
    if not examples.exists():
        raise typer.BadParameter("the demo needs the examples/ directory of a source checkout")
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    model_list = [resolve_model(m) for m in models.split(",")]

    def build(name: str, example: str) -> tuple[Project, Any]:
        tasks_file = examples / example / "tasks.yaml"
        goal = " ".join(str(yaml.safe_load(tasks_file.read_text()).get("goal", "")).split())
        repo = out / name
        if repo.exists():
            shutil.rmtree(repo)
        project = Project.create(repo, ProjectConfig(
            name=name, goal=goal, materials=str((examples / example / "materials").resolve()),
            tasks=_load_tasks(tasks_file), model=resolve_model(None)))
        llm = _llm(project, project.config.model)
        console.print(f"[bold]{name}[/]: building")
        results = Pipeline(project, llm).run()
        _print_stage_results(results)
        if any(r["status"] == "failed" for r in results.values()):
            raise typer.Exit(1)
        return project, llm

    def evaluate(project: Project, llm: Any, settings: list[str]) -> None:
        if skip_eval:
            return
        run_matrix(project, llm, settings, model_list, repeats, tag="demo",
                   on_result=lambda r: console.print(f"  {r['setting']:<9} {r['model']:<18} {r['status']} "
                                                     f"score={(r.get('grade') or {}).get('score')}"))

    # wind: answers from people, then a change in the materials
    project, llm = build("wind", "wind-forecast-eval")
    for gap in _open_gaps(project):
        for keys, text in DEMO_ANSWERS:
            if all(k in gap.description.lower() for k in keys) and not gap.resolved_by:
                record_answer(project, gap, text, "human:demo")
    if project.answers_path.exists():
        console.print("wind: applying answers from people")
        run_update(project, llm)
    v2 = out / "wind-materials-v2"
    if v2.exists():
        shutil.rmtree(v2)
    shutil.copytree(project.materials_dir, v2)
    desc = v2 / "data_description.md"
    desc.write_text(desc.read_text().replace("2023-07-01T00:00:00Z | 120 MW", "2023-06-01T00:00:00Z | 120 MW")
                    .replace("hour ending 2023-07-01T00:00:00Z", "hour ending 2023-06-01T00:00:00Z"))
    # the expected answer changes with the materials: run the independent reference solution again
    expected_v2 = out / "wind-expected-v2.json"
    subprocess.run([sys.executable, str(examples / "wind-forecast-eval" / "reference" / "solution.py"),
                    "--materials", str(v2), "--out", str(expected_v2), "--capacity-change", "2023-06-01T00:00:00Z"],
                   check=True, capture_output=True)
    cfg = project.config
    cfg.materials = str(v2)
    for t in cfg.tasks:
        if t.id == "compare-forecast-models":
            t.expected = str(expected_v2)
    project.save_config(cfg)
    console.print("wind: materials changed (capacity expansion date), updating")
    run_update(project, llm)
    evaluate(project, llm, ["raw", "knowledge", "full"])

    project2, llm2 = build("heatwave", "heatwave-days")
    evaluate(project2, llm2, ["raw", "full"])
    console.print(export_gallery(out / "site", [(project, root / "demo" / "site.yaml"),
                                                (project2, root / "demo" / "site-heatwave.yaml")]))
    console.print(f"[bold]ready[/]: uv run terrakernel serve {out}/site --port 8765")


@app.command()
def gaps(repo: Annotated[Path, typer.Argument()],
         all_: Annotated[bool, typer.Option("--all", help="Also show answered gaps")] = False) -> None:
    """List open questions (gaps) the materials leave unresolved, numbered for `terrakernel answer`."""
    project = Project.open(repo)
    for i, g in enumerate(_open_gaps(project), start=1):
        subject = project.kb.object(g.subject_id) if g.subject_id else None
        console.print(f"[bold]{i:>2}.[/] [{'red' if g.severity.value == 'blocking' else 'yellow'}]{g.severity.value}[/] "
                      f"{g.description}" + (f"  [dim]({subject.name})[/]" if subject else "") + f"\n     [dim]{g.id}[/]")
    if all_:
        for g in project.kb.gaps():
            if g.resolved_by:
                console.print(f"[green]resolved[/] {g.description}\n     [dim]{g.resolved_by}: {g.resolution}[/]")


@app.command()
def answer(
    repo: Annotated[Path, typer.Argument()],
    gap: Annotated[str, typer.Argument(help="Gap number from `terrakernel gaps`, or its id")],
    text: Annotated[str, typer.Argument(help="The answer, as a complete statement")],
    by: Annotated[str | None, typer.Option(help="Who answers (recorded as human:<by>)")] = None,
    no_update: Annotated[bool, typer.Option(help="Only record the answer; do not update the repository")] = False,
) -> None:
    """Answer an open question. The answer becomes human-confirmed knowledge and the repository is updated."""
    import getpass

    from terrakernel.update import format_report, run_update

    project = Project.open(repo)
    open_gaps = _open_gaps(project)
    target = None
    if gap.isdigit() and 1 <= int(gap) <= len(open_gaps):
        target = open_gaps[int(gap) - 1]
    else:
        matches = [g for g in project.kb.gaps() if g.id == gap] or [g for g in open_gaps if gap in g.id]
        if len(matches) == 1:
            target = matches[0]
    if target is None:
        raise typer.BadParameter(f"no unique open gap matches {gap!r}; run `terrakernel gaps`")
    actor = f"human:{by or getpass.getuser()}"
    record_answer(project, target, text, actor)
    console.print(f"Recorded the answer to {target.id} as {actor}.")
    if no_update:
        return
    llm = _llm(project)
    project.add_listener(lambda e: console.print(f"[dim]{e['at'][11:19]}[/] [cyan]{e['stage']:<9}[/] {e['message']}")
                         if e["kind"] in ("item", "warning", "error") else None)
    report = run_update(project, llm, related_objects={target.subject_id} if target.subject_id else None)
    console.print(format_report(report))


@app.command()
def doctor() -> None:
    """Check the model endpoint and which structured-output strategy it honors."""
    llm = _llm()
    try:
        text = llm.text("Reply with exactly: ok", model="claude-haiku-5-5", max_tokens=64)
        console.print(f"model endpoint reachable: reply={text.strip()!r}")
        strategy = llm.probe_structured()
        console.print(f"structured-output strategy: [bold]{strategy}[/]")
    except Exception as e:
        console.print(f"[red]model endpoint check failed:[/] {e}")
        sys.exit(1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
