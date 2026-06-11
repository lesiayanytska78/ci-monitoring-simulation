"""
carbon_layer.py
===============
Module 2 of the MES carbon-intensity monitoring simulation.

Purpose
-------
Layer carbon emissions and carbon intensity on top of the Module 1 energy
substrate. Computes:
  * instantaneous emissions rate         (kg CO2e per second)
  * cumulative emissions                 (kg CO2e since start of day)
  * cumulative CI per piece              (kg CO2e per piece, day-to-date)
  * rolling-window CI per piece          (kg CO2e per piece, last N minutes)
                                         <- the main monitoring signal
  * rolling emissions rate               (kg CO2e per hour, last N minutes)

Method
------
For each timestep:
    emissions(t) = power(t) [kW] * dt [h] * emission_factor(t) [kg CO2e/kWh]

CI per piece over a window is then total_emissions / total_pieces in the
window. This is the metric the monitoring layer (Module 4) will consume: if
energy rises but pieces don't (the anomaly case), CI per piece rises - which
is exactly what an alert engine should fire on.

Provenance tags
---------------
  [ANCHORED]   from a real measurement / authoritative source
  [LITERATURE] cited from published literature; varied in sensitivity analysis
  [ASSUMPTION] provisional engineering estimate; varied in sensitivity analysis
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd

from .energy_substrate import Config as EnergyConfig, simulate_work_center


# ----------------------------------------------------------------------
# Carbon-layer configuration
# ----------------------------------------------------------------------
@dataclass
class CarbonConfig:
    # [LITERATURE] static grid emission factor for the default scenario.
    #   EU average ~0.23 kg CO2e / kWh (European Environment Agency, 2023:
    #   GHG emission intensity of electricity generation).
    #   Real geography-specific values: DEFRA UK ~0.21, US EPA eGRID ~0.39,
    #   France ~0.05 (nuclear), Poland ~0.7 (coal). User overrides per scenario.
    static_emission_factor_kg_per_kwh: float = 0.230

    # [ASSUMPTION] use a synthetic diurnal pattern instead of a constant factor.
    #   The shape (sinusoid, midday trough, late-night peak) reflects grids
    #   with significant solar penetration. For real analysis this would be
    #   replaced with hourly data from ENTSO-E, eGRID, or a national TSO.
    #   SWEPT in sensitivity analysis (both modes are exercised).
    time_varying_ef: bool = False
    diurnal_amplitude: float = 0.30   # +/- fraction around the static value

    # [ASSUMPTION] rolling window for the CI-per-piece monitoring signal.
    #   15 min is a common MES reporting cadence; SWEPT in sensitivity analysis
    #   (shorter -> more responsive to faults but noisier; longer -> smoother
    #   but slower to detect).
    rolling_window_minutes: float = 15.0


# ----------------------------------------------------------------------
# Grid emission factor (constant or time-varying)
# ----------------------------------------------------------------------
def grid_emission_factor(t_seconds: np.ndarray, cfg: CarbonConfig) -> np.ndarray:
    """Return emission factor [kg CO2e / kWh] at each timestamp."""
    ef0 = cfg.static_emission_factor_kg_per_kwh
    if not cfg.time_varying_ef:
        return np.full_like(t_seconds, ef0, dtype=float)
    # synthetic diurnal: trough ~13:00 (solar peak), peak ~01:00 (overnight)
    hours = (t_seconds / 3600.0) % 24.0
    shape = -np.cos((hours - 13.0) * 2 * np.pi / 24.0)
    return ef0 * (1.0 + cfg.diurnal_amplitude * shape)


# ----------------------------------------------------------------------
# Compute the carbon layer on top of the energy substrate
# ----------------------------------------------------------------------
def compute_carbon_layer(substrate: pd.DataFrame, cfg: CarbonConfig) -> pd.DataFrame:
    """Return substrate with carbon columns added."""
    df = substrate.copy()
    t = df["t_s"].values.astype(float)
    dt_s = t[1] - t[0] if len(t) > 1 else 1.0
    dt_h = dt_s / 3600.0

    power_kw = df["total_kw"].values
    pieces_per_step = df["pieces_rate"].values    # pieces produced in this dt

    ef = grid_emission_factor(t, cfg)
    energy_kwh_step = power_kw * dt_h
    emissions_kg_step = energy_kwh_step * ef

    df["emission_factor_kg_per_kwh"] = ef
    df["energy_kwh_step"] = energy_kwh_step
    df["emissions_kg_step"] = emissions_kg_step
    df["emissions_rate_kg_per_s"] = emissions_kg_step / dt_s
    df["energy_kwh_cum"] = np.cumsum(energy_kwh_step)
    df["emissions_kg_cum"] = np.cumsum(emissions_kg_step)

    # cumulative CI per piece (day-to-date)
    cum_pieces = df["pieces_cum"].values
    with np.errstate(divide="ignore", invalid="ignore"):
        df["ci_per_piece_cum_kg"] = np.where(
            cum_pieces > 0, df["emissions_kg_cum"].values / cum_pieces, np.nan
        )

    # rolling-window CI per piece (the monitoring signal)
    win = max(1, int(round(cfg.rolling_window_minutes * 60.0 / dt_s)))
    em_roll = pd.Series(emissions_kg_step).rolling(win, min_periods=1).sum()
    pc_roll = pd.Series(pieces_per_step).rolling(win, min_periods=1).sum()
    with np.errstate(divide="ignore", invalid="ignore"):
        df["ci_per_piece_rolling_kg"] = np.where(
            pc_roll.values > 0, em_roll.values / pc_roll.values, np.nan
        )
    # rolling emissions rate, expressed per hour (a more familiar reporting unit)
    df["emissions_kg_per_h_rolling"] = em_roll.values / (cfg.rolling_window_minutes / 60.0)

    return df


# ----------------------------------------------------------------------
# Summary for sanity-checking
# ----------------------------------------------------------------------
def summarise(df: pd.DataFrame, cfg: CarbonConfig) -> dict:
    prod = df[df["state"] == "PRODUCTION"]
    total_energy = df["energy_kwh_cum"].iloc[-1]
    total_emiss = df["emissions_kg_cum"].iloc[-1]
    total_pieces = int(df["pieces_cum"].iloc[-1])

    # average CI per piece during steady production (rolling-window values, dropping NaN)
    steady = prod["ci_per_piece_rolling_kg"].dropna()
    return {
        "config": {
            "static_emission_factor_kg_per_kwh": cfg.static_emission_factor_kg_per_kwh,
            "time_varying_ef": cfg.time_varying_ef,
            "rolling_window_minutes": cfg.rolling_window_minutes,
        },
        "day_totals": {
            "energy_kwh": round(total_energy, 1),
            "emissions_kg_CO2e": round(total_emiss, 2),
            "pieces": total_pieces,
            "ci_per_piece_kg_CO2e": round(total_emiss / max(total_pieces, 1), 4),
        },
        "during_production": {
            "rolling_ci_per_piece_kg_CO2e_median": round(steady.median(), 4) if len(steady) else None,
            "rolling_ci_per_piece_kg_CO2e_p05": round(steady.quantile(0.05), 4) if len(steady) else None,
            "rolling_ci_per_piece_kg_CO2e_p95": round(steady.quantile(0.95), 4) if len(steady) else None,
        },
    }


if __name__ == "__main__":
    import json

    e_cfg = EnergyConfig()
    c_cfg = CarbonConfig()

    substrate = simulate_work_center(e_cfg)
    df = compute_carbon_layer(substrate, c_cfg)

    print("=== Carbon layer (Module 2): one work center, 24 h ===")
    print(json.dumps(summarise(df, c_cfg), indent=2))

    df.to_csv("carbon_layer_output.csv", index=False)
    print("\nSaved per-second trace -> carbon_layer_output.csv")
