"""
plot_paper_figs.py
==================
Generates Figures 1-6 for the journal paper in the same polished style as
fig_ramp_time.png (Figure 7). Each figure is built from one sweep CSV with:

  - clean white background with subtle grid
  - bold main result line with 95% bootstrap CIs where high-seed data exists
  - viridis/perceptual color palette for parameter sweeps
  - reference annotations (50% detection, etc) with dashed grey lines
  - explanatory subtitle stating methodology and seed counts
  - units in axis labels

Input CSVs (in /home/claude/):  sweep1_latency.csv, sweep2_sampling.csv,
sweep3_roc.csv, sweep4_archetypes.csv, sweep5_threshold_types.csv,
sweep6_attribution.csv, sweep8_boundary.csv

Output: fig1_detection.png through fig6_attribution.png in
/mnt/user-data/outputs/.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

plt.rcParams.update({
    "font.size": 11,
    "axes.titlesize": 12,
    "axes.labelsize": 11,
    "legend.fontsize": 9,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": "-",
    "grid.linewidth": 0.6,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

OUT = "figures"            # output directory for PNGs (relative to repo root)
DATA = "data"              # input directory for CSVs  (relative to repo root)
BASELINE_KW = 3.4          # aux + spindle no-load


def bootstrap_ci(values, n_boot=2000, alpha=0.05, seed=0):
    """95% bootstrap CI for a proportion (detection rate)."""
    rng = np.random.default_rng(seed)
    vals = np.asarray(values, dtype=float)
    if len(vals) == 0:
        return np.nan, np.nan, np.nan
    point = vals.mean()
    boots = rng.choice(vals, size=(n_boot, len(vals)), replace=True).mean(axis=1)
    lo, hi = np.percentile(boots, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return point, lo, hi


# =====================================================================
# FIGURE 1 — Detection rate + latency vs severity, with bootstrap CIs
# =====================================================================
def fig1():
    df = pd.read_csv(f"{DATA}/sweep1_latency.csv")
    df8 = pd.read_csv(f"{DATA}/sweep8_boundary.csv")

    fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(10, 7), sharex=True,
                                         gridspec_kw={"height_ratios": [1.4, 1]})

    # --- Top panel: detection rate vs severity, three duration lines ---
    durations = sorted(df["duration_min"].unique())
    colors = plt.cm.viridis(np.linspace(0.15, 0.75, len(durations)))
    # Add small jitter on x so overlapping lines remain visible
    jitter = {d: (i - (len(durations)-1)/2) * 0.015 for i, d in enumerate(durations)}
    for c, dur in zip(colors, durations):
        sub = df[df["duration_min"] == dur].groupby("severity_kw")["warning_detected"].mean() * 100
        x = sub.index + jitter[dur]
        ax_top.plot(x, sub.values, "-o", color=c, lw=2, ms=6, alpha=0.85,
                    label=f"{dur/60:.1f} h" if dur >= 60 else f"{dur} min")

    # Bootstrap CIs at boundary severities, from sweep 8 (50 seeds)
    boundary_sev = sorted(df8["severity_kw"].unique())
    points, los, his = [], [], []
    for sev in boundary_sev:
        vals = df8[df8["severity_kw"] == sev]["warning_detected"].values
        p, lo, hi = bootstrap_ci(vals, seed=int(sev * 100))
        points.append(p * 100); los.append(lo * 100); his.append(hi * 100)
    yerr = [np.array(points) - np.array(los), np.array(his) - np.array(points)]
    ax_top.errorbar(boundary_sev, points, yerr=yerr, fmt="D", color="black",
                    ms=7, lw=1.5, capsize=4, zorder=10,
                    label="boundary 95% CI (50 seeds)")

    # 80%-detection annotation
    ax_top.axvline(1.5, color="grey", linestyle=":", lw=1, alpha=0.7)
    ax_top.annotate("80% detection at 1.5 kW\n= 44% of baseline (3.4 kW)",
                    xy=(1.5, 80), xytext=(1.75, 55),
                    fontsize=9, color="dimgrey",
                    arrowprops=dict(arrowstyle="->", color="dimgrey",
                                    lw=0.8, alpha=0.7),
                    bbox=dict(boxstyle="round,pad=0.4", fc="white",
                              ec="lightgrey", lw=0.8))
    # Annotation: duration overlap is itself the finding
    ax_top.annotate("Three duration lines overlap:\nabove the boundary, duration\ndoes not affect detection rate",
                    xy=(3.0, 100), xytext=(2.6, 65),
                    fontsize=9, color="dimgrey",
                    arrowprops=dict(arrowstyle="->", color="dimgrey",
                                    lw=0.8, alpha=0.7),
                    bbox=dict(boxstyle="round,pad=0.4", fc="white",
                              ec="lightgrey", lw=0.8))

    ax_top.set_ylabel("Detection rate  (%)")
    ax_top.set_ylim(-5, 108)
    ax_top.set_title("Figure 1.  Detection performance vs severity, by fault duration\n"
                     "10 seeds per condition (50 seeds at boundary, with bootstrap CIs); "
                     "compressed-air leak; baseline = 3.4 kW",
                     loc="left")
    ax_top.legend(loc="lower right", frameon=True, framealpha=0.95)

    # --- Bottom panel: warning latency vs severity ---
    for c, dur in zip(colors, durations):
        sub = df[(df["duration_min"] == dur) & (df["warning_detected"])]
        if len(sub) == 0:
            continue
        grp = sub.groupby("severity_kw")["warning_latency_min"]
        med = grp.median()
        q25 = grp.quantile(0.25)
        q75 = grp.quantile(0.75)
        ax_bot.plot(med.index, med.values, "-o", color=c, lw=2, ms=5)
        ax_bot.fill_between(med.index, q25.values, q75.values, color=c, alpha=0.15)

    ax_bot.set_xlabel(f"Anomaly severity  (kW)    [baseline = {BASELINE_KW} kW]")
    ax_bot.set_ylabel("Warning latency  (min)\nmedian + IQR")
    ax_bot.set_ylim(0, None)

    plt.tight_layout()
    fig.savefig(f"{OUT}/fig1_detection.png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    print("  -> fig1_detection.png")


# =====================================================================
# FIGURE 2 — Detection rate vs severity, by meter sampling cadence
# =====================================================================
def fig2():
    df = pd.read_csv(f"{DATA}/sweep2_sampling.csv")

    fig, ax = plt.subplots(figsize=(10, 5.5))

    samplings = sorted(df["sampling_s"].unique())
    samp_col = "sampling_s"

    def fmt_samp(s):
        if s < 60: return f"{int(s)} s"
        if s < 3600: return f"{int(s/60)} min"
        return f"{s/3600:.0f} h"

    colors = plt.cm.viridis(np.linspace(0.15, 0.85, len(samplings)))
    for c, s in zip(colors, samplings):
        sub = df[df[samp_col] == s].groupby("severity_kw")["warning_detected"].mean() * 100
        ax.plot(sub.index, sub.values, "-o", color=c, lw=2.2, ms=7,
                label=f"sampling = {fmt_samp(s)}")

    # Annotate the 15-min line as unusable
    if 900 in samplings:
        sub_900 = df[df[samp_col] == 900].groupby("severity_kw")["warning_detected"].mean() * 100
        if sub_900.max() < 30:
            ax.annotate("15-min sampling: stays near 0%\nacross all tested severities",
                        xy=(sub_900.index[-1], sub_900.values[-1]),
                        xytext=(1.7, 35),
                        fontsize=9, color="dimgrey",
                        arrowprops=dict(arrowstyle="->", color="dimgrey",
                                       lw=0.8, alpha=0.7),
                        bbox=dict(boxstyle="round,pad=0.4", fc="white",
                                  ec="lightgrey", lw=0.8))

    ax.set_xlabel(f"Anomaly severity  (kW)    [baseline = {BASELINE_KW} kW]")
    ax.set_ylabel("Detection rate  (%)")
    ax.set_ylim(-5, 108)
    ax.set_title("Figure 2.  Detection rate vs severity, by meter sampling cadence\n"
                 "10 seeds per condition, 4 h compressed-air leak, "
                 "rolling-CI estimation decoupled from meter cadence",
                 loc="left")
    ax.legend(loc="lower right", frameon=True, framealpha=0.95, title="meter sampling")

    plt.tight_layout()
    fig.savefig(f"{OUT}/fig2_sampling.png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    print("  -> fig2_sampling.png")


# =====================================================================
# FIGURE 3 — Detection rate and FP rate vs threshold tightness
# =====================================================================
def fig3():
    df = pd.read_csv(f"{DATA}/sweep3_roc.csv")

    thresh_col = "threshold_pct"
    df["warning_detected"] = df["warning_detected"].astype(bool).astype(float)
    grp = df.groupby(thresh_col).agg(
        detection=("warning_detected", "mean"),
        fp_rate=("fp_rate_per_production_hour", "mean"),
    ).reset_index().sort_values(thresh_col)
    grp["detection"] = grp["detection"].astype(float) * 100
    grp["fp_rate"] = grp["fp_rate"].astype(float)

    fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(10, 7), sharex=True,
                                         gridspec_kw={"height_ratios": [1, 1]})

    # --- Top: detection rate vs tightness ---
    ax_top.plot(grp[thresh_col].values, grp["detection"].values, "-o",
                color="#1f77b4", lw=2.4, ms=8, zorder=10)
    ax_top.fill_between(grp[thresh_col].values, 0, grp["detection"].values,
                        alpha=0.08, color="#1f77b4")
    ax_top.set_ylabel("Detection rate  (%)")
    ax_top.set_ylim(-5, 108)
    ax_top.axhline(50, color="grey", linestyle=":", lw=0.8, alpha=0.5)
    ax_top.axhline(100, color="grey", linestyle=":", lw=0.8, alpha=0.5)

    # Mark the operating-region knee
    knee = grp[grp["detection"] >= 95].sort_values(thresh_col, ascending=False)
    if len(knee) > 0:
        k = knee.iloc[0]
        ax_top.annotate(
            f"Loosest tightness\nstill at 100% detection:\n+{int(k[thresh_col])}% above baseline",
            xy=(k[thresh_col], k["detection"]),
            xytext=(60, 20),
            fontsize=9, color="dimgrey",
            arrowprops=dict(arrowstyle="->", color="dimgrey", lw=0.8, alpha=0.7),
            bbox=dict(boxstyle="round,pad=0.4", fc="white",
                      ec="lightgrey", lw=0.8))

    ax_top.set_title("Figure 3.  Detection vs threshold tightness (relative-threshold family)\n"
                     "10 seeds per threshold; severity = 1.5 kW (boundary), duration = 4 h",
                     loc="left")

    # --- Bottom: FP rate vs tightness ---
    ax_bot.plot(grp[thresh_col].values, grp["fp_rate"].values, "-s",
                color="#d62728", lw=2.4, ms=7, zorder=10)
    ax_bot.fill_between(grp[thresh_col].values, 0, grp["fp_rate"].values,
                        alpha=0.08, color="#d62728")
    ax_bot.set_xlabel("Relative threshold tightness  (% above adaptive baseline)")
    ax_bot.set_ylabel("False-positive rate\n(warnings / production-hour)")
    ax_bot.set_ylim(bottom=-0.02)

    # Mark where FP rate starts to climb
    fp_climb = grp[grp["fp_rate"] > 0.05].sort_values(thresh_col)
    if len(fp_climb) > 0:
        f = fp_climb.iloc[0]
        ax_bot.annotate(
            f"FP rate becomes meaningful\nbelow +{int(f[thresh_col])}% tightness",
            xy=(f[thresh_col], f["fp_rate"]),
            xytext=(f[thresh_col] + 10, max(0.15, f["fp_rate"] * 1.5)),
            fontsize=9, color="dimgrey",
            arrowprops=dict(arrowstyle="->", color="dimgrey", lw=0.8, alpha=0.7),
            bbox=dict(boxstyle="round,pad=0.4", fc="white",
                      ec="lightgrey", lw=0.8))

    plt.tight_layout()
    fig.savefig(f"{OUT}/fig3_roc.png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    print("  -> fig3_roc.png")


# =====================================================================
# FIGURE 4 — Detection rate vs severity, four fault archetypes
# =====================================================================
def fig4():
    df = pd.read_csv(f"{DATA}/sweep4_archetypes.csv")

    fig, ax = plt.subplots(figsize=(10, 5.5))

    arch_col = "archetype" if "archetype" in df.columns else "fault_type"
    archetypes = sorted(df[arch_col].unique())

    # Distinct colour + marker + linestyle per archetype so overlapping curves remain visible
    style = {
        "compressed_air_leak": {"color": "#2ca02c", "marker": "o", "ls": "-",  "lw": 2.0},
        "machine_left_on":     {"color": "#1f77b4", "marker": "s", "ls": "--", "lw": 2.0},
        "tool_wear":           {"color": "#d62728", "marker": "D", "ls": "-",  "lw": 2.6},
        "coolant_pump_fault":  {"color": "#ff7f0e", "marker": "^", "ls": ":",  "lw": 2.2},
    }
    label_map = {
        "compressed_air_leak": "compressed-air leak",
        "machine_left_on":     "machine left on",
        "tool_wear":           "tool wear (1 h ramp)",
        "coolant_pump_fault":  "coolant-pump fault",
    }
    # Slight x-jitter to separate overlapping markers
    jitter = {a: (i - (len(archetypes)-1)/2) * 0.02 for i, a in enumerate(archetypes)}

    for a in archetypes:
        sub = df[df[arch_col] == a].groupby("severity_kw")["warning_detected"].mean() * 100
        s = style.get(a, {"color": "grey", "marker": "o", "ls": "-", "lw": 2.0})
        x = sub.index + jitter[a]
        ax.plot(x, sub.values, color=s["color"], marker=s["marker"],
                linestyle=s["ls"], lw=s["lw"], ms=7, alpha=0.9,
                label=label_map.get(a, a))

    # Annotate the tool-wear divergence
    if "tool_wear" in archetypes:
        ax.annotate("tool wear: gradual ramp\n→ detection drops below sigmoid;\nsee Figure 7 for ramp-time sweep",
                    xy=(2.0, 0), xytext=(2.2, 28),
                    fontsize=9, color="dimgrey",
                    arrowprops=dict(arrowstyle="->", color="dimgrey",
                                   lw=0.8, alpha=0.7),
                    bbox=dict(boxstyle="round,pad=0.4", fc="white",
                              ec="lightgrey", lw=0.8))

    ax.set_xlabel(f"Anomaly severity  (kW)    [baseline = {BASELINE_KW} kW]")
    ax.set_ylabel("Detection rate  (%)")
    ax.set_ylim(-5, 108)
    ax.set_title("Figure 4.  Detection rate across four fault archetypes\n"
                 "10 seeds per condition; tool-wear ramp = 60 min (Figure 7 sweeps ramp time)",
                 loc="left")
    ax.legend(loc="center right", frameon=True, framealpha=0.95, title="archetype")

    plt.tight_layout()
    fig.savefig(f"{OUT}/fig4_archetypes.png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    print("  -> fig4_archetypes.png")


# =====================================================================
# FIGURE 5 — ROC: absolute vs relative vs statistical thresholds
# =====================================================================
def fig5():
    df = pd.read_csv(f"{DATA}/sweep5_threshold_types.csv")

    type_col = "threshold_type"
    # Tightness column differs by type (threshold_pct for relative, sigma_k for statistical,
    # threshold_value for absolute). We use fp_rate_per_production_hour for the x-axis,
    # which makes families directly comparable regardless of their tightness parameterisation.

    fig, ax = plt.subplots(figsize=(10, 6))

    pal = {"absolute": "#d62728", "relative": "#2ca02c", "statistical": "#9467bd"}

    for ttype in sorted(df[type_col].unique()):
        sub = df[df[type_col] == ttype]
        # Group by the family's own tightness parameter, then average seeds within
        if ttype == "absolute":
            tcol = "abs_thr_g" if "abs_thr_g" in sub.columns else "threshold_value"
        elif ttype == "relative":
            tcol = "threshold_pct"
        else:  # statistical
            tcol = "sigma_k"
        agg = sub.groupby(tcol).agg(
            detection=("warning_detected", "mean"),
            fp_rate=("fp_rate_per_production_hour", "mean"),
        ).reset_index().sort_values("fp_rate")
        agg["detection"] *= 100
        ax.plot(agg["fp_rate"], agg["detection"], "-o",
                color=pal.get(ttype, "grey"), lw=2.2, ms=7,
                label=ttype)

    # Zoomed annotation on the operating region
    ax.annotate("All three families: near-100% detection\nat very low FP rate.\nSee §4.5 for within-class equivalence;\nCUSUM/EWMA comparison = future work.",
                xy=(0.05, 100), xytext=(0.55, 50),
                fontsize=9, color="dimgrey",
                arrowprops=dict(arrowstyle="->", color="dimgrey",
                               lw=0.8, alpha=0.7),
                bbox=dict(boxstyle="round,pad=0.4", fc="white",
                          ec="lightgrey", lw=0.8))

    ax.set_xlabel("False-positive rate  (warnings / production-hour)")
    ax.set_ylabel("Detection rate  (%, 1.5 kW × 4 h anomaly)")
    ax.set_ylim(-5, 108)
    ax.set_xlim(left=-0.05)
    ax.set_title("Figure 5.  ROC: absolute vs relative vs statistical threshold families\n"
                 "8 seeds per condition; each curve is one family swept across tightness",
                 loc="left")
    ax.legend(loc="lower right", frameon=True, framealpha=0.95, title="threshold family")

    plt.tight_layout()
    fig.savefig(f"{OUT}/fig5_threshold_types.png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    print("  -> fig5_threshold_types.png")


# =====================================================================
# FIGURE 6 — Attribution accuracy by severity, machine vs spindle channel
# =====================================================================
def fig6():
    df = pd.read_csv(f"{DATA}/sweep6_attribution.csv")

    # Only count detected runs
    det = df[df["warning_detected"] == True].copy()

    fig, ax = plt.subplots(figsize=(10, 5.5))

    pal = {"machine": "#ff7f0e", "spindle": "#2ca02c"}
    for ch in sorted(det["affects"].unique()):
        sub = det[det["affects"] == ch]
        grp = sub.groupby("severity_kw").agg(
            acc=("attribution_correct", "mean"),
            n=("attribution_correct", "size"),
        ).reset_index()
        grp["acc"] *= 100
        ax.plot(grp["severity_kw"], grp["acc"], "-o",
                color=pal.get(ch, "grey"), lw=2.2, ms=7,
                label=f"fault in {ch} channel")
        # Annotate sample sizes only where small (n < 5)
        for _, r in grp.iterrows():
            if r["n"] < 5:
                ax.annotate(f"n={int(r['n'])}",
                            xy=(r["severity_kw"], r["acc"]),
                            xytext=(0, 8), textcoords="offset points",
                            fontsize=8, color=pal.get(ch, "grey"),
                            ha="center")

    ax.axhline(50, color="grey", linestyle="--", lw=1, alpha=0.6,
               label="chance (50%)")

    # Annotate the headline
    ax.annotate("≥1 kW: 100% attribution\nin both channels",
                xy=(2.0, 100), xytext=(2.3, 70),
                fontsize=9, color="dimgrey",
                arrowprops=dict(arrowstyle="->", color="dimgrey",
                               lw=0.8, alpha=0.7),
                bbox=dict(boxstyle="round,pad=0.4", fc="white",
                          ec="lightgrey", lw=0.8))

    ax.set_xlabel(f"Anomaly severity  (kW)    [baseline = {BASELINE_KW} kW]")
    ax.set_ylabel("Attribution accuracy  (%, among detected runs)")
    ax.set_ylim(-5, 108)
    ax.set_title("Figure 6.  Attribution accuracy by severity and affected channel\n"
                 "10 seeds per condition; restricted to runs in which a warning was raised",
                 loc="left")
    ax.legend(loc="center right", frameon=True, framealpha=0.95)

    plt.tight_layout()
    fig.savefig(f"{OUT}/fig6_attribution.png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    print("  -> fig6_attribution.png")


def fig7():
    """Figure 7: adaptive-baseline inertia trade-off from the 200-seed Sweep 9."""
    df = pd.read_csv(f"{DATA}/sweep9_ramp_transition_200seed.csv")
    BASELINE_WINDOW_S = 60 * 60  # 60-min baseline-adaptation window

    rows = []
    for ramp in sorted(df.ramp_s.unique()):
        hits = (df[df.ramp_s == ramp]
                .warning_detected.astype(str).str.strip().eq("True")
                .values.astype(float))
        rate, lo, hi = bootstrap_ci(hits, n_boot=10000, seed=20240518)
        rows.append((ramp / BASELINE_WINDOW_S, rate * 100, lo * 100, hi * 100))
    r = pd.DataFrame(rows, columns=["ratio", "det", "lo", "hi"])

    fig, ax = plt.subplots(figsize=(7, 4.3))
    ax.fill_between(r.ratio, r.lo, r.hi, alpha=0.18, color="#1a1a1a",
                    label="95% bootstrap CI")
    ax.plot(r.ratio, r.det, "-o", color="#1a1a1a", lw=2, ms=5,
            label="2 kW, 200 seeds/point (Sweep 9)")
    ax.axvline(1.0, ls="--", color="#999", lw=1)
    ax.axhline(80, ls=":", color="#c0392b", lw=1)
    ax.axhline(50, ls=":", color="#c0392b", lw=1)
    ax.annotate("80% knee\nratio ≈ 0.43", xy=(0.425, 80), xytext=(0.12, 57),
                fontsize=8, color="#c0392b",
                arrowprops=dict(arrowstyle="->", color="#c0392b", lw=0.8))
    ax.annotate("50% midpoint\nratio ≈ 0.69", xy=(0.693, 50), xytext=(0.74, 68),
                fontsize=8, color="#c0392b",
                arrowprops=dict(arrowstyle="->", color="#c0392b", lw=0.8))
    ax.set_xlabel("Ramp time / baseline-window ratio")
    ax.set_ylabel("Detection rate (%)")
    ax.set_title("Figure 7. Adaptive-baseline inertia trade-off (200-seed fine sweep, 2 kW)",
                 loc="left", fontsize=10)
    ax.set_xlim(0.1, 1.05)
    ax.set_ylim(0, 102)
    ax.legend(fontsize=8, frameon=False, loc="upper right")
    ax.grid(alpha=0.25)

    plt.tight_layout()
    fig.savefig(f"{OUT}/fig7_ramp_time.png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    print("  -> fig7_ramp_time.png")


if __name__ == "__main__":
    import os
    os.makedirs(OUT, exist_ok=True)
    print(f"Generating Figures 1-7 → {OUT}/")
    fig1(); fig2(); fig3(); fig4(); fig5(); fig6(); fig7()
    print("Done.")
