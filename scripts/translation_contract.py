"""Deterministic, resumable Chinese translation checkpoints."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

try:
    from scripts.correction_contract import Correction, read_corrections
    from scripts.transcript_contract import (
        exclusive_job_lock,
        format_timestamp,
        parse_timestamp,
    )
except ModuleNotFoundError:  # Direct execution from scripts/.
    from correction_contract import Correction, read_corrections  # type: ignore
    from transcript_contract import (  # type: ignore
        exclusive_job_lock,
        format_timestamp,
        parse_timestamp,
    )


_TRANSLATION_KEYS = ["start", "end", "source_text", "text_zh"]


@dataclass(frozen=True)
class Translation:
    start_ms: int
    end_ms: int
    source_text: str
    text_zh: str

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("translation timestamps must be nonnegative and increasing")
        for label, value in (
            ("source text", self.source_text),
            ("Chinese translation", self.text_zh),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"translation {label} must be nonempty")
            if "\n" in value or "\r" in value:
                raise ValueError(f"translation {label} must stay on one line")

    def to_record(self) -> dict[str, object]:
        return {
            "start": format_timestamp(self.start_ms),
            "end": format_timestamp(self.end_ms),
            "source_text": self.source_text,
            "text_zh": self.text_zh,
        }


def _translation_from_record(value: object, line_number: int) -> Translation:
    if not isinstance(value, dict) or list(value.keys()) != _TRANSLATION_KEYS:
        raise ValueError(
            f"translation line {line_number} must contain exact keys: {_TRANSLATION_KEYS}"
        )
    return Translation(
        parse_timestamp(value["start"]),
        parse_timestamp(value["end"]),
        value["source_text"],
        value["text_zh"],
    )


def read_translations(path: Path | str) -> list[Translation]:
    source = Path(path)
    rows: list[Translation] = []
    with source.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise ValueError(f"translation line {line_number} is empty")
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"translation line {line_number} is not valid JSON"
                ) from exc
            rows.append(_translation_from_record(value, line_number))
    return rows


def validate_translation_pairing(
    correction_rows: Sequence[Correction],
    translation_rows: Sequence[Translation],
    *,
    allow_prefix: bool = False,
) -> None:
    if len(translation_rows) > len(correction_rows) or (
        not allow_prefix and len(correction_rows) != len(translation_rows)
    ):
        raise ValueError("correction and translation row count must match")
    for index, (corrected, translated) in enumerate(
        zip(correction_rows, translation_rows)
    ):
        if (corrected.start_ms, corrected.end_ms) != (
            translated.start_ms,
            translated.end_ms,
        ):
            raise ValueError(f"translation timestamps changed at row {index}")
        if corrected.text != translated.source_text:
            raise ValueError(f"translation source text changed at row {index}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def write_translations_atomic(
    path: Path | str, rows: Iterable[Translation]
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f"{target.name}.partial-{uuid.uuid4().hex}")
    try:
        with partial.open("x", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                json.dump(
                    row.to_record(),
                    handle,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(partial, target)
    finally:
        if partial.exists():
            partial.unlink()


def install_translation_batch(
    corrections_path: Path | str,
    checkpoint_path: Path | str,
    batch_path: Path | str,
    *,
    replace_from: int | None = None,
    expected_translations_sha256: str | None = None,
) -> dict[str, object]:
    corrections_source = Path(corrections_path).resolve()
    checkpoint = Path(checkpoint_path).resolve()
    batch = Path(batch_path).resolve()
    with exclusive_job_lock(checkpoint.parent / "job.lock"):
        correction_rows = read_corrections(corrections_source)
        existing = read_translations(checkpoint) if checkpoint.is_file() else []

        if replace_from is None:
            validate_translation_pairing(
                correction_rows, existing, allow_prefix=True
            )
            if expected_translations_sha256 is not None:
                raise ValueError(
                    "expected translations SHA-256 is only valid with replace_from"
                )
            accepted_prefix = existing
            batch_start = len(existing)
        else:
            if not isinstance(replace_from, int) or isinstance(replace_from, bool):
                raise ValueError("replace_from must be a row index")
            if replace_from < 0 or replace_from > len(existing):
                raise ValueError(
                    "replace_from must address the accepted translation prefix"
                )
            if not checkpoint.is_file() or not expected_translations_sha256:
                raise ValueError(
                    "replacement requires the current expected translations SHA-256"
                )
            actual_hash = _sha256(checkpoint)
            if actual_hash != expected_translations_sha256.upper():
                raise ValueError(
                    "translation checkpoint changed; expected translations SHA-256 does not match"
                )
            accepted_prefix = existing[:replace_from]
            validate_translation_pairing(
                correction_rows, accepted_prefix, allow_prefix=True
            )
            batch_start = replace_from

        next_rows = read_translations(batch)
        if not next_rows:
            raise ValueError("translation batch must contain at least one row")
        candidate = [*accepted_prefix, *next_rows]
        validate_translation_pairing(
            correction_rows, candidate, allow_prefix=True
        )
        if batch_start >= len(correction_rows):
            raise ValueError("translation batch starts after the final correction row")
        first = next_rows[0]
        expected = correction_rows[batch_start]
        if (first.start_ms, first.end_ms, first.source_text) != (
            expected.start_ms,
            expected.end_ms,
            expected.text,
        ):
            raise ValueError("translation batch must start at the next correction row")

        write_translations_atomic(checkpoint, candidate)
        result: dict[str, object] = {
            "accepted_rows": len(candidate),
            "next_index": len(candidate),
            "complete": len(candidate) == len(correction_rows),
            "translations_sha256": _sha256(checkpoint),
        }
        if replace_from is not None:
            result["replaced_from"] = replace_from
        return result
