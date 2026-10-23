"""
run_regime_change.py  (Paper 2 revision, §4.8)
=============================================
Legitimate regime changes: the two faces of the reference. On clean days we inject
a legitimate sustained rise g in CI-per-piece at hour 10 (a higher-energy product
or a feed-rate change); every warning after the change is, by construction, FALSE.
We measure the day-level false-alarm probability for the adaptive deployed detector
(D0) and three fixed-reference configurations (shift-start anchor, periodic+gate,
periodic unconditional).

The adaptive baseline follows a legitimate change (its vice is the same tracking
that absorbs a slow fault); a single held anchor alarms on any change above the
slack; the gate parameterises but cannot escape the trade-off. Resolution: a known
changeover should fire a CONFIRMED re-anchor, not be left to the detector.

N=100 clean seeds per point. Output: regime_change_summary.csv
"""
from __future__ import annotations
import numpy as np, pandas as pd
import revision_common as rc

N = 100
G = [0.0, 0.05, 0.10, 0.125, 0.15, 0.20, 0.30]
T0 = rc.T0


def regime_obs(seed, g):
    """Clean day whose observed CI is multiplied by (1+g) during production, t>=T0."""
    obs = rc.observe(rc.clean_day(seed), seed)
    ci = obs["ci_per_piece_kg_obs"].values.copy()
    t = obs["t_s"].values; st = obs["state"].values
    hit = (st == "PRODUCTION") & (t >= T0) & np.isfinite(ci)
    ci[hit] = ci[hit] * (1.0 + g)
    obs["ci_per_piece_kg_obs"] = ci
    return obs


def _false_after(al, t):
    ts = t[rc.starts(al)] if len(rc.starts(al)) else np.array([])
    return 1 if len(ts[ts >= T0]) else 0


def main():
    rows = []
    for g in G:
        fa = {"D0": 0, "D2_shift": 0, "D2_gated": 0, "D2_uncond": 0}
        for s in range(N):
            obs = regime_obs(242 + s, g)
            ci = obs["ci_per_piece_kg_obs"].values; st = obs["state"].values; t = obs["t_s"].values
            valid = np.isfinite(ci) & (st == "PRODUCTION")
            fa["D0"] += _false_after(rc.D0(obs.copy()), t)
            fa["D2_shift"] += _false_after(
                rc.cusum_alert(ci, valid, rc.held_B(obs, anchor_mode="shift_start")), t)
            fa["D2_gated"] += _false_after(
                rc.cusum_alert(ci, valid, rc.held_B(obs, anchor_mode="periodic_gated",
                                                    health_gate_frac=0.15)), t)
            fa["D2_uncond"] += _false_after(
                rc.cusum_alert(ci, valid, rc.held_B(obs, anchor_mode="periodic")), t)
        row = {"g": g}
        for k, v in fa.items():
            row[k] = v / N
        rows.append(row)
        print(f"  g={g*100:4.1f}%  D0 {fa['D0']/N:.2f}  D2-shift {fa['D2_shift']/N:.2f}  "
              f"gated {fa['D2_gated']/N:.2f}  uncond {fa['D2_uncond']/N:.2f}")
    pd.DataFrame(rows).to_csv("regime_change_summary.csv", index=False)
    print("  wrote regime_change_summary.csv")


if __name__ == "__main__":
    main()
