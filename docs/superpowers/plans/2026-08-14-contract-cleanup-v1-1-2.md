# Contract Cleanup v1.1.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Skill, references, and executable behavior internally consistent without weakening complete-transcript safety.

**Architecture:** Classify whole-row inaudibility in the shared correction contract, then let the finalizer enforce status semantics. Keep executable formats in the output contract, semantic judgment in the correction policy, and only orchestration plus core gates in SKILL.md.

**Tech Stack:** Python 3.11-3.13 standard library, Windows PowerShell 5.1, Markdown, JSON/JSONL.

---

### Task 1: Define whole-row inaudibility semantics

**Files:**
- Modify: `scripts/correction_contract.py`
- Modify: `tests/test_correction_contract.py`

- [ ] Add `test_whole_row_inaudible_marker_is_informational_not_high_risk` using a protected numeric raw row and corrected punctuation plus exactly one `[听不清]`; assert one `explicit-inaudible-substitution` finding with severity `info` and no deletion/rewrite/protected-token high finding.
- [ ] Run `python -X utf8 -m unittest tests.test_correction_contract.CorrectionCheckpointTests.test_whole_row_inaudible_marker_is_informational_not_high_risk` and confirm it fails because the current audit emits `major-deletion`.
- [ ] Add a focused helper that recognizes exactly one listed/visible `[听不清]` with only Unicode whitespace or punctuation around it; emit the informational finding and skip the assertion-oriented rules only for that row.
- [ ] Add companion subtests proving ordinary text, numbers, emoji, mathematical/currency symbols, controls, zero-width characters, `[疑似：…]`, and duplicate markers are ineligible, and that partial ordinary text plus `[听不清]` retains normal auditing.
- [ ] Run `python -X utf8 -m unittest tests.test_correction_contract` and commit.

### Task 2: Enforce incomplete status for whole-row inaudibility

**Files:**
- Modify: `scripts/finalize_transcript.py`
- Modify: `tests/test_finalize_transcript.py`

- [ ] Add a finalization test with one timestamp-matched `[听不清]` row and its uncertainty note. Assert `status=complete` rejects it with an incomplete-status message, while `status=incomplete` with a reason succeeds without `correction-reviews.json`.
- [ ] Run the focused test and confirm the incomplete call currently fails because the audit requests an impossible high-risk audio review.
- [ ] Reuse the shared whole-row classification in `render_corrected`; reject complete before writing and retain full-row pairing for incomplete. Add coverage that another ordinary high-risk row still needs a current review and that a correction prefix is still rejected.
- [ ] Run `python -X utf8 -m unittest tests.test_finalize_transcript tests.test_correction_contract` and commit.

### Task 3: Make the documentation contract single-valued

**Files:**
- Modify: `tests/static-contract.ps1`
- Modify: `SKILL.md`
- Modify: `references/faithful-correction.md`
- Modify: `references/output-contract.md`
- Modify: `README.md` only if public wording contradicts the final contract

- [ ] Add static failures requiring final-review timing, full-row incomplete semantics, accurate atomic-temporary wording, and ASR normalization wording; forbid the stale phrases and duplicated fidelity bullets.
- [ ] Run `powershell -NoProfile -ExecutionPolicy Bypass -File tests/static-contract.ps1` and confirm it fails on the current documents.
- [ ] Shorten `SKILL.md` common mistakes to operational mistakes, point detailed correction decisions to `faithful-correction.md`, and state that reviews are recorded only after the checkpoint is complete and stable.
- [ ] Keep policy reasoning in `faithful-correction.md`; move exact replacement/review command details to `output-contract.md` and explicitly define the `[听不清]` incomplete path.
- [ ] Keep the production VAD example unchanged; correct the temporary/raw-normalization claims in `output-contract.md`; update README only where it describes review timing or incomplete semantics.
- [ ] Run static contract, `python -X utf8 tests/quick_validate_skill.py .`, and `git diff --check`; commit.

### Task 4: Release verification

- [ ] Run at least 77 Python tests, runtime layout/ACL/static PowerShell tests, remote asset verification, Skill validation, CLI help checks, and `git diff --check`.
- [ ] Review the diff against the four reported contradictions and the single-source ownership decision.
- [ ] Fast-forward merge into `main`, rerun the local suite, push GitHub, and wait for Python 3.11/3.12/3.13 plus Windows contracts to succeed.
