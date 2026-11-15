"""Generate the heatwave-days development corpus (a second, unrelated domain).

Synthetic data and self-authored documents with planted pitfalls:

- the NetCDF file stores daily maximum temperature in kelvin, while the agency definition
  uses a threshold in degrees Celsius;
- the file covers a 2x2 grid; the definition asks for the cell nearest to the city centre;
- a heatwave day must belong to a run of at least three consecutive days at or above the
  threshold, and a missing day breaks a run;
- a paper proposes a different, percentile-based definition (conflict);
- the legacy script compares kelvin values with 35, averages the grid, and ignores runs.

Run:  uv run python examples/heatwave-days/make_materials.py
"""

from __future__ import annotations

import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Table, TableStyle  # noqa: E402

HERE = Path(__file__).resolve().parent
MATERIALS = HERE / "materials"
SEED = 7
THRESHOLD_K = 273.15 + 35.0
LATS = [31.0, 31.5]
LONS = [121.25, 121.75]


def make_tasmax(rng: np.random.Generator) -> xr.Dataset:
    days = pd.date_range("2021-01-01", "2022-12-31", freq="D")
    n = len(days)
    doy = days.day_of_year.to_numpy()
    seasonal = 289.0 + 13.5 * np.cos(2 * np.pi * (doy - 200) / 365.25)
    noise = np.zeros(n)
    for i in range(1, n):
        noise[i] = 0.7 * noise[i - 1] + rng.normal(0, 1.6)
    base = seasonal + noise
    # planted summer episodes (kelvin): long runs, short runs, and a run split by a missing day
    episodes = {
        "2021-07-10": [309.4, 310.2, 311.0, 310.1],          # 4-day heatwave
        "2021-07-25": [309.0, 309.6],                        # 2 days only: not a heatwave
        "2021-08-05": [309.2, 310.0, 309.5, 311.2, 310.4],   # 5-day heatwave
        "2021-08-20": [309.3, 309.9, np.nan, 309.8, 310.6],  # 2 + 2 split by a missing day: none
        "2022-07-03": [308.9, 309.7, 310.5],                 # 3-day heatwave
        "2022-07-18": [309.1, 310.8, 311.6, 312.0, 311.1, 310.3],  # 6-day heatwave
        "2022-08-09": [309.5, 309.2],                        # 2 days only
        "2022-08-15": [308.7, 309.9, 310.1, 309.4],          # 4-day heatwave
        # just below 35.0 degC in the city cell; warmer cells and the area mean cross the threshold
        "2021-06-21": [307.70, 307.85, 307.90],
        "2022-06-24": [307.75, 307.95, 307.80, 307.70],
        "2022-09-02": [307.80, 307.90, 307.75],
    }
    city = base.copy()
    planted = np.zeros(n, dtype=bool)
    for start, vals in episodes.items():
        i0 = days.get_loc(pd.Timestamp(start))
        city[i0 - 1] = min(city[i0 - 1], 305.5)  # isolate each episode with a cooler day
        city[i0 + len(vals)] = min(city[i0 + len(vals)], 305.5)
        for k, v in enumerate(vals):
            city[i0 + k] = v
            planted[i0 + k] = True
    # keep every other day clearly below the threshold, and no value near it
    other = ~planted & ~np.isnan(city)
    city[other] = np.minimum(city[other], THRESHOLD_K - 0.6)
    city = np.where(np.abs(city - THRESHOLD_K) < 0.05, city - 0.1, city)
    # the other three cells are warmer or cooler: an area mean or a wrong cell changes the answer
    offsets = np.array([[0.0, 1.4], [-1.1, 2.3]])
    data = np.empty((n, 2, 2))
    for a in range(2):
        for b in range(2):
            data[:, a, b] = city + offsets[a, b] + rng.normal(0, 0.3, n) * (offsets[a, b] != 0)
    data[:, 0, 0] = city
    data = np.round(data, 2)
    bounds = np.stack([days.to_numpy(), (days + pd.Timedelta(days=1)).to_numpy()], axis=1)
    ds = xr.Dataset(
        {
            "tasmax": (("time", "lat", "lon"), data.astype("float64"), {
                "units": "K", "standard_name": "air_temperature",
                "long_name": "Daily maximum near-surface air temperature", "cell_methods": "time: maximum"}),
            "time_bnds": (("time", "nv"), bounds),
        },
        coords={
            "time": ("time", days, {"bounds": "time_bnds", "axis": "T"}),
            "lat": ("lat", LATS, {"units": "degrees_north", "standard_name": "latitude"}),
            "lon": ("lon", LONS, {"units": "degrees_east", "standard_name": "longitude"}),
        },
        attrs={"title": "Daily maximum temperature, downscaled reanalysis (synthetic)",
               "Conventions": "CF-1.8", "institution": "City Climate Office (fictional)",
               "comment": "Synthetic data for testing analysis tooling."},
    )
    enc = {"tasmax": {"_FillValue": -9999.0}, "time": {"units": "days since 2021-01-01", "calendar": "standard"}}
    ds.attrs["_encoding"] = "see to_netcdf"
    del ds.attrs["_encoding"]
    return ds, enc


DEFINITION = """# Heat-health warning definition (City Climate Office)

This note defines how the City Climate Office counts heatwave days for annual heat-health
reports. All data in this folder are synthetic and exist only to test analysis tooling.

## Definition

A **heatwave day** is any day that belongs to a run of at least three consecutive days on
which the daily maximum near-surface air temperature is at or above **35.0 °C**.

A **heatwave event** is one such run; a run of N qualifying days is one event of N heatwave days.

A day with missing data is not a qualifying day and breaks a run.

## Location and period

Use the grid cell of `tasmax_city.nc` nearest to the city centre at 31.23° N, 121.47° E.
Do not average neighbouring cells.

Counts are reported per calendar year, using the date of each daily record.

## Worked example

For daily maxima of 34.0, 36.2, 37.1, 35.0, 30.5, 36.0 and 36.4 °C, the second to fourth days
form a run of three days at or above 35.0 °C, while the sixth and seventh days form a run of only
two days. The heatwave day count is therefore 3, and there is 1 heatwave event.
"""


LEGACY = '''"""Count hot days per year (legacy script from the 2019 heat report)."""

import xarray as xr

THRESHOLD = 35


def hot_days(path, year):
    """Number of days in `year` with maximum temperature above THRESHOLD."""
    ds = xr.open_dataset(path)
    t = ds["tasmax"].sel(time=str(year)).mean(dim=("lat", "lon"))
    return int((t > THRESHOLD).sum())


if __name__ == "__main__":
    for year in (2021, 2022):
        print(year, hot_days("tasmax_city.nc", year))
'''


def _fonts() -> dict:
    ttf = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    pdfmetrics.registerFont(TTFont("DejaVu", str(ttf / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(ttf / "DejaVuSans-Bold.ttf")))
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=ss["Title"], fontName="DejaVu-Bold", fontSize=15, leading=19),
        "authors": ParagraphStyle("a", parent=ss["Normal"], fontName="DejaVu", fontSize=9.5, alignment=1, spaceAfter=10),
        "h": ParagraphStyle("h", parent=ss["Heading2"], fontName="DejaVu-Bold", fontSize=11.5, spaceBefore=8, spaceAfter=4),
        "p": ParagraphStyle("p", parent=ss["Normal"], fontName="DejaVu", fontSize=9.5, leading=12.5, spaceAfter=5),
        "eq": ParagraphStyle("eq", parent=ss["Normal"], fontName="DejaVu", fontSize=10, leading=14, alignment=1,
                             spaceBefore=3, spaceAfter=6),
        "cap": ParagraphStyle("c", parent=ss["Normal"], fontName="DejaVu", fontSize=8.5, leading=11, spaceAfter=8),
    }


def _figure() -> io.BytesIO:
    x = np.arange(1, 13)
    fig, ax = plt.subplots(figsize=(5.2, 2.3), dpi=150)
    ax.bar(x, [0, 0, 0, 0, 1, 4, 9, 8, 2, 0, 0, 0], color="#b5502c")
    ax.set_xlabel("Month")
    ax.set_ylabel("Heatwave days")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf


def write_paper(path: Path) -> None:
    s = _fonts()
    table = Table([["Day", "T_max (°C)", "P90 (°C)", "Exceeds"], ["1", "33.1", "32.0", "yes"], ["2", "33.5", "32.2", "yes"],
                   ["3", "32.4", "32.3", "yes"], ["4", "31.9", "32.3", "no"], ["5", "34.0", "32.4", "yes"]])
    table.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), "DejaVu-Bold", 8.5), ("FONT", (0, 1), (-1, -1), "DejaVu", 8.5),
                               ("LINEABOVE", (0, 0), (-1, 0), 0.8, "black"), ("LINEBELOW", (0, 0), (-1, 0), 0.5, "black"),
                               ("LINEBELOW", (0, -1), (-1, -1), 0.8, "black"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    story = [
        Paragraph("Relative Thresholds for Comparable Heatwave Statistics", s["title"]),
        Paragraph("K. Osei and Y. Lin. Demonstration material written for TerraKernel; not a published paper.", s["authors"]),
        Paragraph("1 Motivation", s["h"]),
        Paragraph("Absolute thresholds such as 35 °C are not comparable across climates: a cool city may never reach "
                  "them, while a hot city exceeds them every summer. We therefore define heatwaves relative to local "
                  "climatology.", s["p"]),
        Paragraph("2 Definition", s["h"]),
        Paragraph("Let T<sub>d</sub> be the daily maximum temperature and P90<sub>d</sub> the 90th percentile of daily "
                  "maxima for the same calendar day in the 1991–2020 reference period, computed from a 15-day window. "
                  "A heatwave day is a day in a run of at least three consecutive days with", s["p"]),
        Paragraph("T<sub>d</sub> &gt; P90<sub>d</sub>", s["eq"]),
        Paragraph("3 Worked example", s["h"]),
        Paragraph("In Table 1, days 1 to 3 exceed their percentile thresholds and form a heatwave of 3 days; day 5 exceeds "
                  "its threshold but is not part of a run of three days.", s["p"]),
        table,
        Paragraph("Table 1: Worked example for the percentile-based definition.", s["cap"]),
        Paragraph("4 Results", s["h"]),
        Paragraph("Under this definition, heatwave days concentrate in July and August (Figure 1).", s["p"]),
        Image(_figure(), width=12 * cm, height=5.3 * cm),
        Paragraph("Figure 1: Heatwave days per month for an illustrative city.", s["cap"]),
    ]
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2 * cm,
                      bottomMargin=2 * cm, title="Relative Thresholds", author="TerraKernel demo material").build(story)


def main() -> None:
    MATERIALS.mkdir(parents=True, exist_ok=True)
    ds, enc = make_tasmax(np.random.default_rng(SEED))
    ds.to_netcdf(MATERIALS / "tasmax_city.nc", encoding=enc)
    (MATERIALS / "heat_definition.md").write_text(DEFINITION)
    (MATERIALS / "count_hot_days.py").write_text(LEGACY)
    write_paper(MATERIALS / "paper_relative_heatwaves.pdf")
    print("materials written to", MATERIALS)


if __name__ == "__main__":
    main()
