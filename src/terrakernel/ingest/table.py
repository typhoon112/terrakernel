"""Tabular ingest (CSV/TSV): a dataset profile plus one evidence unit per column.

Everything here is *measured* from the data. Units are never decided from the data:
a unit-like token in a column name is recorded only as a hypothesis (``unit_hint``),
because the authoritative unit has to come from documentation.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from terrakernel.ingest.common import EvidenceBuilder
from terrakernel.models import Evidence, EvidenceKind, Locator, Source

MAX_ROWS = 2_000_000

# Generic unit tokens that may appear in column names (domain-agnostic, SI and common).
UNIT_TOKENS = [
    "gwh", "mwh", "kwh", "wh", "gw", "mw", "kw", "w", "kva", "mva", "kv", "v", "a", "ma",
    "m/s", "km/h", "mps", "degc", "degf", "celsius", "kelvin", "k", "pa", "hpa", "kpa", "mpa", "bar",
    "mm", "cm", "m", "km", "m2", "km2", "ha", "m3", "l", "kg", "g", "t", "mt", "gt",
    "ppm", "ppb", "pct", "percent", "%", "usd", "eur", "cny", "s", "min", "h", "hr", "d", "j", "kj", "mj", "gj",
]
_UNIT_RE = re.compile(r"(?:^|[_\-\s\(\[])(" + "|".join(re.escape(u) for u in sorted(UNIT_TOKENS, key=len, reverse=True)) + r")(?:$|[_\-\s\)\]])", re.I)


def _unit_hint(name: str) -> str | None:
    m = _UNIT_RE.search(name.strip())
    return m.group(1) if m else None


MAX_SHEETS = 20


def read_frames(path: Path) -> list[tuple[str | None, pd.DataFrame]]:
    """Read a tabular file into (sheet name or None, frame) pairs."""
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm", ".xls"):
        sheets = pd.read_excel(path, sheet_name=None, nrows=MAX_ROWS)
        return [(str(name), df) for name, df in list(sheets.items())[:MAX_SHEETS]]
    if suffix == ".parquet":
        return [(None, pd.read_parquet(path))]
    sep = "\t" if suffix == ".tsv" else None
    if sep is None:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            sample = f.read(20000)
        try:
            sep = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            sep = ","
    return [(None, pd.read_csv(path, sep=sep, nrows=MAX_ROWS, low_memory=False, comment=None))]


def _fmt(v: Any) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "NA"
    if isinstance(v, float | np.floating):
        return f"{v:.6g}"
    return str(v)


def _datetime_profile(raw: pd.Series) -> dict[str, Any] | None:
    sample = raw.dropna().astype(str).head(200)
    if sample.empty:
        return None
    if not sample.str.contains(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|T\d{2}:", regex=True).mean() > 0.8:
        return None
    parsed = pd.to_datetime(raw, errors="coerce", utc=False, format="mixed")
    if parsed.notna().mean() < 0.9:
        return None
    s = raw.dropna().astype(str)
    tz_suffix = s.str.extract(r"(Z|[+-]\d{2}:?\d{2})$")[0].dropna().unique().tolist()
    out: dict[str, Any] = {
        "min": str(parsed.min()),
        "max": str(parsed.max()),
        "timezone_suffixes": tz_suffix[:5],
        "has_timezone": bool(tz_suffix),
    }
    p = parsed.dropna()
    if p.dt.tz is not None:
        p = p.dt.tz_convert("UTC")
    p = p.sort_values()
    diffs = p.diff().dropna()
    if not diffs.empty:
        mode = diffs.mode().iloc[0]
        out["resolution"] = str(mode)
        out["duplicates"] = int(p.duplicated().sum())
        if mode > pd.Timedelta(0):
            expected = int((p.iloc[-1] - p.iloc[0]) / mode) + 1
            out["expected_steps"] = expected
            out["missing_steps"] = max(0, expected - int(p.nunique()))
        out["irregular_steps"] = int((diffs != mode).sum())
    return out


def ingest_table(source: Source, path: Path, assets_dir: Path) -> list[Evidence]:
    b = EvidenceBuilder(source.id)
    for sheet, df in read_frames(path):
        _profile_frame(b, source, df, sheet)
    return b.items


def _profile_frame(b: EvidenceBuilder, source: Source, df: pd.DataFrame, sheet: str | None) -> None:
    from terrakernel.util import slugify

    prefix = f"sheet/{slugify(sheet, 40)}/" if sheet is not None else ""
    where = f"{source.path}" + (f" (sheet {sheet!r})" if sheet is not None else "")
    n_rows, n_cols = df.shape
    col_ids: list[str] = []
    profiles: list[dict[str, Any]] = []
    time_cols: list[str] = []
    start = len(b.items)
    for col in df.columns:
        s = df[col]
        name = str(col)
        prof: dict[str, Any] = {"column": name, "dtype": str(s.dtype), "missing": int(s.isna().sum()),
                                "missing_fraction": round(float(s.isna().mean()), 6) if n_rows else 0.0}
        lines = [f"Column `{name}` in {where}", f"- pandas dtype: {s.dtype}",
                 f"- missing values: {prof['missing']} of {n_rows}"]
        hint = _unit_hint(name)
        if hint:
            prof["unit_hint"] = hint
            lines.append(f"- the column name contains the unit-like token '{hint}' (hypothesis only; not confirmed by documentation)")
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            v = s.astype(float)
            stats = {
                "min": v.min(), "max": v.max(), "mean": v.mean(), "std": v.std(),
                "p01": v.quantile(0.01), "p50": v.quantile(0.5), "p99": v.quantile(0.99),
                "zeros": int((v == 0).sum()), "negatives": int((v < 0).sum()),
            }
            prof.update({k: (float(x) if isinstance(x, float | np.floating) else x) for k, x in stats.items()})
            lines.append(
                "- min {min} | p01 {p01} | median {p50} | mean {mean} | p99 {p99} | max {max} | std {std}".format(
                    **{k: _fmt(x) for k, x in stats.items()}
                )
            )
            lines.append(f"- zeros: {stats['zeros']}, negative values: {stats['negatives']}")
        else:
            dt = _datetime_profile(s) if not pd.api.types.is_datetime64_any_dtype(s) else _datetime_profile(s.astype(str))
            if dt:
                time_cols.append(name)
                prof["datetime"] = dt
                lines.append(f"- parsed as timestamps: {dt['min']} .. {dt['max']}")
                if "resolution" in dt:
                    lines.append(
                        f"- most common step {dt['resolution']}; missing steps {dt.get('missing_steps', 'NA')}; "
                        f"duplicate timestamps {dt.get('duplicates', 0)}; irregular steps {dt.get('irregular_steps', 0)}"
                    )
                lines.append(
                    f"- timezone suffixes present: {', '.join(dt['timezone_suffixes']) or 'none (naive timestamps)'}"
                )
                lines.append("- whether a timestamp marks the start or the end of its interval cannot be measured from the data")
            else:
                uniq = int(s.nunique(dropna=True))
                prof["unique"] = uniq
                top = s.dropna().astype(str).value_counts().head(5)
                prof["top_values"] = {k: int(c) for k, c in top.items()}
                lines.append(f"- distinct values: {uniq}; most frequent: " + ", ".join(f"{k} ({c})" for k, c in top.items()))
        examples = [_fmt(x) for x in s.dropna().head(3).tolist()]
        lines.append(f"- first values: {', '.join(examples)}")
        ev = b.add(EvidenceKind.table_column, "\n".join(lines), Locator(column=name, section=sheet),
                   f"{prefix}col/{name}", meta=prof)
        col_ids.append(ev.id)
        profiles.append(prof)

    head = df.head(5).to_csv(index=False).strip()
    summary = [f"Dataset {where}: {n_rows} rows x {n_cols} columns.",
               "Columns: " + ", ".join(f"`{c}`" for c in df.columns)]
    if time_cols:
        dt = next(p["datetime"] for p in profiles if p["column"] == time_cols[0])
        summary.append(f"Time column `{time_cols[0]}` spans {dt['min']} .. {dt['max']} with step {dt.get('resolution', 'NA')}.")
    summary.append("First rows:\n" + head)
    profile_ev = b.add(
        EvidenceKind.dataset_profile, "\n".join(summary), Locator(section=sheet), f"{prefix}profile", related=col_ids,
        meta={"rows": n_rows, "columns": [str(c) for c in df.columns], "time_columns": time_cols, "sheet": sheet},
    )
    b.items.remove(profile_ev)
    b.items.insert(start, profile_ev)
