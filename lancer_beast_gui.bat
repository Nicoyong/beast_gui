@echo off
setlocal
cd /d "%~dp0"

set "VENV=%~dp0.venv"
set "PY_VENV=%VENV%\Scripts\python.exe"
set "PYW_VENV=%VENV%\Scripts\pythonw.exe"

rem --- 1) Creer l'environnement virtuel s'il n'existe pas
if not exist "%PY_VENV%" (
    echo [1/2] Creation de l'environnement virtuel...
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv "%VENV%"
    ) else (
        python -m venv "%VENV%"
    )
    if not exist "%PY_VENV%" (
        echo.
        echo ERREUR : impossible de creer l'environnement virtuel.
        echo Installe Python 3 depuis https://www.python.org/downloads/
        echo et coche "Add python.exe to PATH" pendant l'installation.
        echo.
        pause
        exit /b 1
    )
)

rem --- 2) Installer les dependances si elles manquent
"%PY_VENV%" -c "import psutil" >nul 2>nul
if errorlevel 1 (
    echo [2/2] Installation des dependances : psutil...
    "%PY_VENV%" -m pip install --upgrade pip
    "%PY_VENV%" -m pip install psutil
    if errorlevel 1 (
        echo.
        echo ERREUR : l'installation de psutil a echoue. Verifie ta connexion internet.
        echo.
        pause
        exit /b 1
    )
)

rem --- 3) Lancer l'interface
rem     "lancer_beast_gui.bat debug" garde la console pour voir les erreurs eventuelles
if /i "%~1"=="debug" (
    "%PY_VENV%" beast_gui.py
    pause
    exit /b
)
start "" "%PYW_VENV%" beast_gui.py
exit /b
