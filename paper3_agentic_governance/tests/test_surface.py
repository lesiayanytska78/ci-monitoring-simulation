"""Pin the characterized detectability surface to the REAL archived anchors.

Source: paper2_multiseverity_summary.csv (D0_deployed & D2_anchored_cusum,
n=200/cell, paper's bootstrap CI) + sweep8_boundary.csv (fast-onset floor).
Pb = 3.4 kW, so 2 kW = 0.5882*Pb. Both detectors' measured severity floor is
1.0 kW = 0.2941*Pb; nothing below that is characterized (no predicted rows).
"""
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Lesia Yanytska
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from contract.surface import DetectabilitySurface  # noqa: E402

S2KW = 0.5882
SFLOOR = 0.2941   # 1.0 kW / 3.4 kW  — lowest MEASURED severity for both detectors


@pytest.fixture(scope="module")
def surf():
    return DetectabilitySurface()


@pytest.mark.parametrize("rho,expected", [
    (0.167, 0.970), (0.40, 0.840), (0.50, 0.680),
    (0.70, 0.420), (1.00, 0.200), (2.00, 0.050),
])
def test_d0_inertia_sigmoid_real(surf, rho, expected):
    assert surf.p_det(S2KW, rho, "D0", conservative=False) == pytest.approx(expected, abs=0.02)


def test_d0_floor_fast_onset(surf):
    assert surf.p_det(0.2941, 0.033, "D0", conservative=False) == pytest.approx(0.10, abs=0.03)
    assert surf.p_det(0.4412, 0.033, "D0", conservative=False) == pytest.approx(0.76, abs=0.03)


def test_d2_reliable_within_measured_envelope(surf):
    for rho in (0.167, 0.50, 1.0, 2.0):
        assert surf.p_det(SFLOOR, rho, "D2") >= 0.90


def test_no_predicted_rows_below_measured_floor(surf):
    assert surf.query(0.235, 1.0, "D2").in_envelope is False
    assert surf.query(0.265, 0.033, "D2").in_envelope is False
    assert surf.query(0.235, 1.0, "D0").in_envelope is False


def test_blind_sub_floor_severity(surf):
    assert surf.p_det(0.20, 0.5, "D0") == 0.0
    assert surf.query(0.20, 0.5, "D0").in_envelope is False


def test_blind_slower_than_characterized(surf):
    assert surf.p_det(S2KW, 3.0, "D0") == 0.0


def test_flat_extension_higher_severity(surf):
    top = surf.query(1.1765, 0.167, "D0")
    ext = surf.query(1.30, 0.167, "D0")
    assert ext.in_envelope is True and ext.extrapolated is True
    assert ext.p_det_lo95 == top.p_det_lo95
    assert ext.p_det <= top.p_det + 1e-9


def test_flat_extension_faster_onset(surf):
    fast = surf.query(S2KW, 0.033, "D0")
    ext = surf.query(S2KW, 0.01, "D0")
    assert ext.extrapolated is True
    assert ext.p_det_lo95 == fast.p_det_lo95


def test_measured_cells_not_flagged_extrapolated(surf):
    assert surf.query(S2KW, 0.40, "D0").extrapolated is False


def test_conservative_uses_lower_bound(surf):
    r = surf.query(S2KW, 0.40, "D0")
    assert r.p_det_lo95 <= r.p_det
    assert surf.p_det(S2KW, 0.40, "D0") == r.p_det_lo95


def test_monotonic_decreasing_in_rho(surf):
    vals = [surf.p_det(S2KW, r, "D0", conservative=False)
            for r in (0.167, 0.40, 0.70, 1.0, 2.0)]
    assert all(a >= b for a, b in zip(vals, vals[1:]))


def test_provenance_is_archived_not_placeholder(surf):
    prov = surf.query(S2KW, 0.40, "D0").provenance
    assert "multiseverity" in prov and "PLACEHOLDER" not in prov
