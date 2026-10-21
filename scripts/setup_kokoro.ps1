<#
  Installs the optional Kokoro voice runtime for NEXUS (Windows).
  Kokoro needs Python 3.10-3.12, so it is installed in its own environment under
  %LOCALAPPDATA%\NEXUS\kokoro\venv and does not touch the NEXUS app itself.

  Usage:  powershell -ExecutionPolicy Bypass -File scripts\setup_kokoro.ps1 [-NoWarmup]
#>
param([switch]$NoWarmup, [string]$Python = "")

$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "setup_kokoro.py"
if (-not (Test-Path $script)) { throw "setup_kokoro.py not found next to this script." }

$launcher = $null
foreach ($candidate in @("py", "python", "python3")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) { $launcher = $candidate; break }
}
if (-not $launcher) {
    Write-Host "Python was not found. Install Python 3.12 from https://www.python.org/downloads/ (tick 'py launcher') and run this again."
    exit 2
}

$arguments = @($script)
if ($NoWarmup) { $arguments += "--no-warmup" }
if ($Python)   { $arguments += @("--python", $Python) }

# "py" selects the newest Python by default; setup_kokoro.py itself looks for 3.10-3.12.
if ($launcher -eq "py") { & py -3 @arguments } else { & $launcher @arguments }
exit $LASTEXITCODE
