# Portable First-Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a fresh standalone installation run on the supported Windows x64 AVX2 baseline without preinstalled media or ASR tools, including under a non-ASCII Windows profile.

**Architecture:** Move external asset pins into one JSON manifest consumed by the bootstrap and an online metadata verifier. Add matching PowerShell and Python runtime-layout helpers that prefer an ASCII `%LOCALAPPDATA%` path and otherwise select a per-user ASCII path under `%PUBLIC%`; keep Skill workflow commands independent of the caller's working directory by resolving the active Skill root once and invoking absolute paths.

**Tech Stack:** Windows PowerShell 5.1, Python 3.11+ standard library, `unittest`, JSON, GitHub release API, Hugging Face LFS metadata, GitHub Actions, Codex Skill Markdown.

---

### Task 1: Centralize runtime asset pins and repair fresh installation

**Files:**
- Create: `scripts/runtime-assets.json`
- Modify: `scripts/bootstrap_runtime.ps1`
- Modify: `tests/static-contract.ps1`

- [ ] **Step 1: Write the failing manifest contract**

Replace the bootstrap-string digest assertions in `tests/static-contract.ps1` with a manifest schema and inventory check:

```powershell
$assetManifestPath = Join-Path $repo 'scripts/runtime-assets.json'
if (-not (Test-Path -LiteralPath $assetManifestPath -PathType Leaf)) {
    throw 'scripts/runtime-assets.json is required'
}
$assetManifest = Get-Content -LiteralPath $assetManifestPath -Raw -Encoding utf8 | ConvertFrom-Json
if ($assetManifest.schema_version -ne 1) {
    throw 'runtime asset manifest schema_version must be 1'
}
$expectedAssets = @{
    yt_dlp = @('18226085', '52FE3C26DCF71FBDC85B528589020BB0B8E383155CFA81B64DD447BBE35E24B8')
    ffmpeg = @('111253802', 'FEC81AE03971D9DD4BE3EBE02E263BD2EC1D789483F931BDBA5F5715E65DA2E9')
    funasr_avx2 = @('4916668', '717EDADDC33D26CDA60594262077A8573C52C96784FED9F4EE82CF8154A53935')
    sensevoice = @('254208320', '4AE45C94422DE949B387E2E0FB10D7E14E4C42C69DB30C3444ECC7D4B844B7C5')
    vad = @('1720512', '1270F2559C495F4E7B6E739541151027D360761A3FDA43FC147034F5719F5479')
}
foreach ($id in $expectedAssets.Keys) {
    $asset = @($assetManifest.assets | Where-Object { $_.id -eq $id })
    if ($asset.Count -ne 1) { throw "runtime asset must appear once: $id" }
    if ([string]$asset[0].size -ne $expectedAssets[$id][0]) { throw "runtime asset size changed: $id" }
    if ([string]$asset[0].sha256 -ne $expectedAssets[$id][1]) { throw "runtime asset digest changed: $id" }
    foreach ($field in @('name', 'version', 'provider', 'url', 'size', 'sha256')) {
        if ([string]::IsNullOrWhiteSpace([string]$asset[0].$field)) {
            throw "runtime asset field is missing for ${id}: $field"
        }
    }
}
```

Also require the bootstrap to contain `runtime-assets.json` and `Get-RuntimeAsset`, and remove the obsolete `F2A138...` assertion.

- [ ] **Step 2: Run the contract and verify RED**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tests/static-contract.ps1
```

Expected: FAIL with `scripts/runtime-assets.json is required`.

- [ ] **Step 3: Create the pinned asset manifest**

Create `scripts/runtime-assets.json`:

```json
{
  "schema_version": 1,
  "assets": [
    {
      "id": "yt_dlp",
      "name": "yt-dlp 2026.07.04",
      "version": "2026.07.04",
      "provider": "github",
      "repository": "yt-dlp/yt-dlp",
      "tag": "2026.07.04",
      "asset_name": "yt-dlp.exe",
      "url": "https://github.com/yt-dlp/yt-dlp/releases/download/2026.07.04/yt-dlp.exe",
      "size": 18226085,
      "sha256": "52FE3C26DCF71FBDC85B528589020BB0B8E383155CFA81B64DD447BBE35E24B8"
    },
    {
      "id": "ffmpeg",
      "name": "FFmpeg 9.0.1 essentials",
      "version": "9.0.1",
      "provider": "github",
      "repository": "GyanD/codexffmpeg",
      "tag": "9.0.1",
      "asset_name": "ffmpeg-9.0.1-essentials_build.zip",
      "url": "https://github.com/GyanD/codexffmpeg/releases/download/9.0.1/ffmpeg-9.0.1-essentials_build.zip",
      "size": 111253802,
      "sha256": "FEC81AE03971D9DD4BE3EBE02E263BD2EC1D789483F931BDBA5F5715E65DA2E9"
    },
    {
      "id": "funasr_avx2",
      "name": "FunASR llama.cpp runtime v0.1.8 AVX2",
      "version": "0.1.8",
      "provider": "github",
      "repository": "modelscope/FunASR",
      "tag": "runtime-llamacpp-v0.1.8",
      "asset_name": "funasr-llamacpp-windows-x64-avx2.zip",
      "url": "https://github.com/modelscope/FunASR/releases/download/runtime-llamacpp-v0.1.8/funasr-llamacpp-windows-x64-avx2.zip",
      "size": 4916668,
      "sha256": "717EDADDC33D26CDA60594262077A8573C52C96784FED9F4EE82CF8154A53935"
    },
    {
      "id": "sensevoice",
      "name": "SenseVoiceSmall q8",
      "version": "q8",
      "provider": "huggingface",
      "repository": "FunAudioLLM/SenseVoiceSmall-GGUF",
      "revision": "main",
      "asset_name": "sensevoice-small-q8.gguf",
      "url": "https://huggingface.co/FunAudioLLM/SenseVoiceSmall-GGUF/resolve/main/sensevoice-small-q8.gguf",
      "size": 254208320,
      "sha256": "4AE45C94422DE949B387E2E0FB10D7E14E4C42C69DB30C3444ECC7D4B844B7C5"
    },
    {
      "id": "vad",
      "name": "FSMN-VAD",
      "version": "main",
      "provider": "huggingface",
      "repository": "FunAudioLLM/fsmn-vad-GGUF",
      "revision": "main",
      "asset_name": "fsmn-vad.gguf",
      "url": "https://huggingface.co/FunAudioLLM/fsmn-vad-GGUF/resolve/main/fsmn-vad.gguf",
      "size": 1720512,
      "sha256": "1270F2559C495F4E7B6E739541151027D360761A3FDA43FC147034F5719F5479"
    }
  ]
}
```

- [ ] **Step 4: Load the manifest in the bootstrap**

After bootstrap parameter parsing, load and validate the manifest:

```powershell
$assetManifestPath = Join-Path $PSScriptRoot 'runtime-assets.json'
$assetManifest = Get-Content -LiteralPath $assetManifestPath -Raw -Encoding utf8 | ConvertFrom-Json
if ($assetManifest.schema_version -ne 1) {
    throw "Unsupported runtime asset manifest: $assetManifestPath"
}
function Get-RuntimeAsset {
    param([Parameter(Mandatory = $true)][string]$Id)
    $matches = @($assetManifest.assets | Where-Object { $_.id -eq $Id })
    if ($matches.Count -ne 1) { throw "Runtime asset must appear once: $Id" }
    return $matches[0]
}
```

Replace each hard-coded download URL and digest with `Get-RuntimeAsset` values, for example:

```powershell
$funasrAsset = Get-RuntimeAsset -Id 'funasr_avx2'
$funasrArchive = Ensure-Asset -Name $funasrAsset.name `
    -Url $funasrAsset.url -Sha256 $funasrAsset.sha256 `
    -Destination (Join-Path $downloads $funasrAsset.asset_name)
```

Use the same pattern for `yt_dlp`, `ffmpeg`, `sensevoice`, and `vad`.

- [ ] **Step 5: Run the contract and verify GREEN**

Run the static contract and the existing Python suite. Expected: `static Skill contract: PASS` and 40 tests pass.

- [ ] **Step 6: Commit the asset fix**

```powershell
git add scripts/runtime-assets.json scripts/bootstrap_runtime.ps1 tests/static-contract.ps1
git commit -m "fix: repair pinned runtime assets"
```

### Task 2: Select one portable runtime root in PowerShell and Python

**Files:**
- Create: `scripts/runtime_layout.ps1`
- Create: `scripts/runtime_layout.py`
- Create: `tests/test-runtime-layout.ps1`
- Create: `tests/test_runtime_layout.py`
- Modify: `scripts/bootstrap_runtime.ps1`
- Modify: `scripts/prepare_transcript.py`
- Modify: `tests/test_prepare_transcript.py`
- Modify: `.github/workflows/test.yml`

- [ ] **Step 1: Write failing Python runtime-layout tests**

Create `tests/test_runtime_layout.py` with tests for ASCII selection, Unicode fallback, missing fallback, and the stable key:

```python
import unittest
from pathlib import Path

from scripts.runtime_layout import default_runtime_root, user_key


class RuntimeLayoutTests(unittest.TestCase):
    def test_ascii_local_app_data_keeps_private_runtime(self):
        env = {"LOCALAPPDATA": r"C:\Users\alice\AppData\Local"}
        self.assertEqual(
            default_runtime_root(env),
            Path(r"C:\Users\alice\AppData\Local\bilibili-transcript-refiner\runtime-v1"),
        )

    def test_unicode_profile_uses_ascii_public_per_user_runtime(self):
        env = {
            "LOCALAPPDATA": "C:\\Users\\\u6d4b\u8bd5\\AppData\\Local",
            "PUBLIC": r"C:\Users\Public",
        }
        self.assertEqual(user_key(env["LOCALAPPDATA"]), "7a6eeeb07d1464ab")
        self.assertEqual(
            default_runtime_root(env),
            Path(r"C:\Users\Public\bilibili-transcript-refiner\users\7a6eeeb07d1464ab\runtime-v1"),
        )

    def test_unicode_profile_requires_ascii_public_fallback(self):
        with self.assertRaisesRegex(RuntimeError, "explicit ASCII --runtime-root"):
            default_runtime_root({"LOCALAPPDATA": "C:\\Users\\\u6d4b\u8bd5"})
```

- [ ] **Step 2: Write the failing PowerShell parity test**

Create `tests/test-runtime-layout.ps1`, dot-source the future helper, construct the Chinese path with character codes, and assert the same key and roots:

```powershell
$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts/runtime_layout.ps1')
$savedLocal = $env:LOCALAPPDATA
$savedPublic = $env:PUBLIC
try {
    $env:LOCALAPPDATA = 'C:\Users\alice\AppData\Local'
    if ((Get-BtrDefaultRuntimeRoot) -ne 'C:\Users\alice\AppData\Local\bilibili-transcript-refiner\runtime-v1') {
        throw 'ASCII LOCALAPPDATA selection failed'
    }
    $profile = 'C:\Users\' + [char]0x6D4B + [char]0x8BD5 + '\AppData\Local'
    $env:LOCALAPPDATA = $profile
    $env:PUBLIC = 'C:\Users\Public'
    if ((Get-BtrUserKey -Source $profile) -ne '7a6eeeb07d1464ab') {
        throw 'portable user key mismatch'
    }
    $expected = 'C:\Users\Public\bilibili-transcript-refiner\users\7a6eeeb07d1464ab\runtime-v1'
    if ((Get-BtrDefaultRuntimeRoot) -ne $expected) { throw 'Unicode fallback selection failed' }
} finally {
    $env:LOCALAPPDATA = $savedLocal
    $env:PUBLIC = $savedPublic
}
Write-Output 'runtime layout parity: PASS'
```

- [ ] **Step 3: Run both tests and verify RED**

Run:

```powershell
python -X utf8 -m unittest tests.test_runtime_layout -v
powershell -NoProfile -ExecutionPolicy Bypass -File tests/test-runtime-layout.ps1
```

Expected: both fail because their runtime-layout modules are missing.

- [ ] **Step 4: Implement the Python selector**

Create `scripts/runtime_layout.py`:

```python
from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path


def is_ascii_path(path: Path | str) -> bool:
    try:
        str(path).encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _normalized_source(value: str) -> str:
    return os.path.normcase(os.path.abspath(value)).rstrip("\\/")


def user_key(local_app_data: str) -> str:
    source = _normalized_source(local_app_data).encode("utf-8")
    return hashlib.sha256(source).hexdigest()[:16]


def default_runtime_root(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    local_app_data = env.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("LOCALAPPDATA is not defined")
    primary = Path(local_app_data) / "bilibili-transcript-refiner" / "runtime-v1"
    if is_ascii_path(primary):
        return primary
    public = env.get("PUBLIC")
    if not public:
        raise RuntimeError("Unicode profile requires an explicit ASCII --runtime-root")
    fallback = (
        Path(public)
        / "bilibili-transcript-refiner"
        / "users"
        / user_key(local_app_data)
        / "runtime-v1"
    )
    if not is_ascii_path(fallback):
        raise RuntimeError("Unicode profile requires an explicit ASCII --runtime-root")
    return fallback
```

- [ ] **Step 5: Implement the PowerShell selector**

Create `scripts/runtime_layout.ps1`:

```powershell
function Test-BtrAsciiPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return -not [regex]::IsMatch($Path, '[^\x00-\x7F]')
}

function Get-BtrUserKey {
    param([Parameter(Mandatory = $true)][string]$Source)
    $normalized = [IO.Path]::GetFullPath($Source).TrimEnd('\').ToLowerInvariant()
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $hash = $sha256.ComputeHash([Text.Encoding]::UTF8.GetBytes($normalized))
        return -join ($hash[0..7] | ForEach-Object { $_.ToString('x2') })
    } finally {
        $sha256.Dispose()
    }
}

function Get-BtrDefaultRuntimeRoot {
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw 'LOCALAPPDATA is not defined. Pass -RuntimeRoot C:\btr-runtime or --runtime-root C:\btr-runtime explicitly.'
    }
    $primary = Join-Path $env:LOCALAPPDATA 'bilibili-transcript-refiner\runtime-v1'
    if (Test-BtrAsciiPath -Path $primary) {
        return [IO.Path]::GetFullPath($primary)
    }
    if ([string]::IsNullOrWhiteSpace($env:PUBLIC)) {
        throw 'Unicode profile has no public fallback. Pass -RuntimeRoot C:\btr-runtime or --runtime-root C:\btr-runtime explicitly.'
    }
    $key = Get-BtrUserKey -Source $env:LOCALAPPDATA
    $fallback = Join-Path $env:PUBLIC "bilibili-transcript-refiner\users\$key\runtime-v1"
    if (-not (Test-BtrAsciiPath -Path $fallback)) {
        throw 'Unicode profile has no ASCII public fallback. Pass -RuntimeRoot C:\btr-runtime or --runtime-root C:\btr-runtime explicitly.'
    }
    return [IO.Path]::GetFullPath($fallback)
}
```

- [ ] **Step 6: Wire defaults without breaking explicit precedence**

Change the bootstrap parameter from an eager default to `[string]$RuntimeRoot`, dot-source `runtime_layout.ps1`, and set the default only when the argument is empty:

```powershell
. (Join-Path $PSScriptRoot 'runtime_layout.ps1')
if ([string]::IsNullOrWhiteSpace($RuntimeRoot)) {
    $RuntimeRoot = Get-BtrDefaultRuntimeRoot
}
```

Import `default_runtime_root` into `prepare_transcript.py`, change `--runtime-root` to `default=None`, then select after parsing:

```python
parser.add_argument("--runtime-root", type=Path)
args = parser.parse_args()
runtime_root = args.runtime_root if args.runtime_root is not None else default_runtime_root()
result = prepare_transcript(args.url, args.output_root, runtime_root, rerun_asr=args.rerun_asr)
```

Add imports to `tests/test_prepare_transcript.py`:

```python
from types import SimpleNamespace
from unittest.mock import patch

from scripts.prepare_transcript import _job_directory, main, prepare_transcript
```

Then add the exact regression test to `PrepareTranscriptTests`:

```python
    def test_main_does_not_evaluate_default_when_runtime_root_is_explicit(self):
        explicit = self.base / "explicit-runtime"
        result = SimpleNamespace(
            job_manifest={"state": "asr_complete"},
            raw_path=self.base / "raw.jsonl",
            job_dir=self.base / "job",
            page_defaulted=False,
            reused=False,
        )
        argv = [
            "prepare_transcript.py",
            "--url",
            "https://www.bilibili.com/video/BV1rnGt61E4j/",
            "--output-root",
            str(self.output),
            "--runtime-root",
            str(explicit),
        ]
        with (
            patch("scripts.prepare_transcript.default_runtime_root") as default_root,
            patch("scripts.prepare_transcript.prepare_transcript", return_value=result) as prepare,
            patch("sys.argv", argv),
        ):
            default_root.side_effect = AssertionError("default must stay lazy")
            self.assertEqual(main(), 0)
        default_root.assert_not_called()
        prepare.assert_called_once_with(
            argv[2], self.output, explicit, rerun_asr=False
        )
```

This proves the fallback is not evaluated eagerly.

- [ ] **Step 7: Add the PowerShell parity test to CI and verify GREEN**

Add this workflow step after Python tests:

```yaml
      - name: Runtime layout parity
        shell: powershell
        run: powershell -NoProfile -ExecutionPolicy Bypass -File tests/test-runtime-layout.ps1
```

Run both focused tests and the full Python suite. Expected: parity PASS and all Python tests pass.

- [ ] **Step 8: Commit portable runtime selection**

```powershell
git add scripts/runtime_layout.ps1 scripts/runtime_layout.py scripts/bootstrap_runtime.ps1 scripts/prepare_transcript.py tests/test-runtime-layout.ps1 tests/test_runtime_layout.py tests/test_prepare_transcript.py .github/workflows/test.yml
git commit -m "fix: select portable Windows runtime paths"
```

### Task 3: Add actionable bootstrap failures

**Files:**
- Modify: `scripts/bootstrap_runtime.ps1`
- Modify: `tests/static-contract.ps1`

- [ ] **Step 1: Write failing diagnostic contracts**

Require these bootstrap messages and helpers in `tests/static-contract.ps1`:

```powershell
foreach ($needle in @(
    'Assert-RuntimeWritable',
    'Assert-FreeSpace',
    'at least 1 GiB of free space',
    'Check internet, proxy, and TLS access',
    'AVX2, FMA, F16C, and BMI2'
)) {
    if (-not $bootstrap.Contains($needle)) {
        throw "missing bootstrap diagnostic contract: $needle"
    }
}
```

- [ ] **Step 2: Run the contract and verify RED**

Expected: FAIL with the first missing diagnostic contract.

- [ ] **Step 3: Implement writable and free-space preflight**

Add these helpers:

```powershell
function Assert-RuntimeWritable {
    param([Parameter(Mandatory = $true)][string]$Path)
    $probe = Join-Path $Path ('.write-probe-' + [Guid]::NewGuid().ToString('N'))
    try {
        [IO.File]::WriteAllText($probe, 'probe')
        Remove-Item -LiteralPath $probe
    } catch {
        $detail = $_.Exception.Message
        if (Test-Path -LiteralPath $probe -PathType Leaf) {
            try { Remove-Item -LiteralPath $probe -ErrorAction SilentlyContinue } catch {}
        }
        throw "Runtime root is not writable: $Path. Pass an ASCII writable -RuntimeRoot C:\btr-runtime. $detail"
    }
}

function Assert-FreeSpace {
    param([Parameter(Mandatory = $true)][string]$Path)
    $drive = (Get-Item -LiteralPath $Path).PSDrive
    if ($null -ne $drive -and $null -ne $drive.Free -and $drive.Free -lt 1GB) {
        throw "Runtime setup needs at least 1 GiB of free space: $Path"
    }
}
```

Immediately after creating `$RuntimeRoot`, run:

```powershell
Assert-RuntimeWritable -Path $RuntimeRoot
if (-not $VerifyOnly) {
    Assert-FreeSpace -Path $RuntimeRoot
}
```

- [ ] **Step 4: Wrap network failures without removing evidence**

Wrap `Invoke-WebRequest` in `Ensure-Asset`:

```powershell
try {
    Invoke-WebRequest -Uri $Url -OutFile $partial -UseBasicParsing
} catch {
    throw "Failed to download $Name. Check internet, proxy, and TLS access. Partial file: $partial. $($_.Exception.Message)"
}
```

Keep the partial file and retain the existing SHA-256 check.

- [ ] **Step 5: Add the AVX2 startup explanation**

Wrap the SenseVoice and VAD startup checks together. On failure, throw:

```text
FunASR AVX2 runtime could not start. This release requires a Windows x64 CPU with AVX2, FMA, F16C, and BMI2; security software may also block the executable.
```

Append the original failure detail.

- [ ] **Step 6: Run the static and full tests and verify GREEN**

Expected: the static contract passes and all Python tests remain green.

- [ ] **Step 7: Commit bootstrap diagnostics**

```powershell
git add scripts/bootstrap_runtime.ps1 tests/static-contract.ps1
git commit -m "fix: explain Windows bootstrap failures"
```

### Task 4: Make the Skill independent of shell working directory

**Files:**
- Modify: `SKILL.md`
- Modify: `README.md`
- Modify: `tests/static-contract.ps1`

- [ ] **Step 1: Write failing Skill and README contracts**

Require `<SKILL_DIR>`, `Never assume the shell current working directory`, absolute quoted script forms, `Windows 10/11 x64`, `Python 3.11+`, `PowerShell 5.1+`, `AVX2`, `372 MiB`, `700 MiB`, `$skill-installer`, `$HOME/.agents/skills`, and the automatic model download claim. Remove assertions for bare `scripts/...` commands.

- [ ] **Step 2: Run the contract and verify RED**

Expected: FAIL with `missing Skill contract: <SKILL_DIR>`.

- [ ] **Step 3: Update the agent workflow**

Make workflow step 1 resolve the directory containing the loaded `SKILL.md` as `<SKILL_DIR>` and state `Never assume the shell current working directory is the Skill directory.` Use:

```text
powershell -NoProfile -ExecutionPolicy Bypass -File "<SKILL_DIR>\scripts\bootstrap_runtime.ps1"
python -X utf8 "<SKILL_DIR>\scripts\prepare_transcript.py" --url "<URL>" --output-root "<DIR>"
python -X utf8 "<SKILL_DIR>\scripts\finalize_transcript.py" --job-dir "<JOB_DIR>" --output-root "<DIR>" --status complete
```

Read both references using absolute paths under `<SKILL_DIR>` while retaining their Markdown links for discoverability.

- [ ] **Step 4: Expand the existing README**

Replace the existing short README with this complete content:

````markdown
# Bilibili Transcript Refiner

把一个完整的 B 站 BV 视频链接转换成可追溯的原始识别稿和严格忠实校订稿。

## 功能

- 使用本地 SenseVoiceSmall 将视频音轨转成带全局时间戳的原始识别证据。
- 由 Codex 结合上下文校订明显的识别错误、术语、人名、断句和标点。
- 最终固定输出 `raw-transcript.jsonl` 和 `corrected-transcript.md`。

## 运行要求

- Windows 10/11 x64。
- Python 3.11+ 和 PowerShell 5.1+。
- CPU 支持 AVX2、FMA、F16C 和 BMI2。
- 首次安装可访问 GitHub、Hugging Face 和 Bilibili。

不需要预装 yt-dlp、FFmpeg、FunASR 或语音模型。首次运行会自动下载五个固定版本且经过 SHA-256 校验的依赖，传输约 372 MiB；安装后约占 700 MiB，尚不包含后续视频任务文件。

## 安装

可以让 Codex 使用 `$skill-installer` 从以下 GitHub 仓库安装：

```text
https://github.com/jiangweiqi001/bilibili-transcript-refiner
```

也可以直接克隆到 Codex 的个人 Skill 目录：

```powershell
git clone https://github.com/jiangweiqi001/bilibili-transcript-refiner "$HOME/.agents/skills/bilibili-transcript-refiner"
```

## 首次运行

直接在 Codex 中调用 Skill；它会先引导执行引导脚本并自动准备工具与模型：

```text
请使用 $bilibili-transcript-refiner 处理 https://www.bilibili.com/video/BV1xxxxxxxxx/，输出到 D:\B站逐字稿。
```

需要单独检查或预装运行时，也可从任意工作目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<SKILL_DIR>\scripts\bootstrap_runtime.ps1"
```

## 中文 Windows 用户名

FunASR 运行路径必须为 ASCII。若 `%LOCALAPPDATA%` 含中文或其他非 ASCII 字符，脚本会自动切换到 `%PUBLIC%\bilibili-transcript-refiner\users\<user-key>\runtime-v1`，不同用户之间不会共享可写任务目录。若公共目录也不可用，按报错提示显式传入 ASCII 路径，例如 `-RuntimeRoot C:\btr-runtime`。

## 忠实性原则

- 严格忠实：不润色、不概括、不把口语改写成书面语。
- 可追溯：保留不可变原始识别稿、逐段时间戳和校订结果。
- 不猜测：无法确认时使用 `[疑似：候选词]` 或 `[听不清]`。
- 可恢复：支持断点续跑、哈希校验、任务隔离和并发防覆盖。
````

- [ ] **Step 5: Run static contract and Skill validators and verify GREEN**

Run `tests/static-contract.ps1`, `tests/quick_validate_skill.py .`, and the system `quick_validate.py`. Expected: all pass.

- [ ] **Step 6: Commit the portable workflow documentation**

```powershell
git add SKILL.md README.md tests/static-contract.ps1
git commit -m "docs: explain portable Skill setup"
```

### Task 5: Detect upstream asset drift without downloading models

**Files:**
- Create: `tests/verify-runtime-assets.ps1`
- Modify: `.github/workflows/test.yml`
- Modify: `tests/static-contract.ps1`

- [ ] **Step 1: Write the failing workflow contract**

Require `workflow_dispatch`, `schedule`, `cron`, `verify-runtime-assets.ps1`, and `Runtime asset metadata` in `.github/workflows/test.yml`. Require the verifier file to exist. Run the static contract and expect failure because the workflow and verifier are absent.

- [ ] **Step 2: Implement GitHub release metadata checks**

In `tests/verify-runtime-assets.ps1`, load `scripts/runtime-assets.json`. For each `github` entry, call:

```powershell
$headers = @{ 'User-Agent' = 'bilibili-transcript-refiner-asset-check'; Accept = 'application/vnd.github+json' }
$release = Invoke-RestMethod -Uri "https://api.github.com/repos/$($asset.repository)/releases/tags/$($asset.tag)" -Headers $headers
$remote = @($release.assets | Where-Object { $_.name -eq $asset.asset_name })
```

Require exactly one match, compare integer `size`, strip the `sha256:` prefix from `digest`, and compare uppercase SHA-256.

- [ ] **Step 3: Implement Hugging Face LFS metadata checks**

Complete `tests/verify-runtime-assets.ps1` as follows (this includes both providers so the resource lifecycle is explicit):

```powershell
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Net.Http

$repo = Split-Path -Parent $PSScriptRoot
$manifestPath = Join-Path $repo 'scripts/runtime-assets.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
if ($manifest.schema_version -ne 1) { throw 'unsupported runtime asset manifest' }

function Get-HeaderValue {
    param(
        [Parameter(Mandatory = $true)]$Response,
        [Parameter(Mandatory = $true)][string]$Name
    )
    foreach ($headers in @($Response.Headers, $Response.Content.Headers)) {
        if ($headers.Contains($Name)) {
            return @($headers.GetValues($Name))[0]
        }
    }
    throw "remote response lacks $Name"
}

$githubHeaders = @{
    'User-Agent' = 'bilibili-transcript-refiner-asset-check'
    Accept = 'application/vnd.github+json'
}
$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.AllowAutoRedirect = $false
$client = [System.Net.Http.HttpClient]::new($handler)
try {
    foreach ($asset in $manifest.assets) {
        if ($asset.provider -eq 'github') {
            $releaseUrl = "https://api.github.com/repos/$($asset.repository)/releases/tags/$($asset.tag)"
            $release = Invoke-RestMethod -Uri $releaseUrl -Headers $githubHeaders
            $remote = @($release.assets | Where-Object { $_.name -eq $asset.asset_name })
            if ($remote.Count -ne 1) { throw "remote GitHub asset must appear once: $($asset.id)" }
            if ([Int64]$remote[0].size -ne [Int64]$asset.size) {
                throw "remote size changed: $($asset.id)"
            }
            $digest = ([string]$remote[0].digest) -replace '^sha256:', ''
            if ($digest.ToUpperInvariant() -ne ([string]$asset.sha256).ToUpperInvariant()) {
                throw "remote digest changed: $($asset.id)"
            }
        } elseif ($asset.provider -eq 'huggingface') {
            $request = [System.Net.Http.HttpRequestMessage]::new(
                [System.Net.Http.HttpMethod]::Head,
                [string]$asset.url
            )
            $response = $null
            try {
                $response = $client.SendAsync($request).GetAwaiter().GetResult()
                $status = [int]$response.StatusCode
                if ($status -lt 200 -or $status -ge 400) {
                    throw "Hugging Face HEAD failed with HTTP $status for $($asset.id)"
                }
                $linkedSize = Get-HeaderValue -Response $response -Name 'X-Linked-Size'
                $linkedEtag = (Get-HeaderValue -Response $response -Name 'X-Linked-ETag').Trim('"')
                if ([Int64]$linkedSize -ne [Int64]$asset.size) {
                    throw "remote size changed: $($asset.id)"
                }
                if ($linkedEtag.ToUpperInvariant() -ne ([string]$asset.sha256).ToUpperInvariant()) {
                    throw "remote digest changed: $($asset.id)"
                }
            } finally {
                if ($null -ne $response) { $response.Dispose() }
                $request.Dispose()
            }
        } else {
            throw "unsupported runtime asset provider: $($asset.provider)"
        }
        Write-Output "verified remote asset: $($asset.id)"
    }
} finally {
    $client.Dispose()
    $handler.Dispose()
}
Write-Output 'runtime asset metadata: PASS'
```

- [ ] **Step 4: Add online verification triggers**

Extend the workflow:

```yaml
on:
  push:
  pull_request:
  workflow_dispatch:
  schedule:
    - cron: "17 3 * * 1"
```

Add:

```yaml
      - name: Runtime asset metadata
        shell: powershell
        run: powershell -NoProfile -ExecutionPolicy Bypass -File tests/verify-runtime-assets.ps1
```

- [ ] **Step 5: Run verifier and contracts and verify GREEN**

Run the online verifier, static contract, and full test suite. Expected: five remote assets verified, metadata PASS, static PASS, and all Python tests pass.

- [ ] **Step 6: Commit drift detection**

```powershell
git add tests/verify-runtime-assets.ps1 tests/static-contract.ps1 .github/workflows/test.yml
git commit -m "test: verify remote runtime asset pins"
```

### Task 6: Verify a fresh external-working-directory run and publish

**Files:**
- Verify: all changed files
- Create outside repository: isolated runtime and acceptance output under the current Codex `work` directory

- [ ] **Step 1: Run the complete local verification**

```powershell
python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v
powershell -NoProfile -ExecutionPolicy Bypass -File tests/test-runtime-layout.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tests/static-contract.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tests/verify-runtime-assets.ps1
python -X utf8 tests/quick_validate_skill.py .
python -X utf8 C:\Users\25739\.codex\skills\.system\skill-creator\scripts\quick_validate.py .
git diff --check
```

Expected: all tests and validators pass with no diff errors.

- [ ] **Step 2: Bootstrap a brand-new runtime**

From `C:\Users\25739\Documents\Codex\2026-08-13\new-chat`, choose a new, nonexistent ASCII directory under `work` and run the bootstrap by absolute Skill path with `-RuntimeRoot`. Do not delete or reuse an earlier audit directory. Expected: all five assets install, packages expand, startup checks pass, and `runtime.json` is printed.

- [ ] **Step 3: Verify the installed runtime**

Run the same absolute bootstrap command with `-VerifyOnly`. Expected: five assets and two expanded packages verify successfully.

- [ ] **Step 4: Run real Bilibili ASR outside the Skill directory**

From the Codex workspace directory, invoke `prepare_transcript.py` by absolute Skill path for `https://www.bilibili.com/video/BV1GJ411x7h7/?p=1`, pass the fresh runtime explicitly, and use a new Unicode output root under `work`. Expected: JSON reports `state: asr_complete`, the raw transcript exists, and it has at least one valid row.

- [ ] **Step 5: Review intended changes and commit any final test-only adjustment**

Run `git status --short`, `git diff --stat origin/main...HEAD`, `git diff --check`, and inspect every changed file. If no adjustment is needed, create no empty commit.

- [ ] **Step 6: Fast-forward main and push**

If implementation used a worktree branch, fast-forward local `main` to it. Re-run `git status --short --branch`, confirm local `main` contains only the reviewed commits, then run:

```powershell
git push origin main
```

Expected: push succeeds and `origin/main` points to the verified local `HEAD`.

- [ ] **Step 7: Confirm GitHub Actions**

Open the workflow run for the pushed commit and wait until `windows-contracts` succeeds. If it fails, diagnose and fix in a new RED-GREEN cycle before reporting completion.
