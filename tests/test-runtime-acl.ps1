$ErrorActionPreference = 'Stop'

. (Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts/runtime_acl.ps1')

$root = Join-Path ([IO.Path]::GetTempPath()) ('btr-acl-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root | Out-Null
$child = Join-Path $root 'existing-job'
$file = Join-Path $child 'audio.wav'
New-Item -ItemType Directory -Path $child | Out-Null
[IO.File]::WriteAllBytes($file, [byte[]](1, 2, 3))

$failedClosed = $false
try {
    Assert-BtrRuntimeAcl -Path $root
} catch {
    $failedClosed = $true
}
if (-not $failedClosed) {
    throw 'A newly inherited temp directory should not already satisfy the protected runtime ACL'
}

Protect-BtrRuntimeAcl -Path $root
Assert-BtrRuntimeAcl -Path $root

$allowed = @(
    [Security.Principal.WindowsIdentity]::GetCurrent().User.Value,
    'S-1-5-18',
    'S-1-5-32-544'
)
foreach ($path in @($root, $child, $file)) {
    $acl = Get-Acl -LiteralPath $path
    if (-not $acl.AreAccessRulesProtected) {
        throw "Runtime ACL must disable inherited access rules: $path"
    }
    foreach ($rule in $acl.Access) {
        $sid = $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
        if ($sid -notin $allowed) {
            throw "Unexpected runtime ACL identity on ${path}: $sid"
        }
    }
}

Remove-Item -LiteralPath $file
Remove-Item -LiteralPath $child
Remove-Item -LiteralPath $root
Write-Output 'runtime ACL isolation: PASS'
