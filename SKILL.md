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

1. Resolve the directory containing the loaded `SKILL.md` as `<SKILL_DIR>`. Never assume the shell current working directory is the Skill directory.
2. Read [references/output-contract.md](references/output-contract.md) completely from `"<SKILL_DIR>\references\output-contract.md"`.
3. Select one ASCII `<RUNTIME_ROOT>` and keep it for the whole job. Obtain the default with `powershell -NoProfile -Command ". '<SKILL_DIR>\scripts\runtime_layout.ps1'; Get-BtrDefaultRuntimeRoot"`; if that fails, use an explicit private NTFS path such as `C:\btr-runtime`. Do not select it independently again between commands.
4. Run `powershell -NoProfile -ExecutionPolicy Bypass -File "<SKILL_DIR>\scripts\bootstrap_runtime.ps1" -RuntimeRoot "<RUNTIME_ROOT>"`. Keep its SenseVoiceSmall model, tools, jobs, and audio outside the requested output root.
5. Run `python -X utf8 "<SKILL_DIR>\scripts\prepare_transcript.py" --url "<URL>" --output-root "<DIR>" --runtime-root "<RUNTIME_ROOT>"`. Read `job_dir` from its JSON output. Do not use `--rerun-asr` unless the user explicitly asks to replace successful ASR evidence.
6. Read [references/faithful-correction.md](references/faithful-correction.md) completely from `"<SKILL_DIR>\references\faithful-correction.md"`.
7. Correct the job's raw segments chronologically in blocks. Write only the next block to a temporary `<BATCH_JSONL>`, then run `python -X utf8 "<SKILL_DIR>\scripts\checkpoint_corrections.py" --raw "<RAW_JSONL>" --checkpoint "<JOB_DIR>\corrections.jsonl" --batch "<BATCH_JSONL>"`. Never append to or edit the authoritative checkpoint directly. Resume from the returned `next_index`; keep earlier accepted rows unchanged.
   - After every block, refresh and read `<JOB_DIR>\correction-audit.json`; use it to revise unjustified findings, but do not list or record reviews during batching.
   - To revise an already accepted suffix, create a replacement batch beginning at the flagged row and rerun the helper with `--replace-from <ROW_INDEX> --expected-corrections-sha256 "<CURRENT_CORRECTIONS_SHA256>"`, using the hash from the current audit.
   - Continue checkpointing until the returned JSON reports `"complete": true`, finish every necessary replacement, and confirm the checkpoint remains complete.
8. Review the complete correction checkpoint.
   - Begin the final review only after the helper reports `"complete": true`, every replacement is finished, and `corrections.jsonl` is stable.
   - Run `python -X utf8 "<SKILL_DIR>\scripts\review_corrections.py" list --job-dir "<JOB_DIR>"`. Replay each returned `clip_path`; if a finding exposes an unjustified change, return to step 7, replace it, and restart the final review after the checkpoint is complete and stable again.
   - For each intentionally retained current finding, run `python -X utf8 "<SKILL_DIR>\scripts\review_corrections.py" record --job-dir "<JOB_DIR>" --finding-id "<FINDING_ID>" --decision confirmed --note "<REVIEW_NOTE>"`. This writes hash-bound evidence to `<JOB_DIR>\correction-reviews.json`; never fabricate a review when audio inspection is unavailable.
   - Reviews are content-addressed, not operation-count based: only changed correction content that gives the current checkpoint a different corrections SHA-256 makes reviews for the old checkpoint inapplicable; a byte-identical replacement keeps the same content hash.
   - Before finalization, if the current complete, stable checkpoint has a corrections SHA-256 different from the reviewed checkpoint, repeat the final review pass against the current checkpoint.
9. Select the truthful final status and finalize the transcript.
   - Both `complete` and `incomplete` require every raw row to have one timestamp-matched correction; `incomplete` is not a prefix.
   - Local uncertainty markers (`[疑似：…]` or `[听不清]`) may remain in `complete` after every other gate passes.
   - A strict whole-row substitution consisting of a single `[听不清]` must use `incomplete` and may proceed without fabricating an audio review for that informational finding.
   - Every other current high-risk finding in an incomplete job still requires a current confirmed review.
   - Run `python -X utf8 "<SKILL_DIR>\scripts\finalize_transcript.py" --job-dir "<JOB_DIR>" --output-root "<DIR>" --status complete` only after all rows, uncertainty listings, and current reviews pass. Use `--status incomplete --incomplete-reason "<REASON>"` when a reliable full result cannot be claimed.
10. Validate that the formal directory contains exactly `raw-transcript.jsonl` and `corrected-transcript.md`, then report both paths.

## Non-negotiable fidelity

Correct only clear recognition errors, terminology, names, sentence boundaries, and punctuation. Do not polish, summarize, translate, reorder, silently omit, or turn speech into written prose. Preserve repetitions, hesitation, colloquial syntax, and even claims that appear wrong.

Use `[疑似：候选词]` for a plausible but unconfirmed reading and `[听不清]` when no candidate is reliable. Inspect the relevant audio when the environment supports it; never claim acoustic verification when only text context was used.

Keep `raw-transcript.jsonl` immutable. Never present partial output as a complete faithful transcript.

## Common mistakes

- Do not download an entire playlist or all multipart pages.
- Do not pass a `b23.tv` or `bili2233.cn` short link; ask for its full `bilibili.com/video/BV...` target.
- Do not place binaries, models, WAV files, or job state beside the two deliverables.
- Do not record high-risk reviews during batching or reuse them after any later correction change; perform the review pass only against the complete, stable checkpoint.
