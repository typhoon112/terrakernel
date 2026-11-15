"""NetCDF ingest: dimensions, coordinates, variables and their self-describing metadata.

NetCDF files carry documentation inside them (``units``, ``long_name``,
``standard_name``, ``cell_methods``, ``_FillValue``, global attributes, CF time bounds).
These attributes are *stated by the file* and recorded as such; statistics are measured
on (a subsample of) the data. Large arrays are never loaded in full.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

from terrakernel.ingest.common import EvidenceBuilder
from terrakernel.models import Evidence, EvidenceKind, Locator, Source

MAX_SAMPLE = 2_000_000
ATTR_KEYS = ("units", "long_name", "standard_name", "cell_methods", "comment", "description", "valid_min", "valid_max",
             "valid_range", "scale_factor", "add_offset", "calendar", "bounds", "axis", "positive", "coordinates",
             "grid_mapping", "missing_value", "_FillValue")
GLOBAL_KEYS = ("title", "summary", "institution", "source", "references", "Conventions", "comment", "history",
               "time_coverage_start", "time_coverage_end", "geospatial_lat_min", "geospatial_lat_max",
               "geospatial_lon_min", "geospatial_lon_max", "license")


def _open(path: Path) -> tuple[xr.Dataset, bool]:
    try:
        return xr.open_dataset(path, decode_times=True, mask_and_scale=True), True
    except (ValueError, TypeError, OverflowError):
        return xr.open_dataset(path, decode_times=False, mask_and_scale=True), False


def _attrs(obj: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    out = {}
    enc = getattr(obj, "encoding", {}) or {}
    for k in keys:
        v = obj.attrs.get(k, enc.get(k))
        if v is None:
            continue
        if isinstance(v, np.generic):
            v = v.item()
        elif isinstance(v, np.ndarray):
            v = v.tolist()
        text = str(v)
        out[k] = v if len(text) <= 400 else text[:400] + "..."
    return out


def _sample(da: xr.DataArray) -> np.ndarray:
    if da.size <= MAX_SAMPLE:
        return np.asarray(da.values).ravel()
    step = int(np.ceil((da.size / MAX_SAMPLE) ** (1 / max(1, da.ndim))))
    return np.asarray(da.isel({d: slice(None, None, step) for d in da.dims}).values).ravel()


def _fmt(v: Any) -> str:
    if isinstance(v, float | np.floating):
        return "NA" if np.isnan(v) else f"{v:.6g}"
    return str(v)


def ingest_netcdf(source: Source, path: Path, assets_dir: Path) -> list[Evidence]:
    ds, times_decoded = _open(path)
    b = EvidenceBuilder(source.id)
    try:
        gattrs = _attrs(ds, GLOBAL_KEYS)
        dims = {k: int(v) for k, v in ds.sizes.items()}
        var_ids, fields, time_coords = [], [], []
        # coordinates
        for name, coord in ds.coords.items():
            name = str(name)
            meta: dict[str, Any] = {"column": name, "role": "coordinate", "dims": list(coord.dims),
                                    "dtype": str(coord.dtype), "attributes": _attrs(coord, ATTR_KEYS)}
            lines = [f"Coordinate `{name}` in {source.path}: dims {list(coord.dims)}, dtype {coord.dtype}, size {coord.size}"]
            vals = np.asarray(coord.values).ravel()
            if np.issubdtype(coord.dtype, np.datetime64) and vals.size:
                time_coords.append(name)
                diffs = np.diff(vals.astype("datetime64[s]").astype(np.int64)) if vals.size > 1 else np.array([])
                step = int(np.median(diffs)) if diffs.size else None
                meta["datetime"] = {"min": str(vals.min()), "max": str(vals.max()),
                                    "resolution_seconds": step,
                                    "irregular_steps": int((diffs != step).sum()) if diffs.size else 0}
                lines.append(f"- time range {vals.min()} .. {vals.max()}, typical step {step} s"
                             + (f", irregular steps {meta['datetime']['irregular_steps']}" if diffs.size else ""))
                bounds = coord.attrs.get("bounds")
                lines.append(f"- bounds variable: {bounds!r}" if bounds else
                             "- no bounds variable: whether a time stamp marks the start, middle or end of its "
                             "interval is not stated by the file")
            elif vals.size and np.issubdtype(coord.dtype, np.number):
                lines.append(f"- range {_fmt(np.nanmin(vals))} .. {_fmt(np.nanmax(vals))}")
                if vals.size > 1:
                    d = np.diff(vals)
                    meta["spacing"] = _fmt(float(np.median(d)))
                    lines.append(f"- typical spacing {meta['spacing']}")
            if not times_decoded and "since" in str(coord.attrs.get("units", "")):
                lines.append(f"- times could not be decoded (units {coord.attrs.get('units')!r}, calendar "
                             f"{coord.attrs.get('calendar', 'unspecified')!r})")
            for k, v in meta["attributes"].items():
                lines.append(f"- attribute {k}: {v}")
            ev = b.add(EvidenceKind.variable, "\n".join(lines), Locator(column=name, symbol="coordinate"),
                       f"coord/{name}", meta=meta)
            var_ids.append(ev.id)
            fields.append(meta)
        # data variables
        for name, da in ds.data_vars.items():
            name = str(name)
            attrs = _attrs(da, ATTR_KEYS)
            meta = {"column": name, "role": "variable", "dims": list(da.dims), "shape": list(da.shape),
                    "dtype": str(da.dtype), "attributes": attrs}
            lines = [f"Variable `{name}` in {source.path}: dims {list(da.dims)}, shape {list(da.shape)}, dtype {da.dtype}"]
            for k, v in attrs.items():
                lines.append(f"- attribute {k}: {v}  (stated in the file)")
            if "units" not in attrs:
                lines.append("- no units attribute: the unit is not stated by the file")
            if np.issubdtype(da.dtype, np.number):
                vals = _sample(da).astype(float)
                n = vals.size
                nan = int(np.isnan(vals).sum())
                meta["missing_fraction"] = round(nan / n, 6) if n else 0.0
                finite = vals[~np.isnan(vals)]
                if finite.size:
                    stats = {"min": float(finite.min()), "max": float(finite.max()), "mean": float(finite.mean()),
                             "p01": float(np.quantile(finite, 0.01)), "p99": float(np.quantile(finite, 0.99))}
                    meta.update(stats)
                    lines.append("- min {min} | p01 {p01} | mean {mean} | p99 {p99} | max {max}".format(
                        **{k: _fmt(v) for k, v in stats.items()}) + (" (on a subsample)" if da.size > MAX_SAMPLE else ""))
                lines.append(f"- missing (masked) fraction: {meta['missing_fraction']}")
            ev = b.add(EvidenceKind.variable, "\n".join(lines), Locator(column=name, symbol="variable"), f"var/{name}",
                       meta=meta)
            var_ids.append(ev.id)
            fields.append(meta)
        summary = [f"NetCDF file {source.path}: dimensions " + ", ".join(f"{k}={v}" for k, v in dims.items()) + ".",
                   "Data variables: " + ", ".join(f"`{v}`" for v in ds.data_vars),
                   "Coordinates: " + ", ".join(f"`{c}`" for c in ds.coords)]
        for k, v in gattrs.items():
            summary.append(f"Global attribute {k}: {v}")
        profile = b.add(EvidenceKind.dataset_profile, "\n".join(summary), Locator(), "profile", related=var_ids,
                        meta={"format": "netcdf", "dims": dims, "global_attributes": gattrs,
                              "columns": [f["column"] for f in fields], "time_columns": time_coords,
                              "fields": fields, "times_decoded": times_decoded})
        b.items.remove(profile)
        b.items.insert(0, profile)
    finally:
        ds.close()
    return b.items
