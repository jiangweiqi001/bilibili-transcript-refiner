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

foreach ($forbidden in @('README.md', 'INSTALLATION_GUIDE.md', 'QUICK_REFERENCE.md', 'CHANGELOG.md')) {
    if (Test-Path -LiteralPath (Join-Path $repo $forbidden)) {
        throw "extraneous Skill file: $forbidden"
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
    '2026.07.04',
    '52FE3C26DCF71FBDC85B528589020BB0B8E383155CFA81B64DD447BBE35E24B8',
    'ffmpeg-9.0.1-essentials_build.zip',
    'FEC81AE03971D9DD4BE3EBE02E263BD2EC1D789483F931BDBA5F5715E65DA2E9',
    'runtime-llamacpp-v0.1.8',
    'F2A1389658E6FB5F5F93C7BAD98B5CE100EB4811E0E3C39603E39466773B1B4C',
    'sensevoice-small-q8.gguf',
    '4AE45C94422DE949B387E2E0FB10D7E14E4C42C69DB30C3444ECC7D4B844B7C5',
    'fsmn-vad.gguf',
    '1270F2559C495F4E7B6E739541151027D360761A3FDA43FC147034F5719F5479'
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

Write-Output 'static Skill contract: PASS'
