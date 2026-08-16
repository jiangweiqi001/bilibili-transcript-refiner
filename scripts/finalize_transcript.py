"""Validate corrections and atomically render the formal Markdown transcript."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

try:
    from scripts.correction_contract import (
        Correction,
        Uncertainty,
        audit_corrections,
        is_whole_row_inaudible,
        read_corrections,
        validate_pairing,
        write_audit_report,
    )
    from scripts.transcript_contract import (
        Segment,
        exclusive_job_lock,
        format_timestamp,
        output_name,
        parse_timestamp,
        read_jsonl,
    )
    from scripts.review_corrections import validate_finding_reviews
    from scripts.translation_contract import (
        Translation,
        read_translations,
        validate_translation_pairing,
    )
except ModuleNotFoundError:  # Direct execution from scripts/.
    from correction_contract import (  # type: ignore
        Correction,
        Uncertainty,
        audit_corrections,
        is_whole_row_inaudible,
        read_corrections,
        validate_pairing,
        write_audit_report,
    )
    from transcript_contract import (  # type: ignore
        Segment,
        exclusive_job_lock,
        format_timestamp,
        output_name,
        parse_timestamp,
        read_jsonl,
    )
    from review_corrections import validate_finding_reviews  # type: ignore
    from translation_contract import (  # type: ignore
        Translation,
        read_translations,
        validate_translation_pairing,
    )

_ALLOWED_FORMAL_FILES = {"raw-transcript.jsonl", "corrected-transcript.md"}


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


_read_corrections = read_corrections


def _validate_pairing(
    raw_rows: Sequence[Segment], correction_rows: Sequence[Correction]
) -> None:
    validate_pairing(raw_rows, correction_rows)


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
    provenance: dict[str, object] | None = None,
    generated_at: str | None = None,
    raw_sha256: str | None = None,
    high_risk_count: int = 0,
    high_risk_reviewed_count: int = 0,
    source_audio_sha256: str | None = None,
    normalized_wav_sha256: str | None = None,
    translation_rows: Sequence[Translation] | None = None,
    translations_sha256: str | None = None,
) -> str:
    if status not in {"complete", "incomplete"}:
        raise ValueError("status must be complete or incomplete")
    if status == "incomplete" and not (incomplete_reason or "").strip():
        raise ValueError("incomplete status requires a reason")
    if incomplete_reason and ("\n" in incomplete_reason or "\r" in incomplete_reason):
        raise ValueError("incomplete reason must stay on one line")
    _validate_pairing(raw_rows, correction_rows)
    if translation_rows is None:
        if translations_sha256 is not None:
            raise ValueError(
                "translations SHA-256 requires a Chinese translation checkpoint"
            )
    else:
        validate_translation_pairing(correction_rows, translation_rows)
        if not isinstance(translations_sha256, str) or not re.fullmatch(
            r"[0-9A-Fa-f]{64}", translations_sha256
        ):
            raise ValueError(
                "bilingual output requires the translation checkpoint SHA-256"
            )
    if status == "complete" and any(
        is_whole_row_inaudible(row) for row in correction_rows
    ):
        raise ValueError("whole-row [听不清] requires status incomplete")

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
    ]
    if provenance is not None:
        required_provenance = (
            "yt_dlp",
            "ffmpeg",
            "ffprobe",
            "funasr_sensevoice",
            "funasr_vad",
            "sensevoice_model",
            "vad_model",
        )
        if any(not isinstance(provenance.get(key), dict) for key in required_provenance):
            raise ValueError("runtime provenance is incomplete")
        sensevoice_model = provenance["sensevoice_model"]
        yt_dlp = provenance["yt_dlp"]
        ffmpeg = provenance["ffmpeg"]
        ffprobe = provenance["ffprobe"]
        funasr = provenance["funasr_sensevoice"]
        funasr_vad = provenance["funasr_vad"]
        vad_model = provenance["vad_model"]
        if not all(
            (generated_at, raw_sha256, source_audio_sha256, normalized_wav_sha256)
        ):
            raise ValueError("formal provenance requires generation time and evidence SHA-256 values")
        lines.extend(
            [
                f"generated_at: {_yaml_string(generated_at)}",
                f"raw_transcript_sha256: {_yaml_string(raw_sha256)}",
                f"source_audio_sha256: {_yaml_string(source_audio_sha256)}",
                f"normalized_wav_sha256: {_yaml_string(normalized_wav_sha256)}",
                'asr_model: "SenseVoiceSmall"',
                f"asr_model_revision: {_yaml_string(sensevoice_model['revision'])}",
                f"asr_model_sha256: {_yaml_string(sensevoice_model['sha256'])}",
                f"yt_dlp_version: {_yaml_string(yt_dlp['version'])}",
                f"yt_dlp_sha256: {_yaml_string(yt_dlp['sha256'])}",
                f"ffmpeg_version: {_yaml_string(ffmpeg['version'])}",
                f"ffmpeg_sha256: {_yaml_string(ffmpeg['sha256'])}",
                f"ffprobe_version: {_yaml_string(ffprobe['version'])}",
                f"ffprobe_sha256: {_yaml_string(ffprobe['sha256'])}",
                f"funasr_runtime_version: {_yaml_string(funasr['version'])}",
                f"funasr_runtime_sha256: {_yaml_string(funasr['sha256'])}",
                f"funasr_vad_version: {_yaml_string(funasr_vad['version'])}",
                f"funasr_vad_sha256: {_yaml_string(funasr_vad['sha256'])}",
                f"vad_model_version: {_yaml_string(vad_model['version'])}",
                f"vad_model_revision: {_yaml_string(vad_model['revision'])}",
                f"vad_model_sha256: {_yaml_string(vad_model['sha256'])}",
                f"correction_high_risk_count: {high_risk_count}",
                f"correction_high_risk_reviewed_count: {high_risk_reviewed_count}",
                "correction_high_risk_reviewed: "
                + (
                    "true"
                    if high_risk_count > 0
                    and high_risk_reviewed_count == high_risk_count
                    else "false"
                ),
            ]
        )
    else:
        lines.append('asr_model: "SenseVoiceSmall"')
    if translation_rows is not None:
        lines.extend(
            [
                'output_mode: "bilingual-en-zh"',
                'translation_mode: "faithful"',
                f"translations_zh_sha256: {_yaml_string(translations_sha256.upper())}",
            ]
        )
    lines.extend(
        [
            'correction_mode: "faithful"',
            f'status: "{status}"',
            "---",
            "",
            f"# {title}",
            "",
            "> 本文为 AI 忠实校订逐字稿。仅结合语境修正明显的识别错误、术语、人名、断句和标点；不润色、不概括、不把口语改写成书面语。",
        ]
    )
    if status == "incomplete":
        lines.extend(["", f"> 完整性说明：{incomplete_reason.strip()}"])
    if translation_rows is not None:
        lines.extend(
            [
                "",
                "> 中文行是对稳定英文校订稿的忠实翻译；不概括、不解释、不修正说话人的观点，并保留原文的不确定性。",
            ]
        )
    lines.extend(["", "## 逐字稿", ""])
    if translation_rows is None:
        for row in correction_rows:
            lines.extend([f"[{format_timestamp(row.start_ms)}] {row.text}", ""])
    else:
        for row, translated in zip(correction_rows, translation_rows):
            timestamp = format_timestamp(row.start_ms)
            lines.extend(
                [
                    f"[{timestamp}] **English:** {row.text}",
                    f"[{timestamp}] **中文：** {translated.text_zh}",
                    "",
                ]
            )
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


def _archive_owned_stale_partials(formal_dir: Path, job_dir: Path) -> None:
    archive = job_dir / "archive"
    for path in sorted(formal_dir.glob("corrected-transcript.md.partial-*")):
        if not path.is_file():
            continue
        archive.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        target = archive / f"{path.name}.stale-{stamp}-{uuid.uuid4().hex[:8]}"
        shutil.move(str(path), str(target))


def _finalize_transcript_locked(
    job_dir: Path | str,
    output_root: Path | str,
    *,
    status: str,
    incomplete_reason: str | None = None,
    acknowledge_high_risk: bool = False,
    bilingual: bool = False,
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
    _validate_pairing(raw_rows, correction_rows)
    translation_rows: list[Translation] | None = None
    translations_sha256: str | None = None
    if bilingual:
        translations_path = job_dir / "translations-zh.jsonl"
        if not translations_path.is_file():
            raise FileNotFoundError(
                f"Chinese translation checkpoint is missing: {translations_path}"
            )
        translation_rows = read_translations(translations_path)
        validate_translation_pairing(correction_rows, translation_rows)
        translations_sha256 = _sha256(translations_path)
    if acknowledge_high_risk:
        raise ValueError(
            "global high-risk acknowledgement is no longer accepted; "
            "record finding-level audio reviews"
        )
    audit = write_audit_report(
        job_dir / "correction-audit.json",
        raw_path,
        corrections_path,
        raw_rows,
        correction_rows,
    )
    high_risk_count = int(audit["high_risk_count"])
    reviewed_count = validate_finding_reviews(job_dir, audit)
    runtime_provenance = job_value.get("runtime_provenance")
    if not isinstance(runtime_provenance, dict):
        raise ValueError(
            "job predates runtime provenance; rerun transcript preparation with --rerun-asr"
        )
    source_audio_sha256 = job_value.get("source_audio_sha256")
    normalized_wav_sha256 = job_value.get("normalized_wav_sha256")
    source_audio_path = Path(str(job_value.get("source_audio_path", ""))).resolve()
    normalized_wav_path = Path(str(job_value.get("normalized_wav_path", ""))).resolve()
    for label, path, expected in (
        ("source audio", source_audio_path, source_audio_sha256),
        ("normalized WAV", normalized_wav_path, normalized_wav_sha256),
    ):
        if (
            not isinstance(expected, str)
            or not re.fullmatch(r"[0-9A-Fa-f]{64}", expected)
            or not path.is_relative_to(job_dir)
            or not path.is_file()
            or _sha256(path) != expected.upper()
        ):
            raise ValueError(f"{label} SHA-256 does not match the prepared job")
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    document = render_corrected(
        metadata_value,
        raw_rows,
        correction_rows,
        status=status,
        incomplete_reason=incomplete_reason,
        provenance=runtime_provenance,
        generated_at=generated_at,
        raw_sha256=actual_hash,
        high_risk_count=high_risk_count,
        high_risk_reviewed_count=reviewed_count,
        source_audio_sha256=source_audio_sha256.upper(),
        normalized_wav_sha256=normalized_wav_sha256.upper(),
        translation_rows=translation_rows,
        translations_sha256=translations_sha256,
    )

    _archive_owned_stale_partials(formal_dir, job_dir)
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

    if bilingual:
        job_value.update(
            {
                "output_mode": "bilingual-en-zh",
                "translations_zh_sha256": translations_sha256,
            }
        )
    else:
        job_value.pop("output_mode", None)
        job_value.pop("translations_zh_sha256", None)
    job_value.update(
        {
            "correction_state": status,
            "corrected_path": str(corrected_path),
            "corrected_sha256": _sha256(corrected_path),
            "correction_high_risk_count": high_risk_count,
            "correction_high_risk_reviewed_count": reviewed_count,
            "correction_high_risk_reviewed": (
                high_risk_count > 0 and reviewed_count == high_risk_count
            ),
            "finalized_at": generated_at,
        }
    )
    _write_json_atomic(job_dir / "job.json", job_value)
    return corrected_path


def finalize_transcript(
    job_dir: Path | str,
    output_root: Path | str,
    *,
    status: str,
    incomplete_reason: str | None = None,
    acknowledge_high_risk: bool = False,
    bilingual: bool | None = None,
) -> Path:
    if bilingual is None:
        raise ValueError(
            "output mode is required; pass bilingual=True or bilingual=False"
        )
    resolved_job_dir = Path(job_dir).resolve()
    with exclusive_job_lock(resolved_job_dir / "job.lock"):
        return _finalize_transcript_locked(
            resolved_job_dir,
            output_root,
            status=status,
            incomplete_reason=incomplete_reason,
            acknowledge_high_risk=acknowledge_high_risk,
            bilingual=bilingual,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and finalize a faithful Bilibili transcript."
    )
    parser.add_argument("--job-dir", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--status", required=True, choices=("complete", "incomplete"))
    parser.add_argument("--incomplete-reason")
    output_mode = parser.add_mutually_exclusive_group(required=True)
    output_mode.add_argument("--bilingual", action="store_true")
    output_mode.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    corrected = finalize_transcript(
        args.job_dir,
        args.output_root,
        status=args.status,
        incomplete_reason=args.incomplete_reason,
        bilingual=args.bilingual,
    )
    print(json.dumps({"corrected_path": str(corrected)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
