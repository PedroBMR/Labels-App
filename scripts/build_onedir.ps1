$ErrorActionPreference = 'Stop'

# Activate virtual environment if present
if (Test-Path '.venv\Scripts\Activate.ps1') {
    & '.\.venv\Scripts\Activate.ps1'
} elseif (Test-Path 'venv\Scripts\Activate.ps1') {
    & '.\venv\Scripts\Activate.ps1'
}

# Ensure required packages are installed
pip install -r requirements-py313.txt

# Build directory-based package
pyinstaller --noconfirm .\GeradorEtiquetas_onedir.spec

# Retrieve version from _version.py
$version = (
    python - <<'PY'
import _version; print(_version.__version__, end='')
PY
).Trim()

$exeName = if ($env:APP_NAME) { $env:APP_NAME } else { 'GeradorEtiquetas' }
$src = Join-Path 'dist' (Join-Path $exeName "$exeName.exe")
$dest = Join-Path 'dist' "${exeName}_v$version.exe"
Copy-Item -Force -Path $src -Destination $dest
