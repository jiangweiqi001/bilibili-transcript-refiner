# Reliability v1.1 Design

## Goal

Move the public Skill from a working beta toward a distributable, resumable, and auditable release without expanding into batch processing or subtitle production.

## Decisions

- License the repository under MIT using the public GitHub identity `jiangweiqi001`, and document every runtime dependency separately. The repository does not redistribute those binaries or models; bootstrap downloads them from upstream.
- Pin Hugging Face model URLs to immutable repository commits. Keep archive and model SHA-256 checks, and additionally pin the hashes of the extracted executables used at runtime.
- Give every Python-launched external command a configurable finite timeout. Give bootstrap downloads and startup probes independent finite timeouts and terminate timed-out startup probes.
- Quarantine malformed per-segment ASR checkpoints inside the active run, then recompute only that segment. Never delete the malformed evidence.
- Add a correction checkpoint CLI that validates the existing prefix and the next batch against immutable raw timestamps, audits semantic risk, and atomically replaces the whole checkpoint file. Direct in-place append is forbidden.
- Audit the ordered sequence of protected tokens (numbers, percentages, money, complete dates, and Latin identifiers), major deletion, and large rewrites, including short rows. Save a deterministic JSON report in the job directory. Finalization rejects high-risk changes unless the caller explicitly confirms that those rows were reviewed against audio.
- Preserve exactly two formal deliverables. Put correction audit state and internal logs in the runtime job directory.
- Add generation time, raw evidence hash, model revision/hash, and tool versions to corrected Markdown frontmatter.
- Test Python 3.11, 3.12, and 3.13. Run remote metadata and Windows contract checks once, and run a cached real bootstrap plus `VerifyOnly` only for weekly/manual CI.

## Components

### Correction contract and checkpoint CLI

`scripts/correction_contract.py` owns correction parsing, pairing, risk detection, audit rendering, and atomic JSONL writes. `scripts/checkpoint_corrections.py` accepts `--raw`, `--checkpoint`, and `--batch`, locks the job, validates that the existing file is an exact prefix, validates that the batch starts at the first missing raw row, writes the checkpoint atomically, refreshes `correction-audit.json`, and prints progress JSON.

The finalizer uses the same contract and high-risk findings fail closed by default. The original v1.1 global acknowledgement design is superseded by the finding-level, hash-bound audio-review contract in `2026-08-14-must-fix-v1-1-1-design.md`.

### Runtime provenance and integrity

`runtime-assets.json` records immutable source revisions and expected extracted-file hashes. Bootstrap verifies these hashes on both install and `VerifyOnly`, then writes a schema-v2 `runtime.json` containing source versions, revisions, hashes, installed paths, and generated time. Preparation copies the relevant provenance into `job.json`, binds VAD and ASR checkpoints to deterministic runtime fingerprints, and starts a fresh run when provenance changes; finalization renders the recorded provenance without consulting mutable external state.

### Failure recovery

Python timeout errors name the operation and timeout value. Bootstrap timeout errors name the asset or executable. Segment checkpoint parse, schema, boundary, and empty-text errors move the offending file to a `quarantine` directory with a unique name before recomputation.

## Compatibility

The public CLI remains a single full Bilibili BV URL and one page per invocation. Formal directory naming and the two-file rule do not change. Existing schema-v1 runtimes must rerun bootstrap; existing prepared jobs without provenance must rerun ASR before finalization.

## Acceptance

- Unit tests demonstrate RED/GREEN coverage for atomic correction prefixes, risk audit, timeout conversion, corrupted checkpoint recovery, provenance output, and extracted-file verification.
- Static Skill checks require the new deterministic checkpoint command and forbid documentation that asks an agent to append checkpoint JSONL directly.
- All local Python tests, PowerShell contract tests, Skill validation, runtime metadata verification, and diff hygiene pass before push.
