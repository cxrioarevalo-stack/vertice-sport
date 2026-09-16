@echo off
setlocal
cd /d "%~dp0"
if not exist requirements.txt (
  echo No se encontro requirements.txt. Ejecuta este archivo desde la carpeta vertice-sport.
  pause
  exit /b 1
)
where py >nul 2>nul
if errorlevel 1 (
  echo Python no esta instalado o no esta disponible como 'py'.
  pause
  exit /b 1
)

echo ================================================
echo VERTICE SPORT - ARRANQUE WINDOWS
echo ================================================
echo.
py -m pip install -r requirements.txt
if errorlevel 1 goto :error

set VERTICE_TZ=America/New_York
set ODDS_PROVIDER=oddspapi
set ODDS_BOOKMAKERS=betano
set VERTICE_DB=%CD%\data\vertice.db
set /p ODDSPAPI_API_KEY=Introduce tu API key de OddsPapi (no se guarda en archivos): 

echo.
echo Iniciando VERTICE SPORT en http://127.0.0.1:8000
cd backend
py -m uvicorn app:app --host 127.0.0.1 --port 8000
exit /b 0

:error
echo.
echo No se pudieron instalar las dependencias.
pause
exit /b 1
