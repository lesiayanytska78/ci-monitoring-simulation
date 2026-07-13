"""contract/surface.py — the characterized detectability surface P_det^d(s, rho).

Loads the archived per-detector detection-rate CSVs (Paper 1 boundary sweep /
inertia sigmoid / Fig-8 surface; Paper 2 D0/D2 severity generalization) and
exposes an interpolated P_det with 95% bootstrap CI lower bounds.

Design invariants (Paper 3 §B.1):
  * The surface is IMPORTED, never estimated at runtime — a property of the
    instrument measured offline under a calibrated campaign.
  * Interpolation is linear in severity s and LOG-linear in onset ratio rho.
  * Outside the characterized envelope, P_det := 0 (uncharacterized == blind).
  * The governance layer consumes the CI LOWER BOUND (`conservative=True`),
    never the point estimate.

The CSV schema (columns): detector, s, rho, p_det, p_det_lo95, n_seeds, source.
Swap the placeholder CSVs in contract/data/ for the archived ones; nothing else
changes.
"""
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Lesia Yanytska
from __future__ import annotations

import csv
import math
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_CSV = {"D0": "p_det_D0.csv", "D2": "p_det_D2.csv"}


@dataclass(frozen=True)
class Detectability:
    """Result of a surface query."""
    p_det: float          # point estimate
    p_det_lo95: float     # 95% bootstrap CI lower bound (governance uses this)
    in_envelope: bool     # False -> value is 0 by the uncharacterized==blind rule
    detector: str
    provenance: str       # pointer to the archived source, for the audit trail
    extrapolated: bool = False  # True -> flat-extended past the measured grid
                                # (easy direction only; value held at nearest
                                # measured cell, never extrapolated upward)


class DetectabilitySurface:
    """Interpolated detectability surface for one or more detectors."""

    def __init__(self, data_dir: str = _DATA_DIR):
        self._grids: Dict[str, _Grid] = {}
        for det, fname in _CSV.items():
            path = os.path.join(data_dir, fname)
            if os.path.exists(path):
                self._grids[det] = _Grid.from_csv(det, path)

    @property
    def detectors(self) -> List[str]:
        return sorted(self._grids)

    def query(self, s: float, rho: float, detector: str) -> Detectability:
        if detector not in self._grids:
            raise KeyError(f"no characterized surface for detector {detector!r}; "
                           f"have {self.detectors}")
        return self._grids[detector].query(s, rho)

    def p_det(self, s: float, rho: float, detector: str,
              conservative: bool = True) -> float:
        """Scalar convenience: CI lower bound by default (the governance value)."""
        r = self.query(s, rho, detector)
        return r.p_det_lo95 if conservative else r.p_det


class _Grid:
    """A structured (s x rho) grid with bilinear / log-rho interpolation."""

    def __init__(self, detector: str, s_axis: List[float], rho_axis: List[float],
                 p: Dict[Tuple[float, float], float],
                 lo: Dict[Tuple[float, float], float], provenance: str):
        self.detector = detector
        self.s_axis = sorted(s_axis)
        self.rho_axis = sorted(rho_axis)
        self._logrho = [math.log10(r) for r in self.rho_axis]
        self.p = p
        self.lo = lo
        self.provenance = provenance
        self.s_min, self.s_max = self.s_axis[0], self.s_axis[-1]
        self.rho_min, self.rho_max = self.rho_axis[0], self.rho_axis[-1]

    @classmethod
    def from_csv(cls, detector: str, path: str) -> "_Grid":
        s_set, rho_set = set(), set()
        p, lo = {}, {}
        provenance = os.path.basename(path)
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                s = float(row["s"]); rho = float(row["rho"])
                s_set.add(s); rho_set.add(rho)
                p[(s, rho)] = float(row["p_det"])
                lo[(s, rho)] = float(row["p_det_lo95"])
                if row.get("source"):
                    provenance = f"{os.path.basename(path)} :: {row['source']}"
        return cls(detector, list(s_set), list(rho_set), p, lo, provenance)

    def query(self, s: float, rho: float) -> Detectability:
        # "Uncharacterized == blind" applies only to the HARD directions, where
        # extrapolation would OVERstate detectability: sub-floor severity
        # (s < s_min) and slower-than-characterized onset (rho > rho_max). The
        # EASY directions are clamped into the measured envelope, since a faster
        # onset (rho < rho_min) or larger severity (s > s_max) is at least as
        # detectable as the nearest measured cell.
        if s < self.s_min or rho > self.rho_max:
            return Detectability(0.0, 0.0, False, self.detector, self.provenance)
        # Flat extension on the easy directions: clamp the query into the grid;
        # _interp then holds the value at the nearest measured cell (no upward
        # extrapolation). Mark it so grants off extended cells are auditable.
        extrap = (s > self.s_max) or (rho < self.rho_min)
        s_q = min(max(s, self.s_min), self.s_max)
        rho_q = min(max(rho, self.rho_min), self.rho_max)
        pt = self._interp(self.p, s_q, rho_q)
        lo = self._interp(self.lo, s_q, rho_q)
        return Detectability(round(pt, 6), round(lo, 6), True, self.detector,
                             self.provenance, extrapolated=extrap)

    def _bracket(self, axis: List[float], x: float) -> Tuple[int, int, float]:
        """Return (i, i+1, t) with axis[i] <= x <= axis[i+1] and t in [0,1]."""
        if x <= axis[0]:
            return 0, 0, 0.0
        if x >= axis[-1]:
            n = len(axis) - 1
            return n, n, 0.0
        for i in range(len(axis) - 1):
            if axis[i] <= x <= axis[i + 1]:
                span = axis[i + 1] - axis[i]
                t = 0.0 if span == 0 else (x - axis[i]) / span
                return i, i + 1, t
        n = len(axis) - 1
        return n, n, 0.0

    def _interp(self, tbl: Dict[Tuple[float, float], float], s: float,
                rho: float) -> float:
        i0, i1, ts = self._bracket(self.s_axis, s)
        j0, j1, tr = self._bracket(self._logrho, math.log10(rho))
        s0, s1 = self.s_axis[i0], self.s_axis[i1]
        r0, r1 = self.rho_axis[j0], self.rho_axis[j1]
        q00 = tbl[(s0, r0)]; q01 = tbl[(s0, r1)]
        q10 = tbl[(s1, r0)]; q11 = tbl[(s1, r1)]
        a = q00 * (1 - tr) + q01 * tr
        b = q10 * (1 - tr) + q11 * tr
        return a * (1 - ts) + b * ts


# module-level singleton for convenience
_DEFAULT = None


def default_surface() -> DetectabilitySurface:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = DetectabilitySurface()
    return _DEFAULT
