"""Ingest: turn input files into locatable evidence units (deterministic, no model calls)."""

from __future__ import annotations

import mimetypes
from collections.abc import Callable
from pathlib import Path

from terrakernel.models import Evidence, Source, SourceKind
from terrakernel.util import sha256_file, source_slug

EXT_KIND: dict[str, SourceKind] = {
    ".pdf": SourceKind.pdf,
    ".md": SourceKind.markdown,
    ".markdown": SourceKind.markdown,
    ".txt": SourceKind.text,
    ".rst": SourceKind.text,
    ".json": SourceKind.text,
    ".yaml": SourceKind.text,
    ".yml": SourceKind.text,
    ".csv": SourceKind.table,
    ".tsv": SourceKind.table,
    ".xlsx": SourceKind.table,
    ".xlsm": SourceKind.table,
    ".parquet": SourceKind.table,
    ".nc": SourceKind.array,
    ".nc4": SourceKind.array,
    ".netcdf": SourceKind.array,
    ".py": SourceKind.code,
    ".ipynb": SourceKind.code,
    ".r": SourceKind.code,
    ".jl": SourceKind.code,
    ".m": SourceKind.code,
    ".js": SourceKind.code,
    ".ts": SourceKind.code,
    ".sql": SourceKind.code,
    ".sh": SourceKind.code,
    ".png": SourceKind.image,
    ".jpg": SourceKind.image,
    ".jpeg": SourceKind.image,
    ".gif": SourceKind.image,
    ".webp": SourceKind.image,
}

IGNORED_NAMES = {".DS_Store", "Thumbs.db"}


def scan_materials(materials_dir: Path) -> tuple[list[Source], list[str]]:
    """List supported files under ``materials_dir`` as Sources; also return skipped paths."""
    root = Path(materials_dir).resolve()
    sources: list[Source] = []
    skipped: list[str] = []
    used_ids: set[str] = set()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if path.name in IGNORED_NAMES or any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        kind = EXT_KIND.get(path.suffix.lower())
        if kind is None:
            skipped.append(rel)
            continue
        sid = source_slug(rel)
        base, n = sid, 2
        while sid in used_ids:
            sid = f"{base}_{n}"
            n += 1
        used_ids.add(sid)
        sources.append(
            Source(
                id=sid,
                path=rel,
                kind=kind,
                sha256=sha256_file(path),
                size=path.stat().st_size,
                media_type=mimetypes.guess_type(path.name)[0],
                title=path.stem.replace("_", " "),
            )
        )
    return sources, skipped


def ingest_file(source: Source, path: Path, assets_dir: Path) -> list[Evidence]:
    """Parse one file into evidence units."""
    from terrakernel.ingest import code, image, markdown, netcdf, pdf, table, text

    handlers: dict[SourceKind, Callable[..., list[Evidence]]] = {
        SourceKind.pdf: pdf.ingest_pdf,
        SourceKind.markdown: markdown.ingest_markdown,
        SourceKind.text: text.ingest_text,
        SourceKind.table: table.ingest_table,
        SourceKind.array: netcdf.ingest_netcdf,
        SourceKind.code: code.ingest_code,
        SourceKind.image: image.ingest_image,
    }
    handler = handlers.get(source.kind)
    if handler is None:
        return []
    items = handler(source, path, assets_dir)
    for i, ev in enumerate(items):
        ev.order = i
    return items
