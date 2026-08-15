"""Atomically accept the next validated batch of Chinese translations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from scripts.translation_contract import install_translation_batch
except ModuleNotFoundError:  # Direct execution from scripts/.
    from translation_contract import install_translation_batch  # type: ignore


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and atomically checkpoint the next Chinese translation batch."
    )
    parser.add_argument("--corrections", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--batch", required=True, type=Path)
    parser.add_argument("--replace-from", type=int)
    parser.add_argument("--expected-translations-sha256")
    args = parser.parse_args()
    result = install_translation_batch(
        args.corrections,
        args.checkpoint,
        args.batch,
        replace_from=args.replace_from,
        expected_translations_sha256=args.expected_translations_sha256,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
