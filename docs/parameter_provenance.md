# Parameter provenance

Every numeric parameter in the simulation carries one of three provenance tags,
matching the tags in the source code and the paper's Methods section:

- **`[ANCHORED]`** — fitted to a real measurement in the Brillinger et al. (2025) open CNC dataset (Mendeley Data, DOI 10.17632/gtvvwmz7r7.2, CC BY-NC).
- **`[LITERATURE]`** — taken from published sources cited in the paper; varied (SWEPT) in the sensitivity analysis.
- **`[ASSUMPTION]`** — engineering estimate; varied (SWEPT) in the sensitivity analysis.

---

## Module 1 — Energy substrate (`simulation/energy_substrate.py`)

| Parameter | Default | Provenance |
|---|---|---|
| Spindle no-load power | 0.9 kW | `[ANCHORED]` median of the no-load spindle level from two representative Brillinger job traces (0.80, 0.99 kW) |
| Cutting power increment | 3.0 kW | `[LITERATURE]` Gutowski et al. (2006); SWEPT |
| Auxiliary base load | 2.5 kW | `[LITERATURE]` Gutowski et al. (2006); Kara & Li (2011); SWEPT |
| Offline standby | 0.2 kW | `[ASSUMPTION]` |
| Cutting duty cycle | 0.55 | `[ASSUMPTION]` consistent with intermittent cutting in Brillinger traces; SWEPT |
| Relative noise | 0.05 | `[ASSUMPTION]` consistent with steady-signal variability; SWEPT |
| Throughput in production | 60 pieces/h | `[ASSUMPTION]` SWEPT |

Reference baseline power (auxiliary + spindle no-load): **P_b = 3.4 kW**. Detection-floor results are reported both as absolute power and as a fraction of P_b.

A note on regenerative braking: the Brillinger servo-drive traces show large negative-power transients during spindle deceleration, consistent with regenerative braking. For an energy-*consumption* model these are clipped to zero (regenerated energy is dissipated in a braking resistor rather than recovered).

---

## Module 2 — Carbon layer (`simulation/carbon_layer.py`)

| Parameter | Default | Provenance |
|---|---|---|
| Grid emission factor (e) | 0.230 kg CO₂e/kWh | `[LITERATURE]` EEA (2023), EU-27 average ~2023. Results are reported in relative terms, so the precise value sets only the absolute emissions scale and does not affect any detection result |
| CI rolling/estimation window | 15 min | `[ASSUMPTION]` common MES reporting cadence; SWEPT |
| Diurnal EF amplitude (optional time-varying mode) | ±0.30 | `[ASSUMPTION]` |

Monitoring signal: rolling CI per piece = (Σ emissions in window) / (Σ pieces in window), defined only where the window contains ≥1 piece and ≥25% of the window is in PRODUCTION state.

---

## Module 3 — Anomaly model (`simulation/anomaly_model.py`)

| Archetype | Magnitude | Duration | Onset | Channel | Provenance |
|---|---|---|---|---|---|
| Compressed-air leak | 1.5 kW | 240 min | Ramp (120 s) | Auxiliary | `[LITERATURE]` DOE (2003); Saidur et al. (2010) |
| Machine left on | 0.9 kW | 60 min | Step | Spindle | `[ANCHORED]` Brillinger no-load level |
| Tool wear | 0.8 kW | 120 min | Ramp (3600 s) | Spindle | `[LITERATURE]` magnitude from Shao et al. (2004); ramp time illustrative, swept in §4.7 |
| Coolant pump fault | 1.2 kW | 180 min | Step | Auxiliary | `[ASSUMPTION]` auxiliary-load scale |

All archetype parameters are illustrative starting points; magnitude, duration, and onset profile are SWEPT in the sensitivity analysis. An anomaly is additive excess power without additional output — the discriminating signature CI normalisation is designed to detect.

---

## Module 4 — Monitoring layer (`simulation/monitoring.py`)

| Parameter | Default | Provenance |
|---|---|---|
| Meter sampling interval | 60 s | `[ASSUMPTION]` typical MES/SCADA cadence; SWEPT 30 s–15 min |
| Meter accuracy | ±1% of reading | `[LITERATURE]` IEC 61557-12 Class 1 |
| Threshold type | relative | `[ASSUMPTION]` SWEPT (absolute / relative / statistical) |
| Relative threshold | +25% of baseline | `[ASSUMPTION]` SWEPT |
| Statistical threshold | mean + 3σ | `[ASSUMPTION]` SWEPT |
| Baseline window | 60 min | `[ASSUMPTION]` SWEPT |
| CI estimation window | 15 min | `[ASSUMPTION]` independent of meter cadence; SWEPT |
| Warning persistence | 3 consecutive samples | `[LITERATURE]` industrial-alerting practice |
| Critical persistence | 9 consecutive samples | `[LITERATURE]` industrial-alerting practice |

---

## Module 5 — Sensitivity harness (`simulation/sensitivity.py`)

Nine sweeps, 4,356 total runs. See the paper's §3.6 table and the `data/` CSVs for the exact ranges, seed counts, and per-run results.
