"""Core data model shared by every stage (pydantic, mirrored 1:1 in SQLite).

Vocabulary
- Source: one input file.
- Evidence: a locatable unit inside a source (paragraph, table column, code symbol ...).
- KnowledgeObject: a typed unit of knowledge (concept, claim, method, dataset,
  constraint, capability) that must be grounded in evidence.
- EvidenceLink: why an object is grounded (with a verbatim quote).
- Relation: a typed edge between objects (variant_of, conflicts_with, implements ...).
- Gap: something the materials do not say but a task needs (never filled with defaults).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SourceKind(StrEnum):
    pdf = "pdf"
    markdown = "markdown"
    text = "text"
    table = "table"
    array = "array"  # self-describing gridded data (NetCDF)
    code = "code"
    image = "image"
    other = "other"


class EvidenceKind(StrEnum):
    heading = "heading"
    paragraph = "paragraph"
    list_item = "list_item"
    table = "table"
    table_row = "table_row"
    table_column = "table_column"
    dataset_profile = "dataset_profile"
    variable = "variable"
    figure = "figure"
    formula = "formula"
    code_module = "code_module"
    code_symbol = "code_symbol"
    code_block = "code_block"
    image = "image"


class ObjectType(StrEnum):
    concept = "concept"
    claim = "claim"
    method = "method"
    dataset = "dataset"
    constraint = "constraint"
    capability = "capability"


class Basis(StrEnum):
    """Where a piece of knowledge comes from. Never collapsed into a single score."""

    stated = "stated"  # the materials say so explicitly
    inferred = "inferred"  # derived by the model from the materials (must explain how)
    measured = "measured"  # computed by a deterministic tool (e.g. a CSV profile)
    human_confirmed = "human_confirmed"  # answered by a person


class ObjectStatus(StrEnum):
    active = "active"
    needs_review = "needs_review"
    superseded = "superseded"


class LinkRole(StrEnum):
    supports = "supports"
    defines = "defines"
    contradicts = "contradicts"
    implements = "implements"
    measures = "measures"
    mentions = "mentions"


class RelationType(StrEnum):
    variant_of = "variant_of"
    same_as = "same_as"
    possibly_same_as = "possibly_same_as"
    conflicts_with = "conflicts_with"
    implements = "implements"
    uses = "uses"
    applies_to = "applies_to"
    depends_on = "depends_on"
    describes = "describes"
    part_of = "part_of"


class Severity(StrEnum):
    blocking = "blocking"
    warning = "warning"


class Locator(BaseModel):
    page: int | None = None
    bbox: list[float] | None = None  # x0, top, x1, bottom in PDF points
    section: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    column: str | None = None
    row: int | None = None
    symbol: str | None = None

    def short(self) -> str:
        parts: list[str] = []
        if self.page is not None:
            parts.append(f"p.{self.page}")
        if self.section:
            parts.append(f"§{self.section}")
        if self.symbol:
            parts.append(self.symbol)
        if self.column:
            parts.append(f"column {self.column}")
        if self.line_start is not None:
            parts.append(
                f"L{self.line_start}" + (f"-{self.line_end}" if self.line_end and self.line_end != self.line_start else "")
            )
        return " ".join(parts)


class Source(BaseModel):
    id: str
    path: str  # relative to the materials root
    kind: SourceKind
    sha256: str
    size: int
    media_type: str | None = None
    title: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class Evidence(BaseModel):
    id: str  # ev:<source>:<stable locator key>
    source_id: str
    kind: EvidenceKind
    locator: Locator = Field(default_factory=Locator)
    content: str
    content_hash: str
    order: int = 0
    asset: str | None = None  # path (relative to the project) of a cropped image, if any
    related: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class KnowledgeObject(BaseModel):
    id: str  # <type>:<slug>
    type: ObjectType
    name: str
    summary: str = ""
    aliases: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    basis: Basis = Basis.stated
    basis_note: str | None = None
    scope: str | None = None
    status: ObjectStatus = ObjectStatus.active
    source_ids: list[str] = Field(default_factory=list)
    produced_by: str = ""  # actor, e.g. terrakernel/0.1.0+claude-opus-5-5


class EvidenceLink(BaseModel):
    object_id: str
    evidence_id: str
    role: LinkRole = LinkRole.supports
    quote: str = ""
    match_score: float | None = None


class Relation(BaseModel):
    id: str
    type: RelationType
    src: str
    dst: str
    basis: Basis = Basis.inferred
    note: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class Gap(BaseModel):
    id: str
    subject_id: str | None = None
    field: str | None = None
    description: str
    severity: Severity = Severity.warning
    suggestion: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    resolved_by: str | None = None
    resolution: str | None = None


class ValidationRecord(BaseModel):
    id: str
    stage: str
    target_id: str
    check: str
    status: str  # pass | fail | warn | skip
    detail: str = ""
    at: str = ""
