"""Model-facing output schemas for the extract stage.

These are deliberately flat and permissive (``attributes`` is a list of key/value
pairs, values as JSON text) so the same schema works for every object type and for
structured-output endpoints that require ``additionalProperties: false`` everywhere.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EvidenceRef(BaseModel):
    evidence_id: str = Field(description="ID of an evidence unit from this batch")
    quote: str = Field(description="Exact text copied from that evidence unit")


class Attribute(BaseModel):
    key: str
    value: str = Field(description="Attribute value. Use plain text, or JSON for lists/objects.")


class ExtractedObject(BaseModel):
    type: Literal["concept", "claim", "method", "dataset", "constraint", "capability"]
    name: str
    aliases: list[str] = Field(default_factory=list)
    summary: str
    attributes: list[Attribute] = Field(default_factory=list)
    basis: Literal["stated", "inferred"]
    basis_note: str | None = None
    evidence: list[EvidenceRef]


class ExtractedGap(BaseModel):
    subject: str = Field(description="Name of the object or field the gap is about")
    field: str | None = None
    description: str
    severity: Literal["blocking", "warning"]
    suggestion: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    objects: list[ExtractedObject]
    gaps: list[ExtractedGap] = Field(default_factory=list)
