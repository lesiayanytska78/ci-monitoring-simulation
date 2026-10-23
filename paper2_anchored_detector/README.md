# Anchored + residual-CUSUM detector — closing the inertia blind spot

Companion code for the method paper (Paper 2), which builds on the characterisation
study in the parent repository. The base study showed that rule-based, MES-embedded
carbon-intensity (CI) monitoring has a structural blind spot: it is nearly blind to
faults that develop slowly relative to its baseline-adaptation window (the
adaptive-baseline *inertia* trade-off). This folder contains the proposed detector
that closes that blind spot, plus the full evaluation.

## The method (`monitoring_anchored.py`, Module 4b)

Two literature-grounded mechanisms replace the deployed rolling-median reference:

1. **Event-anchored held baseline** — the baseline is pinned to a known-healthy MES
   event (shift start / post-maintenance / tool change) and held fixed until the next
   anchor, so slow drift accumulates against a stationary reference instead of a
   tracking one.
2. **Residual CUSUM** — a one-sided cumulative-sum test on the fractional residual
   `(CI − baseline)/baseline` (Page 1954; Lorden 1971), which integrates small
   persistent shifts the Shewhart-equivalent deployed rule is weakest against.

A **health gate** (`anchor_mode="periodic_gated"`) refuses to re-anchor onto an
elevated signal, preventing a re-anchor from re-absorbing an active fault.

Calibrated operating point (selected in `sweep_cusum_roc.py`): **k = 0.10, h = 1.0**,
chosen as the lowest-latency point whose false-alarm rate ≤ the deployed detector.

## Reproducing the figures

```bash
pip install numpy pandas matplotlib      # from the repo root requirements.txt
```

| Script | Produces | What it shows | ~runtime |
|---|---|---|---|
| `sweep_cusum_roc.py` | `results/cusum_roc.csv` | operating-point ROC (k, h selection) | ~30 s |
| `run_paper2_main.py` | `figures/fig_paper2_detection.png`, `figures/fig_paper2_anchor_modes.png` | D0 vs D1 vs D2 recovery (200 seeds, 95% CI); re-anchoring hazard + health-gating fix | ~8–15 min |
| `run_paper2_comparators.py` | `figures/fig_paper2_comparators.png` | ablation: identical CUSUM, different reference — tracking fails, fixed (anchor / model) succeeds | ~8–15 min |
| `run_paper2_multiseverity.py` | `figures/fig_paper2_multiseverity.png` | recovery generalises across fault severity (1–4 kW) | ~15 min |
| `run_paper2_realdata.py` | `figures/fig_paper2_realdata.png` | Level-2 validation on **real** Brillinger spindle power (requires `real_profiles.npz`, see below) | ~5 min |

Each `run_*` script reuses the parent repo's Module 1–5 (copied here so the scripts
run with no path setup) plus `monitoring_anchored.py`, and writes its summary CSV to
`results/`. Pre-computed summaries and figures are included.

> **Note on the ablation comparator `C2`:** in `run_paper2_comparators.py`, `C2` is a fixed *global-mean* reference (the median healthy CI, a single calibration constant). It is a deliberately minimal fixed reference used to test whether a fixed reference *per se* defeats inertia; it is **not** a feature-conditioned, Bhinge-style model-based residual, and should not be read as one.

## Major-revision robustness programme (Paper 2, revised)

The revised manuscript (§3.3–§3.4, §4.4, §4.7–§4.14) adds a statistical re-analysis
and an eleven-part robustness programme. Each experiment has a dedicated script that
imports a shared harness (`revision_common.py`) so the operating point (k = 0.10,
h = 1.0) and sensor model are identical to the headline runs. Every script writes a
`*_summary.csv`; committed copies are in `results/`, and the figures are in `figures/`.

| Script | §  | Produces | What it shows |
|---|---|---|---|
| `recompute_intervals.py` | 3.4 | `results/*_summary_binom.csv`, `false_alarm_poisson.csv` | Wilson + Clopper–Pearson detection intervals, exact (Garwood) Poisson false-alarm intervals (replacing the degenerate `[100,100]` bootstrap) |
| `redraw_figs.py` | 3.4 | `figures/fig_paper2_*_wilson.png` | headline figures redrawn with Wilson error bars |
| `run_calibration_independence.py` | 3.3 | `calibration_independence_summary.csv` | disjoint calibration/validation seed pools; 300-resample operating-point stability |
| `run_transfer_diagnostic.py` | 3.3 / 4.6 | `transfer_diagnostic_summary.csv` | real-substrate h-sweep → the domain-robust point (k = 0.10, h = 2.0) |
| `run_floor_scaling.py` | 4.4 | `floor_scaling_summary.csv` | detection floor Δ = k·P̄_b across regimes (invariant to throughput, scales with P̄_b) |
| `run_cadence_gate.py` | 4.7 | `cadence_gate_summary.csv`, `cadence_gate_decomp.csv` | targeted 2-D cadence×gate; variance decomposition (gate-dominated, interaction secondary) |
| `run_regime_change.py` | 4.8 | `regime_change_summary.csv` | legitimate regime changes: the two faces of the reference |
| `run_contaminated_anchor.py` | 4.9 | `contaminated_anchor_summary.csv` | biased-anchor sensitivity (loud low-bias / silent high-bias; the gate corrects < gate-fraction, preserves above) |
| `run_fault_forms.py` | 4.10 | `fault_forms_summary.csv` | six fault morphologies + randomised trajectories |
| `run_two_sided.py` | 4.11 | `two_sided_summary.csv` | one-sided CUSUM is blind to negative deviations; the two-sided variant recovers them |
| `run_interruptions.py` | 4.12 | `interruptions_summary.csv` | reset / hold / decay of the accumulator across production gaps |
| `run_regen_treatment.py` | 4.13 | `regen_treatment_summary.csv` | clip / net / half negative-power treatments (detection treatment-invariant) |
| `run_sensor_faults.py` | 4.14 | `sensor_faults_summary.csv` | bias / drift / frozen / dropout on the CI channel |

Two detector options were added to `monitoring_anchored.py` for the revision (both
default-off, so the headline results are unchanged):

- `cusum_two_sided=True` — a mirror negative-side accumulator for downward deviations (§4.11).
- `gap_strategy="reset"|"hold"|"decay"` (`decay_halflife_min`) — accumulator treatment across non-production gaps (§4.12).

The new fault morphologies (`step_ramp`, `intermittent`, `oscillatory`,
`partial_recovery`) are added to `anomaly_model.py` (§4.10).

## Real-data validation (Brillinger et al. 2025) — license note

The Level-2 validation replays **real measured CNC spindle power** as the substrate
(`energy_substrate_real.py`). The source dataset is licensed **CC BY-NC** and is
**not redistributed** here, nor is the derived `real_profiles.npz`. To reproduce:

```bash
# 1. download the dataset: Mendeley Data, DOI 10.17632/gtvvwmz7r7.2 ; unzip it
# 2. regenerate the profiles:
python extract_brillinger_profiles.py "/path/to/Raw Datasets (.json)"
# 3. run the real-data sweep:
python run_paper2_realdata.py
```

The Level-1 calibration validation (`results/brillinger_validation.csv`,
`figures/fig_brillinger_validation.png`) confirms the substrate's anchored values
against the same dataset: real no-load spindle power ≈ 0.90 kW (model anchor 0.90 kW),
regenerative-braking transients to ~−20 kW, and noise within the modelled range.

## Headline results (semi-synthetic substrate, 2 kW unless noted)

- At onset-ratio 1.0, the deployed detector falls to **24% [18–30]** detection while
  the proposed detector holds **100% (95% Wilson CI 98.1–100%)**, at a false-alarm rate
  of 0.0025/h (6 warning-starts over 2,447.5 production-h; 95% Poisson CI 0.0009–0.0053).
- The ablation shows a rolling-median CUSUM (no anchor) still collapses (32% at ratio
  2.0): the **fixed reference**, not the CUSUM, is the mechanism — and a model-based
  residual reference works equally well, covering both design responses named in the
  base paper.
- The recovery holds across severities 1–4 kW; the proposed detector also lowers the
  detection floor (catches 1 kW faults the deployed detector misses).
- On a **real** spindle-power substrate the same collapse-and-recovery pattern holds.

## Licence

Code: MIT (see repository root `LICENSE`). Result CSVs/figures: CC BY 4.0.
The Brillinger dataset and any profiles derived from it remain under the upstream
CC BY-NC licence and are not included here.
