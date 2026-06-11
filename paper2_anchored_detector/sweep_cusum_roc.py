"""
sweep_cusum_roc.py
==================
Operating-point selection for the anchored + residual-CUSUM detector (Paper 2, #2).

The CUSUM slack k and decision interval h trade false alarms against detection
speed/power. This script calibrates them: it sweeps (k, h), measuring on an
IDENTICAL observed signal
  - detection rate + median latency on hard inertia-regime faults, and
  - false-alarm rate on anomaly-free days,
then reports the ROC so a defensible operating point (false-positive rate matched
to the deployed detector D0) can be chosen rather than hand-set.

Efficiency: the sensor/CI stage (sample_and_noise) and the held baseline are
computed ONCE per seed; only the cheap CUSUM detection step is repeated across
(k, h). A lightweight in-window detection check replaces evaluate().

Outputs: cusum_roc.csv  (one row per k, h)
"""
from __future__ import annotations
import numpy as np, pandas as pd, time
from energy_substrate import Config as E, simulate_work_center
from carbon_layer import CarbonConfig
from anomaly_model import AnomalyConfig, AnomalySpec, inject_anomalies
from monitoring import MonitorConfig, sample_and_noise, run_monitoring
from monitoring_anchored import AnchoredMonitorConfig, held_baseline

EF = CarbonConfig().static_emission_factor_kg_per_kwh
SENSOR = MonitorConfig(sampling_interval_seconds=60.0, meter_accuracy_pct=1.0,
                       ci_estimation_window_minutes=15.0)
ANCHOR = AnchoredMonitorConfig(anchor_mode="shift_start")

K_GRID = [0.05, 0.10, 0.15, 0.20, 0.30]
H_GRID = [0.1, 0.2, 0.3, 0.4, 0.6, 0.8, 1.0, 1.5, 2.0, 3.0]
N_SEEDS = 40
FAULTS = {"2.0kW": (2.0, 3600.0), "1.25kW": (1.25, 3600.0)}  # both at onset ratio 1.0
T0 = 10 * 3600.0
T1 = T0 + 240 * 60.0


def _cusum(ci, valid, B, k, h):
    S = 0.0
    out = np.zeros(len(ci), dtype=np.int8)
    for i in range(len(ci)):
        if valid[i] and np.isfinite(B[i]) and B[i] > 0:
            S = max(0.0, S + (ci[i] - B[i]) / B[i] - k)
        else:
            S = 0.0
        if S >= h:
            out[i] = 1
    return out


def _starts(alert):
    a = (alert >= 1).astype(int)
    s = list(np.where(np.diff(a) == 1)[0] + 1)
    if a[0] == 1:
        s = [0] + s
    return np.array(s, dtype=int)


def _prep(seed, sev, ramp_s, with_anom):
    sub = simulate_work_center(E(seed=seed))
    if with_anom:
        spec = AnomalySpec(onset_hour=10, duration_minutes=240, magnitude_kw=sev,
                           onset_profile="ramp", onset_ramp_seconds=ramp_s,
                           affects="spindle", label="x")
        sub = inject_anomalies(sub, AnomalyConfig([spec]))
    else:
        sub = sub.copy(); sub["anomaly_kw"] = 0.0
        sub["anomaly_active"] = False; sub["anomaly_labels"] = ""
    obs = sample_and_noise(sub, SENSOR, EF, seed=seed + 1000)
    B = held_baseline(obs, ANCHOR)
    ci = obs["ci_per_piece_kg_obs"].values
    valid = np.isfinite(ci) & (obs["state"].values == "PRODUCTION")
    obs_t = obs["t_s"].values
    prod_hours = (obs["state"].values == "PRODUCTION").sum() * 60.0 / 3600.0
    return ci, valid, B, obs_t, prod_hours


def main():
    t0 = time.time()
    faulted = {name: [_prep(42 + s, sev, ramp, True) for s in range(N_SEEDS)]
               for name, (sev, ramp) in FAULTS.items()}
    free = [_prep(242 + s, 0, 0, False) for s in range(N_SEEDS)]
    print(f"  prepped {N_SEEDS} seeds in {time.time()-t0:.0f}s")

    # D0 deployed reference false-positive rate
    d0 = []
    for s in range(N_SEEDS):
        sub = simulate_work_center(E(seed=242 + s)).copy()
        sub["anomaly_kw"] = 0.0; sub["anomaly_active"] = False; sub["anomaly_labels"] = ""
        obs = run_monitoring(sub, MonitorConfig(), EF, seed=242 + s + 1000)
        al = obs["alert_level"].values
        n = len(_starts(al))
        oph = (obs["state"].values == "PRODUCTION").sum() * 60.0 / 3600.0
        d0.append(n / max(oph, 1e-6))
    D0_FP = float(np.mean(d0))
    print(f"  D0 reference FP rate: {D0_FP:.4f}/prod-hour ({time.time()-t0:.0f}s)")

    rows = []
    for k in K_GRID:
        for h in H_GRID:
            rec = {"k": k, "h": h}
            for name in FAULTS:
                det = []; lat = []
                for (ci, valid, B, obs_t, _) in faulted[name]:
                    al = _cusum(ci, valid, B, k, h)
                    st = _starts(al)
                    ts = obs_t[st] if len(st) else np.array([])
                    inwin = ts[(ts >= T0) & (ts <= T1)]
                    if len(inwin):
                        det.append(True); lat.append((inwin[0] - T0) / 60.0)
                    else:
                        det.append(False)
                rec[f"det_{name}"] = float(np.mean(det))
                rec[f"lat_{name}"] = float(np.median(lat)) if lat else np.nan
            fps = []
            for (ci, valid, B, obs_t, ph) in free:
                al = _cusum(ci, valid, B, k, h)
                fps.append(len(_starts(al)) / max(ph, 1e-6))
            rec["fp_rate"] = float(np.mean(fps))
            rows.append(rec)
    df = pd.DataFrame(rows); df["D0_fp_ref"] = D0_FP
    df.to_csv("cusum_roc.csv", index=False)

    target_fp = max(D0_FP, 0.02)
    cand = df[df.fp_rate <= target_fp]
    cand = (cand if len(cand) else df).sort_values(
        ["det_2.0kW", "lat_2.0kW"], ascending=[False, True])
    pick = cand.iloc[0]

    pd.set_option("display.width", 160)
    show = df.copy()
    show["det_2.0kW"] = (show["det_2.0kW"] * 100).round(0)
    show["det_1.25kW"] = (show["det_1.25kW"] * 100).round(0)
    print("\n=== CUSUM ROC (det % at onset ratio 1.0; latency min; fp/prod-hour) ===")
    print(show[["k", "h", "det_2.0kW", "lat_2.0kW", "det_1.25kW", "fp_rate"]].to_string(index=False))
    print(f"\nTarget FP <= {target_fp:.4f}  (D0 ref {D0_FP:.4f})")
    print(f">>> CHOSEN OPERATING POINT: k={pick.k}, h={pick.h}  "
          f"(det@2kW={pick['det_2.0kW']*100:.0f}%, lat={pick['lat_2.0kW']:.1f}min, "
          f"fp={pick.fp_rate:.4f}/h)")
    print(f"Done in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
