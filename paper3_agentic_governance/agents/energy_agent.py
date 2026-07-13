"""agents/energy_agent.py — minimise emissions, subject to the epistemic contract.

The Energy Agent reads (a) the live detector alarm/estimates and (b) the grid-CI
forecast, and proposes a carbon-reducing action.  Under P-gated every proposal
passes through the EpistemicContract, which may act, notify, require approval, or
BLOCK+ESCALATE.  Under P-naive the agent acts on the CI signal directly — which
is exactly what fails in a standing-blind region, where the CI signal it
optimises is silently contaminated by the undetected fault.
"""
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Lesia Yanytska
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from contract.governance import ACTIONS, Autonomy, EpistemicContract
from env.grid_ci import GridCITrace
from env.plant import Alarm, Piece
from .negotiation import Award, Task, award
from .production_agent import ProductionAgent


@dataclass
class Decision:
    policy: str
    detector: str
    action: str
    executed: bool
    escalated: bool
    autonomy: Optional[int]
    ci_per_piece_seen: float          # what the agent believed (may be contaminated)
    ci_per_piece_truth: float         # ground-truth mean
    note: str
    award: Optional[Award] = None
    payload: Optional[Dict] = None


class EnergyAgent:
    def __init__(self, baseline_kw: float = 3.4, piece_seconds: float = 30.0):
        self.pb = baseline_kw
        self.piece_seconds = piece_seconds

    def _emissions_saved_kg(self, grid: GridCITrace, now_min: float,
                            target_min: float, pieces_deferred: int = 20) -> float:
        ci_now = grid.at(now_min)
        ci_target = grid.at(target_min)
        energy_kwh = self.pb * (self.piece_seconds / 3600.0) * pieces_deferred
        return max(0.0, (ci_now - ci_target) * energy_kwh / 1000.0)  # kg

    def propose(self, pieces: List[Piece], alarm: Alarm, grid: GridCITrace,
                now_min: float = 1080.0) -> Task:
        # Agent's belief about per-piece CI comes from what it can measure.
        # In a blind region the undetected fault inflates recent pieces, but the
        # agent has no alarm, so it treats them as nominal baseline load.
        target = grid.lowest_window(now_min, horizon_min=1440, duration_min=60)
        saved = self._emissions_saved_kg(grid, now_min, target)
        return Task("defer_job", job_id="J1", from_min=now_min, to_min=target,
                    emissions_saved_kg=round(saved, 4))

    # ---- policies ---------------------------------------------------------
    def decide(self, policy: str, detector: str, pieces: List[Piece], alarm: Alarm,
               grid: GridCITrace, fault_class: Optional[Dict],
               contract: Optional[EpistemicContract],
               production: ProductionAgent, now_min: float = 1080.0) -> Decision:
        ci_truth = sum(p.ci_per_piece for p in pieces) / len(pieces)
        # The agent's *seen* CI: if no alarm, it cannot subtract the fault, so it
        # believes the (contaminated) measured value; a clean baseline would be
        # pb-only. We report both to expose the contamination.
        ci_seen = ci_truth  # measured; agent cannot know it is inflated w/o detection

        task = self.propose(pieces, alarm, grid, now_min)
        bid = production.bid(task)
        aw = award(task, bid)

        if policy == "naive":
            # Acts on the CI signal regardless of sensing fidelity.
            note = "acted on CI signal without governance"
            if fault_class and alarm is not None and not alarm.fired:
                note = ("NO ALARM in a fault scenario: agent optimises on a "
                        "CONTAMINATED CI signal, unaware. Confident wrong basis.")
            return Decision(policy, detector, "defer_job", executed=aw.accepted,
                            escalated=False, autonomy=None, ci_per_piece_seen=ci_seen,
                            ci_per_piece_truth=ci_truth, note=note, award=aw)

        # P-gated: consult the epistemic contract.
        assert contract is not None
        if fault_class is not None:
            # EX-ANTE standing grant keyed by the fault class the action is
            # premised on being absent.
            gd = contract.standing_grant(fault_class, "defer_job", detector)
        else:
            gd = contract.gate_action("defer_job", s_hat=alarm.s_hat,
                                      rho_hat=alarm.rho_hat, detector=detector,
                                      attribution_conf=alarm.attribution_conf)
        if gd.escalated:
            return Decision(policy, detector, "defer_job", executed=False,
                            escalated=True, autonomy=int(gd.autonomy),
                            ci_per_piece_seen=ci_seen, ci_per_piece_truth=ci_truth,
                            note="ESCALATED: " + gd.reason, award=aw, payload=gd.payload)
        executed = aw.accepted and gd.autonomy >= Autonomy.ACT_NOTIFY
        return Decision(policy, detector, "defer_job", executed=executed,
                        escalated=False, autonomy=int(gd.autonomy),
                        ci_per_piece_seen=ci_seen, ci_per_piece_truth=ci_truth,
                        note="acted under grant: " + gd.reason, award=aw)
