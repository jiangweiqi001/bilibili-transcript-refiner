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
    from scripts.runtime_layout import default_runtime_root
    from scripts.transcript_contract import (
        BilibiliTarget,
        Segment,
        exclusive_job_lock,
        format_timestamp,
        output_name,
        parse_bilibili_url,
        read_jsonl,
        validate_coverage,
        write_jsonl_atomic,
    )
except ModuleNotFoundError:  # Direct execution from scripts/.
    from runtime_layout import default_runtime_root  # type: ignore
    from transcript_contract import (  # type: ignore
        BilibiliTarget,
        Segment,
        exclusive_job_lock,
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


def _default_runner(
    args: Sequence[str], *, timeout_seconds: int = 1800
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(item) for item in args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout_seconds,
    )


def _run_checked(runner: Runner, args: Sequence[str], label: str):
    command = [str(item) for item in args]
    try:
        result = runner(command)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"{label} timed out after {exc.timeout:g} seconds; job state was preserved for resume"
        ) from exc
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


def _provenance_fingerprint(
    provenance: dict[str, object], keys: Sequence[str]
) -> str:
    selected = {key: provenance[key] for key in keys}
    payload = json.dumps(
        selected, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest().upper()


def _load_runtime(runtime_root: Path) -> tuple[dict[str, str], dict[str, object]]:
    runtime_root = runtime_root.resolve()
    _ensure_ascii(runtime_root)
    manifest_path = runtime_root / "runtime.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"runtime manifest is missing; run bootstrap_runtime.ps1 first: {manifest_path}"
        )
    manifest = _read_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 2:
        raise ValueError(
            "runtime manifest has an unsupported schema; rerun bootstrap_runtime.ps1"
        )
    provenance = manifest.get("provenance")
    required_provenance = {
        "yt_dlp",
        "ffmpeg",
        "ffprobe",
        "funasr_sensevoice",
        "funasr_vad",
        "sensevoice_model",
        "vad_model",
    }
    if not isinstance(provenance, dict) or set(provenance) != required_provenance:
        raise ValueError("runtime manifest provenance is incomplete; rerun bootstrap_runtime.ps1")
    for key, value in provenance.items():
        if not isinstance(value, dict) or not isinstance(value.get("version"), str):
            raise ValueError(f"runtime provenance is invalid for {key}")
        digest = value.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9A-Fa-f]{64}", digest):
            raise ValueError(f"runtime provenance SHA-256 is invalid for {key}")
        if key in {"sensevoice_model", "vad_model"} and not re.fullmatch(
            r"[0-9a-f]{40}", str(value.get("revision", ""))
        ):
            raise ValueError(f"runtime provenance revision is invalid for {key}")
    resolved: dict[str, str] = {}
    for key in _RUNTIME_KEYS:
        value = manifest.get(key)
        if not isinstance(value, str):
            raise ValueError(f"runtime manifest has an invalid {key} path")
        path = Path(value).resolve()
        if not path.is_relative_to(runtime_root):
            raise ValueError(f"runtime artifact {key} is outside the runtime root")
        if not path.is_file():
            raise ValueError(f"runtime manifest has an invalid {key} path")
        expected = str(provenance[key]["sha256"]).upper()
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(
                f"runtime artifact {key} SHA-256 changed; rerun bootstrap_runtime.ps1"
            )
        resolved[key] = str(path)
    return resolved, provenance


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
        try:
            value = _read_json(path)
            if not isinstance(value, dict) or (
                value.get("bvid"), value.get("page")
            ) != (target.bvid, target.page):
                raise ValueError("cached metadata does not match this Bilibili page")
            if not isinstance(value.get("duration_ms"), int) or value["duration_ms"] <= 0:
                raise ValueError("cached metadata duration is invalid")
            return value
        except (OSError, TypeError, ValueError):
            _archive_invalid_media(path, job_dir)

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
) -> tuple[Path, Path, int]:
    audio = _find_cached_audio(job_dir)
    if audio is not None:
        try:
            cached_duration_ms = _probe_duration_ms(audio, runtime, runner)
            valid_audio = _duration_matches(cached_duration_ms, expected_duration_ms)
        except (OSError, RuntimeError, ValueError):
            valid_audio = False
        if not valid_audio:
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
        try:
            wav_duration_ms = _probe_duration_ms(wav, runtime, runner)
            valid_wav = _duration_matches(wav_duration_ms, expected_duration_ms)
        except (OSError, RuntimeError, ValueError):
            valid_wav = False
        if valid_wav:
            return audio, wav, wav_duration_ms
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
    return audio, wav, wav_duration_ms


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
    runtime_provenance: dict[str, object],
    runner: Runner,
) -> list[tuple[int, int]]:
    path = job_dir / "vad.json"
    wav_sha256 = _sha256(wav)
    runtime_fingerprint = _provenance_fingerprint(
        runtime_provenance, ("funasr_vad", "vad_model")
    )
    if path.is_file():
        try:
            value = _read_json(path)
            if not (
                isinstance(value, dict)
                and value.get("schema_version") == 2
                and value.get("wav_sha256") == wav_sha256
                and value.get("wav_duration_ms") == wav_duration_ms
                and value.get("runtime_fingerprint") == runtime_fingerprint
                and isinstance(value.get("spans"), list)
            ):
                raise ValueError("cached VAD state does not match current evidence")
            spans = [
                (int(row["start_ms"]), int(row["end_ms"]))
                for row in value["spans"]
            ]
            _validate_vad_spans(spans, wav_duration_ms)
            return spans
        except (OSError, TypeError, ValueError, KeyError):
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
            "schema_version": 2,
            "wav_sha256": wav_sha256,
            "wav_duration_ms": wav_duration_ms,
            "runtime_fingerprint": runtime_fingerprint,
            "spans": [
                {"start_ms": start, "end_ms": end} for start, end in spans
            ],
        },
    )
    return spans


def _load_segment_checkpoint(
    path: Path,
    clip: Path,
    expected_start: int,
    expected_end: int,
    runtime_fingerprint: str,
    media_fingerprint: str,
) -> Segment | None:
    if not path.is_file():
        return None
    try:
        value = _read_json(path)
        if not isinstance(value, dict) or set(value) != {
            "schema_version",
            "runtime_fingerprint",
            "media_fingerprint",
            "clip_sha256",
            "start_ms",
            "end_ms",
            "text",
        }:
            raise ValueError(f"invalid segment checkpoint: {path}")
        if (
            value.get("schema_version") != 3
            or value.get("runtime_fingerprint") != runtime_fingerprint
            or value.get("media_fingerprint") != media_fingerprint
        ):
            raise ValueError(f"segment checkpoint evidence changed: {path}")
        if not clip.is_file() or _sha256(clip) != value.get("clip_sha256"):
            raise ValueError(f"segment checkpoint clip changed: {path}")
        segment = Segment(int(value["start_ms"]), int(value["end_ms"]), value["text"])
        if (segment.start_ms, segment.end_ms) != (expected_start, expected_end):
            raise ValueError(f"segment checkpoint boundaries changed: {path}")
        return segment
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        quarantine = path.parent / "quarantine"
        quarantine.mkdir(parents=True, exist_ok=True)
        target = quarantine / (
            f"{path.stem}.invalid-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-"
            f"{uuid.uuid4().hex[:8]}{path.suffix}"
        )
        shutil.move(str(path), str(target))
        return None


def _media_fingerprint(
    wav_sha256: str,
    spans: Sequence[tuple[int, int]],
    runtime_provenance: dict[str, object],
) -> str:
    payload = {
        "wav_sha256": wav_sha256,
        "vad_runtime_fingerprint": _provenance_fingerprint(
            runtime_provenance, ("funasr_vad", "vad_model")
        ),
        "spans": [list(span) for span in spans],
    }
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest().upper()


def _archive_run_artifact(path: Path) -> None:
    if not path.is_file():
        return
    quarantine = path.parent / "quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    target = quarantine / f"{path.stem}.invalid-{stamp}-{uuid.uuid4().hex[:8]}{path.suffix}"
    shutil.move(str(path), str(target))


def _clip_is_current(
    clip: Path,
    metadata_path: Path,
    start_ms: int,
    end_ms: int,
    media_fingerprint: str,
) -> bool:
    if not clip.is_file() or not metadata_path.is_file():
        return False
    try:
        value = _read_json(metadata_path)
        return bool(
            isinstance(value, dict)
            and set(value) == {
                "schema_version",
                "media_fingerprint",
                "start_ms",
                "end_ms",
                "clip_sha256",
            }
            and value.get("schema_version") == 1
            and value.get("media_fingerprint") == media_fingerprint
            and value.get("start_ms") == start_ms
            and value.get("end_ms") == end_ms
            and value.get("clip_sha256") == _sha256(clip)
        )
    except (OSError, TypeError, ValueError):
        return False


def _transcribe_segments(
    wav: Path,
    spans: list[tuple[int, int]],
    run_dir: Path,
    runtime: dict[str, str],
    runtime_provenance: dict[str, object],
    media_fingerprint: str,
    runner: Runner,
) -> list[Segment]:
    clips = run_dir / "clips"
    checkpoints = run_dir / "segments"
    clips.mkdir(parents=True, exist_ok=True)
    checkpoints.mkdir(parents=True, exist_ok=True)
    rows: list[Segment] = []
    runtime_fingerprint = _provenance_fingerprint(
        runtime_provenance, ("ffmpeg", "funasr_sensevoice", "sensevoice_model")
    )

    for index, (start_ms, end_ms) in enumerate(spans):
        checkpoint = checkpoints / f"{index:06d}.json"
        clip = clips / f"{index:06d}.wav"
        clip_metadata = clips / f"{index:06d}.json"
        existing = _load_segment_checkpoint(
            checkpoint,
            clip,
            start_ms,
            end_ms,
            runtime_fingerprint,
            media_fingerprint,
        )
        if existing is not None:
            rows.append(existing)
            continue

        if not _clip_is_current(
            clip, clip_metadata, start_ms, end_ms, media_fingerprint
        ):
            _archive_run_artifact(clip)
            _archive_run_artifact(clip_metadata)
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
            _write_json_atomic(
                clip_metadata,
                {
                    "schema_version": 1,
                    "media_fingerprint": media_fingerprint,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "clip_sha256": _sha256(clip),
                },
            )

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
                "schema_version": 3,
                "runtime_fingerprint": runtime_fingerprint,
                "media_fingerprint": media_fingerprint,
                "clip_sha256": _sha256(clip),
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


def _job_directory(runtime_root: Path, output_root: Path, target: BilibiliTarget) -> Path:
    normalized_output = os.path.normcase(str(output_root.resolve()))
    output_digest = hashlib.sha256(normalized_output.encode("utf-8")).hexdigest()[:12]
    return runtime_root / "jobs" / (
        f"{output_name(target.bvid, target.page)}-out-{output_digest}"
    )


def _prepare_output_root(output_root: Path) -> Path:
    resolved = output_root.resolve()
    try:
        resolved.mkdir(parents=True, exist_ok=True)
        if not resolved.is_dir():
            raise ValueError("output root is not a directory")
        probe = resolved / f".btr-write-probe-{uuid.uuid4().hex}"
        try:
            with probe.open("x", encoding="ascii") as handle:
                handle.write("ok")
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            if probe.exists():
                probe.unlink()
    except (OSError, ValueError) as exc:
        raise ValueError(
            f"output root is not a writable directory: {resolved}"
        ) from exc
    return resolved


def _validate_manifest_media(job_dir: Path, manifest: dict[str, object]) -> None:
    for label, path_key, hash_key in (
        ("source audio", "source_audio_path", "source_audio_sha256"),
        ("normalized WAV", "normalized_wav_path", "normalized_wav_sha256"),
    ):
        path = Path(str(manifest.get(path_key, ""))).resolve()
        expected = manifest.get(hash_key)
        if (
            not isinstance(expected, str)
            or not re.fullmatch(r"[0-9A-Fa-f]{64}", expected)
            or not path.is_relative_to(job_dir)
            or not path.is_file()
            or _sha256(path) != expected.upper()
        ):
            raise ValueError(
                f"existing {label} SHA-256 does not match its job manifest; "
                "request an explicit ASR rerun"
            )


def _prepare_transcript_locked(
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
    runtime, runtime_provenance = _load_runtime(runtime_root)
    formal_dir = Path(output_root).resolve() / output_name(target.bvid, target.page)
    raw_path = formal_dir / "raw-transcript.jsonl"
    job_dir = _job_directory(runtime_root, Path(output_root), target)
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
        if manifest.get("state") != "asr_complete":
            raise ValueError(
                "existing raw transcript job is not complete; request an explicit ASR rerun"
            )
        if (
            manifest.get("schema_version") != 1
            or manifest.get("bvid") != target.bvid
            or manifest.get("page") != target.page
        ):
            raise ValueError(
                "existing raw transcript job identity does not match the request; request an explicit ASR rerun"
            )
        if manifest.get("media_validated") is not True:
            raise ValueError(
                "existing raw transcript predates media-duration validation; request an explicit ASR rerun"
            )
        if not isinstance(manifest.get("runtime_provenance"), dict):
            raise ValueError(
                "existing raw transcript predates runtime provenance; request an explicit ASR rerun"
            )
        _validate_manifest_media(job_dir, manifest)
        manifest_raw_path = Path(str(manifest.get("raw_path", ""))).resolve()
        if manifest_raw_path != raw_path.resolve():
            raise ValueError(
                "existing raw transcript manifest does not name the same output path; request an explicit ASR rerun"
            )
        recorded_sha256 = manifest.get("raw_sha256")
        if not isinstance(recorded_sha256, str) or _sha256(raw_path) != recorded_sha256:
            raise ValueError(
                "existing raw transcript SHA-256 does not match its job manifest; request an explicit ASR rerun"
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
    same_runtime = (
        isinstance(old_manifest, dict)
        and old_manifest.get("runtime_provenance") == runtime_provenance
    )
    if rerun_asr:
        if (
            isinstance(old_manifest, dict)
            and old_manifest.get("state") == "preparing"
            and old_manifest.get("rerun_asr") is True
            and isinstance(old_manifest.get("active_run"), str)
            and same_runtime
        ):
            active_run = old_manifest["active_run"]
        else:
            active_run = _new_run_id()
    elif (
        isinstance(old_manifest, dict)
        and isinstance(old_manifest.get("active_run"), str)
        and same_runtime
    ):
        active_run = old_manifest["active_run"]
    else:
        active_run = _new_run_id() if old_manifest else "run-0001"

    manifest: dict[str, object] = {
        "schema_version": 1,
        "bvid": target.bvid,
        "page": target.page,
        "state": "preparing",
        "rerun_asr": rerun_asr,
        "active_run": active_run,
        "output_dir": str(formal_dir),
        "runtime_provenance": runtime_provenance,
    }
    _write_json_atomic(manifest_path, manifest)
    expected_duration_ms = int(metadata["duration_ms"])
    audio, wav, wav_duration_ms = _prepare_wav(
        target, job_dir, runtime, runner, expected_duration_ms
    )
    spans = _load_or_run_vad(
        wav, wav_duration_ms, job_dir, runtime, runtime_provenance, runner
    )
    source_audio_sha256 = _sha256(audio)
    normalized_wav_sha256 = _sha256(wav)
    media_fingerprint = _media_fingerprint(
        normalized_wav_sha256, spans, runtime_provenance
    )
    run_dir = job_dir / "runs" / active_run
    rows = _transcribe_segments(
        wav,
        spans,
        run_dir,
        runtime,
        runtime_provenance,
        media_fingerprint,
        runner,
    )
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
            "source_audio_path": str(audio),
            "source_audio_sha256": source_audio_sha256,
            "normalized_wav_path": str(wav),
            "normalized_wav_sha256": normalized_wav_sha256,
            "media_fingerprint": media_fingerprint,
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


def prepare_transcript(
    url: str,
    output_root: Path | str,
    runtime_root: Path | str,
    *,
    runner: Runner | None = None,
    rerun_asr: bool = False,
    process_timeout_seconds: int = 1800,
) -> PreparationResult:
    if process_timeout_seconds <= 0:
        raise ValueError("process timeout must be a positive number of seconds")
    target = parse_bilibili_url(url)
    output_path = _prepare_output_root(Path(output_root))
    runtime_path = Path(runtime_root).resolve()
    job_dir = _job_directory(runtime_path, output_path, target)
    _ensure_ascii(job_dir)
    selected_runner = runner or (
        lambda command: _default_runner(
            command, timeout_seconds=process_timeout_seconds
        )
    )
    with exclusive_job_lock(job_dir / "job.lock"):
        return _prepare_transcript_locked(
            url,
            output_path,
            runtime_root,
            runner=selected_runner,
            rerun_asr=rerun_asr,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare immutable SenseVoiceSmall evidence for one Bilibili video."
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--rerun-asr", action="store_true")
    parser.add_argument("--process-timeout-seconds", type=int, default=1800)
    args = parser.parse_args()
    runtime_root = (
        args.runtime_root if args.runtime_root is not None else default_runtime_root()
    )
    result = prepare_transcript(
        args.url,
        args.output_root,
        runtime_root,
        rerun_asr=args.rerun_asr,
        process_timeout_seconds=args.process_timeout_seconds,
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
