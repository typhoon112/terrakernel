"""The downloadable research repository works independently of its build machine."""

import json
import shutil
from pathlib import Path
from zipfile import ZipFile

import yaml

from terrakernel.models import Source, SourceKind
from terrakernel.project import Project, ProjectConfig, TaskSpec
from terrakernel.site import _zip_repo


def test_download_is_portable_without_builder_state_or_answer_keys(tmp_path: Path):
    materials = tmp_path / "private-materials"
    originals = {
        "notes.txt": b"Scientific source, unchanged.",
        "site/appendix.txt": b"A legitimate source directory named site.",
        "logs/observations.csv": b"value\n42\n",
        "llm-cache/reference.txt": b"A legitimate source directory named llm-cache.",
    }
    for name, content in originals.items():
        path = materials / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    answer = materials / "reference-answer.json"
    answer.write_text('{"private_reference_answer": 123}')
    project = Project.create(tmp_path / "original" / "research", ProjectConfig(
        name="portable", goal="Research", materials=str(materials),
        tasks=[TaskSpec(id="task", title="A task", prompt="Read the supplied sources", expected=str(answer))],
    ))
    shutil.copytree(materials, project.repo / "sources")
    before = project.config_path.read_bytes()
    (project.repo / "tasks.yaml").write_text(yaml.safe_dump({"tasks": [project.config.tasks[0].model_dump()]}))
    (project.repo / "AGENTS.md").write_text("Read sources/ and knowledge/.")
    for index, name in enumerate(originals):
        project.kb.upsert_source(Source(id=f"s{index}", path=name, kind=SourceKind.text, sha256="abc", size=1))
    project.kb.set_meta("committed_before_export", {"value": 42})
    excluded = [
        ".terrakernel/events.jsonl", ".terrakernel/state.json", ".terrakernel/ingest-report.json",
        ".terrakernel/ingest-cache/intermediate.json", ".terrakernel/llm-cache/response.json",
        ".terrakernel/runs/task.json", ".terrakernel/updates/change.json",
        ".terrakernel/debug.log", ".venv/environment.txt", "site/previous.html",
    ]
    for name in excluded:
        path = project.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"local build detail: {tmp_path}")
    for name, content in {
        ".terrakernel/spec.yaml": "plan: {}\n",
        ".terrakernel/lineage.json": "{}",
        ".terrakernel/human_answers.md": "Confirmed source units: kg.",
        ".terrakernel/assets/figure.svg": "<svg/>",
        ".terrakernel/validation.json": json.dumps({"detail": f"Traceback: {tmp_path}/private/test.py"}),
    }.items():
        path = project.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    archive = tmp_path / "download" / "repo.zip"
    try:
        _zip_repo(project, archive)
        assert project.config_path.read_bytes() == before
        assert project.materials_dir == materials
        with ZipFile(archive) as bundle:
            members = set(bundle.namelist())
            prefix = project.repo.name + "/"
            assert all(prefix + name not in members for name in excluded)
            assert prefix + "sources/reference-answer.json" not in members
            assert prefix + ".terrakernel/kb.sqlite-wal" not in members
            assert prefix + ".terrakernel/kb.sqlite-shm" not in members
            for name, original in originals.items():
                assert bundle.read(prefix + "sources/" + name) == original
            exported_config = yaml.safe_load(bundle.read(prefix + ".terrakernel/project.yaml"))
            assert exported_config["materials"] == "sources"
            assert exported_config["tasks"][0]["expected"] is None
            assert exported_config["tasks"][0]["prompt"] == "Read the supplied sources"
            assert yaml.safe_load(bundle.read(prefix + "tasks.yaml"))["tasks"][0]["expected"] is None
            for name in members:
                if not name.endswith(".sqlite"):
                    assert str(tmp_path).encode() not in bundle.read(name)
            bundle.extractall(tmp_path / "recipient")
        relocated = Project.open(tmp_path / "recipient" / project.repo.name)
        try:
            assert relocated.materials_dir == relocated.repo / "sources"
            assert relocated.config.tasks[0].expected is None
            assert relocated.kb.get_meta("committed_before_export") == {"value": 42}
            assert len(relocated.kb.sources()) == len(originals)
            for source in relocated.kb.sources():
                assert relocated.source_file(source).read_bytes() == originals[source.path]
            assert relocated.validation_path.exists() and relocated.spec_path.exists()
            assert relocated.answers_path.read_text() == "Confirmed source units: kg."
        finally:
            relocated.close()
    finally:
        project.close()
