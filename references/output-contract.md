# Output contract

## Formal directory

Name page 1 as `<BV-id>/`; name page 2 and later as `<BV-id>-pNN/`. Keep exactly:

```text
raw-transcript.jsonl
corrected-transcript.md
```

Persistent intermediate state, including metadata, audio, clips, corrections, logs, and archives, belongs under the runtime root, normally inside its job directory.

For bilingual jobs, `translations-zh.jsonl` and temporary translation batches are also runtime state and never become a third formal deliverable.

Atomic writers may briefly create owned `.partial-*` files beside their target, including in the formal directory.

Only the corrected-transcript finalizer's own stale formal partial is quarantined on retry; do not generalize that behavior to other partial files.

After successful finalization, the formal directory still contains exactly the two files above.

## Raw evidence

Write UTF-8 JSON Lines with keys in this order and no additional keys:

```json
{"start":"00:00:12.400","end":"00:00:18.720","text":"模型原始识别文字"}
```

Use global `HH:MM:SS.mmm` timestamps. Require increasing, non-overlapping, nonempty segments.

During preparation, remove SenseVoice control tags such as `<|zh|>` and trim surrounding whitespace; preserve all remaining recognized text unchanged.

Never edit a successfully installed raw file.

## Correction work state

Checkpoint one row per raw row under the runtime job directory:

```json
{"start":"00:00:12.400","end":"00:00:18.720","text":"忠实校订文字","uncertainties":[]}
```

For an uncertain span, list every visible marker:

```json
{"start":"00:01:42.000","end":"00:01:49.100","text":"这里需要一个[疑似：遍历性]条件。","uncertainties":[{"marker":"[疑似：遍历性]","note":"也可能是“保测性”，音频不足以确认。"}]}
```

Do not change timestamps or row count. The finalizer rejects a changed raw-file hash.

Install each next block through the deterministic checkpoint helper:

```powershell
python -X utf8 "<SKILL_DIR>\scripts\checkpoint_corrections.py" --raw "<RAW_JSONL>" --checkpoint "<JOB_DIR>\corrections.jsonl" --batch "<BATCH_JSONL>"
```

The helper validates the full existing prefix and next timestamps, atomically replaces the checkpoint, and writes `correction-audit.json` in the runtime job directory. Never edit the authoritative checkpoint directly.

Resume at the first missing correction row. Keep earlier accepted rows unchanged unless the audit identifies a correction that needs replacement.

To revise an accepted row, write a replacement batch beginning at that row and use the current audit hash:

```powershell
python -X utf8 "<SKILL_DIR>\scripts\checkpoint_corrections.py" --raw "<RAW_JSONL>" --checkpoint "<JOB_DIR>\corrections.jsonl" --batch "<BATCH_JSONL>" --replace-from <ROW_INDEX> --expected-corrections-sha256 "<CURRENT_CORRECTIONS_SHA256>"
```

## Chinese translation work state

Create this state only for bilingual output and only after the source correction checkpoint is complete, stable, and reviewed. Keep one row per correction under `<JOB_DIR>\translations-zh.jsonl`:

```json
{"start":"00:00:12.400","end":"00:00:18.720","source_text":"Today we discuss speech recognition.","text_zh":"今天我们讨论语音识别。"}
```

Keys must appear exactly as `start`, `end`, `source_text`, and `text_zh`. Timestamps must match the corresponding correction, `source_text` must equal that correction's `text` byte for byte, and both text fields must be nonempty single lines. These bindings make a translation stale when its source correction changes.

Install the next block through the translation checkpoint helper:

```powershell
python -X utf8 "<SKILL_DIR>\scripts\checkpoint_translations.py" --corrections "<JOB_DIR>\corrections.jsonl" --checkpoint "<JOB_DIR>\translations-zh.jsonl" --batch "<TRANSLATION_BATCH_JSONL>"
```

Resume at the returned `next_index`. Revise a suffix only with the current checkpoint hash:

```powershell
python -X utf8 "<SKILL_DIR>\scripts\checkpoint_translations.py" --corrections "<JOB_DIR>\corrections.jsonl" --checkpoint "<JOB_DIR>\translations-zh.jsonl" --batch "<TRANSLATION_BATCH_JSONL>" --replace-from <ROW_INDEX> --expected-translations-sha256 "<CURRENT_TRANSLATIONS_SHA256>"
```

The bilingual finalizer requires a complete translation checkpoint. A prefix, timestamp change, reordered row, empty translation, or stale `source_text` cannot finalize.

## Review timing

During batching, refresh and read `correction-audit.json` after every checkpoint; use its findings to revise unjustified corrections, but do not list or record reviews yet.

Begin the final review only after the helper reports `"complete": true`, every replacement is finished, and `corrections.jsonl` is stable.

Then list current high-risk findings and their exact clips:

```powershell
python -X utf8 "<SKILL_DIR>\scripts\review_corrections.py" list --job-dir "<JOB_DIR>"
```

Replay each returned `clip_path`, then record every intentionally retained finding separately:

```powershell
python -X utf8 "<SKILL_DIR>\scripts\review_corrections.py" record --job-dir "<JOB_DIR>" --finding-id "<FINDING_ID>" --decision confirmed --note "<REVIEW_NOTE>"
```

Each review record also binds the current raw and clip hashes.

Reviews are content-addressed, not operation-count based: only changed correction content that gives the current checkpoint a different corrections SHA-256 makes reviews for the old checkpoint inapplicable; a byte-identical replacement keeps the same content hash.

Before finalization, if the current complete, stable checkpoint has a corrections SHA-256 different from the reviewed checkpoint, repeat the final review pass against the current checkpoint.

Translation is downstream of acoustic correction review. A translation-only change does not invalidate a current correction review, but any source correction change does invalidate its bound translation rows.

## Status semantics

Both `complete` and `incomplete` require one timestamp-matched correction row for every raw row; `incomplete` is not a correction prefix.

A local `[疑似：…]` or `[听不清]` marker inside otherwise meaningful text may still be `complete` after every other gate passes.

The strict whole-row exemption applies only when the correction text contains exactly one `[听不清]`, its `uncertainties` array contains exactly one entry with that matching marker and a nonempty note, and every character surrounding the marker has a Unicode category beginning with `Z` or `P`.

Letters, numbers, Han characters, emoji, mathematical or currency symbols, control or zero-width characters, `[疑似：…]`, duplicate `[听不清]` markers, extra semantic content, and partial rows that mix ordinary text with `[听不清]` receive no exemption; partial rows retain ordinary protected-token and semantic-loss auditing.

A qualifying strict whole-row substitution must use `incomplete` and does not require an audio review for its informational finding; every other high-risk finding in that incomplete job still requires a current confirmed audio review.

Use `status: "incomplete"` when reliable correction cannot be claimed for the full recording, and add a prominent explanation immediately below the fidelity notice. Local uncertainty alone does not force this status; the strict whole-row abstention does.

## Finalization mode

Choose the output mode explicitly. The finalizer requires exactly one of `--source-only` or `--bilingual`; omitting both or passing both is an error. This guard changes no ASR evidence or saved checkpoint and does not download a translation model.

For intentional source-only output, run `python -X utf8 "<SKILL_DIR>\scripts\finalize_transcript.py" --job-dir "<JOB_DIR>" --output-root "<DIR>" --status complete --source-only`.

For bilingual output, run `python -X utf8 "<SKILL_DIR>\scripts\finalize_transcript.py" --job-dir "<JOB_DIR>" --output-root "<DIR>" --status complete --bilingual` only after the current translation checkpoint is complete.

For either mode, replace `--status complete` with `--status incomplete --incomplete-reason "<REASON>"` when the status rules require it; keep the selected mode flag.

## Corrected Markdown

Render this fixed shape:

```markdown
---
source_url: "https://www.bilibili.com/video/BV1xxxxxxxxx/?p=1"
bvid: "BV1xxxxxxxxx"
page: 1
title: "视频标题"
uploader: "UP主"
duration: "00:32:16.000"
generated_at: "2026-08-14T12:34:56.000000Z"
raw_transcript_sha256: "<SHA-256>"
source_audio_sha256: "<SHA-256>"
normalized_wav_sha256: "<SHA-256>"
asr_model: "SenseVoiceSmall"
asr_model_revision: "90c1c61912018b70ada0fcc024ea24aca62f2e63"
asr_model_sha256: "<SHA-256>"
yt_dlp_version: "2026.07.04"
yt_dlp_sha256: "<SHA-256>"
ffmpeg_version: "9.0.1"
ffmpeg_sha256: "<SHA-256>"
ffprobe_version: "9.0.1"
ffprobe_sha256: "<SHA-256>"
funasr_runtime_version: "0.1.8"
funasr_runtime_sha256: "<SHA-256>"
funasr_vad_version: "0.1.8"
funasr_vad_sha256: "<SHA-256>"
vad_model_version: "6840bae"
vad_model_revision: "6840bae4c5c92ee8c04faaf4db23dd0105098d7f"
vad_model_sha256: "<SHA-256>"
correction_high_risk_count: 0
correction_high_risk_reviewed_count: 0
correction_high_risk_reviewed: false
correction_mode: "faithful"
status: "complete"
---

# 视频标题

> 本文为 AI 忠实校订逐字稿。仅结合语境修正明显的识别错误、术语、人名、断句和标点；不润色、不概括、不把口语改写成书面语。

## 逐字稿

[00:00:00.000] 大家好，今天我们来讨论……

## 存疑处

- [00:01:42.000] `[疑似：遍历性]`：也可能是“保测性”，音频不足以确认。
```

When there are no uncertainties, write `- 无` under `## 存疑处`.

For bilingual output, add these fields before `status`:

```yaml
output_mode: "bilingual-en-zh"
translation_mode: "faithful"
translations_zh_sha256: "<SHA-256>"
```

Keep the source correction and Chinese translation adjacent for every timestamp:

```markdown
## 逐字稿

[00:00:12.400] **English:** Today we discuss speech recognition.
[00:00:12.400] **中文：** 今天我们讨论语音识别。
```

Add a bilingual fidelity notice stating that Chinese lines translate the stable source correction without summary, explanation, factual repair, or added certainty. For a mixed row already in Chinese, repeat its faithful corrected content in the Chinese line. Continue to derive `## 存疑处` from the source correction checkpoint.

## Completion checks

- For either status, match every raw row to exactly one correction with the same timestamps.
- List every `[疑似：…]` and `[听不清]` marker in `## 存疑处`.
- Ensure the formal directory contains no third file.
- Wait for a complete, stable checkpoint before the final review. The strict whole-row `[听不清]` informational finding needs no fabricated review; every other current high-risk `finding_id`, including in an incomplete result, must have a current confirmed record in `correction-reviews.json`.
- Declare completion only after the finalizer succeeds.
- Require every finalization to pass exactly one output-mode flag. For bilingual output, require every correction row to have one current source-bound Chinese row, record `translations_zh_sha256`, and finalize with `--bilingual`.
