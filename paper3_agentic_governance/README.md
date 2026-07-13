# paper3_agentic_governance

Proof-of-concept for **Paper 3 — "Measurement-bounded autonomy: characterized
detection limits as the governance boundary for carbon-intelligent energy agents
in manufacturing execution systems."**

> **Thesis.** An energy agent may act autonomously only where its monitoring
> layer's detection performance has been *characterized* as adequate, and must
> escalate to a human where that layer is characterized as blind. The autonomy
> boundary is therefore *measurement-derived*, not a qualitative risk judgment —
> and improving the detector (D0 → D2) is the legitimate way to widen the
> autonomous region, never loosening the governance gate.

This repo lives as a new folder inside the existing `ci-monitoring-simulation`
repo (CI Project), preserving the Papers 1–3 lineage in one citable artifact.

## Status

| Phase | Scope | State |
|------|-------|-------|
| **1 — Contract core** | `surface.py`, `governance.py`, fault registry, unit tests | ✅ built, **26 tests green** |
| **2 — Env + agents** | `plant.py`, `grid_ci.py`, deterministic contract-net agents, smoke test | ✅ built, **thesis reproduced** |
| **1.2 — Real-data wiring + audit** | real surface; envelope axioms; dual-corner; measurement-demand | ✅ done, **36 tests green**; σ-cutpoints #4 OPEN |
| **3 — Full experiment** | 200-seed matrix; metrics + bootstrap CIs; Fig 2 (autonomy map) + Fig 3 from real data | ✅ done |
| 4 — Paper | §3/§4 from the frozen spec, §5 from Phase-3 results | ⏳ |
| 5 — LLM layer + release | LLM proposer + MCP server + Zenodo `v3.0.0` | ⏳ (optional, never blocks) |

## Quickstart

```bash
pip install -r requirements.txt
python -m pytest tests/ -q          # 26 passed
python experiments/smoke_test.py    # prints the acceptance table; exit 0 on PASS
```

Smoke-test acceptance (the AUDITED thesis, running on real data — see SPEC_NOTES.md):

```
naive / D0 / tool-wear -> acts on a CONTAMINATED CI signal (silent alarm)
gated / D0 / coolant   -> A=1 ESCALATE  ->  gated / D2 / coolant -> A=3 acted   (MEASURED recovery)
gated / D2 / tool-wear -> A=0 ESCALATE [measurement_demand]  (below D2's measured floor: refuse + demand)
RESULT: PASS - audited thesis reproduced
```

D2 recovers the two archetypes inside its measured envelope (air leak, coolant) and
issues a measurement demand for the two below it (tool wear, machine-left-on).

## Module map

```
contract/                 ← Phase 1 (the paper's contribution, testable alone)
  surface.py              P_det^d(s, ρ) with CI lower bounds; envelope=0 outside; log-ρ interp
  governance.py           σ (B.2) · α w/ ISA-95 tags + L2 cap (B.3) · A=min(σ,α) (B.4)
                          · ex-ante standing grants + ex-post gating (B.5) · payloads (B.6)
  fault_registry.yaml     Paper 1 Table 3 archetypes (Pb = 3.4 kW)
  data/*.csv              REAL detectability surface (build_real_surface.py from _archive/)
env/                      ← Phase 2 (documented seam for real Module 1–4 code)
  plant.py                Substrate + D0 (rolling) / D2 (event-anchored) detector stand-ins
  grid_ci.py              UK NESO Carbon Intensity API loader + synthetic fallback + snapshot hash
agents/                   deterministic contract-net: energy_agent · production_agent · negotiation
experiments/smoke_test.py acute (air leak) vs blind (tool wear) × {naive, gated} × {D0, D2}
tests/                    pin the B.1 anchor table and every contract invariant
```

## The two seams where your real work drops in

1. **Detectability CSVs** (`contract/data/p_det_D0.csv`, `p_det_D2.csv`) are
   placeholders that reproduce the B.1 anchor table exactly at grid nodes, with
   **zero-width CIs**. Replace with the archived Paper 1/2 detection-rate CSVs
   (real 95% bootstrap CI lower bounds); nothing else changes — `surface.py`
   already consumes the CI lower bound (`conservative=True`).
2. **Substrate + detectors** (`env/plant.py`) are faithful stand-ins behind the
   `Substrate` / `Detector` interfaces. Point them at the `cimonitoring/` package
   (`energy_substrate.py`, `monitoring.py` = D0, `monitoring_anchored.py` = D2);
   the agents and the contract consume only the interfaces.

## Design invariants (auditable)

- **σ cut-points:** `c3 = 0.80` inherited from Papers 1–2's reliable-detection
  convention (fixed); `c2 = 0.50`, `c1 = 0.20` are **derived from the ROC
  false-alarm operating points** via `derive_sigma_cutpoints()` (the single hook
  to wire the real ROC arrays — currently returns the spec defaults).
- **α ↔ ISA-95:** every action is tagged with its ISA-95 level. Level-2 actions
  (throttle / setpoint — a pure MES can only *request* them of the control
  layer) carry `requires_control_layer_ack=True` and are **capped at A ≤ 2**
  regardless of sensing fidelity. This mirrors the "LLM proposes, verifier
  disposes" invariant one layer up: *MES proposes, control layer disposes.*
- **Uncharacterized == blind:** outside the characterized envelope, `P_det := 0`.
  Every autonomy grant traces to an archived, seeded measurement (provenance
  string in the escalation payload).
- **Determinism:** no RNG, no wall-clock in the contract or agents; the grid-CI
  trace is pinned by a `snapshot_sha256`.

## Licensing (REUSE 3.3 / SPDX — `reuse lint` clean)

- **Code:** MIT (`LICENSE`, `LICENSES/MIT.txt`), per-file SPDX headers.
- **First-party data** (`contract/data/` detectability surfaces, from Papers 1–2):
  CC BY 4.0 (`LICENSES/CC-BY-4.0.txt`).
- **Third-party data** and full attribution: see `NOTICE-DATA.md`.
  - UK NESO Carbon Intensity API — CC BY 4.0, free, key-free. Attribute NESO by
    name only; **do not reproduce the NESO logo/word mark**. Record each snapshot's
    capture date. (The separate NESO Data Portal bulk CSVs use a *different*
    licence — not used here.)
  - Brillinger (2025) CNC dataset — Mendeley DOI 10.17632/gtvvwmz7r7.2, **CC BY 4.0**
    (corrects the CC BY-NC in Paper 2's text; CC BY 4.0 is more permissive, so no
    violation occurred).
- **Secrets:** the NESO API needs no key; any LLM-proposer key is env-var only and
  `.gitignore`d. No keys in code or history.

## Release checklist (before the public push)

- [ ] **Employer/IP clearance** — confirm the MIT/CC BY release is cleared under any
      Luxoft USA Inc. employment-IP policy. *(Blocking.)*
- [ ] Swap placeholder CSVs for archived Zenodo CSVs (or push clearly-labelled
      placeholders and verify immediately after — tests catch drift).
- [ ] Zenodo: release as a **new version under concept DOI 10.5281/zenodo.21268863**;
      cite the minted version DOI in the manuscript. Set `repository-code` in
      `CITATION.cff`.
- [ ] JMS is **single-blind** → an author-attributed public repo breaks no blinding,
      and Elsevier does not treat public code as prior publication. Submit promptly
      (no direct competitor to "measurement-bounded autonomy" has surfaced).

## Phase 5 spec-version notes (when the optional LLM/MCP layer is built)

- MCP: build against the **2025-11-25 stable** spec; design transport to migrate to
  the stateless **2026-07-28** model (RC — do not build against RC internals).
- SDK: pin **FastMCP 3.x** in `pyproject.toml`; record the tested MCP spec date.
- Security: cite **OWASP MCP Top 10 (beta)** + **NSA MCP guidance (May 2026)** in the
  threat model; scoped short-lived tokens, pinned tool descriptions, server allowlisting.
- LLM determinism: `temperature=0`/`seed` are best-effort only — make the layer
  reproducible by **caching proposer outputs** keyed on (prompt + pinned model
  snapshot + params) and recording `system_fingerprint`. Hedge all determinism claims.

## Phase 3 results (real surface, 200 seeds, spec C.4 — audited)

Emissions/latency are over the **common set {air-leak, coolant}** (scored under both
detectors) so cross-detector cells are comparable; wrong-action is over all scorable.

| detector | policy | wrong-action | emissions (common) | latency |
|---|---|---|---|---|
| D0 | naive | **≥0.70** [0.67,0.73] | 23 kg | 0 h |
| D0 | gated | 0.00 | 32 kg | 2.2 h |
| D0 | human | 0.00 | 22 kg | 4.3 h |
| D2 | naive | 0.00 *(2/4 scored)* | 42 kg | 0 h |
| D2 | gated | 0.00 | **42 kg** | **0 h** |
| D2 | human | 0.00 | 21 kg | 4.4 h |

- **Wrong-action** (contamination corollary, 4 archetypes): naive ≥ **70%** under D0
  (a conservative *lower* bound — machine/tool miss rates are sub-floor bounds);
  gated and human = 0.
- **Gated-vs-human (Fig 4):** under D2, gated = **42 kg @ 0 h** vs human = **21 kg @
  4.4 h** — ~1.9× emissions, no wait. gated rises 32→42 with the D0→D2 upgrade
  (correct direction); human is flat ~22 (detector-independent). Autonomy's economic
  benefit is *unlocked by sensor fidelity*.
- **Autonomy:** one → **two of four** archetypes granted A≥2; area 34%→82% of the
  characterized envelope (log-ρ measure, Fig 2).
- **Escalation:** D0 = 3 contract-correct; D2 = **2 price-of-rigor** (cost of
  conservatism, remedied by characterizing below the floor). Recall 1.00.
- **Fault-free (cost of autonomy):** gating routes false alarms to escalation via the
  low-attribution rule → **gated = 0 false actions**; naive = 0.81/14d at the measured
  D2 rate and **16.8/14d at Paper 1's 0.05/h budget**.
- **Robustness:** stable at the derived (θ₂=0.5, θ₁=0.181); the one swept-range flip
  (coolant D0) = a human-response horizon > ≈6.7 h — conservative, legible.

> Registry archetype severities (Paper 1 Table 3 defaults) differ from the archive's
> sweep4 (uniform 0.5 kW, a controlled comparison) — reconciled in SPEC_NOTES.

## Honest scope

This is a **mechanism demonstrator**, not a KPI validator. It shows the autonomy
boundary behaves as designed (correct escalation in the blind region, autonomy
recovered by a better detector); it does **not** claim plant-level OEE/energy
percentages. That discipline is inherited from Papers 1–2.
