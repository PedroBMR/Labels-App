$ErrorActionPreference = 'Stop'

function Test-PipPackage {
    param([string]$Name)
    try {
        pip show $Name > $null 2>&1
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Invoke-Build {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SpecFile,

        [ValidateSet('Auto', 'PyQt5', 'PySide6')]
        [string]$Binding = 'PyQt5',

        [switch]$CopyAssets
    )

    if (Test-Path '.venv\Scripts\Activate.ps1') {
        & '.\.venv\Scripts\Activate.ps1'
    } elseif (Test-Path 'venv\Scripts\Activate.ps1') {
        & '.\venv\Scripts\Activate.ps1'
    }

    $selectedBinding = switch ($Binding) {
        'Auto' {
            $value = $env:QT_BINDING
            if (-not $value) { $value = 'PyQt5' }
            $value
        }
        default { $Binding }
    }

    $env:QT_BINDING = $selectedBinding

    if ($selectedBinding -eq 'PySide6') {
        $qtConflicts = @('pyqt5', 'pyqt5-qt5', 'pyqt5-sip')
    } else {
        $qtConflicts = @('pyside6', 'pyside6-addons', 'pyside6-essentials')
    }

    foreach ($pkg in $qtConflicts) {
        if (Test-PipPackage $pkg) { pip uninstall -y $pkg }
    }

    pip install -r requirements-dev.txt

    if ($selectedBinding -eq 'PySide6') {
        if (Test-Path 'requirements-pyside6.txt') {
            pip install -r requirements-pyside6.txt
        }
    } else {
        if (Test-Path 'requirements-pyqt5.txt') {
            pip install -r requirements-pyqt5.txt
        }
    }

    $hasPyQt5 = Test-PipPackage 'PyQt5'
    $hasPySide6 = Test-PipPackage 'PySide6'
    if ($hasPyQt5 -and $hasPySide6) {
        Write-Error 'Both PyQt5 and PySide6 are installed. Please uninstall the unnecessary binding.'
        exit 1
    }

    $specPath = (Resolve-Path $SpecFile).Path
    pyinstaller --noconfirm $specPath

    if ($CopyAssets) {
        if (Test-Path 'assets') {
            Copy-Item -Recurse -Force 'assets' (Join-Path 'dist' 'assets')
        } else {
            Write-Warning 'assets directory not found; skipping asset copy.'
        }
    }

    $exeName = if ($env:APP_NAME) { $env:APP_NAME } else { 'GeradorEtiquetas' }
    $src = Join-Path 'dist' "$exeName.exe"

    if (Get-Command 'signtool.exe' -ErrorAction SilentlyContinue) {
        & signtool sign /fd SHA256 /a /tr http://timestamp.digicert.com $src
    } else {
        Write-Warning 'signtool.exe not found; skipping code signing.'
    }

    $version = (
        python -c "import _version, sys; sys.stdout.write(_version.__version__)"
    ).Trim()

    $dest = Join-Path 'dist' "${exeName}_v$version.exe"
    Copy-Item -Force -Path $src -Destination $dest
}
