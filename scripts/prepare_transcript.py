"""Prepare immutable, timestamped SenseVoiceSmall transcript evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence
from urllib.parse import parse_qs, urlparse

try:
    from scripts.transcript_contract import (
        BilibiliTarget,
        Segment,
        format_timestamp,
        output_name,
        parse_bilibili_url,
        read_jsonl,
        validate_coverage,
        write_jsonl_atomic,
    )
except ModuleNotFoundError:  # Direct execution from scripts/.
    from transcript_contract import (  # type: ignore
        BilibiliTarget,
        Segment,
        format_timestamp,
        output_name,
        parse_bilibili_url,
        read_jsonl,
        validate_coverage,
        write_jsonl_atomic,
    )


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
_CONTROL_TAG_RE = re.compile(r"<\|[^<>|]*\|>")
_VAD_LINE_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s*$", re.MULTILINE)
_RUNTIME_KEYS = (
    "yt_dlp",
    "ffmpeg",
    "ffprobe",
    "funasr_sensevoice",
    "funasr_vad",
    "sensevoice_model",
    "vad_model",
)


@dataclass(frozen=True)
class PreparationResult:
    target: BilibiliTarget
    output_dir: Path
    raw_path: Path
    job_dir: Path
    metadata: dict[str, object]
    job_manifest: dict[str, object]
    page_defaulted: bool
    reused: bool = False


def _default_runner(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(item) for item in args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _run_checked(runner: Runner, args: Sequence[str], label: str):
    result = runner([str(item) for item in args])
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"{label} failed with exit code {result.returncode}: {detail}")
    return result


def _ensure_ascii(path: Path) -> None:
    try:
        str(path).encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(
            "runtime and job paths must contain ASCII characters only"
        ) from exc


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


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _load_runtime(runtime_root: Path) -> dict[str, str]:
    runtime_root = runtime_root.resolve()
    _ensure_ascii(runtime_root)
    manifest_path = runtime_root / "runtime.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"runtime manifest is missing; run bootstrap_runtime.ps1 first: {manifest_path}"
        )
    manifest = _read_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("runtime manifest has an unsupported schema")
    resolved: dict[str, str] = {}
    for key in _RUNTIME_KEYS:
        value = manifest.get(key)
        if not isinstance(value, str) or not Path(value).is_file():
            raise ValueError(f"runtime manifest has an invalid {key} path")
        resolved[key] = value
    return resolved


def _page_was_defaulted(url: str) -> bool:
    return "p" not in parse_qs(urlparse(url).query)


def _load_or_fetch_metadata(
    target: BilibiliTarget,
    job_dir: Path,
    runtime: dict[str, str],
    runner: Runner,
    page_defaulted: bool,
) -> dict[str, object]:
    path = job_dir / "metadata.json"
    if path.is_file():
        value = _read_json(path)
        if isinstance(value, dict) and (
            value.get("bvid"), value.get("page")
        ) == (target.bvid, target.page):
            return value

    result = _run_checked(
        runner,
        [
            runtime["yt_dlp"],
            "--dump-single-json",
            "--no-playlist",
            target.canonical_url,
        ],
        "Bilibili metadata extraction",
    )
    try:
        source = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("yt-dlp returned invalid metadata JSON") from exc
    title = source.get("title")
    uploader = source.get("uploader") or source.get("channel")
    duration = source.get("duration")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Bilibili metadata is missing a title")
    if not isinstance(uploader, str) or not uploader.strip():
        raise ValueError("Bilibili metadata is missing an uploader")
    if not isinstance(duration, (int, float)) or duration <= 0:
        raise ValueError("Bilibili metadata is missing a positive duration")
    duration_ms = round(float(duration) * 1000)
    metadata: dict[str, object] = {
        "source_url": target.canonical_url,
        "bvid": target.bvid,
        "page": target.page,
        "page_defaulted": page_defaulted,
        "title": title.strip(),
        "uploader": uploader.strip(),
        "duration_ms": duration_ms,
        "duration": format_timestamp(duration_ms),
    }
    _write_json_atomic(path, metadata)
    return metadata


def _find_cached_audio(job_dir: Path) -> Path | None:
    matches = sorted(
        path
        for path in job_dir.glob("source.*")
        if path.is_file() and ".partial-" not in path.name
    )
    if len(matches) > 1:
        raise ValueError(f"multiple cached source audio files found in {job_dir}")
    return matches[0] if matches else None


def _probe_duration_ms(
    media: Path, runtime: dict[str, str], runner: Runner
) -> int:
    result = _run_checked(
        runner,
        [
            runtime["ffprobe"],
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(media),
        ],
        f"duration probe for {media.name}",
    )
    try:
        value = json.loads(result.stdout)
        duration = float(value["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"ffprobe returned no valid duration for {media}") from exc
    if duration <= 0:
        raise ValueError(f"media duration must be positive: {media}")
    return round(duration * 1000)


def _duration_matches(actual_ms: int, expected_ms: int) -> bool:
    tolerance_ms = max(2_000, round(expected_ms * 0.002))
    return abs(actual_ms - expected_ms) <= tolerance_ms


def _archive_invalid_media(path: Path, job_dir: Path) -> None:
    archive = job_dir / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    target = archive / f"{path.stem}.invalid-{stamp}-{uuid.uuid4().hex[:8]}{path.suffix}"
    shutil.move(str(path), str(target))


def _prepare_wav(
    target: BilibiliTarget,
    job_dir: Path,
    runtime: dict[str, str],
    runner: Runner,
    expected_duration_ms: int,
) -> tuple[Path, int]:
    audio = _find_cached_audio(job_dir)
    if audio is not None:
        cached_duration_ms = _probe_duration_ms(audio, runtime, runner)
        if not _duration_matches(cached_duration_ms, expected_duration_ms):
            _archive_invalid_media(audio, job_dir)
            audio = None
    if audio is None:
        staging = job_dir / "staging" / f"download-{uuid.uuid4().hex}"
        staging.mkdir(parents=True, exist_ok=False)
        template = staging / "source.%(ext)s"
        result = _run_checked(
            runner,
            [
                runtime["yt_dlp"],
                "--no-playlist",
                "-f",
                "bestaudio/best",
                "--print",
                "after_move:filepath",
                "-o",
                str(template),
                target.canonical_url,
            ],
            "Bilibili audio download",
        )
        printed = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not printed:
            raise ValueError("yt-dlp did not report the downloaded audio path")
        staged_audio = Path(printed[-1])
        if not staged_audio.is_file() or staged_audio.parent.resolve() != staging.resolve():
            raise ValueError("yt-dlp reported an invalid audio path")
        audio = job_dir / f"source{staged_audio.suffix.lower()}"
        if audio.exists():
            raise FileExistsError(f"canonical source audio already exists: {audio}")
        os.replace(staged_audio, audio)
        source_duration_ms = _probe_duration_ms(audio, runtime, runner)
        if not _duration_matches(source_duration_ms, expected_duration_ms):
            _archive_invalid_media(audio, job_dir)
            raise ValueError(
                f"downloaded audio duration {source_duration_ms}ms does not match video metadata {expected_duration_ms}ms"
            )

    wav = job_dir / "speech.wav"
    if wav.is_file():
        wav_duration_ms = _probe_duration_ms(wav, runtime, runner)
        if _duration_matches(wav_duration_ms, expected_duration_ms):
            return wav, wav_duration_ms
        _archive_invalid_media(wav, job_dir)
    partial = job_dir / "speech.partial.wav"
    _run_checked(
        runner,
        [
            runtime["ffmpeg"],
            "-nostdin",
            "-y",
            "-i",
            str(audio),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(partial),
        ],
        "audio conversion",
    )
    if not partial.is_file():
        raise RuntimeError("FFmpeg did not create the expected WAV file")
    wav_duration_ms = _probe_duration_ms(partial, runtime, runner)
    if not _duration_matches(wav_duration_ms, expected_duration_ms):
        _archive_invalid_media(partial, job_dir)
        raise ValueError(
            f"converted WAV duration {wav_duration_ms}ms does not match video metadata {expected_duration_ms}ms"
        )
    os.replace(partial, wav)
    return wav, wav_duration_ms


def _validate_vad_spans(
    spans: list[tuple[int, int]], media_duration_ms: int
) -> None:
    if not spans:
        raise ValueError("VAD found no speech segments")
    previous_end = 0
    for start_ms, end_ms in spans:
        if start_ms < 0 or end_ms <= start_ms:
            raise ValueError("VAD returned invalid segment boundaries")
        if start_ms < previous_end:
            raise ValueError("VAD segments overlap or are out of order")
        if end_ms > media_duration_ms + 1_000:
            raise ValueError("VAD segment extends beyond the validated WAV duration")
        previous_end = end_ms


def _load_or_run_vad(
    wav: Path,
    wav_duration_ms: int,
    job_dir: Path,
    runtime: dict[str, str],
    runner: Runner,
) -> list[tuple[int, int]]:
    path = job_dir / "vad.json"
    wav_sha256 = _sha256(wav)
    if path.is_file():
        value = _read_json(path)
        if (
            isinstance(value, dict)
            and value.get("schema_version") == 1
            and value.get("wav_sha256") == wav_sha256
            and value.get("wav_duration_ms") == wav_duration_ms
            and isinstance(value.get("spans"), list)
        ):
            spans = [
                (int(row["start_ms"]), int(row["end_ms"]))
                for row in value["spans"]
            ]
            _validate_vad_spans(spans, wav_duration_ms)
            return spans
        _archive_invalid_media(path, job_dir)

    result = _run_checked(
        runner,
        [
            runtime["funasr_vad"],
            "-m",
            runtime["vad_model"],
            "-a",
            str(wav),
        ],
        "voice activity detection",
    )
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    spans = [(int(start), int(end)) for start, end in _VAD_LINE_RE.findall(combined)]
    _validate_vad_spans(spans, wav_duration_ms)
    _write_json_atomic(
        path,
        {
            "schema_version": 1,
            "wav_sha256": wav_sha256,
            "wav_duration_ms": wav_duration_ms,
            "spans": [
                {"start_ms": start, "end_ms": end} for start, end in spans
            ],
        },
    )
    return spans


def _load_segment_checkpoint(
    path: Path, expected_start: int, expected_end: int
) -> Segment | None:
    if not path.is_file():
        return None
    value = _read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"invalid segment checkpoint: {path}")
    segment = Segment(int(value["start_ms"]), int(value["end_ms"]), value["text"])
    if (segment.start_ms, segment.end_ms) != (expected_start, expected_end):
        raise ValueError(f"segment checkpoint boundaries changed: {path}")
    return segment


def _transcribe_segments(
    wav: Path,
    spans: list[tuple[int, int]],
    run_dir: Path,
    runtime: dict[str, str],
    runner: Runner,
) -> list[Segment]:
    clips = run_dir / "clips"
    checkpoints = run_dir / "segments"
    clips.mkdir(parents=True, exist_ok=True)
    checkpoints.mkdir(parents=True, exist_ok=True)
    rows: list[Segment] = []

    for index, (start_ms, end_ms) in enumerate(spans):
        checkpoint = checkpoints / f"{index:06d}.json"
        existing = _load_segment_checkpoint(checkpoint, start_ms, end_ms)
        if existing is not None:
            rows.append(existing)
            continue

        clip = clips / f"{index:06d}.wav"
        if not clip.is_file():
            partial = clips / f"{index:06d}.partial.wav"
            _run_checked(
                runner,
                [
                    runtime["ffmpeg"],
                    "-nostdin",
                    "-y",
                    "-ss",
                    f"{start_ms / 1000:.3f}",
                    "-i",
                    str(wav),
                    "-t",
                    f"{(end_ms - start_ms) / 1000:.3f}",
                    "-c:a",
                    "pcm_s16le",
                    str(partial),
                ],
                f"audio segment {index}",
            )
            if not partial.is_file():
                raise RuntimeError(f"FFmpeg did not create audio segment {index}")
            os.replace(partial, clip)

        result = _run_checked(
            runner,
            [
                runtime["funasr_sensevoice"],
                "-m",
                runtime["sensevoice_model"],
                "-a",
                str(clip),
            ],
            f"SenseVoice segment {index}",
        )
        text = _CONTROL_TAG_RE.sub("", result.stdout or "").strip()
        if not text:
            raise ValueError(f"empty ASR text for segment {index}")
        segment = Segment(start_ms, end_ms, text)
        _write_json_atomic(
            checkpoint,
            {
                "start_ms": segment.start_ms,
                "end_ms": segment.end_ms,
                "text": segment.text,
            },
        )
        rows.append(segment)
    return rows


def _new_run_id() -> str:
    return "run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]


def _archive_raw(raw_path: Path, job_dir: Path) -> None:
    archive = job_dir / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    target = archive / f"raw-transcript-{stamp}-{uuid.uuid4().hex[:8]}.jsonl"
    shutil.copy2(raw_path, target)


def _archive_superseded_correction(formal_dir: Path, job_dir: Path) -> None:
    archive = job_dir / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    candidates = (
        (formal_dir / "corrected-transcript.md", "corrected-transcript"),
        (job_dir / "corrections.jsonl", "corrections"),
    )
    for source, label in candidates:
        if source.is_file():
            target = archive / f"{label}-{stamp}-{uuid.uuid4().hex[:8]}{source.suffix}"
            shutil.move(str(source), str(target))


def prepare_transcript(
    url: str,
    output_root: Path | str,
    runtime_root: Path | str,
    *,
    runner: Runner = _default_runner,
    rerun_asr: bool = False,
) -> PreparationResult:
    target = parse_bilibili_url(url)
    page_defaulted = _page_was_defaulted(url)
    runtime_root = Path(runtime_root).resolve()
    runtime = _load_runtime(runtime_root)
    formal_dir = Path(output_root).resolve() / output_name(target.bvid, target.page)
    raw_path = formal_dir / "raw-transcript.jsonl"
    job_dir = runtime_root / "jobs" / output_name(target.bvid, target.page)
    _ensure_ascii(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = job_dir / "metadata.json"
    manifest_path = job_dir / "job.json"

    if raw_path.is_file() and not rerun_asr:
        read_jsonl(raw_path)
        metadata = _read_json(metadata_path)
        manifest = _read_json(manifest_path)
        if not isinstance(metadata, dict) or not isinstance(manifest, dict):
            raise ValueError("reusable transcript job metadata is invalid")
        if manifest.get("state") == "preparing" and manifest.get("rerun_asr") is True:
            raise ValueError(
                "an explicit ASR rerun is incomplete; invoke again with --rerun-asr to resume it"
            )
        if manifest.get("media_validated") is not True:
            raise ValueError(
                "existing raw transcript predates media-duration validation; request an explicit ASR rerun"
            )
        return PreparationResult(
            target,
            formal_dir,
            raw_path,
            job_dir,
            metadata,
            manifest,
            page_defaulted,
            reused=True,
        )

    metadata = _load_or_fetch_metadata(
        target, job_dir, runtime, runner, page_defaulted
    )
    old_manifest = _read_json(manifest_path) if manifest_path.is_file() else {}
    if rerun_asr:
        if (
            isinstance(old_manifest, dict)
            and old_manifest.get("state") == "preparing"
            and old_manifest.get("rerun_asr") is True
            and isinstance(old_manifest.get("active_run"), str)
        ):
            active_run = old_manifest["active_run"]
        else:
            active_run = _new_run_id()
    elif isinstance(old_manifest, dict) and isinstance(old_manifest.get("active_run"), str):
        active_run = old_manifest["active_run"]
    else:
        active_run = "run-0001"

    manifest: dict[str, object] = {
        "schema_version": 1,
        "bvid": target.bvid,
        "page": target.page,
        "state": "preparing",
        "rerun_asr": rerun_asr,
        "active_run": active_run,
        "output_dir": str(formal_dir),
    }
    _write_json_atomic(manifest_path, manifest)
    expected_duration_ms = int(metadata["duration_ms"])
    wav, wav_duration_ms = _prepare_wav(
        target, job_dir, runtime, runner, expected_duration_ms
    )
    spans = _load_or_run_vad(
        wav, wav_duration_ms, job_dir, runtime, runner
    )
    run_dir = job_dir / "runs" / active_run
    rows = _transcribe_segments(wav, spans, run_dir, runtime, runner)
    validate_coverage(spans, rows)

    if raw_path.is_file() and rerun_asr:
        _archive_raw(raw_path, job_dir)
        _archive_superseded_correction(formal_dir, job_dir)
    write_jsonl_atomic(raw_path, rows, allow_replace=rerun_asr)
    manifest.update(
        {
            "state": "asr_complete",
            "raw_path": str(raw_path),
            "raw_sha256": _sha256(raw_path),
            "segment_count": len(rows),
            "media_validated": True,
            "media_duration_ms": wav_duration_ms,
        }
    )
    _write_json_atomic(manifest_path, manifest)
    return PreparationResult(
        target,
        formal_dir,
        raw_path,
        job_dir,
        metadata,
        manifest,
        page_defaulted,
    )


def _default_runtime_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("LOCALAPPDATA is not defined")
    return Path(local_app_data) / "bilibili-transcript-refiner" / "runtime-v1"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare immutable SenseVoiceSmall evidence for one Bilibili video."
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--runtime-root", type=Path, default=_default_runtime_root())
    parser.add_argument("--rerun-asr", action="store_true")
    args = parser.parse_args()
    result = prepare_transcript(
        args.url,
        args.output_root,
        args.runtime_root,
        rerun_asr=args.rerun_asr,
    )
    print(
        json.dumps(
            {
                "state": result.job_manifest["state"],
                "raw_path": str(result.raw_path),
                "job_dir": str(result.job_dir),
                "page_defaulted": result.page_defaulted,
                "reused": result.reused,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
