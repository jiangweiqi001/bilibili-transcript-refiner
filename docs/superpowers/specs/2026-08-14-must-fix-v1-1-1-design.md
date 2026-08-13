# Must-fix v1.1.1 Design

## Goal

Close only the six release-blocking gaps found after reliability v1.1: reversible correction checkpoints, finding-level audio review, runtime/media integrity, private Windows fallback storage, recoverable caches with early output validation, and executable installation/runtime-root guidance.

## Decisions

- Keep correction checkpoints hash-guarded and atomic. Add an explicit replacement path so an accepted row can be revised without editing JSONL by hand or discarding later work accidentally.
- Give every high-risk finding a deterministic ID derived from the current raw evidence, correction evidence, row, rule, and before/after text. Audio review is stored per finding and is valid only for the exact current raw/corrections hashes. A global acknowledgement flag cannot authorize finalization.
- Resolve each finding to its exact segment WAV. Finalization succeeds only when every current high-risk finding has a durable `confirmed` review record; changing corrections invalidates old reviews by hash.
- Re-hash every executable and model artifact named by `runtime.json` before use, and reject paths outside the selected runtime root. Bind clips and ASR checkpoints to the normalized WAV/VAD fingerprint so same-duration replacement audio cannot reuse stale text.
- Record source-audio and normalized-WAV SHA-256 values in job state and formal provenance.
- Protect the selected Windows runtime directory with an explicit DACL granting full control only to the current user, SYSTEM, and Administrators. Apply and verify the ACL before bootstrap creates or trusts runtime assets.
- Treat corrupt metadata, VAD state, source audio, and normalized WAV as recoverable cache failures: quarantine the bad artifact, then refetch or recompute it. Probe output-root creation and writability before any network or ASR work.
- Make the stock root-repository installer invocation explicit (`--path . --name bilibili-transcript-refiner`). Select one runtime root and carry it through both bootstrap and preparation commands.

## Compatibility and boundaries

- Keep the single Bilibili BV URL input, single-page workflow, formal directory naming, and exactly-two-deliverables rule.
- Preserve valid existing jobs where their integrity bindings still match. Legacy review acknowledgements and unbound clip/segment checkpoints fail closed and must be regenerated or reviewed.
- Do not add platforms, architectures, cookie flows, batch processing, subtitle export, GUI, or unrelated README features in this release.

## Acceptance

- Focused tests first reproduce each old failure, including short high-risk corrections, stale same-duration media, tampered runtime files, corrupt caches, unwritable output roots, insecure inherited ACLs, and root-Skill installer/runtime-root instructions.
- Finalization cannot be unlocked by a bare global flag and can be unlocked by current per-finding audio reviews.
- The full Python suite, PowerShell contracts, Skill validator, runtime asset validator, diff hygiene, and GitHub CI pass before release.
