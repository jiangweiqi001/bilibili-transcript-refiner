"""Atomically accept the next validated batch of faithful corrections."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from scripts.correction_contract import install_correction_batch
except ModuleNotFoundError:  # Direct execution from scripts/.
    from correction_contract import install_correction_batch  # type: ignore


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and atomically checkpoint the next correction batch."
    )
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--batch", required=True, type=Path)
    args = parser.parse_args()
    result = install_correction_batch(args.raw, args.checkpoint, args.batch)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
