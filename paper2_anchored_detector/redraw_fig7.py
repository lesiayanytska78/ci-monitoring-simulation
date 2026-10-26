"""
redraw_fig7.py  (Paper 2 revision, §4.7)
========================================
Redraw Figure 7 (targeted 2-D cadence x health-gate) from the reconstructed
repo data (results/cadence_gate_summary.csv) with variance-decomposition
subtitles read from results/cadence_gate_decomp.csv, so the figure cells AND
the panel labels match the released code and the reconciled manuscript text:
  detection: gate 97% . cadence 0.6% . interaction 2%
  latency  : gate 90% . cadence 8.5% . interaction 1%
Writes figures/fig_cadence_gate.png.
"""
from __future__ import annotations
import os, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

R, F = "results", "figures"
os.makedirs(F, exist_ok=True)
plt.rcParams.update({"font.size": 10, "figure.dpi": 150})

g = pd.read_csv(f"{R}/cadence_gate_summary.csv")
d = pd.read_csv(f"{R}/cadence_gate_decomp.csv").set_index("outcome")

cads = sorted(g.cadence_min.unique())                 # 30,60,120,240 (rows)
gates = sorted(g.gate.unique())                        # 0.05 .. 0.5  (cols)
row_lab = [f"{int(c)}min" for c in cads]
col_lab = [f"{x:g}" for x in gates]

det = np.full((len(cads), len(gates)), np.nan)
lat = np.full((len(cads), len(gates)), np.nan)
for _, r in g.iterrows():
    i = cads.index(r.cadence_min); j = gates.index(r.gate)
    det[i, j] = r.fast_det
    lat[i, j] = r.slow_latency_min

dd = d.loc["fast_fault_detection"]; dl = d.loc["slow_fault_latency"]
sub_a = (f"gate {dd.gate_main_pct:.0f}%  ·  cadence {dd.cadence_main_pct:.1f}%"
         f"  ·  interaction {dd.interaction_pct:.0f}%")
sub_b = (f"gate {dl.gate_main_pct:.0f}%  ·  cadence {dl.cadence_main_pct:.1f}%"
         f"  ·  interaction {dl.interaction_pct:.0f}%")

fig, (a1, a2) = plt.subplots(1, 2, figsize=(13.2, 5.0))

# (a) fast-fault detection
im1 = a1.imshow(det, cmap="RdYlGn", vmin=0.0, vmax=1.0, aspect="auto")
a1.set_title("(a) Fast-fault detection (re-anchoring hazard)\n" + sub_a, fontsize=11)
for i in range(len(cads)):
    for j in range(len(gates)):
        if not np.isnan(det[i, j]):
            a1.text(j, i, f"{det[i, j]:.2f}", ha="center", va="center", fontsize=8, color="#222")
cb1 = fig.colorbar(im1, ax=a1, fraction=0.046, pad=0.04); cb1.set_label("detection")

# (b) slow-fault latency
im2 = a2.imshow(lat, cmap="viridis", aspect="auto")
a2.set_title("(b) Slow-fault median latency (min)\n" + sub_b, fontsize=11)
for i in range(len(cads)):
    for j in range(len(gates)):
        if not np.isnan(lat[i, j]):
            a2.text(j, i, f"{lat[i, j]:.0f}", ha="center", va="center", fontsize=8, color="w")
cb2 = fig.colorbar(im2, ax=a2, fraction=0.046, pad=0.04); cb2.set_label("latency (min)")

for ax in (a1, a2):
    ax.set_xticks(range(len(gates))); ax.set_xticklabels(col_lab)
    ax.set_yticks(range(len(cads))); ax.set_yticklabels(row_lab)
    ax.set_xlabel("health-gate fraction"); ax.set_ylabel("re-anchoring cadence")

fig.suptitle("Targeted 2-D cadence × gate: the response is gate-dominated "
             "(nonlinear threshold), the interaction is secondary", fontsize=12)
fig.tight_layout(rect=[0, 0, 1, 0.96])
fig.savefig(f"{F}/fig_cadence_gate.png", bbox_inches="tight")
plt.close(fig)
print("wrote figures/fig_cadence_gate.png")
print("  (a)", sub_a)
print("  (b)", sub_b)
