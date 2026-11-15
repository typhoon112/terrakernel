"""Offline tests for deterministic parts of TerraKernel (no model calls)."""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import pandas as pd
import pytest

from terrakernel.agent.grader import grade
from terrakernel.agent.sandbox import run_python
from terrakernel.extract.grounding import check_refs, quote_score
from terrakernel.ingest import ingest_file, scan_materials
from terrakernel.lineage import impacted_artifacts
from terrakernel.llm.client import extract_json, strict_schema
from terrakernel.models import Evidence, EvidenceKind, Locator
from terrakernel.units import canonical_unit, conversion
from terrakernel.util import _normalize_volatile, write_text_stable

ROOT = Path(__file__).resolve().parents[1]
MATERIALS = ROOT / "examples" / "wind-forecast-eval" / "materials"
TEMPLATES = ROOT / "src" / "terrakernel" / "builtin" / "templates"


# ----------------------------------------------------------------------------- ingest
@pytest.fixture(scope="module")
def evidence(tmp_path_factory):
    assets = tmp_path_factory.mktemp("assets")
    sources, skipped = scan_materials(MATERIALS)
    assert not skipped
    return {s.id: ingest_file(s, MATERIALS / s.path, assets) for s in sources}


def test_scan_assigns_kinds(evidence):
    assert set(evidence) == {"data_description", "eval_forecast", "forecast_model_a", "forecast_model_b",
                             "measured_power", "paper_a_capacity_nrmse", "paper_b_mean_nrmse"}


def test_markdown_locators_have_sections_and_lines(evidence):
    items = evidence["data_description"]
    unit_item = next(e for e in items if "kW" in e.content)
    assert unit_item.locator.line_start is not None
    assert "forecast_model_b.csv" in unit_item.locator.section
    ids = [e.id for e in items]
    assert len(ids) == len(set(ids))


def test_pdf_formulas_keep_subscripts_and_symbols(evidence):
    formulas = [e.content for e in evidence["paper_a_capacity_nrmse"] if e.kind == EvidenceKind.formula]
    assert any("NRMSE_cap" in f and "Σ_t" in f and "C_t" in f for f in formulas)


def test_pdf_rule_table_extracted_with_caption(evidence):
    table = next(e for e in evidence["paper_a_capacity_nrmse"] if e.kind == EvidenceKind.table)
    assert table.content.startswith("Table 1")
    assert "| 3 | 200 | 122 | 120 | 2 |" in table.content
    assert table.locator.page == 1 and table.locator.bbox


def test_csv_profile_is_measured_not_guessed(evidence):
    cols = {e.locator.column: e for e in evidence["forecast_model_b"] if e.kind == EvidenceKind.table_column}
    assert cols["p_forecast"].meta["missing"] == 36
    assert "unit_hint" not in cols["p_forecast"].meta  # no unit token in the name: nothing guessed
    time = cols["time"].meta["datetime"]
    assert time["resolution"] == "0 days 01:00:00" and time["has_timezone"]
    assert "cannot be measured" in cols["time"].content


def test_code_symbols_record_data_handling(evidence):
    evaluate = next(e for e in evidence["eval_forecast"] if e.locator.symbol == "evaluate")
    assert "fillna" in evaluate.meta["notable_ops"]
    nrmse = next(e for e in evidence["eval_forecast"] if e.locator.symbol == "nrmse")
    assert nrmse.meta["uses_constants"] == ["CAPACITY_MW"]


def test_evidence_ids_are_stable_across_runs(tmp_path):
    sources, _ = scan_materials(MATERIALS)
    s = next(x for x in sources if x.id == "data_description")
    a = [e.id for e in ingest_file(s, MATERIALS / s.path, tmp_path)]
    b = [e.id for e in ingest_file(s, MATERIALS / s.path, tmp_path)]
    assert a == b


# ----------------------------------------------------------------------------- grounding
def test_quote_matching_tolerates_layout_but_not_invention():
    content = "NRMSE_cap = 100% ×\nsqrt(0.00025) = 1.58%"
    assert quote_score("NRMSE_cap = 100% × sqrt(0.00025) = 1.58%", content) >= 99
    assert quote_score("NRMSE_cap = 2.67%", content) < 88


def test_check_refs_rejects_foreign_evidence():
    ev = Evidence(id="ev:a:p1", source_id="a", kind=EvidenceKind.paragraph, content="Power is in kW.",
                  content_hash="x", locator=Locator())
    ok = check_refs([("ev:a:p1", "Power is in kW.")], {ev.id: ev})
    assert ok.ok
    bad = check_refs([("ev:b:p9", "Power is in kW.")], {ev.id: ev})
    assert not bad.ok and "not in this batch" in bad.problems[0]


# ----------------------------------------------------------------------------- units
def test_unit_conversions():
    assert conversion("kW", "MW") == (pytest.approx(1e-3), 0.0)
    scale, offset = conversion("degC", "K")
    assert 20 * scale + offset == pytest.approx(293.15)
    assert canonical_unit("megawatts") == "MW"
    with pytest.raises(ValueError):
        conversion("kW", "kWh")


# ----------------------------------------------------------------------------- llm helpers
def test_strict_schema_closes_objects():
    from terrakernel.extract.schemas import ExtractionResult

    schema = strict_schema(ExtractionResult)
    obj = schema["properties"]["objects"]["items"]
    assert obj["additionalProperties"] is False
    assert set(obj["required"]) == set(obj["properties"])


def test_extract_json_from_fenced_text():
    assert extract_json('Result:\n```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}


# ----------------------------------------------------------------------------- generated runtime
@pytest.fixture()
def runtime_pkg(tmp_path):
    """A minimal generated repository using the runtime template and a hand-written config."""
    pkg = tmp_path / "tools" / "research_tools"
    (pkg / "config").mkdir(parents=True)
    shutil.copyfile(TEMPLATES / "runtime.py", pkg / "_runtime.py")
    shutil.copyfile(TEMPLATES / "checks.py", pkg / "_checks.py")
    shutil.copyfile(ROOT / "src" / "terrakernel" / "units.py", pkg / "_units.py")
    (pkg / "__init__.py").write_text("")
    (tmp_path / "sources").mkdir()
    pd.DataFrame({"t": ["2023-01-01T00:00:00Z", "2023-01-01T01:00:00Z", "2023-01-01T02:00:00Z"],
                  "p": [1000.0, None, 3000.0]}).to_csv(tmp_path / "sources" / "f.csv", index=False)
    (pkg / "config" / "datasets.yaml").write_text(
        "datasets:\n- name: f\n  file: f.csv\n  time_column: t\n  time_convention: interval_beginning\n"
        "  timezone: UTC\n  resolution: 1h\n  value_columns:\n  - {column: p, quantity: power, unit: kW}\n")
    (pkg / "config" / "conventions.yaml").write_text(
        "canonical_time_convention: interval_ending\ncanonical_units:\n- {quantity: power, unit: MW}\n")
    (pkg / "config" / "parameters.yaml").write_text(
        "parameters:\n- name: cap\n  unit: MW\n  lookup: interval_start\n  schedule:\n"
        "  - {valid_from: '2023-01-01T00:00:00Z', value: 100}\n  - {valid_from: '2023-01-01T02:00:00Z', value: 120}\n")
    return tmp_path


def _run_in(repo: Path, code: str) -> str:
    import subprocess
    import sys

    proc = subprocess.run([sys.executable, "-c", code], cwd=repo, capture_output=True, text=True,
                          env={"PYTHONPATH": str(repo / "tools"), "PATH": "/usr/bin:/bin"})
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def test_runtime_applies_documented_semantics(runtime_pkg):
    out = _run_in(runtime_pkg, (
        "import json\nfrom research_tools import _runtime as rt\n"
        "s = rt.load_series('f')\n"
        "cap = rt.parameter_series('cap', s.index)\n"
        "print(json.dumps({'index': [str(i) for i in s.index], 'values': [None if v != v else v for v in s],"
        " 'cap': list(cap), 'applied': s.attrs['terrakernel']['applied']}))"))
    d = json.loads(out)
    # interval-beginning -> interval-ending shift by one hour
    assert d["index"][0] == "2023-01-01 01:00:00+00:00"
    # kW -> MW, missing kept as NaN
    assert d["values"] == [1.0, None, 3.0]
    # the hour ending 02:00 starts at 01:00 -> 100; the hour ending 03:00 starts at 02:00 -> 120
    assert d["cap"] == [100.0, 100.0, 120.0]
    assert any("shifted" in a for a in d["applied"]) and any("kW -> MW" in a for a in d["applied"])


def test_common_valid_sample_never_imputes(runtime_pkg):
    out = _run_in(runtime_pkg, (
        "import pandas as pd\nfrom research_tools import _runtime as rt\n"
        "i = pd.date_range('2023-01-01', periods=3, freq='h', tz='UTC')\n"
        "df = rt.common_valid_sample(a=pd.Series([1, None, 3.0], index=i), b=pd.Series([1, 2, None], index=i))\n"
        "print(len(df), df.attrs['terrakernel']['dropped_per_input'])"))
    assert out.startswith("1 ")


# ----------------------------------------------------------------------------- grader
def test_grader_attributes_mistakes(tmp_path):
    expected = {"values": {"x": {"value": 10.0, "rel_tol": 0.001, "abs_tol": 0}},
                "variants": {"forgot_conversion": {"x": 10000.0}},
                "required_open_issues": [{"id": "lead", "any_of": ["lead time"]}]}
    path = tmp_path / "e.json"
    path.write_text(json.dumps(expected))
    good = grade({"values": [{"name": "x", "value": 10.004}], "open_issues": ["Lead time unknown"]}, path)
    assert good["all_correct"] and good["open_issues"]["lead"]
    bad = grade({"values": [{"name": "x", "value": 10000.0}], "open_issues": []}, path)
    assert bad["mistakes"] == ["forgot_conversion"] and not bad["open_issues"]["lead"]
    assert grade(None, path)["score"] == 0.0


# ----------------------------------------------------------------------------- lineage
def test_impact_propagates_through_dependencies():
    lineage = {"artifacts": {
        "config": {"objects": ["o1"], "depends_on": []},
        "runtime": {"objects": [], "depends_on": ["config"]},
        "doc": {"objects": ["o2"], "depends_on": []},
        "skill": {"objects": [], "depends_on": ["runtime"]},
    }}
    hit = impacted_artifacts(lineage, {"o1"})
    assert set(hit) == {"config", "runtime", "skill"}


# ----------------------------------------------------------------------------- stable writes
def test_stable_write_ignores_generation_time_but_not_content_dates(tmp_path):
    f = tmp_path / "a.yaml"
    base = "generated:\n  at: '2026-01-01T00:00:00Z'\nvalid_from: '2023-07-01T00:00:00Z'\n"
    assert write_text_stable(f, base)
    assert not write_text_stable(f, base.replace("2026-01-01", "2026-02-02"))
    assert write_text_stable(f, base.replace("2023-07-01", "2023-06-01"))
    assert _normalize_volatile('  "generated_at": "2026-01-01T00:00:00Z",') == '  "generated_at": <ts>,'


# ----------------------------------------------------------------------------- sandbox
def test_sandbox_has_no_secrets_or_network(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    r = run_python("import os, socket\nprint(sorted(k for k in os.environ if 'KEY' in k))\n"
                   "try:\n    socket.create_connection(('example.com', 80), timeout=2); print('net')\n"
                   "except OSError:\n    print('no-net')\n", tmp_path, timeout=30)
    assert "[]" in r["output"]
    if r["network_isolated"]:
        assert "no-net" in r["output"]


def test_sandbox_times_out(tmp_path):
    r = run_python("while True:\n    pass\n", tmp_path, timeout=2, cpu_seconds=5)
    assert r["timed_out"] or r["exit_code"] != 0
    assert not math.isnan(len(r["output"]))


# ----------------------------------------------------------------------------- two-column PDFs
def _two_column_pdf(path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph

    ss = getSampleStyleSheet()
    w, h = A4
    doc = BaseDocTemplate(str(path), pagesize=A4)
    gap, margin = 18, 50
    col_w = (w - 2 * margin - gap) / 2
    frames = [Frame(margin, margin, col_w, h - 2 * margin, id="left"),
              Frame(margin + col_w + gap, margin, col_w, h - 2 * margin, id="right")]
    doc.addPageTemplates([PageTemplate(frames=frames)])
    story = []
    from reportlab.lib.styles import ParagraphStyle

    style = ParagraphStyle("p", parent=ss["Normal"], spaceAfter=10)
    for i in range(1, 9):
        story.append(Paragraph(f"Paragraph {i}. " + " ".join(f"word{i}x{j}" for j in range(70)), style))
    doc.build(story)


def test_two_column_reading_order(tmp_path):
    from terrakernel.models import Source, SourceKind

    pdf = tmp_path / "two_col.pdf"
    _two_column_pdf(pdf)
    src = Source(id="two_col", path="two_col.pdf", kind=SourceKind.pdf, sha256="x", size=pdf.stat().st_size)
    items = ingest_file(src, pdf, tmp_path)
    paras = [e for e in items if e.kind == EvidenceKind.paragraph]
    joined = "\n".join(e.content for e in paras)
    # no line mixes words from two paragraphs (i.e. the two columns are not interleaved)
    for e in paras:
        for line in e.content.splitlines():
            nums = {t.split("x")[0] for t in line.split() if t.startswith("word")}
            assert len(nums) <= 1, line
    # paragraphs are separated into their own blocks
    assert sum(e.content.startswith("Paragraph") for e in paras) >= 6
    # paragraphs appear in order
    starts = [joined.find(f"Paragraph {i}.") for i in range(1, 9)]
    found = [s for s in starts if s >= 0]
    assert found == sorted(found) and len(found) >= 6


# ----------------------------------------------------------------------------- human answers
def test_human_answers_are_marked_and_attributed():
    from terrakernel.extract import finalize_human, mark_human
    from terrakernel.models import Basis, KnowledgeObject, ObjectType

    sec = "Answers recorded by people > gap:ds/unit-of-x"
    ev_answer = Evidence(id="ev:human_answers:a/p2", source_id="human_answers", kind=EvidenceKind.paragraph,
                         content="Answer: x is in kW.", content_hash="1", locator=Locator(section=sec))
    ev_meta = Evidence(id="ev:human_answers:a/p3", source_id="human_answers", kind=EvidenceKind.paragraph,
                       content="Answered by: human:alice on 2026-11-14", content_hash="2", locator=Locator(section=sec))
    obj = KnowledgeObject(id="constraint:human_answers/x-unit", type=ObjectType.constraint, name="x unit")
    mark_human(obj, [ev_answer])
    finalize_human([obj], [ev_answer, ev_meta])
    assert obj.basis == Basis.human_confirmed
    assert obj.attributes["answers_gap"] == "gap:ds/unit-of-x"
    assert obj.produced_by == "human:alice" and "2026-11-14" in obj.basis_note


def test_gap_resolution_survives_reextraction_but_can_be_reopened(tmp_path):
    from terrakernel.models import Gap
    from terrakernel.store import KnowledgeBase

    kb = KnowledgeBase(tmp_path / "kb.sqlite")
    kb.upsert_gaps([Gap(id="g1", description="unit unknown", resolved_by="human:alice", resolution="kW")])
    kb.upsert_gaps([Gap(id="g1", description="unit unknown")])  # re-extracted without resolution
    assert kb.gaps()[0].resolved_by == "human:alice"
    kb.upsert_gaps([Gap(id="g1", description="unit unknown")], keep_resolution=False)
    assert kb.gaps()[0].resolved_by is None
    kb.close()


# ----------------------------------------------------------------------------- scale
def _fake_objects(n: int):
    from terrakernel.models import KnowledgeObject, ObjectType

    types = list(ObjectType)
    return [KnowledgeObject(id=f"{types[i % 6].value}:s{i % 7}/obj-{i}", type=types[i % 6], name=f"Object {i % 50}",
                            summary="A summary sentence that is reasonably long for testing purposes. " * 2,
                            attributes={"definition": "x" * 300, "unit": "MW", "formula": "y = a * x" * 20},
                            source_ids=[f"s{i % 7}"]) for i in range(n)]


def test_catalog_entries_shrink_with_level():
    from terrakernel.reconcile import catalog_entry

    o = _fake_objects(2)[0]
    sizes = [len(json.dumps(catalog_entry(o, level))) for level in range(4)]
    assert sizes == sorted(sizes, reverse=True) and sizes[3] < sizes[0]


def test_reconcile_groups_respect_budget_and_cover_everything():
    from terrakernel.reconcile import _groups, catalog_entry

    objs = _fake_objects(300)
    groups = _groups(objs, budget=40_000)
    assert len(groups) > 1
    for g in groups:
        assert sum(len(json.dumps(catalog_entry(o), ensure_ascii=False)) for o in g) <= 40_000 + 2_000
    covered = {o.id for g in groups for o in g}
    assert covered == {o.id for o in objs}


# ----------------------------------------------------------------------------- formats
def test_excel_sheets_and_parquet_are_profiled(tmp_path):
    from terrakernel.extract import profile_table_source
    from terrakernel.models import Source, SourceKind

    xlsx = tmp_path / "book.xlsx"
    with pd.ExcelWriter(xlsx) as w:
        pd.DataFrame({"t": pd.date_range("2024-01-01", periods=5, freq="D").astype(str), "temp_degC": range(5)}).to_excel(
            w, sheet_name="daily", index=False)
        pd.DataFrame({"site": ["a", "b"], "elev_m": [10.0, 20.0]}).to_excel(w, sheet_name="sites", index=False)
    src = Source(id="book", path="book.xlsx", kind=SourceKind.table, sha256="x", size=1)
    items = ingest_file(src, xlsx, tmp_path)
    profiles = [e for e in items if e.kind == EvidenceKind.dataset_profile]
    assert [p.meta["sheet"] for p in profiles] == ["daily", "sites"]
    objs, links = profile_table_source(src, items, "terrakernel/test")
    assert len(objs) == 2 and {o.attributes["sheet"] for o in objs} == {"daily", "sites"}
    assert all(lk.evidence_id.startswith("ev:book:sheet/") for lk in links)

    pq = tmp_path / "t.parquet"
    pd.DataFrame({"x": [1.0, None, 3.0]}).to_parquet(pq)
    src2 = Source(id="t", path="t.parquet", kind=SourceKind.table, sha256="x", size=1)
    cols = [e for e in ingest_file(src2, pq, tmp_path) if e.kind == EvidenceKind.table_column]
    assert cols[0].meta["missing"] == 1


def test_netcdf_attributes_are_recorded(tmp_path):
    import numpy as np
    import xarray as xr

    from terrakernel.extract import profile_table_source
    from terrakernel.models import Source, SourceKind

    times = pd.date_range("2020-01-01", periods=4, freq="D")
    ds = xr.Dataset(
        {"tas": (("time", "lat", "lon"), np.random.default_rng(0).normal(280, 5, (4, 3, 2)),
                 {"units": "K", "long_name": "Near-surface air temperature", "cell_methods": "time: mean"})},
        coords={"time": times, "lat": [10.0, 20.0, 30.0], "lon": [100.0, 110.0]},
        attrs={"title": "Test", "Conventions": "CF-1.8"})
    path = tmp_path / "tas.nc"
    ds.to_netcdf(path)
    src = Source(id="tas", path="tas.nc", kind=SourceKind.array, sha256="x", size=1)
    items = ingest_file(src, path, tmp_path)
    var = next(e for e in items if e.locator.column == "tas")
    assert "attribute units: K" in var.content and "cell_methods" in var.content
    time = next(e for e in items if e.locator.column == "time")
    assert "no bounds variable" in time.content
    objs, _ = profile_table_source(src, items, "terrakernel/test")
    assert objs[0].attributes["format"] == "netcdf" and "units: {'tas': 'K'}" in objs[0].basis_note


# ----------------------------------------------------------------------------- stale outputs
def test_remove_stale_outputs_only_touches_generated_files(tmp_path):
    from types import SimpleNamespace

    from terrakernel.compile import remove_stale_outputs
    from terrakernel.project import Project, ProjectConfig

    project = Project.create(tmp_path / "repo", ProjectConfig(name="r", goal="g", materials=str(tmp_path)))
    k = project.repo / "knowledge" / "methods"
    k.mkdir(parents=True)
    (k / "kept.md").write_text("---\ntype: Method\nx-terrakernel: {objects: []}\n---\nbody\n")
    (k / "stale.md").write_text("---\ntype: Method\nx-terrakernel: {objects: []}\n---\nbody\n")
    (k / "handwritten.md").write_text("---\ntype: Note\n---\nwritten by a person\n")
    s = project.repo / ".agents" / "skills"
    for name, meta in (("kept-skill", "terrakernel-task: t"), ("old-skill", "terrakernel-task: t"), ("mine", "x: y")):
        (s / name).mkdir(parents=True)
        (s / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: d\nmetadata:\n  {meta}\n---\n")
    plan = SimpleNamespace(docs=[SimpleNamespace(path="methods/kept.md")], skills=[SimpleNamespace(name="kept-skill")])
    removed = remove_stale_outputs(project, plan)
    assert sorted(removed) == [".agents/skills/old-skill/", "knowledge/methods/stale.md"]
    assert (k / "handwritten.md").exists() and (s / "mine").exists()


def test_saved_runs_are_regraded_when_the_expected_answer_changes(tmp_path):
    from terrakernel.agent.evaluate import regrade_runs
    from terrakernel.project import Project, ProjectConfig, TaskSpec

    def expected(value: float) -> str:
        f = tmp_path / f"expected-{value}.json"
        f.write_text(json.dumps({"values": {"x": {"value": value, "rel_tol": 0.001, "abs_tol": 0.0005}}}))
        return str(f)

    (tmp_path / "materials").mkdir()
    task = TaskSpec(id="t", title="t", prompt="p", expected=expected(1.0))
    project = Project.create(tmp_path / "repo", ProjectConfig(
        name="r", goal="g", materials=str(tmp_path / "materials"), tasks=[task], model="claude-opus-5-5"))
    project.runs_dir.mkdir(parents=True, exist_ok=True)
    answer = {"values": [{"name": "x", "value": 2.0, "unit": ""}], "summary": "", "open_issues": []}
    for tag in ("demo", "other"):
        (project.runs_dir / f"t-full-m-0-{tag}.json").write_text(json.dumps(
            {"run_id": f"t-full-m-0-{tag}", "task": "t", "answer": answer, "grade": {"all_correct": False}}))

    cfg = project.config
    cfg.tasks[0].expected = expected(2.0)  # the materials changed: the reference solution gives a new value
    project.save_config(cfg)
    regraded = regrade_runs(project, tag="demo")
    assert [r["run_id"] for r in regraded] == ["t-full-m-0-demo"]
    assert regraded[0]["grade"]["all_correct"] is True
    assert json.loads((project.runs_dir / "t-full-m-0-demo.json").read_text())["grade"]["all_correct"] is True
    assert json.loads((project.runs_dir / "t-full-m-0-other.json").read_text())["grade"]["all_correct"] is False


def test_model_cost_accumulates_over_builds_and_updates(tmp_path):
    from terrakernel.project import Project, ProjectConfig

    (tmp_path / "materials").mkdir()
    project = Project.create(tmp_path / "repo", ProjectConfig(
        name="r", goal="g", materials=str(tmp_path / "materials"), tasks=[], model="claude-opus-5-5"))
    state = project.load_state()
    state["stages"] = {"plan": {"model_calls": 2, "cost_usd_estimate": 1.5}}
    project.save_state(state)
    assert project.total_model_cost() == {"model_calls": 2, "cost_usd_estimate": 1.5}  # older repositories
    project.add_model_cost(3, 0.25)
    project.add_model_cost(1, 0.5)
    assert project.total_model_cost() == {"model_calls": 4, "cost_usd_estimate": 0.75}
