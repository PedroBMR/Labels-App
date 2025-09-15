$ErrorActionPreference = 'Stop'

# Helper to check if a pip package is installed without throwing
function Test-PipPackage {
    param([string]$Name)
    try {
        pip show $Name > $null 2>&1
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

# Activate virtual environment if present
if (Test-Path '.venv\Scripts\Activate.ps1') {
    & '.\.venv\Scripts\Activate.ps1'
} elseif (Test-Path 'venv\Scripts\Activate.ps1') {
    & '.\venv\Scripts\Activate.ps1'
}

# Determine which Qt binding to use (default: PyQt5)
$binding = $env:QT_BINDING
if (-not $binding) { $binding = 'PyQt5' }
$env:QT_BINDING = $binding

# Remove packages for the opposite binding, if present
if ($binding -eq 'PySide6') {
    $qtConflicts = @('pyqt5', 'pyqt5-qt5', 'pyqt5-sip')
} else {
    $qtConflicts = @('pyside6', 'pyside6-addons', 'pyside6-essentials')
}
foreach ($pkg in $qtConflicts) {
    if (Test-PipPackage $pkg) { pip uninstall -y $pkg }
}

# Install runtime and development dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install the selected Qt binding
if ($binding -eq 'PySide6') {
    pip install -r requirements-pyside6.txt
} else {
    pip install -r requirements-pyqt5.txt
}

# Ensure only one Qt binding is installed
$hasPyQt5 = Test-PipPackage 'PyQt5'
$hasPySide6 = Test-PipPackage 'PySide6'
if ($hasPyQt5 -and $hasPySide6) {
    Write-Error 'Both PyQt5 and PySide6 are installed. Please uninstall the unnecessary binding.'
    exit 1
}

# Build executable
pyinstaller --noconfirm .\GeradorEtiquetas.spec

# Copy assets directory beside executable for runtime access
Copy-Item -Recurse -Force 'assets' (Join-Path 'dist' 'assets')

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

