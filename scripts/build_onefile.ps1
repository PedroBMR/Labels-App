$ErrorActionPreference = 'Stop'

. "$PSScriptRoot/build_shared.ps1"

Invoke-Build -SpecFile '.\GeradorEtiquetas.spec' -Binding 'PyQt5' -CopyAssets
