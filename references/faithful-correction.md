# Faithful correction policy

## Governing rule

Treat the recording as the authority and the raw ASR as immutable evidence. Correct transcription defects, not the speaker.

## Allowed

- Fix a word when pronunciation, nearby sentences, and established terminology make the intended word clear.
- Restore established spellings of technical terms, people, institutions, symbols, and titles.
- Add punctuation and sentence boundaries without changing emphasis or logical relations.
- Remove SenseVoice control tags during preparation, never during semantic correction.
- Use a title, description, on-screen term, or authoritative source only to confirm spelling; do not import new content.

## Forbidden

- Do not improve style, grammar, rigor, or factual accuracy.
- Do not delete repetitions, fillers, false starts, self-corrections, or colloquial constructions.
- Do not combine separate claims, reorder speech, expand abbreviations the speaker did not expand, or translate foreign words.
- Do not infer a term solely because it would make the argument better.
- Do not hide low confidence behind fluent prose.

## Segment procedure

1. Work forward in blocks of roughly ten minutes.
2. Carry a small amount of preceding text plus a rolling list of established names and terms.
3. Preserve exactly one corrected row and the same `start`/`end` for every raw row.
4. Compare each proposed change with the raw wording. Revert any change that is stylistic rather than corrective.
5. Inspect or replay the time range when audio inspection is available. Otherwise try nearby segment boundaries or additional ASR context, then retain an uncertainty marker.
6. Write only the next accepted block to a temporary JSONL batch. Run `checkpoint_corrections.py` to validate it against the first missing raw row and atomically replace the authoritative `corrections.jsonl`. Resume at the first missing correction row, and do not regenerate accepted earlier rows merely to make them stylistically consistent.
7. Read `correction-audit.json` after every checkpoint. For an unjustified finding in an accepted row, build a replacement batch starting at that row and call `checkpoint_corrections.py` with `--replace-from <ROW_INDEX> --expected-corrections-sha256 "<CURRENT_CORRECTIONS_SHA256>"`. This is the only supported way to revise the accepted suffix; the hash guard prevents overwriting concurrent work.
8. Run `review_corrections.py list --job-dir "<JOB_DIR>"` and replay each returned `clip_path`. After acoustic confirmation, record each retained finding by its own `finding_id`; the helper stores the exact raw, corrections, and clip hashes in `correction-reviews.json`.

Never append to or edit `corrections.jsonl` directly. The checkpoint tool validates the complete accepted prefix, exact timestamps, marker accounting, and atomic installation.

## Uncertainty

- Use `[疑似：X]` only when `X` is a meaningful candidate but not secure enough to state as fact.
- Use `[听不清]` when there is no reliable candidate.
- Keep the marker exactly where the uncertain speech occurs.
- Add one concise note for each marker, including alternatives only when genuinely plausible.
- If audio inspection is unavailable, never claim acoustic verification or create a review record; keep the raw reading or use an uncertainty marker instead.

## Calibration example

Raw ASR:

```text
这个问题就是elder老爷子提出的unit distance。
```

Faithful correction when context and the source title establish the name:

```text
这个问题就是 Erdős 老爷子提出的 unit distance。
```

Do not rewrite it as “单位距离问题由数学家 Paul Erdős 提出”，because that converts the speaker's wording into explanatory prose.
