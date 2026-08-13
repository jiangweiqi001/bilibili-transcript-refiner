$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.Net.Http

$repo = Split-Path -Parent $PSScriptRoot
$manifestPath = Join-Path $repo 'scripts/runtime-assets.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
if ($manifest.schema_version -ne 2) {
    throw 'unsupported runtime asset manifest'
}

function Get-HeaderValue {
    param(
        [Parameter(Mandatory = $true)]$Response,
        [Parameter(Mandatory = $true)][string]$Name
    )
    foreach ($headers in @($Response.Headers, $Response.Content.Headers)) {
        if ($headers.Contains($Name)) {
            return @($headers.GetValues($Name))[0]
        }
    }
    throw "remote response lacks $Name"
}

$githubHeaders = @{
    'User-Agent' = 'bilibili-transcript-refiner-asset-check'
    Accept = 'application/vnd.github+json'
}
if (-not [string]::IsNullOrWhiteSpace($env:GITHUB_TOKEN)) {
    $githubHeaders.Authorization = "Bearer $env:GITHUB_TOKEN"
}
$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.AllowAutoRedirect = $false
$client = [System.Net.Http.HttpClient]::new($handler)
$client.DefaultRequestHeaders.UserAgent.ParseAdd('bilibili-transcript-refiner-asset-check')
try {
    foreach ($asset in $manifest.assets) {
        if ($asset.provider -eq 'github') {
            $releaseUrl = "https://api.github.com/repos/$($asset.repository)/releases/tags/$($asset.tag)"
            $release = Invoke-RestMethod -Uri $releaseUrl -Headers $githubHeaders
            $remote = @($release.assets | Where-Object { $_.name -eq $asset.asset_name })
            if ($remote.Count -ne 1) {
                throw "remote GitHub asset must appear once: $($asset.id)"
            }
            if ([Int64]$remote[0].size -ne [Int64]$asset.size) {
                throw "remote size changed: $($asset.id)"
            }
            $digest = ([string]$remote[0].digest) -replace '^sha256:', ''
            if ($digest.ToUpperInvariant() -ne ([string]$asset.sha256).ToUpperInvariant()) {
                throw "remote digest changed: $($asset.id)"
            }
        } elseif ($asset.provider -eq 'huggingface') {
            $request = [System.Net.Http.HttpRequestMessage]::new(
                [System.Net.Http.HttpMethod]::Head,
                [string]$asset.url
            )
            $response = $null
            try {
                $response = $client.SendAsync($request).GetAwaiter().GetResult()
                $status = [int]$response.StatusCode
                if ($status -lt 200 -or $status -ge 400) {
                    throw "Hugging Face HEAD failed with HTTP $status for $($asset.id)"
                }
                $linkedSize = Get-HeaderValue -Response $response -Name 'X-Linked-Size'
                $linkedEtag = (Get-HeaderValue -Response $response -Name 'X-Linked-ETag').Trim('"')
                if ([Int64]$linkedSize -ne [Int64]$asset.size) {
                    throw "remote size changed: $($asset.id)"
                }
                if ($linkedEtag.ToUpperInvariant() -ne ([string]$asset.sha256).ToUpperInvariant()) {
                    throw "remote digest changed: $($asset.id)"
                }
            } finally {
                if ($null -ne $response) {
                    $response.Dispose()
                }
                $request.Dispose()
            }
        } else {
            throw "unsupported runtime asset provider: $($asset.provider)"
        }
        Write-Output "verified remote asset: $($asset.id)"
    }
} finally {
    $client.Dispose()
    $handler.Dispose()
}

Write-Output 'runtime asset metadata: PASS'
