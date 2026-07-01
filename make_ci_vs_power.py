#!/usr/bin/env python3
"""
make_ci_vs_power.py
===================
Reproduces the §4.8 demonstration: what per-piece carbon-intensity (CI)
normalisation adds over raw-power thresholding.

Two scenarios are compared over a four-hour fault window:
  (1) throughput loss  — pieces produced drop 45% at unchanged power;
  (2) additive power    — +2 kW spindle excess at unchanged throughput.

For each, the mean production-state CI per piece and mean observed power in the
fault window are compared to a pre-fault baseline window. A relative-threshold
detector (+25% over baseline) is applied to each signal. The throughput-loss
fault is visible in CI but not in raw power; the additive-power fault is visible
in both. This is a supplementary analysis; its runs are NOT part of the
nine-sweep set (4,356 runs).

Writes `data/ci_vs_power.csv`. Deterministic (seed = 1).

Requires numpy, pandas, and the `cimonitoring` package.
"""
from __future__ import annotations
import csv
import os
import cimonitoring as ci

HERE = os.path.dirname(os.path.abspath(__file__))
EF = ci.CarbonConfig().static_emission_factor_kg_per_kwh
BASE = (6 * 3600, 11 * 3600)     # pre-fault baseline window (s)
FAULT = (12 * 3600, 16 * 3600)   # fault window (s)
THRESHOLD_PCT = 25.0
SEED = 1


def _window_means(obs, lo, hi):
    m = (obs["t_s"] >= lo) & (obs["t_s"] < hi) & obs["ci_per_piece_kg_obs"].notna()
    return obs.loc[m, "ci_per_piece_kg_obs"].mean(), obs.loc[m, "total_kw_obs"].mean()


def _deltas(sub):
    obs = ci.run_monitoring(sub, ci.MonitorConfig(), EF, seed=SEED)
    ci_b, p_b = _window_means(obs, *BASE)
    ci_f, p_f = _window_means(obs, *FAULT)
    return (ci_f / ci_b - 1) * 100.0, (p_f / p_b - 1) * 100.0


def _noop_columns(sub):
    """Add the columns run_monitoring expects, with a zero-power anomaly."""
    return ci.inject_anomalies(sub, ci.AnomalyConfig([ci.AnomalySpec(
        onset_hour=0, duration_minutes=1, magnitude_kw=0.0,
        onset_profile="step", affects="spindle", label="noop")]))


def main() -> None:
    # (1) throughput loss: pieces down 45%, power untouched
    s1 = _noop_columns(ci.simulate_work_center(ci.Config(seed=SEED)))
    w = (s1["t_s"] >= FAULT[0]) & (s1["t_s"] < FAULT[1])
    s1.loc[w, "pieces_rate"] = s1.loc[w, "pieces_rate"] * 0.55
    d_ci1, d_p1 = _deltas(s1)

    # (2) additive power: +2 kW spindle, throughput constant
    s2 = ci.inject_anomalies(ci.simulate_work_center(ci.Config(seed=SEED)),
                             ci.AnomalyConfig([ci.AnomalySpec(
                                 onset_hour=12, duration_minutes=240, magnitude_kw=2.0,
                                 onset_profile="step", affects="spindle", label="power")]))
    d_ci2, d_p2 = _deltas(s2)

    rows = [
        ("throughput_loss_45pct", d_ci1, d_p1, d_ci1 > THRESHOLD_PCT, d_p1 > THRESHOLD_PCT),
        ("additive_power_2kW",    d_ci2, d_p2, d_ci2 > THRESHOLD_PCT, d_p2 > THRESHOLD_PCT),
    ]
    out = os.path.join(HERE, "data", "ci_vs_power.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scenario", "delta_CI_pct", "delta_power_pct",
                    "CI_detector_fires", "power_detector_fires"])
        for r in rows:
            w.writerow([r[0], round(r[1], 1), round(r[2], 1), r[3], r[4]])

    print(f"threshold = +{THRESHOLD_PCT:.0f}%")
    for name, dci, dp, cf, pf in rows:
        print(f"  {name:22} CI {dci:+6.1f}% ({'fires' if cf else 'silent'})  "
              f"power {dp:+6.1f}% ({'fires' if pf else 'silent'})")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
