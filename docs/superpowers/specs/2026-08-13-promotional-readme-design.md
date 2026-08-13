# Promotional README Design

## Goal

Turn the repository README into a credible, shareable landing page for people who both need faithful Bilibili transcripts and are willing to use Codex or GitHub tooling.

## Required opening

The first line of `README.md` must be exactly:

```text
点点关注谢谢喵
```

No badge, heading, comment, or blank line may precede it.

## Positioning

Lead with the outcome: provide one complete Bilibili BV URL and receive timestamped raw ASR evidence plus a faithful corrected transcript. Present the project as a reproducible transcript workflow rather than a generic downloader, summarizer, or subtitle beautifier.

The tone should be energetic and approachable enough to share, while every concrete claim remains supported by the implementation or completed acceptance tests. Do not claim that the entire Codex workflow is offline, that all computers are supported, or that every Bilibili video can bypass login and anti-abuse controls.

Use Bilibili-native emotional language where it creates recognition: the opening may reference saved long videos, progress-bar scrubbing, UP creators, class representatives, and one-click triple support. Keep that voice concentrated in the introduction, use cases, and closing call to action; the technical middle should remain precise and professional. Explicitly say the project does not produce a generic “省流版”.

## Audience path

The README should serve two overlapping readers without splitting into separate documents:

1. A transcript user should understand the result, fidelity rules, typical use cases, and example output before reaching installation details.
2. A technical reader should quickly find prerequisites, automatic dependency behavior, installation commands, runtime storage, Unicode-profile behavior, and verification status.

## Content structure

Use this order:

1. Mandatory opening line, project title, concise value proposition, and lightweight badges.
2. A short “what problem this solves” section contrasting faithful transcripts with summaries or polished rewrites.
3. Feature and highlight sections covering timestamped evidence, faithful correction, uncertainty markers, resumability, automatic runtime installation, checksum verification, Unicode Windows profiles, and formal-output isolation.
4. A compact workflow showing URL input, local media preparation and ASR, Codex correction, validation, and two final files.
5. Use cases for technical videos, interviews, courses, podcasts, research evidence, quoting, and subtitle preparation.
6. A quick-start section with `$skill-installer`, manual clone, and a natural-language Codex invocation.
7. A concrete example showing the request and representative `raw-transcript.jsonl` and `corrected-transcript.md` shapes. Clearly label output as illustrative rather than a benchmark transcript.
8. Output contract, runtime requirements, first-run download/storage cost, Unicode-profile behavior, supported URL boundary, and troubleshooting.
9. Verified status with 44 unit tests, fresh runtime bootstrap, remote metadata checks, and a real-video smoke result of 46 raw rows, tied to the 2026-08-13 acceptance run rather than presented as a permanent performance guarantee.
10. A closing call to try, Star, and share the repository.

## Accuracy constraints

- Say that media preparation and ASR run locally; do not describe the whole workflow as fully offline or private by default.
- Preserve Windows 10/11 x64, Python 3.11+, PowerShell 5.1+, and AVX2/FMA/F16C/BMI2 requirements.
- Preserve the approximate first-run transfer of 372 MiB and installed runtime size of about 700 MiB.
- State that complete `bilibili.com/video/BV...` URLs are supported, one video/page per invocation, with `p=` honored.
- Explain that login, regional, deleted, paid, or anti-abuse-protected videos may still fail.
- Keep the formal output contract to exactly `raw-transcript.jsonl` and `corrected-transcript.md`.
- Use `[疑似：候选词]` and `[听不清]` as the uncertainty examples.

## Validation

Extend `tests/static-contract.ps1` before rewriting the README. The contract must fail on the old README and then require the exact first line, major promotional sections, installation paths, output names, example markers, supported boundary, verified evidence, and call to action. After the rewrite, run the static contract, both Skill validators, all Python unit tests, runtime-layout parity, remote asset verification, and `git diff --check` before publishing.

## Scope

Modify only `README.md`, its static contract, and the design/plan documentation. Do not change the Skill workflow, runtime scripts, dependencies, or output schema in this release.
