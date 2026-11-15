"""Offline checks for user-visible imports and recoverable failures."""

import json
import threading
from types import SimpleNamespace

import pytest

from terrakernel.llm.client import Usage
from terrakernel.project import Project, ProjectConfig
from terrakernel.runner import STAGE_FUNCS, IngestError, Pipeline, run_extract, run_ingest


def make_project(tmp_path):
    materials = tmp_path / "materials"
    materials.mkdir()
    return Project.create(tmp_path / "repo", ProjectConfig(name="research", goal="Organize materials",
                                                          materials=str(materials)))


def test_import_report_and_failed_retry_preserve_update_diff(tmp_path):
    project = make_project(tmp_path)
    source = project.materials_dir / "notes.txt"
    source.write_text("The observation interval is one hour.")
    (project.materials_dir / "slides.unsupported").write_text("Not a supported format")
    first = run_ingest(project)
    assert first["summary"]["parsed"] == 1
    assert first["summary"]["skipped"] == 1
    original_hash = project.kb.sources()[0].sha256
    previous_diff = project.kb.get_meta("last_ingest_diff")

    source.write_text("The observation interval is two hours.")
    broken = project.materials_dir / "empty.txt"
    broken.write_text("")
    with pytest.raises(IngestError, match="empty.txt"):
        run_ingest(project)
    report = json.loads((project.state / "ingest-report.json").read_text())
    assert report["status"] == "failed"
    assert report["summary"]["failed"] == 1
    assert project.kb.sources()[0].sha256 == original_hash
    assert project.kb.get_meta("last_ingest_diff") == previous_diff

    broken.unlink()
    retried = run_ingest(project)
    assert retried["changed"] == first["changed"]
    assert next(f for f in retried["files"] if f["path"] == "notes.txt")["reused_parse"] is True
    assert project.kb.get_meta("last_ingest_diff")[retried["changed"][0]]["changed"]
    assert run_ingest(project)["summary"]["unchanged"] == 1
    project.close()


def test_empty_materials_stop_pipeline_before_model_stages(tmp_path, monkeypatch):
    project = make_project(tmp_path)
    pipeline = Pipeline(project, SimpleNamespace(usage=Usage()))
    def unexpected_extract(*args, **kwargs):
        pytest.fail("Extraction must not start for an empty import")
    monkeypatch.setitem(STAGE_FUNCS, "extract", unexpected_extract)
    results = pipeline.run(until="extract")
    assert list(results) == ["ingest"]
    assert results["ingest"]["status"] == "failed"
    assert results["ingest"]["report"]["summary"]["recognized"] == 0
    assert (project.state / "ingest-report.json").exists()


def test_validation_failures_are_failed_pipeline_stages(tmp_path, monkeypatch):
    project = make_project(tmp_path)
    pipeline = Pipeline(project, SimpleNamespace(usage=Usage()))
    monkeypatch.setitem(STAGE_FUNCS, "validate", lambda *args, **kwargs: {"pass": 2, "fail": 1})
    result = pipeline.run(only=["validate"])
    assert result["validate"]["status"] == "failed"
    assert result["validate"]["report"]["fail"] == 1
    assert project.load_state()["stages"]["validate"]["status"] == "failed"


def test_parallel_extraction_keeps_successful_empty_sources_on_retry(tmp_path, monkeypatch):
    project = make_project(tmp_path)
    for name in ("a", "b", "c"):
        (project.materials_dir / f"{name}.txt").write_text("A document cover with no knowledge objects.")
    run_ingest(project)
    calls = []
    start_together = threading.Barrier(2)
    failing = True

    def extract(project, llm, source, **kwargs):
        calls.append(source.path)
        if failing and source.path in ("a.txt", "b.txt"):
            start_together.wait(timeout=5)
        if failing and source.path == "a.txt":
            raise ValueError("temporary model failure")
        project.kb.set_meta(f"processed:{source.id}", True)
        return {"source": source.id, "objects": 0, "gaps": 0, "problems": []}

    monkeypatch.setattr("terrakernel.extract.extract_source", extract)
    llm = SimpleNamespace(settings=SimpleNamespace(max_concurrency=2))
    with pytest.raises(RuntimeError, match="Completed sources were saved"):
        run_extract(project, llm)
    ids = {s.path: s.id for s in project.kb.sources()}
    fingerprints = project.load_state()["extract_fingerprints"]
    assert ids["a.txt"] not in fingerprints
    assert ids["b.txt"] in fingerprints
    failing = False
    run_extract(project, llm)
    assert calls.count("a.txt") == 2
    assert calls.count("b.txt") == 1
    assert calls.count("c.txt") == 1
    assert run_extract(project, llm)["extracted_sources"] == []
    project.close()
