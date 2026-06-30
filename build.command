#!/bin/bash
# 연구설계 챗봇 빌드 + 배포본 자동 동기화
# 더블클릭하거나 터미널에서 실행하면: 앱을 빌드하고 그 결과를
# 상위 폴더의 '연구설계챗봇(Mac앱).app' 으로 자동 교체한다.
set -e
cd "$(dirname "$0")"

PYI="$HOME/rc-venv/bin/pyinstaller"
TARGET="../연구설계챗봇(Mac앱).app"

if [ ! -x "$PYI" ]; then
  echo "❌ PyInstaller를 찾을 수 없습니다: $PYI"
  echo "   가상환경(~/rc-venv)이 설치되어 있는지 확인하세요."
  exit 1
fi

echo "▶ 실행 중인 앱 종료..."
pkill -f "ResearchChatbot" 2>/dev/null || true
sleep 1

echo "▶ 빌드 시작 (PyMuPDF 포함)..."
"$PYI" --noconfirm --windowed --name ResearchChatbot --collect-all pymupdf app.py

echo "▶ 배포본 동기화..."
if [ ! -d "dist/ResearchChatbot.app" ]; then
  echo "❌ 빌드 결과(dist/ResearchChatbot.app)가 없습니다. 빌드 실패."
  exit 1
fi
rm -rf "$TARGET"
cp -R "dist/ResearchChatbot.app" "$TARGET"

echo "✅ 완료 — 배포본이 최신으로 갱신되었습니다:"
echo "   $(cd .. && pwd)/연구설계챗봇(Mac앱).app"
