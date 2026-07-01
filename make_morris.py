#!/usr/bin/env python3
"""
make_morris.py
==============
Morris elementary-effects screening of the MES-embedded CI-monitoring detector,
over the eight parameters most relevant to detection performance — including the
assumed nuisance parameters (offline standby power, base/auxiliary load,
throughput) flagged for uncertainty analysis.

Output metric: detection rate (fraction of seeds in which the slow-ramp spindle
fault is flagged) at each Morris sample point. mu* ranks each parameter's
influence; sigma indicates nonlinearity / interactions.

Reproduces `data/morris_screening.csv` and `figures/fig_morris_screening.png`.

Requirements: numpy, pandas, matplotlib, SALib, and the `cimonitoring` package
(``pip install .`` from the repository root, or run this script from that root).

For a publication-quality screening use N_TRAJECTORIES >= 20 and >= 10 seeds
(this raises the run count to (k+1)*N*seeds ~ 1,800+); the small defaults below
are a fast preliminary configuration.
"""
from __future__ import annotations
import csv
import os
import numpy as np

import cimonitoring as ci
from SALib.sample.morris import sample as morris_sample
from SALib.analyze.morris import analyze as morris_analyze

HERE = os.path.dirname(os.path.abspath(__file__))

# ----- screening configuration -----
N_TRAJECTORIES = 20          # Morris trajectories (r); >= 20 recommended for final
NUM_LEVELS = 4               # Morris grid levels (p)
SEEDS = list(range(1, 11))   # random seeds averaged at each sample point

PROBLEM = {
    "num_vars": 8,
    "names": ["severity_kW", "onset_ramp_s", "baseline_window_min", "sampling_s",
              "rel_threshold_pct", "offline_standby_kW", "aux_base_kW", "throughput_pph"],
    "bounds": [[1.0, 2.5], [300, 4800], [30, 120], [30, 300],
               [15, 40], [0.1, 0.4], [2.0, 3.0], [40, 80]],
}

EF = ci.CarbonConfig().static_emission_factor_kg_per_kwh


def detection_rate(x) -> float:
    """Fraction of seeds in which the slow-ramp spindle fault is detected."""
    sev, ramp, bw, samp, rel, standby, auxb, pph = x
    hits = 0
    for s in SEEDS:
        sub = ci.simulate_work_center(ci.Config(
            seed=s, offline_standby_kw=standby, aux_base_kw=auxb, pieces_per_hour=pph))
        spec = ci.AnomalySpec(onset_hour=12, duration_minutes=240, magnitude_kw=sev,
                              onset_profile="ramp", onset_ramp_seconds=float(ramp),
                              affects="spindle", label="tool-wear-like ramp")
        sub = ci.inject_anomalies(sub, ci.AnomalyConfig([spec]))
        obs = ci.run_monitoring(sub, ci.MonitorConfig(
            sampling_interval_seconds=float(samp), rel_threshold_pct=rel,
            baseline_window_minutes=bw), EF, seed=s)
        if ci.evaluate(obs, sub, [spec])["per_fault"][0]["warning_detected"]:
            hits += 1
    return hits / len(SEEDS)


def main() -> None:
    X = morris_sample(PROBLEM, N=N_TRAJECTORIES, num_levels=NUM_LEVELS)
    Y = np.array([detection_rate(x) for x in X])
    Si = morris_analyze(PROBLEM, X, Y, num_levels=NUM_LEVELS, print_to_console=False)

    out_csv = os.path.join(HERE, "data", "morris_screening.csv")
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["parameter", "mu_star", "mu_star_conf", "sigma"])
        for i in range(PROBLEM["num_vars"]):
            w.writerow([Si["names"][i], Si["mu_star"][i], Si["mu_star_conf"][i], Si["sigma"][i]])
    print(f"points={len(X)} seeds={len(SEEDS)} runs={len(X)*len(SEEDS)}; wrote {out_csv}")

    try:
        import pandas as pd, matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        df = pd.read_csv(out_csv)
        fig, ax = plt.subplots(figsize=(7, 5))
        ax.scatter(df.mu_star, df.sigma, s=45, color="#1a4f8a", zorder=3)
        for _, r in df.iterrows():
            ax.annotate(r.parameter, (r.mu_star, r.sigma), xytext=(6, 4),
                        textcoords="offset points", fontsize=8)
        mx = max(df.mu_star.max(), df.sigma.max()) * 1.15
        ax.plot([0, mx], [0, mx], ls="--", color="grey", lw=0.8,
                label="σ = μ* (strong nonlinearity/interaction)")
        ax.set_xlabel("μ*  (mean absolute elementary effect — influence on detection rate)")
        ax.set_ylabel("σ  (spread of elementary effects — nonlinearity / interactions)")
        ax.set_title("Morris elementary-effects screening (8 parameters)")
        ax.legend(fontsize=8, loc="upper left")
        ax.set_xlim(-0.02, mx); ax.set_ylim(-0.02, mx)
        fig.tight_layout()
        fig.savefig(os.path.join(HERE, "figures", "fig_morris_screening.png"), dpi=130)
        print("wrote figures/fig_morris_screening.png")
    except Exception as e:  # pragma: no cover
        print("figure skipped:", e)


if __name__ == "__main__":
    main()
