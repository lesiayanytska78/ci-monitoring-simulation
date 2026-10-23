"""
run_regen_treatment.py  (Paper 2 revision, §4.13)
================================================
Robustness to the negative-power (regenerative-braking) accounting choice. Clipping
negative spindle power to zero is a consumption-meter model; a bidirectional meter
would NET the regen energy. We bound the effect by re-deriving per-piece CI under
three meter treatments -- clip (baseline), net (subtract a steady regen credit),
half (half credit) -- over a credit from a realistic 0.2 kW to an extreme 2 kW, on
the real substrate. The proposed detector's DETECTION is treatment-invariant; the
treatment shifts the absolute baseline, which affects the deployed relative detector.

Output: regen_treatment_summary.csv
"""
from __future__ import annotations
import numpy as np, pandas as pd
import revision_common as rc
from anomaly_model import AnomalyConfig, inject_anomalies

N = 50
CREDITS = [0.2, 1.0, 2.0]                   # steady regen credit (kW)
TREATMENTS = {"clip": 0.0, "half": 0.5, "net": 1.0}


def _apply_credit(sub, credit, frac):
    """Subtract a steady regen credit (credit*frac kW) from production spindle power
    (a bidirectional meter would net this energy). Clip keeps >= 0."""
    o = sub.copy()
    prod = (o["state"].values == "PRODUCTION")
    sp = o["spindle_kw"].values.copy()
    sp[prod] = np.clip(sp[prod] - credit * frac, 0.0, None)
    o["spindle_kw"] = sp
    o["total_kw"] = o["machine_kw"].values + sp
    return o


def main():
    rows = []
    for credit in CREDITS:
        for tname, frac in TREATMENTS.items():
            if tname == "clip" and credit != CREDITS[0]:
                continue                     # clip baseline reported once
            d2 = d0 = 0; fa_c, fa_e = 0, 0.0
            for s in range(N):
                sub = rc.substrate(42 + s, real=True)
                sub = _apply_credit(sub, credit, frac)
                obs = rc.observe(inject_anomalies(sub, AnomalyConfig([rc.ramp_spec()])), 42 + s)
                ci = obs["ci_per_piece_kg_obs"].values; st = obs["state"].values; t = obs["t_s"].values
                valid = np.isfinite(ci) & (st == "PRODUCTION")
                d2 += rc.eval_det(rc.cusum_alert(ci, valid, rc.held_B(obs)), t)[0]
                d0 += rc.eval_det(rc.D0(obs.copy()), t)[0]
                # clean-day D2 false alarms under this treatment
                csub = _apply_credit(rc.clean_day(242 + s, real=True), credit, frac)
                cobs = rc.observe(csub, 242 + s)
                cci = cobs["ci_per_piece_kg_obs"].values; cst = cobs["state"].values
                cval = np.isfinite(cci) & (cst == "PRODUCTION")
                c, e = rc.fp_count_exposure(rc.cusum_alert(cci, cval, rc.held_B(cobs)), cst)
                fa_c += c; fa_e += e
            r, lo, hi = rc.poisson(fa_c, fa_e)
            rows.append({"regen_credit_kw": credit, "treatment": tname,
                         "D2_det": d2 / N, "D0_det": d0 / N, "D2_fa_per_h": round(r, 4)})
            print(f"  credit {credit:.1f}kW  {tname:4s}  D2 {d2/N:.2f}  D0 {d0/N:.2f}  "
                  f"D2 FA {r:.4f}/h")
    pd.DataFrame(rows).to_csv("regen_treatment_summary.csv", index=False)
    print("  wrote regen_treatment_summary.csv")


if __name__ == "__main__":
    main()
