"""
monitoring.py
=============
Module 4 of the MES carbon-intensity monitoring simulation.

Purpose
-------
The monitoring layer. Real MES/SCADA systems don't see the per-second ground
truth - they see a downsampled, slightly-noisy version. This module models
that, then applies the detection logic the architecture proposes:

    substrate -> sensor sampling -> measurement noise
              -> observed CI per piece
              -> rolling baseline + threshold
              -> persistence requirement (tiered warning / critical)
              -> attribution by component (machine vs spindle)

Because Modules 1-3 generate ground truth (we know when each fault started),
every alert can be evaluated against it: detection latency, true positives,
false positives, attribution correctness.

Detection logic - three flavours, all swept in the sensitivity analysis:
    "absolute"     CI > fixed limit
    "relative"     CI > (1 + r) * rolling baseline             <- default
    "statistical"  CI > rolling mean + k * rolling sigma

Persistence: a sample must remain above threshold for N consecutive samples
before firing. This is the standard industrial-alerting practice that suppresses
single-sample transients (start-of-run warm-up, sensor glitches) without
suppressing sustained faults. Tiered: warning after W samples, critical
after C samples (with W < C).

Provenance tags
---------------
  [ANCHORED]   from a real measurement
  [LITERATURE] cited from published standards / engineering practice
  [ASSUMPTION] provisional engineering estimate; SWEPT in sensitivity analysis
"""

from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
import pandas as pd


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
@dataclass
class MonitorConfig:
    # --- Sensor model ---
    # [ASSUMPTION] typical MES/SCADA energy-metering polling rate.
    #   Real systems range from 1 s (high-end submetering) to 15 min
    #   (utility-grade). 60 s is a common middle ground. SWEPT.
    sampling_interval_seconds: float = 60.0

    # [LITERATURE] energy-meter accuracy class, % of reading.
    #   IEC 61557-12 / ANSI C12.20: Class 0.5 / 1 / 2 = ±0.5 / ±1 / ±2 %.
    #   Class 1 chosen as default. SWEPT.
    meter_accuracy_pct: float = 1.0

    # --- Threshold logic ---
    # [ASSUMPTION] which detection rule to use. SWEPT (all three exercised).
    threshold_type: str = "relative"   # "absolute" | "relative" | "statistical"

    # parameters per mode
    abs_threshold_g_per_piece: float = 30.0   # for "absolute" mode
    rel_threshold_pct: float = 25.0           # for "relative" mode
    sigma_k: float = 3.0                      # for "statistical" mode

    # [ASSUMPTION] window used to estimate the baseline / sigma. 60 min is
    # long enough to be stable, short enough to track real shift dynamics.
    # SWEPT.
    baseline_window_minutes: float = 60.0

    # [ASSUMPTION] window over which CI per piece is *estimated*, independent
    # of meter sampling rate. Per-meter-window CI is unstable when
    # pieces-per-window is small (e.g., 30 s sampling at 60 pieces/h gives
    # ~0.5 pieces per window). The estimation window aggregates multiple
    # meter samples for a stable CI signal. SWEPT.
    ci_estimation_window_minutes: float = 15.0

    # --- Persistence (tiered) ---
    # [LITERATURE] industrial-alerting practice: require N consecutive
    # over-threshold samples to suppress noise. Tiered = warning then
    # critical at a longer streak.
    warning_persistence_samples: int = 3      # ~3 min at 60 s sampling
    critical_persistence_samples: int = 9     # ~9 min at 60 s sampling


# ----------------------------------------------------------------------
# Sensor model: downsample + measurement noise
# ----------------------------------------------------------------------
def _block_groups(df: pd.DataFrame, every_s: int) -> np.ndarray:
    """Group indices for block-aggregation at the sampling rate."""
    dt_s = df["t_s"].iloc[1] - df["t_s"].iloc[0]
    return (df.index // max(1, int(round(every_s / dt_s)))).astype(int)


def sample_and_noise(substrate: pd.DataFrame, cfg: MonitorConfig,
                     emission_factor_kg_per_kwh: float, seed: int = 7) -> pd.DataFrame:
    """Downsample the ground-truth substrate to the meter's sampling rate, add
    proportional measurement error, and compute the observed CI per piece."""
    rng = np.random.default_rng(seed)
    g = _block_groups(substrate, cfg.sampling_interval_seconds)

    obs = pd.DataFrame()
    obs["t_s"] = substrate["t_s"].groupby(g).first().values
    obs["state"] = substrate["state"].groupby(g).agg(
        lambda x: x.mode().iloc[0] if len(x) else "UNKNOWN").values
    # block-averaged powers (what a meter integrates over the interval)
    obs["machine_kw_obs"] = substrate["machine_kw"].groupby(g).mean().values
    obs["spindle_kw_obs"] = substrate["spindle_kw"].groupby(g).mean().values
    obs["total_kw_obs"] = substrate["total_kw"].groupby(g).mean().values
    # pieces produced in window
    obs["pieces_in_window"] = substrate["pieces_rate"].groupby(g).sum().values
    # ground truth (kept for evaluation, never used in detection)
    obs["anomaly_active_truth"] = substrate["anomaly_active"].groupby(g).max().values \
        if "anomaly_active" in substrate.columns else False

    # measurement noise: proportional, applied independently per channel
    frac = cfg.meter_accuracy_pct / 100.0
    n = len(obs)
    for ch in ["machine_kw_obs", "spindle_kw_obs"]:
        obs[ch] = np.clip(obs[ch].values * (1.0 + frac * rng.standard_normal(n)), 0.0, None)
    obs["total_kw_obs"] = obs["machine_kw_obs"] + obs["spindle_kw_obs"]

    # observed CI per piece - computed over a rolling estimation window of
    # meter samples in PRODUCTION state only (independent of meter sampling
    # rate). This decouples detection cadence (how often we check) from
    # estimation stability (how many pieces are aggregated). Idle/offline
    # samples are excluded from the rolling accumulators so CI is not
    # inflated at production-resume by recent idle stretches.
    dt_h = cfg.sampling_interval_seconds / 3600.0
    energy_kwh_step = (obs["total_kw_obs"] * dt_h).values
    emissions_kg_step = energy_kwh_step * emission_factor_kg_per_kwh
    obs["energy_kwh_window"] = energy_kwh_step
    obs["emissions_kg_window"] = emissions_kg_step

    in_prod = (obs["state"].values == "PRODUCTION")
    emiss_for_ci = np.where(in_prod, emissions_kg_step, 0.0)
    pieces_for_ci = np.where(in_prod, obs["pieces_in_window"].values, 0.0)

    est_win_n = max(1, int(round(cfg.ci_estimation_window_minutes * 60.0
                                  / cfg.sampling_interval_seconds)))
    em_roll = pd.Series(emiss_for_ci).rolling(est_win_n, min_periods=1).sum().values
    pc_roll = pd.Series(pieces_for_ci).rolling(est_win_n, min_periods=1).sum().values
    prod_samples_in_window = pd.Series(in_prod.astype(int)).rolling(
        est_win_n, min_periods=1).sum().values
    min_prod_samples = max(1, est_win_n // 4)   # require >=25% of window in production

    obs["ci_per_piece_kg_obs"] = np.where(
        (pc_roll > 0) & (prod_samples_in_window >= min_prod_samples),
        em_roll / np.where(pc_roll > 0, pc_roll, 1.0), np.nan
    )
    return obs


# ----------------------------------------------------------------------
# Detection: baseline + threshold + persistence + tiered alerts
# ----------------------------------------------------------------------
def detect(obs: pd.DataFrame, cfg: MonitorConfig) -> pd.DataFrame:
    """Add baseline, threshold, and alert_level columns to the observed frame.

    alert_level: 0 = clear, 1 = warning, 2 = critical."""
    ci = obs["ci_per_piece_kg_obs"].values
    valid = ~np.isnan(ci) & (obs["state"].values == "PRODUCTION")

    win_n = max(2, int(round(cfg.baseline_window_minutes * 60.0
                              / cfg.sampling_interval_seconds)))
    min_p = max(2, win_n // 3)
    ci_s = pd.Series(np.where(valid, ci, np.nan))
    baseline = ci_s.rolling(win_n, min_periods=min_p).median().values
    sigma = ci_s.rolling(win_n, min_periods=min_p).std().values

    if cfg.threshold_type == "absolute":
        thr = np.full_like(ci, cfg.abs_threshold_g_per_piece / 1000.0)
    elif cfg.threshold_type == "relative":
        thr = baseline * (1.0 + cfg.rel_threshold_pct / 100.0)
    elif cfg.threshold_type == "statistical":
        thr = baseline + cfg.sigma_k * sigma
    else:
        raise ValueError(f"Unknown threshold_type: {cfg.threshold_type}")

    over = valid & ~np.isnan(thr) & (ci > thr)

    # streak length of consecutive over-threshold samples
    streak = np.zeros(len(over), dtype=int)
    s = 0
    for i, o in enumerate(over):
        s = s + 1 if o else 0
        streak[i] = s

    alert_level = np.zeros(len(over), dtype=int)
    alert_level[streak >= cfg.warning_persistence_samples] = 1
    alert_level[streak >= cfg.critical_persistence_samples] = 2

    obs["baseline_kg_per_piece"] = baseline
    obs["threshold_kg_per_piece"] = thr
    obs["over_threshold"] = over
    obs["alert_level"] = alert_level
    return obs


# ----------------------------------------------------------------------
# Attribution: which component caused an excursion?
# ----------------------------------------------------------------------
def attribute(obs: pd.DataFrame, cfg: MonitorConfig) -> pd.DataFrame:
    """For each over-threshold sample, decide whether excess is in the machine
    or spindle channel, by comparing each against its own rolling baseline."""
    win_n = max(2, int(round(cfg.baseline_window_minutes * 60.0
                              / cfg.sampling_interval_seconds)))
    min_p = max(2, win_n // 3)
    machine_base = pd.Series(obs["machine_kw_obs"]).rolling(win_n, min_periods=min_p).median().values
    spindle_base = pd.Series(obs["spindle_kw_obs"]).rolling(win_n, min_periods=min_p).median().values
    excess_machine = obs["machine_kw_obs"].values - machine_base
    excess_spindle = obs["spindle_kw_obs"].values - spindle_base
    attrib = np.where(excess_machine > excess_spindle, "machine", "spindle")
    obs["attribution"] = np.where(obs["over_threshold"].values, attrib, "")
    obs["excess_machine_kw"] = np.where(obs["over_threshold"].values, excess_machine, 0.0)
    obs["excess_spindle_kw"] = np.where(obs["over_threshold"].values, excess_spindle, 0.0)
    return obs


# ----------------------------------------------------------------------
# Evaluation against ground truth
# ----------------------------------------------------------------------
def _runs(mask: np.ndarray) -> list:
    """Return list of (start_idx, end_idx_exclusive) for contiguous True runs."""
    if not mask.any():
        return []
    diffs = np.diff(mask.astype(int))
    starts = list(np.where(diffs == 1)[0] + 1)
    ends = list(np.where(diffs == -1)[0] + 1)
    if mask[0]:
        starts = [0] + starts
    if mask[-1]:
        ends = ends + [len(mask)]
    return list(zip(starts, ends))


def evaluate(obs: pd.DataFrame, substrate_truth: pd.DataFrame,
             anomaly_specs: list) -> dict:
    """Compare alerts against the ground-truth anomaly intervals."""
    if "anomaly_active" not in substrate_truth.columns:
        return {"n_anomalies": 0, "note": "no anomalies in substrate"}

    truth_mask = substrate_truth["anomaly_active"].values
    truth_t = substrate_truth["t_s"].values
    truth_runs = _runs(truth_mask)
    truth_intervals = [(truth_t[s], truth_t[e - 1]) for (s, e) in truth_runs]

    obs_t = obs["t_s"].values
    warn_mask = obs["alert_level"].values >= 1
    crit_mask = obs["alert_level"].values >= 2
    warn_runs = _runs(warn_mask)
    crit_runs = _runs(crit_mask)
    warn_starts = [obs_t[s] for (s, _) in warn_runs]
    crit_starts = [obs_t[s] for (s, _) in crit_runs]

    per_fault = []
    for (t0, t1), spec in zip(truth_intervals, anomaly_specs):
        w = next((t for t in warn_starts if t0 <= t <= t1), None)
        c = next((t for t in crit_starts if t0 <= t <= t1), None)
        # attribution at first warning sample
        attrib = None
        if w is not None:
            j = int(np.argmin(np.abs(obs_t - w)))
            attrib = obs["attribution"].iloc[j]
        per_fault.append({
            "label": spec.label,
            "onset_h": round(t0 / 3600, 2),
            "end_h": round(t1 / 3600, 2),
            "warning_detected": w is not None,
            "warning_latency_min": round((w - t0) / 60, 1) if w is not None else None,
            "critical_detected": c is not None,
            "critical_latency_min": round((c - t0) / 60, 1) if c is not None else None,
            "attribution": attrib,
            "attribution_correct": (attrib == spec.affects) if attrib else None,
            "ground_truth_channel": spec.affects,
        })

    # false-positive warnings: warnings starting OUTSIDE any truth interval
    fp = sum(1 for t in warn_starts
             if not any(t0 <= t <= t1 for (t0, t1) in truth_intervals))

    return {
        "n_anomalies": len(truth_intervals),
        "n_warning_alerts": len(warn_starts),
        "n_critical_alerts": len(crit_starts),
        "false_positive_warnings": fp,
        "per_fault": per_fault,
    }


# ----------------------------------------------------------------------
# End-to-end convenience
# ----------------------------------------------------------------------
def run_monitoring(substrate_with_anomalies: pd.DataFrame, cfg: MonitorConfig,
                   emission_factor_kg_per_kwh: float, seed: int = 7) -> pd.DataFrame:
    obs = sample_and_noise(substrate_with_anomalies, cfg, emission_factor_kg_per_kwh, seed)
    obs = detect(obs, cfg)
    obs = attribute(obs, cfg)
    return obs


if __name__ == "__main__":
    import json
    from .energy_substrate import Config as EnergyConfig, simulate_work_center
    from .carbon_layer import CarbonConfig
    from .anomaly_model import AnomalyConfig, compressed_air_leak, inject_anomalies

    e_cfg = EnergyConfig()
    c_cfg = CarbonConfig()
    m_cfg = MonitorConfig()

    substrate = simulate_work_center(e_cfg)
    leak = compressed_air_leak(onset_hour=10.0, duration_min=240.0, magnitude_kw=2.0)
    substrate_anom = inject_anomalies(substrate, AnomalyConfig(anomalies=[leak]))

    obs = run_monitoring(substrate_anom, m_cfg, c_cfg.static_emission_factor_kg_per_kwh)
    ev = evaluate(obs, substrate_anom, [leak])

    print("=== Monitoring layer (Module 4) ===")
    print(json.dumps({"config": m_cfg.__dict__, "evaluation": ev}, indent=2, default=str))

    obs.to_csv("monitoring_output.csv", index=False)
    print("\nSaved observed signal + alerts -> monitoring_output.csv")
