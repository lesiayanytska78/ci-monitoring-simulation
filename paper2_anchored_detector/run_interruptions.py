"""
run_interruptions.py  (Paper 2 revision, §4.12)
==============================================
Production-interruption sensitivity. The deployed detector RESETS the CUSUM
accumulator outside production, discarding evidence at every idle gap. We compare
reset with HOLD (freeze across gaps) and DECAY (forget with a 30-min half-life) on
the default schedule (runs 20-90 min) and a frequently-interrupted schedule (runs
8-15 min, gaps 8-20 min), near the detection floor.

Above the floor the strategy is immaterial; near the floor and under frequent
interruptions, reset loses evidence while decay/hold recover it -- at a false-alarm
cost (hold) vs a small one (decay).

Output: interruptions_summary.csv
"""
from __future__ import annotations
import numpy as np, pandas as pd
import revision_common as rc
from energy_substrate import Config as E, simulate_work_center
from anomaly_model import AnomalyConfig, AnomalySpec, inject_anomalies

N = 60
SCHEDULES = {
    "default":        dict(run_minutes_range=(20.0, 90.0), gap_minutes_range=(5.0, 30.0)),
    "frequent":       dict(run_minutes_range=(8.0, 15.0),  gap_minutes_range=(8.0, 20.0)),
}
SEVS = [2.0, 1.0, 0.75]
STRATS = ["reset", "hold", "decay"]


def _fault_obs(seed, sched, sev):
    cfg = E(seed=seed, **sched)
    sub = simulate_work_center(cfg)
    spec = AnomalySpec(onset_hour=10, duration_minutes=240, magnitude_kw=sev,
                       onset_profile="ramp", onset_ramp_seconds=1800.0,
                       affects="spindle", label="x")
    return rc.observe(inject_anomalies(sub, AnomalyConfig([spec])), seed)


def _clean_obs(seed, sched):
    cfg = E(seed=seed, **sched)
    sub = simulate_work_center(cfg).copy()
    sub["anomaly_kw"] = 0.0; sub["anomaly_active"] = False; sub["anomaly_labels"] = ""
    return rc.observe(sub, seed)


def main():
    rows = []
    for sname, sched in SCHEDULES.items():
        for sev in SEVS:
            res = {st: [0, []] for st in STRATS}       # [n_detected, [latencies]]
            for s in range(N):
                obs = _fault_obs(42 + s, sched, sev)
                ci = obs["ci_per_piece_kg_obs"].values; stt = obs["state"].values; t = obs["t_s"].values
                valid = np.isfinite(ci) & (stt == "PRODUCTION")
                B = rc.held_B(obs)
                for strat in STRATS:
                    al = rc.cusum_alert(ci, valid, B, gap_strategy=strat)
                    det, lat = rc.eval_det(al, t)
                    res[strat][0] += det
                    if det:
                        res[strat][1].append(lat)
            # clean-day false alarms per strategy (this schedule)
            fa = {st: [0, 0.0] for st in STRATS}
            for s in range(N):
                cobs = _clean_obs(242 + s, sched)
                cci = cobs["ci_per_piece_kg_obs"].values; cst = cobs["state"].values
                cval = np.isfinite(cci) & (cst == "PRODUCTION")
                cB = rc.held_B(cobs)
                for strat in STRATS:
                    c, e = rc.fp_count_exposure(rc.cusum_alert(cci, cval, cB, gap_strategy=strat), cst)
                    fa[strat][0] += c; fa[strat][1] += e
            for strat in STRATS:
                det = res[strat][0] / N
                lat = float(np.median(res[strat][1])) if res[strat][1] else np.nan
                r, lo, hi = rc.poisson(fa[strat][0], fa[strat][1])
                rows.append({"schedule": sname, "severity_kw": sev, "strategy": strat,
                             "detection": round(det, 3),
                             "median_latency_min": round(lat, 1) if np.isfinite(lat) else np.nan,
                             "clean_fa_per_h": round(r, 4)})
            print(f"  {sname:9s} {sev:4.2f}kW  " +
                  "  ".join(f"{st}:{res[st][0]/N:.2f}" for st in STRATS))
    pd.DataFrame(rows).to_csv("interruptions_summary.csv", index=False)
    print("  wrote interruptions_summary.csv")


if __name__ == "__main__":
    main()
