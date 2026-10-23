"""
recompute_intervals.py  (Paper 2 revision, §3.4)
===============================================
Replace the degenerate percentile-bootstrap detection intervals with binomial
(Wilson score and exact Clopper-Pearson) 95% intervals, and recompute the exact
(Garwood) Poisson intervals for the false-alarm rates.

Reads the headline result summaries (results/*_summary.csv), infers the seed count
per file (200 for the headline/ablation runs, 100 for the severity/real-data runs),
and writes a *_binom.csv alongside each with wilson_lo/hi and cp_lo/hi columns. The
figures are redrawn from these Wilson columns by redraw_figs.py.

A percentile bootstrap of an all-detected sample is degenerate ([100,100]); a
binomial interval is not (200/200 -> 98.1-100%, 100/100 -> 96.3-100%).
"""
from __future__ import annotations
import os, numpy as np, pandas as pd
from scipy.stats import beta, chi2

RESULTS = "results"
# seed count per headline summary (stated in Appendix A / §3.4)
N_BY_FILE = {
    "paper2_summary.csv": 200,
    "paper2_comparators_summary.csv": 200,
    "paper2_multiseverity_summary.csv": 100,
    "paper2_realdata_summary.csv": 100,
}


def wilson(k, n, z=1.959963985):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = (z / d) * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, c - h), min(1.0, c + h))


def clopper_pearson(k, n, alpha=0.05):
    lo = 0.0 if k == 0 else beta.ppf(alpha / 2, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(1 - alpha / 2, k + 1, n - k)
    return (lo, hi)


def poisson(count, exposure, alpha=0.05):
    lo = 0.0 if count == 0 else chi2.ppf(alpha / 2, 2 * count) / 2.0 / exposure
    hi = chi2.ppf(1 - alpha / 2, 2 * (count + 1)) / 2.0 / exposure
    return (count / exposure, lo, hi)


def main():
    for fname, n in N_BY_FILE.items():
        path = os.path.join(RESULTS, fname)
        if not os.path.exists(path):
            print(f"  (skip, not found) {path}")
            continue
        df = pd.read_csv(path)
        wl, wh, cl, ch, kk = [], [], [], [], []
        for p in df["detection_rate"].values:
            k = int(round(p * n))
            wlo, whi = wilson(k, n); clo, chi_ = clopper_pearson(k, n)
            wl.append(wlo); wh.append(whi); cl.append(clo); ch.append(chi_); kk.append(k)
        df["n"] = n; df["k"] = kk
        df["wilson_lo"] = np.round(wl, 4); df["wilson_hi"] = np.round(wh, 4)
        df["cp_lo"] = np.round(cl, 4); df["cp_hi"] = np.round(ch, 4)
        out = path.replace("_summary.csv", "_summary_binom.csv")
        df.to_csv(out, index=False)
        print(f"  wrote {out}  (n={n}; perfect cell -> "
              f"{wilson(n, n)[0]*100:.1f}-100%)")

    # Poisson intervals for the measured false-alarm configurations (§3.4).
    # Counts/exposures are the pooled warning-start counts over clean-day
    # production-hours from the headline runs (run_paper2_main / _comparators /
    # _realdata). Edit here if a re-run changes the pooled counts.
    fa = [
        ("D0_deployed_sim", 0, 2447.5), ("D2_anchored_cusum_sim", 6, 2447.5),
        ("D2_periodic_sim", 27, 2447.5), ("D2_periodic_gated_sim", 30, 2447.5),
        ("C1_rolling_cusum_sim", 3, 2447.5), ("C2_model_residual_sim", 0, 2447.5),
        ("D0_deployed_real", 0, 1223.0), ("D2_anchored_cusum_real", 35, 1223.0),
    ]
    rows = []
    for name, c, e in fa:
        r, lo, hi = poisson(c, e)
        rows.append({"config": name, "fa_count": c, "production_hours": e,
                     "rate_per_h": round(r, 4), "poisson_lo": round(lo, 4),
                     "poisson_hi": round(hi, 4)})
    pd.DataFrame(rows).to_csv(os.path.join(RESULTS, "false_alarm_poisson.csv"), index=False)
    print("  wrote results/false_alarm_poisson.csv")


if __name__ == "__main__":
    main()
