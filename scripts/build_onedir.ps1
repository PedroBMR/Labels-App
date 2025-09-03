$ErrorActionPreference = 'Stop'

# Activate virtual environment if present
if (Test-Path '.venv\Scripts\Activate.ps1') {
    & '.\.venv\Scripts\Activate.ps1'
} elseif (Test-Path 'venv\Scripts\Activate.ps1') {
    & '.\venv\Scripts\Activate.ps1'
}

# Remove conflicting Qt packages if present
$qtConflicts = @('pyside6', 'pyside6-addons', 'pyside6-essentials')
foreach ($pkg in $qtConflicts) {
    pip show $pkg > $null 2>&1
    if ($LASTEXITCODE -eq 0) { pip uninstall -y $pkg }
}

# Install runtime and development dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Build executable
pyinstaller --noconfirm .\GeradorEtiquetas_onedir.spec

# Determine executable name
$exeName = if ($env:APP_NAME) { $env:APP_NAME } else { 'GeradorEtiquetas' }
$src = Join-Path 'dist' "$exeName.exe"

# Sign executable
if (Get-Command 'signtool.exe' -ErrorAction SilentlyContinue) {
    & signtool sign /fd SHA256 /a /tr http://timestamp.digicert.com $src
} else {
    Write-Warning 'signtool.exe not found; skipping code signing.'
}

# Retrieve version from _version.py
$version = (
    python -c "import _version, sys; sys.stdout.write(_version.__version__)"
).Trim()

$dest = Join-Path 'dist' "${exeName}_v$version.exe"
Copy-Item -Force -Path $src -Destination $dest
