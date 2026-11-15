"""Bound artifact-specific gap context while preserving the complete gap register."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from terrakernel.models import Gap
from terrakernel.plan import _terms
from terrakernel.project import Project

GAP_CONTEXT_BUDGET = 12_000


@dataclass
class GapContext:
    gaps: list[Gap]
    text: str
    total_open: int


def gap_context(project: Project, object_ids: set[str], task_text: str,
                budget: int = GAP_CONTEXT_BUDGET, max_gaps: int | None = None) -> GapContext:
    """Select by subject, source, then task terms; count omissions without resolving them."""
    if budget < 512:
        raise ValueError("Gap context budget must be at least 512 characters")
    kb = project.kb
    gaps = [gap for gap in kb.gaps() if not gap.resolved_by]
    sources = {sid for oid in object_ids if (obj := kb.object(oid)) is not None for sid in obj.source_ids}
    evidence_ids = sorted({eid for gap in gaps for eid in gap.evidence_ids})
    evidence_sources: dict[str, str] = {}
    # Only fetch identity columns, not all paragraph/table/image payloads once per artifact.
    for offset in range(0, len(evidence_ids), 900):
        chunk = evidence_ids[offset:offset + 900]
        placeholders = ",".join("?" for _ in chunk)
        evidence_sources.update((row["id"], row["source_id"]) for row in kb.conn.execute(
            f"SELECT id, source_id FROM evidence WHERE id IN ({placeholders})", chunk,
        ))
    terms = {gap.id: _terms(f"{gap.description} {gap.suggestion}") for gap in gaps}
    frequencies = Counter(term for tokens in terms.values() for term in tokens)
    query = _terms(task_text)
    candidates = []
    for gap in gaps:
        shared = terms[gap.id] & query
        score = sum(math.log(1 + len(gaps) / frequencies[term]) for term in shared)
        source_match = any(evidence_sources.get(eid) in sources for eid in gap.evidence_ids)
        if gap.subject_id in object_ids:
            priority = 0
        elif source_match:
            priority = 1
        elif score:
            priority = 2
        else:
            continue
        candidates.append((priority, gap.severity.value != "blocking", -score, gap.id, gap))

    def render(selected: list[Gap]) -> str:
        lines = ["Candidate reports from limited extraction/reconciliation contexts; not rechecked against the full KB. "
                 "Answers may exist elsewhere."]
        lines += [f"- [{gap.severity.value}] ({gap.id}) {gap.description}" for gap in selected]
        lines.append(
            f"Selected {len(selected)} of {len(gaps)} open candidate reports for this artifact; "
            f"{len(gaps) - len(selected)} omitted from this prompt, not resolved. "
            "Full register: knowledge/gaps.md and knowledge/gaps.jsonl."
        )
        lines.append("Cross-check current objects/tools. Do not repeat a missing-material claim they answer; "
                     "without evidence of global absence, label it unconfirmed.")
        return "\n".join(lines)

    selected: list[Gap] = []
    if len(render(selected)) > budget:
        raise ValueError("Gap context budget cannot fit the scope and coverage notices")
    for _, _, _, _, gap in sorted(candidates, key=lambda item: item[:4]):
        if max_gaps is not None and len(selected) >= max_gaps:
            break
        if len(render([*selected, gap])) <= budget:
            selected.append(gap)
    return GapContext(selected, render(selected), len(gaps))
