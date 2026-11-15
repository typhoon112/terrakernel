"""Shared helpers for building evidence with stable identifiers."""

from __future__ import annotations

from collections import defaultdict

from terrakernel.models import Evidence, EvidenceKind, Locator
from terrakernel.util import short_hash, slugify


class EvidenceBuilder:
    """Assigns stable, human-readable evidence IDs.

    IDs are derived from the position inside the document structure (section path +
    ordinal, page + block number, column name, code symbol), *not* from the content, so
    an edited paragraph keeps its ID and the update stage can report it as "changed".
    """

    def __init__(self, source_id: str):
        self.source_id = source_id
        self.items: list[Evidence] = []
        self._counters: dict[str, int] = defaultdict(int)
        self._used: set[str] = set()

    def key(self, scope: str, kind_prefix: str) -> str:
        self._counters[(scope, kind_prefix)] += 1  # type: ignore[index]
        n = self._counters[(scope, kind_prefix)]  # type: ignore[index]
        return f"{scope}/{kind_prefix}{n}" if scope else f"{kind_prefix}{n}"

    def add(
        self,
        kind: EvidenceKind,
        content: str,
        locator: Locator,
        key: str,
        *,
        asset: str | None = None,
        related: list[str] | None = None,
        meta: dict | None = None,
    ) -> Evidence:
        content = content.strip()
        eid = f"ev:{self.source_id}:{key}"
        base, n = eid, 2
        while eid in self._used:
            eid = f"{base}~{n}"
            n += 1
        self._used.add(eid)
        ev = Evidence(
            id=eid,
            source_id=self.source_id,
            kind=kind,
            locator=locator,
            content=content,
            content_hash=short_hash(content, 16),
            asset=asset,
            related=related or [],
            meta=meta or {},
        )
        self.items.append(ev)
        return ev


def section_scope(path: list[str]) -> str:
    return "/".join(slugify(p, 40) for p in path if p) or "root"
