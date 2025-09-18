$ErrorActionPreference = 'Stop'

. "$PSScriptRoot/build_shared.ps1"

Invoke-Build -SpecFile '.\GeradorEtiquetas.spec' -Binding 'Auto' -CopyAssets
