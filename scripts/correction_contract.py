"""Deterministic correction checkpoints and semantic-risk auditing."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, Sequence

try:
    from scripts.transcript_contract import (
        Segment,
        exclusive_job_lock,
        format_timestamp,
        parse_timestamp,
        read_jsonl,
    )
except ModuleNotFoundError:  # Direct execution from scripts/.
    from transcript_contract import (  # type: ignore
        Segment,
        exclusive_job_lock,
        format_timestamp,
        parse_timestamp,
        read_jsonl,
    )


_CORRECTION_KEYS = ["start", "end", "text", "uncertainties"]
_UNCERTAINTY_KEYS = ["marker", "note"]
_MARKER_RE = re.compile(r"\[(?:疑似：[^\]\r\n]+|听不清)\]")
_PROTECTED_TOKEN_RE = re.compile(
    r"\d{2,4}年\d{1,2}月\d{1,2}日"
    r"|\d{2,4}[-/.]\d{1,2}[-/.]\d{1,2}"
    r"|[零〇一二两三四五六七八九十百千万亿兆点]+(?:[%％年月日号元])?"
    r"|(?:[￥¥$€£]\s*)?\d+(?:[.,]\d+)*(?:[%％元万亿元年月日号])?"
    r"|[A-Za-z][A-Za-z0-9_.+#/-]*"
)
_IGNORED_CONTENT_RE = re.compile(r"[^0-9A-Za-z\u3400-\u9fff]+")


@dataclass(frozen=True)
class Uncertainty:
    marker: str
    note: str

    def __post_init__(self) -> None:
        if not _MARKER_RE.fullmatch(self.marker):
            raise ValueError(f"invalid uncertainty marker: {self.marker!r}")
        if not isinstance(self.note, str) or not self.note.strip():
            raise ValueError("uncertainty note must be nonempty")
        if "\n" in self.note or "\r" in self.note:
            raise ValueError("uncertainty note must stay on one line")


@dataclass(frozen=True)
class Correction:
    start_ms: int
    end_ms: int
    text: str
    uncertainties: tuple[Uncertainty, ...]

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("correction timestamps must be nonnegative and increasing")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("correction text must be nonempty")
        if "\n" in self.text or "\r" in self.text:
            raise ValueError("correction text must stay on one line")

    def to_record(self) -> dict[str, object]:
        return {
            "start": format_timestamp(self.start_ms),
            "end": format_timestamp(self.end_ms),
            "text": self.text,
            "uncertainties": [
                {"marker": item.marker, "note": item.note}
                for item in self.uncertainties
            ],
        }


@dataclass(frozen=True)
class RiskFinding:
    row_index: int
    code: str
    severity: str
    message: str
    raw_text: str
    corrected_text: str

    def to_record(self) -> dict[str, object]:
        return {
            "row_index": self.row_index,
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "raw_text": self.raw_text,
            "corrected_text": self.corrected_text,
        }


def finding_id(
    finding: RiskFinding, raw_sha256: str, corrections_sha256: str
) -> str:
    payload = {
        "raw_sha256": raw_sha256.upper(),
        "corrections_sha256": corrections_sha256.upper(),
        "row_index": finding.row_index,
        "code": finding.code,
        "raw_text": finding.raw_text,
        "corrected_text": finding.corrected_text,
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.partial-{uuid.uuid4().hex}")
    try:
        with partial.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(partial, path)
    finally:
        if partial.exists():
            partial.unlink()


def _correction_from_record(value: object, line_number: int) -> Correction:
    if not isinstance(value, dict) or list(value.keys()) != _CORRECTION_KEYS:
        raise ValueError(
            f"correction line {line_number} must contain exact keys: {_CORRECTION_KEYS}"
        )
    raw_uncertainties = value["uncertainties"]
    if not isinstance(raw_uncertainties, list):
        raise ValueError(f"correction line {line_number} uncertainties must be a list")
    uncertainties: list[Uncertainty] = []
    for item in raw_uncertainties:
        if not isinstance(item, dict) or list(item.keys()) != _UNCERTAINTY_KEYS:
            raise ValueError(
                f"correction line {line_number} uncertainty must contain exact keys: {_UNCERTAINTY_KEYS}"
            )
        uncertainties.append(Uncertainty(item["marker"], item["note"]))
    return Correction(
        parse_timestamp(value["start"]),
        parse_timestamp(value["end"]),
        value["text"],
        tuple(uncertainties),
    )


def read_corrections(path: Path | str) -> list[Correction]:
    source = Path(path)
    rows: list[Correction] = []
    with source.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise ValueError(f"correction line {line_number} is empty")
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"correction line {line_number} is not valid JSON"
                ) from exc
            rows.append(_correction_from_record(value, line_number))
    return rows


def validate_pairing(
    raw_rows: Sequence[Segment],
    correction_rows: Sequence[Correction],
    *,
    allow_prefix: bool = False,
) -> None:
    if len(correction_rows) > len(raw_rows) or (
        not allow_prefix and len(raw_rows) != len(correction_rows)
    ):
        raise ValueError("raw and correction row count must match")
    for index, (raw, corrected) in enumerate(zip(raw_rows, correction_rows)):
        if (raw.start_ms, raw.end_ms) != (corrected.start_ms, corrected.end_ms):
            raise ValueError(f"correction timestamps changed at row {index}")
        visible = Counter(_MARKER_RE.findall(corrected.text))
        listed = Counter(item.marker for item in corrected.uncertainties)
        if visible != listed:
            raise ValueError(
                f"visible and listed uncertainty marker counts differ at row {index}"
            )
        marker_prefixes = corrected.text.count("[疑似：") + corrected.text.count(
            "[听不清"
        )
        if marker_prefixes != sum(visible.values()):
            raise ValueError(f"malformed uncertainty marker at row {index}")


def _protected_tokens(text: str) -> tuple[str, ...]:
    without_markers = _MARKER_RE.sub("", text)
    return tuple(match.group(0) for match in _PROTECTED_TOKEN_RE.finditer(without_markers))


def _content(text: str) -> str:
    return _IGNORED_CONTENT_RE.sub("", _MARKER_RE.sub("", text))


def audit_corrections(
    raw_rows: Sequence[Segment], correction_rows: Sequence[Correction]
) -> list[RiskFinding]:
    validate_pairing(raw_rows, correction_rows, allow_prefix=True)
    findings: list[RiskFinding] = []
    for index, (raw, corrected) in enumerate(zip(raw_rows, correction_rows)):
        before_tokens = _protected_tokens(raw.text)
        after_tokens = _protected_tokens(corrected.text)
        if before_tokens != after_tokens:
            findings.append(
                RiskFinding(
                    index,
                    "protected-token-change",
                    "high",
                    f"protected token sequence changed: {list(before_tokens)} -> {list(after_tokens)}",
                    raw.text,
                    corrected.text,
                )
            )

        before = _content(raw.text)
        after = _content(corrected.text)
        if before and len(after) / len(before) < 0.65:
            findings.append(
                RiskFinding(
                    index,
                    "major-deletion",
                    "high",
                    "more than 35% of content characters were removed",
                    raw.text,
                    corrected.text,
                )
            )
        if before and after:
            similarity = SequenceMatcher(None, before, after, autojunk=False).ratio()
            if similarity < 0.45:
                findings.append(
                    RiskFinding(
                        index,
                        "large-rewrite",
                        "high",
                        f"content similarity is {similarity:.3f}",
                        raw.text,
                        corrected.text,
                    )
                )
    return findings


def write_corrections_atomic(
    path: Path | str, rows: Iterable[Correction]
) -> None:
    destination = Path(path)
    materialized = list(rows)
    partial = destination.with_name(f"{destination.name}.partial-{uuid.uuid4().hex}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with partial.open("x", encoding="utf-8", newline="\n") as handle:
            for row in materialized:
                handle.write(
                    json.dumps(row.to_record(), ensure_ascii=False, separators=(",", ":"))
                )
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(partial, destination)
    finally:
        if partial.exists():
            partial.unlink()


def write_audit_report(
    audit_path: Path | str,
    raw_path: Path | str,
    checkpoint_path: Path | str,
    raw_rows: Sequence[Segment],
    correction_rows: Sequence[Correction],
) -> dict[str, object]:
    findings = audit_corrections(raw_rows, correction_rows)
    high_risk_count = sum(item.severity == "high" for item in findings)
    raw_hash = _sha256(Path(raw_path))
    corrections_hash = _sha256(Path(checkpoint_path))
    finding_rows: list[dict[str, object]] = []
    for item in findings:
        record = item.to_record()
        record["finding_id"] = finding_id(item, raw_hash, corrections_hash)
        finding_rows.append(record)
    value: dict[str, object] = {
        "schema_version": 2,
        "raw_sha256": raw_hash,
        "corrections_sha256": corrections_hash,
        "accepted_rows": len(correction_rows),
        "total_rows": len(raw_rows),
        "high_risk_count": high_risk_count,
        "findings": finding_rows,
    }
    _write_json_atomic(Path(audit_path), value)
    return value


def install_correction_batch(
    raw_path: Path | str,
    checkpoint_path: Path | str,
    batch_path: Path | str,
    *,
    replace_from: int | None = None,
    expected_corrections_sha256: str | None = None,
) -> dict[str, object]:
    raw_source = Path(raw_path).resolve()
    checkpoint = Path(checkpoint_path).resolve()
    batch = Path(batch_path).resolve()
    with exclusive_job_lock(checkpoint.parent / "job.lock"):
        raw_rows = read_jsonl(raw_source)
        existing = read_corrections(checkpoint) if checkpoint.is_file() else []
        validate_pairing(raw_rows, existing, allow_prefix=True)
        if replace_from is None:
            if expected_corrections_sha256 is not None:
                raise ValueError(
                    "expected corrections SHA-256 is only valid with replace_from"
                )
            accepted_prefix = existing
            batch_start = len(existing)
        else:
            if not isinstance(replace_from, int) or isinstance(replace_from, bool):
                raise ValueError("replace_from must be a row index")
            if replace_from < 0 or replace_from > len(existing):
                raise ValueError("replace_from must address the accepted correction prefix")
            if not checkpoint.is_file() or not expected_corrections_sha256:
                raise ValueError(
                    "replacement requires the current expected corrections SHA-256"
                )
            actual_hash = _sha256(checkpoint)
            if actual_hash != expected_corrections_sha256.upper():
                raise ValueError(
                    "correction checkpoint changed; expected corrections SHA-256 does not match"
                )
            accepted_prefix = existing[:replace_from]
            batch_start = replace_from
        next_rows = read_corrections(batch)
        if not next_rows:
            raise ValueError("correction batch must contain at least one row")
        remaining = raw_rows[batch_start : batch_start + len(next_rows)]
        if len(remaining) != len(next_rows):
            raise ValueError("correction batch exceeds the remaining raw rows")
        try:
            validate_pairing(remaining, next_rows)
        except ValueError as exc:
            raise ValueError(
                f"correction batch must start at the next raw row: {exc}"
            ) from exc
        accepted = [*accepted_prefix, *next_rows]
        write_corrections_atomic(checkpoint, accepted)
        audit = write_audit_report(
            checkpoint.parent / "correction-audit.json",
            raw_source,
            checkpoint,
            raw_rows,
            accepted,
        )
        return {
            "accepted_rows": len(accepted),
            "total_rows": len(raw_rows),
            "next_index": len(accepted),
            "complete": len(accepted) == len(raw_rows),
            "replaced_from": replace_from,
            "high_risk_count": audit["high_risk_count"],
            "audit_path": str(checkpoint.parent / "correction-audit.json"),
        }
