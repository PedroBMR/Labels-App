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

# Ensure required packages are installed
$packages = @('pyinstaller','pyqt5','pillow','pywin32')
foreach ($pkg in $packages) {
    pip show $pkg > $null 2>&1
    if ($LASTEXITCODE -ne 0) {
        pip install $pkg
    }
}

# Build executable
pyinstaller --noconfirm .\GeradorEtiquetas.spec

# Copy assets directory beside executable for runtime access
Copy-Item -Recurse -Force 'assets' (Join-Path 'dist' 'assets')

# Retrieve version from _version.py
$version = (
    python -c "import _version, sys; sys.stdout.write(_version.__version__)"
).Trim()

$exeName = if ($env:APP_NAME) { $env:APP_NAME } else { 'GeradorEtiquetas' }
$src = Join-Path 'dist' "$exeName.exe"
$dest = Join-Path 'dist' "${exeName}_v$version.exe"
Copy-Item -Force -Path $src -Destination $dest
