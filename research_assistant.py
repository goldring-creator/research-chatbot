# -*- coding: utf-8 -*-
"""
research_assistant.py — 사회과학 연구설계 챗봇 (터미널 버전)
GUI(app.py)와 동일한 두뇌(prompts.py)·엔진(core.py)을 쓴다.
키는 환경변수 NVIDIA_API_KEY 또는 저장된 설정(~/.research-assistant.json)에서 읽는다.

실행: python3 research_assistant.py
"""

import os
import sys

import core
import prompts


def get_key():
    key = os.environ.get("NVIDIA_API_KEY") or core.load_key()
    if not core.valid_key_format(key):
        print("⚠️ 유효한 NVIDIA API 키가 없습니다.")
        key = input("nvapi- 로 시작하는 키를 붙여넣으세요: ").strip()
        if not core.valid_key_format(key):
            print("키 형식이 올바르지 않습니다. 종료합니다.")
            sys.exit(1)
        core.save_key(key)
    return key


def main():
    client = core.make_client(get_key())
    mode, model_key, history = "design", "deepseek", []

    print("=" * 56)
    print(" 사회과학 연구설계 챗봇 (터미널)")
    print(f" 모델: {core.MODEL_LABELS[model_key]} | 모드: {prompts.MODE_LABELS[mode]}")
    print(" /설계 /검토 /문답 /모델 /끝")
    print("=" * 56)

    while True:
        try:
            user = input(f"\n[{prompts.MODE_LABELS[mode]}] 입력: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다."); break
        if user in ("", "/끝"):
            print("종료합니다."); break
        if user == "/설계": mode = "design"; print("→ 연구설계"); continue
        if user == "/검토": mode = "review"; print("→ 초안 검토"); continue
        if user == "/문답": mode = "chat"; print("→ 자유 문답"); continue
        if user == "/모델":
            model_key = "nemotron" if model_key == "deepseek" else "deepseek"
            print(f"→ 모델: {core.MODEL_LABELS[model_key]}"); continue

        history.append({"role": "user", "content": user})
        print("\n답변:")
        acc = []
        for piece in core.stream_answer(client, model_key, mode, history):
            if isinstance(piece, tuple) and piece[0] == "__error__":
                print(f"\n⚠️ 오류: {piece[1]}"); break
            print(piece, end="", flush=True); acc.append(piece)
        print()
        answer = "".join(acc)
        if not answer:
            history.pop(); continue
        history.append({"role": "assistant", "content": answer})

        if mode in ("design", "review"):
            print(prompts.CITATION_NOTE)
        cjk = core.check_cjk(answer)
        if cjk:
            print("\n⚠️ 한자/가나 의심 문자:")
            for item in cjk[:10]:
                print("   " + item)


if __name__ == "__main__":
    main()
