---
name: bilibili-transcript-refiner
description: Use when a user supplies a full bilibili.com/video/BV URL and asks for a verbatim transcript, speech-to-text, timestamps, subtitle transcription, ASR cleanup, or an AI-corrected faithful transcript; also use when resuming or validating such a transcript job on Windows.
---

# Bilibili Transcript Refiner

## Overview

Turn one B站 video into traceable ASR evidence plus a strictly faithful corrected transcript. Preserve what was said; expose uncertainty instead of guessing.

## Required inputs

Obtain one full `bilibili.com/video/BV...` URL and an output root. If the output root is absent, ask once. After both are known, run the whole workflow without approval pauses unless authorization, replacement of existing evidence, or an unrecoverable failure requires the user.

Support Windows only. Process one video/page per invocation. For multipart URLs, honor `p=`; otherwise process page 1 and disclose that choice.

## Workflow

1. Read [references/output-contract.md](references/output-contract.md) completely.
2. Run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap_runtime.ps1`. Keep its SenseVoiceSmall model, tools, jobs, and audio outside the requested output root.
3. Run `python -X utf8 scripts/prepare_transcript.py --url "<URL>" --output-root "<DIR>"`. Read `job_dir` from its JSON output. Do not use `--rerun-asr` unless the user explicitly asks to replace successful ASR evidence.
4. Read [references/faithful-correction.md](references/faithful-correction.md) completely.
5. Correct the job's raw segments chronologically and checkpoint `corrections.jsonl` atomically in the job directory after each block. Resume at the first missing correction row; keep earlier accepted rows unchanged. Preserve one correction row per raw row and identical timestamps. If explicit ASR replacement changed the raw hash, archive the old correction state outside the formal output and start correction again.
6. Run `python -X utf8 scripts/finalize_transcript.py --job-dir "<JOB_DIR>" --output-root "<DIR>" --status complete` only after every row is corrected and every uncertainty marker is listed. Use `--status incomplete --incomplete-reason "<REASON>"` when audio quality prevents a reliable full result.
7. Validate that the formal directory contains exactly `raw-transcript.jsonl` and `corrected-transcript.md`, then report both paths.

## Non-negotiable fidelity

Correct only clear recognition errors, terminology, names, sentence boundaries, and punctuation. Do not polish, summarize, translate, reorder, silently omit, or turn speech into written prose. Preserve repetitions, hesitation, colloquial syntax, and even claims that appear wrong.

Use `[疑似：候选词]` for a plausible but unconfirmed reading and `[听不清]` when no candidate is reliable. Inspect the relevant audio when the environment supports it; never claim acoustic verification when only text context was used.

Keep `raw-transcript.jsonl` immutable. Never present partial output as a complete faithful transcript.

## Common mistakes

- Do not download an entire playlist or all multipart pages.
- Do not pass a `b23.tv` or `bili2233.cn` short link; ask for its full `bilibili.com/video/BV...` target.
- Do not place binaries, models, WAV files, or job state beside the two deliverables.
- Do not overwrite raw evidence to make it resemble the correction.
- Do not add a summary, outline, teaching note, or content analysis.
- Do not guess a technical term merely because it makes the sentence smoother.
