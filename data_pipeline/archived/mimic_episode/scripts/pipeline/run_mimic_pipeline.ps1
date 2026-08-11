[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('sync', 'test', 'validate', 'extract', 'validate-episodes', 'aggregate-episodes', 'export-episode')]
    [string]$Task,

    [string]$EnvironmentPath = $env:UV_PROJECT_ENVIRONMENT,
    [string]$DataRoot = 'mimic',
    [string]$OutputDir,
    [string]$EpisodeId,
    [string]$Destination,
    [string]$MemoryLimit = '8GB',

    [ValidateRange(1, 256)]
    [int]$Threads = 4,

    [switch]$Overwrite
)

$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

if ([string]::IsNullOrWhiteSpace($EnvironmentPath)) {
    $EnvironmentPath = 'C:\Python312\envs\mimic-benchmark'
}

$env:UV_PROJECT_ENVIRONMENT = $EnvironmentPath
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..\..\..')).Path
$uv = (Get-Command uv -ErrorAction Stop).Source

function Invoke-Uv {
    param([string[]]$Arguments)

    & $uv @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "uv 命令执行失败，退出码：$LASTEXITCODE"
    }
}

Push-Location -LiteralPath $projectRoot
try {
    switch ($Task) {
        'sync' {
            Invoke-Uv -Arguments @('sync', '--locked')
        }
        'test' {
            Invoke-Uv -Arguments @(
                'run', '--locked', 'python', '-m', 'unittest',
                'discover', '-s', 'tests', '-v'
            )
        }
        'validate' {
            Invoke-Uv -Arguments @(
                'run', '--locked', 'python', '-m', 'data_pipeline.archived.mimic_episode',
                'validate', '--data-root', $DataRoot
            )
        }
        'extract' {
            $resolvedOutputDir = if ([string]::IsNullOrWhiteSpace($OutputDir)) {
                'outputs/stage1'
            } else {
                $OutputDir
            }
            $arguments = @(
                'run', '--locked', 'python', '-m', 'data_pipeline.archived.mimic_episode',
                'extract', '--data-root', $DataRoot,
                '--output-dir', $resolvedOutputDir,
                '--memory-limit', $MemoryLimit,
                '--threads', $Threads.ToString()
            )
            if ($Overwrite) {
                $arguments += '--overwrite'
            }
            Invoke-Uv -Arguments $arguments
        }
        'validate-episodes' {
            Invoke-Uv -Arguments @(
                'run', '--locked', 'python', '-m', 'data_pipeline.archived.mimic_episode',
                'validate-episodes', '--data-root', $DataRoot
            )
        }
        'aggregate-episodes' {
            $resolvedOutputDir = if ([string]::IsNullOrWhiteSpace($OutputDir)) {
                'G:\Projects\医疗数据集评测-MIMIC\outputs\episodes'
            } else {
                $OutputDir
            }
            $arguments = @(
                'run', '--locked', 'python', '-m', 'data_pipeline.archived.mimic_episode',
                'aggregate-episodes', '--data-root', $DataRoot,
                '--output-dir', $resolvedOutputDir,
                '--memory-limit', $MemoryLimit,
                '--threads', $Threads.ToString()
            )
            if ($Overwrite) {
                $arguments += '--overwrite'
            }
            Invoke-Uv -Arguments $arguments
        }
        'export-episode' {
            if ([string]::IsNullOrWhiteSpace($EpisodeId)) {
                throw 'export-episode 需要 -EpisodeId。'
            }
            if ([string]::IsNullOrWhiteSpace($Destination)) {
                throw 'export-episode 需要 -Destination。'
            }
            $resolvedOutputDir = if ([string]::IsNullOrWhiteSpace($OutputDir)) {
                'G:\Projects\医疗数据集评测-MIMIC\outputs\episodes'
            } else {
                $OutputDir
            }
            $arguments = @(
                'run', '--locked', 'python', '-m', 'data_pipeline.archived.mimic_episode',
                'export-episode', '--output-dir', $resolvedOutputDir,
                '--episode-id', $EpisodeId,
                '--destination', $Destination
            )
            if ($Overwrite) {
                $arguments += '--overwrite'
            }
            Invoke-Uv -Arguments $arguments
        }
    }
}
finally {
    Pop-Location
}
