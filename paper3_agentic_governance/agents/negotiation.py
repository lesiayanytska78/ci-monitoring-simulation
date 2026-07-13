"""agents/negotiation.py — deterministic contract-net (announce -> bid -> award).

Seeded and fully reproducible: no RNG, no wall-clock. The Energy Agent announces
a load-shift/defer task; the Production Agent bids the schedule cost; the award
rule is a weighted multi-objective score.
"""
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Lesia Yanytska
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Task:
    kind: str                 # e.g. 'defer_job'
    job_id: str
    from_min: float
    to_min: float             # proposed new start
    emissions_saved_kg: float


@dataclass
class Bid:
    tardiness_min: float
    deadline_violated: bool


@dataclass
class Award:
    task: Task
    bid: Bid
    accepted: bool
    score: float
    rationale: str


def award(task: Task, bid: Bid, w_carbon: float = 1.0, w_time: float = 0.05) -> Award:
    """score = w_c * emissions_saved - w_t * tardiness ; accept iff score > 0
    and no hard deadline violation."""
    score = w_carbon * task.emissions_saved_kg - w_time * bid.tardiness_min
    accepted = (score > 0.0) and (not bid.deadline_violated)
    rationale = (f"score = {w_carbon}*{task.emissions_saved_kg:.2f} "
                 f"- {w_time}*{bid.tardiness_min:.1f} = {score:.2f}; "
                 f"deadline_violated={bid.deadline_violated}")
    return Award(task, bid, accepted, round(score, 3), rationale)
