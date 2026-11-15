"""Generate the wind-forecast-evaluation development corpus.

This corpus is a *test fixture* for TerraKernel: fully synthetic data and two short
self-authored "papers" with deliberately planted pitfalls:

- model A reports MW with interval-beginning timestamps; measurements use interval-ending;
- model B reports kW (stated only in the documentation) and its issue time is undocumented;
- the two papers define NRMSE with different denominators (capacity vs mean measured power);
- installed capacity changes on an effective date given in the data description;
- the legacy evaluation script assumes a constant capacity and fills missing values with 0;
- the three series have different missing timestamps.

Run:  uv run python examples/wind-forecast-eval/make_materials.py
"""

from __future__ import annotations

import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Table, TableStyle  # noqa: E402

HERE = Path(__file__).resolve().parent
MATERIALS = HERE / "materials"
SEED = 20231101

CAPACITY_CHANGE = "2023-07-01T00:00:00Z"  # effective date of the expansion (documented)
CAP_BEFORE_MW = 100.0
CAP_AFTER_MW = 120.0


def power_curve(ws: np.ndarray) -> np.ndarray:
    """Normalised turbine power curve (0..1): cut-in 3, rated 12, cut-out 25 m/s."""
    p = np.clip((ws - 3.0) / (12.0 - 3.0), 0, 1) ** 3
    p[(ws < 3.0) | (ws >= 25.0)] = 0.0
    return p


def capacity_at(ts: pd.DatetimeIndex, change: str = CAPACITY_CHANGE) -> np.ndarray:
    return np.where(ts >= pd.Timestamp(change), CAP_AFTER_MW, CAP_BEFORE_MW)


def make_series(rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    # Interval-ending hourly stamps for 2023 (value at t = mean over (t-1h, t]).
    end_ts = pd.date_range("2023-01-01T01:00:00Z", "2024-01-01T00:00:00Z", freq="1h")
    n = len(end_ts)
    hours = np.arange(n)
    seasonal = 1.0 + 0.25 * np.cos(2 * np.pi * (hours / 24 - 15) / 365.25)
    diurnal = 1.0 + 0.08 * np.sin(2 * np.pi * (hours % 24 - 9) / 24)
    z = np.zeros(n)
    for i in range(1, n):
        z[i] = 0.97 * z[i - 1] + rng.normal(0, 0.24)
    ws = np.clip(7.2 * seasonal * diurnal * np.exp(0.42 * z), 0, 30)
    cap = capacity_at(end_ts - pd.Timedelta(hours=1))  # capacity valid at the start of each hour
    measured = np.clip(cap * power_curve(ws) + rng.normal(0, 0.8, n), 0, cap)

    def forecast(err_std: float, bias: float, rho: float) -> np.ndarray:
        e = np.zeros(n)
        for i in range(1, n):
            e[i] = rho * e[i - 1] + rng.normal(0, err_std * np.sqrt(1 - rho**2))
        return np.clip(cap * power_curve(np.clip(ws + bias + e, 0, 30)), 0, cap)

    fa = forecast(1.55, 0.0, 0.85)
    fb = forecast(1.30, 0.35, 0.80)

    meas = pd.DataFrame({"timestamp": end_ts, "power_mw": measured.round(3)})
    # sensor outage: 30 hours of missing measurements in March, 6 isolated gaps
    meas.loc[1600:1629, "power_mw"] = np.nan
    for k in (2100, 4555, 5003, 6100, 7020, 8001):
        meas.loc[k, "power_mw"] = np.nan

    # Model A: same intervals, but labelled with the interval *beginning*; 48 rows absent.
    a = pd.DataFrame({"timestamp": end_ts - pd.Timedelta(hours=1), "forecast_mw": fa.round(3)})
    a = a.drop(index=range(5200, 5248)).reset_index(drop=True)

    # Model B: interval-ending labels, values in kW, NaN gaps elsewhere.
    b = pd.DataFrame({"time": end_ts, "p_forecast": (fb * 1000).round(1)})
    b.loc[3000:3023, "p_forecast"] = np.nan
    b.loc[7300:7311, "p_forecast"] = np.nan
    return {"measured": meas, "a": a, "b": b}


def write_csvs(series: dict[str, pd.DataFrame]) -> None:
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    m = series["measured"].copy()
    m["timestamp"] = m["timestamp"].dt.strftime(fmt)
    m.to_csv(MATERIALS / "measured_power.csv", index=False)
    a = series["a"].copy()
    a["timestamp"] = a["timestamp"].dt.strftime(fmt)
    a.to_csv(MATERIALS / "forecast_model_a.csv", index=False)
    b = series["b"].copy()
    b["time"] = b["time"].dt.strftime(fmt)
    b.to_csv(MATERIALS / "forecast_model_b.csv", index=False)


DATA_DESCRIPTION = f"""# Farm Delta wind measurement and forecast data

Prepared by the Wind Analytics Group for the 2023 forecast benchmarking study.
All data in this folder are synthetic and exist only to exercise analysis tooling.

## Site

Farm Delta is an onshore wind farm. Its installed capacity changed once during 2023:

| Valid from (UTC) | Installed capacity |
|---|---|
| 2023-01-01T00:00:00Z | {CAP_BEFORE_MW:.0f} MW |
| {CAPACITY_CHANGE} | {CAP_AFTER_MW:.0f} MW |

The capacity valid at an instant is the most recent entry whose "valid from" is not later than that instant. An hourly value uses the capacity valid at the **start** of its hour; for example, the hour ending 2023-07-01T00:00:00Z still belongs to the 100 MW period.

## Files

All three files cover calendar year 2023 in UTC at hourly resolution.

### measured_power.csv

- `timestamp`: UTC, ISO 8601. Each value is the **mean active power over the hour ending at the timestamp** (interval-ending convention).
- `power_mw`: measured active power in MW.
- Missing measurements are left empty. They must not be filled or interpolated for evaluation.

### forecast_model_a.csv

Day-ahead forecast from the in-house model A, issued daily at 12:00 UTC for the following day.

- `timestamp`: UTC, ISO 8601. Each value refers to the **hour beginning at the timestamp** (interval-beginning convention), which differs from the measurement file.
- `forecast_mw`: forecast mean active power in MW.

### forecast_model_b.csv

Forecast purchased from vendor B.

- `time`: UTC, ISO 8601, interval-ending convention (same as the measurements).
- `p_forecast`: forecast mean active power in **kW**.

The vendor did not state when its forecasts were issued, so the forecast lead time of model B is unknown.

## Evaluation convention

The group reports forecast errors as NRMSE normalised by the installed capacity valid at each timestamp, as defined in Paper A (Section 2), expressed in percent. MAE and RMSE are reported in MW.

Models are compared on common valid samples only: an hour is used when the measurement and every compared forecast are available for that hour after aligning the timestamp conventions. Missing values must not be imputed.
"""


LEGACY_SCRIPT = '''"""Evaluate a wind power forecast against measurements (legacy group script, 2021)."""

import numpy as np
import pandas as pd

CAPACITY_MW = 100.0


def load(path, time_col, value_col):
    df = pd.read_csv(path, parse_dates=[time_col])
    return df.rename(columns={time_col: "timestamp", value_col: "value"})


def mae(forecast, measured):
    """Mean absolute error in the unit of the inputs."""
    return float(np.mean(np.abs(forecast - measured)))


def rmse(forecast, measured):
    """Root mean square error in the unit of the inputs."""
    return float(np.sqrt(np.mean((forecast - measured) ** 2)))


def nrmse(forecast, measured, capacity=CAPACITY_MW):
    """RMSE normalised by installed capacity, in percent."""
    return rmse(forecast, measured) / capacity * 100.0


def evaluate(forecast_csv, measured_csv, forecast_cols=("timestamp", "forecast_mw")):
    fc = load(forecast_csv, *forecast_cols)
    ms = load(measured_csv, "timestamp", "power_mw")
    df = fc.merge(ms, on="timestamp", suffixes=("_f", "_m"))
    df = df.fillna(0)
    f, m = df["value_f"].to_numpy(), df["value_m"].to_numpy()
    return {"mae": mae(f, m), "rmse": rmse(f, m), "nrmse": nrmse(f, m), "n": len(df)}


if __name__ == "__main__":
    print(evaluate("forecast_model_a.csv", "measured_power.csv"))
'''


def _register_fonts() -> None:
    """Use DejaVu Sans (bundled with matplotlib) so Greek letters and math symbols are real Unicode."""
    ttf = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    pdfmetrics.registerFont(TTFont("DejaVu", str(ttf / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(ttf / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold", italic="DejaVu", boldItalic="DejaVu-Bold")


def _styles():
    _register_fonts()
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=ss["Title"], fontName="DejaVu-Bold", fontSize=15, leading=19, spaceAfter=6),
        "authors": ParagraphStyle("a", parent=ss["Normal"], fontName="DejaVu", fontSize=9.5, leading=12, alignment=1, spaceAfter=10),
        "h": ParagraphStyle("h", parent=ss["Heading2"], fontName="DejaVu-Bold", fontSize=11.5, leading=14,
                            spaceBefore=8, spaceAfter=4),
        "p": ParagraphStyle("p", parent=ss["Normal"], fontName="DejaVu", fontSize=9.5, leading=12.5, spaceAfter=5),
        "eq": ParagraphStyle("eq", parent=ss["Normal"], fontName="DejaVu", fontSize=10, leading=14, alignment=1,
                             spaceBefore=3, spaceAfter=6),
        "cap": ParagraphStyle("c", parent=ss["Normal"], fontName="DejaVu", fontSize=8.5, leading=11, spaceAfter=8),
    }


def _table(rows: list[list[str]]) -> Table:
    t = Table(rows, hAlign="CENTER")
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "DejaVu-Bold", 8.5),
        ("FONT", (0, 1), (-1, -1), "DejaVu", 8.5),
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, "black"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, "black"),
        ("LINEBELOW", (0, -1), (-1, -1), 0.8, "black"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    return t


def _lead_time_figure() -> io.BytesIO:
    lead = np.arange(1, 49)
    err = 6.0 + 4.5 * (1 - np.exp(-lead / 14))
    fig, ax = plt.subplots(figsize=(5.2, 2.4), dpi=150)
    ax.plot(lead, err, color="#1f5f4a", lw=2)
    ax.set_xlabel("Forecast lead time (h)")
    ax.set_ylabel("NRMSE (% of capacity)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf


def write_paper_a(path: Path) -> None:
    s = _styles()
    story = [
        Paragraph("Capacity-Normalised Error Metrics for Wind Power Forecast Evaluation", s["title"]),
        Paragraph("L. Hansen and M. Okafor. Demonstration material written for TerraKernel; not a published paper.",
                  s["authors"]),
        Paragraph("1 Introduction", s["h"]),
        Paragraph(
            "Forecast errors of wind farms of different sizes are only comparable after normalisation. "
            "We recommend normalising by installed capacity because capacity is a property of the plant and does "
            "not depend on the weather of the evaluation period.", s["p"]),
        Paragraph("2 Definitions", s["h"]),
        Paragraph(
            "Let F<sub>t</sub> be the forecast and M<sub>t</sub> the measured mean power for interval t, both in MW, "
            "and let C<sub>t</sub> be the installed capacity in MW valid during interval t. Only the N intervals where "
            "both F<sub>t</sub> and M<sub>t</sub> are available are used; missing values are never replaced.", s["p"]),
        Paragraph("MAE = (1/N) &Sigma;<sub>t</sub> |F<sub>t</sub> &minus; M<sub>t</sub>|", s["eq"]),
        Paragraph("RMSE = sqrt( (1/N) &Sigma;<sub>t</sub> (F<sub>t</sub> &minus; M<sub>t</sub>)<super>2</super> )",
                  s["eq"]),
        Paragraph("NRMSE<sub>cap</sub> = 100% &times; sqrt( (1/N) &Sigma;<sub>t</sub> ((F<sub>t</sub> &minus; "
                  "M<sub>t</sub>) / C<sub>t</sub>)<super>2</super> )", s["eq"]),
        Paragraph(
            "When the installed capacity changes during the evaluation period, each error must be divided by the "
            "capacity valid for its own interval. Dividing the overall RMSE by a single capacity value biases the "
            "metric whenever capacity varies.", s["p"]),
        Paragraph("3 Worked example", s["h"]),
        Paragraph("Table 1 gives four intervals around a capacity expansion. The squared normalised errors are "
                  "0.0001, 0.0004, 0.0001 and 0.0004, their mean is 0.00025, and NRMSE<sub>cap</sub> = "
                  "100% &times; sqrt(0.00025) = 1.58%. MAE is 2.25 MW and RMSE is 2.5 MW.", s["p"]),
        _table([["Interval", "C (MW)", "F (MW)", "M (MW)", "F - M (MW)"],
                ["1", "100", "51", "50", "1"], ["2", "100", "38", "40", "-2"],
                ["3", "200", "122", "120", "2"], ["4", "200", "86", "90", "-4"]]),
        Paragraph("Table 1: Worked example for NRMSE<sub>cap</sub> with time-varying capacity.", s["cap"]),
        Paragraph("4 Results", s["h"]),
        Paragraph("Across twelve onshore farms, day-ahead NRMSE<sub>cap</sub> grows with forecast lead time and "
                  "saturates after about 36 hours (Figure 1).", s["p"]),
        Image(_lead_time_figure(), width=12 * cm, height=5.5 * cm),
        Paragraph("Figure 1: Day-ahead NRMSE<sub>cap</sub> as a function of forecast lead time (illustrative).",
                  s["cap"]),
    ]
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2 * cm,
                      bottomMargin=2 * cm, title="Capacity-Normalised Error Metrics",
                      author="TerraKernel demo material").build(story)


def write_paper_b(path: Path) -> None:
    s = _styles()
    story = [
        Paragraph("Benchmarking Wind Power Forecasts with a Mean-Normalised NRMSE", s["title"]),
        Paragraph("R. Silva. Demonstration material written for TerraKernel; not a published paper.", s["authors"]),
        Paragraph("1 Motivation", s["h"]),
        Paragraph("Capacity-normalised errors look small at sites with low capacity factors. To compare forecast "
                  "skill across sites with different wind resources, we normalise by the mean measured power of the "
                  "evaluation period instead.", s["p"]),
        Paragraph("2 Metric", s["h"]),
        Paragraph("With forecasts F<sub>t</sub> and measurements M<sub>t</sub> in the same unit over the N intervals "
                  "where both exist (pairwise exclusion of missing values), we define", s["p"]),
        Paragraph("NRMSE<sub>mean</sub> = 100% &times; RMSE / M&#772;,  where  M&#772; = (1/N) &Sigma;<sub>t</sub> "
                  "M<sub>t</sub>", s["eq"]),
        Paragraph("This NRMSE does not use the installed capacity, so it is unaffected by capacity changes but "
                  "depends on the weather of the evaluation period.", s["p"]),
        Paragraph("3 Worked example", s["h"]),
        Paragraph("For the four intervals in Table 1, RMSE = 2.5 and the mean measured power is 75.0, so "
                  "NRMSE<sub>mean</sub> = 100% &times; 2.5 / 75.0 = 3.33%.", s["p"]),
        _table([["Interval", "F", "M", "F - M"], ["1", "51", "50", "1"], ["2", "38", "40", "-2"],
                ["3", "122", "120", "2"], ["4", "86", "90", "-4"]]),
        Paragraph("Table 1: Worked example for NRMSE<sub>mean</sub> (units of power).", s["cap"]),
        Paragraph("4 Discussion", s["h"]),
        Paragraph("We argue that NRMSE<sub>mean</sub> should be preferred when ranking forecast providers across "
                  "sites. Within a single site and period both normalisations rank models identically, because the "
                  "normaliser is the same constant for all models; this does not hold for capacity normalisation "
                  "when capacity varies over time.", s["p"]),
    ]
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2 * cm,
                      bottomMargin=2 * cm, title="Mean-Normalised NRMSE",
                      author="TerraKernel demo material").build(story)


def main() -> None:
    MATERIALS.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    write_csvs(make_series(rng))
    (MATERIALS / "data_description.md").write_text(DATA_DESCRIPTION)
    (MATERIALS / "eval_forecast.py").write_text(LEGACY_SCRIPT)
    write_paper_a(MATERIALS / "paper_a_capacity_nrmse.pdf")
    write_paper_b(MATERIALS / "paper_b_mean_nrmse.pdf")
    print("materials written to", MATERIALS)


if __name__ == "__main__":
    main()
