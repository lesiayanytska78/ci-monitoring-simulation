"""
monitoring_anchored.py
======================
Module 4b of the MES carbon-intensity monitoring simulation.

Purpose
-------
A *proposed* monitoring layer that closes the structural blind spot characterised
in the base study (Module 4): the adaptive-baseline inertia trade-off, whereby a
rolling-reference detector becomes blind to faults that develop slowly relative
to its baseline-adaptation window.

The deployed architecture (Module 4) compares the CI-per-piece signal to a
*rolling-median* baseline. Any fault whose onset timescale is comparable to the
baseline window is tracked by that baseline and never crosses threshold, so
detection collapses as the onset-to-window ratio approaches 1 (the §4.7 sigmoid).

This module replaces the tracking reference with two complementary, literature-
grounded mechanisms:

  (1) EVENT-ANCHORED HELD BASELINE
      Instead of a continuously updating rolling median, the baseline is anchored
      to a discrete MES event at which the work centre is known to be in a defined
      healthy state -- a shift start after planned maintenance, an operator-
      confirmed post-intervention state, or a tool-change event read from the NC
      program. The baseline is estimated over a short window immediately after the
      anchor and HELD CONSTANT until the next anchor. Slow drift between anchors
      then accumulates against a *stationary* reference rather than a tracking one,
      so a ramp-onset fault is detected once its cumulative effect crosses
      threshold, regardless of how slowly it develops.
      (Fixed-reference end of the spectrum whose adaptive-reference end exhibits
      the §4.7 inertia; cf. Woodall & Mahmoud 2005 on chart inertia.)

  (2) RESIDUAL CUSUM
      A one-sided cumulative-sum test is run on the fractional residual
      e_t = (CI_t - B_anchor) / B_anchor, with reference (slack) k and decision
      interval h. CUSUM is provably near-optimal for detecting small persistent
      shifts (Page 1954; Lorden 1971), exactly the regime in which the Shewhart-
      equivalent rule of Module 4 is weakest. It integrates a slow drift and fires
      well before a single-sample threshold on the same drift would.

Detectors implemented (selectable via AnchoredMonitorConfig.detector):
  "anchored_threshold"  held baseline + relative threshold + persistence  (D1)
  "anchored_cusum"      held baseline + residual CUSUM                     (D2)

The sensor model and CI-estimation stage are REUSED unchanged from Module 4
(monitoring.sample_and_noise), so any difference in detection performance is
attributable to the detection logic alone -- a controlled comparison on an
identical observed signal.

Units discipline
----------------
Following the dimensionless ethos of the base study, the CUSUM operates on the
fractional residual (excess as a fraction of the anchored baseline). k and h are
therefore dimensionless and transfer across process scales, exactly like the
relative-units detection floor of §4.1.

Provenance tags
---------------
  [LITERATURE] CUSUM: Page (1954); optimality: Lorden (1971). Event/fixed
               reference vs inertia: Woodall & Mahmoud (2005).
  [ASSUMPTION] anchor cadence, post-anchor baseline window, k and h operating
               point -- all SWEPT in the detector-comparison harness.
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd

# Reuse the Module 4 sensor + CI-estimation stage and the shared evaluation code,
# so the comparison is on an identical observed signal.
from .monitoring import sample_and_noise, attribute, evaluate, _runs  # noqa: F401


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
@dataclass
class AnchoredMonitorConfig:
    # --- Sensor model (identical defaults to Module 4 for a fair comparison) ---
    sampling_interval_seconds: float = 60.0
    meter_accuracy_pct: float = 1.0
    ci_estimation_window_minutes: float = 15.0   # passed through to sample_and_noise

    # --- Anchor model ---
    # "shift_start"    : single anchor at the first PRODUCTION sample (healthy
    #                    state established at shift start / after planned maint.).
    # "periodic"       : re-anchor every anchor_period_minutes, UNCONDITIONALLY
    #                    (models naive tool-change-cadence re-baselining; an anchor
    #                    landing mid-fault re-absorbs the fault -- the honest
    #                    failure mode shown in step (a)).
    # "periodic_gated" : re-anchor every anchor_period_minutes, but only ACCEPT the
    #                    new baseline if the post-anchor signal is not elevated
    #                    relative to the standing baseline by more than
    #                    health_gate_frac (models operator-/state-confirmed health
    #                    gating; refuses to re-baseline onto a suspected fault).
    anchor_mode: str = "shift_start"
    anchor_period_minutes: float = 120.0          # used for periodic / periodic_gated
    post_anchor_baseline_minutes: float = 20.0    # window after anchor to set B
    health_gate_frac: float = 0.15                # reject a re-anchor if candidate
                                                  # baseline exceeds standing by this

    # --- Detector selection ---
    detector: str = "anchored_cusum"              # "anchored_threshold" | "anchored_cusum"

    # anchored_threshold parameters
    rel_threshold_pct: float = 25.0
    warning_persistence_samples: int = 3
    critical_persistence_samples: int = 9

    # anchored_cusum parameters (dimensionless, fraction-of-baseline units)
    cusum_k_frac: float = 0.10     # slack: ignore fractional excess below this
    cusum_h_warn: float = 0.40     # decision interval for a WARNING
    cusum_h_crit: float = 1.20     # decision interval for a CRITICAL


# ----------------------------------------------------------------------
# Anchor schedule + held baseline
# ----------------------------------------------------------------------
def _anchor_indices(obs: pd.DataFrame, cfg: AnchoredMonitorConfig) -> list:
    """Sample indices at which a fresh baseline anchor is established."""
    state = obs["state"].values
    t = obs["t_s"].values
    prod_idx = np.where(state == "PRODUCTION")[0]
    if len(prod_idx) == 0:
        return []

    if cfg.anchor_mode == "shift_start":
        return [int(prod_idx[0])]

    if cfg.anchor_mode in ("periodic", "periodic_gated"):
        period_s = cfg.anchor_period_minutes * 60.0
        anchors = []
        next_anchor_t = t[prod_idx[0]]
        for i in prod_idx:
            if t[i] >= next_anchor_t:
                anchors.append(int(i))
                next_anchor_t = t[i] + period_s
        return anchors

    raise ValueError(f"Unknown anchor_mode: {cfg.anchor_mode}")


def held_baseline(obs: pd.DataFrame, cfg: AnchoredMonitorConfig) -> np.ndarray:
    """Per-sample held baseline B(t): the median CI over the post-anchor window of
    the most recent ACCEPTED anchor, held constant until the next accepted anchor.
    NaN before the first anchor (machine not yet baselined).

    Anchors are processed sequentially against a 'standing' baseline. In
    "periodic_gated" mode a candidate anchor is REJECTED (the standing baseline is
    kept) when its post-anchor CI is elevated above the standing baseline by more
    than health_gate_frac -- i.e. the work centre does not look healthy, so we do
    not re-baseline onto a suspected fault. The first anchor is always accepted
    (no prior reference). "periodic" mode accepts every anchor unconditionally."""
    n = len(obs)
    ci = obs["ci_per_piece_kg_obs"].values
    state = obs["state"].values
    anchors = _anchor_indices(obs, cfg)
    B = np.full(n, np.nan)
    if not anchors:
        return B

    post_n = max(1, int(round(cfg.post_anchor_baseline_minutes * 60.0
                              / cfg.sampling_interval_seconds)))
    standing = np.nan
    for a_i, anchor in enumerate(anchors):
        nxt = anchors[a_i + 1] if a_i + 1 < len(anchors) else n
        # candidate baseline over production samples in the post-anchor window
        win_end = min(anchor + post_n, n)
        seg_ci = ci[anchor:win_end]
        seg_st = state[anchor:win_end]
        vals = seg_ci[(seg_st == "PRODUCTION") & np.isfinite(seg_ci)]
        cand = float(np.median(vals)) if len(vals) else np.nan

        accept = True
        if (cfg.anchor_mode == "periodic_gated"
                and np.isfinite(standing) and np.isfinite(cand)):
            # reject if the candidate looks elevated -> suspected ongoing fault
            if cand > standing * (1.0 + cfg.health_gate_frac):
                accept = False
        if accept and np.isfinite(cand):
            standing = cand
        B[anchor:nxt] = standing
    return B


# ----------------------------------------------------------------------
# Detection
# ----------------------------------------------------------------------
def _tiered_from_streak(over: np.ndarray, w: int, c: int) -> np.ndarray:
    streak = np.zeros(len(over), dtype=int)
    s = 0
    for i, o in enumerate(over):
        s = s + 1 if o else 0
        streak[i] = s
    lvl = np.zeros(len(over), dtype=int)
    lvl[streak >= w] = 1
    lvl[streak >= c] = 2
    return lvl


def detect_anchored(obs: pd.DataFrame, cfg: AnchoredMonitorConfig) -> pd.DataFrame:
    """Add held baseline, detector internals, and alert_level (0/1/2)."""
    ci = obs["ci_per_piece_kg_obs"].values
    state = obs["state"].values
    valid = np.isfinite(ci) & (state == "PRODUCTION")
    B = held_baseline(obs, cfg)
    obs["baseline_kg_per_piece"] = B

    if cfg.detector == "anchored_threshold":
        thr = B * (1.0 + cfg.rel_threshold_pct / 100.0)
        over = valid & np.isfinite(thr) & (ci > thr)
        obs["threshold_kg_per_piece"] = thr
        obs["over_threshold"] = over
        obs["cusum"] = np.nan
        obs["alert_level"] = _tiered_from_streak(
            over, cfg.warning_persistence_samples, cfg.critical_persistence_samples)

    elif cfg.detector == "anchored_cusum":
        # fractional residual against the held baseline
        with np.errstate(divide="ignore", invalid="ignore"):
            frac_excess = np.where(valid & np.isfinite(B) & (B > 0),
                                   (ci - B) / B, 0.0)
        S = np.zeros(len(ci))
        s = 0.0
        for i in range(len(ci)):
            if valid[i] and np.isfinite(B[i]) and B[i] > 0:
                s = max(0.0, s + frac_excess[i] - cfg.cusum_k_frac)
            else:
                s = 0.0          # reset accumulator outside production
            S[i] = s
        lvl = np.zeros(len(ci), dtype=int)
        lvl[S >= cfg.cusum_h_warn] = 1
        lvl[S >= cfg.cusum_h_crit] = 2
        obs["threshold_kg_per_piece"] = B * (1.0 + cfg.cusum_k_frac)  # for plotting
        obs["over_threshold"] = (lvl >= 1)
        obs["cusum"] = S
        obs["alert_level"] = lvl

    else:
        raise ValueError(f"Unknown detector: {cfg.detector}")

    return obs


# ----------------------------------------------------------------------
# End-to-end convenience (mirrors monitoring.run_monitoring signature)
# ----------------------------------------------------------------------
def run_monitoring_anchored(substrate_with_anomalies: pd.DataFrame,
                            cfg: AnchoredMonitorConfig,
                            emission_factor_kg_per_kwh: float,
                            seed: int = 7) -> pd.DataFrame:
    # reuse Module 4's sensor + CI-estimation stage unchanged
    from .monitoring import MonitorConfig
    m_cfg = MonitorConfig(
        sampling_interval_seconds=cfg.sampling_interval_seconds,
        meter_accuracy_pct=cfg.meter_accuracy_pct,
        ci_estimation_window_minutes=cfg.ci_estimation_window_minutes,
    )
    obs = sample_and_noise(substrate_with_anomalies, m_cfg,
                           emission_factor_kg_per_kwh, seed)
    obs = detect_anchored(obs, cfg)
    # attribution uses the same per-channel rolling logic as Module 4
    obs = attribute(obs, m_cfg)
    return obs


if __name__ == "__main__":
    import json
    from .energy_substrate import Config as EnergyConfig, simulate_work_center
    from .carbon_layer import CarbonConfig
    from .anomaly_model import AnomalyConfig, AnomalySpec, inject_anomalies

    EF = CarbonConfig().static_emission_factor_kg_per_kwh
    substrate = simulate_work_center(EnergyConfig(seed=42))
    # a SLOW-onset fault in the inertia regime: 2 kW, 1 h ramp (ratio ~1.0)
    slow = AnomalySpec(onset_hour=10.0, duration_minutes=240, magnitude_kw=2.0,
                       onset_profile="ramp", onset_ramp_seconds=3600.0,
                       affects="spindle", label="slow_ramp_2kW")
    sub = inject_anomalies(substrate, AnomalyConfig([slow]))

    for det in ("anchored_threshold", "anchored_cusum"):
        cfg = AnchoredMonitorConfig(detector=det)
        obs = run_monitoring_anchored(sub, cfg, EF, seed=1042)
        ev = evaluate(obs, sub, [slow])
        print(f"=== {det} ===")
        print(json.dumps(ev["per_fault"][0], indent=2, default=str))
