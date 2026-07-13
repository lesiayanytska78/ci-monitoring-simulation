"""Generate PLACEHOLDER detectability-surface CSVs for D0 and D2.

These files stand in for the archived Paper 1 / Paper 2 detection-rate CSVs
(Sweeps 7-9, boundary sweep, Fig 8 surface, D0/D2 severity generalization).
The grid values reproduce the B.1 anchor table EXACTLY at grid nodes:

    D0(s=0.47, rho=0.033) = 0.80    # boundary sweep (floor at fast onset)
    D0(s=0.59, rho=0.43)  = 0.80    # inertia sigmoid knee   (2 kW = 0.59*Pb)
    D0(s=0.59, rho=0.69)  = 0.50    # inertia sigmoid midpoint
    D0(s=0.59, rho=1.00)  = 0.24
    D0(s=0.59, rho=2.00)  = 0.04
    D0(s=0.24, rho=1.00)  = 0.10    # tool-wear default -> characterized-blind
    D2(s>=0.10, any rho)  ~ 0.99    # event-anchored, onset-ratio-independent

Placeholder CIs are ZERO-WIDTH (p_det_lo95 == p_det) so the conservative
lower-bound gate reproduces the anchor tiers in tests. The real archived CSVs
carry 95% bootstrap CI lower bounds; drop them in and delete this generator.
"""
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Lesia Yanytska
import csv
import os

RHO = [0.033, 0.10, 0.20, 0.43, 0.55, 0.69, 0.90, 1.00, 1.30, 2.00]
S   = [0.10, 0.20, 0.24, 0.35, 0.44, 0.47, 0.59, 0.70, 0.88, 1.00, 1.18]

# D0 point estimates: monotone increasing in s (down), decreasing in rho (across).
# Anchor cells are exact (see docstring).
D0 = {
    0.10: [0.20, 0.18, 0.16, 0.12, 0.10, 0.08, 0.06, 0.05, 0.03, 0.01],
    0.20: [0.34, 0.32, 0.29, 0.22, 0.18, 0.14, 0.10, 0.08, 0.05, 0.02],
    0.24: [0.42, 0.40, 0.36, 0.27, 0.22, 0.17, 0.12, 0.10, 0.06, 0.02],
    0.35: [0.60, 0.57, 0.52, 0.40, 0.32, 0.25, 0.18, 0.15, 0.09, 0.03],
    0.44: [0.76, 0.73, 0.68, 0.55, 0.46, 0.36, 0.27, 0.22, 0.13, 0.05],
    0.47: [0.80, 0.78, 0.73, 0.60, 0.50, 0.40, 0.30, 0.25, 0.15, 0.05],
    0.59: [0.86, 0.85, 0.84, 0.80, 0.66, 0.50, 0.33, 0.24, 0.12, 0.04],
    0.70: [0.92, 0.91, 0.89, 0.85, 0.75, 0.62, 0.45, 0.36, 0.20, 0.07],
    0.88: [0.97, 0.96, 0.95, 0.92, 0.86, 0.77, 0.62, 0.53, 0.33, 0.12],
    1.00: [0.99, 0.98, 0.97, 0.95, 0.91, 0.84, 0.72, 0.64, 0.43, 0.17],
    1.18: [1.00, 0.99, 0.99, 0.97, 0.95, 0.90, 0.81, 0.74, 0.55, 0.25],
}

# D2 event-anchored: ~100% for s >= 0.10 across all rho (slack floor at 0.10*Pb).
D2_VAL = 0.99


def _rows(detector, table_lookup):
    rows = []
    for s in S:
        for j, rho in enumerate(RHO):
            p = table_lookup(s, j)
            rows.append(dict(
                detector=detector, s=s, rho=rho,
                p_det=round(p, 4), p_det_lo95=round(p, 4),  # zero-width placeholder CI
                n_seeds=200, source="PLACEHOLDER - replace with archived Paper1/2 CSV",
            ))
    return rows


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    d0_rows = _rows("D0", lambda s, j: D0[s][j])
    d2_rows = _rows("D2", lambda s, j: D2_VAL)  # s>=0.10 for all grid rows
    for name, rows in [("p_det_D0.csv", d0_rows), ("p_det_D2.csv", d2_rows)]:
        with open(os.path.join(here, name), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["detector", "s", "rho", "p_det",
                                              "p_det_lo95", "n_seeds", "source"])
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {name}: {len(rows)} rows")


if __name__ == "__main__":
    main()
