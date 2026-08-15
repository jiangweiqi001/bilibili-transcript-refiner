# Faithful Chinese translation policy

## Governing rule

Translate the stable corrected source row, not the raw ASR. Preserve meaning and uncertainty; do not repair the speaker's argument.

## Required

- Preserve every claim, number, name, qualification, repetition, hesitation, and self-correction.
- Keep uncertain wording uncertain. Carry every visible `[疑似：…]` or `[听不清]` marker into the Chinese line at the corresponding meaning.
- Use natural Chinese word order only when it does not add, remove, strengthen, or weaken meaning.
- Copy an already-Chinese source row faithfully for its Chinese line.

## Forbidden

- Do not summarize, explain, annotate, fact-correct, or add background knowledge.
- Do not silently omit difficult phrases or make uncertain source wording definite.
- Do not merge rows, move content across timestamps, or translate from the immutable raw ASR when a stable correction exists.
- Do not replace the source-language correction with Chinese; the final Markdown must retain both rows.

## Row procedure

1. Read one stable corrected row and limited neighboring context.
2. Translate that row only.
3. Compare names, numbers, negation, modality, repetitions, and uncertainty with the source.
4. Keep `source_text` exactly equal to the corrected row and checkpoint the timestamp-matched Chinese row before continuing.

## Calibration example

Stable English correction:

```text
I think this is probably the unit distance problem, but I'm not completely sure.
```

Faithful Chinese translation:

```text
我觉得这可能是单位距离问题，但我不完全确定。
```

Do not translate it as “这是单位距离问题”, because that removes the speaker's hedging and uncertainty.
