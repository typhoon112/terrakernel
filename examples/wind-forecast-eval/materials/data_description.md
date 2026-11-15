# Farm Delta wind measurement and forecast data

Prepared by the Wind Analytics Group for the 2023 forecast benchmarking study.
All data in this folder are synthetic and exist only to exercise analysis tooling.

## Site

Farm Delta is an onshore wind farm. Its installed capacity changed once during 2023:

| Valid from (UTC) | Installed capacity |
|---|---|
| 2023-01-01T00:00:00Z | 100 MW |
| 2023-07-01T00:00:00Z | 120 MW |

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
