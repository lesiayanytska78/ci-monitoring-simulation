"""
run_transfer_diagnostic.py  (Paper 2 revision, §3.3 / §4.6)
==========================================================
Operating-point transfer diagnostic. The latency-optimal point (k=0.10, h_W=1.0)
is calibrated on the modelled clean-day distribution; on the REAL-spindle substrate
its false-alarm rate rises above the 0.02/h tolerance (a transfer-calibration gap).
Raising only the decision threshold (k fixed, so the detection floor k*P_b is
unchanged) gives a domain-robust point that satisfies the tolerance on the real
substrate at no detection cost.

We sweep h_W on the real substrate and report the false-alarm rate (exact Poisson),
the 2 kW and 1 kW-floor detection, and the latency.

Output: transfer_diagnostic_summary.csv
"""
from __future__ import annotations
import numpy as np, pandas as pd
import revision_common as rc
from anomaly_model import AnomalyConfig, inject_anomalies

N = 100
HWS = [1.0, 1.5, 2.0, 3.0]


def _fault_obs(seed, kw):
    sub = rc.substrate(seed, real=True)
    return rc.observe(inject_anomalies(sub, AnomalyConfig([rc.ramp_spec(magnitude_kw=kw)])), seed)


def main():
    rows = []
    for hw in HWS:
        det2 = det1 = 0; lats = []
        for s in range(N):
            o2 = _fault_obs(42 + s, 2.0)
            ci = o2["ci_per_piece_kg_obs"].values; st = o2["state"].values; t = o2["t_s"].values
            valid = np.isfinite(ci) & (st == "PRODUCTION")
            B = rc.held_B(o2)
            d, lat = rc.eval_det(rc.cusum_alert(ci, valid, B, hw=hw, hc=hw + 1.0), t)
            det2 += d
            if d:
                lats.append(lat)
            o1 = _fault_obs(42 + s, 1.0)
            ci1 = o1["ci_per_piece_kg_obs"].values; st1 = o1["state"].values; t1 = o1["t_s"].values
            v1 = np.isfinite(ci1) & (st1 == "PRODUCTION")
            det1 += rc.eval_det(rc.cusum_alert(ci1, v1, rc.held_B(o1), hw=hw, hc=hw + 1.0), t1)[0]
        fa_c, fa_e = 0, 0.0
        for s in range(N):
            cobs = rc.observe(rc.clean_day(242 + s, real=True), 242 + s)
            cci = cobs["ci_per_piece_kg_obs"].values; cst = cobs["state"].values
            cval = np.isfinite(cci) & (cst == "PRODUCTION")
            c, e = rc.fp_count_exposure(rc.cusum_alert(cci, cval, rc.held_B(cobs), hw=hw, hc=hw + 1.0), cst)
            fa_c += c; fa_e += e
        r, lo, hi = rc.poisson(fa_c, fa_e)
        lat = float(np.median(lats)) if lats else np.nan
        rows.append({"h_warn": hw, "real_fa_per_h": round(r, 4), "fa_lo": round(lo, 4),
                     "fa_hi": round(hi, 4), "det_2kw": det2 / N, "det_1kw_floor": det1 / N,
                     "median_latency_min": round(lat, 1)})
        print(f"  h_W={hw:.1f}  FA {r:.4f}/h [{lo:.4f},{hi:.4f}]  det2 {det2/N:.2f}  "
              f"det1 {det1/N:.2f}  lat {lat:.1f} min")
    pd.DataFrame(rows).to_csv("transfer_diagnostic_summary.csv", index=False)
    print("  wrote transfer_diagnostic_summary.csv")


if __name__ == "__main__":
    main()
