"""Uncertain extracted knowledge remains inspectable without becoming an accepted dependency."""

import json
from types import SimpleNamespace

from terrakernel.lineage import build_lineage
from terrakernel.models import Evidence, EvidenceLink, Gap, KnowledgeObject, Source
from terrakernel.plan import build_spec, kb_digest, validate_plan
from terrakernel.plan.spec import ConventionsPlan, DocPlan, RepositoryPlan
from terrakernel.project import Project, ProjectConfig
from terrakernel.reconcile import GapResolution, ReconcileResult, run_reconcile
from terrakernel.validate import Report, check_lineage


def make_project(tmp_path):
    project = Project.create(tmp_path / "repo", ProjectConfig(name="review", goal="Use grounded methods",
                                                            materials=str(tmp_path)))
    project.kb.upsert_source(Source(id="source", path="paper.txt", kind="text", sha256="abc", size=1))
    project.kb.replace_evidence("source", [Evidence(id="ev:known", source_id="source", kind="paragraph",
                                                   content="A grounded method", content_hash="abc")])
    project.kb.upsert_objects([
        KnowledgeObject(id="method:active", type="method", name="Accepted method", source_ids=["source"]),
        KnowledgeObject(id="method:review", type="method", name="Untrusted candidate", status="needs_review",
                        source_ids=["source"]),
    ])
    project.kb.add_links([EvidenceLink(object_id="method:active", evidence_id="ev:known", quote="A grounded method")])
    return project


def make_plan():
    return RepositoryPlan(summary="Use the accepted method", docs=[DocPlan(path="method.md", okf_type="Concept",
                          title="Method", description="Accepted method", object_ids=["method:active"])],
                          conventions=ConventionsPlan(canonical_units=[], canonical_time_convention="instant",
                                                      evidence_object_ids=[]),
                          datasets=[], parameters=[], tools=[], skills=[], capability_gaps=[])


def test_review_objects_excluded_from_planning_but_preserved_in_coverage(tmp_path):
    project = make_project(tmp_path)
    digest = kb_digest(project)
    assert "Accepted method" in digest and "Untrusted candidate" not in digest
    coverage = json.loads((project.state / "planning-coverage.json").read_text())
    assert coverage["total_count"] == 2 and coverage["selected_count"] == 1
    assert coverage["excluded_by_status"] == {"method:review": "needs_review"}
    plan = make_plan()
    plan.docs[0].object_ids.append("method:review")
    issues, _ = validate_plan(plan, project)
    assert any("needs_review; only active" in issue for issue in issues)
    assert len(project.kb.objects()) == 2


def test_review_missing_evidence_warns_but_use_or_active_missing_evidence_fails(tmp_path):
    project = make_project(tmp_path)
    plan = make_plan()
    spec = build_spec(plan, project, [], "test")
    lineage = build_lineage(project, spec)
    assert lineage["objects"]["method:review"]["status"] == "needs_review"
    report = Report()
    check_lineage(report, project)
    assert report.summary().get("fail", 0) == 0
    assert any(c["check"] == "review_objects_ungrounded" and c["status"] == "warn" for c in report.checks)

    spec.artifacts[0].objects.append("method:review")
    build_lineage(project, spec)
    report = Report()
    check_lineage(report, project)
    assert any(c["check"] == "artifact_objects_active" and c["status"] == "fail" for c in report.checks)

    project.kb.upsert_objects([KnowledgeObject(id="method:unbacked", type="method", name="Unbacked active")])
    build_lineage(project, spec)
    report = Report()
    check_lineage(report, project)
    assert any(c["check"] == "objects_grounded" and c["status"] == "fail" for c in report.checks)


def test_reconcile_cannot_resolve_gap_with_review_object_even_mixed_with_active(tmp_path):
    project = make_project(tmp_path)
    project.kb.upsert_gaps([Gap(id="gap:missing", subject_id="method:active", description="Missing parameter")])

    class Proposer:
        settings = SimpleNamespace(max_concurrency=1)

        def structured(self, prompt, schema, **kwargs):
            assert "Untrusted candidate" not in prompt
            return ReconcileResult(gap_resolutions=[GapResolution(
                gap_id="gap:missing", resolved_by=["method:active", "method:review"], explanation="Both agree")])

    result = run_reconcile(project, Proposer())
    assert result["gaps_resolved"] == 0
    assert project.kb.gaps()[0].resolved_by is None
    assert project.kb.object("method:review").status.value == "needs_review"
