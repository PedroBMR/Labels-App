$ErrorActionPreference = 'Stop'

. "$PSScriptRoot/build_shared.ps1"

Invoke-Build -SpecFile '.\GeradorEtiquetas_onedir.spec' -Binding 'PyQt5'
