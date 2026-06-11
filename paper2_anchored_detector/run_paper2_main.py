"""
run_paper2_main.py
==================
Paper 2 main analysis at publication rigor (#1 + #2 combined).

Re-runs the detector comparison AND the anchor-mode robustness study at 200 seeds
per point, with 95% bootstrap confidence intervals, using the calibrated CUSUM
operating point selected in sweep_cusum_roc.py:

    k = 0.10,  h_warn = 1.0,  h_crit = 2.0
    (lowest latency subject to false-alarm rate <= the deployed detector D0)

Five configurations on an IDENTICAL observed signal (2 kW spindle ramp, 4 h),
swept over onset-to-window ratio:
    D0_deployed        rolling-median relative threshold (the inertia collapse)
    D1_anchored        event-anchored held baseline + threshold
    D2_anchored_cusum  event-anchored held baseline + residual CUSUM   (proposed)
    D2_periodic        proposed detector, NAIVE periodic re-anchoring
    D2_periodic_gated  proposed detector, HEALTH-GATED re-anchoring

Efficiency: the sensor/CI stage is computed ONCE per (seed, ramp); all five
detectors are applied to that same observed signal. Runtime ~5-8 min.

Outputs:
    paper2_summary.csv   detection rate + 95% CI + latency + FP, per config x ratio
    paper2_raw.csv       one row per (config, ramp, seed)
    fig_paper2_detection.png
    fig_paper2_anchor_modes.png
"""
from __future__ import annotations
import time, numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from energy_substrate import Config as E, simulate_work_center
from carbon_layer import CarbonConfig
from anomaly_model import AnomalyConfig, AnomalySpec, inject_anomalies
from monitoring import MonitorConfig, sample_and_noise, detect as detect_deployed
from monitoring_anchored import AnchoredMonitorConfig, detect_anchored

EF = CarbonConfig().static_emission_factor_kg_per_kwh
SENSOR = MonitorConfig(sampling_interval_seconds=60.0, meter_accuracy_pct=1.0,
                       ci_estimation_window_minutes=15.0)
K, HW, HC = 0.10, 1.0, 2.0                       # calibrated operating point
BWS = 3600.0                                     # 60-min baseline window
RAMP_SECONDS = [120, 300, 600, 1080, 1440, 1800, 2160, 2520, 2880, 3240, 3600, 5400, 7200]
SEV, DUR = 2.0, 240
N_SEEDS = 200
T0 = 10 * 3600.0
T1 = T0 + DUR * 60.0

def _cusum_cfg(mode):
    return AnchoredMonitorConfig(detector="anchored_cusum", anchor_mode=mode,
                                 anchor_period_minutes=120.0,
                                 cusum_k_frac=K, cusum_h_warn=HW, cusum_h_crit=HC)

DETECTORS = {
    "D0_deployed":       lambda o: detect_deployed(o, MonitorConfig()),
    "D1_anchored":       lambda o: detect_anchored(o, AnchoredMonitorConfig(
                                        detector="anchored_threshold", anchor_mode="shift_start")),
    "D2_anchored_cusum": lambda o: detect_anchored(o, _cusum_cfg("shift_start")),
    "D2_periodic":       lambda o: detect_anchored(o, _cusum_cfg("periodic")),
    "D2_periodic_gated": lambda o: detect_anchored(o, _cusum_cfg("periodic_gated")),
}

def _starts(al):
    a = (al >= 1).astype(int)
    s = list(np.where(np.diff(a) == 1)[0] + 1)
    if a[0] == 1: s = [0] + s
    return np.array(s, dtype=int)

def _eval(obs):
    al = obs["alert_level"].values
    st = _starts(al)
    t = obs["t_s"].values
    ts = t[st] if len(st) else np.array([])
    inwin = ts[(ts >= T0) & (ts <= T1)]
    if len(inwin):
        return True, (inwin[0] - T0) / 60.0
    return False, np.nan

def _fp(obs):
    al = obs["alert_level"].values
    oph = (obs["state"].values == "PRODUCTION").sum() * 60.0 / 3600.0
    return len(_starts(al)) / max(oph, 1e-6)

def _boot(bools, nb=2000, seed=0):
    rng = np.random.default_rng(seed)
    v = np.asarray(bools, float)
    if len(v) == 0: return (np.nan, np.nan, np.nan)
    bs = rng.choice(v, size=(nb, len(v)), replace=True).mean(axis=1)
    return v.mean(), np.percentile(bs, 2.5), np.percentile(bs, 97.5)

def main():
    t0 = time.time(); raw = []
    for ri, ramp in enumerate(RAMP_SECONDS):
        for s in range(N_SEEDS):
            seed = 42 + s
            sub = simulate_work_center(E(seed=seed))
            spec = AnomalySpec(onset_hour=10, duration_minutes=DUR, magnitude_kw=SEV,
                               onset_profile="ramp", onset_ramp_seconds=ramp,
                               affects="spindle", label="x")
            subA = inject_anomalies(sub, AnomalyConfig([spec]))
            obs = sample_and_noise(subA, SENSOR, EF, seed=seed + 1000)
            for name, fn in DETECTORS.items():
                fn(obs)                       # writes obs['alert_level']
                det, lat = _eval(obs)
                raw.append({"config": name, "ramp_s": ramp,
                            "onset_ratio": ramp / BWS, "seed": seed,
                            "detected": det, "latency_min": lat})
        print(f"  ramp {ri+1}/{len(RAMP_SECONDS)} ({ramp}s) done  [{time.time()-t0:.0f}s]")

    # false-positive rate per detector (anomaly-free days)
    fp = {name: [] for name in DETECTORS}
    for s in range(N_SEEDS):
        sub = simulate_work_center(E(seed=242 + s)).copy()
        sub["anomaly_kw"] = 0.0; sub["anomaly_active"] = False; sub["anomaly_labels"] = ""
        obs = sample_and_noise(sub, SENSOR, EF, seed=242 + s + 1000)
        for name, fn in DETECTORS.items():
            fn(obs); fp[name].append(_fp(obs))
    fp_mean = {k: float(np.mean(v)) for k, v in fp.items()}
    print("  FP done")

    df = pd.DataFrame(raw); df.to_csv("paper2_raw.csv", index=False)
    rows = []
    for (cfg, ramp, ratio), g in df.groupby(["config", "ramp_s", "onset_ratio"]):
        m, lo, hi = _boot(g["detected"].values, seed=int(ramp))
        lat = pd.to_numeric(g["latency_min"], errors="coerce")
        rows.append({"config": cfg, "ramp_s": ramp, "onset_ratio": ratio,
                     "detection_rate": m, "ci_lo": lo, "ci_hi": hi,
                     "median_latency_min": float(np.nanmedian(lat)) if lat.notna().any() else np.nan,
                     "mean_fp_rate": fp_mean[cfg], "n": len(g)})
    summ = pd.DataFrame(rows); summ.to_csv("paper2_summary.csv", index=False)

    # ---------- figures ----------
    def plot(configs, fname, title):
        col = {"D0_deployed": "#c0392b", "D1_anchored": "#2980b9",
               "D2_anchored_cusum": "#27ae60", "D2_periodic": "#e67e22",
               "D2_periodic_gated": "#8e44ad"}
        mk = {"D0_deployed": "o", "D1_anchored": "s", "D2_anchored_cusum": "D",
              "D2_periodic": "v", "D2_periodic_gated": "^"}
        fig, (ax, ax2) = plt.subplots(1, 2, figsize=(13.5, 5.3))
        for c in configs:
            d = summ[summ.config == c].sort_values("onset_ratio")
            ax.plot(d.onset_ratio, d.detection_rate * 100, marker=mk[c], color=col[c],
                    lw=2, ms=6, label=f"{c}  (FP {fp_mean[c]:.3f}/h)")
            ax.fill_between(d.onset_ratio, d.ci_lo * 100, d.ci_hi * 100, color=col[c], alpha=0.15)
            ax2.plot(d.onset_ratio, d.median_latency_min, marker=mk[c], color=col[c],
                     lw=2, ms=6, label=c)
        ax.axhline(80, color="grey", ls=":", lw=1); ax.axvline(1.0, color="grey", ls="--", lw=1)
        ax.set_xlabel("onset-to-window ratio"); ax.set_ylabel("detection rate (%)")
        ax.set_ylim(-3, 103); ax.set_title(title); ax.legend(fontsize=8, loc="lower left"); ax.grid(alpha=0.25)
        ax2.set_xlabel("onset-to-window ratio"); ax2.set_ylabel("median warning latency (min)")
        ax2.set_title("Warning latency"); ax2.legend(fontsize=8); ax2.grid(alpha=0.25)
        fig.suptitle(f"200 seeds/point, 95% bootstrap CIs · CUSUM k={K}, h={HW}", fontsize=11)
        fig.tight_layout(rect=[0, 0, 1, 0.95]); fig.savefig(fname, dpi=150)
        print("wrote", fname)

    plot(["D0_deployed", "D1_anchored", "D2_anchored_cusum"],
         "fig_paper2_detection.png", "Closing the inertia blind spot")
    plot(["D0_deployed", "D2_anchored_cusum", "D2_periodic", "D2_periodic_gated"],
         "fig_paper2_anchor_modes.png", "Re-anchoring hazard and health-gating fix")

    # ---------- console summary ----------
    pd.set_option("display.width", 170)
    piv = summ.pivot(index="onset_ratio", columns="config", values="detection_rate")
    print("\n=== DETECTION RATE (%) ===")
    print((piv * 100).round(0).astype("Int64"))
    print("\n=== MEAN FALSE-POSITIVE RATE (warnings/production-hour) ===")
    for k_, v in fp_mean.items(): print(f"  {k_:20s} {v:.4f}")
    print(f"\nDone in {time.time()-t0:.0f}s.  Wrote paper2_summary.csv, paper2_raw.csv, 2 figures.")

if __name__ == "__main__":
    main()
