param(
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$healthUrl = "http://127.0.0.1:$Port/api/health"
$appUrl = "http://127.0.0.1:$Port"

function Test-ServiceReady {
    param(
        [string]$Url
    )

    try {
        $null = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 2
        return $true
    } catch {
        return $false
    }
}

function Stop-ExistingAppServer {
    param(
        [int]$TargetPort,
        [string]$RootPath
    )

    $listeners = @()
    try {
        $listeners = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction Stop
    } catch {
        $listeners = @()
    }

    foreach ($listener in $listeners) {
        $processId = $listener.OwningProcess
        if (-not $processId) {
            continue
        }
        try {
            $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction Stop
        } catch {
            continue
        }

        $commandLine = $process.CommandLine
        if (-not $commandLine) {
            continue
        }

        if ($commandLine -like "*-m app.main*" -and $commandLine -like "*$RootPath*") {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 800
        }
    }
}

function Resolve-PythonCommand {
    $venvPython = Join-Path $root ".venv\Scripts\python.exe"
    $msysVenvPython = Join-Path $root ".venv\bin\python.exe"
    $condaCandidates = @(
        (Join-Path $env:UserProfile "miniconda3\envs\douyin-publisher\python.exe"),
        (Join-Path $env:UserProfile "anaconda3\envs\douyin-publisher\python.exe"),
        "C:\ProgramData\miniconda3\envs\douyin-publisher\python.exe",
        "C:\ProgramData\anaconda3\envs\douyin-publisher\python.exe"
    )

    foreach ($candidate in $condaCandidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return @{
                FilePath = $candidate
                Arguments = @("-m", "app.main")
            }
        }
    }

    if ($env:CONDA_PREFIX -and (Get-Command python -ErrorAction SilentlyContinue)) {
        return @{
            FilePath = "python"
            Arguments = @("-m", "app.main")
        }
    }

    if (Test-Path $venvPython) {
        return @{
            FilePath = $venvPython
            Arguments = @("-m", "app.main")
        }
    }

    if (Test-Path $msysVenvPython) {
        return @{
            FilePath = $msysVenvPython
            Arguments = @("-m", "app.main")
        }
    }

    return @{
        FilePath = "python"
        Arguments = @("-m", "app.main")
    }
}

Stop-ExistingAppServer -TargetPort $Port -RootPath $root

$command = Resolve-PythonCommand
Start-Process `
    -FilePath $command.FilePath `
    -ArgumentList $command.Arguments `
    -WorkingDirectory $root `
    -WindowStyle Hidden | Out-Null

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    if (Test-ServiceReady -Url $healthUrl) {
        $ready = $true
        break
    }
}

if (-not $ready) {
    throw "Service did not become ready on $appUrl"
}

Start-Process $appUrl | Out-Null
