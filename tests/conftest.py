import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
for sub in ("worker", "training", "service"):
    sys.path.insert(0, str(ROOT / sub))
