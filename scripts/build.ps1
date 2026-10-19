param([switch]$Clean)
if ($Clean) { Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue }
pyinstaller NEXUS.spec --clean --noconfirm
Write-Host "Build done: dist/NEXUS/NEXUS.exe"
