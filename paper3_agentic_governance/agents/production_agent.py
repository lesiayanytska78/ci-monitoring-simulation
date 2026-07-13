"""agents/production_agent.py — throughput / deadline objective."""
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Lesia Yanytska
from __future__ import annotations

from dataclasses import dataclass

from .negotiation import Bid, Task


@dataclass
class ProductionAgent:
    job_duration_min: float = 60.0
    deadline_min: float = 3000.0     # generous for the smoke test; tighten in Phase 3

    def bid(self, task: Task) -> Bid:
        finish = task.to_min + self.job_duration_min
        tardiness = max(0.0, finish - self.deadline_min)
        return Bid(tardiness_min=round(tardiness, 2),
                   deadline_violated=finish > self.deadline_min)
