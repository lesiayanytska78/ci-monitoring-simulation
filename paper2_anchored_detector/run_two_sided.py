"""
run_two_sided.py  (Paper 2 revision, §4.11)
==========================================
Negative deviations and the two-sided CUSUM.

The deployed one-sided CUSUM accumulates only POSITIVE fractional excess, so it is
blind to a sustained DOWNWARD deviation on the CI channel (a sensor under-read, an
efficiency improvement that later masks a fault, or a measurement-bias fault). We
inject a sustained -m% step in observed CI from T0 and compare the one-sided CUSUM
(deployed) with a two-sided variant (mirror negative-side accumulator). We also
confirm the two-sided scheme keeps positive-fault detection at 100% and quantify
its clean-day false-alarm cost.

Operating point k=0.10, h=1.0. Output: two_sided_summary.csv
"""
from __future__ import annotations
import numpy as np, pandas as pd
import revision_common as rc

N = 60
MAGS = [0.05, 0.10, 0.20, 0.30]      # downward deviation magnitudes (fraction)
SEED0 = 42


def _neg_day(seed, m):
    """A clean day whose observed CI is reduced by m during production, t in [T0,T1]."""
    sub = rc.clean_day(seed)
    obs = rc.observe(sub, seed)
    ci = obs["ci_per_piece_kg_obs"].values.copy()
    t = obs["t_s"].values
    state = obs["state"].values
    hit = (state == "PRODUCTION") & (t >= rc.T0) & np.isfinite(ci)
    ci[hit] = ci[hit] * (1.0 - m)
    obs["ci_per_piece_kg_obs"] = ci
    return obs


def main():
    rows = []
    for m in MAGS:
        one, two = [], []
        for s in range(N):
            obs = _neg_day(SEED0 + s, m)
            ci = obs["ci_per_piece_kg_obs"].values
            state = obs["state"].values
            t = obs["t_s"].values
            valid = np.isfinite(ci) & (state == "PRODUCTION")
            B = rc.held_B(obs, anchor_mode="shift_start")
            a1 = rc.cusum_alert(ci, valid, B, two_sided=False)
            a2 = rc.cusum_alert(ci, valid, B, two_sided=True)
            one.append(rc.eval_det(a1, t)[0])
            two.append(rc.eval_det(a2, t)[0])
        k1, k2 = int(np.sum(one)), int(np.sum(two))
        lo1, hi1 = rc.wilson(k1, N); lo2, hi2 = rc.wilson(k2, N)
        rows.append({"deviation": -m, "one_sided_det": k1 / N,
                     "two_sided_det": k2 / N, "two_lo": lo2, "two_hi": hi2})
        print(f"  dev -{m*100:.0f}%:  one-sided {k1/N:.2f}   two-sided {k2/N:.2f} "
              f"[{lo2:.2f},{hi2:.2f}]")

    # positive 2 kW fault still caught by the two-sided scheme; clean-day FA cost
    from anomaly_model import AnomalyConfig, inject_anomalies
    pos, fa_c, fa_e = [], 0, 0.0
    for s in range(N):
        sub = rc.substrate(42 + s)
        obs = rc.observe(inject_anomalies(sub, AnomalyConfig([rc.ramp_spec()])), 42 + s)
        ci = obs["ci_per_piece_kg_obs"].values; state = obs["state"].values; t = obs["t_s"].values
        valid = np.isfinite(ci) & (state == "PRODUCTION")
        B = rc.held_B(obs)
        pos.append(rc.eval_det(rc.cusum_alert(ci, valid, B, two_sided=True), t)[0])
        # clean day false-alarm exposure for the two-sided scheme
        cobs = rc.observe(rc.clean_day(242 + s), 242 + s)
        cci = cobs["ci_per_piece_kg_obs"].values; cst = cobs["state"].values
        cval = np.isfinite(cci) & (cst == "PRODUCTION")
        cB = rc.held_B(cobs)
        ca = rc.cusum_alert(cci, cval, cB, two_sided=True)
        c, e = rc.fp_count_exposure(ca, cst); fa_c += c; fa_e += e
    kp = int(np.sum(pos)); lop, hip = rc.wilson(kp, N)
    r, flo, fhi = rc.poisson(fa_c, fa_e)
    print(f"\n  positive 2 kW fault, two-sided: {kp/N:.2f} [{lop:.2f},{hip:.2f}]")
    print(f"  two-sided clean-day FA: {fa_c}/{fa_e:.0f} h = {r:.4f}/h [{flo:.4f},{fhi:.4f}]")
    rows.append({"deviation": "positive_2kW", "one_sided_det": np.nan,
                 "two_sided_det": kp / N, "two_lo": lop, "two_hi": hip})
    rows.append({"deviation": "two_sided_clean_FA_per_h", "one_sided_det": np.nan,
                 "two_sided_det": r, "two_lo": flo, "two_hi": fhi})
    pd.DataFrame(rows).to_csv("two_sided_summary.csv", index=False)
    print("  wrote two_sided_summary.csv")


if __name__ == "__main__":
    main()
