@echo off
REM Arranca el puente TradingView -> MT5 desde la carpeta del proyecto en Windows.
REM Ubicacion prevista: C:\Users\juanc\Documents\Ruah Commodities\RNT\Red Cluster POC
setlocal enabledelayedexpansion
cd /d "%~dp0.."

if not exist .venv (
    py -m venv .venv || goto :error
)
.venv\Scripts\python -m pip install --quiet --upgrade pip || goto :error
.venv\Scripts\python -m pip install --quiet -r bridge\requirements.txt || goto :error

if not exist bridge\.env (
    echo Falta bridge\.env  ^-  copia bridge\.env.example y completa los valores.
    exit /b 1
)

REM Carga bridge\.env (lineas CLAVE=valor, ignora comentarios).
for /f "usebackq tokens=1,* delims==" %%A in ("bridge\.env") do (
    set "line=%%A"
    if not "!line:~0,1!"=="#" if not "%%A"=="" set "%%A=%%B"
)

.venv\Scripts\python -m uvicorn bridge.app:app --host 0.0.0.0 --port 8000
goto :eof

:error
echo Error preparando el entorno.
exit /b 1
