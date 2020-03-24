@echo off
for /r %%f in (dist\*.msi) do (set "installer=%%~f")

if "%installer%" == "" (
    echo **** INSTALLER MISSING ****
    exit /b 1
)

msiexec /l*v installer.log /qb /i "%installer%"

if errorlevel 1 (
    echo **** INSTALLER FAILED ****
    type installer.log
    goto :eof
)

for %%d in (
    "%programfiles%\pympress"
    "%programfiles(x86)%\pympress"
    "%APPDATA%\Programs\pympress"
    "%LOCALAPPDATA%\Programs\pympress"
) do (
    echo %%d
    if exist %%d (
        %%d\pympress --help

        if errorlevel 1 (goto :err)

        echo
        echo Warnings in log file:
        type %LOCALAPPDATA%\pympress.log
        goto :eof
    )
)

echo Pympress not found

:err
echo **** TEST FAILED ****
type %LOCALAPPDATA%\pympress.log
exit /b 1
