"""Plain text ingest (txt, rst, json, yaml): blank-line separated blocks with line ranges."""

from __future__ import annotations

from pathlib import Path

from terrakernel.ingest.common import EvidenceBuilder
from terrakernel.models import Evidence, EvidenceKind, Locator, Source

MAX_BLOCK_LINES = 40


def ingest_text(source: Source, path: Path, assets_dir: Path) -> list[Evidence]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    b = EvidenceBuilder(source.id)
    block: list[str] = []
    start = 0

    def flush(end_line: int) -> None:
        nonlocal block
        if any(x.strip() for x in block):
            b.add(
                EvidenceKind.paragraph,
                "\n".join(block),
                Locator(line_start=start + 1, line_end=end_line),
                b.key("", "b"),
            )
        block = []

    for idx, line in enumerate(lines):
        if not line.strip():
            flush(idx)
            start = idx + 1
            continue
        if not block:
            start = idx
        block.append(line)
        if len(block) >= MAX_BLOCK_LINES:
            flush(idx + 1)
            start = idx + 1
    flush(len(lines))
    return b.items
