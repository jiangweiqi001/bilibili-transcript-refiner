[CmdletBinding()]
param(
    [string]$RuntimeRoot,
    [switch]$VerifyOnly,
    [ValidateRange(1, 86400)][int]$DownloadTimeoutSeconds = 1800,
    [ValidateRange(1, 3600)][int]$StartupTimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

. (Join-Path $PSScriptRoot 'runtime_layout.ps1')
if ([string]::IsNullOrWhiteSpace($RuntimeRoot)) {
    $RuntimeRoot = Get-BtrDefaultRuntimeRoot
}

$assetManifestPath = Join-Path $PSScriptRoot 'runtime-assets.json'
$assetManifest = Get-Content -LiteralPath $assetManifestPath -Raw -Encoding utf8 | ConvertFrom-Json
if ($assetManifest.schema_version -ne 2) {
    throw "Unsupported runtime asset manifest: $assetManifestPath"
}

function Get-RuntimeAsset {
    param([Parameter(Mandatory = $true)][string]$Id)
    $matches = @($assetManifest.assets | Where-Object { $_.id -eq $Id })
    if ($matches.Count -ne 1) { throw "Runtime asset must appear once: $Id" }
    return $matches[0]
}

function Test-AsciiPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return -not [regex]::IsMatch($Path, '[^\x00-\x7F]')
}

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
    try {
        Invoke-WebRequest -Uri $Url -OutFile $partial -UseBasicParsing -TimeoutSec $DownloadTimeoutSeconds
    } catch {
        throw "Failed to download $Name. Check internet, proxy, and TLS access. Partial file: $partial. $($_.Exception.Message)"
    }
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
        [Parameter(Mandatory = $true)][object[]]$ExpectedFiles
    )
    Assert-UnderRoot -Root $RuntimeRoot -Path $Destination
    if (Test-Path -LiteralPath $Destination -PathType Container) {
        try {
            foreach ($expected in $ExpectedFiles) {
                $matches = @(Get-ChildItem -LiteralPath $Destination -Filter $expected.leaf -File -Recurse -ErrorAction Stop)
                if ($matches.Count -ne 1) {
                    throw "Expanded $Name must contain exactly one $($expected.leaf)"
                }
                Assert-Hash -Path $matches[0].FullName -Expected $expected.sha256
            }
            Write-Host "verified package: $Name"
            return
        } catch {
            if ($VerifyOnly) { throw }
            Move-InvalidAside -Path $Destination
        }
    } elseif ($VerifyOnly) {
        throw "Package is not expanded: $Destination"
    }
    $partial = "$Destination.partial-$([Guid]::NewGuid().ToString('N'))"
    Assert-UnderRoot -Root $RuntimeRoot -Path $partial
    Expand-Archive -LiteralPath $Archive -DestinationPath $partial
    foreach ($expected in $ExpectedFiles) {
        $matches = @(Get-ChildItem -LiteralPath $partial -Filter $expected.leaf -File -Recurse -ErrorAction Stop)
        if ($matches.Count -ne 1) {
            throw "Expanded $Name archive must contain exactly one $($expected.leaf); preserved at $partial"
        }
        Assert-Hash -Path $matches[0].FullName -Expected $expected.sha256
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
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $Executable
    $startInfo.Arguments = $Arguments -join ' '
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    try {
        if (-not $process.Start()) {
            throw "Runtime startup check could not start $Executable"
        }
        if (-not $process.WaitForExit($StartupTimeoutSeconds * 1000)) {
            $process.Kill()
            throw "Runtime startup check timed out after $StartupTimeoutSeconds seconds for $Executable"
        }
        $standardOutput = $process.StandardOutput.ReadToEnd()
        $standardError = $process.StandardError.ReadToEnd()
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [IO.File]::WriteAllText($stdout, $standardOutput, $utf8)
        [IO.File]::WriteAllText($stderr, $standardError, $utf8)
        if ($process.ExitCode -notin $AllowedExitCodes) {
            throw "Runtime startup check failed for $Executable with exit code $($process.ExitCode): $standardError"
        }
    } finally {
        $process.Dispose()
    }
}

if (-not (Test-BtrAsciiPath -Path $RuntimeRoot)) {
    throw 'SenseVoice runtime paths must contain ASCII characters only. Pass -RuntimeRoot C:\btr-runtime.'
}
$RuntimeRoot = [IO.Path]::GetFullPath($RuntimeRoot)
New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
Assert-RuntimeWritable -Path $RuntimeRoot
if (-not $VerifyOnly) {
    Assert-FreeSpace -Path $RuntimeRoot
}

$downloads = Join-Path $RuntimeRoot 'downloads'
$bin = Join-Path $RuntimeRoot 'bin'
$models = Join-Path $RuntimeRoot 'models'
$packages = Join-Path $RuntimeRoot 'packages'
foreach ($directory in @($downloads, $bin, $models, $packages)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

$ytDlpAsset = Get-RuntimeAsset -Id 'yt_dlp'
$ffmpegAsset = Get-RuntimeAsset -Id 'ffmpeg'
$funasrAsset = Get-RuntimeAsset -Id 'funasr_avx2'
$sensevoiceAsset = Get-RuntimeAsset -Id 'sensevoice'
$vadAsset = Get-RuntimeAsset -Id 'vad'

$ytDlp = Ensure-Asset -Name $ytDlpAsset.name `
    -Url $ytDlpAsset.url -Sha256 $ytDlpAsset.sha256 `
    -Destination (Join-Path $bin $ytDlpAsset.asset_name)
$ffmpegArchive = Ensure-Asset -Name $ffmpegAsset.name `
    -Url $ffmpegAsset.url -Sha256 $ffmpegAsset.sha256 `
    -Destination (Join-Path $downloads $ffmpegAsset.asset_name)
$funasrArchive = Ensure-Asset -Name $funasrAsset.name `
    -Url $funasrAsset.url -Sha256 $funasrAsset.sha256 `
    -Destination (Join-Path $downloads $funasrAsset.asset_name)
$sensevoiceModel = Ensure-Asset -Name $sensevoiceAsset.name `
    -Url $sensevoiceAsset.url -Sha256 $sensevoiceAsset.sha256 `
    -Destination (Join-Path $models $sensevoiceAsset.asset_name)
$vadModel = Ensure-Asset -Name $vadAsset.name `
    -Url $vadAsset.url -Sha256 $vadAsset.sha256 `
    -Destination (Join-Path $models $vadAsset.asset_name)

$ffmpegPackage = Join-Path $packages 'ffmpeg-9.0.1'
$funasrPackage = Join-Path $packages 'funasr-v0.1.8-avx2'
Ensure-ExpandedArchive -Name 'FFmpeg 9.0.1 essentials' -Archive $ffmpegArchive -Destination $ffmpegPackage -ExpectedFiles @($ffmpegAsset.expanded_files)
Ensure-ExpandedArchive -Name 'FunASR llama.cpp runtime v0.1.8 AVX2' -Archive $funasrArchive -Destination $funasrPackage -ExpectedFiles @($funasrAsset.expanded_files)

$ffmpeg = Find-One -Root $ffmpegPackage -Leaf 'ffmpeg.exe'
$ffprobe = Find-One -Root $ffmpegPackage -Leaf 'ffprobe.exe'
$sensevoice = Find-One -Root $funasrPackage -Leaf 'llama-funasr-sensevoice.exe'
$vad = Find-One -Root $funasrPackage -Leaf 'llama-funasr-vad.exe'

Invoke-StartupCheck -Executable $ytDlp -Arguments @('--version') -AllowedExitCodes @(0)
Invoke-StartupCheck -Executable $ffmpeg -Arguments @('-version') -AllowedExitCodes @(0)
Invoke-StartupCheck -Executable $ffprobe -Arguments @('-version') -AllowedExitCodes @(0)
try {
    Invoke-StartupCheck -Executable $sensevoice -Arguments @('--help') -AllowedExitCodes @(1)
    Invoke-StartupCheck -Executable $vad -Arguments @('--help') -AllowedExitCodes @(1)
} catch {
    throw "FunASR AVX2 runtime could not start. This release requires a Windows x64 CPU with AVX2, FMA, F16C, and BMI2; security software may also block the executable. $($_.Exception.Message)"
}

$manifest = [ordered]@{
    schema_version = 2
    runtime_root = $RuntimeRoot
    generated_at = [DateTime]::UtcNow.ToString('o')
    yt_dlp = $ytDlp
    ffmpeg = $ffmpeg
    ffprobe = $ffprobe
    funasr_sensevoice = $sensevoice
    funasr_vad = $vad
    sensevoice_model = $sensevoiceModel
    vad_model = $vadModel
    provenance = [ordered]@{
        yt_dlp = [ordered]@{ version = $ytDlpAsset.version; sha256 = $ytDlpAsset.sha256; source_url = $ytDlpAsset.url }
        ffmpeg = [ordered]@{ version = $ffmpegAsset.version; sha256 = (Get-Sha256 -Path $ffmpeg); source_url = $ffmpegAsset.url }
        ffprobe = [ordered]@{ version = $ffmpegAsset.version; sha256 = (Get-Sha256 -Path $ffprobe); source_url = $ffmpegAsset.url }
        funasr_sensevoice = [ordered]@{ version = $funasrAsset.version; sha256 = (Get-Sha256 -Path $sensevoice); source_url = $funasrAsset.url }
        funasr_vad = [ordered]@{ version = $funasrAsset.version; sha256 = (Get-Sha256 -Path $vad); source_url = $funasrAsset.url }
        sensevoice_model = [ordered]@{ version = $sensevoiceAsset.version; revision = $sensevoiceAsset.revision; sha256 = $sensevoiceAsset.sha256; source_url = $sensevoiceAsset.url }
        vad_model = [ordered]@{ version = $vadAsset.version; revision = $vadAsset.revision; sha256 = $vadAsset.sha256; source_url = $vadAsset.url }
    }
}
$manifestPath = Join-Path $RuntimeRoot 'runtime.json'
$manifestPartial = "$manifestPath.partial-$([Guid]::NewGuid().ToString('N'))"
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPartial -Encoding utf8
Move-Item -LiteralPath $manifestPartial -Destination $manifestPath -Force
Write-Output "runtime ready: $manifestPath"
