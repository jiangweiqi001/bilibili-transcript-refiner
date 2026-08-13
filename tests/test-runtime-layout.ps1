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
    if ((Get-BtrDefaultRuntimeRoot) -ne $expected) {
        throw 'Unicode fallback selection failed'
    }
} finally {
    $env:LOCALAPPDATA = $savedLocal
    $env:PUBLIC = $savedPublic
}

Write-Output 'runtime layout parity: PASS'
