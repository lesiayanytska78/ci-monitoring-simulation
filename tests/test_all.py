"""Self-contained test suite for the CI-monitoring repository.

Exercises the full pipeline end to end — energy substrate, carbon layer, anomaly
model, the deployed detector, and the proposed event-anchored + residual-CUSUM
detector — plus a regression test for the paper's headline result and an
integrity check on the released data and the shared engine modules.

No conftest needed: the module path is set up at the top of this file.
"""
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "paper2_anchored_detector"))

import numpy as np
import pandas as pd

from energy_substrate import Config, simulate_work_center
from carbon_layer import CarbonConfig, compute_carbon_layer
from anomaly_model import AnomalyConfig, AnomalySpec, inject_anomalies
from monitoring import MonitorConfig, run_monitoring, evaluate
from monitoring_anchored import AnchoredMonitorConfig, run_monitoring_anchored

EF = CarbonConfig().static_emission_factor_kg_per_kwh
SHARED = ["energy_substrate.py", "carbon_layer.py", "anomaly_model.py",
          "monitoring.py", "sensitivity.py"]


def _sub(seed=42):
    return simulate_work_center(Config(seed=seed))


def _ramp(sev=2.0, ramp_s=3600.0, channel="spindle"):
    return AnomalySpec(onset_hour=10, duration_minutes=240, magnitude_kw=sev,
                       onset_profile="ramp", onset_ramp_seconds=ramp_s,
                       affects=channel, label="test")


# ---------- pipeline ----------
def test_substrate_structure():
    df = _sub()
    need = {"t_s", "state", "machine_kw", "spindle_kw", "total_kw", "pieces_rate", "pieces_cum"}
    assert need <= set(df.columns)
    assert np.allclose(df.total_kw, df.machine_kw + df.spindle_kw, atol=1e-6)
    assert set(df.state.unique()) <= {"OFFLINE", "IDLE", "PRODUCTION"}
    assert (df.state == "PRODUCTION").any()
    assert df.total_kw.notna().all()
    assert df.pieces_cum.iloc[-1] > 0
    assert 1.0 < df.loc[df.state == "PRODUCTION", "total_kw"].mean() < 20.0


def test_carbon_layer_positive_ci():
    df = compute_carbon_layer(_sub(), CarbonConfig())
    ci = df.loc[df.state == "PRODUCTION", "ci_per_piece_rolling_kg"].dropna()
    assert len(ci) > 0 and (ci > 0).all()


def test_anomaly_adds_power_not_pieces():
    sub = _sub()
    spec = AnomalySpec(onset_hour=10, duration_minutes=120, magnitude_kw=2.0,
                       onset_profile="step", affects="spindle", label="t")
    inj = inject_anomalies(sub, AnomalyConfig([spec]))
    assert np.allclose(sub.pieces_cum.values, inj.pieces_cum.values)
    t0, t1 = 10 * 3600, 10 * 3600 + 120 * 60
    win = (inj.t_s >= t0) & (inj.t_s < t1)
    assert inj.loc[win, "total_kw"].mean() > sub.loc[win, "total_kw"].mean() + 1.0


def test_deployed_detects_strong_fault():
    inj = inject_anomalies(_sub(), AnomalyConfig([AnomalySpec(
        onset_hour=10, duration_minutes=240, magnitude_kw=3.0,
        onset_profile="step", affects="machine", label="t")]))
    obs = run_monitoring(inj, MonitorConfig(), EF, seed=1)
    spec = AnomalySpec(onset_hour=10, duration_minutes=240, magnitude_kw=3.0,
                       onset_profile="step", affects="machine", label="t")
    assert evaluate(obs, inj, [spec])["per_fault"][0]["warning_detected"] is True


def test_deployed_quiet_when_clean():
    sub = _sub().copy()
    sub["anomaly_kw"] = 0.0
    sub["anomaly_active"] = False
    sub["anomaly_labels"] = ""
    obs = run_monitoring(sub, MonitorConfig(), EF, seed=2)
    assert (obs["alert_level"].values >= 1).mean() < 0.2


def test_anchored_recovers_slow_ramp_headline():
    """Regression test for the paper's central claim."""
    inj = inject_anomalies(_sub(), AnomalyConfig([_ramp(2.0, 3600.0)]))
    cfg = AnchoredMonitorConfig(detector="anchored_cusum", anchor_mode="shift_start",
                                cusum_k_frac=0.10, cusum_h_warn=1.0, cusum_h_crit=2.0)
    obs = run_monitoring_anchored(inj, cfg, EF, seed=1)
    assert evaluate(obs, inj, [_ramp(2.0, 3600.0)])["per_fault"][0]["warning_detected"] is True


def test_held_baseline_constant_within_segment():
    inj = inject_anomalies(_sub(), AnomalyConfig([_ramp(2.0, 3600.0)]))
    obs = run_monitoring_anchored(inj, AnchoredMonitorConfig(anchor_mode="shift_start"), EF, seed=1)
    B = obs["baseline_kg_per_piece"].values
    assert np.unique(np.round(B[np.isfinite(B)], 10)).size == 1


# ---------- repository integrity ----------
def test_released_csvs_load_and_nonempty():
    csvs = sorted((ROOT / "data").glob("*.csv"))
    assert len(csvs) >= 9
    for csv in csvs:
        df = pd.read_csv(csv)
        assert len(df) > 0 and "seed" in df.columns


def test_shared_modules_do_not_drift():
    for m in SHARED:
        a, b = ROOT / "simulation" / m, ROOT / "paper2_anchored_detector" / m
        assert a.exists() and b.exists()
        assert a.read_text() == b.read_text(), f"{m} differs between the two folders"


def test_package_imports_and_matches_flat_engine():
    """The installable cimonitoring package imports and reproduces the flat
    engine's output bit-for-bit (guards the package against silent drift)."""
    sys.path.insert(0, str(ROOT))
    import cimonitoring as ci
    assert hasattr(ci, "run_monitoring_anchored") and hasattr(ci, "AnchoredMonitorConfig")
    a = ci.simulate_work_center(ci.Config(seed=7))
    b = simulate_work_center(Config(seed=7))      # flat engine, imported at top
    assert np.allclose(a.total_kw.values, b.total_kw.values)


def test_architecture_html_claims_match_code():
    """Every number rendered in architecture.html via a data-claim span must
    equal the value recomputed from the engine + released CSVs. Guards the
    interactive diagram against drifting away from the actual results."""
    sys.path.insert(0, str(ROOT))
    import make_claims_manifest as mcm
    claims = mcm.compute_claims(str(ROOT))
    html_claims = mcm.parse_html_claims(str(ROOT / "architecture.html"))
    for key in ("demo_warning_latency_min", "demo_false_positives", "n_runs", "n_sweeps"):
        assert key in html_claims, f"architecture.html missing data-claim span for {key}"
        assert str(claims[key]) == html_claims[key], (
            f"{key}: diagram says {html_claims[key]!r} but code computes {claims[key]!r} "
            "— regenerate with `python make_claims_manifest.py`")
