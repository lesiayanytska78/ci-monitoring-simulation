#!/usr/bin/env python3
"""
make_paper2_sensitivity.py
==========================
Morris elementary-effects screening of the *event-anchored + residual-CUSUM*
detector's own parameters (Paper 2). Because the detector recovers detection to
~100% across the inertia regime, detection rate is at ceiling and uninformative;
the screening therefore targets the two decision-relevant outputs the operating
point actually trades off:

  * warning latency (minutes) on a hard inertia-regime fault (2 kW spindle ramp
    at onset-to-window ratio 1.0);
  * false-alarm rate (warnings per production-hour) on anomaly-free days.

Five parameters are screened, in the health-gated periodic configuration so that
all of them are active:

  cusum_k_frac                slack (fractional excess ignored)      [0.05, 0.20]
  cusum_h_warn                CUSUM decision interval (warning)      [0.5, 2.0]
  post_anchor_baseline_minutes  window used to set the held baseline [10, 40]
  health_gate_frac            re-anchor rejection threshold          [0.05, 0.30]
  anchor_period_minutes       periodic re-anchoring cadence          [60, 240]

mu* ranks each parameter's influence; sigma indicates nonlinearity/interaction.

Writes data/paper2_sensitivity.csv and figures/fig_paper2_sensitivity.png.

Resolution is set by env vars (defaults reproduce the values reported in the
paper — 72 sample points, 8 seeds, 1,152 detector runs):
  P2_TRAJ   Morris trajectories r   (default 12)
  P2_SEEDS  seeds averaged per point (default 8)
Raising both tightens the estimates; the parameter ranking is stable.

Requires numpy, pandas, matplotlib, SALib, and the `cimonitoring` package
(`pip install .` from the repository root, or run from that root).
"""
from __future__ import annotations
import csv, os
import numpy as np
import cimonitoring as ci
from SALib.sample.morris import sample as morris_sample
from SALib.analyze.morris import analyze as morris_analyze

HERE = os.path.dirname(os.path.abspath(__file__))
N_TRAJ = int(os.environ.get("P2_TRAJ", "12"))
NUM_LEVELS = 4
SEEDS = list(range(1, int(os.environ.get("P2_SEEDS", "8")) + 1))
EF = ci.CarbonConfig().static_emission_factor_kg_per_kwh
HORIZON_MIN = 240.0          # 4 h fault horizon; undetected -> horizon latency

PROBLEM = {
    "num_vars": 5,
    "names": ["cusum_k_frac", "cusum_h_warn", "post_anchor_min",
              "health_gate_frac", "anchor_period_min"],
    "bounds": [[0.05, 0.20], [0.5, 2.0], [10, 40], [0.05, 0.30], [60, 240]],
}


def _cfg(x):
    k, hw, paw, gate, period = x
    return ci.AnchoredMonitorConfig(
        detector="anchored_cusum", anchor_mode="periodic_gated",
        cusum_k_frac=float(k), cusum_h_warn=float(hw), cusum_h_crit=float(hw) + 1.0,
        post_anchor_baseline_minutes=float(paw), health_gate_frac=float(gate),
        anchor_period_minutes=float(period))


def outputs(x):
    """Return (mean warning latency on the hard fault, false-alarm rate /h)."""
    lats, fps = [], []
    for s in SEEDS:
        # (1) hard inertia-regime fault: 2 kW ramp at ratio 1.0 (3600 s)
        sub = ci.simulate_work_center(ci.Config(seed=s))
        spec = ci.AnomalySpec(onset_hour=12, duration_minutes=240, magnitude_kw=2.0,
                              onset_profile="ramp", onset_ramp_seconds=3600.0,
                              affects="spindle", label="ramp")
        sub = ci.inject_anomalies(sub, ci.AnomalyConfig([spec]))
        obs = ci.run_monitoring_anchored(sub, _cfg(x), EF, seed=s)
        ev = ci.evaluate(obs, sub, [spec])["per_fault"][0]
        lats.append(ev["warning_latency_min"] if ev["warning_detected"] else HORIZON_MIN)
        # (2) anomaly-free day: false-alarm rate
        clean = ci.simulate_work_center(ci.Config(seed=s)).copy()
        clean["anomaly_kw"] = 0.0; clean["anomaly_active"] = False; clean["anomaly_labels"] = ""
        ob2 = ci.run_monitoring_anchored(clean, _cfg(x), EF, seed=s)
        prod_h = (ob2["state"].values == "PRODUCTION").sum() * \
                 (ob2["t_s"].iloc[1] - ob2["t_s"].iloc[0]) / 3600.0
        warns = int((ob2["alert_level"].values >= 1).sum())
        fps.append(warns / prod_h if prod_h > 0 else 0.0)
    return float(np.mean(lats)), float(np.mean(fps))


def main():
    X = morris_sample(PROBLEM, N=N_TRAJ, num_levels=NUM_LEVELS, seed=12345)
    Y = np.array([outputs(x) for x in X])
    Si_lat = morris_analyze(PROBLEM, X, Y[:, 0], num_levels=NUM_LEVELS, print_to_console=False)
    Si_fa = morris_analyze(PROBLEM, X, Y[:, 1], num_levels=NUM_LEVELS, print_to_console=False)

    out = os.path.join(HERE, "data", "paper2_sensitivity.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["parameter", "mu_star_latency_min", "sigma_latency_min",
                    "mu_star_fa_per_h", "sigma_fa_per_h"])
        for i in range(PROBLEM["num_vars"]):
            w.writerow([PROBLEM["names"][i],
                        round(Si_lat["mu_star"][i], 3), round(Si_lat["sigma"][i], 3),
                        round(Si_fa["mu_star"][i], 5), round(Si_fa["sigma"][i], 5)])
    print(f"points={len(X)} seeds={len(SEEDS)} runs={len(X)*len(SEEDS)*2}; wrote {out}")
    for i in range(PROBLEM["num_vars"]):
        print(f"  {PROBLEM['names'][i]:20} latency mu*={Si_lat['mu_star'][i]:6.2f} min   "
              f"FA mu*={Si_fa['mu_star'][i]:.4f}/h")

    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        import pandas as pd
        df = pd.read_csv(out)
        fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
        ax[0].barh(df.parameter, df.mu_star_latency_min, color="#1a4f8a")
        ax[0].set_xlabel("μ*  (mean |elementary effect| on warning latency, min)")
        ax[0].set_title("Sensitivity of warning latency")
        ax[1].barh(df.parameter, df.mu_star_fa_per_h, color="#8a1a4f")
        ax[1].set_xlabel("μ*  (mean |elementary effect| on false-alarm rate, /h)")
        ax[1].set_title("Sensitivity of false-alarm rate")
        for a in ax: a.invert_yaxis()
        fig.tight_layout()
        fig.savefig(os.path.join(HERE, "figures", "fig_paper2_sensitivity.png"), dpi=130)
        print("wrote figures/fig_paper2_sensitivity.png")
    except Exception as e:  # pragma: no cover
        print("figure skipped:", e)


if __name__ == "__main__":
    main()
