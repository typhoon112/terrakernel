"""Extract readable HTML blocks with original source lines; never fetch resources."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from terrakernel.ingest.common import EvidenceBuilder, section_scope
from terrakernel.models import Evidence, EvidenceKind, Locator, Source

HEADINGS = {f"h{level}" for level in range(1, 7)}
BLOCKS = HEADINGS | {"p", "div", "section", "article", "main", "li", "blockquote", "pre", "dt", "dd"}
IGNORED = {"script", "style", "head", "template", "noscript"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class _Reader(HTMLParser):
    def __init__(self, source_id: str):
        super().__init__(convert_charrefs=True)
        self.builder = EvidenceBuilder(source_id)
        self.ignored: list[str] = []
        self.blocks: list[str] = []
        self.headings: list[tuple[int, str]] = []
        self.parts: list[str] = []
        self.start = 1
        self.end = 1
        self.table_depth = 0
        self.table_rows: list[list[str]] = []
        self.row: list[str] = []
        self.cell: list[str] = []
        self.links: list[str] = []

    def flush(self) -> None:
        content = re.sub(r"\s+", " ", "".join(self.parts)).strip()
        if not content:
            self.parts = []
            self.links = []
            return
        tag = self.blocks[-1] if self.blocks else "body"
        kind = EvidenceKind.list_item if tag == "li" else EvidenceKind.paragraph
        if tag in HEADINGS:
            level = int(tag[1])
            self.headings = [(depth, title) for depth, title in self.headings if depth < level]
            self.headings.append((level, content))
            kind = EvidenceKind.heading
        self.add(kind, content, {"format": "html", "tag": tag, "links": self.links})
        self.parts = []
        self.links = []

    def add(self, kind: EvidenceKind, content: str, meta: dict) -> None:
        section = [title for _, title in self.headings]
        self.builder.add(
            kind, content,
            Locator(section=" / ".join(section) or None, line_start=self.start, line_end=self.end),
            self.builder.key(section_scope(section), "b"), meta=meta,
        )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.ignored:
            if tag not in VOID:
                self.ignored.append(tag)
            return
        attributes = dict(attrs)
        if tag in IGNORED or "hidden" in attributes or attributes.get("aria-hidden") == "true":
            if tag not in VOID:
                self.ignored.append(tag)
            return
        if tag == "table":
            if not self.table_depth:
                self.flush()
                self.start = self.getpos()[0]
                self.table_rows, self.row, self.cell = [], [], []
            self.table_depth += 1
            return
        if self.table_depth:
            if tag in {"td", "th"}:
                self.cell = []
            elif tag == "br" or tag in BLOCKS:
                self.cell.append(" ")
            return
        if tag in BLOCKS:
            self.flush()
            self.blocks.append(tag)
        elif tag in {"br", "hr"}:
            self.parts.append(" ")
        if tag == "a" and attributes.get("href"):
            self.links.append(attributes["href"])

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self.ignored:
            if tag in self.ignored:
                reverse_index = self.ignored[::-1].index(tag)
                del self.ignored[len(self.ignored) - reverse_index - 1:]
            return
        if self.table_depth:
            if tag in {"td", "th"}:
                self.row.append(re.sub(r"\s+", " ", "".join(self.cell)).strip())
                self.cell = []
            elif tag == "tr" and self.row:
                self.table_rows.append(self.row)
                self.row = []
            elif tag == "table":
                self.table_depth -= 1
                if not self.table_depth and self.table_rows:
                    self.end = self.getpos()[0]
                    content = "\n".join("\t".join(row) for row in self.table_rows)
                    self.add(EvidenceKind.table, content, {"format": "html", "rows": self.table_rows})
            return
        if tag in BLOCKS:
            self.flush()
            if tag in self.blocks:
                reverse_index = self.blocks[::-1].index(tag)
                del self.blocks[len(self.blocks) - reverse_index - 1:]

    def handle_data(self, data: str) -> None:
        if self.ignored:
            return
        if self.table_depth:
            self.cell.append(data)
            return
        if not self.parts or not any(part.strip() for part in self.parts):
            self.start = self.getpos()[0]
        if data.strip():
            self.end = self.getpos()[0] + data.count("\n")
        self.parts.append(data)


def ingest_html(source: Source, path: Path, assets_dir: Path) -> list[Evidence]:
    raw = path.read_bytes()
    declaration = re.search(rb"charset\s*=\s*[\"']?([A-Za-z0-9_.-]+)", raw[:8192], re.I)
    encoding = declaration[1].decode("ascii") if declaration else "utf-8-sig"
    try:
        content = raw.decode(encoding, errors="replace")
    except LookupError:
        content = raw.decode("utf-8-sig", errors="replace")
    reader = _Reader(source.id)
    reader.feed(content)
    reader.close()
    reader.flush()
    return reader.builder.items
