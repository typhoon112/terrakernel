"""Compilation scopes large gap sets without dropping the full published register."""

import json

from terrakernel.compile.context import gap_context
from terrakernel.compile.knowledge import doc_body_prompt, write_index
from terrakernel.compile.repo import skill_prompt, write_agents_md
from terrakernel.models import Evidence, EvidenceKind, Gap, KnowledgeObject, ObjectType, Source, SourceKind
from terrakernel.plan import validate_plan
from terrakernel.plan.spec import ConventionsPlan, DocPlan, GapPlan, RepositoryPlan, SkillPlan
from terrakernel.project import Project, ProjectConfig, TaskSpec


def test_gap_context_is_bounded_relevant_and_all_gaps_remain_available(tmp_path):
    project = Project.create(tmp_path / "repo", ProjectConfig(
        name="test", goal="Choose a boundary", materials=str(tmp_path / "materials"),
        tasks=[TaskSpec(id="task", title="Boundary choice", prompt="Compare boundary allocation")],
    ))
    try:
        for sid in ("a", "b"):
            project.kb.upsert_source(Source(id=sid, path=f"{sid}.txt", kind=SourceKind.text, sha256="x", size=1))
            project.kb.replace_evidence(sid, [Evidence(id=f"ev:{sid}:p1", source_id=sid,
                kind=EvidenceKind.paragraph, content="Source statement", content_hash="x")])
        obj = KnowledgeObject(id="method:a/main", type=ObjectType.method, name="Boundary allocation",
                              source_ids=["a"])
        project.kb.upsert_objects([obj])
        gaps = [
            Gap(id="gap:exact", subject_id=obj.id, description="Missing factor", severity="blocking"),
            Gap(id="gap:same-source", description="Unknown year convention", severity="warning",
                evidence_ids=["ev:a:p1"]),
            Gap(id="gap:term", description="Boundary allocation condition", severity="warning",
                evidence_ids=["ev:b:p1"]),
            Gap(id="gap:resolved", description="Previously missing value", severity="warning",
                resolved_by="human:author", resolution="Confirmed"),
            *[Gap(id=f"gap:unrelated-{i}", description="Unrelated glacier tracer limitation " * 6,
                  severity="blocking", evidence_ids=["ev:b:p1"]) for i in range(300)],
        ]
        project.kb.upsert_gaps(gaps)
        context = gap_context(project, {obj.id}, "Boundary allocation", budget=1024)
        assert [gap.id for gap in context.gaps] == ["gap:exact", "gap:same-source", "gap:term"]
        assert len(context.text) <= 1024
        assert "Selected 3 of 303" in context.text and "300 omitted" in context.text

        doc = DocPlan(path="methods/boundary.md", title="Boundary choice", okf_type="Method",
                      description="Compare boundary allocation", object_ids=[obj.id], task_ids=["task"])
        skill = SkillPlan(name="choose-boundary", task_id="task", description="Use this skill when choosing boundaries",
                          tools=[], docs=[doc.path], steps=["Read the boundary guide"])
        plan = RepositoryPlan(summary="Boundary research", docs=[doc], skills=[skill], datasets=[], parameters=[],
                              tools=[], capability_gaps=[GapPlan(description="Plant input data still needed", severity="warning")], conventions=ConventionsPlan(
                                  canonical_units=[], canonical_time_convention="instant", evidence_object_ids=[]))
        for prompt in [doc_body_prompt(project, doc, [obj], plan, {}), skill_prompt(project, skill, plan, [])]:
            assert "gap:exact" in prompt and "gap:same-source" in prompt
            assert "glacier tracer" not in prompt and len(prompt) < 12_000
            assert "gaps.md" in prompt
            assert "not rechecked against the full KB" in prompt
            assert "Do not repeat a missing-material claim they answer" in prompt
        results = [{"path": "knowledge/methods/boundary.md", "status": "stable"}]
        write_index(project, plan, results, [])
        write_agents_md(project, plan, [], [], results)
        rows = [json.loads(line) for line in (project.repo / "knowledge/gaps.jsonl").read_text().splitlines()]
        assert {row["id"] for row in rows} == {gap.id for gap in gaps}
        assert next(row for row in rows if row["id"] == "gap:same-source")["evidence"][0]["source"] == "a.txt"
        assert next(row for row in rows if row["id"] == "gap:resolved")["resolution"] == "Confirmed"
        for path in (project.repo / "knowledge/index.md", project.repo / "AGENTS.md"):
            assert "gaps.md" in path.read_text() and "gaps.jsonl" in path.read_text()
        entry = (project.repo / "AGENTS.md").read_text()
        assert "Plant input data still needed" in entry
        assert "Missing factor" not in entry and "glacier tracer" not in entry
        assert "303 open candidate reports" in entry and "counts do not establish actual missing material" in entry
        assert "`list_datasets()` | list configured dataset names" in entry
        assert "`tested` means generic checks passed without" in entry
        assert "unconfirmed reports from limited evidence batches" in (project.repo / "knowledge/gaps.md").read_text()
        assert len(project.kb.gaps()) == 304
        doc.path = "gaps.md"
        issues, _ = validate_plan(plan, project)
        assert any("reserved" in issue and "gaps.md" in issue for issue in issues)
    finally:
        project.close()
