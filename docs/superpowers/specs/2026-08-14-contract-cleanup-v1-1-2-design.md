# Contract Cleanup v1.1.2 Design

## Goal

Remove contradictions and meaningless repetition from the Skill package while preserving the v1.1.1 integrity gates.

## Decisions

### Explicitly inaudible rows

A corrected row containing exactly one `[听不清]` marker, with only Unicode whitespace or punctuation around it, is a non-assertive disclosure rather than a claim that the raw words were deleted. Its uncertainty list must contain exactly the matching marker and note. Letters, numbers, Han characters, emoji, mathematical or currency symbols, control or zero-width characters, `[疑似：…]`, and extra semantic content make the row ineligible. The correction audit records one `explicit-inaudible-substitution` informational finding and, for that row only, replaces protected-token, deletion, and rewrite findings. A formal transcript containing such a row must use `status: incomplete` with a reason; `status: complete` rejects it even if old review evidence exists. Partial rows that mix ordinary text with `[听不清]` receive no exemption and retain normal protected-token and semantic-loss auditing.

Every raw row still requires one timestamp-matched correction row. `incomplete` describes reliability, not a correction-file prefix.

Local `[疑似：…]` or `[听不清]` markers inside otherwise meaningful text may still appear in `complete` after all normal gates pass. Only a whole-row explicit inaudible substitution forces `incomplete`. Other high-risk findings in an incomplete job keep the existing hash-bound audio-review requirement.

### Review timing

Each correction checkpoint refreshes the audit. During batching, the agent uses findings to revise unjustified changes but does not persist audio confirmations yet, because the review state is bound to the SHA-256 of the entire correction file. After all rows are installed and the checkpoint is stable, the agent lists current findings, replays each returned clip, and records finding-level confirmations once. Any later replacement or append invalidates those reviews and requires the final review pass again.

### Documentation ownership

- `SKILL.md` owns orchestration, required inputs, and non-bypassable gates.
- `references/faithful-correction.md` owns semantic correction judgment and uncertainty policy.
- `references/output-contract.md` owns JSONL/Markdown formats, exact CLI examples, and state semantics.
- `README.md` remains public-facing and must not become an alternative operational specification.

Operational commands may appear in `SKILL.md` and `output-contract.md` because an agent needs the workflow and the contract needs executable examples. Fidelity prohibitions should not be repeated again as common mistakes.

### Accuracy fixes

- Keep the Markdown example's `vad_model_version: "6840bae"`; it matches the pinned production asset. The `main` value in finalizer tests is synthetic fixture data, not a release value.
- Persistent metadata, clips, logs, archives, and resumable partial state stay under the runtime root. Atomic installation may briefly create an owned temporary beside a formal target. Only the corrected-transcript finalizer's own stale formal partial is quarantined on retry, and successful delivery still contains exactly two files.
- Raw ASR text is semantically preserved after SenseVoice control-tag removal and surrounding-whitespace trimming; the documentation no longer claims byte-for-byte preservation before those normalization steps.

## Acceptance

- A focused test first demonstrates that `[听不清]` currently becomes high risk, then proves the strict informational-finding behavior and rejects semantic, emoji, symbol, and zero-width additions.
- Focused finalizer tests first demonstrate that the incomplete path is blocked, then prove incomplete succeeds without an impossible acoustic confirmation, complete fails closed, ordinary high-risk findings remain gated, and correction prefixes remain invalid.
- Static contract tests first fail on ambiguous review timing, the inaccurate partial-file claim, the byte-for-byte overstatement, and duplicated fidelity bullets.
- The full Python suite, PowerShell contracts, Skill validation, diff hygiene, and GitHub Actions pass.
