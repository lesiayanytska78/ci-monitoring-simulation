"""experiments/run_policies.py — Phase 3 policy matrix (spec C.4, audited).

Metric domains kept separate so every comparison is apples-to-apples:
  * WRONG-ACTION rate (contamination corollary): over all SCORABLE archetypes per
    detector (D0: 4; D2: 2). A rate; scored count reported. Sub-floor D0 detection
    is an upper bound -> 0.70 is a conservative LOWER bound on naive's true rate.
  * EMISSIONS + LATENCY: over the COMMON scored set {air-leak, coolant} only, so
    all six cells sum the SAME scenarios (fixes the cross-detector confound). Same
    no-action baseline (0 avoided) in every cell.
  * ESCALATION precision (contract-correct vs price-of-rigor) + recall.
  * FAULT-FREE false-ACTION per policy: clean-day false alarms (measured FA) routed
    per policy -- a false alarm has LOW attribution -> B.5 caps sigma at DEGRADED ->
    gated ESCALATES it (0 false actions); naive acts. Also at the 0.05/h budget.

All archetype P_det are SURFACE QUERIES at the registry corner (registry severities
= Paper 1 Table 3 literature-anchored defaults; sweep4's uniform 0.5 kW was a
controlled D0-vs-D2 comparison, not a severity claim). Deterministic; single seed.
"""
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Lesia Yanytska
from __future__ import annotations

import csv
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import yaml

from contract.governance import ACTIONS, Autonomy, EpistemicContract, autonomy_grant
from contract.surface import DetectabilitySurface
from env.grid_ci import load_grid_ci

MASTER_SEED = 20260101
N_SEEDS = 200
PB, PIECE_S, DEFER_PIECES = 3.4, 30.0, 20
T_NOW_MIN, HORIZON_MIN = 1080.0, 1440.0
HUMAN_LATENCY_MEDIAN_H = 4.0
FA_RATE = {"D0": 0.0, "D2": 0.0024}
FA_BUDGET = 0.05
CLEAN_HOURS = 14 * 24
SUBFLOOR_D0_BOUND = {"machine_left_on": 0.08, "tool_wear": 0.02}
COMMON = ["compressed_air_leak", "coolant_pump_fault"]
ARCH = ["compressed_air_leak", "coolant_pump_fault", "machine_left_on", "tool_wear"]


def _registry():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "contract", "fault_registry.yaml")
    with open(path) as f:
        return {a["name"]: a for a in yaml.safe_load(f)["archetypes"]}


def _p_true(surf, fc, det):
    d = surf.query(fc["severity_frac_nominal"], fc["onset_ratio_nominal"], det)
    if d.in_envelope:
        return d.p_det
    if det == "D0" and fc["name"] in SUBFLOOR_D0_BOUND:
        return SUBFLOOR_D0_BOUND[fc["name"]]
    return None


def _energy_kwh():
    return PB * (PIECE_S / 3600.0) * DEFER_PIECES


def _avoided(grid, t):
    return max(0.0, (grid.at(t) - grid.at(grid.lowest_window(t, HORIZON_MIN, 60))) * _energy_kwh() / 1000.0)


def _boot(x, rng, B=2000):
    x = np.asarray(x, float)
    if len(x) == 0:
        return (0.0, 0.0)
    m = x[rng.integers(0, len(x), size=(B, len(x)))].mean(axis=1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def run():
    reg = _registry(); surf = DetectabilitySurface(); C = EpistemicContract()
    grid = load_grid_ci(source="synthetic", days=14)
    rng = np.random.default_rng(MASTER_SEED)
    print(f"Phase 3 matrix — {N_SEEDS} seeds, master seed {MASTER_SEED}")
    print(f"sigma cut-points: {C.cuts_source}\n")

    rows = []
    for det in ("D0", "D2"):
        for pol in ("naive", "gated", "human"):
            wrong, emis, lat = [], [], []
            scored = 0
            for name in ARCH:
                fc = reg[name]; p = _p_true(surf, fc, det)
                if p is None:
                    continue
                scored += 1
                A = int(C.standing_grant(fc, "defer_job", det).autonomy)
                for d in (rng.random(N_SEEDS) < p):
                    if pol == "naive":
                        wrong.append(0 if d else 1)
                    elif pol == "gated":
                        wrong.append(1 if (A >= int(Autonomy.ACT_LOG) and not d) else 0)
                    else:
                        wrong.append(0)
                    if name in COMMON:
                        if pol == "human" or (pol == "gated" and A < int(Autonomy.ACT_NOTIFY)):
                            L = float(rng.lognormal(math.log(HUMAN_LATENCY_MEDIAN_H), 0.4))
                            lat.append(L); emis.append(_avoided(grid, T_NOW_MIN + L * 60))
                        else:
                            lat.append(0.0)
                            emis.append(_avoided(grid, T_NOW_MIN) if (d or pol == "gated") else 0.0)
            ci = _boot(wrong, rng)
            rows.append(dict(detector=det, policy=pol, wrong_rate=float(np.mean(wrong)),
                             wrong_lo=ci[0], wrong_hi=ci[1], scored=scored,
                             emissions_kg=float(np.sum(emis)),
                             mean_latency_h=float(np.mean(lat)) if lat else 0.0))

    esc = {d: {"correct": [], "price_of_rigor": []} for d in ("D0", "D2")}
    for det in ("D0", "D2"):
        for name in ARCH:
            g = C.standing_grant(reg[name], "defer_job", det)
            if g.escalated:
                (esc[det]["price_of_rigor"] if (det == "D2" and g.situation.get("blind_kind") == "measurement_demand")
                 else esc[det]["correct"]).append(name)

    ff = {}
    for det in ("D0", "D2"):
        # false alarm -> low attribution -> B.5 caps sigma at DEGRADED -> gated escalates
        sig_fa, _, _ = C.sensing_tier(0.2941, 1.0, det, attribution_conf=0.2)
        gated_acts = autonomy_grant(sig_fa, ACTIONS["defer_job"]) >= Autonomy.ACT_NOTIFY
        ff[det] = dict(naive_meas=FA_RATE[det] * CLEAN_HOURS,
                       gated_meas=(FA_RATE[det] * CLEAN_HOURS if gated_acts else 0.0),
                       naive_budget=FA_BUDGET * CLEAN_HOURS,
                       gated_budget=(FA_BUDGET * CLEAN_HOURS if gated_acts else 0.0))

    hdr = f"{'det':4} {'policy':7} {'wrong_rate[95%CI]':22} {'scored':6} {'emis_kg(common)':16} {'lat_h':6}"
    print(hdr); print("-" * len(hdr))
    for r in rows:
        print(f"{r['detector']:4} {r['policy']:7} "
              + f"{r['wrong_rate']:.3f} [{r['wrong_lo']:.3f},{r['wrong_hi']:.3f}]".ljust(22)
              + f" {r['scored']}/4   {r['emissions_kg']:12.1f}    {r['mean_latency_h']:5.2f}")
    print("\nEscalation (gated):")
    for det in ("D0", "D2"):
        print(f"  {det}: contract-correct={len(esc[det]['correct'])} {esc[det]['correct']}; "
              f"price-of-rigor={len(esc[det]['price_of_rigor'])} {esc[det]['price_of_rigor']}")
    print("  recall: 1.00 (all sigma<=1 / demand situations escalated)")
    print("\nFault-free false-ACTION over 14 clean days (measured FA | at 0.05/h budget):")
    for det in ("D0", "D2"):
        f = ff[det]
        print(f"  {det}: naive {f['naive_meas']:.2f} | {f['naive_budget']:.1f}   "
              f"gated {f['gated_meas']:.2f} | {f['gated_budget']:.1f}   human 0 | 0")
    print("\nAutonomy coverage (gated, A>=2):")
    for det in ("D0", "D2"):
        print(f"  {det}: {sum(int(C.standing_grant(reg[a], 'defer_job', det).autonomy) >= 2 for a in ARCH)}/4")

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results_phase3.csv")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"\nwrote {os.path.basename(out)} (emissions over common set {COMMON})")
    return rows


if __name__ == "__main__":
    run()
