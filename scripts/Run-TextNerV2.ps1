[CmdletBinding()]
param(
    [ValidateSet('prepare', 'mentions', 'relations', 'compile', 'status', 'all')]
    [string]$Stage = 'all',

    [int]$MaxDocs = 0,

    [int]$SamplePerSource = 0,

    [int]$RequestsPerMinute = 30,

    [switch]$RetryFailed,

    [switch]$ValidateOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
$aggregationRoot = Join-Path $repositoryRoot 'data\test_1000_0812\event_pipeline_output\aggregation'
$outputRoot = Join-Path $repositoryRoot 'data\ner_v2_v2'
$envFile = Join-Path $repositoryRoot '.env'
$mentionPrompt = Join-Path $repositoryRoot 'config\text_ner\prompts\ner-v2-mentions.md'
$relationPrompt = Join-Path $repositoryRoot 'config\text_ner\prompts\ner-v2-relations.md'

$requiredFiles = [ordered]@{
    python = $pythonPath
    env = $envFile
    mentionPrompt = $mentionPrompt
    relationPrompt = $relationPrompt
    aggregation = (Join-Path $aggregationRoot 'raw_source_records.parquet')
}
$missing = @(
    $requiredFiles.GetEnumerator() |
        Where-Object { -not (Test-Path -LiteralPath $_.Value -PathType Leaf) } |
        ForEach-Object { "{0}: {1}" -f $_.Key, $_.Value }
)
if ($missing.Count -gt 0) {
    throw "Text NER v2 preflight failed; missing files: $($missing -join '; ')"
}

# Resolve the Python runner. Prefer `uv run` so the interpreter is launched through
# uv's resolver; fall back to the venv `python.exe` when uv is missing or cannot
# initialize (for example a read-only uv cache).
$uv = Get-Command uv -ErrorAction SilentlyContinue
$useUv = $false
if ($uv) {
    Push-Location $repositoryRoot
    try {
        & $uv.Source run --no-sync python -c 'import sys' *> $null
        if ($LASTEXITCODE -eq 0) { $useUv = $true }
    }
    catch { }
    finally { Pop-Location }
}

function Invoke-Py {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$PyArgs)
    if ($ValidateOnly) {
        Write-Host "Would run: python $($PyArgs -join ' ')"
        return
    }
    if ($useUv) {
        & $uv.Source run --no-sync python @PyArgs
    }
    else {
        & $pythonPath @PyArgs
    }
}

$pythonVersion = if ($useUv) {
    & $uv.Source run --no-sync python -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'
}
else {
    & $pythonPath -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'
}
if ($LASTEXITCODE -ne 0) { throw "Unable to execute project Python" }
if (-not $pythonVersion.StartsWith('3.12.')) {
    throw "Text NER v2 requires Python 3.12; resolved: $pythonVersion"
}

Write-Host "Repository: $repositoryRoot"
Write-Host "Python runner: $(if ($useUv) { 'uv run (uv ' + (& $uv.Source --version) + ')' } else { $pythonPath + ' (venv redirector)' })"
Write-Host "Python: $pythonVersion"
Write-Host "Output: $outputRoot"
Write-Host "Stage: $Stage"
if ($MaxDocs -gt 0) { Write-Host "Max docs: $MaxDocs" }
if ($SamplePerSource -gt 0) { Write-Host "Sample per source: $SamplePerSource" }

Push-Location $repositoryRoot
try {
    switch ($Stage) {
        'prepare' {
            Invoke-Py -m data_pipeline.text_ner_v2 prepare $aggregationRoot --output-dir $outputRoot
        }
        'mentions' {
            $args = @('-m', 'data_pipeline.text_ner_v2', 'run-mentions', $outputRoot,
                '--env-file', $envFile, '--mention-prompt', $mentionPrompt,
                '--requests-per-minute', $RequestsPerMinute)
            if ($MaxDocs -gt 0) { $args += @('--max-docs', $MaxDocs) }
            if ($SamplePerSource -gt 0) { $args += @('--sample-per-source', $SamplePerSource) }
            if ($RetryFailed) { $args += '--retry-failed' }
            Invoke-Py @args
        }
        'relations' {
            $args = @('-m', 'data_pipeline.text_ner_v2', 'run-relations', $outputRoot,
                '--env-file', $envFile, '--relation-prompt', $relationPrompt,
                '--requests-per-minute', $RequestsPerMinute)
            if ($MaxDocs -gt 0) { $args += @('--max-docs', $MaxDocs) }
            if ($RetryFailed) { $args += '--retry-failed' }
            Invoke-Py @args
        }
        'compile' {
            Invoke-Py -m data_pipeline.text_ner_v2 compile $outputRoot
        }
        'status' {
            Invoke-Py -m data_pipeline.text_ner_v2 status $outputRoot
        }
        'all' {
            if (-not (Test-Path -LiteralPath (Join-Path $outputRoot 'documents.parquet') -PathType Leaf)) {
                Invoke-Py -m data_pipeline.text_ner_v2 prepare $aggregationRoot --output-dir $outputRoot
            }
            $mentionArgs = @('-m', 'data_pipeline.text_ner_v2', 'run-mentions', $outputRoot,
                '--env-file', $envFile, '--mention-prompt', $mentionPrompt,
                '--requests-per-minute', $RequestsPerMinute)
            if ($MaxDocs -gt 0) { $mentionArgs += @('--max-docs', $MaxDocs) }
            if ($SamplePerSource -gt 0) { $mentionArgs += @('--sample-per-source', $SamplePerSource) }
            if ($RetryFailed) { $mentionArgs += '--retry-failed' }
            Invoke-Py @mentionArgs

            $relationArgs = @('-m', 'data_pipeline.text_ner_v2', 'run-relations', $outputRoot,
                '--env-file', $envFile, '--relation-prompt', $relationPrompt,
                '--requests-per-minute', $RequestsPerMinute)
            if ($MaxDocs -gt 0) { $relationArgs += @('--max-docs', $MaxDocs) }
            if ($RetryFailed) { $relationArgs += '--retry-failed' }
            Invoke-Py @relationArgs

            Invoke-Py -m data_pipeline.text_ner_v2 compile $outputRoot
        }
    }
}
finally {
    Pop-Location
}
