[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$DatasetPath,

    [switch]$VerifyHashes,

    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'

function Get-GzipCsvHeader {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fileStream = [System.IO.File]::OpenRead($Path)
    try {
        $gzipStream = [System.IO.Compression.GZipStream]::new(
            $fileStream,
            [System.IO.Compression.CompressionMode]::Decompress
        )
        try {
            $reader = [System.IO.StreamReader]::new($gzipStream)
            try {
                return $reader.ReadLine()
            }
            finally {
                $reader.Dispose()
            }
        }
        finally {
            $gzipStream.Dispose()
        }
    }
    finally {
        $fileStream.Dispose()
    }
}

function Get-ChecksumManifest {
    param([Parameter(Mandatory = $true)][string]$RootPath)

    $manifestPath = Join-Path $RootPath 'SHA256SUMS.txt'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        return @()
    }

    $entries = foreach ($line in Get-Content -LiteralPath $manifestPath) {
        if ($line -match '^([0-9a-fA-F]{64})\s+(.+)$') {
            [PSCustomObject]@{
                ExpectedHash = $matches[1].ToLowerInvariant()
                RelativePath = $matches[2]
            }
        }
    }
    return @($entries)
}

$resolvedRoot = (Resolve-Path -LiteralPath $DatasetPath).Path
$files = @(Get-ChildItem -LiteralPath $resolvedRoot -File -Recurse | Sort-Object FullName)
$manifest = @(Get-ChecksumManifest -RootPath $resolvedRoot)
$manifestByPath = @{}
foreach ($entry in $manifest) {
    $normalized = $entry.RelativePath -replace '/', [System.IO.Path]::DirectorySeparatorChar
    $manifestByPath[$normalized] = $entry.ExpectedHash
}

$fileResults = foreach ($file in $files) {
    $relativePath = [System.IO.Path]::GetRelativePath($resolvedRoot, $file.FullName)
    $header = $null
    if ($file.Name.EndsWith('.csv.gz', [System.StringComparison]::OrdinalIgnoreCase)) {
        $header = Get-GzipCsvHeader -Path $file.FullName
    }

    $expectedHash = $manifestByPath[$relativePath]
    $actualHash = $null
    $hashStatus = if ($expectedHash) { 'not_checked' } else { 'not_listed' }
    if ($VerifyHashes -and $expectedHash) {
        $actualHash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        $hashStatus = if ($actualHash -eq $expectedHash) { 'ok' } else { 'mismatch' }
    }

    [PSCustomObject]@{
        relative_path = $relativePath.Replace('\', '/')
        bytes = $file.Length
        csv_header = $header
        expected_sha256 = $expectedHash
        actual_sha256 = $actualHash
        hash_status = $hashStatus
    }
}

$listedPaths = @($manifest | ForEach-Object {
    ($_.RelativePath -replace '/', [System.IO.Path]::DirectorySeparatorChar)
})
$existingRelativePaths = @($files | ForEach-Object {
    [System.IO.Path]::GetRelativePath($resolvedRoot, $_.FullName)
})
$missingManifestFiles = @($listedPaths | Where-Object { $_ -notin $existingRelativePaths })
$mismatches = @($fileResults | Where-Object hash_status -eq 'mismatch')
$checked = @($fileResults | Where-Object hash_status -in @('ok', 'mismatch'))

$result = [PSCustomObject]@{
    dataset_path = $resolvedRoot
    audited_at_utc = [DateTime]::UtcNow.ToString('o')
    file_count = $files.Count
    total_bytes = ($files | Measure-Object -Property Length -Sum).Sum
    csv_gz_count = @($files | Where-Object Name -Like '*.csv.gz').Count
    checksum_manifest_entries = $manifest.Count
    checksum_checked = $checked.Count
    checksum_ok = @($checked | Where-Object hash_status -eq 'ok').Count
    checksum_mismatch = $mismatches.Count
    checksum_missing_files = $missingManifestFiles
    files = $fileResults
}

$json = $result | ConvertTo-Json -Depth 5
if ($OutputPath) {
    $parent = Split-Path -Parent $OutputPath
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    Set-Content -LiteralPath $OutputPath -Value $json -Encoding utf8
}
else {
    $json
}

if ($mismatches.Count -gt 0 -or $missingManifestFiles.Count -gt 0) {
    exit 1
}
