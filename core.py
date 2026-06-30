# -*- coding: utf-8 -*-
"""
core.py — 사회과학 연구설계 챗봇의 공통 엔진 (터미널·GUI 공용)
모델 호출(스트리밍)·한자 검사·파일 읽기·키 저장/로드를 담당한다.
개발자 키를 하드코딩하지 않는다. 사용자가 입력한 키만 사용한다.
"""

import os
import json
import subprocess

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


# ── 모델 호출 (스트리밍 제너레이터) ──
def stream_answer(client, model_key, mode, history):
    """history를 보내 답변 청크를 하나씩 yield 한다. 오류 시 ('__error__', 메시지) yield."""
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
    try:
        stream = client.chat.completions.create(**kwargs)
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception as e:
        yield ("__error__", str(e))
