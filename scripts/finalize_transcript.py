"""Validate corrections and atomically render the formal Markdown transcript."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

try:
    from scripts.transcript_contract import (
        Segment,
        format_timestamp,
        output_name,
        parse_timestamp,
        read_jsonl,
    )
except ModuleNotFoundError:  # Direct execution from scripts/.
    from transcript_contract import (  # type: ignore
        Segment,
        format_timestamp,
        output_name,
        parse_timestamp,
        read_jsonl,
    )


_CORRECTION_KEYS = ["start", "end", "text", "uncertainties"]
_UNCERTAINTY_KEYS = ["marker", "note"]
_MARKER_RE = re.compile(r"\[(?:疑似：[^\]\r\n]+|听不清)\]")
_ALLOWED_FORMAL_FILES = {"raw-transcript.jsonl", "corrected-transcript.md"}


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


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json_atomic(path: Path, value: object) -> None:
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _read_corrections(path: Path) -> list[Correction]:
    rows: list[Correction] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise ValueError(f"correction line {line_number} is empty")
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"correction line {line_number} is not valid JSON"
                ) from exc
            if not isinstance(value, dict) or list(value.keys()) != _CORRECTION_KEYS:
                raise ValueError(
                    f"correction line {line_number} must contain exact keys: {_CORRECTION_KEYS}"
                )
            raw_uncertainties = value["uncertainties"]
            if not isinstance(raw_uncertainties, list):
                raise ValueError(
                    f"correction line {line_number} uncertainties must be a list"
                )
            uncertainties: list[Uncertainty] = []
            for item in raw_uncertainties:
                if not isinstance(item, dict) or list(item.keys()) != _UNCERTAINTY_KEYS:
                    raise ValueError(
                        f"correction line {line_number} uncertainty must contain exact keys: {_UNCERTAINTY_KEYS}"
                    )
                uncertainties.append(Uncertainty(item["marker"], item["note"]))
            rows.append(
                Correction(
                    parse_timestamp(value["start"]),
                    parse_timestamp(value["end"]),
                    value["text"],
                    tuple(uncertainties),
                )
            )
    return rows


def _validate_pairing(
    raw_rows: Sequence[Segment], correction_rows: Sequence[Correction]
) -> None:
    if len(raw_rows) != len(correction_rows):
        raise ValueError("raw and correction row count must match")
    for index, (raw, corrected) in enumerate(zip(raw_rows, correction_rows)):
        if (raw.start_ms, raw.end_ms) != (
            corrected.start_ms,
            corrected.end_ms,
        ):
            raise ValueError(f"correction timestamps changed at row {index}")
        visible = Counter(_MARKER_RE.findall(corrected.text))
        listed = Counter(item.marker for item in corrected.uncertainties)
        if visible != listed:
            raise ValueError(
                f"visible and listed uncertainty marker counts differ at row {index}"
            )
        marker_prefixes = corrected.text.count("[疑似：") + corrected.text.count("[听不清")
        if marker_prefixes != sum(visible.values()):
            raise ValueError(f"malformed uncertainty marker at row {index}")


def _yaml_string(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("YAML metadata value must be text")
    return json.dumps(value, ensure_ascii=False)


def _single_line(value: str) -> str:
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())


def render_corrected(
    metadata: dict[str, object],
    raw_rows: Sequence[Segment],
    correction_rows: Sequence[Correction],
    *,
    status: str,
    incomplete_reason: str | None = None,
) -> str:
    if status not in {"complete", "incomplete"}:
        raise ValueError("status must be complete or incomplete")
    if status == "incomplete" and not (incomplete_reason or "").strip():
        raise ValueError("incomplete status requires a reason")
    if incomplete_reason and ("\n" in incomplete_reason or "\r" in incomplete_reason):
        raise ValueError("incomplete reason must stay on one line")
    _validate_pairing(raw_rows, correction_rows)

    required = ("source_url", "bvid", "page", "title", "uploader", "duration")
    missing = [key for key in required if key not in metadata]
    if missing:
        raise ValueError(f"metadata is missing: {', '.join(missing)}")
    if not isinstance(metadata["page"], int) or metadata["page"] < 1:
        raise ValueError("metadata page must be a positive integer")

    title = _single_line(str(metadata["title"]))
    lines = [
        "---",
        f"source_url: {_yaml_string(metadata['source_url'])}",
        f"bvid: {_yaml_string(metadata['bvid'])}",
        f"page: {metadata['page']}",
        f"title: {_yaml_string(title)}",
        f"uploader: {_yaml_string(metadata['uploader'])}",
        f"duration: {_yaml_string(metadata['duration'])}",
        'asr_model: "SenseVoiceSmall"',
        'correction_mode: "faithful"',
        f'status: "{status}"',
        "---",
        "",
        f"# {title}",
        "",
        "> 本文为 AI 忠实校订逐字稿。仅结合语境修正明显的识别错误、术语、人名、断句和标点；不润色、不概括、不把口语改写成书面语。",
    ]
    if status == "incomplete":
        lines.extend(["", f"> 完整性说明：{incomplete_reason.strip()}"])
    lines.extend(["", "## 逐字稿", ""])
    for row in correction_rows:
        lines.extend([f"[{format_timestamp(row.start_ms)}] {row.text}", ""])
    lines.extend(["## 存疑处", ""])
    uncertainty_lines: list[str] = []
    for row in correction_rows:
        timestamp = format_timestamp(row.start_ms)
        for item in row.uncertainties:
            uncertainty_lines.append(
                f"- [{timestamp}] `{item.marker}`：{item.note.strip()}"
            )
    lines.extend(uncertainty_lines or ["- 无"])
    return "\n".join(lines).rstrip() + "\n"


def _assert_formal_entries(formal_dir: Path) -> None:
    unexpected = sorted(
        path.name for path in formal_dir.iterdir() if path.name not in _ALLOWED_FORMAL_FILES
    )
    if unexpected:
        raise ValueError(f"unexpected deliverable in formal directory: {unexpected[0]}")


def finalize_transcript(
    job_dir: Path | str,
    output_root: Path | str,
    *,
    status: str,
    incomplete_reason: str | None = None,
) -> Path:
    job_dir = Path(job_dir).resolve()
    output_root = Path(output_root).resolve()
    job_value = _read_json(job_dir / "job.json")
    metadata_value = _read_json(job_dir / "metadata.json")
    if not isinstance(job_value, dict) or not isinstance(metadata_value, dict):
        raise ValueError("job metadata is invalid")
    if job_value.get("state") != "asr_complete":
        raise ValueError("job must be in asr_complete state")
    bvid = job_value.get("bvid")
    page = job_value.get("page")
    if not isinstance(bvid, str) or not isinstance(page, int):
        raise ValueError("job identifier is invalid")

    formal_dir = output_root / output_name(bvid, page)
    raw_path = formal_dir / "raw-transcript.jsonl"
    manifest_raw = Path(str(job_value.get("raw_path", ""))).resolve()
    if manifest_raw != raw_path.resolve() or not raw_path.is_file():
        raise ValueError("formal raw transcript does not match the job manifest")
    expected_hash = job_value.get("raw_sha256")
    actual_hash = _sha256(raw_path)
    if not isinstance(expected_hash, str) or actual_hash != expected_hash.upper():
        raise ValueError("raw transcript SHA-256 changed after ASR preparation")

    raw_rows = read_jsonl(raw_path)
    corrections_path = job_dir / "corrections.jsonl"
    if not corrections_path.is_file():
        raise FileNotFoundError(f"correction checkpoint is missing: {corrections_path}")
    correction_rows = _read_corrections(corrections_path)
    document = render_corrected(
        metadata_value,
        raw_rows,
        correction_rows,
        status=status,
        incomplete_reason=incomplete_reason,
    )

    _assert_formal_entries(formal_dir)
    corrected_path = formal_dir / "corrected-transcript.md"
    partial = formal_dir / f"corrected-transcript.md.partial-{uuid.uuid4().hex}"
    try:
        with partial.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(document)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(partial, corrected_path)
    finally:
        if partial.exists():
            partial.unlink()
    _assert_formal_entries(formal_dir)
    if {path.name for path in formal_dir.iterdir()} != _ALLOWED_FORMAL_FILES:
        raise ValueError("formal directory must contain exactly the two deliverables")

    job_value.update(
        {
            "correction_state": status,
            "corrected_path": str(corrected_path),
            "corrected_sha256": _sha256(corrected_path),
        }
    )
    _write_json_atomic(job_dir / "job.json", job_value)
    return corrected_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and finalize a faithful Bilibili transcript."
    )
    parser.add_argument("--job-dir", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--status", required=True, choices=("complete", "incomplete"))
    parser.add_argument("--incomplete-reason")
    args = parser.parse_args()
    corrected = finalize_transcript(
        args.job_dir,
        args.output_root,
        status=args.status,
        incomplete_reason=args.incomplete_reason,
    )
    print(json.dumps({"corrected_path": str(corrected)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
