# Bilingual Transcript Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add resumable, source-bound Chinese translation checkpoints and deterministic English–Chinese Markdown output for English Bilibili transcripts without changing Chinese-only behavior.

**Architecture:** Preserve `corrections.jsonl` as the sole source-language correction and audio-review artifact. Add a separate `translations-zh.jsonl` runtime checkpoint whose rows bind exact corrected source text to timestamp-matched Chinese text, then make bilingual finalization opt-in through `--bilingual` and reject incomplete or stale translations.

**Tech Stack:** Python 3.11+ standard library, `unittest`, PowerShell 5.1 static contracts, Markdown Skill/reference documentation.

---

## File map

- Create `scripts/translation_contract.py`: parse, validate, hash, resume, and replace Chinese translation checkpoints.
- Create `scripts/checkpoint_translations.py`: command-line adapter for the translation checkpoint contract.
- Create `tests/test_translation_contract.py`: unit coverage for the new checkpoint and source binding.
- Modify `scripts/finalize_transcript.py`: validate optional bilingual state and render paired source/Chinese lines.
- Modify `tests/test_finalize_transcript.py`: bilingual rendering/finalization and Chinese compatibility coverage.
- Create `references/faithful-translation-zh.md`: semantic translation policy loaded only for bilingual jobs.
- Modify `SKILL.md`: classify English jobs and add translation checkpointing after stable correction review.
- Modify `references/output-contract.md`: specify translation runtime state, bilingual frontmatter, and Markdown shape.
- Modify `references/faithful-correction.md`: clarify that its translation ban applies to source-language correction.
- Modify `README.md`: document bilingual output, unchanged runtime size, and an example.
- Modify `tests/static-contract.ps1`: enforce the new workflow while preserving the existing exact contracts.
- Modify `agents/openai.yaml`: mention bilingual output in user-facing metadata without duplicating workflow instructions.

### Task 1: Translation checkpoint contract

**Files:**
- Create: `tests/test_translation_contract.py`
- Create: `scripts/translation_contract.py`
- Create: `scripts/checkpoint_translations.py`

- [ ] **Step 1: Write failing checkpoint tests**

Create tests that define this exact row schema and API:

```python
{"start": "00:00:00.000", "end": "00:00:01.000", "source_text": "Hello.", "text_zh": "你好。"}
```

```python
from scripts.translation_contract import (
    Translation,
    install_translation_batch,
    read_translations,
    validate_translation_pairing,
)

def test_installs_only_the_next_source_bound_translation_batch(self):
    result = install_translation_batch(
        self.corrections_path, self.checkpoint, self.batch
    )
    self.assertEqual(result["accepted_rows"], 1)
    self.assertEqual(result["next_index"], 1)
    self.assertFalse(result["complete"])

def test_rejects_translation_after_source_correction_changes(self):
    translations = [Translation(0, 1000, "Hello.", "你好。")]
    changed = [Correction(0, 1000, "Hello!", ())]
    with self.assertRaisesRegex(ValueError, "source text changed"):
        validate_translation_pairing(changed, translations)

def test_hash_guarded_suffix_replacement_updates_a_bad_translation(self):
    result = install_translation_batch(
        self.corrections_path,
        self.checkpoint,
        self.batch,
        replace_from=1,
        expected_translations_sha256=sha256(self.checkpoint),
    )
    self.assertEqual(result["replaced_from"], 1)
```

Also cover exact/reordered keys, nonempty single-line `source_text` and `text_zh`, timestamp changes, skipped rows, stale replacement hashes, atomic cleanup, and full checkpoint completion.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -X utf8 -m unittest tests.test_translation_contract -v
```

Expected: import failure because `scripts.translation_contract` does not exist.

- [ ] **Step 3: Implement the minimal translation contract**

Implement `Translation(start_ms: int, end_ms: int, source_text: str, text_zh: str)` as a frozen dataclass whose `to_record()` emits the exact four-key JSON order. Add `read_translations(path)`, `validate_translation_pairing(correction_rows, translation_rows, allow_prefix=False)`, `write_translations_atomic(path, rows)`, and `install_translation_batch(corrections_path, checkpoint_path, batch_path, replace_from=None, expected_translations_sha256=None)` as the module's public interfaces.

Use exact keys `start`, `end`, `source_text`, `text_zh`; reject empty/multiline text; compare every timestamp and `source_text` with the corresponding stable `Correction`; use `exclusive_job_lock(checkpoint.parent / "job.lock")`; atomically replace the checkpoint; and return `accepted_rows`, `next_index`, `complete`, `translations_sha256`, plus `replaced_from` for replacement calls.

Create `scripts/checkpoint_translations.py` with arguments:

```text
--corrections --checkpoint --batch
[--replace-from N --expected-translations-sha256 SHA256]
```

It must call `install_translation_batch`, print its result as UTF-8 JSON, and exit nonzero on contract failure.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```powershell
python -X utf8 -m unittest tests.test_translation_contract -v
python -X utf8 scripts/checkpoint_translations.py --help
```

Expected: all translation tests pass and CLI help exits 0.

- [ ] **Step 5: Commit the translation checkpoint**

```powershell
git add scripts/translation_contract.py scripts/checkpoint_translations.py tests/test_translation_contract.py
git commit -m "feat: add resumable Chinese translation checkpoints"
```

### Task 2: Bilingual finalization

**Files:**
- Modify: `tests/test_finalize_transcript.py`
- Modify: `scripts/finalize_transcript.py`

- [ ] **Step 1: Write failing bilingual rendering and finalization tests**

Add rendering coverage using two `Translation` rows:

```python
doc = render_corrected(
    self.metadata,
    self.raw,
    corrections,
    status="complete",
    translation_rows=translations,
    translations_sha256="A" * 64,
)
self.assertIn('output_mode: "bilingual-en-zh"', doc)
self.assertIn('translations_zh_sha256: "' + "A" * 64 + '"', doc)
self.assertIn("[00:00:00.000] **English:** Hello.", doc)
self.assertIn("[00:00:00.000] **中文：** 你好。", doc)
```

Add finalization cases asserting that `bilingual=True` rejects a missing checkpoint, a prefix, stale `source_text`, changed timestamps, empty text, and reordered rows. Assert a valid checkpoint finalizes, records its SHA-256 in both Markdown and `job.json`, and leaves exactly the two formal deliverables.

Add a regression assertion that the existing checked-in Chinese fixture renders exactly as before when `translation_rows` is omitted.

- [ ] **Step 2: Run focused finalizer tests and verify RED**

Run:

```powershell
python -X utf8 -m unittest tests.test_finalize_transcript.RenderingTests tests.test_finalize_transcript.FinalizationTests -v
```

Expected: failure because `Translation`, `translation_rows`, and `bilingual` are not supported by the finalizer.

- [ ] **Step 3: Implement bilingual validation and rendering**

Import `Translation`, `read_translations`, and `validate_translation_pairing`. Extend `render_corrected` with keyword-only `translation_rows: Sequence[Translation] | None = None` and `translations_sha256: str | None = None`. Extend `_finalize_transcript_locked` and `finalize_transcript` with keyword-only `bilingual: bool = False`. These defaults must leave every existing caller unchanged.

When `translation_rows` is present, require complete source pairing and a 64-hex checkpoint hash, add:

```yaml
output_mode: "bilingual-en-zh"
translation_mode: "faithful"
translations_zh_sha256: "<SHA-256>"
```

Render every row as:

```markdown
[HH:MM:SS.mmm] **English:** <correction text>
[HH:MM:SS.mmm] **中文：** <Chinese translation>
```

When `bilingual=True`, require `<JOB_DIR>/translations-zh.jsonl`, validate it against the complete stable corrections, and pass its hash to the renderer. Add `--bilingual` to the CLI. Record `output_mode` and `translations_zh_sha256` in `job.json` only for bilingual finalization. Do not alter the formal directory file set.

- [ ] **Step 4: Run focused and regression tests and verify GREEN**

Run:

```powershell
python -X utf8 -m unittest tests.test_translation_contract tests.test_finalize_transcript -v
```

Expected: all focused tests pass, including the Chinese-only rendering regression.

- [ ] **Step 5: Commit bilingual finalization**

```powershell
git add scripts/finalize_transcript.py tests/test_finalize_transcript.py
git commit -m "feat: render validated bilingual transcripts"
```

### Task 3: Skill and public contracts

**Files:**
- Create: `references/faithful-translation-zh.md`
- Modify: `SKILL.md`
- Modify: `references/output-contract.md`
- Modify: `references/faithful-correction.md`
- Modify: `README.md`
- Modify: `agents/openai.yaml`
- Modify: `tests/static-contract.ps1`

- [ ] **Step 1: Write failing static-contract assertions**

Require all of the following:

- `SKILL.md` selects bilingual mode for predominantly English speech or a mixed recording with at least one complete English clause; a name, title, formula, or isolated English term does not trigger it.
- The bilingual workflow reads `references/faithful-translation-zh.md`, translates only after corrections and audio reviews are stable, checkpoints through `checkpoint_translations.py`, and finalizes with `--bilingual`.
- The translation policy forbids summarization, explanation, fact correction, added certainty, and loss of numbers, names, hedging, repetition, or uncertainty.
- The output contract defines exact translation keys, full pairing, source-text binding, bilingual frontmatter, and two-line rendering.
- README first line remains exactly `点点关注谢谢喵~` and advertises bilingual output without claiming a new local translation model or fully offline translation.

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tests/static-contract.ps1
```

Expected: FAIL because the new bilingual contract sentences and reference do not exist.

- [ ] **Step 2: Add the focused translation policy**

Create `references/faithful-translation-zh.md` with these sections:

```markdown
# Faithful Chinese translation policy

## Governing rule
Translate the stable corrected source row, not the raw ASR. Preserve meaning and uncertainty; do not repair the speaker's argument.

## Required
- Preserve every claim, number, name, qualification, repetition, hesitation, and self-correction.
- Keep uncertainty uncertain and preserve visible source markers in an honest Chinese form.
- Use natural Chinese word order only when it does not add, remove, strengthen, or weaken meaning.
- Copy an already-Chinese source row faithfully for its Chinese line.

## Forbidden
- Do not summarize, explain, annotate, fact-correct, or add background knowledge.
- Do not silently omit difficult phrases or make uncertain source wording definite.
- Do not merge rows, move content across timestamps, or translate from the immutable raw ASR when a stable correction exists.

## Row procedure
1. Read one stable corrected row and limited neighboring context.
2. Translate that row only.
3. Compare names, numbers, negation, modality, and uncertainty with the source.
4. Checkpoint the timestamp-matched row before continuing.
```

- [ ] **Step 3: Update workflow, output, README, and UI metadata**

In `SKILL.md`, keep the existing correction and review steps intact, then add a conditional bilingual stage before finalization. Use a separate runtime batch file and never edit `translations-zh.jsonl` directly. Explicit user choice overrides automatic classification.

In `references/faithful-correction.md`, replace the broad foreign-word translation prohibition with a source-correction boundary: source correction must not translate or replace foreign speech, while the separate post-review translation stage may create the Chinese companion.

In `references/output-contract.md`, document `translations-zh.jsonl` as runtime-only state with exact keys and source binding. Add the bilingual frontmatter and paired Markdown example while leaving the Chinese-only fixed shape intact.

In `README.md`, add bilingual output to features, workflow, sample output, output explanation, privacy/network explanation, and FAQ. State that Codex performs the Chinese translation and no extra local translation model is downloaded. Preserve the first line exactly.

Update `agents/openai.yaml` to mention Chinese–English transcripts in `short_description` and `default_prompt`, keeping the description concise.

- [ ] **Step 4: Run static contract and Skill validation and verify GREEN**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tests/static-contract.ps1
python -X utf8 tests/quick_validate_skill.py .
```

Expected: `static Skill contract: PASS` and `Skill is valid!`.

- [ ] **Step 5: Commit the Skill and public contracts**

```powershell
git add SKILL.md README.md agents/openai.yaml references/faithful-correction.md references/faithful-translation-zh.md references/output-contract.md tests/static-contract.ps1
git commit -m "docs: teach bilingual transcript workflow"
```

### Task 4: Full verification and release

**Files:**
- Verify all changed files

- [ ] **Step 1: Run the complete Python suite**

```powershell
python -X utf8 -m unittest discover -s tests -p "test_*.py" -t .
```

Expected: all tests pass with no errors or warnings.

- [ ] **Step 2: Run all local contract and runtime checks**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tests/static-contract.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tests/test-runtime-layout.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tests/test-runtime-acl.ps1
python -X utf8 tests/quick_validate_skill.py .
python -X utf8 scripts/checkpoint_translations.py --help
python -X utf8 scripts/finalize_transcript.py --help
```

Expected: every command exits 0; both CLIs display the documented flags.

- [ ] **Step 3: Verify repository integrity and scope**

```powershell
git diff --check
git status --short
git log -5 --oneline
```

Confirm README line 1 is exactly `点点关注谢谢喵~`, `scripts/runtime-assets.json` is unchanged, no cache/temporary files are tracked, and the formal two-file contract remains intact.

- [ ] **Step 4: Push the completed commits**

```powershell
git push origin main
```

Expected: `origin/main` advances through the design, implementation, tests, and documentation commits.
