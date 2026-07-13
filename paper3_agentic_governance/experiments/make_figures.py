"""experiments/make_figures.py — Phase 3 figures from the REAL surface (C.4, audited)."""
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Lesia Yanytska
from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml
from matplotlib.colors import ListedColormap, BoundaryNorm

from contract.governance import EpistemicContract, sigma_from_pdet
from contract.surface import DetectabilitySurface

HERE = os.path.dirname(os.path.abspath(__file__))
FIGDIR = os.path.join(os.path.dirname(HERE), "figures")
os.makedirs(FIGDIR, exist_ok=True)
TIER = ["#dcdcdc", "#e8a87c", "#f4d58d", "#bdd7a3"]
POLS, DETS = ["naive", "gated", "human"], ["D0", "D2"]


def _registry():
    with open(os.path.join(os.path.dirname(HERE), "contract", "fault_registry.yaml")) as f:
        return {a["name"]: a for a in yaml.safe_load(f)["archetypes"]}


def _results():
    return list(csv.DictReader(open(os.path.join(HERE, "results_phase3.csv"))))


def _cell(rows, det, pol, key):
    return float(next(r for r in rows if r["detector"] == det and r["policy"] == pol)[key])


def fig_autonomy_map():
    surf = DetectabilitySurface(); C = EpistemicContract(); reg = _registry()
    rhos = np.linspace(0.033, 2.0, 240); sevs = np.linspace(0.10, 1.20, 240)
    def grid(det):
        Z = np.zeros((len(sevs), len(rhos)), int)
        for i, s in enumerate(sevs):
            for j, r in enumerate(rhos):
                d = surf.query(s, r, det)
                Z[i, j] = int(sigma_from_pdet(d.p_det_lo95, C.cuts)) if d.in_envelope else 0
        return Z
    Z0, Z2 = grid("D0"), grid("D2")
    a0, a2 = float(np.mean(Z0 >= 2)), float(np.mean(Z2 >= 2))
    cmap = ListedColormap(TIER); norm = BoundaryNorm([-.5, .5, 1.5, 2.5, 3.5], cmap.N)
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.pcolormesh(rhos, sevs, Z0, cmap=cmap, norm=norm, shading="auto")
    ax.contour(rhos, sevs, (Z2 >= 2).astype(int), levels=[0.5], colors="#2d5b2d", linewidths=2.4, linestyles="--")
    for name, m in [("compressed_air_leak", "o"), ("coolant_pump_fault", "^"),
                    ("machine_left_on", "s"), ("tool_wear", "x")]:
        fc = reg[name]
        ax.scatter(fc["onset_ratio_nominal"], fc["severity_frac_nominal"], c="#111", marker=m, s=70, zorder=5)
        ax.annotate(name.replace("_", " "), (fc["onset_ratio_nominal"], fc["severity_frac_nominal"]),
                    textcoords="offset points", xytext=(8, 4), fontsize=8)
    ax.axhline(0.2941, color="#555", lw=0.8, ls=":")
    ax.text(1.35, 0.305, "measured floor 0.294·Pb", fontsize=7, color="#555")
    ax.set_xscale("log")
    ax.set_xlabel("onset-to-window ratio  ρ = τ_onset / W_b  (log)")
    ax.set_ylabel("fault severity  s = Δ / P_b")
    ax.set_title("Fig. 2 — Autonomy map from the real D0 surface (σ tiers), D2 σ≥2 frontier")
    handles = [plt.Rectangle((0, 0), 1, 1, fc=c) for c in TIER]
    ax.legend(handles + [plt.Line2D([0], [0], color="#2d5b2d", ls="--", lw=2.4)],
              ["σ=0 blind", "σ=1 degraded", "σ=2 transition", "σ=3 reliable", "D2 σ≥2 frontier"],
              loc="upper right", fontsize=8, framealpha=0.9)
    ax.text(0.045, 1.11, f"autonomy area (σ≥2):  D0 = {a0:.0%}  →  D2 = {a2:.0%}", fontsize=9.5, weight="bold")
    ax.text(0.045, 1.05, "(fraction of the characterized envelope, log-ρ measure)",
            fontsize=7.5, style="italic", color="#444")
    fig.tight_layout(); fig.savefig(os.path.join(FIGDIR, "fig2_autonomy_map_real.png"), dpi=140, bbox_inches="tight"); plt.close(fig)
    print(f"wrote fig2 ({a0:.0%} -> {a2:.0%})")


def fig_policy_comparison():
    rows = _results(); C = EpistemicContract(); reg = _registry()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.3)); w = 0.35
    for k, det in enumerate(DETS):
        vals = [_cell(rows, det, p, "wrong_rate") for p in POLS]
        los = [v - _cell(rows, det, p, "wrong_lo") for v, p in zip(vals, POLS)]
        his = [_cell(rows, det, p, "wrong_hi") - v for v, p in zip(vals, POLS)]
        x = np.arange(len(POLS)) + k * w
        ax1.bar(x, vals, w, label=det, yerr=[los, his], capsize=4)
        for xi, v in zip(x, vals):
            ax1.text(xi, v + 0.015, f"{v:.2f}", ha="center", fontsize=8)
    ax1.set_xticks(np.arange(len(POLS)) + w / 2); ax1.set_xticklabels(POLS)
    ax1.set_ylim(0, 0.8); ax1.set_ylabel("wrong-action rate (contamination corollary, 4 archetypes)")
    ax1.set_title("(a) wrong autonomous actions [95% CI]"); ax1.legend(title="detector")
    covv = [sum(int(C.standing_grant(reg[n], "defer_job", d).autonomy) >= 2 for n in reg) for d in DETS]
    ax2.bar(DETS, covv, color=["#8aa1b1", "#2d5b2d"])
    for i, v in enumerate(covv):
        ax2.text(i, v + 0.03, f"{v} of 4", ha="center", fontsize=11)
    ax2.set_ylim(0, 4); ax2.set_ylabel("archetypes granted A≥2 (of 4)")
    ax2.set_title("(b) autonomy coverage: D0 → D2")
    fig.tight_layout(); fig.savefig(os.path.join(FIGDIR, "fig3_policy_comparison.png"), dpi=140); plt.close(fig)
    print("wrote fig3")


def fig_economic():
    rows = _results()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.3)); w = 0.25
    for k, pol in enumerate(POLS):
        em = [_cell(rows, d, pol, "emissions_kg") for d in DETS]
        la = [_cell(rows, d, pol, "mean_latency_h") for d in DETS]
        x = np.arange(len(DETS)) + k * w
        ax1.bar(x, em, w, label=pol); ax2.bar(x, la, w, label=pol)
        for xi, v in zip(x, em): ax1.text(xi, v + 0.5, f"{v:.0f}", ha="center", fontsize=8)
        for xi, v in zip(x, la): ax2.text(xi, v + 0.05, f"{v:.1f}", ha="center", fontsize=8)
    for ax, ttl, yl in [(ax1, "(a) emissions avoided (common set {air, coolant})", "kg CO₂e avoided"),
                        (ax2, "(b) action latency", "mean latency (h)")]:
        ax.set_xticks(np.arange(len(DETS)) + w); ax.set_xticklabels(DETS)
        ax.set_title(ttl, fontsize=10); ax.set_ylabel(yl); ax.legend(title="policy", fontsize=8)
    ax2.annotate("naive: 0 h but ~70% wrong under D0\n(unaudited action)", xy=(0.0, 0.05),
                 xytext=(0.05, 1.7), fontsize=7.5, color="#8a0000",
                 arrowprops=dict(arrowstyle="->", color="#8a0000", lw=0.8))
    fig.suptitle("Fig. 4 — Autonomy's benefit is unlocked by sensor fidelity (gated vs human, see D2)", fontsize=10.5)
    fig.tight_layout(rect=[0, 0, 1, 0.95]); fig.savefig(os.path.join(FIGDIR, "fig4_economic.png"), dpi=140, bbox_inches="tight"); plt.close(fig)
    print("wrote fig4")


if __name__ == "__main__":
    fig_autonomy_map(); fig_policy_comparison(); fig_economic()
