# Chinese README Public Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an intentionally minimal Chinese README containing only functions, highlights, and one usage example, then publish the verified repository publicly.

**Architecture:** Keep the README as repository-facing documentation without changing the runtime Skill instructions. Extend the existing PowerShell static contract so CI enforces the README's three sections and core claims, then reuse the existing Windows test workflow for publication verification.

**Tech Stack:** Markdown, PowerShell 5.1, Python 3.13 `unittest`, Codex Skill validator, Git, GitHub CLI, GitHub Actions.

---

### Task 1: Add the minimal Chinese README contract

**Files:**
- Create: `README.md`
- Modify: `tests/static-contract.ps1`

- [ ] **Step 1: Write the failing static contract**

Remove `README.md` from the forbidden-file list, require the file, and require these exact structural and factual markers:

```powershell
$readmePath = Join-Path $repo 'README.md'
if (-not (Test-Path -LiteralPath $readmePath -PathType Leaf)) {
    throw 'README.md is required for the public repository'
}
$readme = Get-Content -LiteralPath $readmePath -Raw -Encoding utf8
foreach ($needle in @(
    '## 功能',
    '## 亮点',
    '## 使用示例',
    'SenseVoiceSmall',
    'Codex',
    'raw-transcript.jsonl',
    'corrected-transcript.md',
    '$bilibili-transcript-refiner'
)) {
    if (-not $readme.Contains($needle)) {
        throw "missing README contract: $needle"
    }
}
```

- [ ] **Step 2: Run the contract and verify RED**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tests/static-contract.ps1
```

Expected: FAIL with `README.md is required for the public repository`.

- [ ] **Step 3: Write the minimal README**

Create `README.md` with exactly this scope:

````markdown
# Bilibili Transcript Refiner

把一个完整的 B 站 BV 视频链接转换成可追溯的原始识别稿和严格忠实校订稿。

## 功能

- 使用本地 SenseVoiceSmall 将视频音轨转成带全局时间戳的原始识别证据。
- 由 Codex 结合上下文校订明显的识别错误、术语、人名、断句和标点。
- 最终固定输出 `raw-transcript.jsonl` 和 `corrected-transcript.md`。

## 亮点

- 严格忠实：不润色、不概括、不把口语改写成书面语。
- 可追溯：保留不可变原始识别稿、逐段时间戳和校订结果。
- 不猜测：无法确认时使用 `[疑似：候选词]` 或 `[听不清]`。
- 可恢复：支持断点续跑、哈希校验、任务隔离和并发防覆盖。

## 使用示例

```text
请使用 $bilibili-transcript-refiner 处理 https://www.bilibili.com/video/BV1xxxxxxxxx/，输出到 D:\B站逐字稿。
```
````

- [ ] **Step 4: Run the contract and verify GREEN**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tests/static-contract.ps1
```

Expected: `static Skill contract: PASS`.

- [ ] **Step 5: Commit the README change**

```powershell
git add README.md tests/static-contract.ps1
git commit -m "docs: add concise Chinese README"
```

### Task 2: Verify and publish publicly

**Files:**
- Verify: `README.md`
- Verify: `SKILL.md`
- Verify: `.github/workflows/test.yml`

- [ ] **Step 1: Run the complete local verification**

```powershell
python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v
powershell -NoProfile -ExecutionPolicy Bypass -File tests/static-contract.ps1
python -X utf8 tests/quick_validate_skill.py .
python -X utf8 C:\Users\25739\.codex\skills\.system\skill-creator\scripts\quick_validate.py .
git diff --check
```

Expected: 40 Python tests pass, both Skill validators report `Skill is valid!`, the static contract passes, and the diff check is clean.

- [ ] **Step 2: Merge and push `main`**

```powershell
git -C C:\Users\25739\.agents\skills\bilibili-transcript-refiner merge --ff-only codex/implement-bilibili-transcript-refiner
git -C C:\Users\25739\.agents\skills\bilibili-transcript-refiner push origin main
```

Expected: the installed `main` fast-forwards and the remote `main` receives the README commit.

- [ ] **Step 3: Change repository visibility to public**

```powershell
gh repo edit jiangweiqi001/bilibili-transcript-refiner --visibility public --accept-visibility-change-consequences
gh repo view jiangweiqi001/bilibili-transcript-refiner --json visibility,url,defaultBranchRef
```

Expected: `visibility` is `PUBLIC` and the default branch is `main`.

- [ ] **Step 4: Wait for the pushed Windows CI run**

Select the run whose `headSha` equals local `main`, then wait for it:

```powershell
$headSha = git -C C:\Users\25739\.agents\skills\bilibili-transcript-refiner rev-parse HEAD
$runs = gh run list --repo jiangweiqi001/bilibili-transcript-refiner --workflow test.yml --limit 10 --json databaseId,headSha | ConvertFrom-Json
$runId = ($runs | Where-Object { $_.headSha -eq $headSha } | Select-Object -First 1).databaseId
gh run watch $runId --repo jiangweiqi001/bilibili-transcript-refiner --interval 5 --exit-status
```

Expected: Python tests, static contract, Skill package validation, and diff hygiene all pass.

- [ ] **Step 5: Verify publication identity**

Compare local `HEAD`, `git ls-remote origin refs/heads/main`, repository visibility, and the successful CI `headSha`. Require an empty `git status --porcelain` before reporting completion.
