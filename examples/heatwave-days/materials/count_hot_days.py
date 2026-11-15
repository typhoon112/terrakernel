"""Count hot days per year (legacy script from the 2019 heat report)."""

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
