function Get-BtrRuntimeAclSids {
    return @(
        [Security.Principal.WindowsIdentity]::GetCurrent().User,
        (New-Object Security.Principal.SecurityIdentifier('S-1-5-18')),
        (New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544'))
    )
}

function New-BtrRuntimeDirectorySecurity {
    $security = New-Object Security.AccessControl.DirectorySecurity
    $security.SetAccessRuleProtection($true, $false)
    foreach ($sid in Get-BtrRuntimeAclSids) {
        $rule = New-Object Security.AccessControl.FileSystemAccessRule(
            $sid,
            [Security.AccessControl.FileSystemRights]::FullControl,
            ([Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
                [Security.AccessControl.InheritanceFlags]::ObjectInherit),
            [Security.AccessControl.PropagationFlags]::None,
            [Security.AccessControl.AccessControlType]::Allow
        )
        [void]$security.AddAccessRule($rule)
    }
    return $security
}

function New-BtrRuntimeFileSecurity {
    $security = New-Object Security.AccessControl.FileSecurity
    $security.SetAccessRuleProtection($true, $false)
    foreach ($sid in Get-BtrRuntimeAclSids) {
        $rule = New-Object Security.AccessControl.FileSystemAccessRule(
            $sid,
            [Security.AccessControl.FileSystemRights]::FullControl,
            [Security.AccessControl.AccessControlType]::Allow
        )
        [void]$security.AddAccessRule($rule)
    }
    return $security
}

function Protect-BtrRuntimeAcl {
    param([Parameter(Mandatory = $true)][string]$Path)
    $resolved = [IO.Path]::GetFullPath($Path)
    if (-not (Test-Path -LiteralPath $resolved -PathType Container)) {
        throw "Runtime root does not exist for ACL protection: $resolved"
    }
    try {
        Set-Acl -LiteralPath $resolved -AclObject (New-BtrRuntimeDirectorySecurity)
        foreach ($item in Get-ChildItem -LiteralPath $resolved -Force -Recurse) {
            if ($item.PSIsContainer) {
                Set-Acl -LiteralPath $item.FullName -AclObject (New-BtrRuntimeDirectorySecurity)
            } else {
                Set-Acl -LiteralPath $item.FullName -AclObject (New-BtrRuntimeFileSecurity)
            }
        }
    } catch {
        throw "Cannot isolate runtime ACL for $resolved. Choose a private NTFS -RuntimeRoot. $($_.Exception.Message)"
    }
}

function Assert-BtrRuntimeAcl {
    param([Parameter(Mandatory = $true)][string]$Path)
    $resolved = [IO.Path]::GetFullPath($Path)
    $acl = Get-Acl -LiteralPath $resolved
    if (-not $acl.AreAccessRulesProtected) {
        throw "Runtime root ACL still inherits broad access: $resolved"
    }
    $allowed = @(Get-BtrRuntimeAclSids | ForEach-Object { $_.Value })
    $rules = @($acl.GetAccessRules(
        $true,
        $false,
        [Security.Principal.SecurityIdentifier]
    ))
    if ($rules.Count -ne $allowed.Count) {
        throw "Runtime root ACL contains an unexpected rule count: $resolved"
    }
    foreach ($rule in $rules) {
        $sid = $rule.IdentityReference.Value
        $hasFullControl = (
            $rule.FileSystemRights -band [Security.AccessControl.FileSystemRights]::FullControl
        ) -eq [Security.AccessControl.FileSystemRights]::FullControl
        if (
            $sid -notin $allowed -or
            $rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
            -not $hasFullControl
        ) {
            throw "Runtime root ACL contains unexpected access for ${sid}: $resolved"
        }
    }
}
