"""Export a built TerraKernel repository as a static site (`terrakernel site`)."""

from __future__ import annotations

import re
import shutil
import sqlite3
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import yaml

from terrakernel.project import Project

from . import pages
from .model import load_site_data
from .render import PYGMENTS_CSS

SITE_DIR_NAME = "site"
SECRET_RE = re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}|ANTHROPIC_(API_KEY|AUTH_TOKEN)\s*=|llm\.platform\.|"
                       r"/(?:home|Users)/[A-Za-z][A-Za-z0-9_\-]*/|Bearer [A-Za-z0-9_\-]{16,}")


LOCAL_PATH_RE = re.compile(r"/(?:home|Users|root|tmp|var/folders)/[^\s\"'<>&)]*")
VENV_TAIL_RE = re.compile(r".*?/(site-packages/.+)$")


def _redact_path(m: re.Match[str]) -> str:
    """Replace absolute local paths (from tracebacks, tool output) with a neutral form."""
    path = m.group(0)
    tail = VENV_TAIL_RE.match(path)
    if tail:
        return "<python>/" + tail.group(1)
    name = path.rstrip("/").rsplit("/", 1)[-1]
    return f"<local>/{name}" if name else "<local>"


def redact(text: str) -> str:
    return LOCAL_PATH_RE.sub(_redact_path, text)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(redact(text), encoding="utf-8")


def _static(site_dir: Path) -> None:
    src = Path(__file__).resolve().parent / "static"
    fonts = src / "fonts"
    target = site_dir / "static"
    fonts_target = target / "fonts"
    fonts_target.mkdir(parents=True, exist_ok=True)
    for f in fonts.iterdir():
        shutil.copyfile(f, fonts_target / f.name)
    css = (Path(__file__).resolve().parent / "templates" / "site.css").read_text(encoding="utf-8")
    _write(target / "site.css", css + "\n" + PYGMENTS_CSS)


def _zip_repo(project: Project, out: Path) -> None:
    """Export portable inputs and results without builder caches or task answer keys."""
    out.parent.mkdir(parents=True, exist_ok=True)
    config = project.config.model_dump(mode="json")
    expected = {
        (Path(task.expected) if Path(task.expected).is_absolute() else project.repo / task.expected).resolve()
        for task in project.config.tasks if task.expected
    }
    excluded_sources = {
        Path("sources") / path.relative_to(project.materials_dir.resolve())
        for path in expected if path.is_relative_to(project.materials_dir.resolve())
    }
    config["materials"] = "sources"
    for task in config["tasks"]:
        task["expected"] = None
    root_skip = {".git", ".pytest_cache", ".venv", "site"}
    state_skip = {"llm-cache", "ingest-cache", "runs", "updates", "logs", "debug",
                  "events.jsonl", "state.json", "ingest-report.json", "kb.sqlite-wal", "kb.sqlite-shm"}
    written: set[str] = set()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(project.repo.rglob("*")):
            rel = p.relative_to(project.repo)
            if not p.is_file() or p.resolve() == out.resolve() or p.resolve() in expected or rel in excluded_sources:
                continue
            # These are builder paths, not names reserved inside the user's source tree.
            if rel.parts[0] != "sources" and (
                rel.parts[0] in root_skip or "__pycache__" in rel.parts
            ):
                continue
            if rel.parts[0] == ".terrakernel" and len(rel.parts) > 1:
                if rel.parts[1] in state_skip:
                    continue
                if rel.parts[1] != "assets" and p.suffix in {".log", ".jsonl", ".tmp"}:
                    continue
            arcname = f"{project.repo.name}/{rel.as_posix()}"
            if rel.as_posix() == ".terrakernel/project.yaml":
                z.writestr(arcname, yaml.safe_dump(config, sort_keys=False, allow_unicode=True))
            elif rel.as_posix() == ".terrakernel/kb.sqlite":
                # SQLite may still have committed data in its WAL; a standalone copy needs a backup.
                with TemporaryDirectory(prefix=".repo-export-", dir=out.parent) as temporary:
                    snapshot = Path(temporary) / "kb.sqlite"
                    with sqlite3.connect(snapshot) as target:
                        project.kb.conn.backup(target)
                        target.execute("PRAGMA journal_mode=DELETE")
                    z.write(snapshot, arcname=arcname)
            elif rel.as_posix() == ".terrakernel/validation.json":
                z.writestr(arcname, redact(p.read_text(encoding="utf-8")))
            elif rel.as_posix() in {"tasks.yaml", "tasks.yml", ".terrakernel/tasks.yaml", ".terrakernel/tasks.yml"}:
                data = yaml.safe_load(p.read_text(encoding="utf-8"))
                tasks = data.get("tasks", []) if isinstance(data, dict) else data
                if isinstance(tasks, list):
                    for task in tasks:
                        if isinstance(task, dict) and "expected" in task:
                            task["expected"] = None
                z.writestr(arcname, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
            else:
                z.write(p, arcname=arcname)
            written.add(rel.as_posix())
        # Ingest-only previews have not yet mirrored sources during compile.
        for source in project.kb.sources():
            path = project.source_file(source)
            rel = Path("sources") / source.path
            if rel.as_posix() not in written and path.is_file() and path.resolve() not in expected and rel not in excluded_sources:
                z.write(path, arcname=f"{project.repo.name}/{rel.as_posix()}")


def _check_output(site_dir: Path) -> list[str]:
    problems = []
    for f in site_dir.rglob("*"):
        if f.suffix not in (".html", ".css", ".json", ".txt", ".svg"):
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        for m in SECRET_RE.finditer(text):
            problems.append(f"{f.relative_to(site_dir)}: {m.group(0)[:40]}")
    return problems


def export_site(project: Project, out: str | Path | None = None, site_config: str | Path | None = None,
                gallery_href: str | None = None) -> dict[str, Any]:
    data = load_site_data(project, site_config)
    if gallery_href:
        data.site_config["gallery_href"] = gallery_href
    site_dir = Path(out).resolve() if out else project.repo / SITE_DIR_NAME
    if site_dir.exists():
        shutil.rmtree(site_dir)
    site_dir.mkdir(parents=True)
    _static(site_dir)
    for name in ("catalog.jsonl", "gaps.jsonl"):
        catalog = project.repo / "knowledge" / name
        if catalog.is_file():
            # Rendered knowledge pages resolve these downloads at the site root.
            shutil.copyfile(catalog, site_dir / name)

    cases = pages.build_cases(data)
    _write(site_dir / "index.html", pages.index_page(data, cases, site_dir))
    _write(site_dir / "repo.html", pages.repo_page(data))
    _write(site_dir / "results.html", pages.results_page(data))
    _write(site_dir / "limits.html", pages.limits_page(data))
    for case in cases:
        _write(site_dir / "cases" / f"{case['id']}.html", pages.case_page(data, case, site_dir))
    pdf_sources = {source.id for source in data.sources if source.kind == "pdf"}

    def first_pdf_position(oid: str) -> tuple[str, int]:
        for link in data.links.get(oid, []):
            evidence = data.evidence.get(link.evidence_id)
            if evidence and evidence.source_id in pdf_sources and evidence.locator.page:
                return evidence.source_id, evidence.locator.page
        return "", 0

    for oid in sorted(data.objects, key=first_pdf_position):
        _write(site_dir / "objects" / f"{pages._slug(oid)}.html", pages.object_page(data, oid, site_dir))
    for rel, doc in data.kdocs.items():
        _write(site_dir / "docs" / f"{pages._slug(rel)}.html", pages.doc_page(data, doc))
    for a in data.spec.artifacts:
        if a.kind == "source" or (project.repo / a.path).is_dir() or not (project.repo / a.path).exists():
            continue
        _write(site_dir / "files" / f"{pages._slug(a.path)}.html", pages.file_page(data, a.path))
    for run in data.runs:
        _write(site_dir / "runs" / f"{pages._slug(run.id)}.html", pages.run_page(data, run.data))
    _zip_repo(project, site_dir / "download" / "repo.zip")

    problems = _check_output(site_dir)
    n_pages = len(list(site_dir.rglob("*.html")))
    (site_dir / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    return {"site": str(site_dir), "pages": n_pages, "cases": len(cases),
            "size_mb": round(sum(f.stat().st_size for f in site_dir.rglob("*") if f.is_file()) / 1e6, 2),
            "leaks": problems}


def export_gallery(out: str | Path, entries: list[tuple[Project, str | Path | None]]) -> dict[str, Any]:
    """Export several repositories under one entry page: ``<out>/<repository folder name>/`` each."""
    out_dir = Path(out).resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    _static(out_dir)
    results, cards = [], []
    for project, cfg in entries:
        folder = project.repo.name
        results.append(export_site(project, out=out_dir / folder, site_config=cfg, gallery_href="../index.html"))
        cards.append((folder, load_site_data(project, cfg)))
    _write(out_dir / "index.html", pages.gallery_page(cards))
    (out_dir / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    return {"site": str(out_dir), "sites": [Path(r["site"]).name for r in results],
            "pages": sum(r["pages"] for r in results) + 1,
            "size_mb": round(sum(f.stat().st_size for f in out_dir.rglob("*") if f.is_file()) / 1e6, 2),
            "leaks": _check_output(out_dir)}


class SiteServer:
    """Minimal static server bound to a host/port (no directory listing, no writes)."""

    def __init__(self, root: Path, host: str = "0.0.0.0", port: int = 8765):
        import functools
        import socketserver

        root = Path(root).resolve()
        handler = functools.partial(_QuietHandler, directory=str(root))
        self.httpd = socketserver.ThreadingTCPServer((host, port), handler)
        self.httpd.daemon_threads = True
        self.host, self.port = host, self.httpd.server_address[1]

    def serve_forever(self) -> None:
        print(f"serving {self.httpd.RequestHandlerClass.keywords['directory']} on http://{self.host}:{self.port}/")
        self.httpd.serve_forever()


class _QuietHandler:
    def __new__(cls, *args: Any, **kwargs: Any):
        import http.server

        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:  # keep the console quiet
                pass

            def list_directory(self, path: str):  # no listing
                self.send_error(404)
                return None

            def end_headers(self) -> None:
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                super().end_headers()

        return Handler(*args, **kwargs)
