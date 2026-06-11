"""cimonitoring — calibrated simulation and detectors for MES-embedded
carbon-intensity monitoring of energy anomalies in machining-style processes.

This is the installable package form of the simulation framework (Modules 1-5)
and the proposed event-anchored + residual-CUSUM detector. After
``pip install .`` you can build the pipeline directly:

    >>> import cimonitoring as ci
    >>> sub = ci.simulate_work_center(ci.Config(seed=1))
    >>> sub = ci.inject_anomalies(sub, ci.AnomalyConfig([
    ...     ci.AnomalySpec(onset_hour=10, duration_minutes=240, magnitude_kw=2.0,
    ...                    onset_profile="ramp", onset_ramp_seconds=3600,
    ...                    affects="spindle", label="slow ramp")]))
    >>> obs = ci.run_monitoring_anchored(
    ...     sub, ci.AnchoredMonitorConfig(detector="anchored_cusum"),
    ...     ci.CarbonConfig().static_emission_factor_kg_per_kwh)
"""
from .energy_substrate import Config, simulate_work_center
from .carbon_layer import CarbonConfig, compute_carbon_layer, grid_emission_factor
from .anomaly_model import (
    AnomalyConfig, AnomalySpec, inject_anomalies,
    compressed_air_leak, machine_left_on, tool_wear, coolant_pump_fault,
)
from .monitoring import (
    MonitorConfig, run_monitoring, sample_and_noise, detect, attribute, evaluate,
)
from .monitoring_anchored import (
    AnchoredMonitorConfig, run_monitoring_anchored, detect_anchored, held_baseline,
)

__version__ = "2.2.1"

__all__ = [
    "Config", "simulate_work_center",
    "CarbonConfig", "compute_carbon_layer", "grid_emission_factor",
    "AnomalyConfig", "AnomalySpec", "inject_anomalies",
    "compressed_air_leak", "machine_left_on", "tool_wear", "coolant_pump_fault",
    "MonitorConfig", "run_monitoring", "sample_and_noise", "detect", "attribute", "evaluate",
    "AnchoredMonitorConfig", "run_monitoring_anchored", "detect_anchored", "held_baseline",
]
