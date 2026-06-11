@echo off
chcp 65001 >nul
REM ============================================================
REM   My LifeRoad 시연 시작 (Windows)
REM   더블클릭하면: 파이썬 확인 -> 가상환경 + 패키지 설치 -> 서버 2개 -> 브라우저 자동 열기
REM   끄려면: 이 창을 닫기
REM ============================================================

cd /d "%~dp0"

echo =============================================
echo    My LifeRoad 시연 서버 (Windows)
echo =============================================
echo.

REM 1) 파이썬 찾기
set PYBIN=
where python >nul 2>&1 && set PYBIN=python
if "%PYBIN%"=="" (
  where py >nul 2>&1 && set PYBIN=py
)

if "%PYBIN%"=="" (
  echo [오류] 파이썬이 설치돼 있지 않습니다.
  echo.
  echo   아래 주소에서 Python 3.12를 설치한 뒤 이 파일을 다시 실행하세요:
  echo   https://www.python.org/downloads/
  echo   설치 화면에서 "Add Python to PATH" 체크를 꼭 켜세요.
  echo.
  pause
  exit /b 1
)

echo [1/4] 파이썬 확인 완료
%PYBIN% --version

REM 2) 가상환경 (없으면 생성)
if not exist ".venv" (
  echo [2/4] 가상환경 만드는 중... 처음 한 번만, 잠시 걸립니다
  %PYBIN% -m venv .venv
  if errorlevel 1 (
    echo [오류] 가상환경 생성 실패. 파이썬 버전을 확인하세요.
    pause
    exit /b 1
  )
) else (
  echo [2/4] 가상환경 확인 완료
)

REM 3) 패키지 설치
echo [3/4] 필요한 패키지 확인/설치 중... 처음엔 1~3분 걸릴 수 있습니다
.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
if errorlevel 1 (
  echo [오류] 패키지 설치 실패. 인터넷 연결을 확인하세요.
  pause
  exit /b 1
)

REM 4) 서버 2개 띄우기 (각각 새 창)
echo [4/4] 서버 켜는 중...
echo.

start "LifeRoad 백엔드" .venv\Scripts\uvicorn.exe backend.main:app --host 0.0.0.0 --port 8001
start "LifeRoad 프론트" .venv\Scripts\python.exe -m http.server 8000 -d web

REM 백엔드 기동 대기 후 브라우저 자동 열기
timeout /t 3 /nobreak >nul
start "" "http://localhost:8000/"

echo.
echo =============================================
echo   준비 완료. 브라우저가 자동으로 열립니다.
echo   안 열리면 직접 여세요:  http://localhost:8000/
echo.
echo   끄기: 새로 뜬 서버 창 2개를 닫으세요.
echo =============================================
echo.
pause
