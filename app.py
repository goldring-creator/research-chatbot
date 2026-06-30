# -*- coding: utf-8 -*-
"""
app.py — 사회과학 연구설계 챗봇 (데스크탑 앱)
NVIDIA 무료 API + 모래시계 연구 로직. 터미널 느낌의 플로팅 채팅창.
각 사용자가 본인의 무료 NVIDIA 키를 입력해 사용한다(키는 본인 컴퓨터에만 저장).
"""

import os
import re
import json
import queue
import threading
import platform
import webbrowser
from datetime import datetime

import tkinter as tk
from tkinter import filedialog, messagebox

import core
import prompts

# ── 데이터 저장 위치 ──
DATA_DIR = os.path.expanduser("~/Documents/ResearchChatbot")
OUT_DIR = os.path.join(DATA_DIR, "outputs")
CONV_DIR = os.path.join(DATA_DIR, "conversations")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(CONV_DIR, exist_ok=True)

# ── 어두운 테마 + 밝은 테두리 ──
C_BG = "#0d1117"        # 전체 배경(어두움)
C_BG2 = "#161b22"       # 패널(툴바·입력창)
C_BORDER = "#30363d"    # 은은한 구분선
C_LINE = "#cdd5df"      # 카드 테두리(밝은/흰색 느낌)
C_TEXT = "#e6edf3"      # 본문 글자(밝음)
C_DIM = "#8b949e"       # 흐린 글자
C_GREEN = "#3fb950"     # 강조(버튼 배경)
C_GREEN_D = "#2ea043"   # 버튼 hover
C_GREEN_TX = "#3fb950"  # 초록 글자(어두운 배경 위)
C_BLUE = "#58a6ff"
C_AMBER = "#e3b341"
C_RED = "#f85149"
C_HR = "#30363d"

# 폰트: 터미널 느낌의 고정폭
if platform.system() == "Darwin":
    MONO = "Menlo"
elif platform.system() == "Windows":
    MONO = "Consolas"
else:
    MONO = "DejaVu Sans Mono"

NVIDIA_URL = "https://build.nvidia.com"

# ── 모드별 활용 안내 (모드 전환 시 표시) ──
MODE_DESC = {
    "design": [
        "연구 아이디어 → 서론(배경·갭·RQ)·이론적 틀·표집·변수·측정·분석 설계",
        "예상 타당도 위협과 통제 방안 제안",
        "예) \"교사 AI 활용과 직무만족 관계를 연구하고 싶어\"",
    ],
    "review": [
        "초안을 입력하거나 📎로 파일 첨부 → 모래시계 구조로 검토",
        "결과·해석 분리, 논의 6단계, 재현가능성, 인용 점검",
        "예) 📎 내 서론 초안.hwpx 첨부 → 피드백",
    ],
    "chat": [
        "연구방법론·통계·연구설계에 대한 자유 질문",
        "개념 설명, 연구 간 비교, 분석방법 추천 등",
        "예) \"위계적 회귀와 SEM 중 뭐가 적합해?\"",
    ],
}

# ── 버전·업데이트 확인 ──
APP_VERSION = "0.1.7"
REPO = "goldring-creator/research-chatbot"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"

# ── 키 발급 안내 (1) 2) 3) 순서) ──
GUIDE_STEPS = [
    "1)  아래 [NVIDIA 사이트 열기]를 눌러 로그인 (구글·이메일)",
    "2)  화면 위에 Verify가 보이면 눌러 계정 인증",
    "3)  아무 모델이나 열기 (예: 검색창에 deepseek)",
    "4)  Build 탭의 [Generate API Key] 클릭",
    "5)  만들어진  nvapi-...  키를 [Copy]",
    "6)  아래 칸에 붙여넣고 [저장하고 시작]",
]


class _Tooltip:
    """아이콘에 커서를 올리면 설명을 띄운다 (Mac·Windows 공통)."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, e=None):
        if self.tip:
            return
        x = self.widget.winfo_rootx() + 6
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        root = self.widget.winfo_toplevel()
        self.tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        try:
            tw.wm_attributes("-topmost", True)
        except Exception:
            pass
        tk.Label(tw, text=self.text, bg="#1f2630", fg="#e6edf3",
                 font=(MONO, 9), padx=8, pady=4, relief="solid", bd=1).pack()
        tw.wm_geometry(f"+{x}+{y}")
        tw.update_idletasks()

        def raise_tip():
            if not tw.winfo_exists():
                return
            try:
                tw.lift(root)                 # 메인(항상 위) 창 바로 위로 명시적 올림
                tw.wm_attributes("-topmost", True)
            except Exception:
                pass
        raise_tip()
        tw.after(20, raise_tip)               # 창 매니저가 재배치한 뒤 한 번 더

    def hide(self, e=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("연구설계 챗봇")
        self.configure(bg=C_BG)
        self.geometry("640x720")
        self.minsize(600, 560)
        self.attributes("-topmost", True)
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

    # ── 복사·붙여넣기 단축키 활성화 (macOS Tk 보완) ──
    def _enable_clipboard(self, w):
        for mod in ("Command", "Control"):
            w.bind(f"<{mod}-v>", lambda e: (e.widget.event_generate("<<Paste>>"), "break")[1])
            w.bind(f"<{mod}-c>", lambda e: (e.widget.event_generate("<<Copy>>"), "break")[1])
            w.bind(f"<{mod}-x>", lambda e: (e.widget.event_generate("<<Cut>>"), "break")[1])
            w.bind(f"<{mod}-a>", self._select_all)

    def _select_all(self, e):
        w = e.widget
        try:
            w.select_range(0, "end")        # Entry
        except Exception:
            w.tag_add("sel", "1.0", "end-1c")  # Text
        return "break"

    # ── 라벨 기반 버튼 (macOS에서도 색이 제대로 나옴) ──
    def _btn(self, parent, text, cmd, fg=C_TEXT, bg=C_BG2, hover="#21262d",
             font=None, pady=6, padx=10):
        lbl = tk.Label(parent, text=text, fg=fg, bg=bg, cursor="hand2",
                       font=font or (MONO, 10), padx=padx, pady=pady)
        lbl.bind("<Button-1>", lambda e: cmd())
        lbl.bind("<Enter>", lambda e: lbl.configure(bg=hover))
        lbl.bind("<Leave>", lambda e: lbl.configure(bg=bg))
        return lbl

    # ════════ 온보딩 (키 입력) ════════
    def build_onboarding(self):
        for w in self.winfo_children():
            w.destroy()

        outer = tk.Frame(self, bg=C_BG, padx=26, pady=20)
        outer.pack(fill="both", expand=True)

        # 맨 아래: 저장 버튼 (먼저 bottom에 배치)
        bottom = tk.Frame(outer, bg=C_BG)
        bottom.pack(side="bottom", fill="x")
        save_btn = tk.Label(bottom, text="저장하고 시작  ▸", bg=C_GREEN, fg="#0d1117",
                            font=(MONO, 14, "bold"), cursor="hand2", pady=12)
        save_btn.pack(fill="x", pady=(10, 0))
        save_btn.bind("<Button-1>", lambda e: self.save_and_start())
        save_btn.bind("<Enter>", lambda e: save_btn.configure(bg=C_GREEN_D))
        save_btn.bind("<Leave>", lambda e: save_btn.configure(bg=C_GREEN))

        # 위: 제목 + 안내 + 키 입력
        top = tk.Frame(outer, bg=C_BG)
        top.pack(side="top", fill="both", expand=True)

        # 제목 (가운데, 큰 폰트)
        tk.Label(top, text="🧭  사회과학 연구설계 챗봇", bg=C_BG, fg=C_GREEN_TX,
                 font=(MONO, 19, "bold")).pack(pady=(6, 2))
        tk.Label(top, text="NVIDIA 무료 AI · 본인 키로 작동 · 완전 무료",
                 bg=C_BG, fg=C_DIM, font=(MONO, 10)).pack(pady=(0, 16))

        # 키 발급 방법
        tk.Label(top, text="📋  무료 API 키 발급 방법 (약 3분)", bg=C_BG, fg=C_BLUE,
                 font=(MONO, 12, "bold")).pack(anchor="w")
        steps = tk.Frame(top, bg=C_BG2)
        steps.pack(fill="x", pady=(6, 10))
        for s in GUIDE_STEPS:
            tk.Label(steps, text=s, bg=C_BG2, fg=C_TEXT, font=(MONO, 11),
                     justify="left", anchor="w", wraplength=400,
                     padx=12, pady=3).pack(fill="x")

        # NVIDIA 사이트 열기 (하이퍼링크 버튼)
        link = tk.Label(top, text="🔗  NVIDIA 사이트 열기  (build.nvidia.com)",
                        bg=C_BG, fg=C_BLUE, font=(MONO, 11, "underline"),
                        cursor="hand2")
        link.pack(anchor="w", pady=(0, 16))
        link.bind("<Button-1>", lambda e: webbrowser.open(NVIDIA_URL))

        # 키 입력칸
        tk.Label(top, text="🔑  발급받은 API 키 붙여넣기", bg=C_BG, fg=C_TEXT,
                 font=(MONO, 11, "bold")).pack(anchor="w")
        self.key_entry = tk.Entry(top, bg="#ffffff", fg="#1A1A1A",
                                  insertbackground="#1A1A1A", font=(MONO, 12),
                                  relief="flat", highlightthickness=1,
                                  highlightbackground=C_BORDER, highlightcolor=C_BLUE)
        self.key_entry.pack(fill="x", ipady=8, pady=(6, 4))
        self.key_entry.focus_set()
        self._enable_clipboard(self.key_entry)
        tk.Label(top, text="🔒 이 키는 당신 컴퓨터에만 저장되며 외부로 전송되지 않습니다.",
                 bg=C_BG, fg=C_DIM, font=(MONO, 9), wraplength=400,
                 justify="left").pack(anchor="w")

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

    # ════════ 메인 채팅 화면 ════════
    def build_main(self):
        for w in self.winfo_children():
            w.destroy()

        bar = tk.Frame(self, bg=C_BG2)
        bar.pack(fill="x")
        self._toolbar = bar
        left = tk.Frame(bar, bg=C_BG2)
        left.pack(side="left", padx=8, pady=6)
        right = tk.Frame(bar, bg=C_BG2)
        right.pack(side="right", padx=8, pady=6)

        # 좌측: 모드 / 모델
        self.mode_btn = self._btn(left, self._mode_label(), self.open_mode_menu, fg=C_GREEN_TX)
        self.mode_btn.pack(side="left", padx=4)
        _Tooltip(self.mode_btn, "모드 선택 — 클릭하면 설계 / 검토 / 자유문답 목록이 열립니다")

        # 우측: 아이콘 (균등 간격)
        for txt, cmd, tip in [
            ("📎", self.attach_file, "파일 첨부(여러 개 가능) — 초안을 검토 모드로 분석"),
            ("📤", self.export_html, "지금까지 내용을 정돈된 HTML로 자동 생성·저장"),
            ("💾", self.save_conv, "현재 대화 저장"),
            ("📂", self.load_conv, "저장한 대화 불러오기"),
            ("📌", self.toggle_pin, "항상 위에 고정 켜기/끄기"),
            ("🔑", self.change_key, "API 키 변경"),
        ]:
            b = self._btn(right, txt, cmd, padx=9)
            b.pack(side="left", padx=5)
            _Tooltip(b, tip)
        tk.Frame(self, bg=C_BORDER, height=1).pack(side="top", fill="x")  # 툴바 구분선

        # 각주: 읽기 지원 형식 (맨 아래)
        foot = tk.Label(self, text="📎 " + core.SUPPORTED_NOTE, bg=C_BG, fg=C_DIM,
                        font=(MONO, 9))
        foot.pack(side="bottom", fill="x", pady=(0, 6))

        # 입력 영역 — 맨 아래 고정 + 안쪽 카드(밝은 테두리)
        ibar_outer = tk.Frame(self, bg=C_BG)
        ibar_outer.pack(side="bottom", fill="x", padx=10, pady=(4, 0))
        ibar = tk.Frame(ibar_outer, bg=C_BG2, highlightthickness=1,
                        highlightbackground=C_LINE, highlightcolor=C_LINE, bd=0)
        ibar.pack(fill="x")
        # 보내기 버튼을 먼저 오른쪽에 예약 → 좁아져도 안 잘림
        self.send_btn = tk.Label(ibar, text="보내기", bg=C_GREEN, fg="#0d1117",
                                 font=(MONO, 11, "bold"), cursor="hand2", padx=14)
        self.send_btn.pack(side="right", fill="y", padx=(4, 6), pady=6)
        self.send_btn.bind("<Button-1>", lambda e: self.send())
        tk.Label(ibar, text=" 입력 ▸", bg=C_BG2, fg=C_GREEN_TX,
                 font=(MONO, 11, "bold")).pack(side="left", anchor="n", pady=12)
        self.inp = tk.Text(ibar, bg=C_BG2, fg=C_TEXT, font=(MONO, 11), height=3,
                          wrap="word", relief="flat", bd=0, padx=6, pady=8,
                          insertbackground=C_TEXT)
        self.inp.pack(side="left", fill="both", expand=True)
        self.inp.bind("<Return>", self.on_return)
        self.inp.bind("<FocusIn>", self._clear_placeholder)
        self.inp.bind("<FocusOut>", self._restore_placeholder)
        self._enable_clipboard(self.inp)
        self._ph_active = False
        self._set_placeholder()

        # 대화 영역 — 창 안쪽으로 들인 카드(밝은 테두리)
        wrap = tk.Frame(self, bg=C_BG)
        wrap.pack(side="top", fill="both", expand=True, padx=10, pady=(8, 4))
        card = tk.Frame(wrap, bg=C_BG, highlightthickness=1,
                        highlightbackground=C_LINE, highlightcolor=C_LINE, bd=0)
        card.pack(fill="both", expand=True)
        self.chat = tk.Text(card, bg=C_BG, fg=C_TEXT, font=(MONO, 11), wrap="word",
                            relief="flat", bd=0, padx=12, pady=10, insertbackground=C_TEXT,
                            state="disabled", spacing1=2, spacing3=4)
        sb = tk.Scrollbar(card, command=self.chat.yview)
        self.chat.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.chat.pack(side="left", fill="both", expand=True)
        self.chat.tag_config("user", foreground=C_BLUE, font=(MONO, 11, "bold"))
        self.chat.tag_config("bot", foreground=C_TEXT)
        self.chat.tag_config("sys", foreground=C_DIM, font=(MONO, 10))
        self.chat.tag_config("warn", foreground=C_AMBER, font=(MONO, 10))
        self.chat.tag_config("err", foreground=C_RED)
        self.chat.tag_config("label", foreground=C_GREEN_TX, font=(MONO, 10, "bold"))
        self.chat.tag_config("b", font=(MONO, 11, "bold"))
        self.chat.tag_config("h", foreground=C_GREEN_TX, font=(MONO, 12, "bold"))
        self.chat.tag_config("hr", foreground=C_HR)
        self.chat.tag_config("code", foreground="#c9d1d9", font=(MONO, 10))

        self._sys(f"준비 완료. 모드: {prompts.MODE_LABELS[self.mode]} · "
                  f"모델: {core.MODEL_LABELS[self.model_key]}")
        self._sys("연구 아이디어를 입력하거나 📎로 초안을 첨부하세요. "
                  "(Enter 전송 / Shift+Enter 줄바꿈)")
        self._mode_help()      # 현재 모드로 가능한 작업 안내
        self._check_update()   # 백그라운드로 새 버전 확인

    # ════════ 업데이트 알림 ════════
    def _check_update(self):
        def work():
            try:
                import urllib.request
                req = urllib.request.Request(
                    f"https://api.github.com/repos/{REPO}/releases/latest",
                    headers={"User-Agent": "research-chatbot"})
                with urllib.request.urlopen(req, timeout=8) as r:
                    data = json.load(r)
                latest = (data.get("tag_name") or "").lstrip("v")
                if latest and self._is_newer(latest, APP_VERSION):
                    self.after(0, lambda: self._show_update(latest))
            except Exception:
                pass  # 네트워크 실패 시 조용히 무시
        threading.Thread(target=work, daemon=True).start()

    def _is_newer(self, a, b):
        pa = [int(x) for x in re.findall(r"\d+", a)]
        pb = [int(x) for x in re.findall(r"\d+", b)]
        return pa > pb

    def _show_update(self, latest):
        if getattr(self, "_update_shown", False):
            return
        self._update_shown = True
        banner = tk.Label(self, text=f"🆕 새 버전 v{latest} 이(가) 있습니다 — 클릭해서 다운로드",
                          bg="#1f6feb", fg="#ffffff", font=(MONO, 10, "bold"),
                          cursor="hand2", pady=6)
        banner.pack(side="top", fill="x", before=self._toolbar)
        banner.bind("<Button-1>", lambda e: webbrowser.open(RELEASES_URL))

    def _mode_label(self):
        return f" 모드:{prompts.MODE_LABELS[self.mode]} ▾ "

    # ════════ 토글/명령 ════════
    MODE_ORDER = ["design", "review", "chat"]

    def open_mode_menu(self):
        """모드 버튼을 누르면 선택 목록을 띄운다(클릭해서 직접 고르기)."""
        menu = tk.Menu(self, tearoff=0, bg=C_BG2, fg=C_TEXT,
                       activebackground=C_GREEN, activeforeground="#0d1117",
                       font=(MONO, 10), bd=0)
        for key in self.MODE_ORDER:
            mark = "● " if key == self.mode else "○ "
            menu.add_command(label=mark + prompts.MODE_LABELS[key],
                             command=lambda k=key: self.set_mode(k))
        x = self.mode_btn.winfo_rootx()
        y = self.mode_btn.winfo_rooty() + self.mode_btn.winfo_height()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def set_mode(self, key):
        if key == self.mode:
            return
        self.mode = key
        self.mode_btn.configure(text=self._mode_label())
        self._sys(f"→ {prompts.MODE_LABELS[self.mode]} 모드로 변경")
        self._mode_help()

    def _mode_help(self):
        for line in MODE_DESC.get(self.mode, []):
            self._append("   • " + line + "\n", "sys")

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
        win.configure(padx=22, pady=18)
        win.attributes("-topmost", True)
        tk.Label(win, text="무료 NVIDIA API 키 발급 방법", bg=C_BG, fg=C_GREEN_TX,
                 font=(MONO, 13, "bold")).pack(anchor="w", pady=(0, 8))
        for s in GUIDE_STEPS:
            tk.Label(win, text=s, bg=C_BG, fg=C_TEXT, font=(MONO, 11),
                     justify="left", wraplength=440).pack(anchor="w", pady=1)
        link = tk.Label(win, text="🔗 build.nvidia.com 열기", bg=C_BG, fg=C_BLUE,
                        font=(MONO, 11, "underline"), cursor="hand2")
        link.pack(anchor="w", pady=(8, 0))
        link.bind("<Button-1>", lambda e: webbrowser.open(NVIDIA_URL))

    def attach_file(self):
        paths = filedialog.askopenfilenames(
            title="검토할 파일 선택 (여러 개 가능)",
            filetypes=[("지원 문서", "*.txt *.md *.pdf *.docx"), ("모든 파일", "*.*")])
        if not paths:
            return
        parts, names = [], []
        for p in paths:
            content, err = core.read_file(p)
            if err:
                self._warn(f"{os.path.basename(p)}: {err}")
                continue
            parts.append(f"[파일: {os.path.basename(p)}]\n{content}")
            names.append(os.path.basename(p))
        if not parts:
            return
        self.mode = "review"
        self.mode_btn.configure(text=self._mode_label())
        self._sys(f"📎 {len(names)}개 파일 읽음 → 검토 모드: {', '.join(names)}")
        self._dispatch("다음 원고를 검토해줘:\n\n" + "\n\n".join(parts),
                       display=f"[첨부] {', '.join(names)} 검토 요청")

    def export_html(self):
        """버튼 한 번으로: 지금까지 내용을 HTML로 생성 → 저장 → 브라우저로 열기.
        선택된 모드는 그대로 두고, 이번 턴만 내부적으로 HTML 생성용 프롬프트를 쓴다."""
        if self.streaming:
            return
        if not any(m["role"] == "assistant" for m in self.history):
            self._sys("먼저 내용을 작성한 뒤 눌러주세요 (설계·검토·문답 등).")
            return
        self._sys("📤 지금까지 내용을 HTML로 만드는 중…")
        self._export_after = True
        self._dispatch(
            "지금까지의 대화 내용을 바탕으로, 제목·소제목·표·간단한 CSS 스타일이 포함된 "
            "하나의 완성된 standalone HTML 문서를 만들어줘. 코드블록 표시(```) 없이 "
            "<!DOCTYPE html>로 시작하는 순수 HTML만 출력해.",
            display="[내보내기] 지금까지 내용을 HTML 페이지로 생성", mode="code")

    def _save_html(self, answer):
        html = answer.strip()
        m = re.search(r"<!DOCTYPE html.*?</html\s*>", html, re.S | re.I)
        if m:
            html = m.group(0)
        else:
            html = re.sub(r"^```[a-zA-Z]*\n?", "", html)
            html = re.sub(r"\n?```$", "", html.strip())
        ts = datetime.now().strftime("%Y-%m-%d_%H%M")
        path = os.path.join(OUT_DIR, f"{ts}_생성문서.html")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            self._sys(f"📤 HTML 저장됨 — 브라우저로 엽니다:\n   {path}")
            webbrowser.open("file://" + path)
        except Exception as e:
            self._warn(f"HTML 저장 오류: {e}")

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

    # ════════ 입력창 안내문(placeholder) ════════
    PLACEHOLDER = "대화를 입력해 주세요."

    def _set_placeholder(self):
        self.inp.delete("1.0", "end")
        self.inp.insert("1.0", self.PLACEHOLDER)
        self.inp.configure(fg=C_DIM)
        self._ph_active = True

    def _clear_placeholder(self, e=None):
        if getattr(self, "_ph_active", False):
            self.inp.delete("1.0", "end")
            self.inp.configure(fg=C_TEXT)
            self._ph_active = False

    def _restore_placeholder(self, e=None):
        if not self.inp.get("1.0", "end").strip():
            self._set_placeholder()

    # ════════ 전송/스트리밍 ════════
    def on_return(self, event):
        self.send()
        return "break"

    def send(self):
        if getattr(self, "_ph_active", False):
            return
        text = self.inp.get("1.0", "end").strip()
        if not text or self.streaming:
            return
        self.inp.delete("1.0", "end")
        self._dispatch(text)

    def _dispatch(self, content, display=None, mode=None):
        # 이번 턴에만 쓰는 모드(예: 📤 내보내기는 'code'로 처리). 평소엔 선택된 모드.
        self._turn_mode = mode or self.mode
        self._append("\n나 ▸ ", "user")
        self._append((display or content) + "\n", "bot")
        self.history.append({"role": "user", "content": content})
        self.streaming = True
        self.send_btn.configure(text="...")
        self._append("\nAI ▸\n", "label")
        self._ans_start = self.chat.index("end-1c")  # 답변 시작 위치 기록
        self._first_chunk = True
        self._load_i = 0
        self._answer_acc = []
        threading.Thread(target=self._worker, daemon=True).start()
        self.after(40, self._poll)
        self._animate_loading()   # 점멸 로딩 표시 시작

    def _animate_loading(self):
        """첫 글자가 오기 전까지 '입력중 …'을 점멸 애니메이션으로 표시."""
        if not getattr(self, "_first_chunk", False) or not self.streaming:
            return
        frames = ["입력중", "입력중 ·", "입력중 · ·", "입력중 · · ·"]
        self.chat.configure(state="normal")
        self.chat.delete(self._ans_start, "end-1c")
        self.chat.insert("end", frames[self._load_i % len(frames)], "sys")
        self.chat.see("end")
        self.chat.configure(state="disabled")
        self._load_i += 1
        self.after(400, self._animate_loading)

    def _worker(self):
        for piece in core.stream_answer(self.client, self.model_key, self._turn_mode, self.history):
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
                    if self._first_chunk:        # 첫 글자 도착 → 대기표시 제거
                        self.chat.configure(state="normal")
                        self.chat.delete(self._ans_start, "end-1c")
                        self.chat.configure(state="disabled")
                        self._first_chunk = False
                    self._answer_acc.append(data)        # 원본 보관
                    if self._turn_mode == "code":        # HTML 내보내기는 원본 그대로
                        self._append(data, "code")
                    else:                                # 그 외엔 ** 제거
                        self._append(data.replace("**", ""), "bot")
                elif kind == "err":
                    if self._first_chunk:        # 대기표시 제거
                        self.chat.configure(state="normal")
                        self.chat.delete(self._ans_start, "end-1c")
                        self.chat.configure(state="disabled")
                        self._first_chunk = False
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
        self.send_btn.configure(text="보내기")
        answer = "".join(self._answer_acc)
        if not answer:
            return
        self.history.append({"role": "assistant", "content": answer})
        # 스트리밍된 원본(마크다운 기호 포함)을 지우고 깔끔하게 다시 렌더
        self.chat.configure(state="normal")
        self.chat.delete(self._ans_start, "end-1c")
        self.chat.configure(state="disabled")
        if self._turn_mode == "code":
            self._append(answer, "code")          # HTML 원본은 서식 보존(렌더 안 함)
        else:
            self._render_markdown(answer)
        if self._turn_mode in ("design", "review"):
            self._append(prompts.CITATION_NOTE + "\n", "warn")
        cjk = core.check_cjk(answer)
        if cjk:
            self._append("\n⚠️ 한자/가나 의심 문자 발견 (한글 교체 권장):\n", "warn")
            for item in cjk[:10]:
                self._append("   " + item + "\n", "warn")
            if len(cjk) > 10:
                self._append(f"   …외 {len(cjk) - 10}개\n", "warn")
        if self._turn_mode in ("design", "review"):
            ts = datetime.now().strftime("%Y-%m-%d_%H%M")
            label = prompts.MODE_LABELS[self._turn_mode]
            path = os.path.join(OUT_DIR, f"{ts}_{label}.md")
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"# [{label}] {ts}\n\n{answer}\n")
                self._sys(f"📄 저장됨: {path}")
            except Exception:
                pass

        # 📤 내보내기 요청이었으면 결과를 HTML로 저장·열기
        if getattr(self, "_export_after", False):
            self._export_after = False
            self._save_html(answer)

    # ════════ 출력 헬퍼 ════════
    def _append(self, text, tag):
        self.chat.configure(state="normal")
        self.chat.insert("end", text, tag)
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _render_markdown(self, text):
        """마크다운 기호를 실제 서식으로 바꿔 깔끔하게 출력 (** → 굵게, # → 제목, - → •)."""
        self.chat.configure(state="normal")
        for raw in text.split("\n"):
            line = raw.rstrip()
            m = re.match(r"^(#{1,6})\s*(.*)", line)
            if m:                                   # 제목
                self._inline(m.group(2), tag="h"); self.chat.insert("end", "\n"); continue
            if re.match(r"^\s*([-*_])(\s*\1){2,}\s*$", line):  # 구분선
                self.chat.insert("end", "─" * 30 + "\n", "hr"); continue
            mb = re.match(r"^(\s*)[-*]\s+(.*)", line)
            if mb:                                  # 글머리
                self.chat.insert("end", mb.group(1) + "• ", "bot")
                self._inline(mb.group(2)); self.chat.insert("end", "\n"); continue
            self._inline(line); self.chat.insert("end", "\n")
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _inline(self, text, tag="bot"):
        """줄 안의 **굵게**를 처리하고 남은 마크다운 기호(** ` )는 제거."""
        text = text.replace("`", "")
        for part in re.split(r"(\*\*.+?\*\*)", text):
            if len(part) >= 4 and part.startswith("**") and part.endswith("**"):
                self.chat.insert("end", part[2:-2], "b" if tag == "bot" else tag)
            else:
                # 짝이 안 맞아 남은 ** 기호 제거
                self.chat.insert("end", part.replace("**", ""), tag)

    def _sys(self, text):
        self._append("\n· " + text + "\n", "sys")

    def _warn(self, text):
        self._append("\n⚠️ " + text + "\n", "warn")

    # ════════ 전역 단축키 (기본 꺼짐 — macOS 크래시 방지) ════════
    # 켜려면 환경변수 RC_HOTKEY=1 로 실행 + macOS 입력 모니터링 권한 허용.
    def setup_hotkey(self):
        if os.environ.get("RC_HOTKEY") != "1":
            return
        try:
            from pynput import keyboard
        except Exception:
            return

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
        if not self.winfo_viewable():
            self.deiconify(); self.lift(); self.focus_force()
        else:
            self.withdraw()


if __name__ == "__main__":
    App().mainloop()
