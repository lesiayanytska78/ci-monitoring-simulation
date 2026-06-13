#!/usr/bin/env python3
"""
make_claims_manifest.py
=======================
Single source of truth for every number that appears in `architecture.html`.

The interactive architecture diagram embeds a few headline figures (the demo
detection latency, the false-positive count, the run/sweep totals). To stop
those numbers drifting away from the code the way hand-typed claims always do,
they are *generated* here from exactly the same sources as the paper figures:

  * the demo-seed result is computed by running the `cimonitoring` engine, and
  * the run/sweep totals are read from the released CSVs in `data/`.

Running this script:
  1. recomputes the claims,
  2. writes them to `claims_manifest.json`, and
  3. injects them into every `<span data-claim="KEY">…</span>` in
     `architecture.html`.

A test in `tests/test_all.py` re-runs `compute_claims()` and asserts the spans
still match — so CI fails if the diagram is ever out of step with the code.

Usage:  python make_claims_manifest.py
"""
from __future__ import annotations
import csv
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def _demo_claims() -> dict:
    """Run the documented quickstart demo and return its measured outcome."""
    import cimonitoring as ci

    sub = ci.simulate_work_center(ci.Config(seed=1))
    specs = [ci.AnomalySpec(
        onset_hour=12, duration_minutes=240, magnitude_kw=2.0,
        onset_profile="ramp", onset_ramp_seconds=3600,
        affects="spindle", label="slow ramp")]
    sub = ci.inject_anomalies(sub, ci.AnomalyConfig(specs))
    ef = ci.CarbonConfig().static_emission_factor_kg_per_kwh

    deployed = ci.run_monitoring(sub, ci.MonitorConfig(), ef)
    anchored = ci.run_monitoring_anchored(
        sub, ci.AnchoredMonitorConfig(detector="anchored_cusum"), ef)

    ev_anc = ci.evaluate(anchored, sub, specs)
    ev_dep = ci.evaluate(deployed, sub, specs)
    f_anc = ev_anc["per_fault"][0]
    f_dep = ev_dep["per_fault"][0]

    return {
        "demo_warning_latency_min": int(round(f_anc["warning_latency_min"])),
        "demo_critical_latency_min": int(round(f_anc["critical_latency_min"])),
        "demo_false_positives": int(ev_anc["false_positive_warnings"]),
        "deployed_detected": bool(f_dep["warning_detected"]),
    }


def _data_claims(repo_root: str) -> dict:
    """Count released simulation runs and sweeps directly from data/."""
    paths = sorted(glob.glob(os.path.join(repo_root, "data", "sweep*.csv")))
    total = 0
    for p in paths:
        with open(p, newline="") as fh:
            rows = sum(1 for _ in csv.reader(fh))
        total += max(rows - 1, 0)  # subtract header
    return {"n_runs": total, "n_sweeps": len(paths)}


def compute_claims(repo_root: str = HERE) -> dict:
    """Compute every claim from the authoritative sources (engine + CSVs)."""
    claims = {}
    claims.update(_demo_claims())
    claims.update(_data_claims(repo_root))
    return claims


def _fmt(key: str, value) -> str:
    """How a claim value is rendered in the HTML."""
    if key == "n_runs":
        return f"{value:,}"          # thousands separator, e.g. 4,356
    return str(value)


def inject_into_html(claims: dict, html_path: str) -> int:
    """Fill every <span data-claim="KEY">…</span> with the computed value."""
    with open(html_path, encoding="utf-8") as fh:
        html = fh.read()

    n = 0
    for key, value in claims.items():
        rendered = _fmt(key, value)
        pattern = re.compile(
            r'(<span data-claim="' + re.escape(key) + r'">)(.*?)(</span>)')
        html, count = pattern.subn(lambda m: m.group(1) + rendered + m.group(3), html)
        n += count

    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return n


def parse_html_claims(html_path: str) -> dict:
    """Read the values currently rendered in the HTML's data-claim spans."""
    with open(html_path, encoding="utf-8") as fh:
        html = fh.read()
    out = {}
    for m in re.finditer(r'<span data-claim="([^"]+)">(.*?)</span>', html):
        key, raw = m.group(1), m.group(2)
        out.setdefault(key, raw.replace(",", ""))
    return out


def main() -> None:
    claims = compute_claims(HERE)
    manifest_path = os.path.join(HERE, "claims_manifest.json")
    html_path = os.path.join(HERE, "architecture.html")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(claims, fh, indent=2)
        fh.write("\n")
    filled = inject_into_html(claims, html_path)
    print("claims:", claims)
    print(f"wrote {manifest_path}")
    print(f"filled {filled} data-claim span(s) in {os.path.basename(html_path)}")


if __name__ == "__main__":
    main()
