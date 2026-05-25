"""
╔══════════════════════════════════════════════════════════╗
║          AI MOUSE-LENS  ·  PERSONA EDITION               ║
║   Idiot‑proof · Auto‑model fetch · Live sizing           ║
║   Clipboard copy · Session history · Floating HUD        ║
║   Voice · Multi‑provider · Progressive UI                ║
╚══════════════════════════════════════════════════════════╝

Install deps:
    pip install customtkinter pillow pyautogui keyboard requests speechrecognition pyttsx3 pyaudio

Run:
    python main.py
"""

# ── stdlib ──────────────────────────────────────────────────────────────────
import base64
import io
import json
import math
import threading
import sys
import tkinter as tk
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Callable

# ── third-party ─────────────────────────────────────────────────────────────
try:
    import customtkinter as ctk
except ImportError:
    raise SystemExit("Missing: pip install customtkinter")
try:
    import pyautogui
except ImportError:
    raise SystemExit("Missing: pip install pyautogui")
try:
    import keyboard
except ImportError:
    raise SystemExit("Missing: pip install keyboard")
try:
    import requests as _requests
except ImportError:
    raise SystemExit("Missing: pip install requests")
try:
    from PIL import ImageGrab
except ImportError:
    raise SystemExit("Missing: pip install pillow")
try:
    import speech_recognition as sr
except ImportError:
    raise SystemExit("Missing: pip install SpeechRecognition")
try:
    import pyttsx3
except ImportError:
    raise SystemExit("Missing: pip install pyttsx3")

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS & CONFIG DEFAULTS
# ─────────────────────────────────────────────────────────────────────────────
CONFIG_PATH   = Path.home() / ".ai_mouselens_config.json"
BUBBLE_W      = 360
AUTO_HIDE_SEC = 15
TRACK_MS      = 16

FACE = {
    "idle":     "( •_•)",
    "fast":     "(⊙_⊙)",
    "thinking": "(－‸－)",
    "success":  "(＾▽＾)",
    "error":    "(╯°□°）╯",
}

C = {
    "bg":        "#0a0a10",
    "bg2":       "#12121c",
    "border":    "#1e1e30",
    "accent":    "#00c8ff",
    "accent2":   "#6c63ff",
    "text":      "#dde4f0",
    "muted":     "#555570",
    "success":   "#44e88a",
    "error":     "#ff5566",
    "thinking":  "#f0c040",
    "lens_ring": "#00c8ff",
    "transparent_color": "#010101",
}

# Standard image prompt
PROMPT = (
    "You are AI Mouse-Lens, an ultra-concise screen analyst. "
    "The image shows a 400x400px screenshot region under the user's cursor. "
    "In 2-4 short sentences: describe what is visible, then give one sharp, "
    "actionable insight. Be direct. No preamble."
)

# Voice prompt
VOICE_PROMPT = (
    "You are AI Mouse-Lens, a witty, helpful cursor companion. "
    "Answer the user's spoken question in 1-2 concise sentences. "
    "Be friendly, direct, and slightly playful. No preamble."
)

# Special prompt for Ollama (strict against gibberish)
OLLAMA_PROMPT = (
    "You are an OCR and math specialist. OCR first, math second. "
    "No gibberish or alphabet loops. In 2-4 sentences, describe "
    "what is visible in the image and provide one actionable insight. "
    "Be direct."
)
OLLAMA_VOICE_PROMPT = (
    "You are an OCR and math specialist. Answer the question concisely. "
    "No gibberish or alphabet loops. Keep it short."
)

# Default configuration – now using active_providers list
DEFAULT_CFG = {
    "hotkey": "alt+s",
    "voice_hotkey": "alt+v",
    "lens_radius": 38,
    "capture_size": 400,
    "active_providers": [],          # list of provider dicts
    "use_ollama": False,
    "ollama_model_name": "moondream",
}

# Safe fallback models for when fetch fails
SAFE_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gpt-4o-mini",
    "claude-3-haiku-20240307",
    "claude-3-sonnet-20240229",
    "grok-1",
    "moondream",
]

# ─────────────────────────────────────────────────────────────────────────────
#  FONT UTILITY
# ─────────────────────────────────────────────────────────────────────────────
def _system_sans_serif() -> str:
    if sys.platform.startswith("win"):
        return "Segoe UI"
    elif sys.platform.startswith("darwin"):
        return "Helvetica"
    else:
        return "Ubuntu"

FONT_PRIMARY = (_system_sans_serif(), 12)
FONT_BOLD    = (_system_sans_serif(), 12, "bold")
FONT_SMALL   = (_system_sans_serif(), 9)
FONT_HEADER  = (_system_sans_serif(), 22, "bold")

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIG I/O + MIGRATION
# ─────────────────────────────────────────────────────────────────────────────
def migrate_cfg(raw: dict) -> dict:
    """Convert old flat keys to new active_providers list if needed."""
    if "active_providers" not in raw:
        raw["active_providers"] = []
        # Gemini
        key = raw.get("gemini_api_key", "").strip()
        if key:
            raw["active_providers"].append({
                "type": "gemini",
                "key": key,
                "model": raw.get("gemini_model_name", "gemini-2.0-flash"),
            })
        # OpenAI
        key = raw.get("openai_api_key", "").strip()
        if key:
            raw["active_providers"].append({
                "type": "openai",
                "key": key,
                "model": raw.get("openai_model_name", "gpt-4o-mini"),
            })
        # Anthropic
        key = raw.get("anthropic_api_key", "").strip()
        if key:
            raw["active_providers"].append({
                "type": "anthropic",
                "key": key,
                "model": raw.get("anthropic_model_name", "claude-3-haiku-20240307"),
            })
        # Grok
        key = raw.get("grok_api_key", "").strip()
        if key:
            raw["active_providers"].append({
                "type": "grok",
                "key": key,
                "model": raw.get("grok_model_name", "grok-1"),
            })
        # Remove old keys
        for old in ["gemini_api_key","gemini_model_name","openai_api_key","openai_model_name",
                    "anthropic_api_key","anthropic_model_name","grok_api_key","grok_model_name"]:
            raw.pop(old, None)
        save_cfg(raw)
    return raw

def load_cfg() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                raw = json.load(f)
        except Exception:
            raw = {}
        raw = {**DEFAULT_CFG, **raw}
        return migrate_cfg(raw)
    return dict(DEFAULT_CFG)

def save_cfg(cfg: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

# ─────────────────────────────────────────────────────────────────────────────
#  UI HELPERS (INFO BUBBLES)
# ─────────────────────────────────────────────────────────────────────────────
class HoverBubble:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.bubble_window = None
        self.widget.bind("<Enter>", self.show_bubble)
        self.widget.bind("<Leave>", self.hide_bubble)

    def show_bubble(self, event=None):
        x = y = 0
        x, y, _, _ = self.widget.bbox("insert") or (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 35
        y += self.widget.winfo_rooty() + 25
        self.bubble_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)
        lbl = tk.Label(tw, text=self.text, justify="left",
                       background=C["bg2"], foreground=C["accent"],
                       relief="solid", borderwidth=1, highlightbackground=C["border"],
                       font=(FONT_PRIMARY[0], 11, "normal"), padx=8, pady=6)
        lbl.pack(ipadx=1)

    def hide_bubble(self, event=None):
        if self.bubble_window:
            self.bubble_window.destroy()
            self.bubble_window = None

# ─────────────────────────────────────────────────────────────────────────────
#  AI ENGINE — dynamic providers, custom OpenAI‑compatible slot
# ─────────────────────────────────────────────────────────────────────────────
class AIEngine:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    @staticmethod
    def _to_b64(img) -> str:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    # ── standard provider methods (accept provider dict) ─────────────────
    def _gemini_img(self, b64: str, provider: dict) -> str:
        model = provider.get("model", "gemini-1.5-flash")
        key   = provider["key"]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        body = {
            "contents": [{
                "parts": [
                    {"text": PROMPT},
                    {"inline_data": {"mime_type": "image/png", "data": b64}},
                ]
            }]
        }
        r = _requests.post(url, json=body, timeout=30)
        AIEngine._raise_if_404(r, model)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

    def _openai_img(self, b64: str, provider: dict, base_url: Optional[str] = None) -> str:
        model = provider.get("model", "gpt-4o-mini")
        key   = provider["key"]
        url   = base_url or "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        body = {
            "model": model, "max_tokens": 300,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
            ]}],
        }
        r = _requests.post(url, headers=headers, json=body, timeout=30)
        AIEngine._raise_if_404(r, model)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    def _anthropic_img(self, b64: str, provider: dict) -> str:
        model = provider.get("model", "claude-3-haiku-20240307")
        key   = provider["key"]
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        body = {
            "model": model, "max_tokens": 300,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
            ]}],
        }
        r = _requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=body, timeout=30)
        AIEngine._raise_if_404(r, model)
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()

    def _grok_img(self, b64: str, provider: dict) -> str:
        return self._openai_img(b64, provider, base_url="https://api.x.ai/v1/chat/completions")

    def _ollama_img(self, b64: str, provider: dict) -> str:
        model = provider.get("model", "moondream")
        r = _requests.post("http://localhost:11434/api/generate",
                           json={"model": model, "prompt": OLLAMA_PROMPT, "images": [b64], "stream": False}, timeout=60)
        r.raise_for_status()
        return r.json()["response"].strip()

    # ── text variants ────────────────────────────────────────────────────
    def _gemini_text(self, text: str, provider: dict) -> str:
        model = provider.get("model", "gemini-1.5-flash")
        key   = provider["key"]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        body = {"contents": [{"parts": [{"text": VOICE_PROMPT + "\nUser: " + text}]}]}
        r = _requests.post(url, json=body, timeout=30)
        AIEngine._raise_if_404(r, model)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

    def _openai_text(self, text: str, provider: dict, base_url: Optional[str] = None) -> str:
        model = provider.get("model", "gpt-4o-mini")
        key   = provider["key"]
        url   = base_url or "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        body = {"model": model, "max_tokens": 200,
                "messages": [{"role": "system", "content": VOICE_PROMPT}, {"role": "user", "content": text}]}
        r = _requests.post(url, headers=headers, json=body, timeout=30)
        AIEngine._raise_if_404(r, model)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    def _anthropic_text(self, text: str, provider: dict) -> str:
        model = provider.get("model", "claude-3-haiku-20240307")
        key   = provider["key"]
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        body = {"model": model, "max_tokens": 200, "system": VOICE_PROMPT,
                "messages": [{"role": "user", "content": text}]}
        r = _requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=body, timeout=30)
        AIEngine._raise_if_404(r, model)
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()

    def _grok_text(self, text: str, provider: dict) -> str:
        return self._openai_text(text, provider, base_url="https://api.x.ai/v1/chat/completions")

    def _ollama_text(self, text: str, provider: dict) -> str:
        model = provider.get("model", "moondream")
        r = _requests.post("http://localhost:11434/api/generate",
                           json={"model": model, "prompt": OLLAMA_VOICE_PROMPT + "\nUser: " + text, "stream": False}, timeout=60)
        r.raise_for_status()
        return r.json()["response"].strip()

    @staticmethod
    def _raise_if_404(response, model_name):
        if response.status_code == 404:
            raise ValueError(f"Model '{model_name}' not found. Check your model string in Settings.")

    # ── orchestrator: builds callable list from providers ────────────────
    def _build_providers(self, mode: str = "image") -> List[Tuple[str, Callable]]:
        providers_cfg = self.cfg.get("active_providers", [])
        result = []
        for p in providers_cfg:
            ptype = p.get("type")
            key   = p.get("key", "").strip()
            if ptype == "ollama":
                result.append(("Ollama (local)",
                               (lambda b: lambda img: self._ollama_img(img, b))(p) if mode == "image"
                               else (lambda b: lambda txt: self._ollama_text(txt, b))(p)))
                continue
            if not key:
                continue
            if ptype == "gemini":
                fn = (lambda b: lambda img: self._gemini_img(img, b))(p) if mode == "image" \
                     else (lambda b: lambda txt: self._gemini_text(txt, b))(p)
                result.append((f"Gemini ({p.get('model','')})", fn))
            elif ptype == "openai":
                fn = (lambda b: lambda img: self._openai_img(img, b))(p) if mode == "image" \
                     else (lambda b: lambda txt: self._openai_text(txt, b))(p)
                result.append((f"OpenAI ({p.get('model','')})", fn))
            elif ptype == "anthropic":
                fn = (lambda b: lambda img: self._anthropic_img(img, b))(p) if mode == "image" \
                     else (lambda b: lambda txt: self._anthropic_text(txt, b))(p)
                result.append((f"Anthropic ({p.get('model','')})", fn))
            elif ptype == "grok":
                fn = (lambda b: lambda img: self._grok_img(img, b))(p) if mode == "image" \
                     else (lambda b: lambda txt: self._grok_text(txt, b))(p)
                result.append((f"Grok ({p.get('model','')})", fn))
            elif ptype == "custom":
                base_url = p.get("base_url", "")
                name     = p.get("name", "Custom")
                fn = (lambda b: lambda img: self._openai_img(img, b, base_url=b.get("base_url","")))(p) if mode == "image" \
                     else (lambda b: lambda txt: self._openai_text(txt, b, base_url=b.get("base_url","")))(p)
                result.append((f"{name} ({p.get('model','')})", fn))
        # legacy Ollama fallback
        if not result and self.cfg.get("use_ollama"):
            if mode == "image":
                result.append(("Ollama (legacy)", lambda img: self._ollama_img(img, {"model": self.cfg.get("ollama_model_name","moondream")})))
            else:
                result.append(("Ollama (legacy)", lambda txt: self._ollama_text(txt, {"model": self.cfg.get("ollama_model_name","moondream")})))
        return result

    def analyze(self, img):
        b64 = self._to_b64(img)
        providers = self._build_providers("image")
        if not providers:
            return "No active providers configured.", "error"
        last_err = "All providers failed."
        for name, fn in providers:
            try:
                print(f"[MouseLens] Trying {name}...")
                result = fn(b64)
                print(f"[MouseLens] OK  {name}")
                return result, "success"
            except Exception as exc:
                last_err = str(exc)
                print(f"[MouseLens] FAIL {name}: {exc}")
        return f"All providers failed.\n{last_err}", "error"

    def analyze_text(self, text: str):
        providers = self._build_providers("text")
        if not providers:
            return "No active providers configured.", "error"
        last_err = "All providers failed."
        for name, fn in providers:
            try:
                print(f"[MouseLens Voice] Trying {name}...")
                result = fn(text)
                print(f"[MouseLens Voice] OK  {name}")
                return result, "success"
            except Exception as exc:
                last_err = str(exc)
                print(f"[MouseLens Voice] FAIL {name}: {exc}")
        return f"All providers failed.\n{last_err}", "error"

# ─────────────────────────────────────────────────────────────────────────────
#  OVERLAY — lens ring + floating face + result bubble   (live resizing)
# ─────────────────────────────────────────────────────────────────────────────
class Overlay:
    def __init__(self, root: tk.Misc, cfg: dict):
        self.root   = root
        self.cfg    = cfg
        self._state = "idle"
        self._mx = self._my = 0
        self._last_mx = self._last_my = 0
        self._speed = 0.0
        self._bubble_visible = False
        self._hide_job  = None
        self._pulse_phi = 0.0

        self.lens_radius = self.cfg.get("lens_radius", 38)
        self.capture_size = self.cfg.get("capture_size", 400)

        self._build_lens()
        self._build_face()
        self._build_bubble()
        self._track()

    def _build_lens(self):
        S = (self.lens_radius + 8) * 2
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-transparentcolor", C["transparent_color"])
        w.configure(bg=C["transparent_color"])
        c = tk.Canvas(w, width=S, height=S, bg=C["transparent_color"], highlightthickness=0)
        c.pack()
        self._lens_win    = w
        self._lens_canvas = c
        self._lens_size   = S
        self._redraw_lens(C["lens_ring"], 2)

    def _redraw_lens(self, color: str, width: int = 2):
        c = self._lens_canvas
        S = self._lens_size
        c.delete("all")
        pad = 6
        r = self.lens_radius
        c.create_oval(pad - 3, pad - 3, S - pad + 3, S - pad + 3, outline=color, width=1, dash=(3, 7), stipple="gray25")
        c.create_oval(pad, pad, S - pad, S - pad, outline=color, width=width)
        cx, cy = S // 2, S // 2
        t = max(4, r // 6)
        for dx, dy, ex, ey in [(-r,0,-r+t,0),(r-t,0,r,0),(0,-r,0,-r+t),(0,r-t,0,r)]:
            c.create_line(cx+dx, cy+dy, cx+ex, cy+ey, fill=color, width=1)

    def _build_face(self):
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-transparentcolor", C["transparent_color"])
        w.configure(bg=C["transparent_color"])
        lbl = tk.Label(w, text=FACE["idle"], fg=C["accent"], bg=C["transparent_color"],
                       font=(FONT_PRIMARY[0], 11, "bold"), padx=6, pady=2)
        lbl.pack()
        self._face_win = w
        self._face_lbl = lbl

    def _build_bubble(self):
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-alpha", 0.96)
        w.configure(bg=C["border"])
        w.withdraw()
        inner = tk.Frame(w, bg=C["bg2"])
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        hdr = tk.Frame(inner, bg=C["bg"])
        hdr.pack(fill="x", ipadx=10, ipady=7)
        self._dot = tk.Label(hdr, text="◉", fg=C["accent"], bg=C["bg"], font=(FONT_PRIMARY[0], 10, "bold"))
        self._dot.pack(side="left")
        tk.Label(hdr, text="  AI Mouse-Lens", fg=C["text"], bg=C["bg"],
                 font=(FONT_PRIMARY[0], 10, "bold")).pack(side="left")
        xb = tk.Label(hdr, text=" ✕ ", fg=C["muted"], bg=C["bg"], cursor="hand2", font=(FONT_PRIMARY[0], 10))
        xb.pack(side="right")
        xb.bind("<Button-1>", lambda _: self.hide_bubble())
        xb.bind("<Enter>", lambda _: xb.config(fg=C["text"]))
        xb.bind("<Leave>", lambda _: xb.config(fg=C["muted"]))
        tk.Frame(inner, bg=C["border"], height=1).pack(fill="x")
        body = tk.Frame(inner, bg=C["bg2"])
        body.pack(fill="both", expand=True, ipadx=12, ipady=10)
        self._txt = tk.Label(body, text="", fg=C["text"], bg=C["bg2"],
                             font=FONT_SMALL, wraplength=BUBBLE_W - 36, justify="left", anchor="nw")
        self._txt.pack(fill="both", expand=True)
        ftr = tk.Frame(inner, bg=C["bg2"])
        ftr.pack(fill="x", padx=12, pady=(0,7))
        self._timer_lbl = tk.Label(ftr, text="", fg=C["muted"], bg=C["bg2"], font=(FONT_PRIMARY[0], 8))
        self._timer_lbl.pack(side="left")
        self._bubble_win = w

    def set_state(self, state: str):
        self._state = state
        face_color = {"idle":C["accent"],"fast":C["accent"],"thinking":C["thinking"],"success":C["success"],"error":C["error"]}.get(state, C["accent"])
        self._face_lbl.config(text=FACE.get(state, FACE["idle"]), fg=face_color)
        ring_color = {"thinking":C["thinking"],"success":C["success"],"error":C["error"]}.get(state, C["lens_ring"])
        self._redraw_lens(ring_color, width=3 if state=="thinking" else 2)

    def show_loading(self):
        self.set_state("thinking")
        self._dot.config(fg=C["thinking"])
        self._txt.config(text="Analyzing...", fg=C["thinking"])
        self._timer_lbl.config(text="")
        self._bubble_visible = True
        self._bubble_win.deiconify()
        self._bubble_win.lift()
        self._place_bubble()

    def show_result(self, text: str, status: str):
        self.set_state(status)
        col = C["success"] if status=="success" else C["error"]
        self._dot.config(fg=col)
        self._txt.config(text=text, fg=C["text"])
        self._timer_lbl.config(text=f"auto-close {AUTO_HIDE_SEC}s")
        self._bubble_visible = True
        self._bubble_win.deiconify()
        self._bubble_win.lift()
        self._place_bubble()
        if self._hide_job:
            self.root.after_cancel(self._hide_job)
        self._hide_job = self.root.after(AUTO_HIDE_SEC*1000, self.hide_bubble)

    def hide_bubble(self):
        if self._hide_job:
            self.root.after_cancel(self._hide_job)
            self._hide_job = None
        self._bubble_win.withdraw()
        self._bubble_visible = False
        self.set_state("idle")

    def _place_bubble(self):
        bw = self._bubble_win
        bw.update_idletasks()
        w = BUBBLE_W
        h = bw.winfo_reqheight() or 130
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        off = self.lens_radius + 14
        x = self._mx + off
        y = self._my + off
        if x + w > sw: x = self._mx - w - off
        if y + h > sh: y = self._my - h - off
        bw.geometry(f"{w}x{h}+{x}+{y}")

    def _track(self):
        try:
            mx, my = pyautogui.position()
        except:
            self.root.after(TRACK_MS, self._track)
            return
        dx, dy = mx - self._last_mx, my - self._last_my
        self._speed = math.hypot(dx, dy)
        self._last_mx, self._last_my = mx, my
        self._mx, self._my = mx, my
        if self._state == "idle":
            self._face_lbl.config(text=FACE["fast"] if self._speed>18 else FACE["idle"], fg=C["accent"])
        S = self._lens_size
        self._lens_win.geometry(f"{S}x{S}+{mx-S//2}+{my-S//2}")
        self._face_win.update_idletasks()
        fw = max(self._face_win.winfo_reqwidth(), 70)
        fh = max(self._face_win.winfo_reqheight(), 20)
        self._face_win.geometry(f"{fw}x{fh}+{mx-fw//2}+{my+self.lens_radius+5}")
        if self._bubble_visible:
            self._place_bubble()
        if self._state == "thinking":
            self._pulse_phi = (self._pulse_phi + 0.14) % (2*math.pi)
            try: self._lens_win.attributes("-alpha", 0.72+0.23*math.sin(self._pulse_phi))
            except: pass
        else:
            try: self._lens_win.attributes("-alpha", 1.0)
            except: pass
        self.root.after(TRACK_MS, self._track)

    def update_lens_radius(self, radius: int):
        self.lens_radius = radius
        S = (radius+8)*2
        self._lens_size = S
        self._lens_canvas.config(width=S, height=S)
        self._redraw_lens(C["lens_ring"], 2)
        mx, my = self._mx, self._my
        self._lens_win.geometry(f"{S}x{S}+{mx-S//2}+{my-S//2}")

# ─────────────────────────────────────────────────────────────────────────────
#  FETCH MODELS HELPER
# ─────────────────────────────────────────────────────────────────────────────
def fetch_models_for_provider(provider_type: str, key: Optional[str] = None, base_url: Optional[str] = None) -> List[str]:
    """Attempt to fetch available model names from the provider's API.
    Falls back to SAFE_MODELS if anything fails."""
    try:
        if provider_type == "gemini" and key:
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
            resp = _requests.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                models = [m["name"].split("/")[-1] for m in data.get("models", [])
                          if "generateContent" in m.get("supportedGenerationMethods", [])]
                return models if models else SAFE_MODELS[:]
        elif provider_type == "openai" and key:
            headers = {"Authorization": f"Bearer {key}"}
            resp = _requests.get("https://api.openai.com/v1/models", headers=headers, timeout=15)
            if resp.status_code == 200:
                models = [m["id"] for m in resp.json().get("data", [])]
                return models if models else SAFE_MODELS[:]
        elif provider_type == "anthropic" and key:
            headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
            resp = _requests.get("https://api.anthropic.com/v1/models", headers=headers, timeout=15)
            if resp.status_code == 200:
                models = [m["id"] for m in resp.json().get("data", [])]
                return models if models else SAFE_MODELS[:]
        elif provider_type == "grok" and key:
            # xAI does not expose a public list; use safe fallback
            pass
        elif provider_type == "custom" and base_url and key:
            # Try the /models endpoint (common for OpenAI-compatible)
            url = base_url.rstrip("/") + "/models"
            headers = {"Authorization": f"Bearer {key}"}
            resp = _requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                models = [m["id"] for m in resp.json().get("data", [])]
                return models if models else SAFE_MODELS[:]
    except Exception as e:
        print(f"[Models] Fetch failed for {provider_type}: {e}")
    return SAFE_MODELS[:]   # guaranteed safe list

# ─────────────────────────────────────────────────────────────────────────────
#  SETTINGS WINDOW — progressive add/remove, fetch models, live sliders, history
# ─────────────────────────────────────────────────────────────────────────────
PROVIDER_TYPES = ["Select Provider...", "Gemini", "OpenAI", "Anthropic", "Grok", "Custom (OpenAI-Compatible)"]

class SettingsWindow:
    def __init__(self, cfg: dict, on_save, overlay_ref: Optional[Overlay] = None,
                 history_getter: Optional[Callable[[], List[dict]]] = None):
        self.cfg = cfg
        self.on_save = on_save
        self.overlay = overlay_ref
        self.history_getter = history_getter          # app-level history list

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.win = ctk.CTk()
        self.win.title("AI Mouse-Lens · Settings")
        self.win.geometry("560x800")
        self.win.resizable(False, False)

        self.providers: List[Dict] = list(cfg.get("active_providers", []))
        self._init_vars()
        self._build()
        self._refresh_provider_list_display()
        # Start polling history updates
        self._update_history_poll()

    def _init_vars(self):
        self.hk_var = tk.StringVar(value=self.cfg["hotkey"])
        self.voice_hk_var = tk.StringVar(value=self.cfg["voice_hotkey"])
        self.lens_r_var = tk.IntVar(value=self.cfg["lens_radius"])
        self.cap_var = tk.IntVar(value=self.cfg["capture_size"])
        self.oll_var = tk.BooleanVar(value=self.cfg["use_ollama"])
        self.ollama_model_var = tk.StringVar(value=self.cfg["ollama_model_name"])

        self._add_type_var = tk.StringVar(value="Select Provider...")
        self._add_form_frame = None

    def _build(self):
        w = self.win
        hdr = ctk.CTkFrame(w, fg_color="#07070e", corner_radius=0, height=62)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="◉  AI Mouse-Lens", font=ctk.CTkFont(*FONT_HEADER), text_color=C["accent"]).pack(side="left", padx=20)
        self._hdr_hotkey = ctk.CTkLabel(hdr, text=self.cfg["hotkey"].upper(), font=ctk.CTkFont(FONT_PRIMARY[0], 11), text_color=C["muted"])
        self._hdr_hotkey.pack(side="right", padx=20)

        outer = ctk.CTkFrame(w, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=5, pady=5)

        body = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        body.pack(fill="both", expand=True)
        self.body = body

        def section_title(txt):
            ctk.CTkLabel(body, text=txt, font=ctk.CTkFont(FONT_PRIMARY[0], 13, "bold"), text_color=C["text"], anchor="w").pack(fill="x", pady=(20, 8))
        def sub_label(txt):
            ctk.CTkLabel(body, text=txt, font=ctk.CTkFont(FONT_PRIMARY[0], 10), text_color=C["muted"], anchor="w").pack(fill="x", pady=(6, 2))

        # Hotkeys
        section_title("TRIGGER HOTKEYS")
        sub_label("Screen Analysis")
        hk_entry = ctk.CTkEntry(body, textvariable=self.hk_var, placeholder_text="e.g. alt+s", font=ctk.CTkFont(*FONT_PRIMARY))
        hk_entry.pack(fill="x", padx=10)
        HoverBubble(hk_entry, "Capture and analyse the screen region under cursor.")
        sub_label("Voice Command")
        voice_entry = ctk.CTkEntry(body, textvariable=self.voice_hk_var, placeholder_text="e.g. alt+v", font=ctk.CTkFont(*FONT_PRIMARY))
        voice_entry.pack(fill="x", padx=10)
        HoverBubble(voice_entry, "Hold to talk, release to ask Lensy.")

        # Lens & Capture (live sliders)
        section_title("LENS & CAPTURE")
        sub_label("Lens Size (radius)")
        self.lens_slider = ctk.CTkSlider(body, from_=20, to=80, variable=self.lens_r_var, number_of_steps=60, width=200,
                                         command=lambda _: self._on_lens_slider())
        self.lens_slider.pack(fill="x", padx=20)
        ctk.CTkLabel(body, textvariable=self.lens_r_var, font=ctk.CTkFont(FONT_PRIMARY[0], 10), text_color=C["accent"]).pack(anchor="w", padx=30)

        sub_label("Capture Zoom (pixel area)")
        self.cap_slider = ctk.CTkSlider(body, from_=100, to=1000, variable=self.cap_var, number_of_steps=18, width=200)
        self.cap_slider.pack(fill="x", padx=20)
        ctk.CTkLabel(body, textvariable=self.cap_var, font=ctk.CTkFont(FONT_PRIMARY[0], 10), text_color=C["accent"]).pack(anchor="w", padx=30)

        # Cloud Providers – add with model fetcher
        section_title("CLOUD PROVIDERS")
        ctk.CTkLabel(body, text="Add a provider:", font=ctk.CTkFont(FONT_PRIMARY[0], 10), text_color=C["muted"]).pack(anchor="w", padx=10)
        prov_choice_container = ctk.CTkFrame(body, fg_color="transparent")
        prov_choice_container.pack(fill="x", padx=10, pady=(0,5))
        self._prov_dropdown = ctk.CTkOptionMenu(prov_choice_container, variable=self._add_type_var,
                                                values=PROVIDER_TYPES,
                                                command=self._on_add_type_changed)
        self._prov_dropdown.pack(side="left", expand=True)

        # Dynamic add form container
        self._add_form_container = ctk.CTkFrame(body, fg_color="transparent")
        self._add_form_container.pack(fill="x", padx=10, pady=5)

        # Active providers list
        self._prov_list_frame = ctk.CTkFrame(body, fg_color=C["bg"], corner_radius=6)
        self._prov_list_frame.pack(fill="x", padx=10, pady=(10,5))
        tk.Label(self._prov_list_frame, text="Active Providers:", bg=C["bg"], fg=C["muted"],
                 font=(FONT_PRIMARY[0], 10, "bold")).pack(anchor="w", padx=10, pady=5)
        self._prov_list_inner = ctk.CTkFrame(self._prov_list_frame, fg_color="transparent")
        self._prov_list_inner.pack(fill="x", padx=5, pady=5)

        # Ollama
        section_title("LOCAL OLLAMA")
        oll_chk = ctk.CTkCheckBox(body, text="Enable Ollama (moondream)", variable=self.oll_var,
                                  font=ctk.CTkFont(*FONT_PRIMARY), text_color=C["text"],
                                  checkbox_width=18, checkbox_height=18, fg_color=C["accent2"])
        oll_chk.pack(anchor="w", padx=20, pady=(2,0))
        sub_label("Model Name")
        ctk.CTkEntry(body, textvariable=self.ollama_model_var, placeholder_text="moondream", font=ctk.CTkFont(*FONT_PRIMARY)).pack(fill="x", padx=10)

        # Persona preview
        section_title("PERSONA — LENSY")
        strip = ctk.CTkFrame(body, fg_color=C["bg"], corner_radius=6)
        strip.pack(fill="x", pady=(2,0), padx=10)
        face_colors = {"idle":C["accent"],"fast":C["accent"],"thinking":C["thinking"],"success":C["success"],"error":C["error"]}
        for state, face in FACE.items():
            col = ctk.CTkFrame(strip, fg_color="transparent")
            col.pack(side="left", expand=True, pady=8)
            ctk.CTkLabel(col, text=face, font=ctk.CTkFont(FONT_PRIMARY[0], 11, "bold"), text_color=face_colors[state]).pack()
            ctk.CTkLabel(col, text=state, font=ctk.CTkFont(FONT_PRIMARY[0], 8), text_color=C["muted"]).pack()

        # Session History
        section_title("SESSION HISTORY")
        self._history_box = ctk.CTkTextbox(body, height=150, font=ctk.CTkFont(FONT_PRIMARY[0], 9), wrap="word")
        self._history_box.pack(fill="x", padx=10, pady=(0,5))
        self._history_box.configure(state="disabled")

        # status & buttons
        self._status = ctk.CTkLabel(body, text="", font=ctk.CTkFont(*FONT_PRIMARY), text_color=C["success"], anchor="w")
        self._status.pack(fill="x", pady=(10,0), padx=10)
        br = ctk.CTkFrame(body, fg_color="transparent")
        br.pack(fill="x", pady=(8,0), padx=10)
        ctk.CTkButton(br, text="Save & Activate", command=self._save, width=190,
                      font=ctk.CTkFont(*FONT_BOLD), fg_color="#10B981", hover_color="#059669",
                      corner_radius=6).pack(side="left")
        ctk.CTkButton(br, text="Hide to Tray", command=self.win.withdraw, width=150,
                      font=ctk.CTkFont(*FONT_PRIMARY), fg_color="#16161f", hover_color="#22222f",
                      corner_radius=6).pack(side="right")

    # ── live lens slider ─────────────────────────────────────────────────
    def _on_lens_slider(self):
        if self.overlay:
            self.overlay.update_lens_radius(self.lens_r_var.get())

    # ── provider add form logic (with ComboBox + Fetch) ──────────────────
    def _clear_add_form(self):
        if self._add_form_frame:
            self._add_form_frame.pack_forget()
            self._add_form_frame.destroy()
            self._add_form_frame = None

    def _on_add_type_changed(self, choice):
        self._clear_add_form()
        if choice == "Select Provider...":
            return
        frame = ctk.CTkFrame(self._add_form_container, fg_color="transparent")
        frame.pack(fill="x", pady=(5,0))

        if choice == "Custom (OpenAI-Compatible)":
            # custom fields: name, base_url, key, model (ComboBox)
            ctk.CTkLabel(frame, text="Display Name", font=ctk.CTkFont(FONT_PRIMARY[0], 10), text_color=C["muted"]).pack(anchor="w")
            self._add_name_var = tk.StringVar()
            ctk.CTkEntry(frame, textvariable=self._add_name_var, placeholder_text="e.g. Carrot Pie AI", font=ctk.CTkFont(*FONT_PRIMARY)).pack(fill="x", pady=(2,4))

            ctk.CTkLabel(frame, text="Base URL (chat completions endpoint)", font=ctk.CTkFont(FONT_PRIMARY[0], 10), text_color=C["muted"]).pack(anchor="w")
            self._add_url_var = tk.StringVar()
            ctk.CTkEntry(frame, textvariable=self._add_url_var, placeholder_text="https://api.carrotpie.ai/v1/chat/completions", font=ctk.CTkFont(*FONT_PRIMARY)).pack(fill="x", pady=(2,4))

            ctk.CTkLabel(frame, text="API Key", font=ctk.CTkFont(FONT_PRIMARY[0], 10), text_color=C["muted"]).pack(anchor="w")
            self._add_key_var = tk.StringVar()
            ctk.CTkEntry(frame, textvariable=self._add_key_var, show="*", placeholder_text="sk-...", font=ctk.CTkFont(*FONT_PRIMARY)).pack(fill="x", pady=(2,4))

            ctk.CTkLabel(frame, text="Model", font=ctk.CTkFont(FONT_PRIMARY[0], 10), text_color=C["muted"]).pack(anchor="w")
            self._add_model_var = tk.StringVar(value=SAFE_MODELS[0])
            model_combo = ctk.CTkComboBox(frame, variable=self._add_model_var, values=SAFE_MODELS,
                                          font=ctk.CTkFont(*FONT_PRIMARY))
            model_combo.pack(fill="x", pady=(2,4))

            fetch_btn = ctk.CTkButton(frame, text="Fetch Models", width=100, font=ctk.CTkFont(*FONT_PRIMARY),
                                      command=lambda: self._fetch_models("custom",
                                                                        self._add_key_var.get().strip(),
                                                                        self._add_url_var.get().strip(),
                                                                        model_combo))
            fetch_btn.pack(pady=(0,4))
            self._add_form_type = "custom"
        else:
            # standard provider: key + model ComboBox + Fetch
            ctk.CTkLabel(frame, text=f"{choice} API Key", font=ctk.CTkFont(FONT_PRIMARY[0], 10), text_color=C["muted"]).pack(anchor="w")
            self._add_key_var = tk.StringVar()
            ctk.CTkEntry(frame, textvariable=self._add_key_var, show="*", placeholder_text="enter key", font=ctk.CTkFont(*FONT_PRIMARY)).pack(fill="x", pady=(2,4))

            ctk.CTkLabel(frame, text="Model", font=ctk.CTkFont(FONT_PRIMARY[0], 10), text_color=C["muted"]).pack(anchor="w")
            default_model = self._default_model_for(choice)
            self._add_model_var = tk.StringVar(value=default_model)
            model_combo = ctk.CTkComboBox(frame, variable=self._add_model_var, values=SAFE_MODELS,
                                          font=ctk.CTkFont(*FONT_PRIMARY))
            model_combo.pack(fill="x", pady=(2,4))

            fetch_btn = ctk.CTkButton(frame, text="Fetch Models", width=100, font=ctk.CTkFont(*FONT_PRIMARY),
                                      command=lambda ptype=choice.lower(): self._fetch_models(ptype,
                                                                            self._add_key_var.get().strip(),
                                                                            None,
                                                                            model_combo))
            fetch_btn.pack(pady=(0,4))
            self._add_form_type = choice.lower()

        add_btn = ctk.CTkButton(frame, text="Add Provider", command=lambda t=choice: self._add_provider(t),
                                fg_color=C["accent2"], hover_color="#574fcc",
                                font=ctk.CTkFont(*FONT_BOLD), corner_radius=6)
        add_btn.pack(pady=(8,2))
        self._add_form_frame = frame

    @staticmethod
    def _default_model_for(provider: str) -> str:
        defaults = {
            "Gemini": "gemini-1.5-flash",
            "OpenAI": "gpt-4o-mini",
            "Anthropic": "claude-3-haiku-20240307",
            "Grok": "grok-1",
        }
        return defaults.get(provider, SAFE_MODELS[0])

    def _fetch_models(self, ptype: str, key: str, base_url: Optional[str], model_combo: ctk.CTkComboBox):
        if not key and ptype not in ("ollama",):
            self._status.configure(text="API key is required to fetch models.", text_color=C["error"])
            return
        # Update combobox to loading
        model_combo.configure(values=["Fetching..."])
        threading.Thread(target=self._do_fetch, args=(ptype, key, base_url, model_combo), daemon=True).start()

    def _do_fetch(self, ptype, key, base_url, model_combo):
        try:
            models = fetch_models_for_provider(ptype, key, base_url)
        except Exception as e:
            models = SAFE_MODELS[:]
        # Update UI on main thread
        self.win.after(0, lambda: model_combo.configure(values=models))
        if models and models[0] not in ("Fetching...", "No models"):
            self.win.after(0, lambda: self._add_model_var.set(models[0]))

    def _add_provider(self, choice: str):
        key = self._add_key_var.get().strip()
        if not key and choice != "Custom (OpenAI-Compatible)":
            self._status.configure(text="API Key is required.", text_color=C["error"])
            return
        model = self._add_model_var.get().strip()
        if not model:
            self._status.configure(text="Model is required.", text_color=C["error"])
            return
        if choice == "Custom (OpenAI-Compatible)":
            name = self._add_name_var.get().strip() or "Custom"
            base_url = self._add_url_var.get().strip()
            if not base_url:
                self._status.configure(text="Base URL is required for custom provider.", text_color=C["error"])
                return
            provider_dict = {
                "type": "custom",
                "name": name,
                "base_url": base_url,
                "key": key,
                "model": model,
            }
        else:
            provider_dict = {
                "type": choice.lower(),
                "key": key,
                "model": model,
            }
        self.providers.append(provider_dict)
        self._clear_add_form()
        self._add_type_var.set("Select Provider...")
        self._refresh_provider_list_display()

    def _remove_provider(self, index):
        del self.providers[index]
        self._refresh_provider_list_display()

    def _refresh_provider_list_display(self):
        for w in self._prov_list_inner.winfo_children():
            w.destroy()
        if not self.providers:
            ctk.CTkLabel(self._prov_list_inner, text="No providers added yet.", text_color=C["muted"], font=ctk.CTkFont(*FONT_PRIMARY)).pack(anchor="w", padx=5, pady=5)
            return
        for idx, p in enumerate(self.providers):
            row = ctk.CTkFrame(self._prov_list_inner, fg_color="transparent")
            row.pack(fill="x", padx=5, pady=2)
            desc = f"{p.get('type','custom')} • {p.get('model','?')}"
            if p.get("type") == "custom":
                desc = f"{p.get('name','Custom')} ({p.get('model','?')})"
            ctk.CTkLabel(row, text=desc, font=ctk.CTkFont(FONT_PRIMARY[0], 10), text_color=C["text"]).pack(side="left", padx=5)
            rm_btn = ctk.CTkButton(row, text="✕", width=30, height=20, fg_color="transparent", hover_color=C["error"],
                                   font=ctk.CTkFont(FONT_PRIMARY[0], 10, "bold"), text_color=C["muted"],
                                   command=lambda i=idx: self._remove_provider(i))
            rm_btn.pack(side="right", padx=5)

    # ── history update ───────────────────────────────────────────────────
    def _update_history_poll(self):
        if self.history_getter:
            history = self.history_getter()   # returns list of {"time": str, "text": str, "status": str}
            if history:
                # update textbox
                self._history_box.configure(state="normal")
                self._history_box.delete("1.0", tk.END)
                for entry in reversed(history[-20:]):   # show last 20
                    timestamp = entry.get("time", "?")
                    status = entry.get("status", "")
                    text = entry.get("text", "")
                    color = C["success"] if status == "success" else C["error"]
                    self._history_box.insert(tk.END, f"[{timestamp}] ", "time")
                    self._history_box.insert(tk.END, f"{text}\n", "text")
                    self._history_box.tag_config("time", foreground=C["muted"])
                    self._history_box.tag_config("text", foreground=color)
                self._history_box.configure(state="disabled")
        self.win.after(3000, self._update_history_poll)   # refresh every 3s

    # ── save ────────────────────────────────────────────────────────────
    def _save(self):
        self.cfg.update({
            "hotkey": self.hk_var.get().strip().lower(),
            "voice_hotkey": self.voice_hk_var.get().strip().lower(),
            "lens_radius": self.lens_r_var.get(),
            "capture_size": self.cap_var.get(),
            "use_ollama": self.oll_var.get(),
            "ollama_model_name": self.ollama_model_var.get().strip(),
            "active_providers": self.providers,
        })
        save_cfg(self.cfg)
        self.on_save(self.cfg)
        self._hdr_hotkey.configure(text=self.cfg["hotkey"].upper())
        self._status.configure(text=f"Saved! {self.cfg['hotkey'].upper()} for screen, {self.cfg['voice_hotkey'].upper()} for voice.",
                               text_color=C["success"])
        self.win.after(2200, self.win.withdraw)

    def run(self):
        self.win.mainloop()

# ─────────────────────────────────────────────────────────────────────────────
#  APP — with clipboard copy, history, and voice
# ─────────────────────────────────────────────────────────────────────────────
class App:
    def __init__(self):
        self.cfg = load_cfg()
        self.engine = AIEngine(self.cfg)
        self._busy = False
        self._voice_busy = False

        # Speech & recognition
        self._tts = pyttsx3.init()
        self._tts.setProperty('rate', 180)
        self._tts.setProperty('volume', 0.9)
        self._recognizer = sr.Recognizer()
        self._mic = sr.Microphone()

        # Session history
        self.history: List[dict] = []

        # Overlay first, then settings (so settings can reference overlay)
        self.overlay = Overlay(self._temp_root(), self.cfg)
        self.settings = SettingsWindow(self.cfg, on_save=self._reload, overlay_ref=self.overlay,
                                       history_getter=lambda: self.history)
        self.overlay.root = self.settings.win
        self._bind_all_hotkeys()

    def _temp_root(self):
        tmp = tk.Toplevel()
        tmp.withdraw()
        return tmp

    def _bind_all_hotkeys(self):
        keyboard.unhook_all()
        screen_hk = self.cfg.get("hotkey", "alt+s").lower()
        keyboard.add_hotkey(screen_hk, self._hotkey, suppress=True)
        voice_hk = self.cfg.get("voice_hotkey", "alt+v").lower()
        keyboard.add_hotkey(voice_hk, self._voice_hotkey, suppress=True)
        print(f"[MouseLens] Hotkeys ready: {screen_hk.upper()} / {voice_hk.upper()}")

    def _reload(self, cfg: dict):
        self.cfg = cfg
        self.engine = AIEngine(cfg)
        try:
            self.overlay._lens_win.destroy()
            self.overlay._face_win.destroy()
            self.overlay._bubble_win.destroy()
        except:
            pass
        self.overlay = Overlay(self.settings.win, cfg)
        self._bind_all_hotkeys()
        print("[MouseLens] Config reloaded.")

    # ── analysis flow with clipboard & history ───────────────────────────
    def _hotkey(self):
        if self._busy: return
        self._busy = True
        mx, my = pyautogui.position()
        self.settings.win.after(0, lambda: self._begin(mx, my))

    def _begin(self, mx, my):
        self.overlay.show_loading()
        threading.Thread(target=self._worker, args=(mx, my), daemon=True).start()

    def _worker(self, mx, my):
        try:
            half = self.cfg.get("capture_size", 400) // 2
            img = ImageGrab.grab(bbox=(max(0, mx-half), max(0, my-half), mx+half, my+half))
            text, status = self.engine.analyze(img)
        except Exception as e:
            text, status = f"Capture error:\n{e}", "error"
        finally:
            self._busy = False
        # clipboard copy & history on success
        def after_analysis():
            self.overlay.show_result(text, status)
            if status == "success":
                # Copy to clipboard
                try:
                    self.settings.win.clipboard_clear()
                    self.settings.win.clipboard_append(text)
                    print("[MouseLens] Result copied to clipboard.")
                except:
                    pass
            # Add to session history
            self.history.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "text": text[:200] + ("..." if len(text) > 200 else ""),
                "status": status,
            })
        self.settings.win.after(0, after_analysis)

    # ── voice flow with clipboard & history ──────────────────────────────
    def _voice_hotkey(self):
        if self._voice_busy: return
        self._voice_busy = True
        self.settings.win.after(0, self.overlay.show_loading)
        self._speak("Listening...")
        threading.Thread(target=self._listen_and_process, daemon=True).start()

    def _speak(self, text: str):
        def _run():
            try:
                self._tts.say(text)
                self._tts.runAndWait()
            except Exception as e:
                print(f"[Voice] TTS error: {e}")
        threading.Thread(target=_run, daemon=True).start()

    def _listen_and_process(self):
        text = None
        try:
            with self._mic as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self._recognizer.listen(source, timeout=10, phrase_time_limit=5)
            text = self._recognizer.recognize_google(audio)
            print(f"[Voice] Heard: {text}")
        except sr.WaitTimeoutError:
            pass
        except sr.UnknownValueError:
            pass
        except Exception as e:
            print(f"[Voice] Mic error: {e}")

        if not text:
            result = "I didn't catch that. Please try again."
            status = "error"
        else:
            result, status = self.engine.analyze_text(text)

        def after_voice():
            self.overlay.show_result(result, status)
            self._speak(result)
            if status == "success":
                try:
                    self.settings.win.clipboard_clear()
                    self.settings.win.clipboard_append(result)
                except:
                    pass
            self.history.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "text": result[:200] + ("..." if len(result) > 200 else ""),
                "status": status,
            })
            self._voice_busy = False
        self.settings.win.after(0, after_voice)

    def run(self):
        print(f"[MouseLens] Ready — press {self.cfg['hotkey'].upper()} over anything, or {self.cfg['voice_hotkey'].upper()} to talk.")
        self.settings.run()

if __name__ == "__main__":
    App().run()
