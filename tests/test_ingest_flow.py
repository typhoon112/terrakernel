"""Offline checks for user-visible imports and recoverable failures."""

import json
from types import SimpleNamespace

import pytest

from terrakernel.llm.client import Usage
from terrakernel.project import Project, ProjectConfig
from terrakernel.runner import STAGE_FUNCS, IngestError, Pipeline, run_ingest


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
