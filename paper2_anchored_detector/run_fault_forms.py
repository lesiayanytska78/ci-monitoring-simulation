"""
run_fault_forms.py  (Paper 2 revision, §4.10)
============================================
Fault-form and trajectory robustness. (1) Six fault morphologies at 2 kW -- ramp,
step, step-ramp, intermittent, oscillatory, partial-recovery -- D0 vs D2. (2)
Randomised fault trajectories (onset, magnitude, duration, ramp drawn per seed) so
the intervals reflect fault uncertainty rather than one prescribed trajectory.

The proposed detector holds 100% across positive above-floor morphologies; the
deployed detector is strongly form-dependent.

N=60 per point. Output: fault_forms_summary.csv
"""
from __future__ import annotations
import numpy as np, pandas as pd
import revision_common as rc
from anomaly_model import AnomalyConfig, AnomalySpec, inject_anomalies

N = 60
FORMS = ["ramp", "step", "step_ramp", "intermittent", "oscillatory", "partial_recovery"]


def _day(seed, spec):
    sub = rc.substrate(seed)
    return rc.observe(inject_anomalies(sub, AnomalyConfig([spec])), seed)


def _det_pair(obs):
    ci = obs["ci_per_piece_kg_obs"].values; st = obs["state"].values; t = obs["t_s"].values
    valid = np.isfinite(ci) & (st == "PRODUCTION")
    d0 = rc.eval_det(rc.D0(obs.copy()), t)[0]
    d2 = rc.eval_det(rc.cusum_alert(ci, valid, rc.held_B(obs)), t)[0]
    return d0, d2


def main():
    rows = []
    print("(1) Six morphologies at 2 kW:")
    for form in FORMS:
        d0 = d2 = 0
        for s in range(N):
            spec = AnomalySpec(onset_hour=10, duration_minutes=240, magnitude_kw=2.0,
                               onset_profile=form, onset_ramp_seconds=3600.0,
                               affects="spindle", label=form)
            a, b = _det_pair(_day(42 + s, spec)); d0 += a; d2 += b
        lo2, hi2 = rc.wilson(d2, N)
        rows.append(dict(kind="morphology", form=form, D0_det=d0/N, D2_det=d2/N,
                         D2_lo=round(lo2, 3), D2_hi=round(hi2, 3)))
        print(f"   {form:16s} D0 {d0/N:.2f}   D2 {d2/N:.2f} [{lo2:.2f},{hi2:.2f}]")

    print("\n(2) Randomised trajectories:")
    d0 = d2 = 0
    for s in range(N):
        rng = np.random.default_rng(1234 + s)
        onset = rng.uniform(8, 12)
        mag = rng.uniform(1.0, 3.0)
        dur = rng.uniform(2.0, 6.0) * 60.0
        ramp = float(10 ** rng.uniform(np.log10(120), np.log10(7200)))
        spec = AnomalySpec(onset_hour=onset, duration_minutes=dur, magnitude_kw=mag,
                           onset_profile="ramp", onset_ramp_seconds=ramp,
                           affects="spindle", label="rand")
        obs = _day(42 + s, spec)
        ci = obs["ci_per_piece_kg_obs"].values; st = obs["state"].values; t = obs["t_s"].values
        valid = np.isfinite(ci) & (st == "PRODUCTION")
        t0 = onset * 3600.0; t1 = t0 + dur * 60.0
        d0 += rc.eval_det(rc.D0(obs.copy()), t, t0, t1)[0]
        d2 += rc.eval_det(rc.cusum_alert(ci, valid, rc.held_B(obs)), t, t0, t1)[0]
    lo0, hi0 = rc.wilson(d0, N); lo2, hi2 = rc.wilson(d2, N)
    print(f"   randomised   D0 {d0/N:.2f} [{lo0:.2f},{hi0:.2f}]   D2 {d2/N:.2f} [{lo2:.2f},{hi2:.2f}]")
    rows.append(dict(kind="randomised", form="random_trajectory", D0_det=d0/N, D2_det=d2/N,
                     D2_lo=round(lo2, 3), D2_hi=round(hi2, 3)))
    rows.append(dict(kind="randomised", form="random_trajectory_D0_ci", D0_det=d0/N,
                     D2_det=np.nan, D2_lo=round(lo0, 3), D2_hi=round(hi0, 3)))
    pd.DataFrame(rows).to_csv("fault_forms_summary.csv", index=False)
    print("  wrote fault_forms_summary.csv")


if __name__ == "__main__":
    main()
