# Explicit Output Mode Design

## Problem

The workflow correctly supports validated Chinese translation checkpoints and bilingual rendering, but source-only output is the implicit default. An agent can classify an English recording as bilingual, accidentally omit `--bilingual`, and still receive a successful source-only deliverable. The finalizer cannot distinguish that omission from an intentional source-only choice.

## Decision

Require an explicit output-mode choice at finalization. The command line must receive exactly one of `--bilingual` or `--source-only`, and the Python API must receive an explicit `bilingual=True` or `bilingual=False`. Keep language classification in the agent workflow because the existing mixed-language rule requires contextual judgment; do not add a brittle ASCII-ratio classifier or another translation model.

The bilingual path continues to require a complete, source-bound `translations-zh.jsonl`. The source-only path keeps the current formal Markdown shape. Existing job state remains reusable: callers only need to choose an output mode when finalizing.

## Documentation

Update `SKILL.md`, the output contract, and README examples so every finalization command names its mode. State that predominantly English speech defaults to bilingual unless the user explicitly requests source-only output, and that `--source-only` is the auditable override.

## Verification

Add regression coverage that omission is rejected by both the Python API and CLI parser, while explicit source-only and bilingual calls retain their existing behavior. Run the targeted finalizer tests, static documentation contract, full unit suite, Skill validator, and diff checks before pushing.
