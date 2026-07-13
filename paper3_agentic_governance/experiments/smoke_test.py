"""experiments/smoke_test.py — the thesis, running on REAL characterized data.

Three archetypes x {naive, gated} x {D0, D2}:
  * ACUTE       air leak (0.44*Pb, fast)  — above floor, fast onset
  * RECOVERY    coolant  (0.35*Pb, step)  — D0 degraded (propose+wait) -> D2 reliable
  * DEMAND      tool wear (0.24*Pb, slow) — below BOTH detectors' measured floor

Acceptance (Phase-2, audited):
  1. naive / D0 / tool wear  -> acts on a CONTAMINATED CI signal (no alarm);
  2. gated / D0 / coolant     -> escalates, gated / D2 / coolant -> acts  (RECOVERY);
  3. gated / D2 / tool wear   -> escalates with a MEASUREMENT DEMAND.
"""
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Lesia Yanytska
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from contract.governance import EpistemicContract
from env.grid_ci import load_grid_ci
from env.plant import DETECTORS, FaultSpec, Substrate
from agents.energy_agent import EnergyAgent
from agents.production_agent import ProductionAgent

N_PIECES = 400


def _registry():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "contract", "fault_registry.yaml")
    with open(path) as f:
        return {a["name"]: a for a in yaml.safe_load(f)["archetypes"]}


def _bk(dec):
    return (dec.payload or {}).get("evidence", {}).get("blind_kind") if dec.escalated else None


def run_case(fault_class, policy, detector_name, grid, contract):
    sub = Substrate(baseline_kw=3.4)
    fault = FaultSpec(name=fault_class["name"],
                      severity_frac=fault_class["severity_frac_nominal"],
                      onset_ratio=fault_class["onset_ratio_nominal"],
                      profile=fault_class["onset_profile"])
    pieces = sub.run(N_PIECES, grid, fault)
    alarm = DETECTORS[detector_name](pb=3.4).detect(pieces)
    dec = EnergyAgent().decide(policy, detector_name, pieces, alarm, grid,
                               fault_class=fault_class,
                               contract=(contract if policy == "gated" else None),
                               production=ProductionAgent())
    return alarm, dec


def main():
    grid = load_grid_ci(source="synthetic", days=14)
    C = EpistemicContract()
    reg = _registry()
    print(f"grid-CI source={grid.source} snapshot={grid.snapshot_sha256}")
    print(f"sigma cut-points: {C.cuts_source}\n")

    scenarios = [("ACUTE    air leak", reg["compressed_air_leak"]),
                 ("RECOVERY coolant ", reg["coolant_pump_fault"]),
                 ("DEMAND   tool wear", reg["tool_wear"])]
    hdr = f"{'scenario':19} {'det':4} {'policy':7} {'alarm':6} {'A':>2} {'result':9} note"
    print(hdr); print("-" * len(hdr))
    for label, fc in scenarios:
        for detn in ("D0", "D2"):
            for policy in ("naive", "gated"):
                alarm, d = run_case(fc, policy, detn, grid, C)
                A = "" if d.autonomy is None else str(d.autonomy)
                res = "ESCALATE" if d.escalated else ("acted" if d.executed else "held")
                bk = _bk(d)
                tag = f" [{bk}]" if bk else ""
                print(f"{label:19} {detn:4} {policy:7} "
                      f"{'fired' if alarm.fired else 'silent':6} {A:>2} {res:9}{tag}")
        print()

    _, naive_tw_d0 = run_case(reg["tool_wear"], "naive", "D0", grid, C)
    _, gated_co_d0 = run_case(reg["coolant_pump_fault"], "gated", "D0", grid, C)
    _, gated_co_d2 = run_case(reg["coolant_pump_fault"], "gated", "D2", grid, C)
    _, gated_tw_d2 = run_case(reg["tool_wear"], "gated", "D2", grid, C)

    ok = (naive_tw_d0.executed
          and gated_co_d0.escalated and gated_co_d2.executed
          and gated_tw_d2.escalated and _bk(gated_tw_d2) == "measurement_demand")
    print("ACCEPTANCE CHECK")
    print(f"  1. naive/D0/tool-wear acted on contaminated CI : {naive_tw_d0.executed}")
    print(f"  2. coolant  D0 escalate={gated_co_d0.escalated} -> D2 acted={gated_co_d2.executed}  (measured recovery)")
    print(f"  3. tool-wear D2 -> {_bk(gated_tw_d2)}  (refused unmeasured grant)")
    print(f"\nRESULT: {'PASS - audited thesis reproduced' if ok else 'FAIL'}")
    if gated_tw_d2.payload:
        print("  measurement order:", gated_tw_d2.payload["evidence"].get("measurement_order"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
