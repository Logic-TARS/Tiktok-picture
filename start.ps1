$ErrorActionPreference = "Stop"

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$msysVenvPython = Join-Path $PSScriptRoot ".venv\bin\python.exe"
$isConda = $env:CONDA_PREFIX -and (Get-Command python -ErrorAction SilentlyContinue)

if ($isConda) {
    python -m app.main
} elseif (Test-Path $venvPython) {
    & $venvPython -m app.main
} elseif (Test-Path $msysVenvPython) {
    & $msysVenvPython -m app.main
} else {
    python -m app.main
}
