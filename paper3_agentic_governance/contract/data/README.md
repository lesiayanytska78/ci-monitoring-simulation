# contract/data/ — detectability surfaces (first-party data, CC BY 4.0)

<!-- SPDX-License-Identifier: CC-BY-4.0 -->
<!-- SPDX-FileCopyrightText: 2026 Lesia Yanytska -->

These CSVs are **first-party data** derived from the author's Papers 1–2
characterization campaigns (boundary sweep, inertia sigmoid, Fig-8 surface;
D0/D2 severity generalization). Licensed **CC BY 4.0** (`../../LICENSES/CC-BY-4.0.txt`).

**Current files are PLACEHOLDERS** (`_build_placeholder_surface.py`) that reproduce
the B.1 anchor table exactly at grid nodes with **zero-width CIs**. Replace with the
archived Zenodo CSVs before the public push (or immediately after — the unit tests are
designed to flag any discrepancy):

- `p_det_D0.csv`, `p_det_D2.csv` <- archived detection-rate CSVs (real 95% bootstrap
  CI lower bounds). Priority: verify the five hand-entered step-onset rows against
  **Sweep 4**.
- `roc_sweep3.csv` <- drop in so `governance.derive_sigma_cutpoints()` switches the
  sigma=2 / sigma=1 cut-points from fallback constants to **ROC-derived** operating points.
