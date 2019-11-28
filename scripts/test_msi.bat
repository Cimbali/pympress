for /r %%f in (dist\*.msi) do (set "installer=%%~f")

if "%installer%" == "" (
    echo **** INSTALLER MISSING ****
    exit /b 1
)

msiexec /l*v installer.log /qb /i "%installer%"

if errorlevel 1 (
    echo **** INSTALLER FAILED ****
    type installer.log
    exit /b 1
)


if exist "%programfiles%\pympress\" (
    "%programfiles%\pympress\pympress" --help
) else (
    "%programfiles(x86)%\pympress\pympress" --help
)


if errorlevel 1 (
    echo **** TEST FAILED ****
    type %LOCALAPPDATA%\pympress.log
    type %APPDATA%\pympress.log
    exit /b 1
)
