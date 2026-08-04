param(
    [string]$RepoRoot = "C:\SIRAJ\Repositories\siraj-os",
    [string]$PythonExe = "C:\SIRAJ\Repositories\historical-fixture-venv-20260716\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

if (-not (Test-Path $RepoRoot)) {
    throw "SIRAJ repository not found: $RepoRoot"
}

& $PythonExe -c "import PySide6" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "PySide6 is not installed in the SIRAJ environment."
    Write-Host "Install once with:"
    Write-Host "& `"$PythonExe`" -m pip install -e `"${RepoRoot}[desktop]`""
    exit 5
}

Push-Location $RepoRoot
try {
    & $PythonExe -m src.presentation.desktop --repo-root $RepoRoot
}
finally {
    Pop-Location
}
