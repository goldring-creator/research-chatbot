# 사회과학 연구설계 챗봇 🧭

NVIDIA가 무료로 공개한 고성능 AI 모델(DeepSeek V4 Pro 등)에, **사회과학 논문의
모래시계(IMRaD) 연구 로직**을 탑재한 데스크탑 채팅 앱입니다. 바탕화면에 떠 있는 작은
창에서 연구설계 도움을 받고, 초안을 검토할 수 있습니다.

- 💸 **완전 무료** — NVIDIA 무료 API 사용 (분당 약 40회 제한)
- 🔒 **본인 키로 작동** — 각자 본인의 무료 키를 입력하며, 키는 **본인 컴퓨터에만** 저장됩니다
- 🧠 **연구 로직 내장** — 서론 4단계 · 이론적 틀 · 방법 · 결과 · 논의 6단계 · 사회과학 조정
- 🛡️ **안전장치** — 한자 오염 자동 검사, 인용 환각 경고

---

## 설치 (받는 사람용)

1. [Releases](../../releases) 에서 본인 OS용 파일을 다운로드
   - **Mac**: `ResearchChatbot-mac.zip`
   - **Windows**: `ResearchChatbot-windows.zip`
2. 압축을 풀고 앱 실행
   - **Mac**: 처음엔 "확인되지 않은 개발자" 경고 → 앱을 **우클릭 → 열기 → 열기**
   - **Windows**: "Windows의 PC 보호" 경고 → **추가 정보 → 실행**
3. 처음 실행하면 **API 키 입력 화면**이 나옵니다 (아래 방법으로 키 발급)

## 무료 NVIDIA API 키 발급 방법

1. 웹브라우저에서 **build.nvidia.com** 접속
2. 우측 상단 **Login** → 구글/이메일로 로그인
3. 빨간 줄이 보이면 **Verify**(계정 인증) 클릭
4. 아무 모델 열기 (예: `deepseek` 검색)
5. **Build 탭 → Generate API Key** 클릭
6. 만들어진 `nvapi-...` 키를 **Copy**
7. 앱의 입력칸에 **붙여넣고 [저장하고 시작]**

> 키는 비밀번호처럼 다루세요. 남에게 공유하지 마세요.

---

## 사용법

| 버튼 | 기능 |
|------|------|
| 모드 | 설계 / 검토 / 문답 전환 |
| 모델 | DeepSeek(정밀) ↔ Nemotron(빠름) |
| 📎 | 초안 파일 첨부(txt·md·pdf·docx·이미지) → 검토 · 한글(.hwp/.hwpx)은 PDF로 저장 후 첨부 |
| 💾 / 📂 | 대화 저장 / 불러오기 |
| 📌 | 항상 위 켜기/끄기 |
| ❓ / 🔑 | 도움말 / 키 변경 |

- 전송: **Enter** · 줄바꿈: **Shift+Enter**
- 전역 단축키(선택 기능, 기본 꺼짐): 환경변수 `RC_HOTKEY=1` 로 실행하면
  **⌘+Shift+R**(Mac) / **Ctrl+Shift+R**(Win) 으로 창 보이기/숨기기
  (Mac은 시스템 설정 → 개인정보 보호 및 보안 → 입력 모니터링 권한 허용 필요)
- 답변·대화는 `~/Documents/ResearchChatbot/` 에 저장됩니다.
- ℹ️ 질문·첨부한 문서와 이미지 내용은 답변 생성을 위해 NVIDIA API 서버로 전송됩니다.
  민감한 연구 자료(면담 자료, 개인정보 등)는 첨부 전에 익명화해 주세요.

---

## 개발자용 (소스로 실행 / 빌드)

```bash
pip install -r requirements.txt
python3 app.py            # GUI
python3 research_assistant.py   # 터미널 버전
```

빌드(PyInstaller):
```bash
pip install pyinstaller
pyinstaller --noconfirm --windowed --name ResearchChatbot --collect-all pymupdf app.py
```

태그를 push하면 GitHub Actions가 Mac/Windows 빌드를 자동 생성합니다(`.github/workflows/build.yml`).

## 구조
- `prompts.py` — 연구 로직(두뇌)
- `core.py` — 모델 호출·한자검사·파일읽기·키 저장(공통 엔진)
- `app.py` — 데스크탑 GUI
- `research_assistant.py` — 터미널 버전

> ⚠️ 이 저장소에는 어떤 API 키도 포함돼 있지 않습니다. 키는 각 사용자가 직접 입력합니다.
