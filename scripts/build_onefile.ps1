$ErrorActionPreference = 'Stop'

# Activate virtual environment if present
if (Test-Path '.venv\Scripts\Activate.ps1') {
    & '.\.venv\Scripts\Activate.ps1'
} elseif (Test-Path 'venv\Scripts\Activate.ps1') {
    & '.\venv\Scripts\Activate.ps1'
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
pyinstaller --noconfirm .\GeradorEtiquetas_onefile.spec

# Retrieve version from _version.py
$version = (
    python - <<'PY'
import _version; print(_version.__version__, end='')
PY
).Trim()

$exeName = if ($env:APP_NAME) { $env:APP_NAME } else { 'GeradorEtiquetas' }
$src = Join-Path 'dist' "$exeName.exe"
$dest = Join-Path 'dist' "${exeName}_v$version.exe"
Copy-Item -Force -Path $src -Destination $dest
