"""Tests for `terrakernel export-web` (the data bundle behind the showcase web app). No model calls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from terrakernel.export_web import export_web
from terrakernel.project import Project, ProjectConfig, TaskSpec
from terrakernel.site import LOCAL_PATH_RE, SECRET_RE

ROOT = Path(__file__).resolve().parents[1]
MATERIALS = ROOT / "examples" / "wind-forecast-eval" / "materials"


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    """Ingest only: the bundle must still describe materials, evidence and an empty build plan."""
    path = tmp_path_factory.mktemp("repo") / "r"
    project = Project.create(path, ProjectConfig(name="demo", goal="A goal", materials=str(MATERIALS),
                                                 tasks=[TaskSpec(id="t", title="T", prompt="P")]))
    from terrakernel.runner import run_ingest

    run_ingest(project)
    yield project
    project.close()


def test_bundle_describes_the_materials_and_evidence(repo, tmp_path):
    out = tmp_path / "bundle"
    summary = export_web(repo, out)
    assert summary["leaks"] == []
    meta = json.loads((out / "meta.json").read_text())
    assert meta["name"] == "demo" and meta["tasks"][0]["id"] == "t"
    sources = json.loads((out / "sources.json").read_text())
    assert sources and all(s["evidence"] >= 0 for s in sources)
    assert meta["counts"]["sources"] == len(sources)
    assert meta["counts"]["evidence"] == sum(s["evidence"] for s in sources)
    catalog = [json.loads(line) for line in (out / "catalog.jsonl").read_text().splitlines()]
    assert len(catalog) == meta["counts"]["objects"]


def test_bundle_is_self_contained_and_leak_free(repo, tmp_path):
    out = tmp_path / "bundle"
    export_web(repo, out)
    names = {p.name for p in out.iterdir()}
    assert {"meta.json", "sources.json", "catalog.jsonl", "artifacts.json", "chains.json",
            "graph.json", "replay.json", "export-summary.json"} <= names
    for f in list(out.glob("*.json")) + list(out.glob("*.jsonl")):
        text = f.read_text()
        assert not SECRET_RE.search(text), f.name
        assert not LOCAL_PATH_RE.search(text), f.name  # nothing published may name a local directory
    assert "out" not in json.loads((out / "export-summary.json").read_text())
    replay = json.loads((out / "replay.json").read_text())
    assert [s["stage"] for s in replay["stages"]] == ["ingest"]  # only ingest ran
    assert all(item["source"] for item in replay["stages"][0]["items"] if "source" in item)


def test_replay_takes_the_last_successful_attempt():
    """A re-run stage must be reported from its last successful attempt, not from a failed one."""
    from terrakernel.export_web import _final_attempts

    events = [
        {"at": "2026-01-01T00:00:00Z", "stage": "extract", "kind": "stage_start", "message": "start"},
        {"at": "2026-01-01T00:01:00Z", "stage": "extract", "kind": "error", "message": "boom"},
        {"at": "2026-01-01T00:01:01Z", "stage": "extract", "kind": "stage_end", "message": "failed",
         "data": {"status": "failed"}},
        {"at": "2026-01-01T00:02:00Z", "stage": "extract", "kind": "stage_start", "message": "start"},
        {"at": "2026-01-01T00:05:00Z", "stage": "extract", "kind": "item", "message": "a.pdf: 3 objects",
         "data": {"source": "a", "objects": 3}},
        {"at": "2026-01-01T00:05:01Z", "stage": "extract", "kind": "stage_end", "message": "done",
         "data": {"status": "done", "model_calls": 2}},
    ]
    final = _final_attempts(events)
    assert final["extract"][0]["at"] == "2026-01-01T00:02:00Z"
    assert final["extract"][-1]["data"]["model_calls"] == 2


def test_replay_keeps_results_of_a_failed_run_that_a_resumed_run_did_not_redo(repo):
    """A resumed extraction only handles unfinished sources: the totals need both runs."""
    from terrakernel.export_web import _replay

    events = [
        {"at": "2026-01-01T00:00:00Z", "stage": "extract", "kind": "stage_start", "message": "start"},
        {"at": "2026-01-01T00:01:00Z", "stage": "extract", "kind": "item", "message": "a: 5 objects",
         "data": {"source": "a", "objects": 5, "gaps": 1}},
        {"at": "2026-01-01T00:02:00Z", "stage": "extract", "kind": "item", "message": "b: 1 objects",
         "data": {"source": "b", "objects": 1, "gaps": 0}},
        {"at": "2026-01-01T00:03:00Z", "stage": "extract", "kind": "error", "message": "boom"},
        {"at": "2026-01-01T00:03:01Z", "stage": "extract", "kind": "stage_end", "message": "failed",
         "data": {"status": "failed"}},
        {"at": "2026-01-01T00:10:00Z", "stage": "extract", "kind": "stage_start", "message": "start"},
        {"at": "2026-01-01T00:11:00Z", "stage": "extract", "kind": "item", "message": "b: 4 objects",
         "data": {"source": "b", "objects": 4, "gaps": 2}},
        {"at": "2026-01-01T00:12:00Z", "stage": "extract", "kind": "item", "message": "c: 7 objects",
         "data": {"source": "c", "objects": 7, "gaps": 0}},
        {"at": "2026-01-01T00:12:30Z", "stage": "extract", "kind": "stage_end", "message": "done",
         "data": {"status": "done", "model_calls": 3}},
    ]
    stage = _replay(repo, events, {"a": {}, "b": {}, "c": {}})["stages"][0]
    assert stage["seconds"] == 150.0 and stage["model_calls"] == 3  # the last successful run
    assert {i["source"]: (i["objects"], i["a"]) for i in stage["items"]} == {"a": (5, 0), "b": (4, 1), "c": (7, 1)}
    assert [(a["status"], a["kept_items"], a["used"], a["error"]) for a in stage["attempts"]] == [
        ("failed", 1, True, "boom"), ("done", 2, True, None)]


def test_reference_cases_keep_non_ascii_quotes():
    """Quotes from the materials are shown verbatim on the site, so they must survive the export."""
    from terrakernel.export_web import parse_reference_cases

    module = '''REFERENCE_CASES = [
    {"id": "c1", "inputs": {"a": 780.0, "b": [2.9]}, "expected": 0.0, "abs_tol": 0.5,
     "source": "ev:source:p26", "quote": "汽车生产行业的碳排放责任之和为300+100-400=0 kgCO2"},
]
'''
    cases = parse_reference_cases(module)
    assert cases == [{"id": "c1", "quote": "汽车生产行业的碳排放责任之和为300+100-400=0 kgCO2",
                      "evidence": "ev:source:p26", "expected": 0.0, "inputs": {"a": 780.0, "b": [2.9]}}]
    assert parse_reference_cases("x = 1") == [] and parse_reference_cases("def (") == []
