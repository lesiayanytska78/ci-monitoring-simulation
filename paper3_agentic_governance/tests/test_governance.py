"""Pin the epistemic contract against the REAL archived surface (audited)."""
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Lesia Yanytska
import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from contract.governance import (  # noqa: E402
    ACTIONS, Autonomy, EpistemicContract, Sigma, autonomy_grant, sigma_from_pdet,
)

S2KW = 0.5882


@pytest.fixture(scope="module")
def contract():
    return EpistemicContract()


@pytest.fixture(scope="module")
def registry():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "contract", "fault_registry.yaml")
    with open(path) as f:
        reg = yaml.safe_load(f)
    return {a["name"]: a for a in reg["archetypes"]}


@pytest.mark.parametrize("rho,expected", [
    (0.167, Sigma.RELIABLE), (0.40, Sigma.TRANSITION),
    (0.60, Sigma.DEGRADED), (1.00, Sigma.BLIND),
])
def test_sensing_tier_along_sigmoid(contract, rho, expected):
    sigma, _, _ = contract.sensing_tier(S2KW, rho, "D0")
    assert sigma == expected


def test_conservatism_shifts_the_knee(contract):
    sg, plo, _ = contract.sensing_tier(S2KW, 0.40, "D0")
    assert sg == Sigma.TRANSITION and plo < 0.80


def test_sigma_cutpoints_are_derived(contract):
    assert contract.cuts_source.startswith("DERIVED")
    assert "FA-equivalence" in contract.cuts_source


def test_theta1_fa_equivalence_floor():
    from contract.governance import derive_sigma_cutpoints
    import math
    c = derive_sigma_cutpoints(fa_rate=0.05, horizon_h=4.0)
    assert c["c1"] == pytest.approx(1 - math.exp(-0.2), abs=1e-4)
    assert c["c2"] == 0.50 and c["c3"] == 0.80
    assert derive_sigma_cutpoints(fa_rate=0.10, horizon_h=4.0)["c1"] > c["c1"]


def test_sigma_cutpoints_boundaries():
    assert sigma_from_pdet(0.80) == Sigma.RELIABLE
    assert sigma_from_pdet(0.50) == Sigma.TRANSITION
    assert sigma_from_pdet(0.4999) == Sigma.DEGRADED
    assert sigma_from_pdet(0.19) == Sigma.DEGRADED
    assert sigma_from_pdet(0.17) == Sigma.BLIND


def test_autonomy_is_min_of_sigma_alpha():
    assert autonomy_grant(Sigma.RELIABLE, ACTIONS["defer_job"]) == Autonomy.ACT_LOG
    assert autonomy_grant(Sigma.TRANSITION, ACTIONS["defer_job"]) == Autonomy.ACT_NOTIFY
    assert autonomy_grant(Sigma.BLIND, ACTIONS["defer_job"]) == Autonomy.ESCALATE
    assert autonomy_grant(Sigma.RELIABLE, ACTIONS["dispatch_maintenance"]) == Autonomy.PROPOSE_WAIT


def test_l2_action_capped_regardless_of_sensing():
    assert autonomy_grant(Sigma.RELIABLE, ACTIONS["throttle_setpoint"]) == Autonomy.ACT_NOTIFY
    assert ACTIONS["throttle_setpoint"].requires_control_layer_ack is True


def test_shutdown_never_autonomous():
    for sig in (Sigma.BLIND, Sigma.DEGRADED, Sigma.TRANSITION, Sigma.RELIABLE):
        assert autonomy_grant(sig, ACTIONS["shutdown"]) == Autonomy.ESCALATE


@pytest.mark.parametrize("name,d0,d2,d2_blindkind", [
    ("compressed_air_leak", Sigma.TRANSITION, Sigma.RELIABLE, None),
    ("coolant_pump_fault",  Sigma.DEGRADED,   Sigma.RELIABLE, None),
    ("machine_left_on",     Sigma.BLIND,      Sigma.BLIND,    "measurement_demand"),
    ("tool_wear",           Sigma.BLIND,      Sigma.BLIND,    "measurement_demand"),
])
def test_archetype_grants_default(contract, registry, name, d0, d2, d2_blindkind):
    g0 = contract.standing_grant(registry[name], "defer_job", "D0")
    g2 = contract.standing_grant(registry[name], "defer_job", "D2")
    assert g0.sigma == d0
    assert g2.sigma == d2
    assert g2.situation.get("blind_kind") == d2_blindkind


def test_d2_recovers_only_measured_archetypes(contract, registry):
    c0 = contract.standing_grant(registry["coolant_pump_fault"], "defer_job", "D0")
    c2 = contract.standing_grant(registry["coolant_pump_fault"], "defer_job", "D2")
    assert c0.escalated and c2.autonomy == Autonomy.ACT_LOG


def test_measurement_demand_below_floor(contract, registry):
    g = contract.standing_grant(registry["tool_wear"], "defer_job", "D2")
    assert g.escalated and g.situation["blind_kind"] == "measurement_demand"
    assert "measurement_order" in g.payload["evidence"]


def test_worstcase_corner_is_more_conservative(contract, registry):
    dflt = contract.standing_grant(registry["compressed_air_leak"], "defer_job", "D0", corner="default")
    worst = contract.standing_grant(registry["compressed_air_leak"], "defer_job", "D0", corner="worstcase")
    assert int(worst.sigma) <= int(dflt.sigma)
    assert dflt.sigma == Sigma.TRANSITION and worst.sigma == Sigma.DEGRADED


def test_low_attribution_caps_sigma(contract):
    hi, _, _ = contract.sensing_tier(S2KW, 0.167, "D0", attribution_conf=1.0)
    lo, _, _ = contract.sensing_tier(S2KW, 0.167, "D0", attribution_conf=0.2)
    assert hi == Sigma.RELIABLE and lo == Sigma.DEGRADED


def test_escalation_payload_is_auditable(contract):
    d = contract.gate_action("defer_job", s_hat=0.235, rho_hat=1.0, detector="D0")
    assert d.escalated
    for k in ("gate_reason", "p_det_lo95", "provenance", "situation", "proposed_action"):
        assert k in d.payload
