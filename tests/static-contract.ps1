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

foreach ($ref in @('references/faithful-correction.md', 'references/faithful-translation-zh.md', 'references/output-contract.md')) {
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
$requiredFirstLine = [string][char]0x70B9 + [char]0x70B9 + [char]0x5173 + [char]0x6CE8 + [char]0x8C22 + [char]0x8C22 + [char]0x55B5 + '~'
$favoritesWord = [string][char]0x6536 + [char]0x85CF + [char]0x5939
$classRepWord = [string][char]0x8BFE + [char]0x4EE3 + [char]0x8868
$uploaderWord = 'UP ' + [char]0x4E3B
$tripleActionWord = [string][char]0x4E00 + [char]0x952E + [char]0x4E09 + [char]0x8FDE
$progressBarWord = [string][char]0x8FDB + [char]0x5EA6 + [char]0x6761
$noSummaryWord = [string][char]0x4E0D + [char]0x505A + [char]0x7701 + [char]0x6D41 + [char]0x7248
$onePageClaim = [string][char]0x6BCF + [char]0x6B21 + [char]0x8C03 + [char]0x7528 + [char]0x53EA + [char]0x5904 + [char]0x7406 + [char]0x4E00 + [char]0x4E2A + [char]0x89C6 + [char]0x9891 + [char]0x9875 + [char]0x9762
$pythonTestClaimSuffix = [string][char]0x9879 + ' Python ' + [char]0x81EA + [char]0x52A8 + [char]0x5316 + [char]0x6D4B + [char]0x8BD5
$readmeFirstLine = @($readme -split "`r?`n", 2)[0]
if ($readmeFirstLine -cne $requiredFirstLine) {
    throw 'README first line must be exact'
}

$discoverTests = "import pathlib, sys, unittest; root = pathlib.Path(sys.argv[1]).resolve(); sys.path.insert(0, str(root)); print(unittest.defaultTestLoader.discover(start_dir=str(root / 'tests'), pattern='test_*.py', top_level_dir=str(root)).countTestCases())"
$discoveredTestCountOutput = @(& python -X utf8 -c $discoverTests $repo)
if ($LASTEXITCODE -ne 0 -or
    $discoveredTestCountOutput.Count -ne 1 -or
    [string]$discoveredTestCountOutput[0] -notmatch '^\d+$') {
    throw 'could not discover the Python unittest count'
}
$discoveredPythonTestCount = [int]$discoveredTestCountOutput[0]
$pythonTestClaimMatches = [regex]::Matches(
    $readme,
    '(?m)(?<count>\d+) ' + [regex]::Escape($pythonTestClaimSuffix)
)
if ($pythonTestClaimMatches.Count -ne 1) {
    throw 'README must contain exactly one Python unittest count claim'
}
if ([int]$pythonTestClaimMatches[0].Groups['count'].Value -ne $discoveredPythonTestCount) {
    throw "README Python unittest count must equal discovery: $discoveredPythonTestCount"
}

$promotionalRequired = @(
    'actions/workflows/test.yml/badge.svg',
    'yt-dlp -> FFmpeg -> FSMN-VAD -> SenseVoiceSmall',
    'b23.tv',
    'bili2233.cn',
    '46',
    '2026-08-16',
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
$translationGuide = Get-Content -LiteralPath (Join-Path $repo 'references/faithful-translation-zh.md') -Raw -Encoding utf8
$outputGuide = Get-Content -LiteralPath (Join-Path $repo 'references/output-contract.md') -Raw -Encoding utf8
$workflow = $skill + "`n" + $correctionGuide + "`n" + $translationGuide + "`n" + $outputGuide
$bilingualWord = [string][char]0x4E2D + [char]0x82F1 + [char]0x53CC + [char]0x8BED
$noLocalTranslationModel = [string][char]0x4E0D + [char]0x65B0 + [char]0x589E + [char]0x672C + [char]0x5730 + [char]0x7FFB + [char]0x8BD1 + [char]0x6A21 + [char]0x578B
$chineseLineLabel = '**' + [char]0x4E2D + [char]0x6587 + [char]0xFF1A + '**'

foreach ($needle in @(
    'references/faithful-translation-zh.md',
    'complete English clause',
    'isolated English',
    'checkpoint_translations.py',
    'translations-zh.jsonl',
    '--bilingual'
)) {
    if (-not $skill.Contains($needle)) {
        throw "missing bilingual Skill contract: $needle"
    }
}
foreach ($needle in @(
    'Translate the stable corrected source row, not the raw ASR.',
    'Preserve every claim, number, name, qualification, repetition, hesitation, and self-correction.',
    'Do not summarize, explain, annotate, fact-correct, or add background knowledge.',
    'Do not silently omit difficult phrases or make uncertain source wording definite.'
)) {
    if (-not $translationGuide.Contains($needle)) {
        throw "missing faithful Chinese translation contract: $needle"
    }
}
foreach ($needle in @(
    '"source_text"',
    '"text_zh"',
    'output_mode: "bilingual-en-zh"',
    'translation_mode: "faithful"',
    'translations_zh_sha256:',
    '**English:**',
    $chineseLineLabel
)) {
    if (-not $outputGuide.Contains($needle)) {
        throw "missing bilingual output contract: $needle"
    }
}
foreach ($needle in @($bilingualWord, $noLocalTranslationModel, 'translations-zh.jsonl')) {
    if (-not $readme.Contains($needle)) {
        throw "missing bilingual README contract: $needle"
    }
}
if (-not $ui.Contains(([string][char]0x4E2D + [char]0x82F1))) {
    throw 'Skill UI metadata must mention Chinese-English output'
}

function Normalize-ContractText {
    param([Parameter(Mandatory = $true)][string]$Text)

    return [regex]::Replace($Text, '\s+', ' ').Trim()
}

function Get-MarkdownContractSegments {
    param([Parameter(Mandatory = $true)][string]$Text)

    $inFence = $false
    foreach ($line in [regex]::Split($Text, '\r?\n')) {
        $candidate = $line.Trim()
        if ($candidate -match '^(?:```|~~~)') {
            $inFence = -not $inFence
            continue
        }
        if ($inFence -or [string]::IsNullOrWhiteSpace($candidate) -or $candidate -match '^#{1,6}\s') {
            continue
        }
        if ($candidate -match '^(?:\d+\.|[-*+])\s+(?<body>.+)$') {
            $candidate = $Matches['body']
        } elseif ($candidate -match '^>\s?(?<body>.+)$') {
            $candidate = $Matches['body']
        }
        $normalized = Normalize-ContractText -Text $candidate
        if (-not [string]::IsNullOrWhiteSpace($normalized)) {
            Write-Output $normalized
        }
    }
}

function Get-ContractSentenceCount {
    param(
        [Parameter(Mandatory = $true)][string]$Text,
        [Parameter(Mandatory = $true)][string]$Sentence
    )

    $normalizedSentence = Normalize-ContractText -Text $Sentence
    return @(
        Get-MarkdownContractSegments -Text $Text |
            Where-Object { $_ -ceq $normalizedSentence }
    ).Count
}

function Assert-UniqueContractSentence {
    param(
        [Parameter(Mandatory = $true)][string]$Text,
        [Parameter(Mandatory = $true)][string]$Sentence,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $count = Get-ContractSentenceCount -Text $Text -Sentence $Sentence
    if ($count -ne 1) {
        throw "contract sentence must appear exactly once for ${Label}; found: $count"
    }
}

function Get-ContractSection {
    param(
        [Parameter(Mandatory = $true)][string]$Text,
        [Parameter(Mandatory = $true)][string]$Heading,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $pattern = '(?ms)^' + [regex]::Escape($Heading) + '[ \t]*\r?\n(?<body>.*?)(?=^##[ \t]+[^\r\n]+\r?$|\z)'
    $matches = [regex]::Matches($Text, $pattern)
    if ($matches.Count -ne 1) {
        throw "contract section must appear exactly once for ${Label}; found: $($matches.Count)"
    }
    return $matches[0].Groups['body'].Value
}

function Get-WorkflowStep {
    param(
        [Parameter(Mandatory = $true)][string]$Workflow,
        [Parameter(Mandatory = $true)][int]$Number
    )

    $pattern = '(?ms)^' + $Number + '\.[ \t]+(?<body>.*?)(?=^\d+\.[ \t]+|\z)'
    $matches = [regex]::Matches($Workflow, $pattern)
    if ($matches.Count -ne 1) {
        throw "Skill workflow step must appear exactly once for ${Number}; found: $($matches.Count)"
    }
    return $matches[0].Groups['body'].Value
}

$duplicateSectionRejected = $false
try {
    [void](Get-ContractSection -Text "## Heading`nfirst`n`n## Heading   `nsecond`n" -Heading '## Heading' -Label 'horizontal-whitespace duplicate heading self-test')
} catch {
    $duplicateSectionRejected = $true
}
if (-not $duplicateSectionRejected) {
    throw 'Get-ContractSection must reject duplicate headings that differ only by trailing horizontal whitespace'
}

$duplicateStepRejected = $false
try {
    [void](Get-WorkflowStep -Workflow "8. x`n8.   y`n9. z`n" -Number 8)
} catch {
    $duplicateStepRejected = $true
}
if (-not $duplicateStepRejected) {
    throw 'Get-WorkflowStep must reject duplicate step markers that use different horizontal whitespace widths'
}

$trailingWhitespaceSection = Get-ContractSection -Text "## Heading`t `nbody`n`n## Next`nnext`n" -Heading '## Heading' -Label 'trailing horizontal-whitespace heading self-test'
if ((Normalize-ContractText -Text $trailingWhitespaceSection) -cne 'body') {
    throw 'Get-ContractSection must accept trailing horizontal whitespace on a heading'
}

$tabbedStep = Get-WorkflowStep -Workflow "8.`talpha`n9.`tbeta`n" -Number 8
if ((Normalize-ContractText -Text $tabbedStep) -cne 'alpha') {
    throw 'Get-WorkflowStep must accept horizontal whitespace after a step marker and stop at the next equivalent marker'
}

$stepWithNestedNumber = Get-WorkflowStep -Workflow "8. outer`n   9. nested`n9. next`n" -Number 8
if ((Normalize-ContractText -Text $stepWithNestedNumber) -cne 'outer 9. nested') {
    throw 'Get-WorkflowStep must not treat an indented numbered item as a top-level step marker'
}

$skillWorkflow = Get-ContractSection -Text $skill -Heading '## Workflow' -Label 'Skill workflow'
$skillCommonMistakes = Get-ContractSection -Text $skill -Heading '## Common mistakes' -Label 'Skill common mistakes'
$faithfulUncertainty = Get-ContractSection -Text $correctionGuide -Heading '## Uncertainty' -Label 'faithful uncertainty policy'
$formalDirectoryContract = Get-ContractSection -Text $outputGuide -Heading '## Formal directory' -Label 'formal directory contract'
$rawEvidenceContract = Get-ContractSection -Text $outputGuide -Heading '## Raw evidence' -Label 'raw evidence contract'
$reviewTimingContract = Get-ContractSection -Text $outputGuide -Heading '## Review timing' -Label 'review timing contract'
$statusContract = Get-ContractSection -Text $outputGuide -Heading '## Status semantics' -Label 'status semantics contract'
$skillStep7 = Get-WorkflowStep -Workflow $skillWorkflow -Number 7
$skillStep8 = Get-WorkflowStep -Workflow $skillWorkflow -Number 8
$skillStep9 = Get-WorkflowStep -Workflow $skillWorkflow -Number 9

$suspectEllipsisMarker = $suspectMarker + [char]0x2026 + ']'
$suspectXMarker = $suspectMarker + 'X]'
$emDash = [char]0x2014

$step7AuditSentence = 'After every block, refresh and read `<JOB_DIR>\correction-audit.json`; use it to revise unjustified findings, but do not list or record reviews during batching.'
$step7CompleteSentence = 'Continue checkpointing until the returned JSON reports `"complete": true`, finish every necessary replacement, and confirm the checkpoint remains complete.'
$reviewStableSentence = 'Begin the final review only after the helper reports `"complete": true`, every replacement is finished, and `corrections.jsonl` is stable.'
$reviewContentAddressedSentence = 'Reviews are content-addressed, not operation-count based: only changed correction content that gives the current checkpoint a different corrections SHA-256 makes reviews for the old checkpoint inapplicable; a byte-identical replacement keeps the same content hash.'
$reviewCurrentCheckpointSentence = 'Before finalization, if the current complete, stable checkpoint has a corrections SHA-256 different from the reviewed checkpoint, repeat the final review pass against the current checkpoint.'
$pairingSentence = 'Both `complete` and `incomplete` require every raw row to have one timestamp-matched correction; `incomplete` is not a prefix.'
$skillLocalMarkerSentence = 'Local uncertainty markers (`' + $suspectEllipsisMarker + '` or `' + $inaudibleMarker + '`) may remain in `complete` after every other gate passes.'
$skillWholeRowSentence = 'A strict whole-row substitution consisting of a single `' + $inaudibleMarker + '` must use `incomplete` and may proceed without fabricating an audio review for that informational finding.'
$skillOtherHighSentence = 'Every other current high-risk finding in an incomplete job still requires a current confirmed review.'
$outputBatchingSentence = 'During batching, refresh and read `correction-audit.json` after every checkpoint; use its findings to revise unjustified corrections, but do not list or record reviews yet.'
$statusPairingSentence = 'Both `complete` and `incomplete` require one timestamp-matched correction row for every raw row; `incomplete` is not a correction prefix.'
$statusLocalMarkerSentence = 'A local `' + $suspectEllipsisMarker + '` or `' + $inaudibleMarker + '` marker inside otherwise meaningful text may still be `complete` after every other gate passes.'
$statusEligibilitySentence = 'The strict whole-row exemption applies only when the correction text contains exactly one `' + $inaudibleMarker + '`, its `uncertainties` array contains exactly one entry with that matching marker and a nonempty note, and every character surrounding the marker has a Unicode category beginning with `Z` or `P`.'
$statusNoExemptionSentence = 'Letters, numbers, Han characters, emoji, mathematical or currency symbols, control or zero-width characters, `' + $suspectEllipsisMarker + '`, duplicate `' + $inaudibleMarker + '` markers, extra semantic content, and partial rows that mix ordinary text with `' + $inaudibleMarker + '` receive no exemption; partial rows retain ordinary protected-token and semantic-loss auditing.'
$statusStrictReviewSentence = 'A qualifying strict whole-row substitution must use `incomplete` and does not require an audio review for its informational finding; every other high-risk finding in that incomplete job still requires a current confirmed audio review.'
$persistentStateSentence = 'Persistent intermediate state, including metadata, audio, clips, corrections, logs, and archives, belongs under the runtime root, normally inside its job directory.'
$atomicPartialSentence = 'Atomic writers may briefly create owned `.partial-*` files beside their target, including in the formal directory.'
$quarantineSentence = 'Only the corrected-transcript finalizer''s own stale formal partial is quarantined on retry; do not generalize that behavior to other partial files.'
$twoFilesSentence = 'After successful finalization, the formal directory still contains exactly the two files above.'
$rawNormalizationSentence = 'During preparation, remove SenseVoice control tags such as `<|zh|>` and trim surrounding whitespace; preserve all remaining recognized text unchanged.'
$faithfulLocalSentence = 'A local `' + $suspectXMarker + '` or `' + $inaudibleMarker + '` marker inside otherwise meaningful text may remain in a `complete` transcript after every other gate passes.'
$faithfulWholeRowSentence = 'A whole-row substitution consisting of a single `' + $inaudibleMarker + '`, with only ordinary Unicode whitespace or punctuation around it, is an abstention: it forces `incomplete` and does not need' + $emDash + 'and must not invent' + $emDash + 'an audio review for that informational finding.'
$commonReviewReuseSentence = 'Do not reuse reviews when the current corrections SHA-256 differs from the reviewed checkpoint; review only a complete, stable checkpoint.'

foreach ($contract in @(
    @{ Text = $skillStep7; Sentence = $step7AuditSentence; Label = 'Skill step 7 audit-only batching' },
    @{ Text = $skillStep7; Sentence = $step7CompleteSentence; Label = 'Skill step 7 complete replacement loop' },
    @{ Text = $skillStep8; Sentence = $reviewStableSentence; Label = 'Skill step 8 stable final review timing' },
    @{ Text = $skillStep8; Sentence = $reviewContentAddressedSentence; Label = 'Skill step 8 content-addressed reviews' },
    @{ Text = $skillStep8; Sentence = $reviewCurrentCheckpointSentence; Label = 'Skill step 8 current-checkpoint final review' },
    @{ Text = $skillStep9; Sentence = $pairingSentence; Label = 'Skill step 9 full pairing' },
    @{ Text = $skillStep9; Sentence = $skillLocalMarkerSentence; Label = 'Skill step 9 local uncertainty' },
    @{ Text = $skillStep9; Sentence = $skillWholeRowSentence; Label = 'Skill step 9 strict whole-row status' },
    @{ Text = $skillStep9; Sentence = $skillOtherHighSentence; Label = 'Skill step 9 other high-risk review' },
    @{ Text = $reviewTimingContract; Sentence = $outputBatchingSentence; Label = 'output batching review timing' },
    @{ Text = $reviewTimingContract; Sentence = $reviewStableSentence; Label = 'output stable final review timing' },
    @{ Text = $reviewTimingContract; Sentence = $reviewContentAddressedSentence; Label = 'output content-addressed reviews' },
    @{ Text = $reviewTimingContract; Sentence = $reviewCurrentCheckpointSentence; Label = 'output current-checkpoint final review' },
    @{ Text = $statusContract; Sentence = $statusPairingSentence; Label = 'output status full pairing' },
    @{ Text = $statusContract; Sentence = $statusLocalMarkerSentence; Label = 'output status local uncertainty' },
    @{ Text = $statusContract; Sentence = $statusEligibilitySentence; Label = 'output strict whole-row eligibility' },
    @{ Text = $statusContract; Sentence = $statusNoExemptionSentence; Label = 'output strict whole-row exclusions' },
    @{ Text = $statusContract; Sentence = $statusStrictReviewSentence; Label = 'output strict whole-row review boundary' },
    @{ Text = $formalDirectoryContract; Sentence = $persistentStateSentence; Label = 'output persistent runtime state' },
    @{ Text = $formalDirectoryContract; Sentence = $atomicPartialSentence; Label = 'output owned atomic partials' },
    @{ Text = $formalDirectoryContract; Sentence = $quarantineSentence; Label = 'output scoped quarantine' },
    @{ Text = $formalDirectoryContract; Sentence = $twoFilesSentence; Label = 'output successful two-file directory' },
    @{ Text = $rawEvidenceContract; Sentence = $rawNormalizationSentence; Label = 'output raw normalization' },
    @{ Text = $faithfulUncertainty; Sentence = $faithfulLocalSentence; Label = 'faithful local uncertainty boundary' },
    @{ Text = $faithfulUncertainty; Sentence = $faithfulWholeRowSentence; Label = 'faithful whole-row abstention boundary' },
    @{ Text = $skillCommonMistakes; Sentence = $commonReviewReuseSentence; Label = 'Skill common-mistake review reuse warning' }
)) {
    Assert-UniqueContractSentence -Text $contract.Text -Sentence $contract.Sentence -Label $contract.Label
}

foreach ($obsoleteReviewWarning in @(
    'after any later correction change',
    'after every later correction change'
)) {
    if ($skill.Contains($obsoleteReviewWarning)) {
        throw "Skill must not use operation-count review invalidation wording: $obsoleteReviewWarning"
    }
}

if ($rawEvidenceContract -match 'byte-for-byte') {
    throw 'raw evidence contract must not claim byte-for-byte preservation before normalization'
}

foreach ($forbidden in @(
    'checkpoint_corrections.py',
    'review_corrections.py',
    'python -X utf8',
    '--url',
    '--output-root',
    '--runtime-root',
    '--rerun-asr',
    '--raw',
    '--checkpoint',
    '--batch',
    '--replace-from',
    '--expected-corrections-sha256',
    '--job-dir',
    '--finding-id',
    '--decision',
    '--note',
    '--status',
    '--incomplete-reason'
)) {
    if ($correctionGuide.Contains($forbidden)) {
        throw "faithful policy must stay semantic and omit helper command details: $forbidden"
    }
}
foreach ($duplicate in @(
    'Do not overwrite raw evidence to make it resemble the correction.',
    'Do not add a summary, outline, teaching note, or content analysis.',
    'Do not guess a technical term merely because it makes the sentence smoother.'
)) {
    if ($skillCommonMistakes.Contains($duplicate)) {
        throw "Skill common mistakes must not repeat fidelity policy: $duplicate"
    }
}

$readmeRiskFeatureSentence = '"**\u6821\u8ba2\u98ce\u9669\u5ba1\u8ba1**\uff1a\u81ea\u52a8\u6807\u8bb0\u6570\u5b57\u3001\u5b8c\u6574\u65e5\u671f\u3001\u91d1\u989d\u3001\u62c9\u4e01\u6807\u8bc6\u7b26\u7684\u589e\u5220\u4e0e\u6362\u5e8f\uff0c\u4ee5\u53ca\u5927\u6bb5\u5220\u9664\u548c\u91cd\u5199\uff1b\u7b49\u5168\u90e8\u6821\u8ba2 checkpoint \u7a33\u5b9a\u540e\uff0c\u518d\u7edf\u4e00\u9010\u6761\u590d\u542c\u5f53\u524d\u9ad8\u98ce\u9669\u53d1\u73b0\u5e76\u8bb0\u5f55\u3002"' | ConvertFrom-Json
$readmeHighRiskClipSentence = '"\u6bcf\u6761\u9700\u590d\u6838\u7684\u9ad8\u98ce\u9669\u53d1\u73b0\u90fd\u5e26\u6709\u5bf9\u5e94\u97f3\u9891\u7247\u6bb5\uff1b\u6700\u7ec8\u590d\u542c\u8bb0\u5f55\u7ed1\u5b9a\u539f\u7a3f\u3001\u6821\u8ba2\u7a3f\u548c\u97f3\u9891 SHA-256\u3002"' | ConvertFrom-Json
$readmeIncompleteSentence = '"\u5176\u4ed6\u4efb\u4f55\u65e0\u6cd5\u58f0\u660e\u6574\u6bb5\u5f55\u97f3\u5df2\u53ef\u9760\u6821\u8ba2\u5b8c\u6210\u7684\u60c5\u51b5\u4e5f\u4f7f\u7528 `incomplete`\u3002"' | ConvertFrom-Json
Assert-UniqueContractSentence -Text $readme -Sentence $readmeRiskFeatureSentence -Label 'README stable high-risk review timing'
Assert-UniqueContractSentence -Text $readme -Sentence $readmeHighRiskClipSentence -Label 'README high-risk clip scope'
Assert-UniqueContractSentence -Text $readme -Sentence $readmeIncompleteSentence -Label 'README nonexclusive incomplete status'

$designPath = Join-Path $repo 'docs/superpowers/specs/2026-08-14-contract-cleanup-v1-1-2-design.md'
$designQuarantineSentence = 'Only the corrected-transcript finalizer''s own stale formal partial is quarantined on retry, and successful delivery still contains exactly two files.'
$designReviewSentence = 'Review validity is content-addressed, not operation-count based: only changed correction content that gives the current complete checkpoint a different corrections SHA-256 makes old reviews inapplicable and requires the final review pass again; a byte-identical replacement keeps the same content hash.'
$design = Get-Content -LiteralPath $designPath -Raw -Encoding utf8
Assert-UniqueContractSentence -Text $design -Sentence $designQuarantineSentence -Label 'design scoped formal partial quarantine'
Assert-UniqueContractSentence -Text $design -Sentence $designReviewSentence -Label 'design content-addressed review validity'
if ($design.Contains('interruption remnants are quarantined on retry')) {
    throw 'design must not generalize quarantine to every interruption remnant'
}

$oppositeReviewSentence = 'Reviews are never content-addressed and do not remain valid after a byte-identical replacement.'
$mutatedStep8 = $skillStep8.Replace($reviewContentAddressedSentence, $oppositeReviewSentence)
if ($mutatedStep8 -ceq $skillStep8) {
    throw 'negative exact-sentence self-test could not create its in-memory mutation'
}
$oppositeWasRejected = $false
try {
    Assert-UniqueContractSentence -Text $mutatedStep8 -Sentence $reviewContentAddressedSentence -Label 'negative content-addressed review self-test'
} catch {
    $oppositeWasRejected = $true
}
if (-not $oppositeWasRejected) {
    throw 'exact contract assertion accepted a contradictory never/do not sentence'
}

$prefixedReviewSentence = 'Do not ' + $reviewContentAddressedSentence
if ((Get-ContractSentenceCount -Text $prefixedReviewSentence -Sentence $reviewContentAddressedSentence) -ne 0) {
    throw 'exact contract assertion accepted a Do not prefix around the canonical sentence'
}
$suffixedReviewSentence = $reviewContentAddressedSentence + ' This is false.'
if ((Get-ContractSentenceCount -Text $suffixedReviewSentence -Sentence $reviewContentAddressedSentence) -ne 0) {
    throw 'exact contract assertion accepted a contradictory suffix after the canonical sentence'
}

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
    'test-runtime-acl.ps1',
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
