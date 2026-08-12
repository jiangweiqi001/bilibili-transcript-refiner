# Bilibili Transcript Refiner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows Codex Skill that turns one Bilibili URL into immutable SenseVoiceSmall JSONL evidence and a strictly faithful, timestamped, AI-corrected Markdown transcript.

**Architecture:** Keep deterministic media/ASR work in small Python and PowerShell scripts, while the Skill directs Codex's semantic correction. Store all runtime binaries, models, audio, job metadata, and resumable correction state under an ASCII-only per-user cache; atomically copy only the two contractual deliverables into the requested output directory.

**Tech Stack:** Codex Skill Markdown, Python 3.11+ standard library, PowerShell 7/Windows PowerShell 5.1, yt-dlp 2026.07.04, FFmpeg 9.0.1 essentials, FunASR llama.cpp runtime v0.1.8, SenseVoiceSmall q8 GGUF, FSMN-VAD GGUF, `unittest`, GitHub Actions Windows runner.

---

## File map

- `SKILL.md`: trigger description and end-to-end agent procedure.
- `agents/openai.yaml`: human-facing Skill metadata.
- `references/faithful-correction.md`: the only detailed semantic correction policy and examples.
- `references/output-contract.md`: the only detailed schemas and final-file contract.
- `scripts/bootstrap_runtime.ps1`: download, checksum, extract, verify, and reuse the isolated Windows runtime.
- `scripts/transcript_contract.py`: URL, time, JSONL, coverage, atomic-write, and output-validation primitives.
- `scripts/prepare_transcript.py`: metadata, audio download/conversion, VAD segmentation, per-segment ASR, and resume orchestration.
- `scripts/finalize_transcript.py`: validate resumable corrections and atomically render the final Markdown.
- `tests/test_transcript_contract.py`: pure unit tests for contracts.
- `tests/test_prepare_transcript.py`: mocked-process orchestration tests.
- `tests/test_finalize_transcript.py`: rendering, immutability, and incomplete-status tests.
- `tests/static-contract.ps1`: Skill metadata/reference/output constraints.
- `.github/workflows/test.yml`: offline Windows unit and contract tests.
- `.gitignore`: Python caches and local test artifacts only; runtime never lives in the repository.

### Task 1: Scaffold the discoverable Skill

**Files:**
- Create: `SKILL.md`
- Create: `agents/openai.yaml`
- Create: `references/faithful-correction.md`
- Create: `references/output-contract.md`
- Create: `.gitignore`
- Test: `tests/static-contract.ps1`

- [ ] **Step 1: Generate a canonical temporary scaffold**

Run the official initializer outside the worktree, then use its generated frontmatter and `agents/openai.yaml` structure as the basis for repository files:

```powershell
python C:\Users\25739\.codex\skills\.system\skill-creator\scripts\init_skill.py bilibili-transcript-refiner `
  --path $env:TEMP\btr-skill-scaffold `
  --resources scripts,references `
  --interface 'display_name=B站逐字稿转写与校订' `
  --interface 'short_description=将B站视频转为可追溯的忠实校订逐字稿' `
  --interface 'default_prompt=请将这个B站视频转写为严格忠实、带时间戳且保留疑点的双稿。'
```

Expected: `$env:TEMP\btr-skill-scaffold\bilibili-transcript-refiner\SKILL.md` and `agents\openai.yaml` exist.

- [ ] **Step 2: Write the failing static contract**

Require exact frontmatter keys, Bilibili triggers, faithful-mode language, Windows scope, SenseVoiceSmall, the two output names, uncertainty markers, raw immutability, output-location behavior, and direct links to both references. Reject README/installation/changelog files and any promise of summaries or rewriting.

```powershell
$required = @(
  'name: bilibili-transcript-refiner',
  'SenseVoiceSmall',
  'raw-transcript.jsonl',
  'corrected-transcript.md',
  '[疑似：',
  '[听不清]',
  'references/faithful-correction.md',
  'references/output-contract.md'
)
foreach ($needle in $required) {
  if (-not $skill.Contains($needle)) { throw "missing contract: $needle" }
}
```

- [ ] **Step 3: Run the static contract and verify RED**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File tests/static-contract.ps1`

Expected: non-zero exit because `SKILL.md` is absent.

- [ ] **Step 4: Add the minimal Skill and references**

Write imperative instructions that always continue once URL and output root are known; load `output-contract.md` before preparation/finalization and `faithful-correction.md` before semantic correction. Keep all implementation detail in scripts/references, not duplicated in `SKILL.md`.

- [ ] **Step 5: Run the static contract and validate the scaffold**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tests/static-contract.ps1
python -X utf8 C:\Users\25739\.codex\skills\.system\skill-creator\scripts\quick_validate.py .
```

Expected: both commands exit 0.

- [ ] **Step 6: Commit**

```powershell
git add SKILL.md agents references tests/static-contract.ps1 .gitignore
git commit -m "feat: scaffold bilibili transcript skill"
```

### Task 2: Implement the transcript contract primitives

**Files:**
- Create: `scripts/transcript_contract.py`
- Create: `tests/test_transcript_contract.py`

- [ ] **Step 1: Write failing unit tests**

Cover these concrete interfaces:

```python
from scripts.transcript_contract import (
    Segment, format_timestamp, output_name, parse_bilibili_url,
    read_jsonl, validate_coverage, write_jsonl_atomic,
)

def test_parse_url_and_page():
    parsed = parse_bilibili_url("https://www.bilibili.com/video/BV1rnGt61E4j/?p=2")
    assert (parsed.bvid, parsed.page) == ("BV1rnGt61E4j", 2)

def test_output_name_adds_page_suffix_only_after_page_one():
    assert output_name("BV1rnGt61E4j", 1) == "BV1rnGt61E4j"
    assert output_name("BV1rnGt61E4j", 2) == "BV1rnGt61E4j-p02"

def test_coverage_requires_one_nonempty_asr_row_per_vad_span():
    vad = [(0, 950), (1200, 2200)]
    rows = [Segment(0, 950, "甲"), Segment(1200, 2200, "乙")]
    validate_coverage(vad, rows)
```

Also reject non-Bilibili hosts, missing/invalid BV identifiers, page zero, negative or reversed timestamps, empty ASR text, unordered/overlapping rows, invalid JSONL keys, and overwrite of an existing raw file.

- [ ] **Step 2: Run unit tests and verify RED**

Run: `python -m unittest tests.test_transcript_contract -v`

Expected: import failure because the module is absent.

- [ ] **Step 3: Implement the minimal standard-library module**

Use frozen dataclasses for `BilibiliTarget` and `Segment`, integer milliseconds internally, `HH:MM:SS.mmm` externally, UTF-8 without BOM, `os.replace` for atomic installation, and `FileExistsError` unless `allow_replace=True` is explicitly passed for non-evidence files.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m unittest tests.test_transcript_contract -v`

Expected: all contract tests pass.

- [ ] **Step 5: Commit**

```powershell
git add scripts/transcript_contract.py tests/test_transcript_contract.py
git commit -m "feat: add transcript data contracts"
```

### Task 3: Bootstrap the isolated runtime

**Files:**
- Create: `scripts/bootstrap_runtime.ps1`
- Test: `tests/static-contract.ps1`

- [ ] **Step 1: Extend the static test and verify RED**

Require an ASCII-path guard, SHA-256 validation, idempotent `-VerifyOnly`, and these immutable assets:

```text
yt-dlp 2026.07.04
  https://github.com/yt-dlp/yt-dlp/releases/download/2026.07.04/yt-dlp.exe
  52FE3C26DCF71FBDC85B528589020BB0B8E383155CFA81B64DD447BBE35E24B8
FFmpeg 9.0.1 essentials
  https://github.com/GyanD/codexffmpeg/releases/download/9.0.1/ffmpeg-9.0.1-essentials_build.zip
  FEC81AE03971D9DD4BE3EBE02E263BD2EC1D789483F931BDBA5F5715E65DA2E9
FunASR llama.cpp runtime v0.1.8 AVX2
  https://github.com/modelscope/FunASR/releases/download/runtime-llamacpp-v0.1.8/funasr-llamacpp-windows-x64-avx2.zip
  F2A1389658E6FB5F5F93C7BAD98B5CE100EB4811E0E3C39603E39466773B1B4C
SenseVoiceSmall q8
  https://huggingface.co/FunAudioLLM/SenseVoiceSmall-GGUF/resolve/main/sensevoice-small-q8.gguf
  4AE45C94422DE949B387E2E0FB10D7E14E4C42C69DB30C3444ECC7D4B844B7C5
FSMN-VAD
  https://huggingface.co/FunAudioLLM/fsmn-vad-GGUF/resolve/main/fsmn-vad.gguf
  1270F2559C495F4E7B6E739541151027D360761A3FDA43FC147034F5719F5479
```

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File tests/static-contract.ps1`

Expected: failure because the bootstrap script is absent.

- [ ] **Step 2: Implement deterministic setup**

Default `RuntimeRoot` to `$env:LOCALAPPDATA\bilibili-transcript-refiner\runtime-v1`. Reject non-ASCII runtime paths with a message requesting `-RuntimeRoot C:\btr-runtime`. Download to `*.partial`, hash before rename, use `Expand-Archive`, locate executables recursively, and write `runtime.json` with absolute paths and versions. On AVX2 startup failure, emit an explicit unsupported-CPU error; do not silently switch models.

- [ ] **Step 3: Verify against the already downloaded diagnostic runtime**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap_runtime.ps1 `
  -RuntimeRoot C:\Users\25739\AppData\Local\bilibili-transcript-refiner\runtime-v1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap_runtime.ps1 `
  -RuntimeRoot C:\Users\25739\AppData\Local\bilibili-transcript-refiner\runtime-v1 -VerifyOnly
```

Expected: first invocation installs or reuses assets; second reports all five verified without downloading.

- [ ] **Step 4: Commit**

```powershell
git add scripts/bootstrap_runtime.ps1 tests/static-contract.ps1
git commit -m "feat: add verified Windows runtime bootstrap"
```

### Task 4: Prepare immutable ASR evidence with resume

**Files:**
- Create: `scripts/prepare_transcript.py`
- Create: `tests/test_prepare_transcript.py`

- [ ] **Step 1: Write mocked failing tests**

Test a fake runner returning yt-dlp metadata/audio, FFmpeg success, VAD stderr containing `0 33600` and `33600 59980`, and SenseVoice stdout for each clip. Assert:

```python
assert result.output_dir.name == "BV1rnGt61E4j"
assert result.raw_path.read_text(encoding="utf-8").splitlines() == [
    '{"start":"00:00:00.000","end":"00:00:33.600","text":"第一段"}',
    '{"start":"00:00:33.600","end":"00:00:59.980","text":"第二段"}',
]
assert result.job_manifest["state"] == "asr_complete"
```

Also test first-page default disclosure, `p=2` directory naming, Unicode output roots, ASCII-only working paths, model tag removal without rewriting recognized text, resume without re-running successful segments, failure on a missing segment, and refusal to replace an existing raw transcript.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest tests.test_prepare_transcript -v`

Expected: import failure because the module is absent.

- [ ] **Step 3: Implement preparation**

Expose:

```text
python -X utf8 scripts/prepare_transcript.py --url URL --output-root DIR [--runtime-root DIR]
python -X utf8 scripts/prepare_transcript.py --url URL --output-root DIR --rerun-asr
```

Use `yt-dlp --dump-single-json --no-playlist` for metadata and `-f bestaudio/best --no-playlist` for audio. Convert to mono 16-kHz PCM WAV. Run `llama-funasr-vad.exe` to obtain millisecond spans, cut each clip with FFmpeg under the ASCII job directory, and run `llama-funasr-sensevoice.exe` once per clip. Preserve its lexical output exactly after removing only documented `<|...|>` control tags. Store `metadata.json`, `vad.json`, per-segment text, and `job.json` only in the job cache. Atomically install raw JSONL after count/order/coverage validation.

- [ ] **Step 4: Run focused and full tests**

Run:

```powershell
python -m unittest tests.test_prepare_transcript -v
python -m unittest discover -s tests -p 'test_*.py' -v
```

Expected: all tests pass and no network is accessed by unit tests.

- [ ] **Step 5: Commit**

```powershell
git add scripts/prepare_transcript.py tests/test_prepare_transcript.py
git commit -m "feat: prepare resumable SenseVoice evidence"
```

### Task 5: Finalize faithful corrections atomically

**Files:**
- Create: `scripts/finalize_transcript.py`
- Create: `tests/test_finalize_transcript.py`

- [ ] **Step 1: Write failing renderer tests**

Define work-state `corrections.jsonl` rows with exactly `start`, `end`, `text`, and `uncertainties`. Require one correction per raw row with identical timestamps. Test YAML quoting, title/uploader/duration/model/status fields, the fidelity notice, timestamped body, `[疑似：遍历性]`, `[听不清]`, deduplicated uncertainty summary, incomplete status, and rejection of extra final files.

```python
doc = render_corrected(metadata, raw_rows, correction_rows, status="complete")
assert "correction_mode: faithful" in doc
assert "[00:00:18.000] 这里使用的是费马平方和定理。" in doc
assert "## 存疑处" in doc
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest tests.test_finalize_transcript -v`

Expected: import failure because the finalizer is absent.

- [ ] **Step 3: Implement finalization and validation**

Expose:

```text
python -X utf8 scripts/finalize_transcript.py --job-dir DIR --output-root DIR --status complete
python -X utf8 scripts/finalize_transcript.py --job-dir DIR --output-root DIR --status incomplete
```

Reject missing/extra correction rows, changed timestamps, empty text, malformed uncertainty markers, `complete` with unlisted markers, unexpected deliverables, and changed raw SHA-256 since correction began. Write `corrected-transcript.md.partial`, validate it, then `os.replace`. Archive a superseded raw transcript only under `job-dir/archive/`; formal output must end with exactly the two contractual filenames.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m unittest discover -s tests -p 'test_*.py' -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add scripts/finalize_transcript.py tests/test_finalize_transcript.py
git commit -m "feat: finalize faithful transcript atomically"
```

### Task 6: Complete the agent correction workflow

**Files:**
- Modify: `SKILL.md`
- Modify: `references/faithful-correction.md`
- Modify: `references/output-contract.md`
- Modify: `tests/static-contract.ps1`

- [ ] **Step 1: Add failing behavioral contract checks**

Require instructions to process corrections chronologically in approximately ten-minute blocks, carry prior context and a rolling terminology list, preserve one-to-one segment timestamps, replay or re-segment doubtful spans when audio inspection is available, mark rather than guess, checkpoint `corrections.jsonl`, resume without repeating accepted rows, and always run the finalizer before completion.

- [ ] **Step 2: Run static tests and verify RED**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File tests/static-contract.ps1`

Expected: failure naming the first missing workflow clause.

- [ ] **Step 3: Write the concise orchestration instructions**

Make the normal path one uninterrupted run after URL and output root are known. Pause only for missing output root, authorization/cookie needs, explicit ASR replacement, or a failure that cannot be resolved locally. Do not claim Codex acoustically verified a span unless audio was actually inspected; otherwise use ASR re-segmentation/context and preserve uncertainty.

- [ ] **Step 4: Run Skill and static validation**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tests/static-contract.ps1
python -X utf8 C:\Users\25739\.codex\skills\.system\skill-creator\scripts\quick_validate.py .
```

Expected: both exit 0.

- [ ] **Step 5: Commit**

```powershell
git add SKILL.md references tests/static-contract.ps1
git commit -m "feat: define faithful correction workflow"
```

### Task 7: Add CI and run a real Bilibili acceptance test

**Files:**
- Create: `.github/workflows/test.yml`
- Modify: `.gitignore`
- Create: `tests/fixtures/raw-transcript.jsonl`
- Create: `tests/fixtures/corrections.jsonl`
- Create: `tests/fixtures/metadata.json`

- [ ] **Step 1: Add offline Windows CI**

Run Python `unittest`, `tests/static-contract.ps1`, `quick_validate.py`, and `git diff --check` on `windows-latest`. Do not download models in CI.

- [ ] **Step 2: Run the complete offline suite locally**

Run:

```powershell
python -m unittest discover -s tests -p 'test_*.py' -v
powershell -NoProfile -ExecutionPolicy Bypass -File tests/static-contract.ps1
python -X utf8 C:\Users\25739\.codex\skills\.system\skill-creator\scripts\quick_validate.py .
git diff --check
```

Expected: all tests pass, Skill validation succeeds, and diff check is empty.

- [ ] **Step 3: Run one full public-video preparation**

Use the already supplied public reference video and a dedicated acceptance output root:

```powershell
python -X utf8 scripts/prepare_transcript.py `
  --url 'https://www.bilibili.com/video/BV1rnGt61E4j/' `
  --output-root 'C:\Users\25739\AppData\Local\bilibili-transcript-refiner\acceptance-output'
```

Expected: metadata/audio/VAD/ASR complete, raw JSONL validates, timestamps increase, and the formal output directory contains raw evidence only until correction finalization.

- [ ] **Step 4: Complete and inspect faithful correction**

Use the Skill workflow to create corrections and finalize. Spot-check at least five spans: opening speech, ordinary exposition, a mathematical term, a proper name, and an acoustically uncertain span. Record pass/fail evidence in the task log, not the published Skill.

Expected: no invented content or prose polishing; unresolved audio uses the fixed markers; final directory contains exactly two files.

- [ ] **Step 5: Commit**

```powershell
git add .github .gitignore tests/fixtures
git commit -m "test: add Windows contracts and fixtures"
```

### Task 8: Final validation and publication

**Files:**
- Modify only files implicated by review findings.

- [ ] **Step 1: Run independent forward and publication reviews**

Give reviewers the raw Skill/repository and realistic prompt, not the intended answers. Audit triggering, one-video behavior, faithful correction, exact outputs, resume/overwrite safety, Unicode/output versus ASCII/runtime assumptions, and contradictions.

- [ ] **Step 2: Fix confirmed findings test-first**

For each confirmed defect, add a failing regression test, run it RED, apply the smallest fix, and run it GREEN.

- [ ] **Step 3: Run final verification from a clean worktree**

Run the full offline suite, runtime `-VerifyOnly`, final-output validator on the acceptance result, `git status --short`, and `git diff --check`. Expected: all green and only intentional committed files.

- [ ] **Step 4: Merge into the installed Skill and validate discovery**

Use the finishing-development-branch workflow to merge `codex/implement-bilibili-transcript-refiner` into `main`. Run `quick_validate.py` at `C:\Users\25739\.agents\skills\bilibili-transcript-refiner` and inspect `agents/openai.yaml` there.

- [ ] **Step 5: Publish to GitHub**

Create a GitHub repository named `bilibili-transcript-refiner` under the authenticated personal account, defaulting to private unless the user explicitly requests public visibility, add it as `origin`, and push `main`.
