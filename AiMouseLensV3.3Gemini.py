"""
╔══════════════════════════════════════════════════════════════════╗
║        AI MOUSE-LENS  ·  GOLD MASTER EDITION (v5.0)              ║
║  Stable Core · Ghost HUD · Voice Gallery · 503 Silent Retries    ║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio, base64, difflib, io, json, math, os, sys
import tempfile, threading, time, tkinter as tk
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# ── third-party guards ───────────────────────────────────────────────────────
def _require(pkg, install):
    try: return __import__(pkg)
    except ImportError: raise SystemExit(f"Missing: pip install {install}")

ctk       = _require("customtkinter", "customtkinter")
pyautogui = _require("pyautogui",     "pyautogui")
keyboard  = _require("keyboard",      "keyboard")
_req      = _require("requests",      "requests")
from PIL import ImageGrab

try: import speech_recognition as sr; HAS_SR = True
except: HAS_SR = False

try: import edge_tts as _edge_tts; HAS_EDGE_TTS = True
except: HAS_EDGE_TTS = False

try: import whisper as _whisper; HAS_WHISPER = True
except: HAS_WHISPER = False

try: 
    import pygame as _pygame
    _pygame.mixer.init()
    HAS_PYGAME = True
except: HAS_PYGAME = False

try: import pyperclip; HAS_PYPERCLIP = True
except: HAS_PYPERCLIP = False

# Hide pygame deprecation warnings
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module='pkg_resources')

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS & CONFIG
# ─────────────────────────────────────────────────────────────────────────────
CONFIG_PATH   = Path.home() / ".ai_mouselens_v5_config.json"
BUBBLE_W      = 370
AUTO_HIDE_SEC = 15
TRACK_MS      = 16

FACE = {"idle": "( •_•)", "fast": "(⊙_⊙)", "thinking": "(－‸－)", "success": "(＾▽＾)", "error": "(╯°□°）╯", "talking": "( ◦0◦)"}
C = {
    "bg": "#0a0a10", "bg2": "#12121c", "border": "#1e1e30", "accent": "#00c8ff", 
    "accent2": "#6c63ff", "text": "#dde4f0", "muted": "#555570", "success": "#44e88a", 
    "error": "#ff5566", "thinking": "#f0c040", "lens_ring": "#00c8ff", "transp": "#010101"
}

def _font(): return "Segoe UI Variable" if sys.platform.startswith("win") else "Helvetica"
FN = _font()

PROMPT = "You are AI Mouse-Lens, an ultra-concise screen analyst. Describe what is visible in the image under the cursor in 2-4 short sentences, then give one actionable insight. No preamble."
VOICE_PROMPT = "You are AI Mouse-Lens, a witty cursor companion. Answer the user's question in 1-2 concise sentences. Be friendly and direct. No preamble."
JUDGE_PROMPT = "You are a fair judge reviewing two AI responses. Pick the better, more accurate answer and output ONLY the final 2-4 sentence response."

SAFE_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gpt-4o-mini", "claude-3-haiku-20240307", "moondream", "llava"]
PROVIDER_OPTIONS = ["── Select Provider ──", "Gemini", "OpenAI", "Anthropic", "DeepSeek", "Ollama (local)", "Custom"]

DEFAULT_CFG = {
    "hotkey": "alt+s", "voice_hotkey": "alt+v", "lens_radius": 38, "capture_size": 400,
    "active_providers": [], "use_ollama": False, "ollama_model": "moondream",
    "consensus": True, "judge_model": "llava", "tts_voice": "en-US-AndrewNeural"
}

def load_cfg() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f: return {**DEFAULT_CFG, **json.load(f)}
        except: pass
    return dict(DEFAULT_CFG)

def save_cfg(cfg: dict):
    with open(CONFIG_PATH, "w") as f: json.dump(cfg, f, indent=2)

# ─────────────────────────────────────────────────────────────────────────────
#  AI ENGINE (With Silent 503 Retries)
# ─────────────────────────────────────────────────────────────────────────────
class AIEngine:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    @staticmethod
    def _b64(img) -> str:
        buf = io.BytesIO(); img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    @staticmethod
    def _retry_req(method: str, url: str, **kwargs) -> _req.Response:
        """Silent 503/429 Retry Loop (Hides Google's busy errors)"""
        for attempt in range(3):
            try:
                r = _req.request(method, url, **kwargs)
                if r.status_code in (503, 429):
                    time.sleep(1.5); continue
                r.raise_for_status(); return r
            except Exception as e:
                if attempt == 2: raise e
                time.sleep(1.5)
        raise Exception("Failed after retries")

    def _gemini_img(self, b64: str, p: dict) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{p.get('model', 'gemini-2.5-flash')}:generateContent?key={p['key']}"
        body = {"contents": [{"parts": [{"text": PROMPT}, {"inline_data": {"mime_type": "image/png", "data": b64}}]}]}
        return self._retry_req("POST", url, json=body, timeout=30).json()["candidates"][0]["content"]["parts"][0]["text"].strip()

    def _openai_img(self, b64: str, p: dict, base_url="https://api.openai.com/v1/chat/completions") -> str:
        body = {"model": p.get("model", "gpt-4o-mini"), "messages": [{"role": "user", "content": [{"type": "text", "text": PROMPT}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]}
        return self._retry_req("POST", base_url, headers={"Authorization": f"Bearer {p['key']}"}, json=body, timeout=30).json()["choices"][0]["message"]["content"].strip()

    def _ollama_img(self, b64: str, p: dict) -> str:
        return _req.post("http://localhost:11434/api/generate", json={"model": p.get("model", "moondream"), "prompt": PROMPT, "images": [b64], "stream": False}, timeout=60).json()["response"].strip()

    def _gemini_txt(self, q: str, p: dict) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{p.get('model', 'gemini-2.5-flash')}:generateContent?key={p['key']}"
        return self._retry_req("POST", url, json={"contents": [{"parts": [{"text": VOICE_PROMPT + "\nUser: " + q}]}]}, timeout=30).json()["candidates"][0]["content"]["parts"][0]["text"].strip()

    def _openai_txt(self, q: str, p: dict, base_url="https://api.openai.com/v1/chat/completions") -> str:
        body = {"model": p.get("model", "gpt-4o-mini"), "messages": [{"role": "system", "content": VOICE_PROMPT}, {"role": "user", "content": q}]}
        return self._retry_req("POST", base_url, headers={"Authorization": f"Bearer {p['key']}"}, json=body, timeout=30).json()["choices"][0]["message"]["content"].strip()

    def _ollama_txt(self, q: str, p: dict) -> str:
        return _req.post("http://localhost:11434/api/generate", json={"model": p.get("model", "moondream"), "prompt": VOICE_PROMPT + "\nUser: " + q, "stream": False}, timeout=60).json()["response"].strip()

    def _call_img(self, b64: str, p: dict) -> str:
        t = p.get("type", "")
        if t == "gemini": return self._gemini_img(b64, p)
        if t in ("openai", "grok", "deepseek", "custom"): return self._openai_img(b64, p, p.get("base_url", "https://api.deepseek.com/v1/chat/completions" if t=="deepseek" else ""))
        if t == "ollama": return self._ollama_img(b64, p)
        raise ValueError("Unknown provider")

    def _call_txt(self, q: str, p: dict) -> str:
        t = p.get("type", "")
        if t == "gemini": return self._gemini_txt(q, p)
        if t in ("openai", "grok", "deepseek", "custom"): return self._openai_txt(q, p, p.get("base_url", "https://api.deepseek.com/v1/chat/completions" if t=="deepseek" else ""))
        if t == "ollama": return self._ollama_txt(q, p)
        raise ValueError("Unknown provider")

    def _judge(self, b64: str, a: str, b: str, is_txt: bool) -> str:
        body = {"model": self.cfg.get("judge_model", "llava"), "prompt": f"{JUDGE_PROMPT}\nResponse A: {a}\nResponse B: {b}\n", "stream": False}
        if not is_txt and b64: body["images"] = [b64]
        try: return _req.post("http://localhost:11434/api/generate", json=body, timeout=60).json()["response"].strip()
        except: return a if len(a) >= len(b) else b

    def _consensus(self, fn, providers, data, is_txt=False):
        ops = [p for p in providers if p.get("type") == "ollama"]; cps = [p for p in providers if p.get("type") != "ollama" and p.get("key")]
        if not ops or not cps: return None
        res, errs = {}, []
        def run(name, p):
            try: res[name] = fn(data, p)
            except Exception as e: errs.append(str(e))
        t1, t2 = threading.Thread(target=run, args=("ollama", ops[0])), threading.Thread(target=run, args=("cloud", cps[0]))
        t1.start(); t2.start(); t1.join(30); t2.join(30)
        
        if "ollama" in res and "cloud" in res:
            if difflib.SequenceMatcher(None, res["ollama"][:200], res["cloud"][:200]).ratio() > 0.5: return res["cloud"], "success"
            return self._judge(data if not is_txt else "", res["ollama"], res["cloud"], is_txt), "success"
        if "cloud" in res: return res["cloud"], "success"
        if "ollama" in res: return res["ollama"], "success"
        return f"Error: {errs}", "error"

    def analyze(self, img) -> Tuple[str, str]:
        b64 = self._b64(img)
        if self.cfg.get("consensus", True):
            r = self._consensus(self._call_img, self.cfg.get("active_providers", []), b64)
            if r: return r
        for p in self.cfg.get("active_providers", []):
            try: return self._call_img(b64, p), "success"
            except: continue
        return "All providers failed.", "error"

    def analyze_txt(self, q: str) -> Tuple[str, str]:
        if self.cfg.get("consensus", True):
            r = self._consensus(self._call_txt, self.cfg.get("active_providers", []), q, True)
            if r: return r
        for p in self.cfg.get("active_providers", []):
            try: return self._call_txt(q, p), "success"
            except: continue
        return "All providers failed.", "error"

# ─────────────────────────────────────────────────────────────────────────────
#  AUDIO PLAYER (Silent Pygame Mixer)
# ─────────────────────────────────────────────────────────────────────────────
class AudioPlayer:
    def __init__(self, voice="en-US-AndrewNeural"):
        self.voice = voice
        self.lock = threading.Lock()

    def speak(self, text, on_done=None):
        threading.Thread(target=self._play, args=(text, on_done), daemon=True).start()

    def _play(self, text, on_done):
        if not HAS_EDGE_TTS or not HAS_PYGAME: 
            if on_done: on_done()
            return
        asyncio.set_event_loop(asyncio.new_event_loop())
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f: tmp = f.name
            asyncio.get_event_loop().run_until_complete(_edge_tts.Communicate(text, self.voice).save(tmp))
            with self.lock:
                _pygame.mixer.music.load(tmp)
                _pygame.mixer.music.play()
                while _pygame.mixer.music.get_busy(): time.sleep(0.1)
                _pygame.mixer.music.unload()
        except: pass
        finally:
            try: os.unlink(tmp)
            except: pass
            if on_done: on_done()

# ─────────────────────────────────────────────────────────────────────────────
#  OVERLAY (Ghost HUD + Pin)
# ─────────────────────────────────────────────────────────────────────────────
class Overlay:
    def __init__(self, root, cfg):
        self.root, self.cfg, self._state, self._pinned = root, cfg, "idle", False
        self._mx = self._my = self._last_mx = self._last_my = self._phi = 0
        self._bubble_vis, self._hide_job = False, None
        self.lens_r = int(cfg.get("lens_radius", 38))
        self._build(); self._track()

    def _build(self):
        S = (self.lens_r + 8) * 2
        # Lens
        self._lw = tk.Toplevel(self.root)
        self._lw.overrideredirect(True); self._lw.attributes("-topmost", True, "-transparentcolor", C["transp"])
        self._lc = tk.Canvas(self._lw, width=S, height=S, bg=C["transp"], highlightthickness=0); self._lc.pack()
        # Face
        self._fw = tk.Toplevel(self.root)
        self._fw.overrideredirect(True); self._fw.attributes("-topmost", True, "-transparentcolor", C["transp"])
        self._fl = tk.Label(self._fw, text=FACE["idle"], fg=C["accent"], bg=C["transp"], font=(FN, 11, "bold")); self._fl.pack()
        # Bubble
        self._bw = tk.Toplevel(self.root)
        self._bw.overrideredirect(True); self._bw.attributes("-topmost", True, "-alpha", 0.95); self._bw.withdraw()
        inner = tk.Frame(self._bw, bg=C["bg2"], highlightbackground=C["border"], highlightthickness=1)
        inner.pack(fill="both", expand=True)
        hdr = tk.Frame(inner, bg=C["bg"], padx=10, pady=5); hdr.pack(fill="x")
        self._dot = tk.Label(hdr, text="◉", fg=C["accent"], bg=C["bg"], font=(FN, 10)); self._dot.pack(side="left")
        tk.Label(hdr, text=" Mouse-Lens", fg=C["text"], bg=C["bg"], font=(FN, 10, "bold")).pack(side="left")
        self._pin = tk.Label(hdr, text="📌", fg=C["muted"], bg=C["bg"], cursor="hand2"); self._pin.pack(side="right", padx=5)
        self._pin.bind("<Button-1>", lambda _: self._toggle_pin())
        tk.Label(hdr, text="✕", fg=C["muted"], bg=C["bg"], cursor="hand2").pack(side="right").bind("<Button-1>", lambda _: self.hide())
        self._btxt = tk.Label(inner, text="", fg=C["text"], bg=C["bg2"], font=(FN, 9), wraplength=BUBBLE_W-20, justify="left", anchor="nw")
        self._btxt.pack(fill="both", expand=True, padx=10, pady=10)
        self._draw_lens(C["lens_ring"])

    def _draw_lens(self, col):
        S, r, p, t = (self.lens_r + 8) * 2, self.lens_r, 6, max(4, self.lens_r // 6)
        self._lc.delete("all")
        self._lc.create_oval(p-3, p-3, S-p+3, S-p+3, outline=col, width=1, dash=(3,7))
        self._lc.create_oval(p, p, S-p, S-p, outline=col, width=2)
        c = S//2
        for dx, dy, ex, ey in [(-r,0,-r+t,0),(r-t,0,r,0),(0,-r,0,-r+t),(0,r-t,0,r)]: self._lc.create_line(c+dx, c+dy, c+ex, c+ey, fill=col)

    def _toggle_pin(self):
        self._pinned = not self._pinned
        self._pin.config(fg=C["accent"] if self._pinned else C["muted"])
        if self._pinned and self._hide_job: self.root.after_cancel(self._hide_job)

    def set_state(self, s: str):
        self._state = s
        col = {"idle": C["accent"], "thinking": C["thinking"], "success": C["success"], "error": C["error"]}.get(s, C["accent"])
        if self._fw.winfo_exists(): self._fl.config(text=FACE.get(s, FACE["idle"]), fg=col)
        self._draw_lens(col)

    def show(self, text, status="success"):
        self.set_state(status)
        if not self._bw.winfo_exists(): return
        self._dot.config(fg=C["success"] if status == "success" else C["error"])
        self._btxt.config(text=text); self._bubble_vis = True
        self._bw.deiconify(); self._bw.lift(); self._place()
        if self._hide_job: self.root.after_cancel(self._hide_job)
        if not self._pinned: self._hide_job = self.root.after(AUTO_HIDE_SEC * 1000, self.hide)

    def hide(self):
        if self._pinned: return
        self._bubble_vis = False; self.set_state("idle")
        if self._bw.winfo_exists(): self._bw.withdraw()

    def _place(self):
        self._bw.update_idletasks()
        h, sw, sh, o = self._bw.winfo_reqheight(), self.root.winfo_screenwidth(), self.root.winfo_screenheight(), self.lens_r + 14
        x, y = min(self._mx + o, sw - BUBBLE_W), min(self._my + o, sh - h)
        self._bw.geometry(f"{BUBBLE_W}x{h}+{x}+{y}")

    def _track(self):
        try: mx, my = pyautogui.position()
        except: return self.root.after(16, self._track)
        self._mx, self._my = mx, my
        if self._state == "idle" and self._fw.winfo_exists(): self._fl.config(text=FACE["fast"] if math.hypot(mx-self._last_mx, my-self._last_my) > 18 else FACE["idle"])
        self._last_mx, self._last_my = mx, my
        if self._lw.winfo_exists(): S=(self.lens_r+8)*2; self._lw.geometry(f"{S}x{S}+{mx-S//2}+{my-S//2}")
        if self._fw.winfo_exists(): self._fw.geometry(f"70x20+{mx-35}+{my+self.lens_r+5}")
        if self._bubble_vis: self._place()
        if self._state == "thinking" and self._lw.winfo_exists():
            self._phi = (self._phi + 0.15) % 6.28; self._lw.attributes("-alpha", 0.7 + 0.3 * math.sin(self._phi))
        self.root.after(16, self._track)

# ─────────────────────────────────────────────────────────────────────────────
#  SETTINGS WINDOW
# ─────────────────────────────────────────────────────────────────────────────
class SettingsWindow:
    def __init__(self, app):
        self.app, self.cfg = app, app.cfg
        ctk.set_appearance_mode("dark"); ctk.set_default_color_theme("dark-blue")
        self.win = ctk.CTk(); self.win.title("AI Mouse-Lens"); self.win.geometry("560x860")
        self._build()

    def _build(self):
        w = self.win; b = ctk.CTkScrollableFrame(w, fg_color="transparent"); b.pack(fill="both", expand=True, padx=5, pady=5)
        def sec(t): ctk.CTkLabel(b, text=t, font=ctk.CTkFont(FN, 12, "bold")).pack(anchor="w", pady=(15,2))
        
        # Hotkeys & Sliders
        sec("SETTINGS"); row1 = ctk.CTkFrame(b, fg_color="transparent"); row1.pack(fill="x")
        self.hk_v = tk.StringVar(value=self.cfg["hotkey"]); self.vhk_v = tk.StringVar(value=self.cfg["voice_hotkey"])
        ctk.CTkEntry(row1, textvariable=self.hk_v, width=120).pack(side="left", padx=5); ctk.CTkEntry(row1, textvariable=self.vhk_v, width=120).pack(side="left", padx=5)
        
        self.l_var = tk.IntVar(value=self.cfg["lens_radius"])
        def update_l(v): self.l_lbl.configure(text=str(int(v))); self.app.overlay.lens_r = int(v)
        sec("LENS RADIUS"); sl_row = ctk.CTkFrame(b, fg_color="transparent"); sl_row.pack(fill="x")
        ctk.CTkSlider(sl_row, from_=20, to=80, variable=self.l_var, command=update_l).pack(side="left", expand=True)
        self.l_lbl = ctk.CTkLabel(sl_row, text=str(self.l_var.get()), text_color=C["accent"]); self.l_lbl.pack(side="right", padx=10)

        # Provider UI
        sec("ADD PROVIDER")
        self.ptype_v = tk.StringVar(value=PROVIDER_OPTIONS[0])
        ctk.CTkOptionMenu(b, variable=self.ptype_v, values=PROVIDER_OPTIONS, command=self._draw_form).pack(fill="x", padx=5)
        self.form_frame = ctk.CTkFrame(b, fg_color=C["bg2"]); self.form_frame.pack(fill="x", pady=5)
        
        self.prov_list = ctk.CTkFrame(b, fg_color="transparent"); self.prov_list.pack(fill="x", pady=5)
        self._refresh_list()

        # Voice
        sec("VOICE")
        self.v_var = tk.StringVar(value=self.cfg["tts_voice"])
        self.v_combo = ctk.CTkComboBox(b, variable=self.v_var, values=["Loading..."], width=300); self.v_combo.pack(anchor="w", padx=5)
        threading.Thread(target=self._fetch_voices, daemon=True).start()

        # History
        sec("HISTORY (Click to Replay)"); self.hist = tk.Text(b, height=8, font=(FN, 9), bg=C["bg2"], fg=C["text"])
        self.hist.pack(fill="x"); self.hist.bind("<Button-1>", self._click_hist); self._poll_hist()

        # Save
        br = ctk.CTkFrame(b, fg_color="transparent"); br.pack(fill="x", pady=15)
        ctk.CTkButton(br, text="Save & Hide", fg_color="#10B981", command=self._save).pack(side="left")

    def _draw_form(self, choice):
        for w in self.form_frame.winfo_children(): w.destroy()
        if choice == PROVIDER_OPTIONS[0]: return
        t = choice.lower().split()[0]
        k_v, m_v, u_v = tk.StringVar(), tk.StringVar(value="gemini-2.5-flash"), tk.StringVar()
        if t != "ollama": ctk.CTkEntry(self.form_frame, textvariable=k_v, placeholder_text="API Key").pack(fill="x", padx=10, pady=5)
        if t == "custom": ctk.CTkEntry(self.form_frame, textvariable=u_v, placeholder_text="URL").pack(fill="x", padx=10, pady=5)
        row = ctk.CTkFrame(self.form_frame, fg_color="transparent"); row.pack(fill="x", padx=10)
        ctk.CTkEntry(row, textvariable=m_v).pack(side="left", expand=True, fill="x")
        ctk.CTkButton(self.form_frame, text="Add", command=lambda: self._add(t, k_v.get(), m_v.get(), u_v.get())).pack(pady=5)

    def _add(self, t, k, m, u):
        self.cfg["active_providers"].append({"type": t, "key": k, "model": m, "base_url": u})
        self._refresh_list(); self.ptype_v.set(PROVIDER_OPTIONS[0]); self._draw_form(PROVIDER_OPTIONS[0])

    def _refresh_list(self):
        for w in self.prov_list.winfo_children(): w.destroy()
        for i, p in enumerate(self.cfg["active_providers"]):
            row = ctk.CTkFrame(self.prov_list, fg_color=C["bg"]); row.pack(fill="x", pady=2)
            tk.Label(row, text=f"{p['type'].upper()} ({p['model']})", bg=C["bg"], fg=C["text"]).pack(side="left", padx=5)
            tk.Button(row, text="X", bg=C["error"], command=lambda idx=i: [self.cfg["active_providers"].pop(idx), self._refresh_list()]).pack(side="right")

    def _fetch_voices(self):
        try:
            loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
            v = [x["ShortName"] for x in loop.run_until_complete(_edge_tts.list_voices()) if "en-" in x["ShortName"]]
            self.win.after(0, lambda: self.v_combo.configure(values=sorted(v)))
        except: pass

    def _poll_hist(self):
        self.hist.config(state="normal"); self.hist.delete("1.0", "end")
        for h in self.app.history[-8:]: self.hist.insert("end", f"[{h['time']}] {h['text'][:80]}...\n")
        self.hist.config(state="disabled"); self.win.after(2000, self._poll_hist)

    def _click_hist(self, e):
        idx = int(self.hist.index(f"@{e.x},{e.y}").split(".")[0]) - 1
        if idx < len(self.app.history[-8:]):
            h = self.app.history[-8:][idx]
            self.app.overlay.show(h["text"]); self.app.overlay._pinned = True; self.app.overlay._pin.config(fg=C["accent"])

    def _save(self):
        self.cfg["hotkey"], self.cfg["voice_hotkey"], self.cfg["lens_radius"], self.cfg["tts_voice"] = self.hk_v.get(), self.vhk_v.get(), self.l_var.get(), self.v_var.get()
        save_cfg(self.cfg); self.app._reload(); self.win.withdraw()

# ─────────────────────────────────────────────────────────────────────────────
#  MAIN APP
# ─────────────────────────────────────────────────────────────────────────────
class App:
    def __init__(self):
        self.cfg, self.history = load_cfg(), []
        self.engine, self.audio = AIEngine(self.cfg), AudioPlayer(self.cfg["tts_voice"])
        self.mic, self.rec = sr.Microphone() if HAS_SR else None, sr.Recognizer() if HAS_SR else None
        self.whisp = _whisper.load_model("tiny") if HAS_WHISPER else None
        self.settings = SettingsWindow(self)
        self.overlay = Overlay(self.settings.win, self.cfg)
        self._bind()

    def _bind(self):
        keyboard.unhook_all()
        keyboard.add_hotkey(self.cfg["hotkey"], lambda: self.settings.win.after(0, self._screen))
        keyboard.add_hotkey(self.cfg["voice_hotkey"], lambda: self.settings.win.after(0, self._voice))

    def _reload(self):
        self.engine, self.audio = AIEngine(self.cfg), AudioPlayer(self.cfg["tts_voice"])
        self._bind()

    def _screen(self):
        self.overlay.show_loading(); threading.Thread(target=self._s_work, daemon=True).start()

    def _s_work(self):
        mx, my = pyautogui.position(); s = self.cfg.get("capture_size", 400)//2
        img = ImageGrab.grab(bbox=(mx-s, my-s, mx+s, my+s))
        txt, stat = self.engine.analyze(img)
        self.settings.win.after(0, lambda: self._finish(txt, stat))

    def _voice(self):
        if not self.rec: return
        self.overlay.show_loading(); threading.Thread(target=self._v_work, daemon=True).start()

    def _v_work(self):
        txt = None
        try:
            with self.mic as s: self.rec.adjust_for_ambient_noise(s, 0.4); aud = self.rec.listen(s, 8, 6)
            try: txt = self.rec.recognize_google(aud)
            except: 
                if self.whisp:
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f: f.write(aud.get_wav_data()); tmp = f.name
                    txt = self.whisp.transcribe(tmp, fp16=False)["text"].strip(); os.unlink(tmp)
        except: pass
        if txt: res, stat = self.engine.analyze_txt(txt)
        else: res, stat = "I didn't catch that.", "error"
        self.settings.win.after(0, lambda: [self._finish(res, stat), self.overlay.set_state("talking"), self.audio.speak(res, lambda: self.settings.win.after(0, lambda: self.overlay.set_state("idle")))])

    def _finish(self, txt, stat):
        self.overlay.show(txt, stat); self.history.append({"time": datetime.now().strftime("%H:%M:%S"), "text": txt, "status": stat})
        if HAS_PYPERCLIP: pyperclip.copy(txt)
        else: self.settings.win.clipboard_clear(); self.settings.win.clipboard_append(txt)

if __name__ == "__main__":
    App().settings.win.mainloop()
