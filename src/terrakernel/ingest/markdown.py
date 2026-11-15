"""Markdown ingest: headings, paragraphs, list items, tables and code blocks with line ranges."""

from __future__ import annotations

from pathlib import Path

from markdown_it import MarkdownIt

from terrakernel.ingest.common import EvidenceBuilder, section_scope
from terrakernel.models import Evidence, EvidenceKind, Locator, Source


def ingest_markdown(source: Source, path: Path, assets_dir: Path) -> list[Evidence]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return ingest_markdown_text(source.id, text)


def ingest_markdown_text(source_id: str, text: str, line_offset: int = 0, scope_prefix: str = "") -> list[Evidence]:
    md = MarkdownIt("commonmark").enable("table")
    tokens = md.parse(text)
    lines = text.splitlines()
    b = EvidenceBuilder(source_id)
    heading_path: list[str] = []

    def span(m: list[int] | None) -> tuple[int | None, int | None, str]:
        if not m:
            return None, None, ""
        start, end = m
        return start + 1 + line_offset, end + line_offset, "\n".join(lines[start:end])

    def scope() -> str:
        s = section_scope(heading_path)
        return f"{scope_prefix}/{s}" if scope_prefix else s

    i = 0
    list_depth = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open":
            level = int(tok.tag[1])
            inline = tokens[i + 1]
            title = inline.content.strip()
            heading_path = heading_path[: level - 1] + [title]
            ls, le, _ = span(tok.map)
            b.add(
                EvidenceKind.heading,
                title,
                Locator(section=" > ".join(heading_path), line_start=ls, line_end=le),
                b.key(scope(), "h"),
                meta={"level": level},
            )
            i += 3
            continue
        if tok.type in ("bullet_list_open", "ordered_list_open"):
            list_depth += 1
        elif tok.type in ("bullet_list_close", "ordered_list_close"):
            list_depth -= 1
        elif tok.type == "list_item_open" and list_depth == 1:
            ls, le, raw = span(tok.map)
            b.add(
                EvidenceKind.list_item,
                raw,
                Locator(section=" > ".join(heading_path) or None, line_start=ls, line_end=le),
                b.key(scope(), "li"),
            )
        elif tok.type == "paragraph_open" and list_depth == 0:
            ls, le, raw = span(tok.map)
            b.add(
                EvidenceKind.paragraph,
                raw,
                Locator(section=" > ".join(heading_path) or None, line_start=ls, line_end=le),
                b.key(scope(), "p"),
            )
        elif tok.type == "table_open":
            ls, le, raw = span(tok.map)
            b.add(
                EvidenceKind.table,
                raw,
                Locator(section=" > ".join(heading_path) or None, line_start=ls, line_end=le),
                b.key(scope(), "t"),
            )
        elif tok.type in ("fence", "code_block"):
            ls, le, raw = span(tok.map)
            b.add(
                EvidenceKind.code_block,
                raw,
                Locator(section=" > ".join(heading_path) or None, line_start=ls, line_end=le),
                b.key(scope(), "code"),
                meta={"info": tok.info.strip()} if tok.info else None,
            )
        i += 1
    return b.items
