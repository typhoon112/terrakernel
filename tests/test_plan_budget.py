"""Large research collections must not overflow the planner or disappear from the KB."""

import json

from terrakernel.models import Gap, KnowledgeObject, Relation
from terrakernel.plan import kb_digest
from terrakernel.project import Project, ProjectConfig, TaskSpec


def test_large_catalog_is_bounded_and_keeps_task_methods_and_conflicts(tmp_path):
    project = Project.create(tmp_path / "repo", ProjectConfig(
        name="large-collection", materials=str(tmp_path), goal="Compare energy accounting methods",
        tasks=[TaskSpec(id="power", title="电力责任", prompt="计算电力碳排放责任"),
               TaskSpec(id="water", title="Water allocation", prompt="Calculate freshwater allocation")],
    ))
    objects = [KnowledgeObject(id=f"method:other-{i}", type="method", name=f"Forestry procedure {i}",
                               summary="Tree growth measurements. " * 25, source_ids=[f"source-{i % 5}"],
                               attributes={"formula": "increment = current_volume - previous_volume"})
               for i in range(100)]
    objects += [
        KnowledgeObject(id="method:power", type="method", name="电力碳排放责任", source_ids=["power"]),
        KnowledgeObject(id="method:water", type="method", name="Freshwater allocation", source_ids=["water"]),
        KnowledgeObject(id="constraint:boundary", type="constraint", name="Boundary exception", source_ids=["power"]),
    ]
    project.kb.upsert_objects(objects)
    project.kb.upsert_relations([Relation(id="rel:boundary", type="conflicts_with", src="method:power",
                                         dst="constraint:boundary", note="Different treatment of output credits")])
    project.kb.upsert_gaps([Gap(id=f"gap:{i}", description="Missing documented accounting parameter. " * 50,
                               severity="blocking", subject_id="method:power") for i in range(60)])

    digest = kb_digest(project, budget=12_000)
    coverage = json.loads((project.state / "planning-coverage.json").read_text())
    assert len(digest) <= 12_000
    assert {"method:power", "method:water", "constraint:boundary"} <= set(coverage["selected_object_ids"])
    assert coverage["mode"] == "task_working_set"
    assert coverage["selected_count"] < len(objects)
    assert set(coverage["selected_object_ids"]) | set(coverage["omitted_object_ids"]) == {o.id for o in objects}
    assert coverage["omitted_gap_ids"]
    assert "not exhaustive" in digest and "catalog.jsonl" in digest
    assert len(project.kb.objects()) == len(objects)
    assert len(project.kb.gaps()) == 60
    assert kb_digest(project, budget=12_000) == digest


def test_oversized_single_object_does_not_overflow_minimum_budget(tmp_path):
    project = Project.create(tmp_path / "repo", ProjectConfig(name="wide-table", materials=str(tmp_path), goal="data"))
    project.kb.upsert_objects([KnowledgeObject(
        id="dataset:wide", type="dataset", name="Wide data file", basis="measured",
        attributes={"fields": [{"column": f"measurement_{i}"} for i in range(5000)]},
    )])
    digest = kb_digest(project, budget=2048)
    assert len(digest) <= 2048
    coverage = json.loads((project.state / "planning-coverage.json").read_text())
    assert coverage["omitted_object_ids"] == ["dataset:wide"]
    assert project.kb.object("dataset:wide") is not None
