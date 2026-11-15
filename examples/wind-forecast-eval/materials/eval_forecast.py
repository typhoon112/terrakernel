"""Evaluate a wind power forecast against measurements (legacy group script, 2021)."""

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
