"""Independent reference solution for the heatwave-days example (used only for grading).

Run:  uv run python examples/heatwave-days/reference/solution.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

HERE = Path(__file__).resolve().parent
MATERIALS = HERE.parent / "materials"
OUT = HERE.parent / "expected" / "heatwave-days.json"
CITY = (31.23, 121.47)


def runs(qualifying: np.ndarray, min_len: int = 3) -> list[int]:
    """Lengths of runs of True of at least ``min_len`` (False and NaN days break runs)."""
    out, n = [], 0
    for q in list(qualifying) + [False]:
        if q:
            n += 1
        else:
            if n >= min_len:
                out.append(n)
            n = 0
    return out


def count(series: pd.Series, threshold: float, strict: bool = False, min_len: int = 3,
          drop_missing_first: bool = False) -> dict[int, tuple[int, int]]:
    out = {}
    for year in (2021, 2022):
        s = series[series.index.year == year]
        if drop_missing_first:
            s = s.dropna()
        q = (s > threshold) if strict else (s >= threshold)
        q = q & s.notna()
        r = runs(q.to_numpy(), min_len)
        out[year] = (sum(r), len(r))
    return out


def main() -> None:
    ds = xr.open_dataset(MATERIALS / "tasmax_city.nc")
    da = ds["tasmax"]
    cell = da.sel(lat=CITY[0], lon=CITY[1], method="nearest")
    celsius = (cell - 273.15).to_series()
    correct = count(celsius, 35.0)
    values = {}
    for y in (2021, 2022):
        values[f"hw_days_{y}"] = correct[y][0]
        values[f"hw_events_{y}"] = correct[y][1]

    def flat(res: dict[int, tuple[int, int]]) -> dict[str, int]:
        return {k: v for y in (2021, 2022) for k, v in ((f"hw_days_{y}", res[y][0]), (f"hw_events_{y}", res[y][1]))}

    area_mean = (da.mean(dim=("lat", "lon")) - 273.15).to_series()
    kelvin = cell.to_series()
    variants = {
        "kelvin_compared_with_celsius_threshold": flat(count(kelvin, 35.0)),
        "grid_cells_averaged": flat(count(area_mean, 35.0)),
        "run_length_rule_ignored": flat(count(celsius, 35.0, min_len=1)),
        "missing_days_dropped_before_counting_runs": flat(count(celsius, 35.0, drop_missing_first=True)),
    }
    for (a, b) in ((0, 1), (1, 0), (1, 1)):
        other = (da.isel(lat=a, lon=b) - 273.15).to_series()
        variants[f"wrong_grid_cell_{a}{b}"] = flat(count(other, 35.0))
    expected = {
        "task": "heatwave-days",
        "values": {k: {"value": v, "rel_tol": 0.0, "abs_tol": 0} for k, v in values.items()},
        "variants": variants,
        "required_open_issues": [],
        "notes": "Nearest cell to 31.23N 121.47E is lat 31.0, lon 121.25. Threshold 35.0 degC applied to kelvin data "
                 "after conversion; a missing day breaks a run.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(expected, indent=2))
    print(json.dumps(expected, indent=2))


if __name__ == "__main__":
    main()
