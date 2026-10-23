"""
run_floor_scaling.py  (Paper 2 revision, §4.4)
=============================================
Detection-floor derivation and verification. For a persistent additive power fault
Delta at fixed throughput/EF/window, the fractional CI residual is Delta / P_b,
where P_b is the baseline mean production power, so the CUSUM accumulates only when
this exceeds the slack k -- giving a floor Delta_floor = k * P_b. The floor is
therefore fractional: invariant to the throughput LEVEL (which cancels) but scaling
with the baseline power of the operating regime.

We verify this by a fine severity sweep in four regimes, locating the empirical
50%-detection floor and comparing it with k * P_b.

Output: floor_scaling_summary.csv
"""
from __future__ import annotations
import numpy as np, pandas as pd
import revision_common as rc
from energy_substrate import Config as E, simulate_work_center
from energy_substrate_real import simulate_work_center_real
from anomaly_model import AnomalyConfig, AnomalySpec, inject_anomalies

N = 40
DELTAS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.9]      # fault magnitude sweep (kW)
RAMP = 1800.0                                          # slow onset (inertia regime)


def _Pb(cfg: E) -> float:
    """Baseline mean production power: aux + spindle idle + cutting-duty*increment."""
    return (cfg.aux_base_kw + cfg.spindle_idle_kw
            + cfg.cutting_duty * cfg.spindle_cut_increment_kw)


def _sub(seed, cfg_kw, real):
    cfg = E(seed=seed, **cfg_kw)
    return (simulate_work_center_real(cfg) if real else simulate_work_center(cfg))


def _det_rate(cfg_kw, real, delta):
    d = 0
    for s in range(N):
        sub = _sub(42 + s, cfg_kw, real)
        spec = AnomalySpec(onset_hour=10, duration_minutes=240, magnitude_kw=delta,
                           onset_profile="ramp", onset_ramp_seconds=RAMP,
                           affects="spindle", label="x")
        obs = rc.observe(inject_anomalies(sub, AnomalyConfig([spec])), 42 + s)
        ci = obs["ci_per_piece_kg_obs"].values; st = obs["state"].values; t = obs["t_s"].values
        valid = np.isfinite(ci) & (st == "PRODUCTION")
        d += rc.eval_det(rc.cusum_alert(ci, valid, rc.held_B(obs)), t)[0]
    return d / N


def _floor50(curve_delta, curve_rate):
    """Linear-interpolate the magnitude at which detection crosses 0.5."""
    x = np.array(curve_delta); y = np.array(curve_rate)
    for i in range(1, len(x)):
        if y[i - 1] < 0.5 <= y[i]:
            return x[i - 1] + (0.5 - y[i - 1]) * (x[i] - x[i - 1]) / (y[i] - y[i - 1])
    return np.nan


REGIMES = [
    ("real substrate",            {}, True),
    ("synthetic 60 pcs/h",        {}, False),
    ("throughput 40 pcs/h",       {"pieces_per_hour": 40.0}, False),
    ("throughput 80 pcs/h",       {"pieces_per_hour": 80.0}, False),
    ("higher aux (+2 kW)",        {"aux_base_kw": 4.5}, False),
]


def main():
    rows = []
    for name, cfg_kw, real in REGIMES:
        pb = _Pb(E(**cfg_kw)) if not real else 3.5     # real-substrate P_b ~ 3.5 kW (measured)
        rates = [_det_rate(cfg_kw, real, d) for d in DELTAS]
        floor = _floor50(DELTAS, rates)
        pred = rc.K * pb
        rows.append({"regime": name, "P_b_kw": round(pb, 2),
                     "predicted_k_Pb": round(pred, 3),
                     "empirical_50pct_floor": round(floor, 3) if np.isfinite(floor) else np.nan})
        print(f"  {name:22s} P_b={pb:4.2f}  k*P_b={pred:.3f}  empirical floor={floor:.3f}")
    pd.DataFrame(rows).to_csv("floor_scaling_summary.csv", index=False)
    print("  wrote floor_scaling_summary.csv")


if __name__ == "__main__":
    main()
