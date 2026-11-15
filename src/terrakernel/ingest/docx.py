"""Read Word paragraphs and tables without executing fields or embedded objects."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

from terrakernel.ingest.common import EvidenceBuilder, section_scope
from terrakernel.ingest.docx_media import CAPTION, DocxMedia
from terrakernel.models import Evidence, EvidenceKind, Locator, Source

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
}
W = "{" + NS["w"] + "}"
M = "{" + NS["m"] + "}"


def _text(node: ET.Element) -> str:
    pieces: list[str] = []
    for child in node.iter():
        if child.tag in {W + "t", M + "t"}:
            pieces.append(child.text or "")
        elif child.tag == W + "tab":
            pieces.append("\t")
        elif child.tag in {W + "br", W + "cr"}:
            pieces.append("\n")
    return "".join(pieces).strip()


def _heading_level(properties: ET.Element | None) -> int | None:
    if properties is None:
        return None
    outline = properties.find("w:outlineLvl", NS)
    if outline is not None:
        value = outline.get(W + "val", "")
        if value.isdigit() and int(value) < 9:
            return int(value) + 1
    return None


def _styles(archive: ZipFile) -> dict[str, int]:
    if "word/styles.xml" not in archive.namelist():
        return {}
    root = ET.fromstring(archive.read("word/styles.xml"))
    levels: dict[str, int] = {}
    parents: dict[str, str] = {}
    for style in root.findall("w:style", NS):
        sid = style.get(W + "styleId", "")
        level = _heading_level(style.find("w:pPr", NS))
        name = style.find("w:name", NS)
        match = re.fullmatch(r"(?:heading|标题)\s*([1-9])", name.get(W + "val", "") if name is not None else sid, re.I)
        if level is not None or match:
            levels[sid] = level if level is not None else int(match[1])
        parent = style.find("w:basedOn", NS)
        if parent is not None:
            parents[sid] = parent.get(W + "val", "")
    for sid in parents:
        seen: set[str] = set()
        current = sid
        while current in parents and current not in seen and current not in levels:
            seen.add(current)
            current = parents[current]
        if current in levels:
            levels[sid] = levels[current]
    return levels


def _blocks(node: ET.Element):
    for child in node:
        if child.tag in {W + "p", W + "tbl"}:
            yield child
        elif child.tag in {W + "sdt", W + "sdtContent", W + "customXml", W + "ins"}:
            yield from _blocks(child)


def ingest_docx(source: Source, path: Path, assets_dir: Path) -> list[Evidence]:
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
        levels = _styles(archive)
        media = DocxMedia(archive, source, assets_dir)
    body = root.find("w:body", NS)
    if body is None:
        return []
    builder = EvidenceBuilder(source.id)
    headings: list[tuple[int, str]] = []
    counts = {"paragraph": 0, "table": 0}
    blocks = list(_blocks(body))
    block_evidence: dict[int, Evidence] = {}
    caption_links: list[tuple[Evidence, int]] = []
    for block_index, block in enumerate(blocks, 1):
        is_table = block.tag == W + "tbl"
        block_type = "table" if is_table else "paragraph"
        counts[block_type] += 1
        meta: dict = {"format": "docx", "xml_part": "word/document.xml", "body_block": block_index}
        if is_table:
            rows = [
                ["\n".join(_text(p) for p in cell.findall(".//w:p", NS)) for cell in row.findall("w:tc", NS)]
                for row in block.findall("w:tr", NS)
            ]
            content = "\n".join("\t".join(cell.replace("\n", " / ") for cell in row) for row in rows)
            kind = EvidenceKind.table
            meta["rows"] = rows
        else:
            content = _text(block)
            properties = block.find("w:pPr", NS)
            level = _heading_level(properties)
            style = block.find("w:pPr/w:pStyle", NS)
            if level is None and style is not None:
                level = levels.get(style.get(W + "val", ""))
            kind = EvidenceKind.paragraph
            if level is not None and content:
                headings = [(depth, title) for depth, title in headings if depth < level]
                headings.append((level, content))
                kind = EvidenceKind.heading
            elif block.find("w:pPr/w:numPr", NS) is not None:
                kind = EvidenceKind.list_item
        math = block.findall(".//m:oMath", NS)
        if math:
            meta["math_representation"] = "Plain OMML text; mathematical layout is not reconstructed."
            meta["omml"] = [ET.tostring(item, encoding="unicode") for item in math]
        section = [title for _, title in headings]
        locator = Locator(section=" / ".join(section) or None, symbol=f"{block_type} {counts[block_type]}")
        related = []
        if content.strip():
            item = builder.add(kind, content, locator, builder.key(section_scope(section), "t" if is_table else "p"), meta=meta)
            block_evidence[block_index] = item
            related.append(item.id)
        caption, caption_index = "", None
        for neighbor_index in (block_index + 1, block_index - 1):
            if 1 <= neighbor_index <= len(blocks):
                neighbor = blocks[neighbor_index - 1]
                text = _text(neighbor)
                style = neighbor.find("w:pPr/w:pStyle", NS)
                style_name = style.get(W + "val", "") if style is not None else ""
                if neighbor.tag == W + "p" and (CAPTION.match(text) or style_name.lower() == "caption"):
                    caption, caption_index = text, neighbor_index
                    break
        start = len(media.figures)
        media.add(builder, block, locator, section, block_index, related, caption)
        if caption_index is not None:
            caption_links.extend((item, caption_index) for item in media.figures[start:])
    for item, caption_index in caption_links:
        if caption_index in block_evidence:
            item.related.append(block_evidence[caption_index].id)
    media.finish()
    return builder.items
