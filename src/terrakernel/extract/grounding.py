"""Deterministic grounding checks for extracted knowledge.

An extracted object is accepted only if every evidence reference points to a unit in
the batch it was extracted from and its quote can be found in that unit's content
(after normalization; fuzzy matching tolerates PDF line breaks and spacing).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from terrakernel.models import Evidence
from terrakernel.util import normalize_text

MIN_SCORE = 88.0


def _squash(text: str) -> str:
    return re.sub(r"[\s_^*`|]+", "", normalize_text(text))


def quote_score(quote: str, content: str) -> float:
    """Best-match score (0-100) of ``quote`` inside ``content``."""
    q = normalize_text(quote)
    c = normalize_text(content)
    if not q:
        return 0.0
    if q in c:
        return 100.0
    qs, cs = _squash(quote), _squash(content)
    if qs and qs in cs:
        return 99.0
    if len(q) > len(c) * 1.3:
        return float(fuzz.ratio(q, c))
    return float(fuzz.partial_ratio(q, c))


@dataclass
class GroundingReport:
    accepted: list[tuple[str, float]] = field(default_factory=list)  # (evidence_id, score)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.accepted) and not self.problems


def check_refs(refs: list[tuple[str, str]], batch: dict[str, Evidence], min_score: float = MIN_SCORE) -> GroundingReport:
    report = GroundingReport()
    if not refs:
        report.problems.append("no evidence given")
        return report
    for eid, quote in refs:
        ev = batch.get(eid)
        if ev is None:
            report.problems.append(f"evidence id {eid!r} is not in this batch")
            continue
        score = quote_score(quote, ev.content)
        if score < min_score:
            report.problems.append(f"quote not found in {eid} (match {score:.0f}/100): {quote[:120]!r}")
        else:
            report.accepted.append((eid, score))
    return report
