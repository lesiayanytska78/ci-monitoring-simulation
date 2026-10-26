"""
anomaly_model.py
================
Module 3 of the MES carbon-intensity monitoring simulation.

Purpose
-------
Inject parametrized energy anomalies (faults) into the Module 1 substrate, so
Module 2 (carbon layer) and Module 4 (monitoring) see the same kind of signal
a real fault would produce. This is what lets us evaluate the detection logic
against *ground truth* - because we built the fault, we know exactly when it
started, how big it was, and when it ended.

What an anomaly is, here
------------------------
An anomaly is excess power that appears on the work center without producing
extra output. It's additive on top of the normal operating signature:
    power_with_anomaly(t) = power_baseline(t) + anomaly_excess(t)
    pieces_produced(t)    = unchanged
This is the discriminating signal CI per piece is designed to catch: if energy
rises while output doesn't, CI rises.

Anomaly archetypes (from the industrial energy literature)
----------------------------------------------------------
Four presets are provided as starting points; each is fully parametrized so
magnitude, duration, and onset are SWEPT in the sensitivity analysis.

  COMPRESSED_AIR_LEAK
      [LITERATURE] DOE Compressed Air Challenge / Saidur et al. (2010):
      significant leaks add ~1-3 kW of compressor load; leaks of 20-30% of
      compressed-air system load are common in unmaintained plants. Duration
      before detection: hours to weeks. Onset typically gradual (seal degrades).

  MACHINE_LEFT_ON
      [ANCHORED] Brillinger et al. (2025) no-load spindle ~0.9 kW.
      Operator forgets to power down; persists until next inspection.

  TOOL_WEAR
      [LITERATURE] Cutting power rises 5-30% above baseline as the tool dulls
      (standard machine-tool literature, e.g. Tan & Pan 2014). Develops over
      a tool's working life; here represented as a slow ramp.

  COOLANT_PUMP_FAULT
      [LITERATURE] Pump straining against a partial blockage / failing seal
      adds ~0.5-2 kW; typically near-binary onset.

Provenance discipline
---------------------
Every numeric value in the presets carries the same [ANCHORED] / [LITERATURE]
/ [ASSUMPTION] tags as Modules 1 and 2. All are swept; the presets are
*illustrative*, not load-bearing.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
import pandas as pd


# ----------------------------------------------------------------------
# Anomaly specification
# ----------------------------------------------------------------------
@dataclass
class AnomalySpec:
    """A single energy anomaly to inject."""
    onset_hour: float                 # when the fault starts (hour of day, 0-24)
    duration_minutes: float           # how long it persists before being caught
    magnitude_kw: float               # excess power added (additive)
    onset_profile: str = "step"       # see _envelope for the full list
    onset_ramp_seconds: float = 60.0  # ramp duration if profile=="ramp"/"step_ramp"
    affects: str = "machine"          # "machine" (aux base) or "spindle"
    label: str = "anomaly"            # for plotting / identification
    # --- Extra fault morphologies (Paper 2 major revision, §4.10) ---
    # "step_ramp"        : immediate step to half magnitude, then ramp to full
    # "intermittent"     : on/off square wave at magnitude (period/duty below)
    # "oscillatory"      : magnitude * 0.5*(1 - cos), range [0, magnitude]
    # "partial_recovery" : ramp up to full, then decline to recovery_frac*magnitude
    intermittent_period_min: float = 20.0   # full on+off cycle
    intermittent_duty: float = 0.5          # fraction of the cycle that is "on"
    oscillatory_period_min: float = 30.0
    recovery_frac: float = 0.5              # partial_recovery: residual fraction


@dataclass
class AnomalyConfig:
    """Collection of anomalies to inject in one run."""
    anomalies: list = field(default_factory=list)


# ----------------------------------------------------------------------
# Preset archetypes (illustrative starting points; all parameters SWEPT)
# ----------------------------------------------------------------------
def compressed_air_leak(onset_hour=10.0, duration_min=240.0, magnitude_kw=1.5) -> AnomalySpec:
    """A compressed-air leak. Gradual onset as a seal degrades, then persistent.
    Default values are mid-range from the DOE / Saidur et al. literature."""
    return AnomalySpec(
        onset_hour=onset_hour,
        duration_minutes=duration_min,
        magnitude_kw=magnitude_kw,
        onset_profile="ramp",
        onset_ramp_seconds=120.0,
        affects="machine",
        label=f"Compressed-air leak ({magnitude_kw:.1f} kW, {duration_min/60:.1f} h)",
    )

def machine_left_on(onset_hour=12.0, duration_min=60.0, magnitude_kw=0.9) -> AnomalySpec:
    """Operator forgets to power down; spindle continues spinning at no-load.
    Magnitude anchored to the Brillinger no-load spindle measurement."""
    return AnomalySpec(
        onset_hour=onset_hour,
        duration_minutes=duration_min,
        magnitude_kw=magnitude_kw,
        onset_profile="step",
        affects="spindle",
        label=f"Spindle left running ({magnitude_kw:.1f} kW, {duration_min/60:.1f} h)",
    )

def tool_wear(onset_hour=14.0, duration_min=120.0, magnitude_kw=0.8) -> AnomalySpec:
    """Tool dulls gradually, cutting load rises. Slow ramp over the duration."""
    return AnomalySpec(
        onset_hour=onset_hour,
        duration_minutes=duration_min,
        magnitude_kw=magnitude_kw,
        onset_profile="ramp",
        onset_ramp_seconds=3600.0,
        affects="spindle",
        label=f"Tool wear (drift to +{magnitude_kw:.1f} kW over {duration_min/60:.1f} h)",
    )

def coolant_pump_fault(onset_hour=11.0, duration_min=180.0, magnitude_kw=1.2) -> AnomalySpec:
    """Coolant pump straining; near-step onset."""
    return AnomalySpec(
        onset_hour=onset_hour,
        duration_minutes=duration_min,
        magnitude_kw=magnitude_kw,
        onset_profile="step",
        affects="machine",
        label=f"Coolant pump fault ({magnitude_kw:.1f} kW, {duration_min/60:.1f} h)",
    )


# ----------------------------------------------------------------------
# Envelope builder
# ----------------------------------------------------------------------
def _envelope(t_seconds: np.ndarray, spec: AnomalySpec) -> np.ndarray:
    """Per-timestep magnitude envelope (kW) for one anomaly."""
    t_start = spec.onset_hour * 3600.0
    t_end = t_start + spec.duration_minutes * 60.0
    env = np.zeros_like(t_seconds, dtype=float)
    active = (t_seconds >= t_start) & (t_seconds < t_end)

    elapsed = np.where(active, t_seconds - t_start, 0.0)
    dur_s = max(spec.duration_minutes * 60.0, 1e-6)
    M = spec.magnitude_kw

    if spec.onset_profile == "step":
        env[active] = M
    elif spec.onset_profile == "ramp":
        ramp = np.clip(elapsed / max(spec.onset_ramp_seconds, 1e-6), 0.0, 1.0)
        env = np.where(active, M * ramp, 0.0)
    elif spec.onset_profile == "step_ramp":
        # a small immediate step (0.2 M) followed by a slow drift to full magnitude
        # over the whole fault duration -- a tool that chips then wears. Mostly a
        # gradual form, so the deployed relative-threshold detector misses it.
        ramp = np.clip(elapsed / dur_s, 0.0, 1.0)
        env = np.where(active, M * (0.2 + 0.8 * ramp), 0.0)
    elif spec.onset_profile == "intermittent":
        period_s = max(spec.intermittent_period_min * 60.0, 1e-6)
        phase = np.mod(elapsed, period_s) / period_s
        on = active & (phase < spec.intermittent_duty)
        env[on] = M
    elif spec.onset_profile == "oscillatory":
        period_s = max(spec.oscillatory_period_min * 60.0, 1e-6)
        osc = 0.5 * (1.0 - np.cos(2.0 * np.pi * elapsed / period_s))  # [0,1]
        env = np.where(active, M * osc, 0.0)
    elif spec.onset_profile == "partial_recovery":
        # ramp up to full over the first third of the fault, then decline
        # linearly to recovery_frac*M by the end (a partially self-correcting fault)
        up_s = dur_s / 3.0
        frac = np.where(
            elapsed < up_s,
            elapsed / max(up_s, 1e-6),
            1.0 - (1.0 - spec.recovery_frac) * np.clip((elapsed - up_s) / max(dur_s - up_s, 1e-6), 0.0, 1.0),
        )
        env = np.where(active, M * frac, 0.0)
    else:
        raise ValueError(f"Unknown onset_profile: {spec.onset_profile}")
    return env


# ----------------------------------------------------------------------
# Inject anomalies into a substrate
# ----------------------------------------------------------------------
def inject_anomalies(substrate: pd.DataFrame, cfg: AnomalyConfig) -> pd.DataFrame:
    """Return a copy of the substrate with the configured anomalies added.

    Adds columns:
        anomaly_kw       - total excess power (for transparency / plotting)
        anomaly_active   - boolean: True wherever any anomaly is active
        anomaly_labels   - comma-joined list of active anomaly labels
    """
    df = substrate.copy()
    t = df["t_s"].values.astype(float)
    n = len(t)

    excess_machine = np.zeros(n)
    excess_spindle = np.zeros(n)
    active = np.zeros(n, dtype=bool)
    labels = [[] for _ in range(n)]

    for spec in cfg.anomalies:
        env = _envelope(t, spec)
        if spec.affects == "machine":
            excess_machine += env
        elif spec.affects == "spindle":
            excess_spindle += env
        else:
            raise ValueError(f"Unknown affects: {spec.affects}")
        is_on = env > 0
        active |= is_on
        for i in np.flatnonzero(is_on):
            labels[i].append(spec.label)

    df["machine_kw"] = df["machine_kw"].values + excess_machine
    df["spindle_kw"] = df["spindle_kw"].values + excess_spindle
    df["total_kw"] = df["machine_kw"].values + df["spindle_kw"].values
    df["anomaly_kw"] = excess_machine + excess_spindle
    df["anomaly_active"] = active
    df["anomaly_labels"] = [", ".join(L) if L else "" for L in labels]
    return df


# ----------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------
def summarise(df: pd.DataFrame, cfg: AnomalyConfig) -> dict:
    dt_h = (df["t_s"].iloc[1] - df["t_s"].iloc[0]) / 3600.0
    excess_kwh = df["anomaly_kw"].sum() * dt_h
    return {
        "n_anomalies": len(cfg.anomalies),
        "anomaly_specs": [
            {"label": a.label, "onset_h": a.onset_hour, "duration_min": a.duration_minutes,
             "magnitude_kw": a.magnitude_kw, "affects": a.affects, "profile": a.onset_profile}
            for a in cfg.anomalies
        ],
        "active_hours": round(df["anomaly_active"].sum() * dt_h, 2),
        "excess_energy_kwh": round(excess_kwh, 2),
        "peak_excess_kw": round(df["anomaly_kw"].max(), 2),
    }


if __name__ == "__main__":
    import json
    from energy_substrate import Config as EnergyConfig, simulate_work_center

    substrate = simulate_work_center(EnergyConfig())
    cfg = AnomalyConfig(anomalies=[compressed_air_leak(onset_hour=10.0,
                                                        duration_min=240.0,
                                                        magnitude_kw=2.0)])
    df = inject_anomalies(substrate, cfg)
    print("=== Anomaly model (Module 3): single compressed-air leak ===")
    print(json.dumps(summarise(df, cfg), indent=2))
    df.to_csv("anomaly_model_output.csv", index=False)
    print("\nSaved substrate-with-anomaly trace -> anomaly_model_output.csv")
