$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$skillPath = Join-Path $repo 'SKILL.md'
if (-not (Test-Path -LiteralPath $skillPath -PathType Leaf)) {
    throw 'SKILL.md is required'
}

$skill = Get-Content -LiteralPath $skillPath -Raw -Encoding utf8
$bStation = 'B' + [char]0x7AD9
$suspectMarker = '[' + [char]0x7591 + [char]0x4F3C + [char]0xFF1A
$inaudibleMarker = '[' + [char]0x542C + [char]0x4E0D + [char]0x6E05 + ']'
$required = @(
    'name: bilibili-transcript-refiner',
    'description: Use when',
    'Bilibili',
    $bStation,
    'Windows',
    'SenseVoiceSmall',
    'raw-transcript.jsonl',
    'corrected-transcript.md',
    $suspectMarker,
    $inaudibleMarker,
    'references/faithful-correction.md',
    'references/output-contract.md'
    'full bilibili.com/video/BV'
    '<SKILL_DIR>'
    'Never assume the shell current working directory is the Skill directory.'
    '"<SKILL_DIR>\references\output-contract.md"'
    '"<SKILL_DIR>\references\faithful-correction.md"'
    'Get-BtrDefaultRuntimeRoot'
    'powershell -NoProfile -ExecutionPolicy Bypass -File "<SKILL_DIR>\scripts\bootstrap_runtime.ps1" -RuntimeRoot "<RUNTIME_ROOT>"'
    'python -X utf8 "<SKILL_DIR>\scripts\prepare_transcript.py" --url "<URL>" --output-root "<DIR>" --runtime-root "<RUNTIME_ROOT>"'
    'python -X utf8 "<SKILL_DIR>\scripts\checkpoint_corrections.py" --raw "<RAW_JSONL>" --checkpoint "<JOB_DIR>\corrections.jsonl" --batch "<BATCH_JSONL>"'
    '--replace-from <ROW_INDEX> --expected-corrections-sha256 "<CURRENT_CORRECTIONS_SHA256>"'
    'python -X utf8 "<SKILL_DIR>\scripts\review_corrections.py" list --job-dir "<JOB_DIR>"'
    'python -X utf8 "<SKILL_DIR>\scripts\review_corrections.py" record --job-dir "<JOB_DIR>" --finding-id "<FINDING_ID>" --decision confirmed --note "<REVIEW_NOTE>"'
    'python -X utf8 "<SKILL_DIR>\scripts\finalize_transcript.py" --job-dir "<JOB_DIR>" --output-root "<DIR>" --status complete'
    'correction-audit.json'
    'correction-reviews.json'
)
foreach ($needle in $required) {
    if (-not $skill.Contains($needle)) {
        throw "missing Skill contract: $needle"
    }
}

$frontmatter = [regex]::Match($skill, '(?s)\A---\r?\n(.*?)\r?\n---').Groups[1].Value
$keys = @([regex]::Matches($frontmatter, '(?m)^([a-zA-Z0-9_-]+):') | ForEach-Object { $_.Groups[1].Value })
if (($keys -join ',') -ne 'name,description') {
    throw "SKILL.md frontmatter must contain only name and description; got: $($keys -join ',')"
}

foreach ($ref in @('references/faithful-correction.md', 'references/output-contract.md')) {
    if (-not (Test-Path -LiteralPath (Join-Path $repo $ref) -PathType Leaf)) {
        throw "missing reference: $ref"
    }
}

$uiPath = Join-Path $repo 'agents/openai.yaml'
if (-not (Test-Path -LiteralPath $uiPath -PathType Leaf)) {
    throw 'agents/openai.yaml is required'
}
$ui = Get-Content -LiteralPath $uiPath -Raw -Encoding utf8
if (-not $ui.Contains('$bilibili-transcript-refiner')) {
    throw 'default_prompt must explicitly mention $bilibili-transcript-refiner'
}

foreach ($forbidden in @('INSTALLATION_GUIDE.md', 'QUICK_REFERENCE.md', 'CHANGELOG.md')) {
    if (Test-Path -LiteralPath (Join-Path $repo $forbidden)) {
        throw "extraneous Skill file: $forbidden"
    }
}

$readmePath = Join-Path $repo 'README.md'
if (-not (Test-Path -LiteralPath $readmePath -PathType Leaf)) {
    throw 'README.md is required for the public repository'
}
$readme = Get-Content -LiteralPath $readmePath -Raw -Encoding utf8
$requiredFirstLine = [string][char]0x70B9 + [char]0x70B9 + [char]0x5173 + [char]0x6CE8 + [char]0x8C22 + [char]0x8C22 + [char]0x55B5
$favoritesWord = [string][char]0x6536 + [char]0x85CF + [char]0x5939
$classRepWord = [string][char]0x8BFE + [char]0x4EE3 + [char]0x8868
$uploaderWord = 'UP ' + [char]0x4E3B
$tripleActionWord = [string][char]0x4E00 + [char]0x952E + [char]0x4E09 + [char]0x8FDE
$progressBarWord = [string][char]0x8FDB + [char]0x5EA6 + [char]0x6761
$noSummaryWord = [string][char]0x4E0D + [char]0x505A + [char]0x7701 + [char]0x6D41 + [char]0x7248
$onePageClaim = [string][char]0x6BCF + [char]0x6B21 + [char]0x8C03 + [char]0x7528 + [char]0x53EA + [char]0x5904 + [char]0x7406 + [char]0x4E00 + [char]0x4E2A + [char]0x89C6 + [char]0x9891 + [char]0x9875 + [char]0x9762
$readmeFirstLine = @($readme -split "`r?`n", 2)[0]
if ($readmeFirstLine -cne $requiredFirstLine) {
    throw 'README first line must be exact'
}
$promotionalRequired = @(
    'actions/workflows/test.yml/badge.svg',
    'yt-dlp -> FFmpeg -> FSMN-VAD -> SenseVoiceSmall',
    'b23.tv',
    'bili2233.cn',
    '73',
    '46',
    '2026-08-14',
    'Star',
    'github.com/jiangweiqi001/bilibili-transcript-refiner/issues',
    'scripts/runtime-assets.json',
    'references/faithful-correction.md',
    'tests/test_prepare_transcript.py',
    'tests/test_finalize_transcript.py',
    'Codex token',
    ([string][char]0x51C6 + [char]0x786E + [char]0x7387 + [char]0x662F + [char]0x591A + [char]0x5C11),
    '{"start":"00:00:12.400","end":"00:00:18.720","text":',
    '[00:00:12.400]',
    $onePageClaim
    $favoritesWord
    $classRepWord
    $uploaderWord
    $tripleActionWord
    $progressBarWord
    $noSummaryWord
)
foreach ($needle in $promotionalRequired) {
    if (-not $readme.Contains($needle)) {
        throw "missing promotional README contract: $needle"
    }
}
if ([regex]::Matches($readme, [regex]::Escape($classRepWord)).Count -ne 1) {
    throw 'README should use the class-representative phrase exactly once'
}
if ($readme.Contains('one video/page per invocation')) {
    throw 'README video boundary should use natural Chinese'
}
$functionHeading = '## ' + [char]0x529F + [char]0x80FD
$firstRunHeading = '## ' + [char]0x9996 + [char]0x6B21 + [char]0x8FD0 + [char]0x884C
$automaticDownloadClaim = [string][char]0x81EA + [char]0x52A8 + [char]0x4E0B + [char]0x8F7D + [char]0x4E94 + [char]0x4E2A
$aclReaders = '"\u5f53\u524d Windows \u7528\u6237\u3001SYSTEM \u548c Administrators"' | ConvertFrom-Json
$resumeOverclaim = '"\u4e0b\u8f7d\u3001\u8f6c\u7801\u3001VAD\u3001ASR \u548c\u6821\u8ba2\u90fd\u6709\u53ef\u6062\u590d\u72b6\u6001"' | ConvertFrom-Json
foreach ($needle in @(
    $functionHeading,
    $firstRunHeading,
    'SenseVoiceSmall',
    'Codex',
    'raw-transcript.jsonl',
    'corrected-transcript.md',
    '$bilibili-transcript-refiner',
    'Windows 10/11 x64',
    'Python 3.11+',
    'PowerShell 5.1+',
    'AVX2',
    '372 MiB',
    '700 MiB',
    '$skill-installer',
    '--repo jiangweiqi001/bilibili-transcript-refiner --path . --name bilibili-transcript-refiner',
    '$HOME/.agents/skills',
    $automaticDownloadClaim,
    '%PUBLIC%\bilibili-transcript-refiner\users\<user-key>\runtime-v1'
    $aclReaders
    '-RuntimeRoot $runtimeRoot'
    '--runtime-root $runtimeRoot'
)) {
    if (-not $readme.Contains($needle)) {
        throw "missing README contract: $needle"
    }
}

$bootstrapPath = Join-Path $repo 'scripts/bootstrap_runtime.ps1'
if (-not (Test-Path -LiteralPath $bootstrapPath -PathType Leaf)) {
    throw 'scripts/bootstrap_runtime.ps1 is required'
}
$bootstrap = Get-Content -LiteralPath $bootstrapPath -Raw -Encoding utf8
$bootstrapRequired = @(
    'VerifyOnly',
    'Test-AsciiPath',
    'Get-FileHash',
    'runtime-assets.json',
    'Get-RuntimeAsset',
    'DownloadTimeoutSeconds',
    'StartupTimeoutSeconds',
    'ExpectedFiles',
    'Invoke-StartupCheck -Executable $ffprobe'
    'Invoke-StartupCheck -Executable $vad'
    'runtime_acl.ps1'
    'Protect-BtrRuntimeAcl -Path $RuntimeRoot'
    'Assert-BtrRuntimeAcl -Path $RuntimeRoot'
)
foreach ($needle in $bootstrapRequired) {
    if (-not $bootstrap.Contains($needle)) {
        throw "missing runtime bootstrap contract: $needle"
    }
}
if ($bootstrap -match 'Write-Output\s+"(?:verified|installed|downloading|expanded)') {
    throw 'bootstrap helper status must not use the success output stream'
}
if (-not $bootstrap.Contains('System.Diagnostics.ProcessStartInfo') -or
    -not $bootstrap.Contains('.WaitForExit(') -or
    -not $bootstrap.Contains('RedirectStandardError')) {
    throw 'native startup checks must isolate expected stderr from PowerShell error handling'
}

$preparePath = Join-Path $repo 'scripts/prepare_transcript.py'
$prepare = Get-Content -LiteralPath $preparePath -Raw -Encoding utf8
foreach ($needle in @('runtime_fingerprint', 'media_fingerprint', '_provenance_fingerprint', 'same_runtime')) {
    if (-not $prepare.Contains($needle)) {
        throw "missing provenance-bound resume contract: $needle"
    }
}

$licensePath = Join-Path $repo 'LICENSE'
if (-not (Test-Path -LiteralPath $licensePath -PathType Leaf) -or
    -not (Get-Content -LiteralPath $licensePath -Raw -Encoding utf8).Contains('MIT License')) {
    throw 'repository MIT LICENSE is required'
}
$noticesPath = Join-Path $repo 'THIRD_PARTY_NOTICES.md'
if (-not (Test-Path -LiteralPath $noticesPath -PathType Leaf)) {
    throw 'THIRD_PARTY_NOTICES.md is required'
}
$notices = Get-Content -LiteralPath $noticesPath -Raw -Encoding utf8
foreach ($needle in @('yt-dlp.exe', 'FFmpeg', 'FunASR', 'SenseVoiceSmall-GGUF', 'fsmn-vad-GGUF', 'not redistributed')) {
    if (-not $notices.Contains($needle)) { throw "missing third-party notice: $needle" }
}
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

$assetManifestPath = Join-Path $repo 'scripts/runtime-assets.json'
if (-not (Test-Path -LiteralPath $assetManifestPath -PathType Leaf)) {
    throw 'scripts/runtime-assets.json is required'
}
$assetManifest = Get-Content -LiteralPath $assetManifestPath -Raw -Encoding utf8 | ConvertFrom-Json
if ($assetManifest.schema_version -ne 2) {
    throw 'runtime asset manifest schema_version must be 2'
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

foreach ($id in @('sensevoice', 'vad')) {
    $asset = @($assetManifest.assets | Where-Object { $_.id -eq $id })[0]
    if ([string]$asset.revision -notmatch '^[0-9a-f]{40}$' -or
        -not ([string]$asset.url).Contains("/resolve/$($asset.revision)/")) {
        throw "Hugging Face asset must use an immutable revision: $id"
    }
}
foreach ($id in @('ffmpeg', 'funasr_avx2')) {
    $asset = @($assetManifest.assets | Where-Object { $_.id -eq $id })[0]
    if (@($asset.expanded_files).Count -ne 2) { throw "expanded file pins are required: $id" }
}

$correctionGuide = Get-Content -LiteralPath (Join-Path $repo 'references/faithful-correction.md') -Raw -Encoding utf8
$outputGuide = Get-Content -LiteralPath (Join-Path $repo 'references/output-contract.md') -Raw -Encoding utf8
$workflow = $skill + "`n" + $correctionGuide + "`n" + $outputGuide
$workflowRequired = @(
    'roughly ten minutes',
    'rolling list',
    'one corrected row',
    'audio inspection is available',
    'never claim acoustic verification',
    'Resume at the first missing correction row',
    'finalize_transcript.py',
    '--status complete',
    '--status incomplete',
    'run the whole workflow without approval pauses',
    'checkpoint_corrections.py',
    'review_corrections.py',
    'correction-audit.json',
    'correction-reviews.json',
    'source_audio_sha256',
    'normalized_wav_sha256',
    'correction_high_risk_reviewed',
    'yt_dlp_sha256',
    'ffprobe_sha256',
    'vad_model_revision'
)
foreach ($needle in $workflowRequired) {
    if (-not $workflow.Contains($needle)) {
        throw "missing faithful workflow contract: $needle"
    }
}
if ($workflow.Contains('Append accepted rows to `corrections.jsonl` atomically')) {
    throw 'workflow must not instruct direct correction checkpoint append'
}
if ($workflow.Contains('--acknowledge-high-risk')) {
    throw 'workflow must not expose the obsolete global high-risk acknowledgement'
}
if ($readme.Contains($resumeOverclaim)) {
    throw 'README must not overstate operation-level resume support'
}

$workflowPath = Join-Path $repo '.github/workflows/test.yml'
$workflowYaml = Get-Content -LiteralPath $workflowPath -Raw -Encoding utf8
foreach ($needle in @(
    'workflow_dispatch',
    'schedule',
    'cron',
    'matrix',
    '["3.11", "3.12", "3.13"]',
    'real-runtime-smoke',
    'actions/checkout@v6',
    'actions/setup-python@v6',
    'actions/cache@v5',
    '-VerifyOnly',
    'verify-runtime-assets.ps1',
    'Runtime asset metadata'
)) {
    if (-not $workflowYaml.Contains($needle)) {
        throw "missing Actions asset contract: $needle"
    }
}
$assetVerifierPath = Join-Path $repo 'tests/verify-runtime-assets.ps1'
if (-not (Test-Path -LiteralPath $assetVerifierPath -PathType Leaf)) {
    throw 'tests/verify-runtime-assets.ps1 is required'
}
$assetVerifier = Get-Content -LiteralPath $assetVerifierPath -Raw -Encoding utf8
if (-not $assetVerifier.Contains('$env:GITHUB_TOKEN') -or
    -not $workflowYaml.Contains('GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}')) {
    throw 'remote GitHub asset checks must use the Actions token when available'
}

Write-Output 'static Skill contract: PASS'
