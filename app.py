# -*- coding: utf-8 -*-
"""
app.py — 사회과학 연구설계 챗봇 (데스크탑 앱)
NVIDIA 무료 API + 모래시계 연구 로직. 터미널 느낌의 플로팅 채팅창.
각 사용자가 본인의 무료 NVIDIA 키를 입력해 사용한다(키는 본인 컴퓨터에만 저장).

실행: python3 app.py
"""

import os
import sys
import json
import queue
import threading
import platform
from datetime import datetime

import tkinter as tk
from tkinter import filedialog, messagebox

import core
import prompts

# ── 데이터 저장 위치 (쓰기 가능한 홈 폴더) ──
DATA_DIR = os.path.expanduser("~/Documents/ResearchChatbot")
OUT_DIR = os.path.join(DATA_DIR, "outputs")
CONV_DIR = os.path.join(DATA_DIR, "conversations")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(CONV_DIR, exist_ok=True)

# ── 색상 (터미널 다크 테마) ──
C_BG = "#0d1117"
C_BG2 = "#161b22"
C_BORDER = "#30363d"
C_TEXT = "#e6edf3"
C_DIM = "#8b949e"
C_GREEN = "#3fb950"
C_BLUE = "#58a6ff"
C_AMBER = "#e3b341"
C_RED = "#f85149"
C_PURPLE = "#bc8cff"

# ── 폰트 (OS별 모노스페이스) ──
if platform.system() == "Darwin":
    MONO = "Menlo"
elif platform.system() == "Windows":
    MONO = "Consolas"
else:
    MONO = "DejaVu Sans Mono"

# ── 키 발급 온보딩 안내문 ──
GUIDE_STEPS = [
    "① 웹브라우저에서  build.nvidia.com  접속",
    "② 우측 상단 Login → 구글/이메일로 로그인 (계정 가입 절차 최소)",
    "③ 빨간 줄이 보이면 Verify(계정 인증) 클릭",
    "④ 아무 모델이나 열기 (예: deepseek 검색)",
    "⑤ Build 탭 → Generate API Key 클릭",
    "⑥ 만들어진  nvapi-...  키를 Copy",
    "⑦ 아래 칸에 붙여넣고 [저장하고 시작]",
]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("연구설계 챗봇")
        self.configure(bg=C_BG)
        self.geometry("460x620")
        self.minsize(380, 480)
        self.attributes("-topmost", True)  # 항상 위 (위젯 느낌)
        self.pinned = True

        self.mode = "design"
        self.model_key = "deepseek"
        self.history = []
        self.client = None
        self.q = queue.Queue()
        self.streaming = False

        key = core.load_key()
        if core.valid_key_format(key):
            self.client = core.make_client(key)
            self.build_main()
        else:
            self.build_onboarding()

        self.setup_hotkey()

    # ════════ 온보딩 (키 입력) ════════
    def build_onboarding(self):
        for w in self.winfo_children():
            w.destroy()
        f = tk.Frame(self, bg=C_BG, padx=22, pady=20)
        f.pack(fill="both", expand=True)

        tk.Label(f, text="사회과학 연구설계 챗봇", bg=C_BG, fg=C_GREEN,
                 font=(MONO, 16, "bold")).pack(anchor="w")
        tk.Label(f, text="NVIDIA 무료 API 기반 · 본인 키로 작동",
                 bg=C_BG, fg=C_DIM, font=(MONO, 10)).pack(anchor="w", pady=(2, 14))

        tk.Label(f, text="무료 API 키 발급 방법", bg=C_BG, fg=C_BLUE,
                 font=(MONO, 11, "bold")).pack(anchor="w")
        for s in GUIDE_STEPS:
            tk.Label(f, text=s, bg=C_BG, fg=C_TEXT, font=(MONO, 10),
                     justify="left", wraplength=400).pack(anchor="w", pady=1)

        tk.Label(f, text="\nNVIDIA API 키 붙여넣기:", bg=C_BG, fg=C_TEXT,
                 font=(MONO, 10, "bold")).pack(anchor="w")
        self.key_entry = tk.Entry(f, bg=C_BG2, fg=C_TEXT, insertbackground=C_TEXT,
                                  font=(MONO, 11), relief="flat", width=44)
        self.key_entry.pack(fill="x", ipady=6, pady=(4, 4))
        tk.Label(f, text="🔒 이 키는 당신 컴퓨터에만 저장되며 외부로 전송되지 않습니다.",
                 bg=C_BG, fg=C_DIM, font=(MONO, 9)).pack(anchor="w")

        tk.Button(f, text="저장하고 시작", command=self.save_and_start,
                  bg=C_GREEN, fg="#0d1117", font=(MONO, 12, "bold"),
                  relief="flat", activebackground="#2ea043",
                  cursor="hand2").pack(fill="x", ipady=8, pady=(14, 4))

        link = tk.Label(f, text="↗ build.nvidia.com 열기", bg=C_BG, fg=C_BLUE,
                        font=(MONO, 10, "underline"), cursor="hand2")
        link.pack(anchor="w")
        link.bind("<Button-1>", lambda e: self.open_url("https://build.nvidia.com"))

    def save_and_start(self):
        key = self.key_entry.get().strip()
        if not core.valid_key_format(key):
            messagebox.showerror("키 형식 오류",
                                 "키는 nvapi- 로 시작하는 영문/숫자여야 합니다.\n"
                                 "한글이나 빈칸이 섞이지 않았는지 확인하세요.")
            return
        core.save_key(key)
        self.client = core.make_client(key)
        self.build_main()

    def open_url(self, url):
        import webbrowser
        webbrowser.open(url)

    # ════════ 메인 채팅 화면 ════════
    def build_main(self):
        for w in self.winfo_children():
            w.destroy()

        # 상단 툴바
        bar = tk.Frame(self, bg=C_BG2, height=40)
        bar.pack(fill="x")
        self.mode_btn = self._toolbtn(bar, self._mode_label(), self.cycle_mode)
        self.model_btn = self._toolbtn(bar, self._model_label(), self.cycle_model)
        self._toolbtn(bar, "📎", self.attach_file, w=3)
        self._toolbtn(bar, "💾", self.save_conv, w=3)
        self._toolbtn(bar, "📂", self.load_conv, w=3)
        self.pin_btn = self._toolbtn(bar, "📌", self.toggle_pin, w=3)
        self._toolbtn(bar, "❓", self.show_help, w=3)
        self._toolbtn(bar, "🔑", self.change_key, w=3)

        # 대화 영역
        wrap = tk.Frame(self, bg=C_BG)
        wrap.pack(fill="both", expand=True)
        self.chat = tk.Text(wrap, bg=C_BG, fg=C_TEXT, font=(MONO, 11),
                            wrap="word", relief="flat", padx=12, pady=10,
                            insertbackground=C_TEXT, state="disabled",
                            spacing1=2, spacing3=4)
        sb = tk.Scrollbar(wrap, command=self.chat.yview, troughcolor=C_BG2)
        self.chat.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.chat.pack(side="left", fill="both", expand=True)

        self.chat.tag_config("user", foreground=C_BLUE, font=(MONO, 11, "bold"))
        self.chat.tag_config("bot", foreground=C_TEXT)
        self.chat.tag_config("sys", foreground=C_DIM, font=(MONO, 10))
        self.chat.tag_config("warn", foreground=C_AMBER, font=(MONO, 10))
        self.chat.tag_config("err", foreground=C_RED)
        self.chat.tag_config("label", foreground=C_GREEN, font=(MONO, 10, "bold"))

        # 입력 영역
        ibar = tk.Frame(self, bg=C_BG2)
        ibar.pack(fill="x")
        self.inp = tk.Text(ibar, bg=C_BG2, fg=C_TEXT, font=(MONO, 11), height=3,
                          wrap="word", relief="flat", padx=10, pady=8,
                          insertbackground=C_TEXT)
        self.inp.pack(side="left", fill="both", expand=True)
        self.inp.bind("<Return>", self.on_return)
        self.inp.bind("<Shift-Return>", lambda e: None)
        self.send_btn = tk.Button(ibar, text="보내기", command=self.send,
                                  bg=C_GREEN, fg="#0d1117", font=(MONO, 11, "bold"),
                                  relief="flat", activebackground="#2ea043",
                                  cursor="hand2", width=6)
        self.send_btn.pack(side="right", fill="y", padx=(4, 6), pady=6)

        self._sys(f"준비 완료. 모드: {prompts.MODE_LABELS[self.mode]} · "
                  f"모델: {core.MODEL_LABELS[self.model_key]}")
        self._sys("연구 아이디어를 입력하거나 📎로 초안을 첨부하세요. (Enter 전송 / Shift+Enter 줄바꿈)")
        self.inp.focus_set()

    def _toolbtn(self, parent, text, cmd, w=None):
        b = tk.Button(parent, text=text, command=cmd, bg=C_BG2, fg=C_TEXT,
                      font=(MONO, 10), relief="flat", activebackground=C_BORDER,
                      activeforeground=C_TEXT, cursor="hand2", bd=0,
                      padx=8, pady=8)
        if w:
            b.configure(width=w)
        b.pack(side="left", padx=1, pady=2)
        return b

    def _mode_label(self):
        return f"모드:{prompts.MODE_LABELS[self.mode]}▾"

    def _model_label(self):
        short = "DeepSeek" if self.model_key == "deepseek" else "Nemotron"
        return f"모델:{short}▾"

    # ════════ 토글/명령 ════════
    def cycle_mode(self):
        order = ["design", "review", "chat"]
        self.mode = order[(order.index(self.mode) + 1) % 3]
        self.mode_btn.configure(text=self._mode_label())
        self._sys(f"→ {prompts.MODE_LABELS[self.mode]} 모드")

    def cycle_model(self):
        self.model_key = "nemotron" if self.model_key == "deepseek" else "deepseek"
        self.model_btn.configure(text=self._model_label())
        self._sys(f"→ 모델: {core.MODEL_LABELS[self.model_key]}")
        if self.model_key == "nemotron":
            self._warn("주의: Nemotron은 가끔 한자를 섞습니다. 한자 경고를 확인하세요.")

    def toggle_pin(self):
        self.pinned = not self.pinned
        self.attributes("-topmost", self.pinned)
        self._sys("항상 위: " + ("켜짐 📌" if self.pinned else "꺼짐"))

    def change_key(self):
        if messagebox.askyesno("키 변경", "API 키를 다시 입력하시겠습니까?"):
            self.build_onboarding()

    def show_help(self):
        win = tk.Toplevel(self, bg=C_BG)
        win.title("도움말 — 키 발급 방법")
        win.configure(padx=20, pady=16)
        win.attributes("-topmost", True)
        tk.Label(win, text="무료 NVIDIA API 키 발급 방법", bg=C_BG, fg=C_GREEN,
                 font=(MONO, 13, "bold")).pack(anchor="w", pady=(0, 8))
        for s in GUIDE_STEPS:
            tk.Label(win, text=s, bg=C_BG, fg=C_TEXT, font=(MONO, 10),
                     justify="left", wraplength=420).pack(anchor="w", pady=1)
        tk.Label(win, text="\n명령: 모드/모델 버튼으로 전환, 📎 초안첨부, 💾 저장, 📂 불러오기, 📌 항상위",
                 bg=C_BG, fg=C_DIM, font=(MONO, 9), wraplength=420,
                 justify="left").pack(anchor="w")

    def attach_file(self):
        path = filedialog.askopenfilename(
            title="검토할 초안 선택",
            filetypes=[("문서", "*.txt *.md *.pdf *.docx *.hwpx *.hwp *.xlsx"), ("모든 파일", "*.*")])
        if not path:
            return
        content, err = core.read_file(path)
        if err:
            self._warn(err)
            return
        self.mode = "review"
        self.mode_btn.configure(text=self._mode_label())
        self._sys(f"📎 {os.path.basename(path)} ({len(content)}자) 읽음 → 검토 모드")
        self._dispatch(f"다음 원고를 검토해줘:\n\n{content}",
                       display=f"[첨부] {os.path.basename(path)} 검토 요청")

    # ════════ 대화 저장/불러오기 ════════
    def save_conv(self):
        if not self.history:
            self._sys("저장할 대화가 없습니다."); return
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        path = os.path.join(CONV_DIR, f"conv_{ts}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)
        self._sys(f"💾 저장됨: {path}")

    def load_conv(self):
        path = filedialog.askopenfilename(initialdir=CONV_DIR, title="대화 불러오기",
                                          filetypes=[("대화", "*.json")])
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            self.history = json.load(f)
        self.chat.configure(state="normal"); self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        for m in self.history:
            if m["role"] == "user":
                self._append("\n나 ▸ ", "user"); self._append(m["content"] + "\n", "bot")
            else:
                self._append("\nAI ▸\n", "label"); self._append(m["content"] + "\n", "bot")
        self._sys(f"📂 불러옴 (메시지 {len(self.history)}개)")

    # ════════ 전송/스트리밍 ════════
    def on_return(self, event):
        self.send()
        return "break"

    def send(self):
        text = self.inp.get("1.0", "end").strip()
        if not text or self.streaming:
            return
        self.inp.delete("1.0", "end")
        self._dispatch(text)

    def _dispatch(self, content, display=None):
        self._append("\n나 ▸ ", "user")
        self._append((display or content) + "\n", "bot")
        self.history.append({"role": "user", "content": content})
        self.streaming = True
        self.send_btn.configure(state="disabled", text="...")
        self._append("\nAI ▸\n", "label")
        self._answer_acc = []
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()
        self.after(40, self._poll)

    def _worker(self):
        for piece in core.stream_answer(self.client, self.model_key, self.mode, self.history):
            if isinstance(piece, tuple) and piece[0] == "__error__":
                self.q.put(("err", piece[1]))
            else:
                self.q.put(("chunk", piece))
        self.q.put(("done", None))

    def _poll(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "chunk":
                    self._answer_acc.append(data)
                    self._append(data, "bot")
                elif kind == "err":
                    self._append(f"\n⚠️ 오류: {data}\n", "err")
                elif kind == "done":
                    self._finish()
                    return
        except queue.Empty:
            pass
        if self.streaming:
            self.after(40, self._poll)

    def _finish(self):
        self.streaming = False
        self.send_btn.configure(state="normal", text="보내기")
        answer = "".join(self._answer_acc)
        if not answer:
            return
        self.history.append({"role": "assistant", "content": answer})

        # 인용 경고 (설계·검토)
        if self.mode in ("design", "review"):
            self._append(prompts.CITATION_NOTE + "\n", "warn")

        # 한자/가나 검사
        cjk = core.check_cjk(answer)
        if cjk:
            self._append("\n⚠️ 한자/가나 의심 문자 발견 (한글 교체 권장):\n", "warn")
            for item in cjk[:10]:
                self._append("   " + item + "\n", "warn")
            if len(cjk) > 10:
                self._append(f"   …외 {len(cjk) - 10}개\n", "warn")

        # 설계·검토 자동 저장
        if self.mode in ("design", "review"):
            ts = datetime.now().strftime("%Y-%m-%d_%H%M")
            label = prompts.MODE_LABELS[self.mode]
            path = os.path.join(OUT_DIR, f"{ts}_{label}.md")
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"# [{label}] {ts}\n\n{answer}\n")
                self._sys(f"📄 저장됨: {path}")
            except Exception:
                pass

    # ════════ 출력 헬퍼 ════════
    def _append(self, text, tag):
        self.chat.configure(state="normal")
        self.chat.insert("end", text, tag)
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _sys(self, text):
        self._append("\n· " + text + "\n", "sys")

    def _warn(self, text):
        self._append("\n⚠️ " + text + "\n", "warn")

    # ════════ 전역 단축키 (선택) ════════
    def setup_hotkey(self):
        try:
            from pynput import keyboard
        except Exception:
            return  # pynput 없으면 단축키 비활성 (앱은 정상 작동)

        def toggle():
            self.after(0, self._toggle_window)

        try:
            combo = "<cmd>+<shift>+r" if platform.system() == "Darwin" else "<ctrl>+<shift>+r"
            self._hk = keyboard.GlobalHotKeys({combo: toggle})
            self._hk.daemon = True
            self._hk.start()
        except Exception:
            pass

    def _toggle_window(self):
        if self.state() == "withdrawn" or not self.winfo_viewable():
            self.deiconify(); self.lift(); self.focus_force()
        else:
            self.withdraw()


if __name__ == "__main__":
    App().mainloop()
