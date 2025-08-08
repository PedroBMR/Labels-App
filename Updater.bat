@echo off
setlocal enabledelayedexpansion

rem Determine dry run
set "DRYRUN=0"
if /I "%~1"=="/D" (
    echo [Dry-run] Nenhuma alteracao sera feita.
    set "DRYRUN=1"
)

rem Ensure working directory is script location
pushd "%~dp0" >nul

rem Read manifest.json using PowerShell
for /f %%i in ('powershell -NoProfile -Command "(Get-Content manifest.json | ConvertFrom-Json).exe"') do set "NEW_EXE=%%i"
for /f %%i in ('powershell -NoProfile -Command "(Get-Content manifest.json | ConvertFrom-Json).version"') do set "NEW_VERSION=%%i"
for /f %%i in ('powershell -NoProfile -Command "(Get-Content manifest.json | ConvertFrom-Json).sha256"') do set "NEW_SHA256=%%i"

echo Atualizando para versao %NEW_VERSION% usando %NEW_EXE%

rem Timestamp for backups
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmm"') do set "STAMP=%%i"

set "TARGET_EXE=GeradorEtiquetas.exe"
if exist "%TARGET_EXE%" (
    set "BACKUP=%TARGET_EXE%.bak-%STAMP%"
    if "%DRYRUN%"=="1" (
        echo [DRY-RUN] move "%TARGET_EXE%" "%BACKUP%"
    ) else (
        echo Fazendo backup de "%TARGET_EXE%" para "%BACKUP%"
        move /Y "%TARGET_EXE%" "%BACKUP%" >nul
    )
)

rem Copiar novo executavel
if "%DRYRUN%"=="1" (
    echo [DRY-RUN] copy "%NEW_EXE%" "%TARGET_EXE%"
) else (
    echo Copiando novo executavel...
    copy /Y "%NEW_EXE%" "%TARGET_EXE%" >nul
)

rem Validar SHA256
if "%DRYRUN%"=="1" (
    echo [DRY-RUN] certutil -hashfile "%TARGET_EXE%" SHA256
) else (
    for /f "tokens=1" %%h in ('certutil -hashfile "%TARGET_EXE%" SHA256 ^| findstr /R "^[0-9A-F][0-9A-F]*$"') do set "CALC_SHA=%%h"
    if /I not "%CALC_SHA%"=="%NEW_SHA256%" (
        echo Erro: hash SHA256 divergente!
        exit /b 1
    ) else (
        echo Hash SHA256 validado com sucesso.
    )
)

rem Criar version.txt
if "%DRYRUN%"=="1" (
    echo [DRY-RUN] echo %NEW_VERSION% ^> version.txt
) else (
    >version.txt echo %NEW_VERSION%
)

rem Migracao _internal -> assets
set "OLD_DIR=_internal"
set "NEW_DIR=assets"
for %%f in (historico_impressoes.csv contagem.json contagem_mensal.json logo.png color.png color.ico) do (
    if exist "%OLD_DIR%\%%f" (
        if exist "%NEW_DIR%\%%f" (
            echo Arquivo %%f ja existe em %NEW_DIR%.
        ) else (
            if "%DRYRUN%"=="1" (
                echo [DRY-RUN] copy "%OLD_DIR%\%%f" "%NEW_DIR%\%%f"
            ) else (
                echo Copiando %%f para %NEW_DIR%.
                copy "%OLD_DIR%\%%f" "%NEW_DIR%\%%f" >nul
            )
        )
    )
)

if exist "%OLD_DIR%" (
    set "BAK_DIR=_internal.bak-%STAMP%"
    if "%DRYRUN%"=="1" (
        echo [DRY-RUN] ren "%OLD_DIR%" "%BAK_DIR%"
    ) else (
        echo Renomeando %OLD_DIR% para %BAK_DIR%.
        ren "%OLD_DIR%" "%BAK_DIR%"
    )
)

echo Atualizacao concluida.

popd >nul
endlocal
