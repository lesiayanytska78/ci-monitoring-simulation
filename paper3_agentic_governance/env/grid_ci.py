"""env/grid_ci.py — grid carbon-intensity signal for the Energy Agent.

Primary source (real deployment): UK NESO Carbon Intensity API
(https://api.carbonintensity.org.uk, CC BY 4.0, no key), half-hourly national
forecast + actual.  For a reproducible run we PIN a fixed window to a cache file
and record its sha256 snapshot hash; the offline synthetic diurnal fallback
keeps the smoke test deterministic and network-free.

Swap: point `source="neso"` and provide a from/to window to fetch and cache the
real trace; the snapshot hash goes in the reproducibility statement.
"""
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Lesia Yanytska
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from typing import List, Optional
from urllib import request

_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(_CACHE_DIR, exist_ok=True)
_CACHE = os.path.join(_CACHE_DIR, "grid_ci_snapshot.json")
_NESO = "https://api.carbonintensity.org.uk/intensity/{frm}/{to}"


@dataclass
class GridCITrace:
    """Half-hourly carbon intensity in gCO2/kWh."""
    values: List[float]        # gCO2e / kWh, one per 30-min slot
    period_min: int            # slot length in minutes
    source: str                # 'neso' or 'synthetic'
    snapshot_sha256: str

    def at(self, t_min: float) -> float:
        idx = int((t_min // self.period_min)) % len(self.values)
        return self.values[idx]

    def lowest_window(self, start_min: float, horizon_min: float,
                      duration_min: float) -> float:
        """Return the start time (min) of the lowest-CI slot in the horizon."""
        best_t, best_ci = start_min, float("inf")
        t = start_min
        while t <= start_min + horizon_min:
            ci = self.at(t)
            if ci < best_ci:
                best_ci, best_t = ci, t
            t += self.period_min
        return best_t


def _sha(values: List[float]) -> str:
    return hashlib.sha256(json.dumps([round(v, 3) for v in values]).encode()).hexdigest()[:16]


def _synthetic(days: int = 14, period_min: int = 30, seed: int = 7) -> List[float]:
    """Deterministic diurnal CI: overnight low, daytime/evening peaks."""
    slots_per_day = 24 * 60 // period_min
    vals = []
    for d in range(days):
        for k in range(slots_per_day):
            hour = k * period_min / 60.0
            # base diurnal shape (gCO2/kWh): trough ~120 at 04:00, peak ~330 at 18:00
            diurnal = 225 + 105 * math.sin((hour - 10.0) / 24.0 * 2 * math.pi)
            # mild day-to-day drift, fully deterministic
            drift = 15 * math.sin((d + seed) / 7.0 * 2 * math.pi)
            vals.append(round(max(60.0, diurnal + drift), 2))
    return vals


def load_grid_ci(source: str = "synthetic", days: int = 14,
                 frm: Optional[str] = None, to: Optional[str] = None,
                 use_cache: bool = True) -> GridCITrace:
    if use_cache and os.path.exists(_CACHE):
        with open(_CACHE) as f:
            c = json.load(f)
        return GridCITrace(c["values"], c["period_min"], c["source"], c["snapshot_sha256"])

    values, src = None, source
    if source == "neso" and frm and to:
        try:                                             # pragma: no cover - network
            url = _NESO.format(frm=frm, to=to)
            with request.urlopen(url, timeout=10) as resp:
                data = json.load(resp)
            values = [d["intensity"]["forecast"] for d in data["data"]]
            src = "neso"
        except Exception:
            values = None
    if not values:
        values, src = _synthetic(days=days), "synthetic"

    trace = GridCITrace(values, 30, src, _sha(values))
    with open(_CACHE, "w") as f:
        json.dump(trace.__dict__, f)
    return trace
