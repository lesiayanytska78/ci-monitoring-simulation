"""
run_contaminated_anchor.py  (Paper 2 revision, §4.9)
===================================================
Anchor-quality sensitivity. The held baseline assumes the anchor is established at
a healthy state. We bias the initial anchor by b (the CI over the post-anchor
window is off by b, i.e. the machine was not truly healthy when anchored) and
measure clean-day false alarms and fault detection (2 kW and 1 kW near-floor), for
the single-anchor detector and for health-gated re-anchoring.

Two failure regimes split at the slack: a low-biased anchor fails LOUD (false
alarms), a high-biased anchor fails SILENT (misses low-severity faults). The gate
corrects contamination below the gate fraction but PRESERVES it above.

N=60 per point. Output: contaminated_anchor_summary.csv
"""
from __future__ import annotations
import numpy as np, pandas as pd
import revision_common as rc
from anomaly_model import AnomalyConfig, inject_anomalies

N = 60
BIAS = [-0.25, -0.20, -0.15, -0.10, -0.05, -0.02, 0.0, 0.05, 0.10, 0.15, 0.20]
T0 = rc.T0


def _bias_first_window(obs, b, win_min=20.0):
    """Multiply the CI over the first post-anchor production window by (1+b):
    the anchor is set from an unhealthy window, so the standing baseline is off."""
    o = obs.copy()
    ci = o["ci_per_piece_kg_obs"].values.copy()
    st = o["state"].values; t = o["t_s"].values
    prod = np.where(st == "PRODUCTION")[0]
    if len(prod):
        t0 = t[prod[0]]
        win = (st == "PRODUCTION") & (t >= t0) & (t < t0 + win_min * 60.0)
        ci[win] = ci[win] * (1.0 + b)
    o["ci_per_piece_kg_obs"] = ci
    return o


def _clean(seed):
    return rc.observe(rc.clean_day(seed), seed)

def _fault(seed, kw):
    sub = rc.substrate(seed)
    return rc.observe(inject_anomalies(sub, AnomalyConfig([rc.ramp_spec(magnitude_kw=kw)])), seed)


def _fp_and_det(obs_clean, obs_f2, obs_f1, mode):
    """Return (clean FA/h, 2 kW det, 1 kW det) for a given anchor mode."""
    def al_for(o):
        ci = o["ci_per_piece_kg_obs"].values; st = o["state"].values
        valid = np.isfinite(ci) & (st == "PRODUCTION")
        B = rc.held_B(o, anchor_mode=mode, health_gate_frac=0.15)
        return rc.cusum_alert(ci, valid, B), o["t_s"].values, st
    a, t, st = al_for(obs_clean); fa = rc.fp_rate(a, st)
    a2, t2, _ = al_for(obs_f2); d2 = rc.eval_det(a2, t2)[0]
    a1, t1, _ = al_for(obs_f1); d1 = rc.eval_det(a1, t1)[0]
    return fa, d2, d1


def main():
    rows = []
    for b in BIAS:
        agg = {"single": [0.0, 0, 0], "gated": [0.0, 0, 0]}
        for s in range(N):
            oc = _bias_first_window(_clean(242 + s), b)
            o2 = _bias_first_window(_fault(42 + s, 2.0), b)
            o1 = _bias_first_window(_fault(42 + s, 1.0), b)
            for mode, key in [("shift_start", "single"), ("periodic_gated", "gated")]:
                fa, d2, d1 = _fp_and_det(oc, o2, o1, mode)
                agg[key][0] += fa; agg[key][1] += d2; agg[key][2] += d1
        row = {"bias": b,
               "single_fa_h": agg["single"][0] / N, "single_det2": agg["single"][1] / N,
               "single_det1": agg["single"][2] / N,
               "gated_fa_h": agg["gated"][0] / N, "gated_det2": agg["gated"][1] / N,
               "gated_det1": agg["gated"][2] / N}
        rows.append(row)
        print(f"  b={b:+.2f}  single FA {row['single_fa_h']:.3f}/h  det1 {row['single_det1']:.2f}"
              f"   gated FA {row['gated_fa_h']:.3f}/h  det1 {row['gated_det1']:.2f}")
    pd.DataFrame(rows).to_csv("contaminated_anchor_summary.csv", index=False)
    print("  wrote contaminated_anchor_summary.csv")


if __name__ == "__main__":
    main()
