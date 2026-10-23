"""
redraw_figs.py  (Paper 2 revision, §3.4)
=======================================
Redraw the headline figures (detection, re-anchoring, ablation, severity, real-data)
with binomial (Wilson score) 95% error bars read from results/*_summary_binom.csv
produced by recompute_intervals.py -- replacing the degenerate percentile-bootstrap
bands. Writes figures/fig_paper2_*_wilson.png.
"""
from __future__ import annotations
import os, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

R, F = "results", "figures"
os.makedirs(F, exist_ok=True)
COL = {"D0_deployed": "#B44A2E", "D1_anchored": "#8C6D31", "D2_anchored_cusum": "#1F6F8B",
       "C1_rolling_cusum": "#8A8D91", "C2_model_residual": "#5B8C5A",
       "D2_periodic": "#C08457", "D2_periodic_gated": "#3D5A80"}
plt.rcParams.update({"font.size": 10, "axes.grid": True, "grid.alpha": 0.25,
                     "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 150})


def ser(df, cfg):
    d = df[df.config == cfg].sort_values("onset_ratio")
    return (d.onset_ratio.values, d.detection_rate.values * 100,
            d.wilson_lo.values * 100, d.wilson_hi.values * 100, d)


def plot(ax, df, cfg, label, ls="-", mk="o"):
    x, y, lo, hi, _ = ser(df, cfg)
    ax.errorbar(x, y, yerr=np.vstack([y - lo, hi - y]), label=label, color=COL[cfg],
                ls=ls, marker=mk, ms=4, lw=1.8, capsize=2, elinewidth=1)


def main():
    # Fig 1 detection + latency
    s = pd.read_csv(f"{R}/paper2_summary_binom.csv")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.2))
    plot(a1, s, "D0_deployed", "D0 deployed", "-", "o")
    plot(a1, s, "D1_anchored", "D1 anchor", "--", "s")
    plot(a1, s, "D2_anchored_cusum", "D2 proposed", "-", "D")
    a1.axhline(80, color="k", lw=.7, ls=":"); a1.axvline(1, color="k", lw=.7, ls=":")
    a1.set_xlabel("onset-to-window ratio"); a1.set_ylabel("detection rate (%)")
    a1.set_title("(a) Detection"); a1.set_ylim(-3, 105); a1.legend(fontsize=8, loc="lower left")
    for cfg, lab, ls, mk in [("D0_deployed", "D0", "-", "o"), ("D1_anchored", "D1", "--", "s"),
                             ("D2_anchored_cusum", "D2", "-", "D")]:
        d = s[s.config == cfg].sort_values("onset_ratio")
        a2.plot(d.onset_ratio, d.median_latency_min, label=lab, color=COL[cfg], ls=ls, marker=mk, ms=4, lw=1.8)
    a2.axvline(1, color="k", lw=.7, ls=":"); a2.set_xlabel("onset-to-window ratio")
    a2.set_ylabel("median latency (min)"); a2.set_title("(b) Latency"); a2.legend(fontsize=8)
    fig.suptitle("Fig 1. Closing the blind spot (200 seeds, 95% Wilson CIs)", fontsize=10)
    fig.tight_layout(); fig.savefig(f"{F}/fig_paper2_detection_wilson.png", bbox_inches="tight"); plt.close(fig)

    # Fig 2 re-anchoring
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    plot(ax, s, "D0_deployed", "D0 deployed", "-", "o")
    plot(ax, s, "D2_anchored_cusum", "D2 shift-start", "-", "D")
    plot(ax, s, "D2_periodic", "D2-periodic (naive)", "--", "^")
    plot(ax, s, "D2_periodic_gated", "D2-periodic-gated", "-", "s")
    ax.axvline(1, color="k", lw=.7, ls=":"); ax.set_ylim(-3, 105)
    ax.set_xlabel("onset-to-window ratio"); ax.set_ylabel("detection rate (%)")
    ax.set_title("Fig 2. Re-anchoring hazard & health-gate fix (200 seeds, Wilson CIs)")
    ax.legend(fontsize=8, loc="lower right"); fig.tight_layout()
    fig.savefig(f"{F}/fig_paper2_anchor_modes_wilson.png", bbox_inches="tight"); plt.close(fig)

    # Fig 3 ablation
    c = pd.read_csv(f"{R}/paper2_comparators_summary_binom.csv")
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    plot(ax, c, "D0_deployed", "D0 deployed threshold", "-", "o")
    plot(ax, c, "C1_rolling_cusum", "C1 rolling + CUSUM", "--", "^")
    plot(ax, c, "D2_anchored_cusum", "D2 anchored + CUSUM", "-", "D")
    plot(ax, c, "C2_model_residual", "C2 fixed global-mean + CUSUM", "-", "s")
    ax.axvline(1, color="k", lw=.7, ls=":"); ax.set_ylim(-3, 105)
    ax.set_xlabel("onset-to-window ratio"); ax.set_ylabel("detection rate (%)")
    ax.set_title("Fig 3. Mechanism vs statistic (200 seeds, Wilson CIs)")
    ax.legend(fontsize=8, loc="lower left"); fig.tight_layout()
    fig.savefig(f"{F}/fig_paper2_comparators_wilson.png", bbox_inches="tight"); plt.close(fig)

    # Fig 4 severity
    m = pd.read_csv(f"{R}/paper2_multiseverity_summary_binom.csv")
    sevs = sorted(m.severity_kw.unique()); cmap = plt.cm.viridis(np.linspace(.15, .85, len(sevs)))
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    for ax, cfg, ttl in [(a1, "D0_deployed", "(a) D0"), (a2, "D2_anchored_cusum", "(b) D2")]:
        for sv, cc in zip(sevs, cmap):
            d = m[(m.config == cfg) & (m.severity_kw == sv)].sort_values("onset_ratio")
            y = d.detection_rate.values * 100
            ax.errorbar(d.onset_ratio, y, yerr=np.vstack([y - d.wilson_lo*100, d.wilson_hi*100 - y]),
                        color=cc, marker="o", ms=3, lw=1.5, capsize=1.5, label=f"{sv:.1f} kW")
        ax.axvline(1, color="k", lw=.7, ls=":"); ax.set_xlabel("onset-to-window ratio"); ax.set_title(ttl); ax.set_ylim(-3, 105)
    a1.set_ylabel("detection rate (%)"); a2.legend(fontsize=8, title="severity", loc="lower left")
    fig.suptitle("Fig 4. Generalisation across severity (100 seeds, Wilson CIs)", fontsize=10)
    fig.tight_layout(); fig.savefig(f"{F}/fig_paper2_multiseverity_wilson.png", bbox_inches="tight"); plt.close(fig)

    # Fig 6 real-data overlaid on synthetic
    r = pd.read_csv(f"{R}/paper2_realdata_summary_binom.csv")
    fig, ax = plt.subplots(figsize=(6.6, 4.4))
    for cfg in ["D0_deployed", "D2_anchored_cusum"]:
        x, y, _, _, _ = ser(s, cfg); ax.plot(x, y, color=COL[cfg], ls="--", lw=1.2, alpha=.55)
    plot(ax, r, "D0_deployed", "D0 (real)", "-", "o")
    plot(ax, r, "D2_anchored_cusum", "D2 (real)", "-", "D")
    ax.plot([], [], color="k", ls="--", alpha=.55, label="synthetic")
    ax.axvline(1, color="k", lw=.7, ls=":"); ax.set_ylim(-3, 105)
    ax.set_xlabel("onset-to-window ratio"); ax.set_ylabel("detection rate (%)")
    ax.set_title("Fig 6. Real measured CNC spindle power (100 seeds, Wilson CIs)")
    ax.legend(fontsize=8, loc="lower left"); fig.tight_layout()
    fig.savefig(f"{F}/fig_paper2_realdata_wilson.png", bbox_inches="tight"); plt.close(fig)
    print("  wrote 5 Wilson-interval figures to figures/")


if __name__ == "__main__":
    main()
