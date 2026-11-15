"""Unit registry shared by the planner (validation) and the generated runtime.

Units map to (dimension, factor to the dimension's base unit, offset). Only linear
conversions plus temperature offsets are supported; anything else is rejected rather
than guessed. Matching is case-sensitive for SI prefixes (``mW`` is not ``MW``) but
accepts a few spelled-out aliases.
"""

from __future__ import annotations

UNITS: dict[str, tuple[str, float, float]] = {
    # power
    "W": ("power", 1.0, 0.0), "kW": ("power", 1e3, 0.0), "MW": ("power", 1e6, 0.0), "GW": ("power", 1e9, 0.0),
    "TW": ("power", 1e12, 0.0),
    # energy
    "Wh": ("energy", 3600.0, 0.0), "kWh": ("energy", 3.6e6, 0.0), "MWh": ("energy", 3.6e9, 0.0),
    "GWh": ("energy", 3.6e12, 0.0), "TWh": ("energy", 3.6e15, 0.0), "J": ("energy", 1.0, 0.0),
    "kJ": ("energy", 1e3, 0.0), "MJ": ("energy", 1e6, 0.0), "GJ": ("energy", 1e9, 0.0), "PJ": ("energy", 1e15, 0.0),
    # length / area / volume
    "mm": ("length", 1e-3, 0.0), "cm": ("length", 1e-2, 0.0), "m": ("length", 1.0, 0.0), "km": ("length", 1e3, 0.0),
    "m2": ("area", 1.0, 0.0), "km2": ("area", 1e6, 0.0), "ha": ("area", 1e4, 0.0),
    "L": ("volume", 1e-3, 0.0), "m3": ("volume", 1.0, 0.0),
    # mass
    "g": ("mass", 1e-3, 0.0), "kg": ("mass", 1.0, 0.0), "t": ("mass", 1e3, 0.0), "kt": ("mass", 1e6, 0.0),
    "Mt": ("mass", 1e9, 0.0), "Gt": ("mass", 1e12, 0.0),
    # speed
    "m/s": ("speed", 1.0, 0.0), "km/h": ("speed", 1 / 3.6, 0.0), "kn": ("speed", 0.514444, 0.0),
    # temperature (base: kelvin)
    "K": ("temperature", 1.0, 0.0), "degC": ("temperature", 1.0, 273.15),
    "degF": ("temperature", 5 / 9, 273.15 - 32 * 5 / 9),
    # pressure
    "Pa": ("pressure", 1.0, 0.0), "hPa": ("pressure", 100.0, 0.0), "kPa": ("pressure", 1e3, 0.0),
    "MPa": ("pressure", 1e6, 0.0), "bar": ("pressure", 1e5, 0.0),
    # dimensionless
    "1": ("ratio", 1.0, 0.0), "fraction": ("ratio", 1.0, 0.0), "%": ("ratio", 0.01, 0.0),
    "ppm": ("ratio", 1e-6, 0.0), "ppb": ("ratio", 1e-9, 0.0),
    # time
    "s": ("time", 1.0, 0.0), "min": ("time", 60.0, 0.0), "h": ("time", 3600.0, 0.0), "d": ("time", 86400.0, 0.0),
    # irradiance / energy flux
    "W/m2": ("irradiance", 1.0, 0.0), "kW/m2": ("irradiance", 1e3, 0.0), "W m-2": ("irradiance", 1.0, 0.0),
    "kWh/m2": ("irradiation", 3.6e6, 0.0), "J/m2": ("irradiation", 1.0, 0.0), "MJ/m2": ("irradiation", 1e6, 0.0),
    # precipitation rate (water-equivalent mass flux; 1 mm of water = 1 kg m-2)
    "kg m-2 s-1": ("mass_flux", 1.0, 0.0), "kg/m2/s": ("mass_flux", 1.0, 0.0),
    "mm/h": ("mass_flux", 1 / 3600.0, 0.0), "mm/day": ("mass_flux", 1 / 86400.0, 0.0), "mm/d": ("mass_flux", 1 / 86400.0, 0.0),
    # mass of carbon dioxide (emissions)
    "tCO2": ("mass_co2", 1e3, 0.0), "ktCO2": ("mass_co2", 1e6, 0.0), "MtCO2": ("mass_co2", 1e9, 0.0),
    "GtCO2": ("mass_co2", 1e12, 0.0), "kgCO2": ("mass_co2", 1.0, 0.0),
    "tCO2e": ("mass_co2e", 1e3, 0.0), "MtCO2e": ("mass_co2e", 1e9, 0.0), "GtCO2e": ("mass_co2e", 1e12, 0.0),
    # concentration (mole fraction)
    "mol/mol": ("mole_fraction", 1.0, 0.0),
    # concentration / emissions intensity
    "gCO2/kWh": ("emission_intensity", 1.0, 0.0), "kgCO2/MWh": ("emission_intensity", 1.0, 0.0),
    "tCO2/MWh": ("emission_intensity", 1e3, 0.0),
}

ALIASES = {
    "watt": "W", "watts": "W", "kilowatt": "kW", "kilowatts": "kW", "megawatt": "MW", "megawatts": "MW",
    "gigawatt": "GW", "gigawatts": "GW", "percent": "%", "pct": "%", "celsius": "degC", "°C": "degC",
    "fahrenheit": "degF", "°F": "degF", "kelvin": "K", "m^2": "m2", "m²": "m2", "km²": "km2", "m^3": "m3",
    "m³": "m3", "W/m^2": "W/m2", "W/m²": "W/m2", "W m**-2": "W m-2", "mps": "m/s", "kmh": "km/h",
    "m s-1": "m/s", "m s**-1": "m/s", "kg m**-2 s**-1": "kg m-2 s-1", "mm day-1": "mm/day", "mm/hr": "mm/h",
    "degrees_C": "degC", "degree_Celsius": "degC", "deg C": "degC", "unitless": "1",
    "dimensionless": "1", "hours": "h", "hour": "h", "minutes": "min", "seconds": "s", "days": "d",
}


def canonical_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    u = unit.strip()
    if u in UNITS:
        return u
    return ALIASES.get(u) or ALIASES.get(u.lower())


def dimension(unit: str) -> str | None:
    cu = canonical_unit(unit)
    return UNITS[cu][0] if cu else None


def conversion(src: str, dst: str) -> tuple[float, float]:
    """Return (scale, offset) such that value_dst = value_src * scale + offset."""
    s, d = canonical_unit(src), canonical_unit(dst)
    if s is None or d is None:
        raise ValueError(f"unknown unit: {src if s is None else dst!r}")
    ds, fs, os_ = UNITS[s]
    dd, fd, od = UNITS[d]
    if ds != dd:
        raise ValueError(f"cannot convert {src} ({ds}) to {dst} ({dd})")
    # base = v*fs + os ; v_dst = (base - od)/fd
    return fs / fd, (os_ - od) / fd
