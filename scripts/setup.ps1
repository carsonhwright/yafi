#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvDir = if ($env:VENV_DIR) { $env:VENV_DIR } else { Join-Path $RepoRoot ".yafi-venv" }
$RequirementsFile = Join-Path $RepoRoot "requirements.txt"

$PythonBin = $env:PYTHON_BIN
if (-not $PythonBin) {
    $PythonBin = if (Get-Command py -ErrorAction SilentlyContinue) { "py -3" } else { "python" }
}

if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating virtual environment at $VenvDir"
    Invoke-Expression "$PythonBin -m venv `"$VenvDir`""
}
else {
    Write-Host "Virtual environment already exists at $VenvDir"
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

Write-Host "Upgrading pip"
& $VenvPython -m pip install --upgrade pip

Write-Host "Installing dependencies from $RequirementsFile"
& $VenvPython -m pip install -r $RequirementsFile

Write-Host ""
Write-Host "Setup complete. Activate the environment with:"
Write-Host "  $VenvDir\Scripts\Activate.ps1"
