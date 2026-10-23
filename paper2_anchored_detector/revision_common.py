"""
revision_common.py
==================
Shared harness for the Paper 2 major-revision robustness experiments
(§4.4, §4.7-§4.14, §3.3). Every revision script imports its substrate builder,
detector wrappers, evaluation helpers, and the finite-sample interval estimators
from here, so the operating point and sensor model are identical across all of
them and match the headline runs (run_paper2_main.py / _comparators / _realdata).

Operating point (calibrated in sweep_cusum_roc.py): k = 0.10, h_W = 1.0, h_C = 2.0.

Interval estimators (replacing the degenerate percentile bootstrap, §3.4):
  wilson()  - Wilson score 95% interval for a binomial detection rate
  poisson() - exact (Garwood) Poisson 95% interval for a false-alarm rate
"""
from __future__ import annotations
from functools import lru_cache
import numpy as np
import pandas as pd
from scipy.stats import chi2

from energy_substrate import Config as E, simulate_work_center
from energy_substrate_real import simulate_work_center_real
from carbon_layer import CarbonConfig
from anomaly_model import AnomalyConfig, AnomalySpec, inject_anomalies
from monitoring import MonitorConfig, sample_and_noise, detect as detect_deployed
from monitoring_anchored import AnchoredMonitorConfig, detect_anchored, held_baseline

# ---------------------------------------------------------------- constants
EF = CarbonConfig().static_emission_factor_kg_per_kwh
SENSOR = MonitorConfig(sampling_interval_seconds=60.0, meter_accuracy_pct=1.0,
                       ci_estimation_window_minutes=15.0)
K, HW, HC = 0.10, 1.0, 2.0          # calibrated operating point
BWS = 3600.0                         # 60-min baseline window, in seconds
DUR = 240                            # default fault duration (minutes)
T0 = 10 * 3600.0                     # default fault onset (s)
T1 = T0 + DUR * 60.0

# ---------------------------------------------------------------- substrate
@lru_cache(maxsize=8192)
def _sim(seed: int, real: bool):
    """Cached raw substrate (deterministic in the seed), so repeated conditions on
    the same seed simulate the work centre only once."""
    return (simulate_work_center_real(E(seed=seed)) if real
            else simulate_work_center(E(seed=seed)))

def substrate(seed: int, real: bool = False) -> pd.DataFrame:
    """One day of substrate (synthetic Gutowski or real Brillinger spindle)."""
    return _sim(seed, real).copy()

def clean_day(seed: int, real: bool = False) -> pd.DataFrame:
    sub = substrate(seed, real).copy()
    sub["anomaly_kw"] = 0.0
    sub["anomaly_active"] = False
    sub["anomaly_labels"] = ""
    return sub

def observe(sub: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Apply the (shared) sensor + CI-estimation stage."""
    return sample_and_noise(sub, SENSOR, EF, seed=seed + 1000)

def ramp_spec(magnitude_kw=2.0, ramp_s=3600.0, duration_min=DUR,
              onset_hour=10.0, profile="ramp", **kw) -> AnomalySpec:
    return AnomalySpec(onset_hour=onset_hour, duration_minutes=duration_min,
                       magnitude_kw=magnitude_kw, onset_profile=profile,
                       onset_ramp_seconds=ramp_s, affects="spindle", label="x", **kw)

# ---------------------------------------------------------------- detectors
def D0(obs: pd.DataFrame) -> np.ndarray:
    detect_deployed(obs, MonitorConfig())
    return obs["alert_level"].values

def D2(obs: pd.DataFrame, k=K, hw=HW, hc=HC, anchor_mode="shift_start",
       health_gate_frac=0.15, anchor_period_minutes=120.0,
       two_sided=False, gap_strategy="reset", decay_halflife_min=30.0) -> np.ndarray:
    cfg = AnchoredMonitorConfig(
        detector="anchored_cusum", anchor_mode=anchor_mode,
        anchor_period_minutes=anchor_period_minutes, health_gate_frac=health_gate_frac,
        cusum_k_frac=k, cusum_h_warn=hw, cusum_h_crit=hc,
        cusum_two_sided=two_sided, gap_strategy=gap_strategy,
        decay_halflife_min=decay_halflife_min)
    detect_anchored(obs, cfg)
    return obs["alert_level"].values

# ---------------------------------------------------------------- CUSUM on an arbitrary baseline
def held_B(obs: pd.DataFrame, anchor_mode="shift_start", health_gate_frac=0.15,
           anchor_period_minutes=120.0, post_anchor_baseline_minutes=20.0) -> np.ndarray:
    """The held reference baseline array B(t) for an observed day (same logic the
    detector uses). Exposed so experiments can perturb it (e.g. a contaminated
    anchor, §4.9) and re-run the CUSUM explicitly."""
    cfg = AnchoredMonitorConfig(anchor_mode=anchor_mode, health_gate_frac=health_gate_frac,
                                anchor_period_minutes=anchor_period_minutes,
                                post_anchor_baseline_minutes=post_anchor_baseline_minutes)
    return held_baseline(obs, cfg)

def cusum_alert(ci: np.ndarray, valid: np.ndarray, B: np.ndarray,
                k=K, hw=HW, hc=HC, two_sided=False,
                gap_strategy="reset", decay_halflife_min=30.0) -> np.ndarray:
    """Residual-CUSUM alert levels (0/1/2) for an arbitrary baseline array B.
    Identical formula to monitoring_anchored.detect_anchored, exposed for the
    experiments that supply a perturbed baseline or a perturbed CI channel."""
    dt_min = SENSOR.sampling_interval_seconds / 60.0
    decay = 0.5 ** (dt_min / max(decay_halflife_min, 1e-6))
    out = np.zeros(len(ci), dtype=np.int8)
    s = 0.0; sn = 0.0
    for i in range(len(ci)):
        if valid[i] and np.isfinite(B[i]) and B[i] > 0:
            fe = (ci[i] - B[i]) / B[i]
            s = max(0.0, s + fe - k)
            if two_sided:
                sn = max(0.0, sn - fe - k)
        else:
            if gap_strategy == "hold":
                pass
            elif gap_strategy == "decay":
                s *= decay; sn *= decay
            else:
                s = 0.0; sn = 0.0
        se = max(s, sn) if two_sided else s
        out[i] = 2 if se >= hc else (1 if se >= hw else 0)
    return out

# ---------------------------------------------------------------- evaluation
def starts(al: np.ndarray) -> np.ndarray:
    a = (al >= 1).astype(int)
    s = list(np.where(np.diff(a) == 1)[0] + 1)
    if len(a) and a[0] == 1:
        s = [0] + s
    return np.array(s, dtype=int)

def eval_det(al: np.ndarray, t: np.ndarray, t0=T0, t1=T1):
    """(detected_within_horizon, latency_min) for a fault over [t0, t1]."""
    st = starts(al)
    ts = t[st] if len(st) else np.array([])
    inwin = ts[(ts >= t0) & (ts <= t1)]
    return (True, (inwin[0] - t0) / 60.0) if len(inwin) else (False, np.nan)

def fp_count_exposure(al: np.ndarray, state: np.ndarray):
    """(false-alarm-start count, production-hours of exposure) for a clean day."""
    oph = (state == "PRODUCTION").sum() * SENSOR.sampling_interval_seconds / 3600.0
    return len(starts(al)), oph

def fp_rate(al: np.ndarray, state: np.ndarray) -> float:
    c, oph = fp_count_exposure(al, state)
    return c / max(oph, 1e-6)

# ---------------------------------------------------------------- intervals
def wilson(k: int, n: int, z: float = 1.959963985):
    """Wilson score 95% interval for k successes in n trials. Returns (lo, hi)."""
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    d = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = (z / d) * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, centre - half), min(1.0, centre + half))

def poisson(count: int, exposure: float, alpha: float = 0.05):
    """Exact (Garwood) Poisson 95% interval for a rate = count/exposure.
    Returns (rate, lo, hi) per unit exposure."""
    if exposure <= 0:
        return (np.nan, np.nan, np.nan)
    lo = 0.0 if count == 0 else chi2.ppf(alpha / 2, 2 * count) / 2.0 / exposure
    hi = chi2.ppf(1 - alpha / 2, 2 * (count + 1)) / 2.0 / exposure
    return (count / exposure, lo, hi)
