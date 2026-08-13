"""List and durably record finding-level correction audio reviews."""

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

try:
    from scripts.correction_contract import read_corrections, write_audit_report
    from scripts.transcript_contract import exclusive_job_lock, read_jsonl
except ModuleNotFoundError:  # Direct execution from scripts/.
    from correction_contract import read_corrections, write_audit_report  # type: ignore
    from transcript_contract import exclusive_job_lock, read_jsonl  # type: ignore


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8-sig"))


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


def _current_audit(job_dir: Path) -> tuple[dict[str, object], dict[str, object]]:
    job_value = _read_json(job_dir / "job.json")
    if not isinstance(job_value, dict):
        raise ValueError("job metadata is invalid")
    raw_path = Path(str(job_value.get("raw_path", ""))).resolve()
    corrections_path = job_dir / "corrections.jsonl"
    if not raw_path.is_file() or not corrections_path.is_file():
        raise FileNotFoundError("raw transcript or correction checkpoint is missing")
    raw_rows = read_jsonl(raw_path)
    corrections = read_corrections(corrections_path)
    audit = write_audit_report(
        job_dir / "correction-audit.json",
        raw_path,
        corrections_path,
        raw_rows,
        corrections,
    )
    return job_value, audit


def _high_risk_with_clips(
    job_dir: Path, job_value: dict[str, object], audit: dict[str, object]
) -> list[dict[str, object]]:
    active_run = job_value.get("active_run")
    if not isinstance(active_run, str) or not re.fullmatch(
        r"run-[A-Za-z0-9-]+", active_run
    ):
        raise ValueError("job does not identify the active ASR run")
    clips_dir = (job_dir / "runs" / active_run / "clips").resolve()
    findings = audit.get("findings")
    if not isinstance(findings, list):
        raise ValueError("correction audit findings are invalid")
    result: list[dict[str, object]] = []
    for item in findings:
        if not isinstance(item, dict) or item.get("severity") != "high":
            continue
        row_index = item.get("row_index")
        finding = item.get("finding_id")
        if not isinstance(row_index, int) or not isinstance(finding, str):
            raise ValueError("correction audit finding is invalid")
        clip = (clips_dir / f"{row_index:06d}.wav").resolve()
        if not clip.is_relative_to(clips_dir) or not clip.is_file():
            raise FileNotFoundError(
                f"review audio clip is missing for correction row {row_index}: {clip}"
            )
        enriched = dict(item)
        enriched["clip_path"] = str(clip)
        enriched["clip_sha256"] = _sha256(clip)
        result.append(enriched)
    return result


def list_review_findings(job_dir: Path | str) -> list[dict[str, object]]:
    resolved = Path(job_dir).resolve()
    with exclusive_job_lock(resolved / "job.lock"):
        job_value, audit = _current_audit(resolved)
        return _high_risk_with_clips(resolved, job_value, audit)


def _archive_stale_reviews(path: Path, job_dir: Path) -> None:
    if not path.is_file():
        return
    archive = job_dir / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    target = archive / f"{path.name}.stale-{stamp}-{uuid.uuid4().hex[:8]}"
    shutil.move(str(path), str(target))


def record_finding_review(
    job_dir: Path | str,
    finding_id: str,
    *,
    decision: str,
    note: str,
) -> dict[str, object]:
    resolved = Path(job_dir).resolve()
    if decision != "confirmed":
        raise ValueError("review decision must be confirmed; revise corrections otherwise")
    if not isinstance(note, str) or not note.strip() or "\n" in note or "\r" in note:
        raise ValueError("review note must be nonempty and stay on one line")
    with exclusive_job_lock(resolved / "job.lock"):
        job_value, audit = _current_audit(resolved)
        findings = _high_risk_with_clips(resolved, job_value, audit)
        current = next(
            (item for item in findings if item["finding_id"] == finding_id), None
        )
        if current is None:
            raise ValueError("finding ID is not a current high-risk correction finding")
        reviews_path = resolved / "correction-reviews.json"
        reviews: list[dict[str, object]] = []
        if reviews_path.is_file():
            old = _read_json(reviews_path)
            if (
                isinstance(old, dict)
                and old.get("schema_version") == 1
                and old.get("raw_sha256") == audit["raw_sha256"]
                and old.get("corrections_sha256") == audit["corrections_sha256"]
                and isinstance(old.get("reviews"), list)
            ):
                reviews = [item for item in old["reviews"] if isinstance(item, dict)]
            else:
                _archive_stale_reviews(reviews_path, resolved)
        reviewed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        record = {
            "finding_id": finding_id,
            "row_index": current["row_index"],
            "code": current["code"],
            "decision": decision,
            "note": note.strip(),
            "clip_path": current["clip_path"],
            "clip_sha256": current["clip_sha256"],
            "reviewed_at": reviewed_at,
        }
        reviews = [item for item in reviews if item.get("finding_id") != finding_id]
        reviews.append(record)
        value = {
            "schema_version": 1,
            "raw_sha256": audit["raw_sha256"],
            "corrections_sha256": audit["corrections_sha256"],
            "reviews": sorted(reviews, key=lambda item: str(item["finding_id"])),
        }
        _write_json_atomic(reviews_path, value)
        return record


def validate_finding_reviews(
    job_dir: Path | str, audit: dict[str, object]
) -> int:
    resolved = Path(job_dir).resolve()
    job_value = _read_json(resolved / "job.json")
    if not isinstance(job_value, dict):
        raise ValueError("job metadata is invalid")
    current = _high_risk_with_clips(resolved, job_value, audit)
    if not current:
        return 0
    reviews_path = resolved / "correction-reviews.json"
    if not reviews_path.is_file():
        raise ValueError(
            f"{len(current)} unreviewed high-risk correction finding(s); "
            "record finding-level audio reviews first"
        )
    value = _read_json(reviews_path)
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or value.get("raw_sha256") != audit.get("raw_sha256")
        or value.get("corrections_sha256") != audit.get("corrections_sha256")
        or not isinstance(value.get("reviews"), list)
    ):
        raise ValueError(
            f"{len(current)} unreviewed high-risk correction finding(s); "
            "stored reviews do not match current evidence hashes"
        )
    reviews = {
        item.get("finding_id"): item
        for item in value["reviews"]
        if isinstance(item, dict) and item.get("decision") == "confirmed"
    }
    missing = 0
    for finding in current:
        review = reviews.get(finding["finding_id"])
        if (
            not isinstance(review, dict)
            or review.get("clip_path") != finding["clip_path"]
            or review.get("clip_sha256") != finding["clip_sha256"]
        ):
            missing += 1
    if missing:
        raise ValueError(
            f"{missing} unreviewed high-risk correction finding(s); "
            "record current finding-level audio reviews first"
        )
    return len(current)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List or record finding-level correction audio reviews."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--job-dir", required=True, type=Path)
    record_parser = subparsers.add_parser("record")
    record_parser.add_argument("--job-dir", required=True, type=Path)
    record_parser.add_argument("--finding-id", required=True)
    record_parser.add_argument("--decision", required=True, choices=("confirmed",))
    record_parser.add_argument("--note", required=True)
    args = parser.parse_args()
    if args.command == "list":
        value: object = {"findings": list_review_findings(args.job_dir)}
    else:
        value = record_finding_review(
            args.job_dir,
            args.finding_id,
            decision=args.decision,
            note=args.note,
        )
    print(json.dumps(value, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
