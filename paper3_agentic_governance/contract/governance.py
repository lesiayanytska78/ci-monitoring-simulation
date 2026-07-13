"""contract/governance.py — the epistemic contract (Paper 3 §4 / §B.1-B.6).

Maps the characterized detectability surface onto agent autonomy:

    sigma (sensing tier)  <- P_det lower bound            (B.2)
    alpha (action tier)   <- reversibility / ISA-95 level (B.3)
    A = min(sigma, alpha)                                 (B.4)
    L2 actions capped at A<=2 (MES proposes, control layer disposes)

Two gating modes (B.5):
    ex-ante  : standing grants from the fault registry (catches the naive
               agent's confident inaction on a standing-blind class)
    ex-post  : alarm response gated by estimated (s_hat, rho_hat), with
               attribution confidence capping sigma

Everything here is pure and deterministic; it is testable before any agent
exists.
"""
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Lesia Yanytska
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, Optional

from .surface import DetectabilitySurface, default_surface


# --------------------------------------------------------------------------- #
# Sensing tier sigma (B.2)
# --------------------------------------------------------------------------- #
class Sigma(IntEnum):
    BLIND = 0        # P_det < c1               characterized-blind -> escalate
    DEGRADED = 1     # c1 <= P_det < c2
    TRANSITION = 2   # c2 <= P_det < c3
    RELIABLE = 3     # P_det >= c3              characterized-reliable


# sigma cut-points.  c3 = 0.80 is INHERITED from Papers 1-2's reliable-detection
# convention (defended there at <=0.05 false alarms / production-hour) and is
# fixed.  c2 (0.50) and c1 (0.20) are DERIVED from the ROC false-alarm operating
# points rather than left as free constants (Phase-0 decision).  Until the ROC
# arrays are dropped in, derive_sigma_cutpoints() returns the spec defaults and
# is the single place to wire the real derivation.
# Three thresholds, three DISTINCT justifications, zero arbitrary constants (B.2):
#   c3 = 0.80  INHERITED (Papers 1-2 reliable-detection convention, <=0.05 FA/h).
#   c2 = 0.50  PREPONDERANCE: act-with-veto only where detecting the premise fault
#              is more likely than not; coincides with the measured sigmoid midpoint.
#   c1 = 1 - exp(-r_FA * T_h)  FA-EQUIVALENCE floor: below this P_det the TP yield
#              over the response horizon ~ the characterized FA yield -> "blind".
#              Computed, not chosen; rises for a noisier detector.
SIGMA_C3_RELIABLE = 0.80
SIGMA_C2_PREPONDERANCE = 0.50
FA_OPERATING_RATE_PER_H = 0.05    # r_FA: Sweep-3 defended operating point
HUMAN_RESPONSE_HORIZON_H = 4.0    # T_h: PoC human-response horizon (hours)


def derive_sigma_cutpoints(fa_rate: float = FA_OPERATING_RATE_PER_H,
                           horizon_h: float = HUMAN_RESPONSE_HORIZON_H) -> Dict[str, float]:
    """theta_1 = 1 - exp(-r_FA * T_h); theta_2 = 0.50; theta_3 = 0.80."""
    theta_1 = 1.0 - math.exp(-fa_rate * horizon_h)
    return {"c1": round(theta_1, 4), "c2": SIGMA_C2_PREPONDERANCE, "c3": SIGMA_C3_RELIABLE}


def sigma_cutpoints_provenance(fa_rate: float = FA_OPERATING_RATE_PER_H,
                               horizon_h: float = HUMAN_RESPONSE_HORIZON_H) -> str:
    c = derive_sigma_cutpoints(fa_rate, horizon_h)
    return (f"DERIVED: c3={c['c3']} (inherited, Papers 1-2); "
            f"c2={c['c2']} (preponderance = measured sigmoid midpoint); "
            f"c1={c['c1']} = 1-exp(-{fa_rate}*{horizon_h}) (FA-equivalence floor)")


def sigma_from_pdet(p_det_lo95: float, cuts: Optional[Dict[str, float]] = None) -> Sigma:
    c = cuts or derive_sigma_cutpoints()
    if p_det_lo95 >= c["c3"]:
        return Sigma.RELIABLE
    if p_det_lo95 >= c["c2"]:
        return Sigma.TRANSITION
    if p_det_lo95 >= c["c1"]:
        return Sigma.DEGRADED
    return Sigma.BLIND


# --------------------------------------------------------------------------- #
# Action tier alpha (B.3) — tagged to the ISA-95 / IEC 62264 functional layer
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Action:
    name: str
    alpha: int                       # 0..3 reversibility/impact tier
    isa95_level: int                 # 3 = native MES (MOM); 2 = control layer
    exposing_module: str             # which MES/plant module exposes it
    requires_control_layer_ack: bool = False  # L2 handoff: MES proposes only

    def __post_init__(self):
        assert 0 <= self.alpha <= 3
        assert self.isa95_level in (2, 3)


# Confirmed action space (Paper 3 §B.3, ISA-95-validated).  The only L2 entries
# are throttle/setpoint: a pure MES cannot command them, it can only request
# them of the control layer, so they carry requires_control_layer_ack=True and
# are capped at A<=2 by autonomy_grant() regardless of sigma.
ACTIONS: Dict[str, Action] = {
    "defer_job":          Action("defer_job", 3, 3, "detailed scheduling & dispatching"),
    "shift_load_window":  Action("shift_load_window", 2, 3, "scheduling / APS"),
    "throttle_setpoint":  Action("throttle_setpoint", 2, 2, "EMS / APC (control-layer request)",
                                 requires_control_layer_ack=True),
    "reschedule_cross_shift": Action("reschedule_cross_shift", 1, 3, "scheduling / dispatching"),
    "dispatch_maintenance":   Action("dispatch_maintenance", 1, 3, "maintenance mgmt (CMMS/EAM)"),
    "quarantine_wip":         Action("quarantine_wip", 1, 3, "quality management (hold)"),
    "shutdown":               Action("shutdown", 0, 2, "SIS / interlocks",
                                     requires_control_layer_ack=True),
}


# --------------------------------------------------------------------------- #
# Autonomy grant A = min(sigma, alpha), with the L2 cap (B.4)
# --------------------------------------------------------------------------- #
class Autonomy(IntEnum):
    ESCALATE = 0      # propose nothing autonomously; human operates
    PROPOSE_WAIT = 1  # propose + wait for approval
    ACT_NOTIFY = 2    # act + notify (human veto window)
    ACT_LOG = 3       # autonomous act + log


def autonomy_grant(sigma: Sigma, action: Action) -> Autonomy:
    a = min(int(sigma), action.alpha)
    # L2 cap: an action the MES can only *request* of the control layer can
    # never be fully autonomous, no matter how reliable the sensing.
    if action.isa95_level == 2:
        a = min(a, int(Autonomy.ACT_NOTIFY))
    return Autonomy(a)


AUTONOMY_LABEL = {
    Autonomy.ACT_LOG: "A=3 autonomous act + log",
    Autonomy.ACT_NOTIFY: "A=2 act + notify (veto window)",
    Autonomy.PROPOSE_WAIT: "A=1 propose + wait (approval required)",
    Autonomy.ESCALATE: "A=0 mandatory escalation",
}


# --------------------------------------------------------------------------- #
# The contract object
# --------------------------------------------------------------------------- #
@dataclass
class GovernanceDecision:
    action: Action
    detector: str
    sigma: Sigma
    autonomy: Autonomy
    p_det_lo95: float
    reason: str
    situation: Dict[str, float]
    escalated: bool
    payload: Optional[Dict] = None


class EpistemicContract:
    """Runtime enforcement of the measurement-bounded autonomy principle."""

    def __init__(self, surface: Optional[DetectabilitySurface] = None,
                 cuts: Optional[Dict[str, float]] = None):
        self.surface = surface or default_surface()
        self.cuts = cuts or derive_sigma_cutpoints()
        # provenance of the sigma cut-points (challenge #4 resolved).
        self.cuts_source = "explicit" if cuts else sigma_cutpoints_provenance()

    # ---- sensing tier for a situation -------------------------------------
    def sensing_tier(self, s: float, rho: float, detector: str,
                     attribution_conf: float = 1.0) -> "tuple[Sigma, float, str]":
        d = self.surface.query(s, rho, detector)
        sigma = sigma_from_pdet(d.p_det_lo95, self.cuts)
        # Attribution reliability conditions sigma (B.5 ex-post): if we cannot
        # confidently say WHICH fault, cap the sensing tier at DEGRADED.
        if attribution_conf < 0.5 and sigma > Sigma.DEGRADED:
            sigma = Sigma.DEGRADED
        return sigma, d.p_det_lo95, d.provenance

    # ---- ex-post: alarm response ------------------------------------------
    def gate_action(self, action_name: str, s_hat: float, rho_hat: float,
                    detector: str, attribution_conf: float = 1.0,
                    evidence: Optional[Dict] = None,
                    deferral_cost: Optional[Dict] = None) -> GovernanceDecision:
        action = ACTIONS[action_name]
        sigma, plo, prov = self.sensing_tier(s_hat, rho_hat, detector, attribution_conf)
        A = autonomy_grant(sigma, action)
        reason = self._reason(sigma, action, A)
        escalated = A <= Autonomy.PROPOSE_WAIT
        situation = {"s": s_hat, "rho": rho_hat, "attribution_conf": attribution_conf}
        payload = None
        if escalated:
            payload = self._escalation_payload(action, detector, sigma, plo, prov,
                                               reason, situation, evidence, deferral_cost)
        return GovernanceDecision(action, detector, sigma, A, plo, reason,
                                  situation, escalated, payload)

    # ---- ex-ante: standing grant from the fault registry ------------------
    def standing_grant(self, fault_class: Dict, action_name: str,
                       detector: str, corner: str = "default") -> GovernanceDecision:
        """Standing autonomy grant for a fault class (B.5).

        corner: 'default' (nominal severity) or 'worstcase' (min of the class's
        severity range; onset held at nominal). A BLIND result is either
        'characterized_blind' (in-envelope, P_det too low) or 'measurement_demand'
        (below the detector's measured floor -> refuse the unmeasured grant and
        issue a measurement order)."""
        if corner == "worstcase":
            s = min(fault_class.get("severity_frac_range",
                                    [fault_class["severity_frac_nominal"]]))
        else:
            s = fault_class["severity_frac_nominal"]
        rho = fault_class["onset_ratio_nominal"]
        d = self.surface.query(s, rho, detector)
        sigma = sigma_from_pdet(d.p_det_lo95, self.cuts)
        action = ACTIONS[action_name]
        A = autonomy_grant(sigma, action)
        blind_kind = None
        if sigma == Sigma.BLIND:
            blind_kind = "characterized_blind" if d.in_envelope else "measurement_demand"
        reason = (f"standing grant [{corner}] for '{fault_class['name']}' under "
                  f"{detector}: P_det_lo95={d.p_det_lo95:.2f} -> sigma={int(sigma)}"
                  + (f" ({blind_kind})" if blind_kind else ""))
        escalated = A <= Autonomy.PROPOSE_WAIT
        situation = {"s": s, "rho": rho, "corner": corner}
        payload = None
        if escalated:
            evidence = {"standing_blind_class": fault_class["name"],
                        "blind_kind": blind_kind}
            if blind_kind == "measurement_demand":
                evidence["measurement_order"] = (
                    f"characterize {detector} at severity <= {s:.3f}*Pb "
                    f"(below current measured floor) before granting autonomy")
            else:
                evidence["contamination_note"] = (
                    "CI signal is CONTAMINATED as an optimization input in this "
                    "standing-blind region: an undetected fault silently biases "
                    "every per-piece CI number the Energy Agent optimizes.")
            payload = self._escalation_payload(
                action, detector, sigma, d.p_det_lo95, d.provenance, reason,
                situation, evidence=evidence, deferral_cost=None)
        gd = GovernanceDecision(action, detector, sigma, A, d.p_det_lo95, reason,
                                situation, escalated, payload)
        gd.situation["blind_kind"] = blind_kind
        return gd

    # ---- helpers ----------------------------------------------------------
    def _reason(self, sigma: Sigma, action: Action, A: Autonomy) -> str:
        bits = [f"sigma={int(sigma)} ({sigma.name})", f"alpha={action.alpha}",
                f"A=min={int(A)}"]
        if action.isa95_level == 2:
            bits.append("L2 cap applied (control-layer request)")
        return "; ".join(bits)

    def _escalation_payload(self, action, detector, sigma, plo, prov, reason,
                            situation, evidence, deferral_cost) -> Dict:
        # B.6: everything the human needs to act and audit.
        return {
            "gate_reason": reason,
            "sensing_tier": int(sigma),
            "p_det_lo95": plo,
            "provenance": prov,               # which archived sweep
            "detector": detector,
            "situation": situation,           # position on the autonomy map
            "proposed_action": action.name,   # what the agent would have done
            "action_alpha": action.alpha,
            "isa95_level": action.isa95_level,
            "evidence": evidence or {},
            "projected_deferral_cost": deferral_cost or {},
        }
