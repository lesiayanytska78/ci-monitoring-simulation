<!-- SPDX-License-Identifier: MIT -->
<!-- SPDX-FileCopyrightText: 2026 Lesia Yanytska -->

# Spec amendments from the Phase-1.2 real-data audit

Four challenges were raised against the first real-data wiring. Status:

## #1 — D2 grant below its measured floor (RESOLVED, code)
`paper2_multiseverity_summary.csv` characterizes D2 only down to 1.0 kW = 0.294*Pb.
The initial build injected a *predicted* s=0.10 slack-floor row (Paper 2's k*Pb≈0.10),
which let sub-floor faults receive an unmeasured grant. **Removed.** Sub-0.294*Pb
faults (tool wear 0.235, machine-left-on 0.265) are now below the characterized
floor → BLIND → `measurement_demand` (the contract issues a measurement order rather
than a silent grant). D2 recovers only the two archetypes it has measured (air leak,
coolant). This is the honest result: *three... two recovered, two measurement-demanded.*

## #2 — Envelope rule is a SPEC AMENDMENT, not a bug fix (B.1 addendum)
The surface extends detectability past the measured grid on the EASY directions only.
Two monotonicity axioms, justified by the measured monotone behaviour of the sigmoid:
  A1 (severity): P_det is non-decreasing in severity → for s > s_max, hold at the top
     measured cell (flat), never extrapolate upward.
  A2 (onset): P_det is non-increasing in onset ratio → for ρ < ρ_min (faster than
     tested), hold at the fastest measured cell.
The HARD directions remain blind by fiat: s < s_min (sub-floor) and ρ > ρ_max (slower
than tested). Implementation: `surface.query` flat-clamps and sets `extrapolated=True`;
the conservative value never exceeds the nearest measured lower bound. Tests:
`test_flat_extension_*`, `test_blind_*`. **Every grant traces to a measurement plus
these two stated axioms.**

## #3 — Ex-ante evaluation point (B.5 amendment, dual reporting)
`standing_grant(corner=...)`: `default` = nominal (calibrated expected case, for the
demonstration); `worstcase` = min-severity corner of the class's range (for the audit).
Reported together; the worst-case corner is provably ≤ the default tier. Example
(air leak, D0): default → TRANSITION, worst-case → DEGRADED.

## #4 — σ cut-point derivation (RESOLVED, spec B.2 amendment)
Decision-theoretic, one threshold at a time — no arbitrary constants:
  * c3 = 0.80  INHERITED (Papers 1-2 reliable-detection convention).
  * c2 = 0.50  PREPONDERANCE (balance of probabilities): autonomous-act-with-veto
    only where detecting the premise fault is more likely than not. Coincides with
    the measured sigmoid midpoint (rho~0.69 @ 2 kW) — boundary sits on a measurement
    though its justification is normative.
  * c1 = 1 - exp(-r_FA * T_h)  FA-EQUIVALENCE floor. With r_FA = 0.05/h (Sweep-3
    operating point) and T_h = 4 h (PoC response horizon): c1 = 1 - e^-0.2 ~= 0.1813.
    Below it, TP yield over the horizon ~ the characterized FA yield. Computed from
    two quantities with provenance; rises automatically for a noisier detector.
`derive_sigma_cutpoints()` implements it; `EpistemicContract.cuts_source` reports
"DERIVED: ...". The knee's lo95=0.71 still lands at c2=0.50 -> TRANSITION (the §5
"uncertainty tightens the boundary" finding is unchanged).

Robustness (experiments/threshold_sensitivity.py): grants are STABLE at the derived
point (c2=0.5, c1=0.181), but not across the full swept ranges — coolant's D0 tier
drops DEGRADED->BLIND once c1 >= ~0.28 (its lo95 = 0.277), and air-leak's worst-case
corner shifts at c2=0.4. Report as "stable at the derived operating point with a
0.096 margin on the coolant grant", not "flip-free everywhere".

# Phase-3 audit resolutions

## A1 — wrong-action denominator widened (C.4 contamination corollary)
The first matrix scored only air-leak + coolant (0.45). Machine-left-on and tool
wear are sub-floor for D0 and were excluded — silently redefining "wrong action"
as "wrong action following an alarm". Fixed: scored over ALL FOUR archetypes (sub-
floor D0 detection upper-bounded by the floor). Naive/D0 wrong-action = 0.699
[0.666,0.731]. D2 leaves the two uncharacterized archetypes UNSCORED.

## A2 — economic metrics added (the gated-vs-human differentiator)
emissions avoided + action latency now reported. Under D2, gated = 42 kg @ 0 h vs
human = 22 kg @ 4.2 h — autonomy's benefit is unlocked by sensor fidelity; under D0
gated ~ human (both escalate). Escalation precision split: D0 = 3 contract-correct;
D2 = 2 price-of-rigor (measurement_demand on faults the detector may catch — the
measurable cost of conservatism, remedied by characterizing below the floor).
Fault-free false-escalation from measured FA: D0 = 0.0000, D2 = 0.0096.

## A3 — figure craft
Fig 3(a) labels every bar (incl. zeros) with value + CI whiskers; 3(b) uses
"n of 4" not percentages. Fig 4 added (economic). Fig 2 area metric caption now
states: fraction of the characterized envelope, log-ρ measure.

## OPEN — spec-vs-archive archetype severity
Registry archetype severities come from the Paper-3 spec's delta_kw (air 1.5 kW =
0.44*Pb, etc.). The archive's sweep4_archetypes ran ALL archetypes at 0.5 kW =
0.147*Pb (air 0.52 / coolant 0.53 / machine 0.53 / tool 0.08 detection). The two
disagree on each archetype's severity — a registry-vs-archive reconciliation for
the author before submission. The matrix uses the registry severities.

# Phase-3 audit round 2

## R1 — registry severity documentation (decision: keep registry)
Registry archetype severities = Paper 1 Table 3 literature-anchored defaults (DOE
orifice tables; Shao et al.; anchored Brillinger no-load level) — the paper's own
definition of each archetype. sweep4's uniform 0.5 kW was a controlled-comparison
choice for the D0-vs-D2 ablation, not a severity claim. All archetype-level P_det
in the matrix are SURFACE QUERIES at the registry corner (never a direct sweep4
read) — consistent with the contract philosophy.

## R2 — emissions confound fixed (Fig 4a)
The emissions total was summed over the SCORED archetypes: D0 summed 4, D2 summed 2
(machine/tool unscored under D2), so cross-detector totals were not comparable (the
"human 43->22" halving was the archetype COUNT, not a detector effect). Fixed:
emissions + latency are now over the COMMON set {air-leak, coolant} in every cell.
Now gated rises 32->42 kg with the D0->D2 upgrade (correct direction), human is flat
~22 (detector-independent), and the within-D2 1.9x (gated 42 vs human 21) stands.

## R3 — fault-free wrong-ACTION per policy (cost-of-autonomy)
A false alarm carries LOW attribution confidence, so the contract's B.5 rule caps
its sigma at DEGRADED -> gated ESCALATES it (0 false actions). naive acts on every
false alarm. Over 14 clean days: measured FA -> naive D2 = 0.81, gated = 0; at Paper
1's defended 0.05/h budget -> naive = 16.8 false actions/14d, gated = 0. This is the
cost-of-autonomy counterpart to the price-of-rigor count.

## R4 — figure craft
Fig 2 area annotation + domain caveat moved inside the plot (no clip); Fig 4 suptitle
shortened; Fig 4b carries a caveat that naive's 0 h latency is unaudited action
(~70% wrong under D0). Fig 4a title states the common set.

## §5 sentence to bank
Because machine/tool miss rates are sub-floor bounds, naive's 0.70 is a conservative
LOWER bound — the honest headline is "at least 70% wrong under D0".
