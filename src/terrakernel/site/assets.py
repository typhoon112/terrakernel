"""Source viewers: show where a piece of evidence is, not just its text.

- PDF: the page is rendered once (pypdfium2) and cropped around the evidence's bounding box,
  with the region outlined, so a reader sees the formula or table in its context.
- Markdown / text / code: the lines are shown with the cited range highlighted.
- Tables: the column profile as a small table plus the first rows of the file.
"""

from __future__ import annotations

import atexit
import hashlib
from collections import OrderedDict
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import pypdfium2 as pdfium
from PIL import Image, ImageDraw

RENDER_SCALE = 2.0
CROP_MARGIN = 28
MAX_CROP_WIDTH = 900
MAX_CACHED_PDF_PAGES = 8
_PDF_PAGE_CACHE: OrderedDict[tuple[str, int, int, float], Image.Image] = OrderedDict()


@atexit.register
def _clear_pdf_page_cache() -> None:
    while _PDF_PAGE_CACHE:
        _, image = _PDF_PAGE_CACHE.popitem(last=False)
        image.close()


def _pdf_page_image(source_path: Path, page: int, modified: int) -> Image.Image | None:
    key = (str(source_path.resolve()), modified, page, RENDER_SCALE)
    if key in _PDF_PAGE_CACHE:
        _PDF_PAGE_CACHE.move_to_end(key)
        return _PDF_PAGE_CACHE[key]
    doc = pdfium.PdfDocument(str(source_path))
    try:
        if page < 1 or page > len(doc):
            return None
        pdf_page = doc[page - 1]
        try:
            bitmap = pdf_page.render(scale=RENDER_SCALE)
            try:
                rendered = bitmap.to_pil()
                try:
                    image = rendered.convert("RGB")  # independent pixels, safe after bitmap.close()
                finally:
                    rendered.close()
            finally:
                bitmap.close()
        finally:
            pdf_page.close()
    finally:
        doc.close()
    _PDF_PAGE_CACHE[key] = image
    while len(_PDF_PAGE_CACHE) > MAX_CACHED_PDF_PAGES:
        _, evicted = _PDF_PAGE_CACHE.popitem(last=False)
        evicted.close()
    return image


def _cache_path(assets_dir: Path, key: str) -> Path:
    return assets_dir / "pdf" / f"{hashlib.sha256(key.encode()).hexdigest()[:16]}.png"


def pdf_region(project_repo: Path, source_path: Path, page: int, bbox: list[float] | None, assets_dir: Path) -> str | None:
    """Crop a PDF page around ``bbox`` and return the site-relative asset path."""
    if not page:
        return None
    modified = source_path.stat().st_mtime_ns
    key = f"{source_path}:{modified}:{page}:{bbox}"
    out = _cache_path(assets_dir, key)
    site_rel = (out.relative_to(assets_dir) if out.is_relative_to(assets_dir) else out).as_posix()
    if out.exists():
        return site_rel
    page_image = _pdf_page_image(source_path, page, modified)
    if page_image is None:
        return None
    img = page_image.copy()  # highlighting one evidence region must not contaminate the cached page.
    crop = None
    try:
        draw = ImageDraw.Draw(img)
        if bbox:
            x0, top, x1, bottom = [v * RENDER_SCALE for v in bbox]
            left = max(0, x0 - CROP_MARGIN)
            right = min(img.width, x1 + CROP_MARGIN)
            up = max(0, top - CROP_MARGIN)
            down = min(img.height, bottom + CROP_MARGIN)
            draw.rectangle([x0 - 2, top - 2, x1 + 2, bottom + 2], outline=(200, 135, 59), width=3)
            crop = img.crop((int(left), int(up), int(right), int(down)))
        else:
            crop = img
        if crop.width > MAX_CROP_WIDTH:
            ratio = MAX_CROP_WIDTH / crop.width
            resized = crop.resize((MAX_CROP_WIDTH, int(crop.height * ratio)))
            if crop is not img:
                crop.close()
            crop = resized
        out.parent.mkdir(parents=True, exist_ok=True)
        crop.save(out)
    finally:
        if crop is not None and crop is not img:
            crop.close()
        img.close()
    return site_rel


def text_lines(path: Path, start: int | None, end: int | None, context: int = 3, max_lines: int = 40) -> str:
    """HTML block with numbered lines and the cited range highlighted."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    if not start:
        start, end = 1, min(len(lines), max_lines)
    end = end or start
    lo = max(1, start - context)
    hi = min(len(lines), end + context, lo + max_lines - 1)
    rows = []
    for n in range(lo, hi + 1):
        text = escape(lines[n - 1].rstrip())
        cls = "hl" if start <= n <= end else ""
        rows.append(f'<div class="ln {cls}"><span class="no">{n}</span><span class="tx">{text or "&nbsp;"}</span></div>')
    return f'<div class="lines">{"".join(rows)}</div>'


def table_preview(path: Path, column: str | None, n: int = 6) -> tuple[str, dict[str, Any]]:
    """A few rows of a data file, with the cited column marked; returns (html, stats)."""
    try:
        df = pd.read_csv(path, nrows=n + 1)
    except (OSError, pd.errors.ParserError, UnicodeDecodeError):
        return "", {}
    head = df.head(n)
    header = "".join(f'<th class="{"sel" if str(c) == column else ""}">{escape(str(c))}</th>' for c in df.columns)
    body = "".join("<tr>" + "".join(
        f'<td class="{"sel" if str(c) == column else ""}">{escape("" if pd.isna(v) else str(v))}</td>'
        for c, v in zip(df.columns, row, strict=False)) + "</tr>" for row in head.itertuples(index=False))
    stats: dict[str, Any] = {}
    if column and column in df.columns:
        full = pd.read_csv(path, usecols=[column])
        col = full[column]
        numeric = pd.to_numeric(col, errors="coerce")
        stats = {"rows": len(col), "missing": int(col.isna().sum())}
        if numeric.notna().any():
            stats["min"], stats["max"] = float(numeric.min()), float(numeric.max())
    return f'<div class="table-wrap"><table class="preview"><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>', stats


def figure_image(project_assets: Path, name: str | None, site_assets: Path) -> str | None:
    if not name:
        return None
    src = project_assets / name
    if not src.exists():
        return None
    dst = site_assets / "figures" / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists() or dst.stat().st_size != src.stat().st_size:
        dst.write_bytes(src.read_bytes())
    return dst.relative_to(site_assets).as_posix()
