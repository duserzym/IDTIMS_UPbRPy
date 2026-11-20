"""Write the reduction snapshot used by tests/test_snapshot.py.

Run only when a change to reduced numbers is intended and reviewed:

    python tools/make_snapshot.py

The snapshot records every numeric attribute of every grain reduced from
examples/synthetic_zircon_CA-ID-TIMS.csv under three Th-correction settings.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from snapshot_support import OUTPUT, reduce_variants  # noqa: E402


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(reduce_variants(), sort_keys=True, separators=(",", ":")) + "\n")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
