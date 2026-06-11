"""
run_paper2_comparators.py
=========================
Paper 2, #3: the ablation that isolates WHY the proposed detector works, and the
second design response named in Paper 1.

Four detectors on an IDENTICAL observed signal (2 kW spindle ramp, 4 h), swept
over onset-to-window ratio. The CUSUM is held identical (k=0.10, h=1.0) across
the three CUSUM variants, so the ONLY thing that changes is the reference the
residual is measured against:

    D0_deployed        rolling-median baseline + relative threshold (deployed)
    C1_rolling_cusum   rolling-median baseline + CUSUM     (ABLATION: no anchor)
    D2_anchored_cusum  event-anchored held baseline + CUSUM   (proposed)
    C2_model_residual  fixed model-predicted CI + CUSUM    (Bhinge-style, 2nd
                                                            design response, §5.2)

Expected: D0 and C1 collapse as onset ratio -> 1 (a tracking reference absorbs the
fault); D2 and C2 hold (a FIXED reference does not). That dissociation shows the
mechanism is the fixed reference, and the CUSUM is a refinement on top of it.

Set N_SEEDS / RAMP_SECONDS small for a quick check; 200 / full for publication.

Outputs: paper2_comparators_summary.csv, paper2_comparators_raw.csv,
         fig_paper2_comparators.png
"""
from __future__ import annotations
import time, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from energy_substrate import Config as E, simulate_work_center
from carbon_layer import CarbonConfig
from anomaly_model import AnomalyConfig, AnomalySpec, inject_anomalies
from monitoring import MonitorConfig, sample_and_noise, detect as detect_deployed
from monitoring_anchored import AnchoredMonitorConfig, held_baseline

EF = CarbonConfig().static_emission_factor_kg_per_kwh
SENSOR = MonitorConfig(sampling_interval_seconds=60.0, meter_accuracy_pct=1.0,
                       ci_estimation_window_minutes=15.0)
K, HW, HC = 0.10, 1.0, 2.0
BWS = 3600.0
WIN_N = 60          # 60-min rolling baseline window at 60 s sampling
MIN_P = 20
RAMP_SECONDS = [120, 300, 600, 1080, 1440, 1800, 2160, 2520, 2880, 3240, 3600, 5400, 7200]
SEV, DUR = 2.0, 240
N_SEEDS = 200
T0 = 10 * 3600.0
T1 = T0 + DUR * 60.0
ANCHOR = AnchoredMonitorConfig(anchor_mode="shift_start")


def _rolling_baseline(ci, valid):
    s = pd.Series(np.where(valid, ci, np.nan))
    return s.rolling(WIN_N, min_periods=MIN_P).median().values


def _cusum_alert(ci, valid, B):
    S = 0.0; out = np.zeros(len(ci), dtype=np.int8)
    for i in range(len(ci)):
        if valid[i] and np.isfinite(B[i]) and B[i] > 0:
            S = max(0.0, S + (ci[i] - B[i]) / B[i] - K)
        else:
            S = 0.0
        out[i] = 2 if S >= HC else (1 if S >= HW else 0)
    return out


def _starts(al):
    a = (al >= 1).astype(int)
    s = list(np.where(np.diff(a) == 1)[0] + 1)
    if a[0] == 1: s = [0] + s
    return np.array(s, dtype=int)


def _eval(al, t):
    st = _starts(al)
    ts = t[st] if len(st) else np.array([])
    inwin = ts[(ts >= T0) & (ts <= T1)]
    return (True, (inwin[0] - T0) / 60.0) if len(inwin) else (False, np.nan)


def _fp(al, state):
    oph = (state == "PRODUCTION").sum() * 60.0 / 3600.0
    return len(_starts(al)) / max(oph, 1e-6)


def _calibrate_ci_model(nseed=20):
    vals = []
    for s in range(nseed):
        sub = simulate_work_center(E(seed=900 + s)).copy()
        sub["anomaly_kw"] = 0.0; sub["anomaly_active"] = False; sub["anomaly_labels"] = ""
        obs = sample_and_noise(sub, SENSOR, EF, seed=900 + s + 1000)
        ci = obs["ci_per_piece_kg_obs"].values
        prod = obs["state"].values == "PRODUCTION"
        v = ci[prod & np.isfinite(ci)]
        if len(v): vals.append(np.median(v))
    return float(np.median(vals))


def _detect_all(obs, ci_model):
    ci = obs["ci_per_piece_kg_obs"].values
    state = obs["state"].values
    valid = np.isfinite(ci) & (state == "PRODUCTION")
    t = obs["t_s"].values
    out = {}
    # D0 deployed
    detect_deployed(obs, MonitorConfig()); out["D0_deployed"] = obs["alert_level"].values.copy()
    # C1 rolling-CUSUM (no anchor)
    out["C1_rolling_cusum"] = _cusum_alert(ci, valid, _rolling_baseline(ci, valid))
    # D2 anchored-CUSUM
    out["D2_anchored_cusum"] = _cusum_alert(ci, valid, held_baseline(obs, ANCHOR))
    # C2 model-based residual (fixed predicted CI) + CUSUM
    out["C2_model_residual"] = _cusum_alert(ci, valid, np.full(len(ci), ci_model))
    return out, t, state


CONFIGS = ["D0_deployed", "C1_rolling_cusum", "D2_anchored_cusum", "C2_model_residual"]


def _boot(b, nb=2000, seed=0):
    rng = np.random.default_rng(seed); v = np.asarray(b, float)
    if len(v) == 0: return (np.nan, np.nan, np.nan)
    bs = rng.choice(v, size=(nb, len(v)), replace=True).mean(axis=1)
    return v.mean(), np.percentile(bs, 2.5), np.percentile(bs, 97.5)


def main():
    t0 = time.time()
    ci_model = _calibrate_ci_model()
    print(f"  calibrated CI model = {ci_model:.5f} kgCO2e/piece  [{time.time()-t0:.0f}s]")
    raw = []
    for ri, ramp in enumerate(RAMP_SECONDS):
        for s in range(N_SEEDS):
            seed = 42 + s
            sub = simulate_work_center(E(seed=seed))
            spec = AnomalySpec(onset_hour=10, duration_minutes=DUR, magnitude_kw=SEV,
                               onset_profile="ramp", onset_ramp_seconds=ramp,
                               affects="spindle", label="x")
            obs = sample_and_noise(inject_anomalies(sub, AnomalyConfig([spec])), SENSOR, EF, seed=seed + 1000)
            alerts, t, state = _detect_all(obs, ci_model)
            for name in CONFIGS:
                det, lat = _eval(alerts[name], t)
                raw.append({"config": name, "ramp_s": ramp, "onset_ratio": ramp / BWS,
                            "seed": seed, "detected": det, "latency_min": lat})
        print(f"  ramp {ri+1}/{len(RAMP_SECONDS)} ({ramp}s) done  [{time.time()-t0:.0f}s]")

    fp = {n: [] for n in CONFIGS}
    for s in range(N_SEEDS):
        sub = simulate_work_center(E(seed=242 + s)).copy()
        sub["anomaly_kw"] = 0.0; sub["anomaly_active"] = False; sub["anomaly_labels"] = ""
        obs = sample_and_noise(sub, SENSOR, EF, seed=242 + s + 1000)
        alerts, t, state = _detect_all(obs, ci_model)
        for n in CONFIGS: fp[n].append(_fp(alerts[n], state))
    fp_mean = {n: float(np.mean(v)) for n, v in fp.items()}

    df = pd.DataFrame(raw); df.to_csv("paper2_comparators_raw.csv", index=False)
    rows = []
    for (cfg, ramp, ratio), g in df.groupby(["config", "ramp_s", "onset_ratio"]):
        m, lo, hi = _boot(g["detected"].values, seed=int(ramp))
        lat = pd.to_numeric(g["latency_min"], errors="coerce")
        rows.append({"config": cfg, "ramp_s": ramp, "onset_ratio": ratio,
                     "detection_rate": m, "ci_lo": lo, "ci_hi": hi,
                     "median_latency_min": float(np.nanmedian(lat)) if lat.notna().any() else np.nan,
                     "mean_fp_rate": fp_mean[cfg]})
    summ = pd.DataFrame(rows); summ.to_csv("paper2_comparators_summary.csv", index=False)

    col = {"D0_deployed": "#c0392b", "C1_rolling_cusum": "#e67e22",
           "D2_anchored_cusum": "#27ae60", "C2_model_residual": "#2980b9"}
    mk = {"D0_deployed": "o", "C1_rolling_cusum": "v", "D2_anchored_cusum": "D", "C2_model_residual": "s"}
    lab = {"D0_deployed": "D0  deployed (rolling threshold)",
           "C1_rolling_cusum": "C1  rolling-median + CUSUM  (no anchor)",
           "D2_anchored_cusum": "D2  anchored + CUSUM  (proposed)",
           "C2_model_residual": "C2  model-predicted CI + CUSUM  (Bhinge-style)"}
    fig, ax = plt.subplots(figsize=(8, 5.6))
    for c in CONFIGS:
        d = summ[summ.config == c].sort_values("onset_ratio")
        ax.plot(d.onset_ratio, d.detection_rate * 100, marker=mk[c], color=col[c], lw=2, ms=6,
                label=f"{lab[c]}  (FP {fp_mean[c]:.3f}/h)")
        ax.fill_between(d.onset_ratio, d.ci_lo * 100, d.ci_hi * 100, color=col[c], alpha=0.15)
    ax.axhline(80, color="grey", ls=":", lw=1); ax.axvline(1.0, color="grey", ls="--", lw=1)
    ax.set_xlabel("onset-to-window ratio  (ramp time / baseline window)")
    ax.set_ylabel("detection rate (%)"); ax.set_ylim(-3, 103)
    ax.set_title("Ablation: identical CUSUM, different reference\n"
                 "a tracking reference fails; a fixed reference (anchor or model) succeeds")
    ax.legend(fontsize=8, loc="lower left"); ax.grid(alpha=0.25)
    fig.tight_layout(); fig.savefig("fig_paper2_comparators.png", dpi=150)

    pd.set_option("display.width", 170)
    print("\n=== DETECTION RATE (%) ===")
    print((summ.pivot(index="onset_ratio", columns="config", values="detection_rate")[CONFIGS] * 100).round(0).astype("Int64"))
    print("\n=== MEAN FP (warn/prod-hour) ===")
    for n in CONFIGS: print(f"  {n:20s} {fp_mean[n]:.4f}")
    print(f"\nDone in {time.time()-t0:.0f}s.  Wrote summary, raw, fig_paper2_comparators.png")


if __name__ == "__main__":
    main()
