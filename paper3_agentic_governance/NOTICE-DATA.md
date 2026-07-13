<!-- SPDX-License-Identifier: MIT -->
<!-- SPDX-FileCopyrightText: 2026 Lesia Yanytska -->

# Third-party and first-party data notices

This repository mixes licenses by design (REUSE 3.3 / SPDX):

- **Code** — MIT (`LICENSE`, `LICENSES/MIT.txt`), with per-file SPDX MIT headers.
- **First-party data** (detectability surfaces derived from the author's Papers 1–2
  characterization campaigns, under `contract/data/`) — **CC BY 4.0**
  (`LICENSES/CC-BY-4.0.txt`).
- **Third-party data** — attributed below under its own license.

> **Zenodo note:** a single Zenodo deposit cannot mix licenses. On release, declare
> the dominant license in the deposit metadata and keep these per-folder notices for
> the rest, or separate code and data logically. Release paper 3 as a **new version
> under the existing concept DOI 10.5281/zenodo.21268863**.

## NESO Carbon Intensity API — CC BY 4.0

> Contains data from the Carbon Intensity API, © National Energy System Operator
> (NESO), licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).
> Source: https://carbonintensity.org.uk. Data captured on <YYYY-MM-DD> (record the
> capture date with each snapshot).

Notes: the API is free and key-free. Attribute NESO **by name only** — do **not**
reproduce the NESO logo or word mark (the Terms require prior written approval for
mark use). National `/intensity` data includes forecast **and** actual; regional data
is forecast-only. The separate NESO **Data Portal bulk CSVs** carry a *different*
"NESO Open Data Licence," not CC BY 4.0 — if you ever pull those instead of API JSON,
check that license separately.

## Brillinger et al. 2025 CNC machining dataset — CC BY 4.0

> Brillinger, M. (2025). CNC machining dataset (geometry, NC code, high-frequency
> energy). Mendeley Data, V2. DOI: 10.17632/gtvvwmz7r7.2. Licensed under CC BY 4.0.
> Hosted by FH Joanneum GmbH. Companion: *Data in Brief*, DOI 10.1016/j.dib.2025.111814.

**License correction (carry-over from Paper 2).** Paper 2's text refers to this
dataset as **CC BY-NC**. That is an error: the Mendeley Data landing page states
**CC BY 4.0**. CC BY 4.0 is *more* permissive (redistribution and commercial use with
attribution are permitted), so no license was violated — but the Paper 2 record should
be corrected, and every reference in this repo uses the correct **CC BY 4.0**.
