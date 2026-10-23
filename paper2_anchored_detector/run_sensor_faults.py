"""
run_sensor_faults.py  (Paper 2 revision, §4.14)
==============================================
Sensor-fault modes on the CI channel: measurement bias, calibration drift, a
frozen (stuck) sensor, and dropout. The question is whether a fixed-reference
detector can tell a SENSOR fault from a PROCESS fault.

  A) CLEAN day + a positive sensor fault -> does it false-alarm? A bias or drift
     raises CI above the held reference and is, by construction, indistinguishable
     from a process fault, so the detector fires.
  B) FAULT day (real 2 kW fault) + a sensor fault -> is the detector blinded? A
     frozen sensor is the one silent-failure mode; dropout is benign.

Operating point k=0.10, h=1.0, N=40 per point. Output: sensor_faults_summary.csv
"""
from __future__ import annotations
import numpy as np, pandas as pd
import revision_common as rc
from anomaly_model import AnomalyConfig, inject_anomalies

N = 40
T0 = rc.T0


def clean_obs(seed):
    return rc.observe(rc.clean_day(seed), seed)

def fault_obs(seed):
    sub = rc.substrate(seed)
    return rc.observe(inject_anomalies(sub, AnomalyConfig([rc.ramp_spec()])), seed)

def apply_sensor(obs, mode, mag, rng):
    o = obs.copy()
    ci = o["ci_per_piece_kg_obs"].values.copy()
    t = o["t_s"].values
    prod = (o["state"].values == "PRODUCTION")
    aft = (t >= T0)
    if mode == "bias":
        ci = np.where(prod & aft, ci * (1 + mag), ci)
    elif mode == "drift":                                  # +mag per hour
        ci = np.where(prod & aft, ci * (1 + mag * (t - T0) / 3600.0), ci)
    elif mode == "frozen":
        idx = np.where(prod & aft)[0]
        if len(idx):
            ci[idx] = ci[idx[0]]                           # hold at freeze-start value
    elif mode == "dropout":
        m = prod & aft & (rng.random(len(ci)) < mag)
        ci[m] = np.nan                                     # mag fraction of samples drop
    o["ci_per_piece_kg_obs"] = ci
    return o

D2 = dict(k=rc.K, hw=rc.HW, hc=rc.HC)


def _det(o):
    ci = o["ci_per_piece_kg_obs"].values; st = o["state"].values; t = o["t_s"].values
    valid = np.isfinite(ci) & (st == "PRODUCTION")
    B = rc.held_B(o, anchor_mode="shift_start")
    al = rc.cusum_alert(ci, valid, B)
    return al, t


def main():
    rows = []
    print("A) CLEAN day + sensor fault -> false-alarm probability:")
    for mode, mags in [("bias", [0.02, 0.05, 0.10]), ("drift", [0.02, 0.05, 0.10])]:
        for mag in mags:
            fa = 0
            for s in range(N):
                rng = np.random.default_rng(500 + s)
                o = apply_sensor(clean_obs(242 + s), mode, mag, rng)
                al, t = _det(o)
                ts = t[rc.starts(al)] if len(rc.starts(al)) else np.array([])
                fa += 1 if len(ts[ts >= T0]) else 0
            lo, hi = rc.wilson(fa, N)
            unit = "/h" if mode == "drift" else "  "
            print(f"   {mode:7} {int(mag*100):>3}%{unit} -> FA prob {fa/N:.3f} [{lo:.3f},{hi:.3f}]")
            rows.append(dict(part="clean", mode=mode, mag=mag, fa_prob=round(fa/N, 3),
                             lo=round(lo, 3), hi=round(hi, 3)))

    print("\nB) FAULT day (2 kW fault) + sensor fault -> detection:")
    base = 0
    for s in range(N):
        al, t = _det(fault_obs(42 + s)); base += rc.eval_det(al, t)[0]
    print(f"   (baseline, no sensor fault): detection {base/N:.2f}")
    for mode, mag in [("frozen", 0.0), ("dropout", 0.1), ("dropout", 0.3)]:
        d = 0
        for s in range(N):
            rng = np.random.default_rng(700 + s)
            o = apply_sensor(fault_obs(42 + s), mode, mag, rng)
            al, t = _det(o); d += rc.eval_det(al, t)[0]
        lo, hi = rc.wilson(d, N)
        tag = f"{int(mag*100)}%" if mode == "dropout" else "at onset"
        print(f"   {mode:7} {tag:>8} -> detection {d/N:.3f} [{lo:.3f},{hi:.3f}]")
        rows.append(dict(part="fault", mode=f"{mode}_{mag}", mag=mag, det=round(d/N, 3),
                         lo=round(lo, 3), hi=round(hi, 3)))
    pd.DataFrame(rows).to_csv("sensor_faults_summary.csv", index=False)
    print("\n  wrote sensor_faults_summary.csv")


if __name__ == "__main__":
    main()
