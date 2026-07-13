"""env/plant.py — plant substrate + detectors behind a documented interface.

The REAL Papers 1-2 code drops in here: `Substrate` wraps your Module 1-4
energy/CI simulation and `Detector` wraps the deployed D0 (rolling-median +
CUSUM) and D2 (event-anchored fixed-reference + CUSUM) monitors.  Until then a
minimal, faithful STAND-IN lets the smoke test run end-to-end today:

  * Substrate emits per-piece spindle power around baseline P_b with an injected
    fault (severity Delta, onset profile) and derives per-piece CI from the grid
    trace.  This is the *ground truth* the detectors must (or must not) see.
  * D0's adaptive rolling baseline chases a slow ramp and ABSORBS it -> misses
    tool wear at rho~1 (the inertia limit, live).  D2's fixed reference does not
    chase -> catches it.  This reproduces the qualitative Paper 1/2 behaviour so
    the smoke test demonstrates the mechanism for real, not by fiat.

Replace the two stand-in classes with imports of your archived modules; the
Agents and the contract consume only the interfaces below.
"""
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Lesia Yanytska
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .grid_ci import GridCITrace


# --------------------------------------------------------------------------- #
# Interfaces (stable seam for the real Module 1-4 code)
# --------------------------------------------------------------------------- #
@dataclass
class Piece:
    idx: int
    power_kw: float          # measured spindle power for this piece
    ci_per_piece: float      # gCO2e attributed to this piece (power * grid CI * t)


@dataclass
class Alarm:
    fired: bool
    piece_idx: Optional[int]
    s_hat: float             # estimated severity fraction Delta/P_b
    rho_hat: float           # estimated onset ratio
    attribution_conf: float  # [0,1]


@dataclass
class FaultSpec:
    name: str
    severity_frac: float     # Delta / P_b
    onset_ratio: float       # tau_onset / W_b
    profile: str = "ramp"    # 'ramp' | 'step' | 'slow_ramp'
    start_frac: float = 0.25 # where in the run the fault begins


# --------------------------------------------------------------------------- #
# Stand-in substrate
# --------------------------------------------------------------------------- #
class Substrate:
    def __init__(self, baseline_kw: float = 3.4, window_slots: int = 120,
                 piece_seconds: float = 30.0):
        self.pb = baseline_kw
        self.wb = window_slots            # W_b in pieces (adaptive window)
        self.piece_seconds = piece_seconds

    def run(self, n_pieces: int, grid: GridCITrace,
            fault: Optional[FaultSpec] = None) -> List[Piece]:
        pieces = []
        onset_pieces = max(1.0, (fault.onset_ratio * self.wb)) if fault else 1.0
        start = int(fault.start_frac * n_pieces) if fault else n_pieces + 1
        for i in range(n_pieces):
            delta = 0.0
            if fault and i >= start:
                frac = min(1.0, (i - start) / onset_pieces)
                if fault.profile == "step":
                    frac = 1.0
                delta = fault.severity_frac * self.pb * frac
            power = self.pb + delta
            t_min = i * self.piece_seconds / 60.0
            ci = power * grid.at(t_min) * (self.piece_seconds / 3600.0)  # gCO2e
            pieces.append(Piece(i, round(power, 4), round(ci, 4)))
        return pieces


# --------------------------------------------------------------------------- #
# Stand-in detectors
# --------------------------------------------------------------------------- #
class _CusumBase:
    def __init__(self, pb: float, k_frac: float = 0.10, h: float = 2.5):
        self.pb = pb
        self.k = k_frac * pb          # CUSUM slack
        self.h = h                    # alarm threshold (kW-pieces)

    def _estimate(self, pieces, fired_idx):
        """Rough (s_hat, rho_hat) from the residual trajectory after an alarm."""
        tail = [p.power_kw - self.pb for p in pieces[max(0, fired_idx - 40):fired_idx + 1]]
        s_hat = max(0.0, max(tail, default=0.0)) / self.pb
        # crude onset estimate: pieces from first positive residual to alarm
        first = next((j for j, r in enumerate(tail) if r > 0.02 * self.pb), 0)
        rho_hat = max(0.033, (len(tail) - first) / 120.0)
        return round(s_hat, 3), round(rho_hat, 3)


class D0RollingDetector(_CusumBase):
    """Adaptive rolling-median baseline + CUSUM. Chases slow drift (inertia)."""
    name = "D0"

    def detect(self, pieces: List[Piece], window: int = 45) -> Alarm:
        cusum = 0.0
        for i, p in enumerate(pieces):
            lo = max(0, i - window)
            ref = sorted(x.power_kw for x in pieces[lo:i + 1])[max(0, (i - lo) // 2)]
            resid = p.power_kw - ref            # rolling baseline absorbs slow ramps
            cusum = max(0.0, cusum + resid - self.k)
            if cusum > self.h:
                s_hat, rho_hat = self._estimate(pieces, i)
                return Alarm(True, i, s_hat, rho_hat, attribution_conf=0.95)
        return Alarm(False, None, 0.0, 0.0, attribution_conf=0.0)


class D2EventAnchoredDetector(_CusumBase):
    """Fixed-reference (event-anchored) baseline + CUSUM. Does not chase drift."""
    name = "D2"

    def detect(self, pieces: List[Piece], ref_slots: int = 60) -> Alarm:
        ref = sum(x.power_kw for x in pieces[:ref_slots]) / max(1, ref_slots)
        cusum = 0.0
        for i, p in enumerate(pieces):
            resid = p.power_kw - ref             # fixed anchor -> slow ramp accumulates
            cusum = max(0.0, cusum + resid - self.k)
            if cusum > self.h:
                s_hat, rho_hat = self._estimate(pieces, i)
                return Alarm(True, i, s_hat, rho_hat, attribution_conf=0.9)
        return Alarm(False, None, 0.0, 0.0, attribution_conf=0.0)


DETECTORS = {"D0": D0RollingDetector, "D2": D2EventAnchoredDetector}
