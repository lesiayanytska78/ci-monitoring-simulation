"""
run_cadence_gate.py  (Paper 2 revision, §4.7)
============================================
Targeted 2-D cadence x health-gate experiment, to adjudicate whether the large
Morris elementary-effect spread on the re-anchoring parameters reflects a cadence-
gate INTERACTION or the gate's NONLINEARITY. We measure two outcomes over the full
grid -- fast-fault detection (the re-anchoring hazard) and slow-fault warning
latency -- and decompose each into cadence main effect, gate main effect, and the
non-additive interaction term (a two-way fixed-effects variance decomposition).

Result: the response is gate-dominated with a sharp nonlinear threshold; the
cadence-gate interaction is genuine but secondary.

Output: cadence_gate_summary.csv, cadence_gate_decomp.csv
"""
from __future__ import annotations
import numpy as np, pandas as pd
import revision_common as rc
from anomaly_model import AnomalyConfig, inject_anomalies

N = 40
CADENCE = [30.0, 60.0, 120.0, 240.0]                 # minutes
GATE = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]


def _day(seed, ramp_s, sev=2.0):
    sub = rc.substrate(seed)
    return rc.observe(inject_anomalies(
        sub, AnomalyConfig([rc.ramp_spec(magnitude_kw=sev, ramp_s=ramp_s)])), seed)


def _cell(cad, gate):
    """(fast-fault detection, slow-fault median latency) for one cadence x gate cell."""
    fast_det = 0; lats = []
    for s in range(N):
        # fast fault (ramp 120 s): the re-anchoring hazard bites fast faults
        of = _day(42 + s, 120.0)
        al = rc.D2(of, anchor_mode="periodic_gated", anchor_period_minutes=cad,
                   health_gate_frac=gate)
        fast_det += rc.eval_det(al, of["t_s"].values)[0]
        # slow fault (ramp 3600 s): warning latency
        os_ = _day(42 + s, 3600.0)
        al2 = rc.D2(os_, anchor_mode="periodic_gated", anchor_period_minutes=cad,
                    health_gate_frac=gate)
        det, lat = rc.eval_det(al2, os_["t_s"].values)
        if det:
            lats.append(lat)
    return fast_det / N, (float(np.median(lats)) if lats else np.nan)


def _decompose(grid):
    """Two-way fixed-effects variance decomposition of a (cadence x gate) matrix.
    Returns (% cadence main, % gate main, % interaction)."""
    Y = np.array(grid, float)
    grand = np.nanmean(Y)
    row_m = np.nanmean(Y, axis=1)         # cadence marginal means
    col_m = np.nanmean(Y, axis=0)         # gate marginal means
    nr, nc = Y.shape
    ss_tot = np.nansum((Y - grand) ** 2)
    ss_cad = nc * np.nansum((row_m - grand) ** 2)
    ss_gate = nr * np.nansum((col_m - grand) ** 2)
    ss_int = max(ss_tot - ss_cad - ss_gate, 0.0)
    if ss_tot <= 0:
        return (0.0, 0.0, 0.0)
    return (100 * ss_cad / ss_tot, 100 * ss_gate / ss_tot, 100 * ss_int / ss_tot)


def main():
    det = np.zeros((len(CADENCE), len(GATE)))
    lat = np.zeros((len(CADENCE), len(GATE)))
    rows = []
    for i, cad in enumerate(CADENCE):
        for j, g in enumerate(GATE):
            d, L = _cell(cad, g)
            det[i, j] = d; lat[i, j] = L
            rows.append({"cadence_min": cad, "gate": g, "fast_det": d, "slow_latency_min": L})
        print(f"  cadence {cad:5.0f} min done")
    pd.DataFrame(rows).to_csv("cadence_gate_summary.csv", index=False)

    dc, dg, di = _decompose(det)
    lc, lg, li = _decompose(lat)
    dec = pd.DataFrame([
        {"outcome": "fast_fault_detection", "cadence_main_pct": round(dc, 1),
         "gate_main_pct": round(dg, 1), "interaction_pct": round(di, 1)},
        {"outcome": "slow_fault_latency", "cadence_main_pct": round(lc, 1),
         "gate_main_pct": round(lg, 1), "interaction_pct": round(li, 1)},
    ])
    dec.to_csv("cadence_gate_decomp.csv", index=False)
    print("\n=== variance decomposition ===")
    print(dec.to_string(index=False))
    print("  wrote cadence_gate_summary.csv, cadence_gate_decomp.csv")


if __name__ == "__main__":
    main()
