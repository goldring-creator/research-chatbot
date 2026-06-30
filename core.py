# -*- coding: utf-8 -*-
"""
core.py — 사회과학 연구설계 챗봇의 공통 엔진 (터미널·GUI 공용)
모델 호출(스트리밍)·한자 검사·파일 읽기·키 저장/로드를 담당한다.
개발자 키를 하드코딩하지 않는다. 사용자가 입력한 키만 사용한다.
"""

import os
import json
import time
import base64
import subprocess
import urllib.request
import urllib.error

from openai import OpenAI
import prompts

# ── 설정(키) 저장 위치: 사용자 홈 폴더 ──
CONFIG_PATH = os.path.expanduser("~/.research-assistant.json")

# ── 모델 ──
MODELS = {
    "deepseek": "deepseek-ai/deepseek-v4-pro",
    "nemotron": "nvidia/llama-3.3-nemotron-super-49b-v1",
}
MODEL_LABELS = {
    "deepseek": "DeepSeek V4 Pro (정밀)",
    "nemotron": "Nemotron 49B (빠름)",
}

BASE_URL = "https://integrate.api.nvidia.com/v1"

# 읽기 지원 형식 (앱 각주 표시용)
SUPPORTED_NOTE = "읽기 지원: PDF · Word(.docx) · 텍스트(.txt /.md)   ·   한글(.hwp /.hwpx)은 지원 제한"


# ── 키 저장/로드 ──
def load_key() -> str:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f).get("api_key", "")
        except Exception:
            return ""
    return ""


def save_key(key: str):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"api_key": key.strip()}, f, ensure_ascii=False)


def valid_key_format(key: str) -> bool:
    key = (key or "").strip()
    return key.startswith("nvapi-") and len(key) > 20 and key.isascii()


def make_client(key: str) -> OpenAI:
    return OpenAI(base_url=BASE_URL, api_key=key.strip())


# ── 한자/가나 오염 검사 ──
def check_cjk(text: str) -> list:
    """한자(U+4E00–9FFF)·가나(U+3040–30FF) 의심 문자를 찾는다."""
    found = []
    for i, ch in enumerate(text):
        code = ord(ch)
        if 0x4E00 <= code <= 0x9FFF or 0x3040 <= code <= 0x30FF:
            ctx = text[max(0, i - 6):i + 6].replace("\n", " ")
            found.append(f"'{ch}'(U+{code:04X}) …{ctx}…")
    return found


# ── 파일 → 텍스트 (내장 파서: pypdf / python-docx) ──
def read_file(path: str):
    path = os.path.expanduser(path.strip().strip('"').strip("'"))
    if not os.path.exists(path):
        return None, f"파일을 찾을 수 없습니다: {os.path.basename(path)}"
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".txt", ".md"):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read(), None
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(path)
            text = "\n".join((p.extract_text() or "") for p in reader.pages).strip()
            if not text:
                return None, "이미지로 스캔된 PDF로 보입니다 — 텍스트를 추출할 수 없습니다."
            return text, None
        if ext == ".docx":
            import docx
            d = docx.Document(path)
            return "\n".join(p.text for p in d.paragraphs), None
        if ext in (".hwp", ".hwpx"):
            return None, ("한글 파일(.hwp/.hwpx)은 현재 지원되지 않습니다. "
                          "한글에서 'PDF로 저장' 후 PDF를 첨부해 주세요.")
        return None, f"지원하지 않는 형식입니다: {ext} (PDF·docx·txt·md만 가능)"
    except Exception as e:
        return None, f"파일 읽기 오류: {e}"


# ── OCR (스캔 PDF·이미지 → 텍스트) : NVIDIA nemotron-ocr-v2 ──
OCR_URL = "https://ai.api.nvidia.com/v1/cv/nvidia/nemotron-ocr-v2"
OCR_MAX_PAGES = 30                       # 한 번에 OCR 처리할 최대 쪽수(속도제한 보호)
OCR_PAGE_GAP = 1.6                       # 페이지 간 간격(초) — 분당 40회 제한 회피
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif")


def _load_fitz():
    """PyMuPDF 모듈을 불러온다(신 이름 pymupdf 우선, 구 이름 fitz 대체). 없으면 None.
    PyInstaller 번들에서는 보통 'pymupdf'만 포함되므로 이 이름을 먼저 시도한다."""
    try:
        import pymupdf
        return pymupdf
    except Exception:
        try:
            import fitz
            return fitz
        except Exception:
            return None


def ocr_image_bytes(key: str, img_bytes: bytes):
    """이미지 한 장(PNG/JPEG bytes)을 OCR 모델에 보내 텍스트를 추출한다. (text, err) 반환."""
    b64 = base64.b64encode(img_bytes).decode()
    body = {"input": [{"type": "image_url", "url": f"data:image/png;base64,{b64}"}]}
    req = urllib.request.Request(
        OCR_URL, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key.strip()}",
                 "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "ignore")
        except Exception:
            detail = ""
        return None, f"OCR 오류 {e.code}: {detail[:200]}"
    except Exception as e:
        return None, f"OCR 연결 오류: {e}"

    # 응답 파싱 — 읽기 순서(위→아래, 왼→오른)로 정렬해 줄을 잇는다
    lines = []
    for item in data.get("data", []):
        dets = item.get("text_detections", [])

        def order(d):
            pts = d.get("bounding_box", {}).get("points", [])
            ys = [p.get("y", 0) for p in pts] or [0]
            xs = [p.get("x", 0) for p in pts] or [0]
            return (round(min(ys), 2), min(xs))

        for d in sorted(dets, key=order):
            t = d.get("text_prediction", {}).get("text", "")
            if t:
                lines.append(t)
    return "\n".join(lines), None


def _render_under_limit(page, limit=170000) -> bytes:
    """fitz 페이지(또는 이미지)를 회색조 PNG로 렌더링하되, 용량 한도 안에 들도록 해상도를 낮춘다."""
    fitz = _load_fitz()
    last = None
    for dpi in (220, 170, 130, 100, 75):
        pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        last = pix.tobytes("png")
        if len(last) <= limit:
            return last
    return last


def read_file_ocr(path: str, key: str, progress=None, should_cancel=None):
    """텍스트 추출을 시도하고, 스캔 PDF·이미지면 OCR로 자동 전환한다. (text, err) 반환.
    progress(msg): 진행 안내 콜백, should_cancel(): True면 중단."""
    path = os.path.expanduser(path.strip().strip('"').strip("'"))
    if not os.path.exists(path):
        return None, f"파일을 찾을 수 없습니다: {os.path.basename(path)}"
    ext = os.path.splitext(path)[1].lower()

    # 1) 이미지 파일 → 바로 OCR
    if ext in IMAGE_EXTS:
        fitz = _load_fitz()
        if fitz is None:
            return None, "이미지 OCR 구성요소(PyMuPDF)가 설치되어 있지 않습니다."
        if progress:
            progress("이미지 OCR 처리 중…")
        try:
            doc = fitz.open(path)
            img = _render_under_limit(doc.load_page(0))
        except Exception as e:
            return None, f"이미지 열기 오류: {e}"
        text, err = ocr_image_bytes(key, img)
        if err:
            return None, err
        if not (text or "").strip():
            return None, "이미지에서 글자를 찾지 못했습니다."
        return text, None

    # 2) PDF → 일반 텍스트 우선, 비어 있으면(스캔본) OCR
    if ext == ".pdf":
        text, _err = read_file(path)
        if text and text.strip():
            return text, None          # 일반(텍스트) PDF — OCR 불필요
        return _ocr_pdf(path, key, progress, should_cancel)

    # 3) 그 외(txt·md·docx·hwp) → 기존 처리
    return read_file(path)


def _ocr_pdf(path, key, progress=None, should_cancel=None):
    fitz = _load_fitz()
    if fitz is None:
        return None, "스캔 PDF OCR 구성요소(PyMuPDF)가 설치되어 있지 않습니다."
    try:
        doc = fitz.open(path)
        total = doc.page_count
    except Exception as e:
        return None, f"PDF 열기 오류: {e}"

    pages = min(total, OCR_MAX_PAGES)
    out = []
    for i in range(pages):
        if should_cancel and should_cancel():
            return None, "사용자가 중지했습니다."
        if progress:
            progress(f"스캔 문서 OCR 처리 중… ({i + 1}/{pages}쪽)")
        try:
            img = _render_under_limit(doc.load_page(i))
        except Exception as e:
            return None, f"{i + 1}쪽 렌더링 오류: {e}"
        text, err = ocr_image_bytes(key, img)
        if err and _is_rate_limit(err):          # 429면 한 번 쉬고 재시도
            time.sleep(20)
            text, err = ocr_image_bytes(key, img)
        if err:
            return None, err
        if text:
            out.append(text)
        if i < pages - 1:
            time.sleep(OCR_PAGE_GAP)              # 분당 40회 제한 회피

    result = "\n\n".join(out).strip()
    if not result:
        return None, "OCR로 텍스트를 추출하지 못했습니다."
    if total > pages:
        result += f"\n\n[안내: 분량이 많아 처음 {pages}쪽만 OCR 처리했습니다. (전체 {total}쪽)]"
    return result, None


# ── 오류 메시지 한글 변환 ──
def friendly_error(raw: str) -> str:
    """API 원문 오류(영어)를 사용자용 한글 안내 한 줄로 바꾼다.
    알 수 없는 오류는 짧은 한글 안내 + 원문을 함께 보여준다."""
    s = str(raw)
    low = s.lower()
    if "429" in s or "too many requests" in low:
        return "요청이 잠시 많아 한도(분당 40회)에 걸렸습니다. 1분쯤 기다린 뒤 다시 보내 주세요."
    if "401" in s or "unauthorized" in low or "invalid api key" in low:
        return "API 키가 올바르지 않거나 만료되었습니다. 우측 상단 열쇠 버튼에서 키를 다시 입력해 주세요."
    if "403" in s or "forbidden" in low:
        return "이 키로는 해당 모델에 접근할 수 없습니다. NVIDIA 계정의 키 권한을 확인해 주세요."
    if "404" in s or "not found" in low:
        return "모델을 찾을 수 없습니다. 모델 이름이 바뀌었거나 종료되었을 수 있습니다."
    if "500" in s or "502" in s or "503" in s or "internal server" in low or "service unavailable" in low:
        return "NVIDIA 서버가 일시적으로 불안정합니다. 잠시 후 다시 시도해 주세요."
    if "timeout" in low or "timed out" in low:
        return "응답 시간이 초과되었습니다. 네트워크를 확인하고 다시 시도해 주세요."
    if "connection" in low or "network" in low or "getaddrinfo" in low:
        return "인터넷 연결을 확인해 주세요. 네트워크에 연결되지 않은 것 같습니다."
    # 알 수 없는 오류: 한글 안내 + 원문 일부
    return f"문제가 발생했습니다. 잠시 후 다시 시도해 주세요. (상세: {s[:120]})"


# ── 429(요청 과다) 자동 재시도 대기 시간(초) — 단계별로 늘린다 ──
RETRY_WAITS = [15, 30, 60]


def _is_rate_limit(msg: str) -> bool:
    low = str(msg).lower()
    return "429" in str(msg) or "too many requests" in low


def _interruptible_sleep(seconds, should_cancel):
    """초 단위 대기. should_cancel()이 True가 되면 즉시 중단하고 False를 반환."""
    for _ in range(int(seconds * 10)):
        if should_cancel and should_cancel():
            return False
        time.sleep(0.1)
    return True


# ── 모델 호출 (스트리밍 제너레이터) ──
def stream_answer(client, model_key, mode, history, should_cancel=None):
    """history를 보내 답변 청크를 하나씩 yield 한다. 오류 시 ('__error__', 메시지) yield.
    429(요청 과다)는 자동으로 최대 3회 재시도하며, 그때마다 ('__retry__', 대기초, 회차, 총회차)를 yield 한다.
    should_cancel()가 True를 반환하면 스트림을 닫고 즉시 멈춘다(사용자 중지)."""
    system = prompts.build_system(mode)
    messages = [{"role": "system", "content": system}] + history
    kwargs = dict(
        model=MODELS[model_key],
        messages=messages,
        temperature=0.5,
        top_p=0.95,
        max_tokens=8192,
        stream=True,
    )
    # DeepSeek은 내부 추론(thinking)을 끄면 첫 응답이 빨라진다
    if model_key == "deepseek":
        kwargs["extra_body"] = {"chat_template_kwargs": {"thinking": False}}

    max_retries = len(RETRY_WAITS)
    attempt = 0
    while True:
        got_chunk = False
        try:
            stream = client.chat.completions.create(**kwargs)
            for chunk in stream:
                if should_cancel and should_cancel():   # 사용자가 중지 → 스트림 종료
                    stream.close()
                    return
                delta = chunk.choices[0].delta.content
                if delta:
                    got_chunk = True
                    yield delta
            return   # 정상 종료
        except Exception as e:
            msg = str(e)
            # 429이고, 아직 답변이 시작되지 않았고, 재시도 여유가 있으면 자동 재시도
            if _is_rate_limit(msg) and not got_chunk and attempt < max_retries:
                wait = RETRY_WAITS[attempt]
                attempt += 1
                yield ("__retry__", wait, attempt, max_retries)
                if not _interruptible_sleep(wait, should_cancel):
                    return   # 대기 중 사용자가 중지
                continue
            yield ("__error__", msg)
            return
