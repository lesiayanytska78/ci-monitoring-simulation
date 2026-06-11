"""Repository-integrity checks: the released data loads, and the simulation
modules shared between `simulation/` and `paper2_anchored_detector/` have not
drifted apart."""
import pathlib
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHARED = ["energy_substrate.py", "carbon_layer.py", "anomaly_model.py",
          "monitoring.py", "sensitivity.py"]


def test_released_csvs_load_and_nonempty():
    csvs = sorted((ROOT / "data").glob("*.csv"))
    assert len(csvs) >= 9, "expected the nine released sweep CSVs"
    for csv in csvs:
        df = pd.read_csv(csv)
        assert len(df) > 0, f"{csv.name} is empty"
        assert "seed" in df.columns, f"{csv.name} missing 'seed' column"


def test_shared_modules_do_not_drift():
    for m in SHARED:
        a = (ROOT / "simulation" / m)
        b = (ROOT / "paper2_anchored_detector" / m)
        assert a.exists() and b.exists(), f"{m} missing from one location"
        assert a.read_text() == b.read_text(), (
            f"{m} differs between simulation/ and paper2_anchored_detector/ — "
            f"re-sync the shared engine modules")
