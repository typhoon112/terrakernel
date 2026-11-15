"""SQLite storage for the source knowledge base.

The database is the single source of truth for a project; Markdown and code in the
generated repository are views compiled from it. Tables mirror the pydantic models
in ``terrakernel.models``; flexible fields are stored as JSON text.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from terrakernel.models import (
    Evidence,
    EvidenceLink,
    Gap,
    KnowledgeObject,
    Locator,
    Relation,
    Source,
    ValidationRecord,
)

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY, path TEXT NOT NULL, kind TEXT NOT NULL, sha256 TEXT NOT NULL,
    size INTEGER NOT NULL, media_type TEXT, title TEXT, meta TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY, source_id TEXT NOT NULL, kind TEXT NOT NULL, locator TEXT NOT NULL,
    content TEXT NOT NULL, content_hash TEXT NOT NULL, ord INTEGER NOT NULL DEFAULT 0,
    asset TEXT, related TEXT NOT NULL DEFAULT '[]', meta TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS evidence_source ON evidence(source_id, ord);
CREATE TABLE IF NOT EXISTS objects (
    id TEXT PRIMARY KEY, type TEXT NOT NULL, name TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
    aliases TEXT NOT NULL DEFAULT '[]', attributes TEXT NOT NULL DEFAULT '{}', basis TEXT NOT NULL,
    basis_note TEXT, scope TEXT, status TEXT NOT NULL, source_ids TEXT NOT NULL DEFAULT '[]',
    produced_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS evidence_links (
    object_id TEXT NOT NULL, evidence_id TEXT NOT NULL, role TEXT NOT NULL, quote TEXT NOT NULL DEFAULT '',
    match_score REAL, PRIMARY KEY (object_id, evidence_id, role)
);
CREATE INDEX IF NOT EXISTS links_evidence ON evidence_links(evidence_id);
CREATE TABLE IF NOT EXISTS relations (
    id TEXT PRIMARY KEY, type TEXT NOT NULL, src TEXT NOT NULL, dst TEXT NOT NULL, basis TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '', evidence_ids TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS gaps (
    id TEXT PRIMARY KEY, subject_id TEXT, field TEXT, description TEXT NOT NULL, severity TEXT NOT NULL,
    suggestion TEXT NOT NULL DEFAULT '', evidence_ids TEXT NOT NULL DEFAULT '[]', resolved_by TEXT, resolution TEXT
);
CREATE TABLE IF NOT EXISTS validation_records (
    id TEXT PRIMARY KEY, stage TEXT NOT NULL, target_id TEXT NOT NULL, check_name TEXT NOT NULL,
    status TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def _j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class KnowledgeBase:
    """Thread-safe access: one SQLite connection per thread, writes serialized by a lock."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._write_lock = threading.RLock()
        self._all: list[sqlite3.Connection] = []
        self.conn.executescript(SCHEMA)

    @property
    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA busy_timeout=30000")
            self._local.conn = c
            self._all.append(c)
        return c

    def close(self) -> None:
        for c in self._all:
            try:
                c.close()
            except sqlite3.ProgrammingError:
                pass  # connection owned by a finished thread
        self._all.clear()
        self._local = threading.local()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self._write_lock:
            c = self.conn
            try:
                yield c
                c.commit()
            except Exception:
                c.rollback()
                raise

    # ------------------------------------------------------------- meta
    def set_meta(self, key: str, value: Any) -> None:
        with self.tx() as c:
            c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, _j(value)))

    def get_meta(self, key: str, default: Any = None) -> Any:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    # ------------------------------------------------------------- sources
    def upsert_source(self, s: Source) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT OR REPLACE INTO sources VALUES (?,?,?,?,?,?,?,?)",
                (s.id, s.path, s.kind.value, s.sha256, s.size, s.media_type, s.title, _j(s.meta)),
            )

    def sources(self) -> list[Source]:
        rows = self.conn.execute("SELECT * FROM sources ORDER BY path").fetchall()
        return [
            Source(
                id=r["id"], path=r["path"], kind=r["kind"], sha256=r["sha256"], size=r["size"],
                media_type=r["media_type"], title=r["title"], meta=json.loads(r["meta"]),
            )
            for r in rows
        ]

    def source(self, source_id: str) -> Source | None:
        r = self.conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        if r is None:
            return None
        return Source(id=r["id"], path=r["path"], kind=r["kind"], sha256=r["sha256"], size=r["size"],
                      media_type=r["media_type"], title=r["title"], meta=json.loads(r["meta"]))

    def delete_source(self, source_id: str) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM evidence WHERE source_id=?", (source_id,))
            c.execute("DELETE FROM sources WHERE id=?", (source_id,))

    # ------------------------------------------------------------- evidence
    def replace_evidence(self, source_id: str, items: Iterable[Evidence]) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM evidence WHERE source_id=?", (source_id,))
            c.executemany(
                "INSERT OR REPLACE INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        e.id, e.source_id, e.kind.value, e.locator.model_dump_json(exclude_none=True), e.content,
                        e.content_hash, e.order, e.asset, _j(e.related), _j(e.meta),
                    )
                    for e in items
                ],
            )

    @staticmethod
    def _row_to_evidence(r: sqlite3.Row) -> Evidence:
        return Evidence(
            id=r["id"], source_id=r["source_id"], kind=r["kind"], locator=Locator.model_validate_json(r["locator"]),
            content=r["content"], content_hash=r["content_hash"], order=r["ord"], asset=r["asset"],
            related=json.loads(r["related"]), meta=json.loads(r["meta"]),
        )

    def evidence(self, source_id: str | None = None) -> list[Evidence]:
        if source_id:
            rows = self.conn.execute("SELECT * FROM evidence WHERE source_id=? ORDER BY ord", (source_id,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM evidence ORDER BY source_id, ord").fetchall()
        return [self._row_to_evidence(r) for r in rows]

    def evidence_by_ids(self, ids: Iterable[str]) -> dict[str, Evidence]:
        ids = list(dict.fromkeys(ids))
        out: dict[str, Evidence] = {}
        for i in range(0, len(ids), 500):
            chunk = ids[i : i + 500]
            q = f"SELECT * FROM evidence WHERE id IN ({','.join('?' * len(chunk))})"
            for r in self.conn.execute(q, chunk).fetchall():
                out[r["id"]] = self._row_to_evidence(r)
        return out

    # ------------------------------------------------------------- objects
    def upsert_objects(self, objs: Iterable[KnowledgeObject]) -> None:
        with self.tx() as c:
            c.executemany(
                "INSERT OR REPLACE INTO objects VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        o.id, o.type.value, o.name, o.summary, _j(o.aliases), _j(o.attributes), o.basis.value,
                        o.basis_note, o.scope, o.status.value, _j(o.source_ids), o.produced_by,
                    )
                    for o in objs
                ],
            )

    def objects(self, type_: str | None = None) -> list[KnowledgeObject]:
        if type_:
            rows = self.conn.execute("SELECT * FROM objects WHERE type=? ORDER BY id", (type_,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM objects ORDER BY type, id").fetchall()
        return [
            KnowledgeObject(
                id=r["id"], type=r["type"], name=r["name"], summary=r["summary"], aliases=json.loads(r["aliases"]),
                attributes=json.loads(r["attributes"]), basis=r["basis"], basis_note=r["basis_note"], scope=r["scope"],
                status=r["status"], source_ids=json.loads(r["source_ids"]), produced_by=r["produced_by"],
            )
            for r in rows
        ]

    def object(self, object_id: str) -> KnowledgeObject | None:
        r = self.conn.execute("SELECT * FROM objects WHERE id=?", (object_id,)).fetchone()
        if r is None:
            return None
        return KnowledgeObject(
            id=r["id"], type=r["type"], name=r["name"], summary=r["summary"], aliases=json.loads(r["aliases"]),
            attributes=json.loads(r["attributes"]), basis=r["basis"], basis_note=r["basis_note"], scope=r["scope"],
            status=r["status"], source_ids=json.loads(r["source_ids"]), produced_by=r["produced_by"],
        )

    def delete_objects(self, ids: Iterable[str]) -> None:
        ids = list(ids)
        with self.tx() as c:
            for oid in ids:
                c.execute("DELETE FROM objects WHERE id=?", (oid,))
                c.execute("DELETE FROM evidence_links WHERE object_id=?", (oid,))
                c.execute("DELETE FROM relations WHERE src=? OR dst=?", (oid, oid))

    # ------------------------------------------------------------- links
    def add_links(self, links: Iterable[EvidenceLink]) -> None:
        with self.tx() as c:
            c.executemany(
                "INSERT OR REPLACE INTO evidence_links VALUES (?,?,?,?,?)",
                [(lk.object_id, lk.evidence_id, lk.role.value, lk.quote, lk.match_score) for lk in links],
            )

    def links(self, object_id: str | None = None) -> list[EvidenceLink]:
        if object_id:
            rows = self.conn.execute("SELECT * FROM evidence_links WHERE object_id=?", (object_id,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM evidence_links").fetchall()
        return [
            EvidenceLink(object_id=r["object_id"], evidence_id=r["evidence_id"], role=r["role"], quote=r["quote"],
                         match_score=r["match_score"])
            for r in rows
        ]

    # ------------------------------------------------------------- relations
    def upsert_relations(self, rels: Iterable[Relation]) -> None:
        with self.tx() as c:
            c.executemany(
                "INSERT OR REPLACE INTO relations VALUES (?,?,?,?,?,?,?)",
                [(r.id, r.type.value, r.src, r.dst, r.basis.value, r.note, _j(r.evidence_ids)) for r in rels],
            )

    def relations(self) -> list[Relation]:
        rows = self.conn.execute("SELECT * FROM relations ORDER BY type, id").fetchall()
        return [
            Relation(id=r["id"], type=r["type"], src=r["src"], dst=r["dst"], basis=r["basis"], note=r["note"],
                     evidence_ids=json.loads(r["evidence_ids"]))
            for r in rows
        ]

    def clear_relations(self) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM relations")

    # ------------------------------------------------------------- gaps
    def upsert_gaps(self, gaps: Iterable[Gap], keep_resolution: bool = True) -> None:
        """Insert or replace gaps. By default an existing resolution survives re-extraction of the
        same gap; pass ``keep_resolution=False`` to deliberately reopen gaps."""
        gaps = list(gaps)
        if keep_resolution:
            existing = {g.id: g for g in self.gaps()}
            for g in gaps:
                old = existing.get(g.id)
                if old and old.resolved_by and not g.resolved_by:
                    g.resolved_by, g.resolution = old.resolved_by, old.resolution
        with self.tx() as c:
            c.executemany(
                "INSERT OR REPLACE INTO gaps VALUES (?,?,?,?,?,?,?,?,?)",
                [
                    (g.id, g.subject_id, g.field, g.description, g.severity.value, g.suggestion, _j(g.evidence_ids),
                     g.resolved_by, g.resolution)
                    for g in gaps
                ],
            )

    def gaps(self) -> list[Gap]:
        rows = self.conn.execute("SELECT * FROM gaps ORDER BY severity, id").fetchall()
        return [
            Gap(id=r["id"], subject_id=r["subject_id"], field=r["field"], description=r["description"],
                severity=r["severity"], suggestion=r["suggestion"], evidence_ids=json.loads(r["evidence_ids"]),
                resolved_by=r["resolved_by"], resolution=r["resolution"])
            for r in rows
        ]

    def clear_gaps(self, keep_resolved: bool = True) -> None:
        with self.tx() as c:
            if keep_resolved:
                c.execute("DELETE FROM gaps WHERE resolved_by IS NULL")
            else:
                c.execute("DELETE FROM gaps")

    # ------------------------------------------------------------- validation
    def add_validation(self, records: Iterable[ValidationRecord]) -> None:
        with self.tx() as c:
            c.executemany(
                "INSERT OR REPLACE INTO validation_records VALUES (?,?,?,?,?,?,?)",
                [(v.id, v.stage, v.target_id, v.check, v.status, v.detail, v.at) for v in records],
            )

    def validation(self, stage: str | None = None) -> list[ValidationRecord]:
        if stage:
            rows = self.conn.execute("SELECT * FROM validation_records WHERE stage=?", (stage,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM validation_records").fetchall()
        return [
            ValidationRecord(id=r["id"], stage=r["stage"], target_id=r["target_id"], check=r["check_name"],
                             status=r["status"], detail=r["detail"], at=r["at"])
            for r in rows
        ]

    def clear_validation(self, stage: str) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM validation_records WHERE stage=?", (stage,))

    # ------------------------------------------------------------- knowledge reset
    def clear_knowledge(self) -> None:
        """Drop everything derived by extraction (keeps sources and evidence)."""
        with self.tx() as c:
            for table in ("objects", "evidence_links", "relations"):
                c.execute(f"DELETE FROM {table}")
            c.execute("DELETE FROM gaps WHERE resolved_by IS NULL")

    def stats(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for table in ("sources", "evidence", "objects", "evidence_links", "relations", "gaps"):
            out[table] = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        out["objects_by_type"] = {
            r[0]: r[1] for r in self.conn.execute("SELECT type, COUNT(*) FROM objects GROUP BY type").fetchall()
        }
        out["evidence_by_kind"] = {
            r[0]: r[1] for r in self.conn.execute("SELECT kind, COUNT(*) FROM evidence GROUP BY kind").fetchall()
        }
        return out
