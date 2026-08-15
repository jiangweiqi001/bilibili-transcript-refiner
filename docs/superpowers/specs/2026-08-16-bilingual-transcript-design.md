# Bilingual transcript design

Date: 2026-08-16

## Goal

When a Bilibili recording is predominantly English, or contains meaningful English speech, deliver a corrected Markdown transcript that includes both the faithful English transcript and a faithful Chinese translation. Keep Chinese-only behavior unchanged and do not add a local translation model.

## User-visible behavior

- After ASR preparation, classify the recording as Chinese-only or bilingual from the raw transcript and the user's explicit request.
- Keep the existing Chinese-only workflow and Markdown shape unchanged.
- For an English or meaningfully mixed recording, first complete and review the source-language correction checkpoint, then translate the stable corrected rows into Chinese.
- Render each bilingual row as two self-contained, timestamped lines:

  ```markdown
  [00:00:12.400] **English:** Today we are going to discuss...
  [00:00:12.400] **中文：** 今天我们要讨论……
  ```

- For a mixed row that is already Chinese, preserve that Chinese content in the Chinese line instead of inventing a second translation.
- Preserve uncertainty markers in the English correction. Represent the same uncertainty honestly in the Chinese translation; never turn an uncertain source into a certain translation.

## State and contracts

Keep `corrections.jsonl` unchanged as the authoritative source-language correction checkpoint. This preserves the existing semantic-risk audit, finding IDs, audio reviews, and backward compatibility.

Store Chinese translations in a separate resumable `translations-zh.jsonl` checkpoint under the runtime job directory. Each row must contain the same timestamps, the exact stable source correction text it translates, and a nonempty Chinese text. The source text binding prevents a translation from being reused after its English correction changes.

Add a deterministic translation checkpoint helper that:

- accepts only the next timestamp-matched block;
- validates the entire existing prefix;
- installs updates atomically;
- supports hash-guarded suffix replacement for a bad translation;
- reports the accepted row count, next index, completion state, and checkpoint SHA-256.

Translation is a semantic transformation, so it is not part of the acoustic correction-risk audit. Finalization still requires all current source-language high-risk findings to have valid audio reviews.

## Finalization

Add an explicit bilingual finalization mode. In that mode the finalizer must reject missing, partial, timestamp-mismatched, empty, or stale translations before writing the formal Markdown. It records bilingual provenance in frontmatter, including the translation checkpoint SHA-256 and source/target language identifiers.

The formal directory remains exactly two files:

```text
raw-transcript.jsonl
corrected-transcript.md
```

No translation checkpoint, model, audio, or other intermediate state is copied into the formal directory.

## Translation fidelity

Translate the speaker's meaning row by row after the English correction is stable. Preserve claims, numbers, names, repetitions, hedging, self-corrections, and uncertainty. Do not summarize, explain, fact-correct, add background knowledge, or make the Chinese more certain than the English. Natural Chinese word order is allowed when required for an accurate translation.

## Skill workflow

The Skill determines whether bilingual output is required after reading the raw transcript. For bilingual work it completes the existing correction and audio-review stages first, reads a concise translation policy, checkpoints all Chinese rows, and then invokes bilingual finalization. A user may explicitly request or decline bilingual output; that explicit choice overrides automatic classification.

## Documentation and compatibility

Update `SKILL.md`, the output and correction references, README examples, CLI help, and static contracts. Existing Chinese correction fixtures and callers must continue to pass without changes. The runtime bootstrap manifest and downloadable assets remain unchanged, so the installed model size does not increase.

## Verification

Tests must demonstrate:

- bilingual rendering contains timestamp-matched English and Chinese lines;
- Chinese-only rendering is byte-for-byte unchanged for the existing fixture;
- translation checkpoints resume and replace suffixes safely;
- partial, stale, empty, reordered, or timestamp-changed translations cannot finalize;
- correction audits and review validity are unaffected by translation-only changes;
- the formal directory still contains exactly two deliverables;
- Skill and README contracts describe bilingual behavior without contradicting the non-translation rule for source-language correction;
- the complete Python, PowerShell, static-contract, and Skill validation suites pass.
