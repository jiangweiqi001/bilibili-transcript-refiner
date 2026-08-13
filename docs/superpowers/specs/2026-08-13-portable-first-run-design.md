# Portable First-Run Design

## Goal

Make the public Skill run from a fresh Windows 10 or 11 x64 Codex installation when the user has no ASR model, yt-dlp, or FFmpeg installed and the Windows profile path may contain non-ASCII characters. Keep the existing AVX2 performance baseline and fail clearly on unsupported CPUs.

## Scope

- Repair the stale FunASR release-asset digest that blocks fresh installation.
- Make the bootstrap and Python entry points select the same writable ASCII runtime root automatically.
- Make every workflow command resolve bundled files from the Skill directory instead of the caller's current working directory.
- Document installation, prerequisites, first-run downloads, storage, and compatibility boundaries.
- Add regression coverage for local behavior and remote asset metadata.
- Verify a clean bootstrap and one real public Bilibili ASR preparation before release.

Do not add Linux or macOS support, switch ASR models, polish transcripts, redesign the output contract, or package a plugin in this change.

## Runtime layout

Use one deterministic selection rule in both PowerShell and Python:

1. Use `%LOCALAPPDATA%\bilibili-transcript-refiner\runtime-v1` when the full path is ASCII.
2. Otherwise use `%PUBLIC%\bilibili-transcript-refiner\users\<user-key>\runtime-v1`, where `<user-key>` is the first 16 lowercase hex characters of SHA-256 over the normalized `%LOCALAPPDATA%` path encoded as UTF-8.
3. Reject the fallback when `%PUBLIC%` is missing, non-ASCII, or not writable, and instruct the caller to pass an explicit ASCII `-RuntimeRoot` or `--runtime-root`.

The per-user key prevents different Windows accounts from sharing job state. The bootstrap prints the selected manifest path. `prepare_transcript.py` independently selects the identical default so the workflow does not need to copy an implicit path between commands. Explicit runtime-root arguments always win.

## Skill-relative invocation

At the start of the workflow, resolve the absolute directory containing the active `SKILL.md` as `<SKILL_DIR>`. Read references and invoke scripts using absolute paths under `<SKILL_DIR>`. Never assume that the shell current working directory is the Skill directory.

Keep the existing command interfaces. Quote every path so spaces and non-ASCII characters in the Skill installation path or output root remain valid.

## Bootstrap and compatibility errors

Keep one tracked `scripts/runtime-assets.json` manifest containing each asset's name, version, provider, URL, byte size, and SHA-256 digest. Make both the bootstrap and remote verifier read this manifest so runtime pins have a single source of truth. Keep pinned HTTPS URLs and SHA-256 validation. Replace the stale FunASR AVX2 archive digest with the digest published by the current GitHub release asset.

Preserve partial downloads for diagnosis when validation fails. Add contextual failures for:

- a missing or unwritable runtime parent;
- insufficient free disk space before large downloads;
- network or TLS download failure;
- a FunASR AVX2 executable that cannot start, including the AVX2/FMA/F16C/BMI2 CPU requirement and security-software possibility.

Do not silently weaken digest checks or fall back to an unpinned dependency.

## Remote asset drift detection

Add a PowerShell verification script that reads the pinned runtime assets and checks remote metadata without downloading the model bodies:

- use GitHub release API asset digests for GitHub-hosted files;
- use Hugging Face LFS response metadata for GGUF files;
- compare both size and SHA-256 where the provider publishes them.

Run this check in GitHub Actions on pushes, pull requests, manual dispatch, and a scheduled cadence. A provider outage may fail this dedicated check visibly; it must not cause the local runtime to skip integrity verification.

## Documentation

Expand `README.md` with:

- installation through Codex's skill installer or the user skill directory;
- Windows 10/11 x64, Python 3.11+, PowerShell 5.1+, internet access, and AVX2-class CPU prerequisites;
- the approximately 372 MiB first download and approximately 700 MiB base installed footprint;
- automatic SenseVoiceSmall, VAD, FunASR, FFmpeg, and yt-dlp setup;
- the Unicode-profile fallback and explicit runtime-root escape hatch;
- one invocation example.

Keep `SKILL.md` concise and agent-facing. Put user setup details in the existing README rather than adding another guide.

## Tests and acceptance

Follow RED-GREEN-REFACTOR:

1. Make static contracts fail on the new FunASR digest, Skill-root resolution rule, documented prerequisites, and remote-check workflow.
2. Add executable tests for identical runtime-root selection under ASCII and non-ASCII profiles.
3. Add focused tests for explicit runtime-root precedence and actionable AVX2 startup failure.
4. Implement the minimum changes that pass the new tests.
5. Run the complete Python and PowerShell suite plus Skill package validation.
6. Bootstrap into a new empty runtime directory and run `-VerifyOnly` afterward.
7. From a working directory outside the Skill, prepare ASR evidence for one short public Bilibili video into a Unicode output path.
8. Confirm the formal repository is clean except for intended changes, commit them, and push `main` to `origin` only after all checks pass.

## Release boundary

This release makes direct standalone Skill installation reliable on the supported Windows baseline. Plugin packaging and a non-AVX2 compatible runtime variant remain separate follow-up work.
