"""
energy_substrate.py  (v2 - calibrated)
======================================
Module 1 of the MES carbon-intensity monitoring simulation.

Purpose
-------
Generate a synthetic energy-consumption time series for a single work center,
used as the substrate the rest of the simulation builds on.

Model structure (validated twice over)
---------------------------------------
total power = auxiliary base load
            + spindle no-load (idle-spin) power
            + spindle cutting increment   (only while the tool is engaged)

This base-load-plus-production-correlated decomposition is the canonical
machine-tool energy model of Gutowski et al. (2006), and it is independently
confirmed by the per-axis energy breakdown in the open Brillinger et al. (2025)
CNC machining dataset (Mendeley Data, DOI 10.17632/gtvvwmz7r7.2, CC BY 4.0),
which separates a distinct spindle energy component (ENERGY|S).

Calibration status (Option B - "grounded in, not surgically fitted to")
-----------------------------------------------------------------------
Every parameter below carries a provenance tag:
  [ANCHORED]   fitted to a real measurement in the Brillinger et al. (2025) dataset
  [LITERATURE] from the machine-tool energy literature; varied in sensitivity analysis
  [ASSUMPTION] provisional engineering estimate; varied in sensitivity analysis

What the Brillinger dataset established and is used here:
  * model STRUCTURE (separate spindle component)              -> [ANCHORED]
  * spindle no-load power ~0.8-1.0 kW (stable)                 -> [ANCHORED]
  * stopped spindle = 0 W                                      -> [ANCHORED]
  * cutting is intermittent even within a machining run        -> structural insight

What the dataset could NOT give us (and why), now from literature + swept:
  * the cutting-power increment - the servo-drive traces don't cleanly isolate it
  * the auxiliary base load     - the dataset is servo-drive power only; it does
                                  not capture coolant pumps, hydraulics, control cabinet

Note on regenerative braking
----------------------------
The Brillinger traces show large negative-power transients (~-17 to -20 kW)
during spindle deceleration - real regenerative braking, confirmed by the
co-occurring high torque/current and changing spindle speed. For an energy-
*consumption* model these are clipped to zero (regen energy is typically
dissipated in a braking resistor, not recovered), so brake events contribute
~0 to consumption and are not modelled as a separate component.

Note on absolute scale
----------------------
The [ANCHORED] value comes from a small 5-axis mill (Spinner U5-630) machining
aluminium/plastic parts. The target context (precision grinding in bearing
manufacturing) runs heavier, so absolute scale is an explicit per-scenario
input - the dataset anchors the *structure* and the *no-load spindle* point;
scenario scaling is applied on top.
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd


# ----------------------------------------------------------------------
# Configuration  (provenance tag on every energy parameter)
# ----------------------------------------------------------------------
@dataclass
class Config:
    # --- time base ---
    duration_hours: float = 24.0
    dt_seconds: float = 1.0

    # --- operating window: two 8 h shifts ---
    shift_start_hour: float = 6.0
    operating_hours: float = 16.0

    # === ENERGY MODEL [kW] ===
    # [ANCHORED] spindle spinning at operating speed but NOT engaged in material.
    #   Brillinger et al. (2025): no-load spindle power was a stable ~0.8-1.0 kW
    #   (median ~0.80 kW and ~0.99 kW across two job traces).
    spindle_idle_kw: float = 0.9

    # [LITERATURE] additional spindle power while the tool is actually cutting.
    #   Gutowski et al. (2006): cutting power adds on top of idle power and scales
    #   with material removal rate. Not cleanly isolatable from the servo-drive
    #   traces, so taken from literature and SWEPT in sensitivity analysis.
    spindle_cut_increment_kw: float = 3.0

    # [LITERATURE] auxiliary / peripheral load: coolant pump, hydraulics, control
    #   cabinet, lighting. Present whenever the machine is operational. NOT captured
    #   by the Brillinger dataset (servo-drive power only). Gutowski "fixed power".
    #   SWEPT in sensitivity analysis.
    aux_base_kw: float = 2.5

    # [ASSUMPTION] true standby draw when the machine is OFF.
    offline_standby_kw: float = 0.2

    # [ASSUMPTION] within a production run, fraction of time the tool is actually
    #   engaged in material (rest = rapid moves / positioning, spindle spinning but
    #   not cutting). Brillinger traces show cutting is intermittent. SWEPT.
    cutting_duty: float = 0.55

    # [ASSUMPTION] relative stochastic noise (sensor + process), broadly consistent
    #   with the variability of the steady free-spin signal in the dataset. SWEPT.
    noise_frac: float = 0.05

    # slow correlated drift on the auxiliary load (lube/coolant pumps cycling)
    aux_base_drift: float = 0.05

    # --- production pattern ---
    run_minutes_range: tuple = (20.0, 90.0)    # length of a production run
    gap_minutes_range: tuple = (5.0, 30.0)     # idle gap between runs (changeover)
    cut_subinterval_range: tuple = (3.0, 25.0) # length of a cut sub-interval within a run [s]
    spindle_rampup_s: float = 1.5              # spindle accel to speed at run start
    pieces_per_hour: float = 60.0              # throughput during a run

    seed: int = 42


# ----------------------------------------------------------------------
# Production schedule
# ----------------------------------------------------------------------
def build_schedule(cfg: Config, rng: np.random.Generator) -> pd.DataFrame:
    """Segments over the day: (start_s, end_s, state) for OFFLINE/IDLE/PRODUCTION."""
    op_start = cfg.shift_start_hour * 3600.0
    op_end = op_start + cfg.operating_hours * 3600.0
    day_end = cfg.duration_hours * 3600.0

    segments = []
    if op_start > 0:
        segments.append((0.0, op_start, "OFFLINE"))
    t = op_start
    while t < op_end:
        run_len = rng.uniform(*cfg.run_minutes_range) * 60.0
        run_end = min(t + run_len, op_end)
        segments.append((t, run_end, "PRODUCTION"))
        t = run_end
        if t >= op_end:
            break
        gap_len = rng.uniform(*cfg.gap_minutes_range) * 60.0
        gap_end = min(t + gap_len, op_end)
        segments.append((t, gap_end, "IDLE"))
        t = gap_end
    if op_end < day_end:
        segments.append((op_end, day_end, "OFFLINE"))
    return pd.DataFrame(segments, columns=["start_s", "end_s", "state"])


def _cutting_mask(seg_len: int, cfg: Config, rng: np.random.Generator) -> np.ndarray:
    """Boolean per-second mask: True where the tool is engaged in material.
    Cut and air sub-intervals alternate; air length is set so the long-run cut
    fraction matches cfg.cutting_duty."""
    duty = min(max(cfg.cutting_duty, 0.05), 0.95)
    mask = np.zeros(seg_len, dtype=bool)
    i = 0
    cutting = True
    while i < seg_len:
        cut_len = rng.uniform(*cfg.cut_subinterval_range)
        if cutting:
            L = int(round(cut_len))
        else:
            L = int(round(cut_len * (1.0 - duty) / duty))
        L = max(1, L)
        j = min(i + L, seg_len)
        mask[i:j] = cutting
        i = j
        cutting = not cutting
    return mask


# ----------------------------------------------------------------------
# Energy time series
# ----------------------------------------------------------------------
def simulate_work_center(cfg: Config) -> pd.DataFrame:
    """Per-timestep energy substrate for one work center.

    Columns: state, cutting, machine_kw (aux base), spindle_kw, total_kw,
             pieces_rate, pieces_cum
    """
    rng = np.random.default_rng(cfg.seed)
    schedule = build_schedule(cfg, rng)

    n = int(round(cfg.duration_hours * 3600.0 / cfg.dt_seconds))
    t = np.arange(n) * cfg.dt_seconds

    state = np.empty(n, dtype=object)
    cutting = np.zeros(n, dtype=bool)
    machine = np.zeros(n)     # auxiliary base load (or offline standby)
    spindle = np.zeros(n)     # spindle: idle-spin + cutting increment
    pieces_rate = np.zeros(n)

    drift = 1.0 + cfg.aux_base_drift * np.sin(2 * np.pi * t / (3600.0 * 3.0))

    for _, seg in schedule.iterrows():
        i0 = int(round(seg.start_s / cfg.dt_seconds))
        i1 = min(int(round(seg.end_s / cfg.dt_seconds)), n)
        if i1 <= i0:
            continue
        state[i0:i1] = seg.state
        seg_len = i1 - i0

        if seg.state == "OFFLINE":
            machine[i0:i1] = cfg.offline_standby_kw

        elif seg.state == "IDLE":
            # machine on between runs: auxiliary load only, spindle stopped
            machine[i0:i1] = cfg.aux_base_kw * drift[i0:i1]

        elif seg.state == "PRODUCTION":
            machine[i0:i1] = cfg.aux_base_kw * drift[i0:i1]
            # spindle spins for the whole run; short ramp-up to speed
            ramp = np.minimum(1.0, np.arange(seg_len) / max(1, int(cfg.spindle_rampup_s / cfg.dt_seconds)))
            sp = cfg.spindle_idle_kw * ramp
            # cutting increment on intermittent sub-intervals; per-run intensity +/-15%
            cut = _cutting_mask(seg_len, cfg, rng)
            run_intensity = rng.uniform(0.85, 1.15)
            sp = sp + cut * cfg.spindle_cut_increment_kw * run_intensity * ramp
            spindle[i0:i1] = sp
            cutting[i0:i1] = cut
            pieces_rate[i0:i1] = (cfg.pieces_per_hour / 3600.0) * cfg.dt_seconds * ramp

    # stochastic noise (sensor + process), proportional to instantaneous load
    machine = np.clip(machine * (1.0 + cfg.noise_frac * rng.standard_normal(n)), 0.0, None)
    spindle = np.clip(spindle * (1.0 + cfg.noise_frac * rng.standard_normal(n)), 0.0, None)
    total = machine + spindle
    pieces_cum = np.cumsum(pieces_rate)

    return pd.DataFrame({
        "t_s": t, "state": state, "cutting": cutting,
        "machine_kw": machine, "spindle_kw": spindle, "total_kw": total,
        "pieces_rate": pieces_rate, "pieces_cum": pieces_cum,
    })


# ----------------------------------------------------------------------
# Summary for sanity-checking
# ----------------------------------------------------------------------
def summarise(df: pd.DataFrame, cfg: Config) -> dict:
    dt_h = cfg.dt_seconds / 3600.0
    prod = df[df.state == "PRODUCTION"]
    idle = df[df.state == "IDLE"]
    off = df[df.state == "OFFLINE"]
    total_kwh = df["total_kw"].sum() * dt_h
    return {
        "mean_total_kw": {
            "OFFLINE": round(off["total_kw"].mean(), 2) if len(off) else None,
            "IDLE": round(idle["total_kw"].mean(), 2) if len(idle) else None,
            "PRODUCTION": round(prod["total_kw"].mean(), 2) if len(prod) else None,
        },
        "production_breakdown_kw": {
            "while_cutting": round(prod[prod.cutting]["total_kw"].mean(), 2) if len(prod[prod.cutting]) else None,
            "spinning_not_cutting": round(prod[~prod.cutting]["total_kw"].mean(), 2) if len(prod[~prod.cutting]) else None,
        },
        "time_split_hours": {
            s: round((df.state == s).sum() * dt_h, 2) for s in ["OFFLINE", "IDLE", "PRODUCTION"]
        },
        "cutting_duty_realised": round(prod["cutting"].mean(), 3) if len(prod) else None,
        "idle_to_production_power_ratio": round(idle["total_kw"].mean() / prod["total_kw"].mean(), 3)
            if len(idle) and len(prod) else None,
        "energy_kwh_total_day": round(total_kwh, 1),
        "non_productive_energy_share": round(
            (idle["total_kw"].sum() + off["total_kw"].sum()) * dt_h / total_kwh, 3),
        "pieces_produced_day": int(df["pieces_cum"].iloc[-1]),
    }


if __name__ == "__main__":
    import json
    cfg = Config()
    df = simulate_work_center(cfg)
    print("=== Energy substrate v2 (calibrated): one work center, 24 h ===")
    print(json.dumps(summarise(df, cfg), indent=2))
    df.to_csv("/home/claude/energy_substrate_output.csv", index=False)
    print("\nSaved per-second trace -> energy_substrate_output.csv")
