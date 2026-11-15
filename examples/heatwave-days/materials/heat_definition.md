# Heat-health warning definition (City Climate Office)

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
