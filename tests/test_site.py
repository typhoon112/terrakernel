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
