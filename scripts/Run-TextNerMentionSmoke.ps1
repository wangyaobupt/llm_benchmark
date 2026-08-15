[CmdletBinding()]
param(
    [ValidateRange(1, 1000)]
    [int]$MaximumRequests = 10,

    [switch]$ConfirmExternalDataTransfer,

    [switch]$RetryFailuresOnly,

    [switch]$ValidateOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $ValidateOnly -and -not $ConfirmExternalDataTransfer) {
    throw (
        'External clinical-text transfer is not authorized. ' +
        'Pass -ConfirmExternalDataTransfer to execute, or -ValidateOnly for preflight.'
    )
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
$nerRoot = Join-Path $repositoryRoot 'data\test_1000_0812\event_pipeline_output\NER'
$executionRoot = Join-Path $nerRoot 'model_execution'
$requestPath = Join-Path $nerRoot 'extraction_interface\requests\mention_requests.jsonl'
$promptPath = Join-Path $nerRoot 'extraction_interface\configuration\prompts\mentions.md'
$responsePath = Join-Path $executionRoot 'mention_responses.jsonl'
$auditPath = Join-Path $executionRoot 'mention_api_audit.jsonl'
$failureAuditPath = Join-Path $executionRoot 'mention_api_audit.failures.jsonl'
$apiConfigPath = Join-Path $repositoryRoot 'config\text_ner\openai-compatible-api.json'
$environmentPath = Join-Path $repositoryRoot '.env'

$requiredFiles = [ordered]@{
    python = $pythonPath
    requests = $requestPath
    prompt = $promptPath
    api_config = $apiConfigPath
    environment = $environmentPath
}
$missing = @(
    $requiredFiles.GetEnumerator() |
        Where-Object { -not (Test-Path -LiteralPath $_.Value -PathType Leaf) } |
        ForEach-Object { "{0}: {1}" -f $_.Key, $_.Value }
)
if ($missing.Count -gt 0) {
    throw "Text NER preflight failed; missing files: $($missing -join '; ')"
}

$pythonVersion = & $pythonPath -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'
if ($LASTEXITCODE -ne 0) {
    throw "Unable to execute project Python: $pythonPath"
}
if (-not $pythonVersion.StartsWith('3.12.')) {
    throw "Text NER requires Python 3.12; resolved version: $pythonVersion"
}

Write-Host "Repository: $repositoryRoot"
Write-Host "Python: $pythonPath ($pythonVersion)"
Write-Host "Requests: $requestPath"
Write-Host "Prompt: $promptPath"
Write-Host "Responses: $responsePath"
Write-Host "Audit: $auditPath"
Write-Host "Maximum text units this run: $MaximumRequests"
Write-Host "Selection: $(if ($RetryFailuresOnly) { 'terminal failures only' } else { 'all pending' })"

if ($RetryFailuresOnly -and -not (Test-Path -LiteralPath $failureAuditPath -PathType Leaf)) {
    throw "Failure audit does not exist: $failureAuditPath"
}

if ($ValidateOnly) {
    Write-Host 'Preflight passed; no API request was sent.'
    return
}

if (-not (Test-Path -LiteralPath $executionRoot -PathType Container)) {
    New-Item -ItemType Directory -Path $executionRoot -Force | Out-Null
}

$arguments = @(
    '-m', 'data_pipeline.text_ner',
    'run-openai-compatible-api',
    $requestPath,
    $promptPath,
    $responsePath,
    $auditPath,
    $apiConfigPath,
    '--env-file', $environmentPath,
    '--execute',
    '--endpoint-scope', 'external',
    '--confirm-data-transfer-authorized',
    '--maximum-requests', $MaximumRequests
)
if ($RetryFailuresOnly) {
    $arguments += @('--retry-failures-from', $failureAuditPath)
}

Push-Location $repositoryRoot
try {
    & $pythonPath @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Text NER mention smoke run failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
