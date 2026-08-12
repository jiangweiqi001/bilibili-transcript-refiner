# Output contract

## Formal directory

Name page 1 as `<BV-id>/`; name page 2 and later as `<BV-id>-pNN/`. Keep exactly:

```text
raw-transcript.jsonl
corrected-transcript.md
```

Keep metadata, audio, clips, corrections, logs, archives, and partial files in the runtime job directory.

## Raw evidence

Write UTF-8 JSON Lines with keys in this order and no additional keys:

```json
{"start":"00:00:12.400","end":"00:00:18.720","text":"模型原始识别文字"}
```

Use global `HH:MM:SS.mmm` timestamps. Require increasing, non-overlapping, nonempty segments. Remove only SenseVoice control tags such as `<|zh|>`; otherwise keep the recognized text byte-for-byte. Never edit a successfully installed raw file.

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
asr_model: "SenseVoiceSmall"
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

Use `status: "incomplete"` when reliable correction cannot cover the full recording, and add a prominent explanation immediately below the fidelity notice. When there are no uncertainties, write `- 无` under `## 存疑处`.

## Completion checks

- Match every corrected row to one raw row.
- List every `[疑似：…]` and `[听不清]` marker in `## 存疑处`.
- Ensure the formal directory contains no third file.
- Declare completion only after the finalizer succeeds.
