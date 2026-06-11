"""Make the self-contained module set importable for the test suite.

The simulation modules (Modules 1-5) plus the proposed detector
(monitoring_anchored.py) live together in `paper2_anchored_detector/`, so adding
that folder to the path lets the tests exercise the full pipeline end to end with
a single, consistent copy of the code.
"""
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "paper2_anchored_detector"))
