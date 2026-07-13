# env/data/ — grid carbon-intensity snapshot

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Pinned grid carbon-intensity traces for reproducible runs.

**Attribution (required, CC BY 4.0):**

> Contains data from the Carbon Intensity API, © National Energy System Operator
> (NESO), licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).
> Source: https://carbonintensity.org.uk. Capture date: <YYYY-MM-DD>.

Attribute NESO **by name only** — do not reproduce the NESO logo or word mark.
`grid_ci_snapshot.json` is `.gitignore`d by default (regenerate via `env/grid_ci.py`);
commit a pinned snapshot with its capture date and `snapshot_sha256` when you want a
frozen reproducibility artifact. The offline synthetic fallback carries no NESO data
and no attribution requirement.
