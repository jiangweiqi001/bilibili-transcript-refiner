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
    'python -X utf8 scripts/prepare_transcript.py --url "<URL>" --output-root "<DIR>"'
    'python -X utf8 scripts/finalize_transcript.py --job-dir "<JOB_DIR>" --output-root "<DIR>" --status complete'
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
$functionHeading = '## ' + [char]0x529F + [char]0x80FD
$highlightHeading = '## ' + [char]0x4EAE + [char]0x70B9
$usageHeading = '## ' + [char]0x4F7F + [char]0x7528 + [char]0x793A + [char]0x4F8B
foreach ($needle in @(
    $functionHeading,
    $highlightHeading,
    $usageHeading,
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
    'Invoke-StartupCheck -Executable $ffprobe'
    'Invoke-StartupCheck -Executable $vad'
)
foreach ($needle in $bootstrapRequired) {
    if (-not $bootstrap.Contains($needle)) {
        throw "missing runtime bootstrap contract: $needle"
    }
}
if ($bootstrap -match 'Write-Output\s+"(?:verified|installed|downloading|expanded)') {
    throw 'bootstrap helper status must not use the success output stream'
}
if (-not $bootstrap.Contains('Start-Process') -or -not $bootstrap.Contains('RedirectStandardError')) {
    throw 'native startup checks must isolate expected stderr from PowerShell error handling'
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
    'run the whole workflow without approval pauses'
)
foreach ($needle in $workflowRequired) {
    if (-not $workflow.Contains($needle)) {
        throw "missing faithful workflow contract: $needle"
    }
}

Write-Output 'static Skill contract: PASS'
