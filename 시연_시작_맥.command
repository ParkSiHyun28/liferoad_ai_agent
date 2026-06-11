#!/bin/bash
# ============================================================
#  My LifeRoad 시연 시작 (macOS)
#  더블클릭하면: 파이썬 확인 → 가상환경 + 패키지 설치 → 서버 2개 → 브라우저 자동 열기
#  끄려면: 이 터미널 창에서 Ctrl+C 또는 창 닫기
# ============================================================

cd "$(dirname "$0")"

echo "============================================="
echo "   My LifeRoad 시연 서버 (macOS)"
echo "============================================="
echo ""

# 1) 파이썬 찾기 (python3 우선)
PYBIN=""
if command -v python3 >/dev/null 2>&1; then
  PYBIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYBIN="python"
fi

if [ -z "$PYBIN" ]; then
  echo "[오류] 파이썬이 설치돼 있지 않습니다."
  echo ""
  echo "  아래 주소에서 Python 3.12를 설치한 뒤 이 파일을 다시 실행하세요:"
  echo "  https://www.python.org/downloads/"
  echo ""
  echo "  (창을 닫으려면 아무 키나 누르세요)"
  read -n 1 -s
  exit 1
fi

echo "[1/4] 파이썬 확인: $($PYBIN --version)"

# 2) 가상환경 (없으면 생성)
if [ ! -d ".venv" ]; then
  echo "[2/4] 가상환경 만드는 중... (처음 한 번만, 잠시 걸립니다)"
  "$PYBIN" -m venv .venv
  if [ $? -ne 0 ]; then
    echo "[오류] 가상환경 생성 실패. 위 파이썬 버전을 확인하세요."
    read -n 1 -s
    exit 1
  fi
else
  echo "[2/4] 가상환경 확인 완료"
fi

# 3) 패키지 설치 (이미 설치돼 있으면 빠르게 넘어감)
echo "[3/4] 필요한 패키지 확인/설치 중... (처음엔 1~3분 걸릴 수 있습니다)"
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt
if [ $? -ne 0 ]; then
  echo "[오류] 패키지 설치 실패. 인터넷 연결을 확인하세요."
  read -n 1 -s
  exit 1
fi

# 4) 서버 2개 띄우기
echo "[4/4] 서버 켜는 중..."
echo ""

.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8001 &
BACK_PID=$!

.venv/bin/python -m http.server 8000 -d web &
FRONT_PID=$!

# 창 닫으면 두 서버 같이 정리
trap "kill $BACK_PID $FRONT_PID 2>/dev/null" EXIT

# 백엔드 기동 대기 후 브라우저 자동 열기
sleep 3
open "http://localhost:8000/"

echo ""
echo "============================================="
echo "  준비 완료. 브라우저가 자동으로 열립니다."
echo "  안 열리면 직접 여세요:  http://localhost:8000/"
echo ""
echo "  끄기: 이 창에서 Ctrl+C 또는 창 닫기"
echo "============================================="
echo ""

wait
