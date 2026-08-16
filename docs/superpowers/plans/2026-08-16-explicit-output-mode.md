# Explicit Output Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent an English transcript from being silently finalized as source-only when the bilingual flag is accidentally omitted.

**Architecture:** Keep contextual language classification in `SKILL.md`, but make finalization mechanically require an explicit source-only or bilingual choice. Preserve existing translation checkpoints and rendering; change only the mode-selection boundary and its documentation.

**Tech Stack:** Python 3 standard library, `unittest`, PowerShell static-contract checks, Markdown Skill documentation.

---

### Task 1: Prove the implicit default is unsafe

**Files:**
- Modify: `tests/test_finalize_transcript.py`

- [ ] Add a test that calls `finalize_transcript(..., status="complete")` without a mode and expects an error containing `output mode`.
- [ ] Add a subprocess test that invokes `scripts/finalize_transcript.py` without either mode flag and expects argparse exit code 2 mentioning `--bilingual` and `--source-only`.
- [ ] Run `python -X utf8 -m unittest tests.test_finalize_transcript` and confirm both tests fail because source-only is still implicit.

### Task 2: Require an explicit mode

**Files:**
- Modify: `scripts/finalize_transcript.py`
- Modify: `tests/test_finalize_transcript.py`

- [ ] Change the Python API default to `bilingual: bool | None = None` and reject `None` before reading or writing job artifacts:

```python
if bilingual is None:
    raise ValueError("output mode is required; pass bilingual=True or bilingual=False")
```

- [ ] Replace the optional CLI flag with a required mutually exclusive group:

```python
mode = parser.add_mutually_exclusive_group(required=True)
mode.add_argument("--bilingual", action="store_true")
mode.add_argument("--source-only", action="store_true")
```

- [ ] Map the parsed choice to `bilingual=args.bilingual` and update every existing finalizer test call to pass `bilingual=False` unless the test already passes `True`.
- [ ] Run `python -X utf8 -m unittest tests.test_finalize_transcript` and confirm the finalizer tests pass.

### Task 3: Make the Skill and public examples unambiguous

**Files:**
- Modify: `SKILL.md`
- Modify: `references/output-contract.md`
- Modify: `README.md`
- Modify: `tests/static-contract.ps1`

- [ ] Add static assertions that both canonical finalization modes are documented and that the old flagless source-only command is absent.
- [ ] Run `powershell -NoProfile -ExecutionPolicy Bypass -File tests/static-contract.ps1` and confirm RED.
- [ ] Update the workflow and command examples so English defaults to `--bilingual`, while intentional source-only output always uses `--source-only`.
- [ ] State that mode omission is an error and no translation model is downloaded by this change.
- [ ] Re-run the static contract and confirm GREEN.

### Task 4: Verify and publish

**Files:**
- Verify all changed files.

- [ ] Run `python -X utf8 -m unittest` and require zero failures.
- [ ] Run `powershell -NoProfile -ExecutionPolicy Bypass -File tests/static-contract.ps1`.
- [ ] Run the repository Skill validator and `git diff --check`.
- [ ] Inspect the final diff for unrelated edits, README first-line preservation, and unchanged pinned VAD revision.
- [ ] Commit the implementation, merge it into `main`, push `origin/main`, and verify the remote commit hash.
