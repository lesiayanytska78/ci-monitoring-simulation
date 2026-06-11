"""
sensitivity.py
==============
Module 5 of the MES carbon-intensity monitoring simulation.

Purpose
-------
The scenario harness. Runs the substrate-anomaly-monitor pipeline across
parameter sweeps and aggregates outcome metrics. Three core sweeps are
implemented here; each produces one of the paper's main figures:

  1. Latency vs severity (per fault duration)        -> "how big and how long
                                                         before we catch it?"
  2. Detection rate vs severity (per sampling rate)  -> "what does sensor
                                                         cadence cost us?"
  3. ROC: detection rate vs false-positive rate      -> "where's the operating
                                                         point?"

Plus baseline statistics on the false-positive rate from anomaly-free days.

All scenarios use the calibrated modules with provenance-tagged parameters.
Raw results are saved to CSV so reviewers can re-run any aggregation.

Honest reporting
----------------
The sweeps produce whatever they produce. No tuning to hit a target. The
honest contribution is the *characterisation* - the curves showing tradeoffs
and limits, including where the architecture struggles.
"""

from __future__ import annotations
from dataclasses import asdict
import time
import numpy as np
import pandas as pd

from energy_substrate import Config as EnergyConfig, simulate_work_center
from carbon_layer import CarbonConfig
from anomaly_model import AnomalyConfig, AnomalySpec, inject_anomalies
from monitoring import MonitorConfig, run_monitoring, evaluate


EF = CarbonConfig().static_emission_factor_kg_per_kwh   # 0.230 kg CO2e/kWh


# ----------------------------------------------------------------------
# Substrate-without-anomaly helper (for false-positive baselines)
# ----------------------------------------------------------------------
def empty_anomaly_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add the anomaly bookkeeping columns set to no-fault, for FP runs."""
    df = df.copy()
    df["anomaly_kw"] = 0.0
    df["anomaly_active"] = False
    df["anomaly_labels"] = ""
    return df


# ----------------------------------------------------------------------
# Single-scenario runner
# ----------------------------------------------------------------------
def run_scenario(params: dict, seed: int = 42) -> dict:
    """Run one (substrate, anomaly, monitor) end-to-end and return metrics."""
    e_cfg = EnergyConfig(seed=seed)
    substrate = simulate_work_center(e_cfg)

    sev = params.get("severity_kw", 0.0)
    dur = params.get("duration_min", 0.0)
    affects = params.get("affects", "machine")

    truth_specs = []
    if sev > 0 and dur > 0:
        a = AnomalySpec(
            onset_hour=params.get("onset_h", 10.0),
            duration_minutes=dur,
            magnitude_kw=sev,
            onset_profile=params.get("profile", "ramp"),
            onset_ramp_seconds=params.get("ramp_s", 120.0),
            affects=affects,
            label=f"sev{sev:g}_dur{dur:g}_{affects}",
        )
        substrate = inject_anomalies(substrate, AnomalyConfig([a]))
        truth_specs = [a]
    else:
        substrate = empty_anomaly_columns(substrate)

    m_cfg = MonitorConfig(
        sampling_interval_seconds=params.get("sampling_s", 60.0),
        meter_accuracy_pct=params.get("meter_pct", 1.0),
        threshold_type=params.get("threshold_type", "relative"),
        rel_threshold_pct=params.get("threshold_pct", 25.0),
        abs_threshold_g_per_piece=params.get("abs_thr_g", 30.0),
        sigma_k=params.get("sigma_k", 3.0),
        baseline_window_minutes=params.get("baseline_min", 60.0),
        warning_persistence_samples=params.get("persist_w", 3),
        critical_persistence_samples=params.get("persist_c", 9),
    )
    obs = run_monitoring(substrate, m_cfg, EF, seed=seed + 1000)

    out = {**params, "seed": seed}
    if truth_specs:
        ev = evaluate(obs, substrate, truth_specs)
        f = ev["per_fault"][0]
        out.update({
            "warning_detected": f["warning_detected"],
            "warning_latency_min": f["warning_latency_min"],
            "critical_detected": f["critical_detected"],
            "critical_latency_min": f["critical_latency_min"],
            "attribution": f["attribution"],
            "attribution_correct": f["attribution_correct"],
            "n_fp_warnings": ev["false_positive_warnings"],
        })
    else:
        warn = (obs["alert_level"].values >= 1)
        diffs = np.diff(warn.astype(int))
        n_warn_starts = int((diffs == 1).sum() + (1 if warn[0] else 0))
        op_hours = obs.loc[obs["state"] == "PRODUCTION", "t_s"].count() \
                   * m_cfg.sampling_interval_seconds / 3600.0
        out.update({
            "warning_detected": None, "warning_latency_min": None,
            "critical_detected": None, "critical_latency_min": None,
            "attribution": None, "attribution_correct": None,
            "n_fp_warnings": n_warn_starts,
            "fp_rate_per_production_hour": n_warn_starts / max(op_hours, 1e-6),
        })
    return out


def _persistence_for_sampling(sampling_s: float) -> tuple:
    """Keep warning/critical persistence at ~3 / ~9 minutes regardless of sampling rate."""
    w = max(2, int(round(180.0 / sampling_s)))
    c = max(w + 2, int(round(540.0 / sampling_s)))
    return w, c


# ----------------------------------------------------------------------
# Sweep 1: latency vs severity, per fault duration
# ----------------------------------------------------------------------
def sweep_severity_x_duration(severities, durations, n_seeds=3,
                              affects="machine") -> pd.DataFrame:
    rows = []
    total = len(severities) * len(durations) * n_seeds
    i = 0
    for sev in severities:
        for dur in durations:
            for s in range(n_seeds):
                i += 1
                if i % 20 == 0 or i == total:
                    print(f"  [sweep 1] {i}/{total}")
                rows.append(run_scenario(
                    {"severity_kw": sev, "duration_min": dur, "affects": affects},
                    seed=42 + s,
                ))
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------
# Sweep 2: detection rate vs severity, per sampling rate
# ----------------------------------------------------------------------
def sweep_severity_x_sampling(severities, samplings, n_seeds=3,
                              duration_min=240, affects="machine") -> pd.DataFrame:
    rows = []
    total = len(severities) * len(samplings) * n_seeds
    i = 0
    for sev in severities:
        for samp in samplings:
            w, c = _persistence_for_sampling(samp)
            for s in range(n_seeds):
                i += 1
                if i % 20 == 0 or i == total:
                    print(f"  [sweep 2] {i}/{total}")
                rows.append(run_scenario(
                    {"severity_kw": sev, "duration_min": duration_min,
                     "sampling_s": samp, "persist_w": w, "persist_c": c,
                     "affects": affects},
                    seed=42 + s,
                ))
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------
# Sweep 3: ROC - vary threshold tightness, with and without anomaly
# ----------------------------------------------------------------------
def sweep_roc(thresholds, n_seeds=5, severity_kw=1.5, duration_min=240,
              affects="machine") -> pd.DataFrame:
    rows = []
    total = len(thresholds) * n_seeds * 2
    i = 0
    for thr in thresholds:
        for s in range(n_seeds):
            i += 1
            if i % 20 == 0 or i == total:
                print(f"  [sweep 3] {i}/{total}")
            r = run_scenario({"severity_kw": severity_kw, "duration_min": duration_min,
                              "threshold_pct": thr, "affects": affects}, seed=42 + s)
            r["scenario"] = "with_anomaly"
            rows.append(r)
        for s in range(n_seeds):
            i += 1
            if i % 20 == 0 or i == total:
                print(f"  [sweep 3] {i}/{total}")
            r = run_scenario({"severity_kw": 0.0, "duration_min": 0.0,
                              "threshold_pct": thr}, seed=242 + s)
            r["scenario"] = "no_anomaly"
            rows.append(r)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------
# Sweep 4: cross-archetype - all four fault types at varying severity
# ----------------------------------------------------------------------
def sweep_archetypes(severities, n_seeds=10, duration_min=240) -> pd.DataFrame:
    """Run each of the four archetypes across severities."""
    archetypes = {
        # name                    affects     profile  ramp_s
        "compressed_air_leak":   ("machine", "ramp", 120.0),
        "machine_left_on":       ("spindle", "step",   0.0),
        "tool_wear":             ("spindle", "ramp", 3600.0),
        "coolant_pump_fault":    ("machine", "step",   0.0),
    }
    rows = []
    total = len(severities) * len(archetypes) * n_seeds
    i = 0
    for arch_name, (affects, profile, ramp_s) in archetypes.items():
        for sev in severities:
            for s in range(n_seeds):
                i += 1
                if i % 50 == 0 or i == total:
                    print(f"  [sweep 4] {i}/{total}")
                r = run_scenario(
                    {"severity_kw": sev, "duration_min": duration_min,
                     "affects": affects, "profile": profile, "ramp_s": ramp_s},
                    seed=42 + s,
                )
                r["archetype"] = arch_name
                rows.append(r)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------
# Sweep 5: ROC for each threshold type (absolute / relative / statistical)
# ----------------------------------------------------------------------
def sweep_threshold_types(n_seeds=8, severity_kw=1.5, duration_min=240) -> pd.DataFrame:
    """Compare the three threshold types on the same canonical fault, by sweeping
    each type's own tightness parameter and recording detection + FP rate."""
    # each grid is in the type's own natural units
    grids = {
        "absolute":    [15, 20, 22, 24, 26, 28, 30, 35, 40, 50, 75],   # g CO2e/piece
        "relative":    [5, 7, 10, 12, 15, 20, 25, 30, 40, 50, 75],     # % above baseline
        "statistical": [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0],  # sigmas
    }
    param_key = {"absolute": "abs_thr_g", "relative": "threshold_pct", "statistical": "sigma_k"}
    rows = []
    total = sum(len(g) * n_seeds * 2 for g in grids.values())
    i = 0
    for ttype, grid in grids.items():
        for tval in grid:
            for s in range(n_seeds):
                i += 1
                if i % 80 == 0 or i == total:
                    print(f"  [sweep 5] {i}/{total}")
                p = {"severity_kw": severity_kw, "duration_min": duration_min,
                     "threshold_type": ttype, param_key[ttype]: tval, "affects": "machine"}
                r = run_scenario(p, seed=42 + s)
                r["scenario"] = "with_anomaly"
                r["threshold_value"] = tval
                rows.append(r)
            for s in range(n_seeds):
                i += 1
                if i % 80 == 0 or i == total:
                    print(f"  [sweep 5] {i}/{total}")
                p = {"severity_kw": 0.0, "duration_min": 0.0,
                     "threshold_type": ttype, param_key[ttype]: tval}
                r = run_scenario(p, seed=242 + s)
                r["scenario"] = "no_anomaly"
                r["threshold_value"] = tval
                rows.append(r)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------
# Sweep 6: attribution accuracy by severity and channel
# ----------------------------------------------------------------------
def sweep_attribution(severities, channels=("machine", "spindle"), n_seeds=10,
                      duration_min=240) -> pd.DataFrame:
    """Run faults in machine vs spindle channel; record whether attribution is correct."""
    rows = []
    total = len(channels) * len(severities) * n_seeds
    i = 0
    for ch in channels:
        for sev in severities:
            for s in range(n_seeds):
                i += 1
                if i % 50 == 0 or i == total:
                    print(f"  [sweep 6] {i}/{total}")
                # use ramp onset (more realistic & harder for attribution)
                r = run_scenario(
                    {"severity_kw": sev, "duration_min": duration_min,
                     "affects": ch, "profile": "ramp", "ramp_s": 120.0},
                    seed=42 + s,
                )
                rows.append(r)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------
# Sweep 7: ramp-time vs detection (the tool-wear-is-baseline-tracking probe)
# ----------------------------------------------------------------------
def sweep_ramp_time(ramp_seconds, severities, n_seeds=10, duration_min=240,
                    affects="spindle") -> pd.DataFrame:
    """Sweep onset-ramp duration vs severity to characterize detection as a
    function of the ramp-time / baseline-window ratio."""
    rows = []
    total = len(ramp_seconds) * len(severities) * n_seeds
    i = 0
    for rs in ramp_seconds:
        for sev in severities:
            for s in range(n_seeds):
                i += 1
                if i % 50 == 0 or i == total:
                    print(f"  [sweep 7] {i}/{total}")
                rows.append(run_scenario(
                    {"severity_kw": sev, "duration_min": duration_min,
                     "affects": affects, "profile": "ramp", "ramp_s": rs},
                    seed=42 + s,
                ))
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------
# Sweep 8: high-seed boundary sweep for confidence intervals on the floor
# ----------------------------------------------------------------------
def sweep_boundary_high_seed(boundary_severities, n_seeds=50, duration_min=240,
                             affects="machine") -> pd.DataFrame:
    """Re-run boundary severities with many seeds for bootstrap CIs on the
    detection floor."""
    rows = []
    total = len(boundary_severities) * n_seeds
    i = 0
    for sev in boundary_severities:
        for s in range(n_seeds):
            i += 1
            if i % 50 == 0 or i == total:
                print(f"  [sweep 8] {i}/{total}")
            rows.append(run_scenario(
                {"severity_kw": sev, "duration_min": duration_min,
                 "affects": affects, "profile": "ramp", "ramp_s": 120.0},
                seed=42 + s,
            ))
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------
# Run all and save
# ----------------------------------------------------------------------
if __name__ == "__main__":
    t0 = time.time()
    print("=== Module 5 (refined): sensitivity sweeps, 10 seeds per condition ===")

    print("\n[1/6] latency + detection vs severity, per duration")
    severities1 = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0]
    durations1 = [30, 120, 240]
    df1 = sweep_severity_x_duration(severities1, durations1, n_seeds=10)
    df1.to_csv("../data/sweep1_latency.csv", index=False)
    print(f"   -> {len(df1)} runs saved")

    print("\n[2/6] detection rate vs severity, per sampling rate")
    severities2 = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
    samplings2 = [30, 60, 300, 900]
    df2 = sweep_severity_x_sampling(severities2, samplings2, n_seeds=10, duration_min=240)
    df2.to_csv("../data/sweep2_sampling.csv", index=False)
    print(f"   -> {len(df2)} runs saved")

    print("\n[3/6] ROC - relative-threshold tightness sweep")
    thresholds3 = [5, 8, 10, 12, 15, 20, 25, 30, 40, 50, 75, 100]
    df3 = sweep_roc(thresholds3, n_seeds=10, severity_kw=1.5, duration_min=240)
    df3.to_csv("../data/sweep3_roc.csv", index=False)
    print(f"   -> {len(df3)} runs saved")

    print("\n[4/6] cross-archetype generalisation")
    severities4 = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
    df4 = sweep_archetypes(severities4, n_seeds=10)
    df4.to_csv("../data/sweep4_archetypes.csv", index=False)
    print(f"   -> {len(df4)} runs saved")

    print("\n[5/6] threshold-type comparison")
    df5 = sweep_threshold_types(n_seeds=8, severity_kw=1.5, duration_min=240)
    df5.to_csv("../data/sweep5_threshold_types.csv", index=False)
    print(f"   -> {len(df5)} runs saved")

    print("\n[6/6] attribution accuracy by severity and channel")
    severities6 = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0]
    df6 = sweep_attribution(severities6, channels=("machine", "spindle"), n_seeds=10)
    df6.to_csv("../data/sweep6_attribution.csv", index=False)
    print(f"   -> {len(df6)} runs saved")

    elapsed = time.time() - t0
    total_runs = len(df1) + len(df2) + len(df3) + len(df4) + len(df5) + len(df6)
    print(f"\nDone in {elapsed:.1f} s. Total runs: {total_runs}.")
