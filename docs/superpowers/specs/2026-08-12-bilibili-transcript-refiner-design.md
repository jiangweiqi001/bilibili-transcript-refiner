# Bilibili Transcript Refiner Design

## Goal

Create a Windows-only personal Codex Skill that accepts one Bilibili video URL and produces a source-faithful, AI-corrected Chinese transcript. Favor a small, repeatable workflow over broad platform support.

## Scope

- Support one ordinary Bilibili video or one explicitly selected multipart page per run.
- If a multipart URL omits `p=`, process the first page and state that choice.
- Run through all stages without approval pauses after inputs are sufficient.
- Exclude summaries, outlines, teaching notes, content analysis, translation, and prose rewriting.
- Do not bundle large executables, audio, or model weights in Git.

## Fixed outputs

Write exactly two deliverables under a directory named with the BV identifier:

```text
BV1xxxxxxxxx/
├── raw-transcript.jsonl
└── corrected-transcript.md
```

`raw-transcript.jsonl` is immutable ASR evidence. Each line contains `start`, `end`, and the unedited model `text`.

`corrected-transcript.md` contains YAML source metadata, a fidelity notice, timestamped corrected speech, and a final uncertainty list. Use `[疑似：候选词]` when a candidate is plausible and `[听不清]` when none is reliable.

Ask for an output root once if the user did not provide one. Keep tools, models, and working audio outside the output directory.

## Components and data flow

1. Parse and normalize the URL; collect BV identifier, selected page, title, uploader, duration, and canonical URL.
2. Use an isolated cached `yt-dlp` and FFmpeg toolchain to acquire the best audio and convert it to recognition-ready WAV.
3. Segment speech while retaining global timestamps and run local SenseVoiceSmall. Atomically create the raw JSONL only after validating segment order and coverage.
4. Have the executing Codex correct segments in chronological blocks with limited overlap and a rolling terminology context. It may replay uncertain time ranges.
5. Apply the faithful-mode constraints, render Markdown, aggregate uncertain spans, and validate the final pair before declaring completion.

The ASR engine is fixed to local SenseVoiceSmall. The correction stage is performed by the current Codex model rather than pinned to a particular GPT release.

## Faithful correction contract

- Correct only clear recognition mistakes, terminology, names, sentence boundaries, and punctuation using acoustic and linguistic context.
- Preserve repetitions, hesitation, colloquial syntax, claims, and ordering.
- Do not polish, summarize, silently omit, translate, or add facts not present in the recording.
- Replay audio before resolving a material uncertainty. Mark uncertainty instead of guessing.
- Preserve the raw transcript unchanged and keep corrected timestamps traceable to it.

## Runtime and recovery

- Target Windows and Codex Desktop only in the first version.
- Cache pinned tools and model files in a dedicated per-user runtime directory; verify downloads and reuse them.
- Write downloads, WAV, intermediate segments, and partial correction state to a work directory. Resume completed stages after interruption.
- Never overwrite a successful raw transcript. On an explicitly requested ASR rerun, retain the previous raw file under a versioned name.
- Fail explicitly for unavailable/login-gated videos, missing audio, invalid metadata, model startup failure, or incomplete segment coverage.
- If poor audio prevents a fully reliable result, preserve the reliable work and label the corrected transcript as incomplete rather than presenting it as complete.

## Validation and tests

- Unit-test URL/BV/page parsing, timestamps, output rendering, uncertainty syntax, coverage checks, and overwrite protection.
- Contract-test that forbidden rewriting and extra deliverables are rejected.
- Integration-test metadata extraction, audio conversion, ASR JSONL creation, resume behavior, and atomic finalization using short fixtures.
- Run one end-to-end test on a public Chinese Bilibili video and manually spot-check several ordinary, technical, and uncertain spans against audio.
- Run an independent Skill audit for trigger clarity, contradictions, portability assumptions, and failure modes before publishing.

## Success criteria

A normal invocation with a valid Bilibili URL and output root completes without intermediate questions, leaves exactly the agreed two deliverables, retains verbatim ASR evidence, exposes every unresolved uncertainty, and never represents a partial or rewritten transcript as a faithful complete transcript.
