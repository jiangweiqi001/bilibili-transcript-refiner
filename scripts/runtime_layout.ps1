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
