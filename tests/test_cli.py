"""Offline checks of the user-facing materials entry point."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from terrakernel import cli
from terrakernel.llm.client import Usage
from terrakernel.project import Project, ProjectConfig
from terrakernel.runner import Pipeline

runner = CliRunner()


@pytest.fixture
def materials(tmp_path, monkeypatch):
    # No model client is created: these cases only ingest or substitute a pipeline result.
    monkeypatch.setattr(cli, "_llm", lambda *args: SimpleNamespace(usage=Usage()))
    folder = tmp_path / "research materials"
    folder.mkdir()
    (folder / "notes.md").write_text("# Study\n\nThe station records daily maximum temperature in Celsius.\n")
    (folder / "archive.bin").write_bytes(b"unsupported input")
    return folder


def test_build_materials_without_tasks_and_continue_existing_repo(materials, tmp_path):
    output = tmp_path / "research repository"
    result = runner.invoke(cli.app, ["build", str(materials), "--goal", "Organize the study",
                                     "--output", str(output), "--until", "ingest"])
    assert result.exit_code == 0, result.output
    assert "parsed" in result.output and "skipped" in result.output
    assert "Continue the full build" in result.output
    assert "Repository ready" not in result.output
    config = Project.open(output).config
    assert len(config.tasks) == 1
    assert config.tasks[0].id == "research-goal"
    assert config.tasks[0].prompt == "Organize the study"
    assert config.tasks[0].expected is None
    report = json.loads((output / ".terrakernel" / "ingest-report.json").read_text())
    assert {f["path"]: f["status"] for f in report["files"]} == {
        "notes.md": "parsed", "archive.bin": "skipped",
    }

    resumed = runner.invoke(cli.app, ["build", str(output), "--until", "ingest"])
    assert resumed.exit_code == 0, resumed.output
    assert "unchanged" in resumed.output
    assert "Continue the full build" in resumed.output


@pytest.mark.parametrize("kind, message", [
    ("nonempty", "not an empty directory"),
    ("existing", "Repository already exists"),
    ("inside", "outside the materials directory"),
])
def test_new_build_protects_existing_files(materials, tmp_path, kind, message):
    output = materials / "output" if kind == "inside" else tmp_path / "output"
    output.mkdir()
    (output / "keep.txt").write_text("Keep this original file unchanged.\n")
    if kind == "existing":
        Project.create(output, ProjectConfig(name="original", goal="Original goal", materials=str(materials)))
    before = {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()}

    result = runner.invoke(cli.app, ["build", str(materials), "--goal", "New goal", "--output", str(output)])

    assert result.exit_code == 2, result.output
    assert message in result.output
    assert {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("options, message", [
    (["--goal", "Organize the study", "--until", "missing-stage"], "Unknown stage"),
    ([], "Provide --goal"),
])
def test_invalid_request_does_not_create_output(materials, tmp_path, options, message):
    output = tmp_path / "output"
    result = runner.invoke(cli.app, ["build", str(materials), "--output", str(output), *options])
    assert result.exit_code == 2, result.output
    assert message in result.output
    assert not output.exists()


def test_failed_validation_is_not_presented_as_ready(materials, tmp_path, monkeypatch):
    monkeypatch.setattr(Pipeline, "run", lambda *args, **kwargs: {
        "validate": {"status": "failed", "seconds": 0, "report": {"summary": {"fail": 1}},
                     "error": "One generated tool failed validation"},
    })
    output = tmp_path / "output"
    result = runner.invoke(cli.app, ["build", str(materials), "--goal", "Organize the study",
                                     "--output", str(output)])
    assert result.exit_code == 1, result.output
    assert "Build stopped at validate" in result.output
    assert "terrakernel build" in result.output
    assert "Repository ready" not in result.output
