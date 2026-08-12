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

Write-Output 'static Skill contract: PASS'
