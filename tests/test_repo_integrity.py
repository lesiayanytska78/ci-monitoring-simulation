"""Repository-integrity checks: the released data loads, and the simulation
modules shared between `simulation/` and `paper2_anchored_detector/` have not
drifted apart."""
import pathlib
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHARED = ["energy_substrate.py", "carbon_layer.py", "anomaly_model.py",
          "monitoring.py", "sensitivity.py"]


def test_released_csvs_load_and_nonempty():
    # the nine per-run sweep CSVs each carry a 'seed' column
    sweeps = sorted((ROOT / "data").glob("sweep*.csv"))
    assert len(sweeps) >= 9, "expected the nine released sweep CSVs"
    for csv in sweeps:
        df = pd.read_csv(csv)
        assert len(df) > 0, f"{csv.name} is empty"
        assert "seed" in df.columns, f"{csv.name} missing 'seed' column"
    # supplementary analysis outputs (Morris screening, CI-vs-power) load and are
    # non-empty; they are not sweep files and need not carry a 'seed' column
    for name in ("morris_screening.csv", "ci_vs_power.csv"):
        p = ROOT / "data" / name
        if p.exists():
            assert len(pd.read_csv(p)) > 0, f"{name} is empty"


def test_shared_modules_do_not_drift():
    for m in SHARED:
        a = (ROOT / "simulation" / m)
        b = (ROOT / "paper2_anchored_detector" / m)
        assert a.exists() and b.exists(), f"{m} missing from one location"
        assert a.read_text() == b.read_text(), (
            f"{m} differs between simulation/ and paper2_anchored_detector/ — "
            f"re-sync the shared engine modules")
