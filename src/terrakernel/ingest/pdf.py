"""PDF ingest with pdfplumber (text + coordinates) and pypdfium2 (rendering).

Each page is split into blocks (headings, paragraphs, centred formulas, captions),
tables and figures, all with page numbers and bounding boxes so any later knowledge
can be traced to an exact region. Sub- and superscripts are kept on their line and
written as ``x_t`` / ``x^2``. Figures are cropped to PNG assets for visual extraction.
"""

from __future__ import annotations

import re
import statistics
from pathlib import Path
from typing import Any

import pdfplumber
import pypdfium2 as pdfium

from terrakernel.ingest.common import EvidenceBuilder
from terrakernel.models import Evidence, EvidenceKind, Locator, Source

SECTION_RE = re.compile(r"^(\d+(?:\.\d+)*|[IVX]{1,5}|[A-H])\.?\s+([A-Z][^\n]{0,90})$")
CAPS_HEADING_RE = re.compile(r"^[A-Z][A-Z0-9 ,&:\-]{3,60}$")
CID_RE = re.compile(r"\(cid:\d+\)")
PAGE_NUMBER_RE = re.compile(r"^(page\s*)?\d{1,4}(\s*(of|/)\s*\d{1,4})?$", re.I)
WORD_OPTS = {"x_tolerance": 1.5, "x_tolerance_ratio": 0.15, "y_tolerance": 3}
CAPTION_RE = re.compile(r"^(Figure|Fig\.|Table)\s*(\d+)\s*[.:]", re.I)
MATH_CHARS = set("=+−-×·÷/^_∑Σ√∫≤≥≈≠∈∀∂αβγδεθλμνπρστφχψωΔΩ()[]|%")
RENDER_SCALE = 2.0

# Adobe Symbol font encoding -> Unicode, for PDFs whose Symbol font lacks a ToUnicode map.
SYMBOL_MAP = {
    "a": "α", "b": "β", "g": "γ", "d": "δ", "e": "ε", "z": "ζ", "h": "η", "q": "θ", "i": "ι", "k": "κ",
    "l": "λ", "m": "μ", "n": "ν", "x": "ξ", "o": "ο", "p": "π", "r": "ρ", "s": "σ", "t": "τ", "u": "υ",
    "f": "φ", "c": "χ", "y": "ψ", "w": "ω", "G": "Γ", "D": "Δ", "Q": "Θ", "L": "Λ", "X": "Ξ", "P": "Π",
    "S": "Σ", "U": "Υ", "F": "Φ", "Y": "Ψ", "W": "Ω", "-": "−", "´": "×", "¸": "÷", "£": "≤", "³": "≥",
    "¹": "≠", "»": "≈", "±": "±", "Ö": "√", "ò": "∫", "¶": "∂", "¥": "∞", "Î": "∈", "×": "·",
}


def _fix_symbol_font(words: list[dict[str, Any]]) -> None:
    for w in words:
        if "symbol" in str(w.get("fontname", "")).lower():
            w["text"] = "".join(SYMBOL_MAP.get(ch, ch) for ch in w["text"])
        if "(cid:" in w["text"]:
            w["text"] = CID_RE.sub("\ufffd", w["text"])


def _extract_words(page: Any) -> list[dict[str, Any]]:
    try:
        words = page.extract_words(extra_attrs=["size", "fontname"], keep_blank_chars=False, **WORD_OPTS)
    except TypeError:  # older pdfplumber without x_tolerance_ratio
        words = page.extract_words(extra_attrs=["size", "fontname"], keep_blank_chars=False, x_tolerance=1.5)
    # drop rotated text (margin watermarks such as arXiv identifiers, rotated axis labels)
    return [w for w in words if w.get("upright", True)]


def _is_section_heading(text: str) -> bool:
    t = text.strip()
    if len(t) > 90 or "\n" in t:
        return False
    return bool(SECTION_RE.match(t)) or (bool(CAPS_HEADING_RE.match(t)) and len(t.split()) <= 6)


def _inside(word: dict[str, Any], bbox: tuple[float, float, float, float]) -> bool:
    x0, top, x1, bottom = bbox
    cx = (word["x0"] + word["x1"]) / 2
    cy = (word["top"] + word["bottom"]) / 2
    return x0 - 1 <= cx <= x1 + 1 and top - 1 <= cy <= bottom + 1


def _group_lines(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cluster words into text lines by vertical overlap, keeping sub/superscripts on their line."""
    words = sorted(words, key=lambda w: (-w.get("size", 0), w["top"], w["x0"]))
    lines: list[dict[str, Any]] = []
    for w in words:
        h = max(0.1, w["bottom"] - w["top"])
        best, best_ratio = None, 0.0
        for ln in lines:
            ov = min(w["bottom"], ln["bottom"]) - max(w["top"], ln["top"])
            if ov <= 0:
                continue
            ratio = ov / min(h, max(0.1, ln["bottom"] - ln["top"]))
            if ratio > best_ratio:
                best, best_ratio = ln, ratio
        if best is not None and best_ratio >= 0.4:
            best["words"].append(w)
            if w.get("size", 0) >= 0.9 * best["size"]:
                best["top"] = min(best["top"], w["top"])
                best["bottom"] = max(best["bottom"], w["bottom"])
            best["x0"] = min(best["x0"], w["x0"])
            best["x1"] = max(best["x1"], w["x1"])
        else:
            lines.append({"words": [w], "top": w["top"], "bottom": w["bottom"], "x0": w["x0"], "x1": w["x1"],
                          "size": w.get("size", 0)})
    for ln in lines:
        ln["words"].sort(key=lambda w: w["x0"])
        mid = (ln["top"] + ln["bottom"]) / 2
        parts: list[str] = []
        prev_x1 = None
        for w in ln["words"]:
            small = w.get("size", 0) < 0.85 * ln["size"]
            adjacent = prev_x1 is not None and w["x0"] - prev_x1 < 1.5
            if small:
                center = (w["top"] + w["bottom"]) / 2
                mark = "_" if center > mid else "^"
                token = mark + w["text"]
                if adjacent and parts:
                    parts[-1] += token
                else:
                    parts.append(token)
            elif adjacent and parts and parts[-1][-1:] in "_^" + "".join(MATH_CHARS):
                parts[-1] += w["text"]
            else:
                parts.append(w["text"])
            prev_x1 = w["x1"]
        ln["text"] = " ".join(parts)
        fonts = [str(w.get("fontname", "")) for w in ln["words"]]
        ln["bold"] = sum("bold" in f.lower() for f in fonts) >= max(1, len(fonts) // 2)
    lines.sort(key=lambda ln: (ln["top"], ln["x0"]))
    return lines


def _is_formula_text(text: str) -> bool:
    t = text.strip()
    if len(t) < 3 or len(t) > 220:
        return False
    sym = sum(ch in MATH_CHARS for ch in t)
    letters = sum(ch.isalpha() for ch in t)
    words = len(t.split())
    return ("=" in t and sym / max(1, len(t)) > 0.06 and words <= 30) or (sym > letters and words <= 12)


def _rule_tables(page: Any, words: list[dict[str, Any]]) -> list[tuple[tuple[float, float, float, float], list[list[str]]]]:
    """Find tables drawn with horizontal rules only (booktabs style) and extract them by text alignment."""
    rules = [
        (ln["x0"], ln["top"], ln["x1"])
        for ln in page.lines
        if abs(ln["top"] - ln["bottom"]) < 1.0 and (ln["x1"] - ln["x0"]) > 60
    ]
    rules += [
        (r["x0"], r["top"], r["x1"])
        for r in page.rects
        if r["height"] < 1.5 and r["width"] > 60
    ]
    rules.sort(key=lambda r: r[1])
    clusters: list[list[tuple[float, float, float]]] = []
    for r in rules:
        if clusters:
            last = clusters[-1][-1]
            if abs(r[0] - last[0]) < 4 and abs(r[2] - last[2]) < 4 and r[1] - last[1] < 160:
                clusters[-1].append(r)
                continue
        clusters.append([r])
    out = []
    for cl in clusters:
        if len(cl) < 2:
            continue
        bbox = (min(r[0] for r in cl) - 2, cl[0][1] - 2, max(r[2] for r in cl) + 2, cl[-1][1] + 2)
        rows = _rows_from_words([w for w in words if _inside(w, bbox)])
        if len(rows) >= 2:
            out.append((bbox, rows))
    return out


def _rows_from_words(words: list[dict[str, Any]]) -> list[list[str]]:
    """Rebuild a table from word positions: rows by vertical overlap, columns by x-projection bands."""
    if not words:
        return []
    lines = _group_lines(words)
    size = statistics.median([w.get("size", 8) for w in words])
    spans = sorted((w["x0"], w["x1"]) for w in words)
    bands: list[list[float]] = []
    for x0, x1 in spans:
        if bands and x0 - bands[-1][1] < 0.6 * size:
            bands[-1][1] = max(bands[-1][1], x1)
        else:
            bands.append([x0, x1])
    rows = []
    for ln in lines:
        cells = [""] * len(bands)
        for w in ln["words"]:
            cx = (w["x0"] + w["x1"]) / 2
            idx = min(range(len(bands)), key=lambda i: 0 if bands[i][0] <= cx <= bands[i][1]
                      else min(abs(cx - bands[i][0]), abs(cx - bands[i][1])))
            cells[idx] = (cells[idx] + " " + w["text"]).strip()
        if any(cells):
            rows.append(cells)
    return rows


def _table_markdown(rows: list[list[str]]) -> str:
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    md = ["| " + " | ".join(c.replace("\n", " ") for c in r) + " |" for r in rows]
    md.insert(1, "|" + "---|" * width)
    return "\n".join(md)


def _find_gutter(words: list[dict[str, Any]], width: float, body_size: float) -> float | None:
    """x position of the gap between two text columns, or None for a single-column page.

    Works on pages that mix full-width blocks (title, abstract) with two columns: it looks
    for an x position in the middle of the page where many text rows have a wide gap.
    """
    rows = [r for r in _group_lines(words) if len(r["words"]) >= 2]
    if len(rows) < 8:
        return None
    lo, hi = width * 0.3, width * 0.7
    min_gap = max(6.0, 0.9 * body_size)
    gaps: list[tuple[float, float, float]] = []  # (center, left edge, right edge)
    for r in rows:
        ws = sorted(r["words"], key=lambda w: w["x0"])
        for a, b in zip(ws, ws[1:], strict=False):
            gap = b["x0"] - a["x1"]
            c = (a["x1"] + b["x0"]) / 2
            if gap >= min_gap and lo <= c <= hi:
                gaps.append((c, a["x1"], b["x0"]))
    if not gaps:
        return None
    # the right column starts at a nearly constant x: cluster on the right edges of the gaps
    bins: dict[int, list[tuple[float, float, float]]] = {}
    for g in gaps:
        bins.setdefault(int(g[2] // 6), []).append(g)
    key = max(bins, key=lambda k: len(bins[k]) + len(bins.get(k + 1, [])) + len(bins.get(k - 1, [])))
    support = bins[key] + bins.get(key + 1, []) + bins.get(key - 1, [])
    if len(support) < max(6, 0.25 * len(rows)):
        return None
    right_start = sorted(g[2] for g in support)[len(support) // 10]
    left_end = max(g[1] for g in support)
    if left_end >= right_start:
        return statistics.median(g[0] for g in support)
    return (left_end + right_start) / 2


def _order_lines(words: list[dict[str, Any]], gutter: float | None, min_gap: float = 6.0) -> list[dict[str, Any]]:
    """Group words into lines in reading order; two-column pages read left column, then right.

    Lines get ``col``: 0 for full-width (single-column page or spanning rows), 1 left, 2 right.
    Spanning rows (titles, wide figures' captions) separate bands of two-column text.
    """
    if gutter is None:
        lines = _group_lines(words)
        for ln in lines:
            ln["col"] = 0
        return lines
    rows = _group_lines(words)
    out: list[dict[str, Any]] = []
    band_left: list[dict[str, Any]] = []
    band_right: list[dict[str, Any]] = []

    def flush() -> None:
        for col, items in ((1, band_left), (2, band_right)):
            for ln in _group_lines([w for row in items for w in row["words"]]) if items else []:
                ln["col"] = col
                out.append(ln)
        band_left.clear()
        band_right.clear()

    for row in rows:
        ws = sorted(row["words"], key=lambda w: w["x0"])
        crosses = any(w["x0"] < gutter - 2 and w["x1"] > gutter + 2 for w in ws)
        if not crosses:
            before = [w for w in ws if (w["x0"] + w["x1"]) / 2 < gutter]
            after = [w for w in ws if (w["x0"] + w["x1"]) / 2 >= gutter]
            if before and after and after[0]["x0"] - before[-1]["x1"] < min_gap:
                crosses = True  # an ordinary word space happens to sit on the gutter: full-width line
        if crosses:
            flush()
            row["col"] = 0
            out.append(row)
            continue
        left = [w for w in row["words"] if (w["x0"] + w["x1"]) / 2 < gutter]
        right = [w for w in row["words"] if (w["x0"] + w["x1"]) / 2 >= gutter]
        if left:
            band_left.append({"words": left})
        if right:
            band_right.append({"words": right})
    flush()
    return out


def _furniture_key(word: dict[str, Any], words: list[dict[str, Any]], height: float) -> str:
    """Normalized text of the header/footer line containing ``word`` (digits masked)."""
    same = [w for w in words if abs(w["top"] - word["top"]) < 2]
    text = " ".join(w["text"] for w in sorted(same, key=lambda w: w["x0"]))
    zone = "top" if word["top"] < height / 2 else "bottom"
    return zone + ":" + re.sub(r"\d+", "#", text.strip().lower())


def _page_furniture(pdf: Any) -> set[str]:
    """Find running headers/footers using up to twelve evenly spaced pages.

    Sampling is only for repeated margin detection. The ingest loop still reads
    every page in full, without retaining a whole-book geometry cache.
    """
    pages = pdf.pages
    if len(pages) < 3:
        return set()
    sample_size = min(12, len(pages))
    sampled = [pages[round(i * (len(pages) - 1) / (sample_size - 1))] for i in range(sample_size)]
    counts: dict[str, int] = {}
    for page in sampled:
        words = _extract_words(page)
        margin = page.height * 0.07
        keys = {_furniture_key(w, words, page.height) for w in words
                if w["top"] < margin or w["bottom"] > page.height - margin}
        for k in keys:
            counts[k] = counts.get(k, 0) + 1
        # pdfplumber keeps parsed geometry on each Page. A full-document first
        # pass otherwise retains every page until the document is closed.
        page.close()
    return {k for k, c in counts.items() if c >= max(3, sample_size // 2)}


def ingest_pdf(source: Source, path: Path, assets_dir: Path) -> list[Evidence]:
    b = EvidenceBuilder(source.id)
    assets_dir.mkdir(parents=True, exist_ok=True)
    section_number: str | None = None
    section_title: str | None = None
    doc_title: str | None = None
    pdfium_doc = pdfium.PdfDocument(str(path))
    try:
        with pdfplumber.open(path) as pdf:
            body_sizes: list[float] = []
            for page in pdf.pages[:3]:
                body_sizes += [round(w.get("size", 0), 1) for w in page.extract_words(extra_attrs=["size"])]
                page.close()
            body_size = statistics.mode(body_sizes) if body_sizes else 10.0
            furniture = _page_furniture(pdf)

            for pno, page in enumerate(pdf.pages, start=1):
                words = _extract_words(page)
                _fix_symbol_font(words)
                margin = page.height * 0.07
                words = [w for w in words if not (
                    (w["top"] < margin or w["bottom"] > page.height - margin)
                    and _furniture_key(w, words, page.height) in furniture)]
                tables: list[tuple[tuple[float, float, float, float], list[list[str]]]] = []
                for t in page.find_tables():
                    rows = [[(c or "").strip() for c in row] for row in t.extract() if row]
                    if rows:
                        tables.append((t.bbox, rows))
                for bbox, rows in _rule_tables(page, words):
                    if not any(_inside({"x0": bbox[0], "x1": bbox[2], "top": bbox[1], "bottom": bbox[3]}, tb[0])
                               for tb in tables):
                        tables.append((bbox, rows))
                table_boxes = [t[0] for t in tables]
                images = [im for im in page.images if (im["x1"] - im["x0"]) > 40 and (im["bottom"] - im["top"]) > 40]
                image_boxes = [(im["x0"], im["top"], im["x1"], im["bottom"]) for im in images]
                free_words = [w for w in words if not any(_inside(w, bb) for bb in table_boxes + image_boxes)]
                gutter = _find_gutter(free_words, page.width, body_size)
                lines = _order_lines(free_words, gutter, min_gap=max(6.0, 0.9 * body_size))
                if not lines and not tables and not image_boxes:
                    page.close()
                    continue
                bounds: dict[int, tuple[float, float]] = {}
                for col in {ln["col"] for ln in lines}:
                    cl = [ln for ln in lines if ln["col"] == col]
                    bounds[col] = (min(ln["x0"] for ln in cl), max(ln["x1"] for ln in cl))
                heights = [ln["bottom"] - ln["top"] for ln in lines] or [body_size]
                lh = statistics.median(heights)

                blocks: list[dict[str, Any]] = []
                for ln in lines:
                    text = ln["text"]
                    is_heading = ((ln["size"] >= body_size * 1.15 or (ln["bold"] and len(text) < 90)) and len(text) < 160) \
                        or _is_section_heading(text)
                    left, right = bounds[ln["col"]]
                    centred = ln["x0"] > left + 20 and ln["x1"] < right - 20
                    is_formula = not is_heading and centred and _is_formula_text(text)
                    starts_caption = bool(CAPTION_RE.match(text))
                    prev = blocks[-1] if blocks else None
                    gap = (ln["top"] - prev["bottom"]) if prev else 0
                    same_heading = (
                        prev is not None and is_heading and prev["heading"]
                        and abs(ln["size"] - prev["size"]) < 0.6 and gap < lh * 0.9
                    )
                    new_block = not same_heading and (
                        prev is None or is_heading or prev["heading"] or starts_caption or is_formula
                        or prev["formula"] or gap > lh * 0.9 or gap < -lh or prev["col"] != ln["col"]
                        or abs(ln["size"] - prev["size"]) > 0.8
                    )
                    if new_block:
                        blocks.append({"lines": [ln], "top": ln["top"], "bottom": ln["bottom"], "x0": ln["x0"],
                                       "x1": ln["x1"], "heading": is_heading, "formula": is_formula,
                                       "size": ln["size"], "caption": starts_caption, "col": ln["col"]})
                    else:
                        prev["lines"].append(ln)
                        prev["bottom"] = max(prev["bottom"], ln["bottom"])
                        prev["x0"] = min(prev["x0"], ln["x0"])
                        prev["x1"] = max(prev["x1"], ln["x1"])

                captions: list[dict[str, Any]] = []
                page_sections: list[tuple[float, str | None]] = [(float("-inf"), (
                    f"{section_number} {section_title}" if section_number else section_title))]
                block_no = 0
                for bl in blocks:
                    sep = " " if bl["heading"] else "\n"
                    text = sep.join(ln["text"] for ln in bl["lines"]).strip()
                    if not text:
                        continue
                    bbox = [round(bl["x0"], 1), round(bl["top"], 1), round(bl["x1"], 1), round(bl["bottom"], 1)]
                    if not bl["heading"] and len(bl["lines"]) == 1 and PAGE_NUMBER_RE.match(text):
                        continue  # stray page number
                    if bl["heading"]:
                        m = SECTION_RE.match(text)
                        if m:
                            section_number, section_title = m.group(1), m.group(2).strip()
                        elif pno == 1 and doc_title is None:
                            doc_title = text
                        else:
                            section_number, section_title = None, text
                    section = f"{section_number} {section_title}" if section_number else section_title
                    if bl["heading"]:
                        page_sections.append((bl["top"], section))
                    cap = CAPTION_RE.match(text)
                    if bl["caption"] and cap:
                        captions.append({"text": text, "bbox": bbox, "label": f"{cap.group(1)} {cap.group(2)}",
                                         "is_table": cap.group(1).lower() == "table", "section": section})
                        continue
                    block_no += 1
                    kind = (EvidenceKind.heading if bl["heading"]
                            else EvidenceKind.formula if bl["formula"] else EvidenceKind.paragraph)
                    b.add(kind, text, Locator(page=pno, bbox=bbox, section=section), f"p{pno}-b{block_no:02d}",
                          meta={"font_size": round(bl["size"], 1)})

                def nearest_caption(box: tuple[float, float, float, float], want_table: bool,
                                    captions: list[dict[str, Any]] = captions) -> dict | None:
                    cands = [c for c in captions if c["is_table"] == want_table]
                    best = None
                    for c in cands:
                        dist = min(abs(c["bbox"][1] - box[3]), abs(box[1] - c["bbox"][3]))
                        if dist < 45 and (best is None or dist < best[0]):
                            best = (dist, c)
                    if best:
                        captions.remove(best[1])
                        return best[1]
                    return None

                def section_at(top: float, page_sections: list = page_sections) -> str | None:
                    return [sec for t, sec in page_sections if t <= top][-1]

                for tno, (tb, rows) in enumerate(sorted(tables, key=lambda t: t[0][1]), start=1):
                    caption = nearest_caption(tb, True)
                    content = (caption["text"] + "\n" if caption else "") + _table_markdown(rows)
                    b.add(EvidenceKind.table, content,
                          Locator(page=pno, bbox=[round(x, 1) for x in tb], section=section_at(tb[1])),
                          f"p{pno}-t{tno}",
                          meta={"caption": caption["text"] if caption else None,
                                "label": caption["label"] if caption else None, "rows": rows})

                rendered_page = None
                if image_boxes:
                    render_page = None
                    try:
                        render_page = pdfium_doc[pno - 1]
                        bitmap = render_page.render(scale=RENDER_SCALE)
                        try:
                            # The PIL view may share native memory, so detach it
                            # before closing the bitmap. Reuse one render for all
                            # figure crops on this page.
                            rendered_page = bitmap.to_pil().copy()
                        finally:
                            bitmap.close()
                    except Exception:
                        pass
                    finally:
                        if render_page is not None:
                            render_page.close()
                for fno, box in enumerate(image_boxes, start=1):
                    caption = nearest_caption(box, False)
                    asset_name: str | None = f"{source.id}_p{pno}_f{fno}.png"
                    try:
                        if rendered_page is None:
                            raise ValueError("Page could not be rendered")
                        with rendered_page.crop(tuple(int(v * RENDER_SCALE) for v in box)) as crop:
                            crop.save(assets_dir / asset_name)
                    except Exception:
                        asset_name = None
                    text = caption["text"] if caption else f"Figure on page {pno} (no caption found)."
                    b.add(EvidenceKind.figure, text,
                          Locator(page=pno, bbox=[round(v, 1) for v in box], section=section_at(box[1])),
                          f"p{pno}-f{fno}", asset=asset_name, meta={"label": caption["label"] if caption else None})
                if rendered_page is not None:
                    rendered_page.close()
                for c in captions:  # captions without a detected image or table (e.g. vector drawings)
                    b.add(EvidenceKind.figure if not c["is_table"] else EvidenceKind.table, c["text"],
                          Locator(page=pno, bbox=c["bbox"], section=c["section"]), f"p{pno}-cap-{c['label']}",
                          meta={"label": c["label"], "caption_only": True})
                page.close()
    finally:
        pdfium_doc.close()
    if doc_title:
        for ev in b.items:
            ev.meta.setdefault("doc_title", doc_title)
    return b.items
