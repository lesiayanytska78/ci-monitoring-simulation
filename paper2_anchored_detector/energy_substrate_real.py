"""
energy_substrate_real.py
========================
Module 1b (real-data, Level-2 validation).

A drop-in replacement for energy_substrate.simulate_work_center that builds the
operating-day substrate from REAL measured spindle-power traces (Brillinger et
al. 2025, Mendeley DOI 10.17632/gtvvwmz7r7.2) instead of the synthetic Gutowski
spindle model. Everything downstream (carbon layer, anomaly model, monitoring,
detectors) is unchanged.

Semi-synthetic by necessity (stated honestly in the paper):
  * spindle_kw : REAL measured servo-drive spindle power (POWER|5), regen-clipped
                 to zero, resampled to 1 s, tiled to fill each production run.
  * machine_kw : MODELLED auxiliary base load (2.5 kW + drift) -- the open dataset
                 records servo-drive power only and does not capture coolant/
                 hydraulics/control-cabinet load.
  * pieces     : imposed at cfg.pieces_per_hour (60/h) for apples-to-apples
                 comparison with the synthetic study.
  * schedule   : same two-shift run/idle structure as the synthetic substrate.

The real spindle trace carries its own process variability, so no synthetic
process noise is added to it; modelled measurement noise is still applied by the
monitoring layer (Module 4). Modelled aux carries the modelled process noise.
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd
from energy_substrate import Config, build_schedule

_PROF_PATH = os.path.join(os.path.dirname(__file__), "real_profiles.npz")
if not os.path.exists(_PROF_PATH):
    raise FileNotFoundError(
        "real_profiles.npz not found.\n"
        "This file is DERIVED from the Brillinger et al. (2025) CNC dataset, which is "
        "licensed CC BY-NC and is therefore not redistributed in this repository.\n"
        "To generate it: download the dataset (Mendeley Data, DOI 10.17632/gtvvwmz7r7.2), "
        "unzip it, then run:\n"
        '    python extract_brillinger_profiles.py "<path to Raw Datasets (.json) folder>"')
_PROFILES = [v for v in np.load(_PROF_PATH).values() if len(v) > 5]


def simulate_work_center_real(cfg: Config) -> pd.DataFrame:
    rng = np.random.default_rng(cfg.seed)
    schedule = build_schedule(cfg, rng)
    n = int(round(cfg.duration_hours * 3600.0 / cfg.dt_seconds))
    t = np.arange(n) * cfg.dt_seconds

    state = np.empty(n, dtype=object)
    machine = np.zeros(n)
    spindle = np.zeros(n)
    cutting = np.zeros(n, dtype=bool)
    pieces_rate = np.zeros(n)
    drift = 1.0 + cfg.aux_base_drift * np.sin(2 * np.pi * t / (3600.0 * 3.0))

    for _, seg in schedule.iterrows():
        i0 = int(round(seg.start_s / cfg.dt_seconds))
        i1 = min(int(round(seg.end_s / cfg.dt_seconds)), n)
        if i1 <= i0:
            continue
        state[i0:i1] = seg.state
        L = i1 - i0
        if seg.state == "OFFLINE":
            machine[i0:i1] = cfg.offline_standby_kw
        elif seg.state == "IDLE":
            machine[i0:i1] = cfg.aux_base_kw * drift[i0:i1]
        elif seg.state == "PRODUCTION":
            machine[i0:i1] = cfg.aux_base_kw * drift[i0:i1]
            prof = _PROFILES[rng.integers(len(_PROFILES))]      # a real job trace
            reps = int(np.ceil((L + len(prof)) / len(prof)))
            tiled = np.tile(prof, reps)
            off = int(rng.integers(0, len(prof)))
            spindle[i0:i1] = tiled[off:off + L]
            cutting[i0:i1] = spindle[i0:i1] > np.percentile(prof, 45)
            pieces_rate[i0:i1] = (cfg.pieces_per_hour / 3600.0) * cfg.dt_seconds

    # modelled measurement/process noise on the MODELLED aux only; spindle is real
    machine = np.clip(machine * (1.0 + cfg.noise_frac * rng.standard_normal(n)), 0.0, None)
    total = machine + spindle
    pieces_cum = np.cumsum(pieces_rate)
    return pd.DataFrame({
        "t_s": t, "state": state, "cutting": cutting,
        "machine_kw": machine, "spindle_kw": spindle, "total_kw": total,
        "pieces_rate": pieces_rate, "pieces_cum": pieces_cum,
    })


if __name__ == "__main__":
    df = simulate_work_center_real(Config(seed=1))
    prod = df[df.state == "PRODUCTION"]
    print(f"profiles loaded: {len(_PROFILES)}")
    print(f"production mean total kW: {prod.total_kw.mean():.2f}  "
          f"spindle mean: {prod.spindle_kw.mean():.2f}  aux mean: {prod.machine_kw.mean():.2f}")
    print(f"pieces/day: {int(df.pieces_cum.iloc[-1])}")
