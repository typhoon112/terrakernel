"""Grade agent answers against an expected answer file.

The expected file (written by an independent reference solution) contains:
- ``values``: name -> {value, rel_tol, abs_tol}
- ``variants``: named common mistakes -> values that mistake would produce
- ``required_open_issues``: issues the answer must mention (keyword match)

Grading is deterministic. A value is correct when it is within tolerance. A wrong value is
attributed to a mistake when it matches that mistake's variant value within the same
tolerance.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def _close(got: float, want: float, rel: float, abs_: float) -> bool:
    return math.isfinite(got) and abs(got - want) <= max(abs_, rel * abs(want))


def grade(answer: dict[str, Any] | None, expected_path: str | Path) -> dict[str, Any]:
    expected = json.loads(Path(expected_path).read_text())
    spec = expected["values"]
    if not answer:
        return {"score": 0.0, "correct": 0, "total": len(spec), "values": {}, "mistakes": [], "open_issues": {},
                "all_correct": False}
    reported = {v["name"]: v for v in answer.get("values", [])}
    results: dict[str, Any] = {}
    mistakes: set[str] = set()
    correct = 0
    for name, s in spec.items():
        r = reported.get(name)
        if r is None:
            results[name] = {"status": "missing", "expected": s["value"]}
            continue
        got = float(r["value"])
        if _close(got, s["value"], s.get("rel_tol", 0.001), s.get("abs_tol", 0.0)):
            results[name] = {"status": "correct", "got": got, "expected": s["value"]}
            correct += 1
            continue
        matched = [m for m, vals in expected.get("variants", {}).items()
                   if name in vals and _close(got, vals[name], s.get("rel_tol", 0.001), s.get("abs_tol", 0.0))]
        results[name] = {"status": "wrong", "got": got, "expected": s["value"], "explained_by": matched}
        mistakes |= set(matched)
    text = " ".join(answer.get("open_issues", []) + [answer.get("summary", "")]).lower()
    issues = {i["id"]: any(k in text for k in i["any_of"]) for i in expected.get("required_open_issues", [])}
    total = len(spec)
    return {
        "score": round(correct / total, 4) if total else 0.0,
        "correct": correct, "total": total, "all_correct": correct == total,
        "values": results, "mistakes": sorted(mistakes), "open_issues": issues,
        "open_issues_reported": sum(issues.values()), "open_issues_required": len(issues),
    }
