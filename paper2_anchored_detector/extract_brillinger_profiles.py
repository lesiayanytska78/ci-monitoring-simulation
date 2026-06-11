"""
extract_brillinger_profiles.py
==============================
Regenerates `real_profiles.npz` from the Brillinger et al. (2025) CNC dataset,
used by energy_substrate_real.py for the Level-2 real-data validation.

The dataset is licensed CC BY-NC and is therefore NOT redistributed in this
repository. To reproduce the real-data validation:

  1. Download the dataset from Mendeley Data, DOI 10.17632/gtvvwmz7r7.2
     (Brillinger et al., 2025; CC BY-NC).
  2. Unzip it.
  3. Run this script, pointing it at the folder that contains the per-job raw
     JSON traces (the "Raw Datasets (.json)" tree):

        python extract_brillinger_profiles.py "/path/to/Raw Datasets (.json)"

It extracts the spindle drive-power channel (POWER|5), clips regenerative-braking
negatives to zero (consumption model), resamples to ~1 s, and writes
real_profiles.npz next to this script.
"""
import sys, os, glob, json
import numpy as np

SP_POW = 75        # column index of POWER|5 (spindle drive power) in HFData rows
BIN = 500          # ~500 Hz servo cycle -> ~1 s bins


def extract(path):
    files = [f for f in glob.glob(os.path.join(path, "**", "*.json"), recursive=True)
             if "config" not in os.path.basename(f).lower()]
    if not files:
        sys.exit(f"No .json job files found under: {path}\n"
                 f"Point the script at the 'Raw Datasets (.json)' folder of the dataset.")
    prof = {}
    for f in sorted(files):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        if "Payload" not in d:
            continue
        vals = []
        for blk in d["Payload"]:
            hf = blk.get("HFData")
            if not hf:
                continue
            for r in hf:
                if len(r) > SP_POW:
                    vals.append(r[SP_POW])
        if not vals:
            continue
        v = np.clip(np.array(vals, float), 0.0, None) / 1000.0   # regen-clip, W -> kW
        n = (len(v) // BIN) * BIN
        if n < BIN:
            continue
        name = os.path.splitext(os.path.basename(f))[0]
        prof[name] = v[:n].reshape(-1, BIN).mean(axis=1)
        print(f"  {name}: {len(prof[name])} s spindle profile "
              f"(no-load ~{np.percentile(prof[name],30):.2f} kW)")
    if not prof:
        sys.exit("Parsed files but found no spindle-power payloads.")
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "real_profiles.npz")
    np.savez(out, **prof)
    print(f"\nwrote {out} with {len(prof)} profiles")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit('usage: python extract_brillinger_profiles.py "<path to Raw Datasets (.json) folder>"')
    extract(sys.argv[1])
