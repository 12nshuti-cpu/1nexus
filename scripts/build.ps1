<#
  Reproducible Windows build for NEXUS.

  Produces:
    dist\NEXUS\NEXUS.exe             (+ NEXUSHotkey.exe beside it)
    installer_output\NEXUS-Setup-<version>.exe   (only if Inno Setup 6 is installed)

  Usage (from the repository root, in a normal PowerShell window):
    powershell -ExecutionPolicy Bypass -File scripts\build.ps1
    ... -SkipTests        skip the test suite (not recommended for releases)
    ... -SkipInstaller    build the app folder only

  Requirements: 64-bit Windows 10/11, Python 3.11 or 3.12 (64-bit) on PATH as
  "py" or "python". Python 3.13+ is untested for the packaged build.
  Inno Setup 6 (https://jrsoftware.org/isinfo.php) is optional.
#>
param([switch]$SkipTests, [switch]$SkipInstaller)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Step($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }
function Run($exe, [string[]]$arguments) {
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { throw "'$exe $($arguments -join ' ')' failed with exit code $LASTEXITCODE" }
}

# --- version (single source: config\settings.py) ------------------------------------
$match = Select-String -Path "config\settings.py" -Pattern '^APP_VERSION\s*=\s*"([^"]+)"'
if (-not $match) { throw "Could not read APP_VERSION from config\settings.py" }
$version = $match.Matches[0].Groups[1].Value
Write-Host "Building NEXUS $version"

# --- clean build environment ---------------------------------------------------------
Step "Creating build environment (.venv-build)"
$python = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
if (-not (Test-Path ".venv-build\Scripts\python.exe")) {
    if ($python -eq "py") { Run "py" @("-3.12", "-m", "venv", ".venv-build") } else { Run "python" @("-m", "venv", ".venv-build") }
}
$venvPython = (Resolve-Path ".venv-build\Scripts\python.exe").Path
Run $venvPython @("-m", "pip", "install", "--disable-pip-version-check", "--upgrade", "pip")
Run $venvPython @("-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements-dev.txt")

# --- tests -----------------------------------------------------------------------------
if (-not $SkipTests) {
    Step "Running tests"
    Run $venvPython @("-m", "pytest", "tests", "-q")
}

# --- freeze ----------------------------------------------------------------------------
Step "Building NEXUS.exe"
Run $venvPython @("-m", "PyInstaller", "--noconfirm", "--clean", "NEXUS.spec")
Step "Building NEXUSHotkey.exe"
Run $venvPython @("-m", "PyInstaller", "--noconfirm", "--clean", "NEXUSHotkey.spec")
Copy-Item "dist\NEXUSHotkey.exe" "dist\NEXUS\NEXUSHotkey.exe" -Force

# --- sanity: no user data in the build ----------------------------------------------------
Step "Checking the build contains no user data"
$leaks = Get-ChildItem "dist\NEXUS" -Recurse -Include "*.db", "*.db-wal", "*.db-shm", "gemini_api_key*", "*.key", ".env" -ErrorAction SilentlyContinue
if ($leaks) { $leaks | ForEach-Object { Write-Host "LEAK: $($_.FullName)" -ForegroundColor Red }; throw "User data found in dist\NEXUS" }

# --- smoke test the frozen app ------------------------------------------------------------
Step "Smoke-testing the frozen app (--selftest: builds the UI, checks bundled files, exits)"
$env:NEXUS_DATA_DIR = Join-Path $env:TEMP "nexus-build-smoke"
$env:NEXUS_DISABLE_KEYRING = "1"
$process = Start-Process -FilePath "dist\NEXUS\NEXUS.exe" -ArgumentList "--selftest" -PassThru -Wait -WindowStyle Hidden
$code = $process.ExitCode
Remove-Item Env:NEXUS_DATA_DIR, Env:NEXUS_DISABLE_KEYRING
if ($code -ne 0) {
    $logFile = Get-ChildItem (Join-Path $env:TEMP "nexus-build-smoke\logs") -Filter "*.log" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($logFile) { Get-Content $logFile.FullName -Tail 30 }
    throw "The frozen NEXUS.exe failed its self-test (exit code $code)."
}
Write-Host "Self-test passed." -ForegroundColor Green

# --- installer ------------------------------------------------------------------------------
if (-not $SkipInstaller) {
    $iscc = @(
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($iscc) {
        Step "Building installer"
        Run $iscc @("/DAppVersion=$version", "installer\nexus.iss")
        Write-Host "Installer: installer_output\NEXUS-Setup-$version.exe" -ForegroundColor Green
    } else {
        Write-Host "Inno Setup 6 not found - skipping the installer. Install it and re-run to produce NEXUS-Setup.exe." -ForegroundColor Yellow
    }
}

Write-Host "`nBuild finished. Follow docs\RELEASE.md to test it on a clean machine before distributing." -ForegroundColor Green
