"""Tests for the showcase site exporter (no model calls)."""

from __future__ import annotations

from pathlib import Path

import pytest

from terrakernel.project import Project, ProjectConfig, TaskSpec
from terrakernel.site import SECRET_RE, export_site, redact
from terrakernel.site.render import md_to_html

ROOT = Path(__file__).resolve().parents[1]
MATERIALS = ROOT / "examples" / "wind-forecast-eval" / "materials"


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    """A repository built offline: ingest only, so the site must cope with no model output."""
    path = tmp_path_factory.mktemp("repo") / "r"
    project = Project.create(path, ProjectConfig(name="demo", goal="A goal", materials=str(MATERIALS),
                                                 tasks=[TaskSpec(id="t", title="T", prompt="P")]))
    from terrakernel.runner import run_ingest

    run_ingest(project)
    yield project
    project.close()


def test_redaction_hides_local_paths():
    text = "File \"/home/alice/hackathon/.venv/lib/python3.12/site-packages/pandas/core/x.py\", line 3\n" \
           "/tmp/tk_repo/sources/a.csv and /Users/bob/x"
    out = redact(text)
    assert not SECRET_RE.search(out)
    assert "<python>/site-packages/pandas/core/x.py" in out and "<local>/a.csv" in out


def test_citations_become_links():
    html = md_to_html("Power is in kW.[^dataset:s1/f] Another.[^unknown:x]",
                      object_href=lambda oid: "../objects/dataset-s1-f.html" if oid != "unknown:x" else None)
    assert 'class="cite"' in html and "../objects/dataset-s1-f.html" in html
    assert "cite-missing" in html
    assert "[^" not in html  # definitions and markers are gone


def test_code_fences_are_highlighted_and_tables_wrapped():
    html = md_to_html("```python\ndef f(x):\n    return x\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |")
    assert 'class="codehilite"' in html and '<span class="k">def</span>' in html
    assert '<div class="table-wrap"><table>' in html


def test_export_produces_a_self_contained_site(repo, tmp_path):
    out = tmp_path / "site"
    result = export_site(repo, out=out)
    assert result["leaks"] == [] and result["pages"] >= 4  # index, repo, results, limits
    assert (out / "index.html").exists() and (out / "static" / "site.css").exists()
    assert (out / "static" / "fonts" / "plex-sans-var.woff2").exists()
    assert (out / "download" / "repo.zip").exists()
    html = (out / "index.html").read_text()
    assert "TerraKernel" in html and 'data-zh=' in html  # bilingual strings inline
    # nothing is loaded from another host (links inside quoted source text are fine)
    import re

    for page in list(out.rglob("*.html")) + [out / "static" / "site.css"]:
        text = page.read_text()
        loaded = re.findall(r'(?:src|href)="(https?://[^"]+)"|url\((https?://[^)]+)\)', text)
        assert not [u for pair in loaded for u in pair if u and "<link" in text and u in text and
                    re.search(r'<(?:link|script|img)[^>]*' + re.escape(u), text)], page


def test_gallery_links_each_site_and_each_site_links_back(repo, tmp_path):
    from terrakernel.site import export_gallery

    cfg = tmp_path / "site.yaml"
    cfg.write_text("title: Example\ntitle_zh: 示例\n", encoding="utf-8")
    out = tmp_path / "gallery"
    result = export_gallery(out, [(repo, cfg)])
    folder = repo.repo.name
    assert result["leaks"] == [] and result["sites"] == [folder]
    entry = (out / "index.html").read_text()
    assert f'href="{folder}/index.html"' in entry and 'data-zh="示例"' in entry
    assert (out / "static" / "site.css").exists()
    assert 'href="../index.html"' in (out / folder / "index.html").read_text()
    assert 'href="../../index.html"' in next((out / folder / "objects").glob("*.html")).read_text() \
        if (out / folder / "objects").exists() and list((out / folder / "objects").glob("*.html")) else True


def test_object_navigation_and_catalog_remain_valid_for_long_source_ids(tmp_path):
    import re
    from urllib.parse import urljoin

    import yaml

    from terrakernel.compile.knowledge import write_catalog
    from terrakernel.models import KnowledgeObject
    from terrakernel.plan import save_spec
    from terrakernel.plan.spec import Artifact, ConventionsPlan, RepositoryPlan, RepositorySpec
    from terrakernel.site.pages import _slug

    project = Project.create(tmp_path / "research", ProjectConfig(
        name="real-materials", goal="Compare documented methods", materials=str(tmp_path / "materials")))
    prefix = "method:" + "a_long_source_identifier_" * 5
    objects = [KnowledgeObject(id=f"{prefix}/{name}", type="method", name=name)
               for name in ("Production responsibility", "Consumption responsibility")]
    try:
        project.kb.upsert_objects(objects)
        write_catalog(project)
        guide_path = "knowledge/methods.md"
        frontmatter = {"title": "Methods", "type": "Guide", "sources": [{"id": "ref", "object": objects[0].id}],
                       "x-terrakernel": {"objects": [objects[0].id]}}
        (project.repo / guide_path).write_text("---\n" + yaml.safe_dump(frontmatter) + "---\nA documented method.[^ref]\n")
        plan = RepositoryPlan(summary="", docs=[], datasets=[], parameters=[], tools=[], skills=[], capability_gaps=[],
                              conventions=ConventionsPlan(canonical_units=[], canonical_time_convention="instant",
                                                          evidence_object_ids=[]))
        save_spec(project, RepositorySpec(generated_at="", generated_by="test", summary="", plan=plan,
                                          artifacts=[Artifact(id="doc:methods", kind="knowledge_doc", path=guide_path,
                                                              objects=[objects[0].id])]))
        out = tmp_path / "site"
        export_site(project, out=out)
        assert len(list((out / "objects").glob("*.html"))) == 2
        for obj in objects:
            assert obj.name in (out / "objects" / f"{_slug(obj.id)}.html").read_text()
        page = out / "docs" / f"{_slug('knowledge/catalog.md')}.html"
        assert 'href="../catalog.jsonl"' in page.read_text()
        assert (out / "catalog.jsonl").read_bytes() == (project.repo / "knowledge" / "catalog.jsonl").read_bytes()
        assert "synthetically generated" not in (out / "limits.html").read_text()
        object_page = out / "objects" / f"{_slug(objects[0].id)}.html"
        guide_page = out / "docs" / f"{_slug(guide_path)}.html"
        doc_href = f"../docs/{guide_page.name}"
        assert f'href="{doc_href}"' in object_page.read_text()
        assert (object_page.parent / doc_href).resolve() == guide_page
        citation = re.search(r'<sup class="cite"><a href="([^"]+)"', guide_page.read_text())[1]
        assert (guide_page.parent / citation).resolve() == object_page
        assert urljoin(f"https://demo.invalid/gallery/research/docs/{guide_page.name}", citation) == (
            f"https://demo.invalid/gallery/research/objects/{object_page.name}")
    finally:
        project.close()


def test_homepage_exposes_tasks_and_keeps_all_cases_with_initial_limit(tmp_path):
    from html.parser import HTMLParser

    from terrakernel.plan import save_spec
    from terrakernel.plan.spec import Artifact, ConventionsPlan, RepositoryPlan, RepositorySpec, SkillPlan
    from terrakernel.site.model import load_site_data
    from terrakernel.site.pages import _slug, file_page, index_page, repo_page

    tasks = [TaskSpec(id=f"task-{i}", title=f"Research task {i}", prompt="Follow the documented workflow.")
             for i in range(4)]
    project = Project.create(tmp_path / "research", ProjectConfig(
        name="research", goal="Explore materials", materials=str(tmp_path / "materials"), tasks=tasks))
    skills = [SkillPlan(name=t.id, task_id=t.id, description="Use this skill when researching", tools=[], docs=[], steps=[])
              for t in tasks]
    artifacts = [Artifact(id=f"skill:{s.name}", kind="skill", path=f".agents/skills/{s.name}/SKILL.md") for s in skills]
    for artifact in artifacts:
        path = project.repo / artifact.path
        path.parent.mkdir(parents=True)
        path.write_text("# Workflow\n[Read the method](../../../knowledge/method.md).")
    method = project.repo / "knowledge" / "method.md"
    method.parent.mkdir()
    method.write_text("---\ntitle: Method\ntype: Method\n---\nA documented method.")
    artifacts.append(Artifact(id="doc:method", kind="knowledge_doc", path="knowledge/method.md"))
    plan = RepositoryPlan(summary="", docs=[], datasets=[], parameters=[], tools=[], skills=skills, capability_gaps=[],
                          conventions=ConventionsPlan(canonical_units=[], canonical_time_convention="instant",
                                                      evidence_object_ids=[]))
    save_spec(project, RepositorySpec(generated_at="", generated_by="test", summary="", plan=plan, artifacts=artifacts))
    cases = [{"id": f"case-{i}", "kinds": ["gap"], "title": f"Question {i}", "lede": "A question to review."}
             for i in range(50)]

    class Cards(HTMLParser):
        def __init__(self):
            super().__init__()
            self.cards = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "a" and "data-kinds" in attrs:
                self.cards.append(attrs)

    try:
        data = load_site_data(project)
        html = index_page(data, cases, tmp_path)
        parser = Cards()
        parser.feed(html)
        assert len(parser.cards) == 50
        assert sum("hidden" not in card for card in parser.cards) == 24
        assert {card["href"] for card in parser.cards} == {f"cases/case-{i}.html" for i in range(50)}
        assert html.index('id="tasks"') < html.index('id="cases"')
        for artifact in artifacts[:4]:
            assert f'href="files/{_slug(artifact.path)}.html"' in html
            skill_html = file_page(data, artifact.path)
            assert f'href="../docs/{_slug("knowledge/method.md")}.html"' in skill_html
            assert "../../../knowledge" not in skill_html
        assert 'id="case-search"' in html and 'id="case-more"' in html
        assert f'href="files/{_slug("AGENTS.md")}.html"' in repo_page(data)
    finally:
        project.close()


def test_resolved_questions_preserve_human_and_model_attribution(tmp_path):
    from terrakernel.models import Evidence, EvidenceLink, Gap, KnowledgeObject, Source
    from terrakernel.site.model import load_site_data
    from terrakernel.site.pages import build_cases, limits_page

    project = Project.create(tmp_path / "research", ProjectConfig(name="research", goal="Read sources", materials="sources"))
    try:
        project.kb.upsert_source(Source(id="paper", path="paper.txt", kind="text", sha256="x", size=5))
        project.kb.replace_evidence("paper", [Evidence(id="ev:paper:1", source_id="paper", kind="paragraph",
                                                       content="unit: kg", content_hash="x")])
        project.kb.upsert_objects([KnowledgeObject(id="concept:unit", name="Unit", type="concept", source_ids=["paper"])])
        project.kb.add_links([EvidenceLink(object_id="concept:unit", evidence_id="ev:paper:1", quote="unit: kg")])
        project.kb.upsert_gaps([
            Gap(id="gap:human", description="Manual answer", resolved_by="human:alice", resolution="Confirmed by Alice"),
            Gap(id="gap:model", description="Source answer", resolved_by="reconcile:concept:unit", resolution="kg"),
            Gap(id="gap:open", description="Still open"),
        ])
        data = load_site_data(project)
        counts = data.counts()
        assert counts["answered_gaps"] == 1 and counts["model_resolved_gaps"] == 1 and counts["resolved_gaps"] == 2
        cases = build_cases(data)
        model = next(c for c in cases if "model" in c["kinds"])
        human = next(c for c in cases if "human" in c["kinds"])
        assert model["source_ids"] == ["paper"] and model["objects"] == ["concept:unit"]
        assert "human_answers" not in model["source_ids"] and "Answered by a person" not in model["lede"]
        assert "Answered by a person" in human["lede"]
        html = limits_page(data)
        assert "1 answered by people and 1 resolved by model reconciliation" in html
        assert "human:alice" in html and "reconcile:concept:unit" in html
    finally:
        project.close()
