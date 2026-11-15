"""Export a built TerraKernel repository as a static site (`terrakernel site`)."""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

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
    out.parent.mkdir(parents=True, exist_ok=True)
    skip = {".git", "__pycache__", ".pytest_cache", ".venv", "llm-cache", "site"}
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(project.repo.rglob("*")):
            if any(part in skip for part in p.relative_to(project.repo).parts):
                continue
            if p.is_file():
                z.write(p, arcname=f"{project.repo.name}/{p.relative_to(project.repo).as_posix()}")


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

    cases = pages.build_cases(data)
    _write(site_dir / "index.html", pages.index_page(data, cases, site_dir))
    _write(site_dir / "repo.html", pages.repo_page(data))
    _write(site_dir / "results.html", pages.results_page(data))
    _write(site_dir / "limits.html", pages.limits_page(data))
    for case in cases:
        _write(site_dir / "cases" / f"{case['id']}.html", pages.case_page(data, case, site_dir))
    for oid in data.objects:
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
