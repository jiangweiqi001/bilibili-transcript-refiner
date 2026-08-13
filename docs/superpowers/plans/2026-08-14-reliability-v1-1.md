# Reliability v1.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Skill legally reusable, mechanically resumable, timeout-bounded, supply-chain pinned, provenance-rich, and correction-risk auditable.

**Architecture:** Put reusable correction invariants in one Python contract module shared by checkpointing and finalization. Carry immutable runtime provenance from the pinned asset manifest through `runtime.json` and `job.json` into the formal Markdown. Keep all audit and recovery artifacts outside the two-file formal directory.

**Tech Stack:** Python 3.11-3.13 standard library, Windows PowerShell 5.1, GitHub Actions, JSON/JSONL, Markdown.

---

### Task 1: Establish correction checkpoint and audit behavior

**Files:**
- Create: `scripts/correction_contract.py`
- Create: `scripts/checkpoint_corrections.py`
- Create: `tests/test_correction_contract.py`
- Modify: `tests/test_finalize_transcript.py`
- Modify: `scripts/finalize_transcript.py`

- [ ] Write failing tests for exact-prefix validation, atomic batch installation, protected-token changes, major deletion, large rewrite, and finalizer rejection without acknowledgement.
- [ ] Run the focused tests and confirm failures are caused by missing APIs.
- [ ] Implement correction records, JSONL parsing/writing, pairing, risk findings, audit JSON, and the checkpoint CLI.
- [ ] Refactor the finalizer to consume the shared contract and require explicit high-risk acknowledgement.
- [ ] Run focused tests and the complete Python suite.

### Task 2: Bound processes and recover corrupt ASR checkpoints

**Files:**
- Modify: `scripts/prepare_transcript.py`
- Modify: `tests/test_prepare_transcript.py`

- [ ] Write failing tests proving `subprocess.run` receives a timeout, timeout exceptions become labelled runtime errors, and malformed segment checkpoints are quarantined and recomputed.
- [ ] Run the focused tests and confirm the expected failures.
- [ ] Add a positive `--process-timeout-seconds` option with a 1,800-second default and quarantine invalid segment checkpoints without deleting them.
- [ ] Run focused tests and the complete Python suite.

### Task 3: Pin and verify runtime provenance

**Files:**
- Modify: `scripts/runtime-assets.json`
- Modify: `scripts/bootstrap_runtime.ps1`
- Modify: `scripts/prepare_transcript.py`
- Modify: `scripts/finalize_transcript.py`
- Modify: `tests/verify-runtime-assets.ps1`
- Modify: `tests/test_finalize_transcript.py`
- Modify: `tests/static-contract.ps1`

- [ ] Add failing contract checks for immutable Hugging Face revisions, expanded executable hashes, schema-v2 runtime provenance, and formal frontmatter fields.
- [ ] Pin both model revisions and record verified hashes for `ffmpeg.exe`, `ffprobe.exe`, and both FunASR executables.
- [ ] Verify expanded files on every bootstrap, bound downloads and startup probes, and write structured runtime provenance.
- [ ] Carry provenance into the job and render generation time, raw SHA-256, model revision/hash, tool versions, and high-risk acknowledgement.
- [ ] Run Python and PowerShell contract tests.

### Task 4: Update the Skill and public/legal documentation

**Files:**
- Create: `LICENSE`
- Create: `THIRD_PARTY_NOTICES.md`
- Modify: `SKILL.md`
- Modify: `README.md`
- Modify: `references/faithful-correction.md`
- Modify: `references/output-contract.md`
- Modify: `tests/static-contract.ps1`

- [ ] Add failing static checks requiring the checkpoint CLI and forbidding direct checkpoint append instructions.
- [ ] Add the MIT license and upstream dependency notices with source and license links.
- [ ] Replace manual append guidance with deterministic batch checkpointing, audit review, and acknowledgement rules.
- [ ] Document timeouts, recovery, provenance, and the schema-v1 migration boundary while retaining the required README first line.
- [ ] Run static and package validation.

### Task 5: Expand CI and verify release

**Files:**
- Modify: `.github/workflows/test.yml`

- [ ] Add Python 3.11-3.13 matrix jobs and keep Windows/online checks in one job.
- [ ] Add a cached weekly/manual real bootstrap job that runs bootstrap followed by `VerifyOnly`.
- [ ] Run all unit tests, PowerShell parity/static/asset checks, Skill validation, and `git diff --check`.
- [ ] Review the complete diff against every design decision, commit the implementation, push the feature branch, and merge/push `main` after review passes.
