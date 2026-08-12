[CmdletBinding()]
param(
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'bilibili-transcript-refiner\runtime-v1'),
    [switch]$VerifyOnly
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Test-AsciiPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return -not [regex]::IsMatch($Path, '[^\x00-\x7F]')
}

function Assert-UnderRoot {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Path
    )
    $resolvedRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    $resolvedPath = [IO.Path]::GetFullPath($Path)
    if (-not $resolvedPath.StartsWith($resolvedRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to write outside RuntimeRoot: $resolvedPath"
    }
}

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Assert-Hash {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Expected
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing runtime asset: $Path"
    }
    $actual = Get-Sha256 -Path $Path
    if ($actual -ne $Expected) {
        throw "SHA-256 mismatch for $Path. Expected $Expected, got $actual"
    }
}

function Move-InvalidAside {
    param([Parameter(Mandatory = $true)][string]$Path)
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
    $archive = Join-Path $RuntimeRoot 'archive'
    New-Item -ItemType Directory -Path $archive -Force | Out-Null
    $target = Join-Path $archive ((Split-Path -Leaf $Path) + ".invalid-$stamp")
    Assert-UnderRoot -Root $RuntimeRoot -Path $target
    Move-Item -LiteralPath $Path -Destination $target
}

function Ensure-Asset {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Sha256,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    Assert-UnderRoot -Root $RuntimeRoot -Path $Destination
    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        try {
            Assert-Hash -Path $Destination -Expected $Sha256
            Write-Host "verified: $Name"
            return $Destination
        } catch {
            if ($VerifyOnly) { throw }
            Move-InvalidAside -Path $Destination
        }
    } elseif ($VerifyOnly) {
        throw "Missing runtime asset in VerifyOnly mode: $Destination"
    }

    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    $partial = "$Destination.partial-$([Guid]::NewGuid().ToString('N'))"
    Assert-UnderRoot -Root $RuntimeRoot -Path $partial
    Write-Host "downloading: $Name"
    Invoke-WebRequest -Uri $Url -OutFile $partial -UseBasicParsing
    Assert-Hash -Path $partial -Expected $Sha256
    Move-Item -LiteralPath $partial -Destination $Destination
    Write-Host "installed: $Name"
    return $Destination
}

function Ensure-ExpandedArchive {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Archive,
        [Parameter(Mandatory = $true)][string]$Destination,
        [Parameter(Mandatory = $true)][string]$RequiredLeaf
    )
    Assert-UnderRoot -Root $RuntimeRoot -Path $Destination
    $existing = Get-ChildItem -LiteralPath $Destination -Filter $RequiredLeaf -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $existing) {
        Write-Host "verified package: $Name"
        return
    }
    if ($VerifyOnly) {
        throw "Package is not expanded or lacks ${RequiredLeaf}: $Destination"
    }
    if (Test-Path -LiteralPath $Destination) {
        Move-InvalidAside -Path $Destination
    }
    $partial = "$Destination.partial-$([Guid]::NewGuid().ToString('N'))"
    Assert-UnderRoot -Root $RuntimeRoot -Path $partial
    Expand-Archive -LiteralPath $Archive -DestinationPath $partial
    $required = Get-ChildItem -LiteralPath $partial -Filter $RequiredLeaf -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $required) {
        throw "Expanded $Name archive does not contain $RequiredLeaf; preserved at $partial"
    }
    Move-Item -LiteralPath $partial -Destination $Destination
    Write-Host "expanded: $Name"
}

function Find-One {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Leaf
    )
    $match = Get-ChildItem -LiteralPath $Root -Filter $Leaf -File -Recurse | Select-Object -First 1
    if ($null -eq $match) { throw "Cannot find $Leaf under $Root" }
    return $match.FullName
}

function Invoke-StartupCheck {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][int[]]$AllowedExitCodes
    )
    $checkDirectory = Join-Path $RuntimeRoot 'startup-checks'
    New-Item -ItemType Directory -Path $checkDirectory -Force | Out-Null
    $stem = [IO.Path]::GetFileNameWithoutExtension($Executable)
    $stdout = Join-Path $checkDirectory "$stem.stdout.txt"
    $stderr = Join-Path $checkDirectory "$stem.stderr.txt"
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments `
        -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    if ($process.ExitCode -notin $AllowedExitCodes) {
        $detail = Get-Content -LiteralPath $stderr -Raw -ErrorAction SilentlyContinue
        throw "Runtime startup check failed for $Executable with exit code $($process.ExitCode): $detail"
    }
}

if (-not (Test-AsciiPath -Path $RuntimeRoot)) {
    throw 'SenseVoice runtime paths must contain ASCII characters only. Pass -RuntimeRoot C:\btr-runtime.'
}
$RuntimeRoot = [IO.Path]::GetFullPath($RuntimeRoot)
New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null

$downloads = Join-Path $RuntimeRoot 'downloads'
$bin = Join-Path $RuntimeRoot 'bin'
$models = Join-Path $RuntimeRoot 'models'
$packages = Join-Path $RuntimeRoot 'packages'
foreach ($directory in @($downloads, $bin, $models, $packages)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

$ytDlp = Ensure-Asset -Name 'yt-dlp 2026.07.04' `
    -Url 'https://github.com/yt-dlp/yt-dlp/releases/download/2026.07.04/yt-dlp.exe' `
    -Sha256 '52FE3C26DCF71FBDC85B528589020BB0B8E383155CFA81B64DD447BBE35E24B8' `
    -Destination (Join-Path $bin 'yt-dlp.exe')
$ffmpegArchive = Ensure-Asset -Name 'FFmpeg 9.0.1 essentials' `
    -Url 'https://github.com/GyanD/codexffmpeg/releases/download/9.0.1/ffmpeg-9.0.1-essentials_build.zip' `
    -Sha256 'FEC81AE03971D9DD4BE3EBE02E263BD2EC1D789483F931BDBA5F5715E65DA2E9' `
    -Destination (Join-Path $downloads 'ffmpeg-9.0.1-essentials_build.zip')
$funasrArchive = Ensure-Asset -Name 'FunASR llama.cpp runtime v0.1.8 AVX2' `
    -Url 'https://github.com/modelscope/FunASR/releases/download/runtime-llamacpp-v0.1.8/funasr-llamacpp-windows-x64-avx2.zip' `
    -Sha256 'F2A1389658E6FB5F5F93C7BAD98B5CE100EB4811E0E3C39603E39466773B1B4C' `
    -Destination (Join-Path $downloads 'funasr-llamacpp-windows-x64-avx2.zip')
$sensevoiceModel = Ensure-Asset -Name 'SenseVoiceSmall q8' `
    -Url 'https://huggingface.co/FunAudioLLM/SenseVoiceSmall-GGUF/resolve/main/sensevoice-small-q8.gguf' `
    -Sha256 '4AE45C94422DE949B387E2E0FB10D7E14E4C42C69DB30C3444ECC7D4B844B7C5' `
    -Destination (Join-Path $models 'sensevoice-small-q8.gguf')
$vadModel = Ensure-Asset -Name 'FSMN-VAD' `
    -Url 'https://huggingface.co/FunAudioLLM/fsmn-vad-GGUF/resolve/main/fsmn-vad.gguf' `
    -Sha256 '1270F2559C495F4E7B6E739541151027D360761A3FDA43FC147034F5719F5479' `
    -Destination (Join-Path $models 'fsmn-vad.gguf')

$ffmpegPackage = Join-Path $packages 'ffmpeg-9.0.1'
$funasrPackage = Join-Path $packages 'funasr-v0.1.8-avx2'
Ensure-ExpandedArchive -Name 'FFmpeg 9.0.1 essentials' -Archive $ffmpegArchive -Destination $ffmpegPackage -RequiredLeaf 'ffmpeg.exe'
Ensure-ExpandedArchive -Name 'FunASR llama.cpp runtime v0.1.8 AVX2' -Archive $funasrArchive -Destination $funasrPackage -RequiredLeaf 'llama-funasr-sensevoice.exe'

$ffmpeg = Find-One -Root $ffmpegPackage -Leaf 'ffmpeg.exe'
$ffprobe = Find-One -Root $ffmpegPackage -Leaf 'ffprobe.exe'
$sensevoice = Find-One -Root $funasrPackage -Leaf 'llama-funasr-sensevoice.exe'
$vad = Find-One -Root $funasrPackage -Leaf 'llama-funasr-vad.exe'

Invoke-StartupCheck -Executable $ytDlp -Arguments @('--version') -AllowedExitCodes @(0)
Invoke-StartupCheck -Executable $ffmpeg -Arguments @('-version') -AllowedExitCodes @(0)
Invoke-StartupCheck -Executable $sensevoice -Arguments @('--help') -AllowedExitCodes @(1)

$manifest = [ordered]@{
    schema_version = 1
    runtime_root = $RuntimeRoot
    yt_dlp = $ytDlp
    ffmpeg = $ffmpeg
    ffprobe = $ffprobe
    funasr_sensevoice = $sensevoice
    funasr_vad = $vad
    sensevoice_model = $sensevoiceModel
    vad_model = $vadModel
}
$manifestPath = Join-Path $RuntimeRoot 'runtime.json'
$manifestPartial = "$manifestPath.partial-$([Guid]::NewGuid().ToString('N'))"
$manifest | ConvertTo-Json | Set-Content -LiteralPath $manifestPartial -Encoding utf8
Move-Item -LiteralPath $manifestPartial -Destination $manifestPath -Force
Write-Output "runtime ready: $manifestPath"
