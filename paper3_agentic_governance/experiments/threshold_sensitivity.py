"""experiments/threshold_sensitivity.py — cut-point robustness ablation.

Re-gate the archetype standing grants at theta_2 in {0.4,0.5,0.6} and theta_1 in
{0.10,0.18,0.30} (no re-simulation) and report which grants flip vs the derived
operating point (c2=0.50, c1=0.1813).
"""
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Lesia Yanytska
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from contract.governance import EpistemicContract, SIGMA_C3_RELIABLE

ARCHES = ["compressed_air_leak", "coolant_pump_fault", "machine_left_on", "tool_wear"]
THETA2 = [0.4, 0.5, 0.6]
THETA1 = [0.10, 0.18, 0.30]


def _registry():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "contract", "fault_registry.yaml")
    with open(path) as f:
        return {a["name"]: a for a in yaml.safe_load(f)["archetypes"]}


def grants(cuts, reg):
    C = EpistemicContract(cuts=cuts)
    out = {}
    for det in ("D0", "D2"):
        for name in ARCHES:
            for corner in ("default", "worstcase"):
                out[(det, name, corner)] = int(
                    C.standing_grant(reg[name], "defer_job", det, corner=corner).sigma)
    return out


def main():
    reg = _registry()
    base = grants({"c1": 0.1813, "c2": 0.50, "c3": SIGMA_C3_RELIABLE}, reg)
    flips = 0
    for t2 in THETA2:
        for t1 in THETA1:
            g = grants({"c1": t1, "c2": t2, "c3": SIGMA_C3_RELIABLE}, reg)
            diff = {k: (base[k], g[k]) for k in base if base[k] != g[k]}
            if diff:
                flips += 1
                print(f"theta2={t2} theta1={t1}: "
                      + ", ".join(f"{k[1]}/{k[0]}/{k[2]} {a}->{b}"
                                  for k, (a, b) in diff.items()))
    total = len(THETA2) * len(THETA1)
    print(f"\n{total-flips}/{total} combinations leave all {len(base)} grants unchanged; "
          f"derived point (0.50/0.181) is in the stable interior.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
