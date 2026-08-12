"""Deterministic data contracts for Bilibili transcript evidence."""

from __future__ import annotations

import json
import os
import re
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable, Iterator, Sequence
from urllib.parse import parse_qs, urlparse


_BVID_RE = re.compile(r"/video/(BV[A-Za-z0-9]{10})(?:/|$)")
_TIMESTAMP_RE = re.compile(r"^(\d{2,}):(\d{2}):(\d{2})\.(\d{3})$")
_RAW_KEYS = ["start", "end", "text"]


def _lock_byte(handle: BinaryIO, *, unlock: bool = False) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        mode = msvcrt.LK_UNLCK if unlock else msvcrt.LK_NBLCK
        msvcrt.locking(handle.fileno(), mode, 1)
        return

    import fcntl  # pragma: no cover - the published Skill targets Windows.

    mode = fcntl.LOCK_UN if unlock else fcntl.LOCK_EX | fcntl.LOCK_NB
    fcntl.flock(handle.fileno(), mode)


@contextmanager
def exclusive_job_lock(path: Path | str) -> Iterator[None]:
    """Hold a process-level lock for one transcript job, releasing it on crashes."""

    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    acquired = False
    try:
        if lock_path.stat().st_size == 0:
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            _lock_byte(handle)
            acquired = True
        except OSError as exc:
            raise RuntimeError(
                f"transcript job is already running: {lock_path.parent}"
            ) from exc
        yield
    finally:
        if acquired:
            _lock_byte(handle, unlock=True)
        handle.close()


@dataclass(frozen=True)
class BilibiliTarget:
    bvid: str
    page: int = 1

    @property
    def canonical_url(self) -> str:
        return f"https://www.bilibili.com/video/{self.bvid}/?p={self.page}"


@dataclass(frozen=True)
class Segment:
    start_ms: int
    end_ms: int
    text: str

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("segment timestamps must be nonnegative and increasing")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("segment text must be nonempty")

    def to_record(self) -> dict[str, str]:
        return {
            "start": format_timestamp(self.start_ms),
            "end": format_timestamp(self.end_ms),
            "text": self.text,
        }


def parse_bilibili_url(url: str) -> BilibiliTarget:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not (
        host == "bilibili.com" or host.endswith(".bilibili.com")
    ):
        raise ValueError("URL must use a Bilibili host")

    match = _BVID_RE.search(parsed.path)
    if not match:
        raise ValueError("URL must contain a valid BV identifier")

    raw_pages = parse_qs(parsed.query).get("p", ["1"])
    try:
        page = int(raw_pages[0])
    except (TypeError, ValueError) as exc:
        raise ValueError("page must be a positive integer") from exc
    if page < 1:
        raise ValueError("page must be a positive integer")
    return BilibiliTarget(match.group(1), page)


def output_name(bvid: str, page: int) -> str:
    if page < 1:
        raise ValueError("page must be a positive integer")
    return bvid if page == 1 else f"{bvid}-p{page:02d}"


def format_timestamp(milliseconds: int) -> str:
    if milliseconds < 0:
        raise ValueError("timestamp cannot be negative")
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def parse_timestamp(value: str) -> int:
    match = _TIMESTAMP_RE.fullmatch(value)
    if not match:
        raise ValueError(f"invalid timestamp: {value!r}")
    hours, minutes, seconds, millis = (int(part) for part in match.groups())
    if minutes >= 60 or seconds >= 60:
        raise ValueError(f"invalid timestamp: {value!r}")
    return ((hours * 60 + minutes) * 60 + seconds) * 1_000 + millis


def validate_segments(rows: Sequence[Segment]) -> None:
    previous: Segment | None = None
    for row in rows:
        if previous is not None:
            if row.start_ms < previous.start_ms:
                raise ValueError("segments must be ordered by start time")
            if row.start_ms < previous.end_ms:
                raise ValueError("segments must not overlap")
        previous = row


def validate_coverage(
    vad_spans: Sequence[tuple[int, int]], rows: Sequence[Segment]
) -> None:
    if len(vad_spans) != len(rows):
        raise ValueError("VAD and ASR segment count must match")
    validate_segments(rows)
    for index, ((start_ms, end_ms), row) in enumerate(zip(vad_spans, rows)):
        if (start_ms, end_ms) != (row.start_ms, row.end_ms):
            raise ValueError(f"ASR segment {index} boundaries do not match VAD")


def _segment_from_record(record: object, line_number: int) -> Segment:
    if not isinstance(record, dict) or list(record.keys()) != _RAW_KEYS:
        raise ValueError(f"line {line_number} must contain exact keys: {_RAW_KEYS}")
    return Segment(
        parse_timestamp(record["start"]),
        parse_timestamp(record["end"]),
        record["text"],
    )


def read_jsonl(path: Path | str) -> list[Segment]:
    source = Path(path)
    rows: list[Segment] = []
    with source.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise ValueError(f"line {line_number} is empty")
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_number} is not valid JSON") from exc
            rows.append(_segment_from_record(record, line_number))
    validate_segments(rows)
    return rows


def write_jsonl_atomic(
    path: Path | str,
    rows: Iterable[Segment],
    *,
    allow_replace: bool = False,
) -> None:
    destination = Path(path)
    materialized = list(rows)
    validate_segments(materialized)
    if destination.exists() and not allow_replace:
        raise FileExistsError(f"refusing to replace transcript evidence: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(
        f"{destination.name}.partial-{uuid.uuid4().hex}"
    )
    try:
        with partial.open("x", encoding="utf-8", newline="\n") as handle:
            for row in materialized:
                handle.write(
                    json.dumps(row.to_record(), ensure_ascii=False, separators=(",", ":"))
                )
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if allow_replace:
            os.replace(partial, destination)
        elif os.name == "nt":
            os.rename(partial, destination)
        else:  # pragma: no cover - the published Skill targets Windows.
            os.link(partial, destination)
            partial.unlink()
    finally:
        if partial.exists():
            partial.unlink()
