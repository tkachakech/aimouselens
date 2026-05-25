"""
╔══════════════════════════════════════════════════════════════════╗
║        AI MOUSE-LENS  ·  CONSENSUS EDITION  v3.0 (FIXED)        ║
║  Consensus · DeepSeek · Neural Voice · Whisper · pygame Audio    ║
║  All geometry bugs fixed · Live sliders · Working provider UI    ║
╚══════════════════════════════════════════════════════════════════╝

pip install customtkinter pillow pyautogui keyboard requests
         speechrecognition edge-tts openai-whisper pyaudio pygame

python main.py
"""

# ── stdlib ───────────────────────────────────────────────────────────────────
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

from PIL import ImageGrab  # pillow

try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False
    print("[MouseLens] SpeechRecognition missing – pip install speechrecognition pyaudio")

try:
    import edge_tts as _edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False
    print("[MouseLens] edge-tts missing – pip install edge-tts")

try:
    import whisper as _whisper
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False
    print("[MouseLens] openai-whisper missing – pip install openai-whisper")

try:
    import pygame as _pygame
    _pygame.mixer.init()
    HAS_PYGAME = True
except Exception:
    HAS_PYGAME = False
    print("[MouseLens] pygame missing or init failed – pip install pygame")

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
CONFIG_PATH   = Path.home() / ".ai_mouselens_v3_config.json"
BUBBLE_W      = 370
AUTO_HIDE_SEC = 15
TRACK_MS      = 16            # ~62 fps

FACE = {
    "idle":     "( •_•)",
    "fast":     "(⊙_⊙)",
    "thinking": "(－‸－)",
    "success":  "(＾▽＾)",
    "error":    "(╯°□°）╯",
    "talking":  "( ◦0◦)",
}

C = {
    "bg":          "#0a0a10",
    "bg2":         "#12121c",
    "border":      "#1e1e30",
    "accent":      "#00c8ff",
    "accent2":     "#6c63ff",
    "text":        "#dde4f0",
    "muted":       "#555570",
    "success":     "#44e88a",
    "error":       "#ff5566",
    "thinking":    "#f0c040",
    "lens_ring":   "#00c8ff",
    "transp":      "#010101",   # chroma-key transparent colour
}

# Font helpers (platform-aware)
def _sans():
    if sys.platform.startswith("win"):   return "Segoe UI"
    if sys.platform.startswith("darwin"): return "Helvetica"
    return "Ubuntu"

FN = _sans()
F_NORM  = (FN, 11)
F_BOLD  = (FN, 11, "bold")
F_SMALL = (FN, 9)
F_HEAD  = (FN, 20, "bold")

PROMPT = (
    "You are AI Mouse-Lens, an ultra-concise screen analyst. "
    "The image shows a screenshot region under the user's cursor. "
    "In 2–4 short sentences: describe what is visible, then give one sharp "
    "actionable insight. Be direct. No preamble."
)
VOICE_PROMPT = (
    "You are AI Mouse-Lens, a witty cursor companion. "
    "Answer the user's spoken question in 1–2 concise sentences. "
    "Be friendly and direct. No preamble."
)
OLLAMA_PROMPT = (
    "You are an OCR and visual analysis specialist. "
    "Describe the image and give one actionable insight. No gibberish."
)
JUDGE_PROMPT = (
    "You are a fair judge reviewing two AI responses. "
    "Pick the better answer and output ONLY the final 2–4 sentence response."
)

SAFE_MODELS = [
    "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro",
    "gpt-4o-mini", "gpt-4o",
    "claude-3-haiku-20240307", "claude-3-5-sonnet-20241022",
    "grok-1",
    "deepseek-chat", "deepseek-vision",
    "moondream", "llava", "llava-llama3",
]

DEFAULT_CFG = {
    "hotkey":          "alt+s",
    "voice_hotkey":    "alt+v",
    "lens_radius":     38,
    "capture_size":    400,
    "active_providers": [],
    "use_ollama":      False,
    "ollama_model":    "moondream",
    "consensus":       True,
    "judge_model":     "llava",
    "tts_voice":       "en-US-AndrewNeural",
}

PROVIDER_OPTIONS = [
    "── Select Provider ──",
    "Gemini",
    "OpenAI",
    "Anthropic",
    "Grok",
    "DeepSeek",
    "Ollama (local)",
    "Custom (OpenAI-compatible)",
]

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────────────────────
def load_cfg() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                raw = json.load(f)
            return {**DEFAULT_CFG, **raw}
        except Exception:
            pass
    return dict(DEFAULT_CFG)

def save_cfg(cfg: dict):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
#  AI ENGINE
# ─────────────────────────────────────────────────────────────────────────────
class AIEngine:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    # ── utils ────────────────────────────────────────────────────────────────
    @staticmethod
    def _b64(img) -> str:
        buf = io.BytesIO(); img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    @staticmethod
    def _check_404(r, model):
        if r.status_code == 404:
            raise ValueError(f"Model '{model}' not found (404). Check model name in Settings.")

    @staticmethod
    def _sim(a: str, b: str) -> float:
        if not a or not b: return 0.0
        return difflib.SequenceMatcher(None, a[:200], b[:200]).ratio()

    # ── image providers ──────────────────────────────────────────────────────
    def _gemini_img(self, b64: str, p: dict) -> str:
        model = p.get("model", "gemini-1.5-flash")
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={p['key']}")
        body = {"contents": [{"parts": [
            {"text": PROMPT},
            {"inline_data": {"mime_type": "image/png", "data": b64}},
        ]}]}
        r = _req.post(url, json=body, timeout=30)
        self._check_404(r, model); r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

    def _openai_img(self, b64: str, p: dict, base_url: str = "") -> str:
        model = p.get("model", "gpt-4o-mini")
        url   = base_url or "https://api.openai.com/v1/chat/completions"
        body  = {"model": model, "max_tokens": 300,
                 "messages": [{"role": "user", "content": [
                     {"type": "text",      "text": PROMPT},
                     {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                 ]}]}
        r = _req.post(url, headers={"Authorization": f"Bearer {p['key']}",
                                    "Content-Type": "application/json"},
                      json=body, timeout=30)
        self._check_404(r, model); r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    def _anthropic_img(self, b64: str, p: dict) -> str:
        model = p.get("model", "claude-3-haiku-20240307")
        body  = {"model": model, "max_tokens": 300,
                 "messages": [{"role": "user", "content": [
                     {"type": "text",   "text": PROMPT},
                     {"type": "image",  "source": {"type": "base64",
                                                   "media_type": "image/png",
                                                   "data": b64}},
                 ]}]}
        r = _req.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": p["key"],
                                "anthropic-version": "2023-06-01",
                                "Content-Type": "application/json"},
                      json=body, timeout=30)
        self._check_404(r, model); r.raise_for_status()
        return r.json()["content"][0]["text"].strip()

    def _grok_img(self,     b64, p): return self._openai_img(b64, p, "https://api.x.ai/v1/chat/completions")
    def _deepseek_img(self, b64, p): return self._openai_img(b64, p, "https://api.deepseek.com/v1/chat/completions")

    def _ollama_img(self, b64: str, p: dict) -> str:
        model = p.get("model", "moondream")
        r = _req.post("http://localhost:11434/api/generate",
                      json={"model": model, "prompt": OLLAMA_PROMPT,
                            "images": [b64], "stream": False}, timeout=60)
        r.raise_for_status()
        return r.json()["response"].strip()

    # ── text providers ───────────────────────────────────────────────────────
    def _gemini_txt(self, q: str, p: dict) -> str:
        model = p.get("model", "gemini-1.5-flash")
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={p['key']}")
        r = _req.post(url, json={"contents": [{"parts": [
            {"text": VOICE_PROMPT + "\nUser: " + q}]}]}, timeout=30)
        self._check_404(r, model); r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

    def _openai_txt(self, q: str, p: dict, base_url: str = "") -> str:
        model = p.get("model", "gpt-4o-mini")
        url   = base_url or "https://api.openai.com/v1/chat/completions"
        r = _req.post(url, headers={"Authorization": f"Bearer {p['key']}",
                                    "Content-Type": "application/json"},
                      json={"model": model, "max_tokens": 200,
                            "messages": [{"role": "system", "content": VOICE_PROMPT},
                                         {"role": "user",   "content": q}]},
                      timeout=30)
        self._check_404(r, model); r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    def _anthropic_txt(self, q: str, p: dict) -> str:
        model = p.get("model", "claude-3-haiku-20240307")
        r = _req.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": p["key"],
                                "anthropic-version": "2023-06-01",
                                "Content-Type": "application/json"},
                      json={"model": model, "max_tokens": 200,
                            "system": VOICE_PROMPT,
                            "messages": [{"role": "user", "content": q}]},
                      timeout=30)
        self._check_404(r, model); r.raise_for_status()
        return r.json()["content"][0]["text"].strip()

    def _grok_txt(self,     q, p): return self._openai_txt(q, p, "https://api.x.ai/v1/chat/completions")
    def _deepseek_txt(self, q, p): return self._openai_txt(q, p, "https://api.deepseek.com/v1/chat/completions")

    def _ollama_txt(self, q: str, p: dict) -> str:
        model = p.get("model", "moondream")
        r = _req.post("http://localhost:11434/api/generate",
                      json={"model": model,
                            "prompt": VOICE_PROMPT + "\nUser: " + q,
                            "stream": False}, timeout=60)
        r.raise_for_status()
        return r.json()["response"].strip()

    # ── dispatch helpers ─────────────────────────────────────────────────────
    def _call_img(self, b64: str, p: dict) -> str:
        t = p.get("type", "")
        if t == "gemini":    return self._gemini_img(b64, p)
        if t == "openai":    return self._openai_img(b64, p)
        if t == "anthropic": return self._anthropic_img(b64, p)
        if t == "grok":      return self._grok_img(b64, p)
        if t == "deepseek":  return self._deepseek_img(b64, p)
        if t == "ollama":    return self._ollama_img(b64, p)
        if t == "custom":    return self._openai_img(b64, p, p.get("base_url", ""))
        raise ValueError(f"Unknown provider type: {t}")

    def _call_txt(self, q: str, p: dict) -> str:
        t = p.get("type", "")
        if t == "gemini":    return self._gemini_txt(q, p)
        if t == "openai":    return self._openai_txt(q, p)
        if t == "anthropic": return self._anthropic_txt(q, p)
        if t == "grok":      return self._grok_txt(q, p)
        if t == "deepseek":  return self._deepseek_txt(q, p)
        if t == "ollama":    return self._ollama_txt(q, p)
        if t == "custom":    return self._openai_txt(q, p, p.get("base_url", ""))
        raise ValueError(f"Unknown provider type: {t}")

    # ── judge ────────────────────────────────────────────────────────────────
    def _judge(self, b64: str, a: str, b_txt: str, text_mode: bool = False) -> str:
        model = self.cfg.get("judge_model", "llava")
        prompt = f"{JUDGE_PROMPT}\nResponse A: {a}\nResponse B: {b_txt}\nFinal answer:"
        try:
            body: dict = {"model": model, "prompt": prompt, "stream": False}
            if not text_mode and b64:
                body["images"] = [b64]
            r = _req.post("http://localhost:11434/api/generate", json=body, timeout=60)
            r.raise_for_status()
            return r.json()["response"].strip()
        except Exception as e:
            print(f"[Judge] {e}")
            return a if len(a) >= len(b_txt) else b_txt

    # ── parallel consensus ───────────────────────────────────────────────────
    def _consensus(self, call_fn, providers, b64_or_q, text_mode=False):
        """Run ollama + first cloud provider in parallel; judge on conflict."""
        ollama_ps = [p for p in providers if p.get("type") == "ollama"]
        cloud_ps  = [p for p in providers if p.get("type") != "ollama"
                     and (p.get("key") or "").strip()]
        if not ollama_ps or not cloud_ps:
            return None  # signal: fall back to sequential
        op = ollama_ps[0]; cp = cloud_ps[0]
        results: dict = {}; errors: list = []

        def run(name, p):
            try:    results[name] = call_fn(b64_or_q, p)
            except Exception as e: errors.append((name, str(e)))

        t1 = threading.Thread(target=run, args=("ollama", op), daemon=True)
        t2 = threading.Thread(target=run, args=("cloud",  cp), daemon=True)
        t1.start(); t2.start(); t1.join(30); t2.join(30)

        if "ollama" in results and "cloud" in results:
            sim = self._sim(results["ollama"], results["cloud"])
            if sim > 0.5:
                return results["cloud"], "success"
            print("[Consensus] Conflict → judge")
            b64 = "" if text_mode else b64_or_q
            final = self._judge(b64, results["ollama"], results["cloud"], text_mode)
            return final, "success"
        if "cloud"  in results: return results["cloud"],  "success"
        if "ollama" in results: return results["ollama"], "success"
        err = "; ".join(f"{k}: {v}" for k, v in errors)
        return f"Consensus failed: {err}", "error"

    # ── sequential fallback ──────────────────────────────────────────────────
    def _sequential(self, call_fn, providers, b64_or_q) -> Tuple[str, str]:
        if not providers:
            return "No providers configured — add one in Settings.", "error"
        last = "Unknown error"
        for p in providers:
            name = p.get("type", "?").capitalize()
            try:
                print(f"[MouseLens] → {name} ({p.get('model','?')})…")
                r = call_fn(b64_or_q, p)
                print(f"[MouseLens] ✓ {name}")
                return r, "success"
            except Exception as e:
                last = str(e)
                print(f"[MouseLens] ✗ {name}: {e}")
        return f"All providers failed.\n{last}", "error"

    # ── public ───────────────────────────────────────────────────────────────
    def _active(self):
        return self.cfg.get("active_providers", [])

    def analyze(self, img) -> Tuple[str, str]:
        b64 = self._b64(img)
        if self.cfg.get("consensus", True):
            r = self._consensus(self._call_img, self._active(), b64)
            if r is not None: return r
        return self._sequential(self._call_img, self._active(), b64)

    def analyze_text(self, q: str) -> Tuple[str, str]:
        if self.cfg.get("consensus", True):
            r = self._consensus(self._call_txt, self._active(), q, text_mode=True)
            if r is not None: return r
        return self._sequential(self._call_txt, self._active(), q)


# ─────────────────────────────────────────────────────────────────────────────
#  FETCH MODELS (background, non-blocking)
# ─────────────────────────────────────────────────────────────────────────────
def fetch_models(ptype: str, key: str = "", base_url: str = "") -> List[str]:
    try:
        if ptype == "gemini" and key:
            r = _req.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={key}", timeout=10)
            if r.ok:
                return [m["name"].split("/")[-1] for m in r.json().get("models", [])
                        if "generateContent" in m.get("supportedGenerationMethods", [])]
        elif ptype == "openai" and key:
            r = _req.get("https://api.openai.com/v1/models",
                         headers={"Authorization": f"Bearer {key}"}, timeout=10)
            if r.ok: return sorted(m["id"] for m in r.json().get("data", []))
        elif ptype == "anthropic" and key:
            r = _req.get("https://api.anthropic.com/v1/models",
                         headers={"x-api-key": key, "anthropic-version": "2023-06-01"}, timeout=10)
            if r.ok: return [m["id"] for m in r.json().get("data", [])]
        elif ptype == "deepseek" and key:
            r = _req.get("https://api.deepseek.com/v1/models",
                         headers={"Authorization": f"Bearer {key}"}, timeout=10)
            if r.ok: return [m["id"] for m in r.json().get("data", [])]
        elif ptype == "ollama":
            r = _req.get("http://localhost:11434/api/tags", timeout=5)
            if r.ok: return [t["name"] for t in r.json().get("models", [])]
        elif ptype == "custom" and base_url and key:
            r = _req.get(base_url.rstrip("/") + "/models",
                         headers={"Authorization": f"Bearer {key}"}, timeout=10)
            if r.ok: return [m["id"] for m in r.json().get("data", [])]
    except Exception as e:
        print(f"[Models] fetch error ({ptype}): {e}")
    return SAFE_MODELS[:]


# ─────────────────────────────────────────────────────────────────────────────
#  OVERLAY  (lens ring + Lensy face + result bubble)
# ─────────────────────────────────────────────────────────────────────────────
class Overlay:
    def __init__(self, root: tk.Misc, cfg: dict):
        self.root = root
        self.cfg  = cfg
        self._state = "idle"
        self._mx = self._my = 0
        self._last_mx = self._last_my = 0
        self._speed = 0.0
        self._bubble_vis = False
        self._hide_job   = None
        self._phi        = 0.0
        self.lens_r      = int(cfg.get("lens_radius", 38))
        self._build_lens()
        self._build_face()
        self._build_bubble()
        self._track()

    # ── builders ─────────────────────────────────────────────────────────────
    def _build_lens(self):
        S = (self.lens_r + 8) * 2
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-transparentcolor", C["transp"])
        w.configure(bg=C["transp"])
        cv = tk.Canvas(w, width=S, height=S, bg=C["transp"], highlightthickness=0)
        cv.pack()
        self._lw = w; self._lc = cv; self._ls = S
        self._draw_lens(C["lens_ring"], 2)

    def _draw_lens(self, color: str, w: int = 2):
        if not self._lw.winfo_exists(): return
        cv = self._lc; S = self._ls; r = self.lens_r; pad = 6; t = max(4, r // 6)
        cv.delete("all")
        cv.create_oval(pad-3, pad-3, S-pad+3, S-pad+3,
                       outline=color, width=1, dash=(3, 7), stipple="gray25")
        cv.create_oval(pad, pad, S-pad, S-pad, outline=color, width=w)
        cx, cy = S//2, S//2
        for dx, dy, ex, ey in [(-r,0,-r+t,0),(r-t,0,r,0),(0,-r,0,-r+t),(0,r-t,0,r)]:
            cv.create_line(cx+dx, cy+dy, cx+ex, cy+ey, fill=color, width=1)

    def _build_face(self):
        # ── transparent background so no black box appears ──
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-transparentcolor", C["transp"])
        w.configure(bg=C["transp"])
        lbl = tk.Label(w, text=FACE["idle"], fg=C["accent"],
                       bg=C["transp"],
                       font=(FN, 11, "bold"), padx=4, pady=1)
        lbl.pack()
        self._fw = w; self._fl = lbl

    def _build_bubble(self):
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-alpha", 0.96)
        w.configure(bg=C["border"])
        w.withdraw()
        inner = tk.Frame(w, bg=C["bg2"])
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        # header
        hdr = tk.Frame(inner, bg=C["bg"], padx=10, pady=7)
        hdr.pack(fill="x")
        self._dot = tk.Label(hdr, text="◉", fg=C["accent"], bg=C["bg"],
                             font=(FN, 10, "bold"))
        self._dot.pack(side="left")
        tk.Label(hdr, text="  AI Mouse-Lens", fg=C["text"], bg=C["bg"],
                 font=(FN, 10, "bold")).pack(side="left")
        xb = tk.Label(hdr, text=" ✕ ", fg=C["muted"], bg=C["bg"],
                      cursor="hand2", font=(FN, 10))
        xb.pack(side="right")
        xb.bind("<Button-1>", lambda _: self.hide_bubble())
        xb.bind("<Enter>",    lambda _: xb.config(fg=C["text"]))
        xb.bind("<Leave>",    lambda _: xb.config(fg=C["muted"]))
        tk.Frame(inner, bg=C["border"], height=1).pack(fill="x")
        body = tk.Frame(inner, bg=C["bg2"], padx=12, pady=10)
        body.pack(fill="both", expand=True)
        self._btxt = tk.Label(body, text="", fg=C["text"], bg=C["bg2"],
                              font=F_SMALL, wraplength=BUBBLE_W-36,
                              justify="left", anchor="nw")
        self._btxt.pack(fill="both", expand=True)
        ftr = tk.Frame(inner, bg=C["bg2"], padx=12)
        ftr.pack(fill="x", pady=(0, 7))
        self._btimer = tk.Label(ftr, text="", fg=C["muted"], bg=C["bg2"],
                                font=(FN, 8))
        self._btimer.pack(side="left")
        self._bw = w

    # ── public state API ──────────────────────────────────────────────────────
    def set_state(self, state: str):
        self._state = state
        fc = {"idle": C["accent"], "fast": C["accent"], "thinking": C["thinking"],
              "success": C["success"], "error": C["error"],
              "talking": C["accent"]}.get(state, C["accent"])
        if self._fw.winfo_exists():
            self._fl.config(text=FACE.get(state, FACE["idle"]), fg=fc)
        rc = {"thinking": C["thinking"], "success": C["success"],
              "error": C["error"]}.get(state, C["lens_ring"])
        self._draw_lens(rc, w=3 if state == "thinking" else 2)

    def show_loading(self):
        self.set_state("thinking")
        if not self._bw.winfo_exists(): return
        self._dot.config(fg=C["thinking"])
        self._btxt.config(text="Analyzing…", fg=C["thinking"])
        self._btimer.config(text="")
        self._bubble_vis = True
        self._bw.deiconify(); self._bw.lift()
        self._place_bubble()

    def show_result(self, text: str, status: str):
        self.set_state(status)
        if not self._bw.winfo_exists(): return
        col = C["success"] if status == "success" else C["error"]
        self._dot.config(fg=col)
        self._btxt.config(text=text, fg=C["text"])
        self._btimer.config(text=f"auto-close {AUTO_HIDE_SEC}s")
        self._bubble_vis = True
        self._bw.deiconify(); self._bw.lift()
        self._place_bubble()
        if self._hide_job: self.root.after_cancel(self._hide_job)
        self._hide_job = self.root.after(AUTO_HIDE_SEC * 1000, self.hide_bubble)

    def hide_bubble(self):
        if self._hide_job: self.root.after_cancel(self._hide_job); self._hide_job = None
        if self._bw.winfo_exists(): self._bw.withdraw()
        self._bubble_vis = False
        self.set_state("idle")

    # ── placement (geometry ALWAYS "WxH+X+Y") ────────────────────────────────
    def _place_bubble(self):
        if not self._bw.winfo_exists(): return
        self._bw.update_idletasks()
        bh = self._bw.winfo_reqheight() or 130
        sw = self.root.winfo_screenwidth(); sh = self.root.winfo_screenheight()
        off = self.lens_r + 14
        x, y = self._mx + off, self._my + off
        if x + BUBBLE_W > sw: x = self._mx - BUBBLE_W - off
        if y + bh       > sh: y = self._my - bh - off
        self._bw.geometry(f"{BUBBLE_W}x{bh}+{x}+{y}")

    # ── 62fps tracking loop ───────────────────────────────────────────────────
    def _track(self):
        try:   mx, my = pyautogui.position()
        except: self.root.after(TRACK_MS, self._track); return

        dx, dy = mx - self._last_mx, my - self._last_my
        self._speed = math.hypot(dx, dy)
        self._last_mx, self._last_my = mx, my
        self._mx, self._my = mx, my

        # idle face reacts to speed
        if self._state == "idle" and self._fw.winfo_exists():
            self._fl.config(
                text=FACE["fast"] if self._speed > 18 else FACE["idle"],
                fg=C["accent"])

        # lens ring
        if self._lw.winfo_exists():
            S = self._ls
            self._lw.geometry(f"{S}x{S}+{mx - S//2}+{my - S//2}")

        # face label (below ring, transparent bg)
        if self._fw.winfo_exists():
            self._fw.update_idletasks()
            fw = max(self._fw.winfo_reqwidth(), 70)
            fh = max(self._fw.winfo_reqheight(), 20)
            self._fw.geometry(f"{fw}x{fh}+{mx - fw//2}+{my + self.lens_r + 5}")

        # bubble
        if self._bubble_vis: self._place_bubble()

        # pulse lens when thinking
        if self._state == "thinking" and self._lw.winfo_exists():
            self._phi = (self._phi + 0.14) % (2 * math.pi)
            try: self._lw.attributes("-alpha", 0.72 + 0.23 * math.sin(self._phi))
            except: pass
        elif self._lw.winfo_exists():
            try: self._lw.attributes("-alpha", 1.0)
            except: pass

        self.root.after(TRACK_MS, self._track)

    def update_lens_radius(self, r: int):
        self.lens_r = r
        S = (r + 8) * 2; self._ls = S
        self._lc.config(width=S, height=S)
        self._draw_lens(C["lens_ring"], 2)
        self._lw.geometry(f"{S}x{S}+{self._mx - S//2}+{self._my - S//2}")


# ─────────────────────────────────────────────────────────────────────────────
#  SETTINGS WINDOW  — fully working provider form, live sliders, history
# ─────────────────────────────────────────────────────────────────────────────
class SettingsWindow:
    def __init__(self, cfg: dict, on_save,
                 overlay: Optional["Overlay"] = None,
                 history_fn: Optional[Callable[[], List[dict]]] = None):
        self.cfg        = cfg
        self.on_save    = on_save
        self.overlay    = overlay
        self.history_fn = history_fn
        self.providers: List[dict] = list(cfg.get("active_providers", []))

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.win = ctk.CTk()
        self.win.title("AI Mouse-Lens  ·  Settings  v3")
        self.win.geometry("560x840")
        self.win.resizable(False, True)
        self._init_vars()
        self._build()

    def _init_vars(self):
        cfg = self.cfg
        self.hk_var        = tk.StringVar(value=cfg.get("hotkey",       "alt+s"))
        self.vhk_var       = tk.StringVar(value=cfg.get("voice_hotkey", "alt+v"))
        # IntVars for live slider labels
        self.lens_var  = tk.IntVar(value=int(cfg.get("lens_radius",  38)))
        self.cap_var   = tk.IntVar(value=int(cfg.get("capture_size", 400)))
        # StringVars that mirror the IntVars (shown in labels)
        self.lens_str  = tk.StringVar(value=str(self.lens_var.get()))
        self.cap_str   = tk.StringVar(value=str(self.cap_var.get()))
        self.oll_var   = tk.BooleanVar(value=cfg.get("use_ollama", False))
        self.oll_model = tk.StringVar(value=cfg.get("ollama_model", "moondream"))
        self.cons_var  = tk.BooleanVar(value=cfg.get("consensus", True))
        self.judge_var = tk.StringVar(value=cfg.get("judge_model", "llava"))
        self.tts_var   = tk.StringVar(value=cfg.get("tts_voice", "en-US-AndrewNeural"))
        # Provider add-form state
        self._form_type_var  = tk.StringVar(value=PROVIDER_OPTIONS[0])
        self._form_key_var   = tk.StringVar()
        self._form_model_var = tk.StringVar()
        self._form_url_var   = tk.StringVar()   # custom only
        self._form_frame: Optional[ctk.CTkFrame] = None
        self._model_menu: Optional[ctk.CTkOptionMenu] = None

    # ── master layout ─────────────────────────────────────────────────────────
    def _build(self):
        w = self.win
        # header
        hdr = ctk.CTkFrame(w, fg_color="#07070e", corner_radius=0, height=60)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="◉  AI Mouse-Lens",
                     font=ctk.CTkFont(FN, 20, "bold"),
                     text_color=C["accent"]).pack(side="left", padx=18)
        self._hdr_hk = ctk.CTkLabel(hdr,
                                    text=self.cfg["hotkey"].upper(),
                                    font=ctk.CTkFont(FN, 10),
                                    text_color=C["muted"])
        self._hdr_hk.pack(side="right", padx=18)

        scroll = ctk.CTkScrollableFrame(w, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=6, pady=4)
        b = scroll    # shorthand

        def sec(t):
            ctk.CTkLabel(b, text=t, font=ctk.CTkFont(FN, 12, "bold"),
                         text_color=C["text"], anchor="w").pack(
                             fill="x", pady=(14, 4))
        def sub(t):
            ctk.CTkLabel(b, text=t, font=ctk.CTkFont(FN, 9),
                         text_color=C["muted"], anchor="w").pack(
                             fill="x", padx=10, pady=(3, 1))

        # ── hotkeys ─────────────────────────────────────────────────────────
        sec("HOTKEYS")
        sub("Screen analysis")
        ctk.CTkEntry(b, textvariable=self.hk_var, placeholder_text="alt+s",
                     font=ctk.CTkFont(FN, 11)).pack(fill="x", padx=10)
        sub("Voice command")
        ctk.CTkEntry(b, textvariable=self.vhk_var, placeholder_text="alt+v",
                     font=ctk.CTkFont(FN, 11)).pack(fill="x", padx=10)

        # ── lens + capture sliders ───────────────────────────────────────────
        sec("LENS & CAPTURE")
        sub("Lens ring radius (px)")

        def on_lens(val):
            v = int(float(val))
            self.lens_str.set(str(v))
            if self.overlay: self.overlay.update_lens_radius(v)

        sl1_row = ctk.CTkFrame(b, fg_color="transparent")
        sl1_row.pack(fill="x", padx=10)
        ctk.CTkSlider(sl1_row, from_=20, to=80, variable=self.lens_var,
                      number_of_steps=60, command=on_lens,
                      width=300).pack(side="left")
        ctk.CTkLabel(sl1_row, textvariable=self.lens_str,
                     text_color=C["accent"],
                     font=ctk.CTkFont(FN, 11, "bold"), width=40).pack(side="left", padx=6)

        sub("Capture area (px²  — square side length)")

        def on_cap(val):
            self.cap_str.set(str(int(float(val))))

        sl2_row = ctk.CTkFrame(b, fg_color="transparent")
        sl2_row.pack(fill="x", padx=10)
        ctk.CTkSlider(sl2_row, from_=100, to=1000, variable=self.cap_var,
                      number_of_steps=18, command=on_cap,
                      width=300).pack(side="left")
        ctk.CTkLabel(sl2_row, textvariable=self.cap_str,
                     text_color=C["accent"],
                     font=ctk.CTkFont(FN, 11, "bold"), width=50).pack(side="left", padx=6)

        # ── provider add form ────────────────────────────────────────────────
        sec("ADD CLOUD PROVIDER")
        ctk.CTkOptionMenu(b, variable=self._form_type_var,
                          values=PROVIDER_OPTIONS,
                          command=self._on_type_pick,
                          font=ctk.CTkFont(FN, 11)).pack(fill="x", padx=10, pady=(4, 2))

        self._form_container = ctk.CTkFrame(b, fg_color="transparent")
        self._form_container.pack(fill="x", padx=10, pady=2)

        # ── active providers list ────────────────────────────────────────────
        sec("ACTIVE PROVIDERS")
        self._prov_list = ctk.CTkFrame(b, fg_color=C["bg"], corner_radius=6)
        self._prov_list.pack(fill="x", padx=10, pady=(0, 4))
        self._refresh_prov_list()

        # ── ollama ───────────────────────────────────────────────────────────
        sec("LOCAL OLLAMA")
        ctk.CTkCheckBox(b, text="Enable Ollama",
                        variable=self.oll_var,
                        font=ctk.CTkFont(FN, 11), text_color=C["text"],
                        checkbox_width=18, checkbox_height=18,
                        fg_color=C["accent2"]).pack(anchor="w", padx=20)
        sub("Ollama model name")
        ctk.CTkEntry(b, textvariable=self.oll_model,
                     placeholder_text="moondream",
                     font=ctk.CTkFont(FN, 11)).pack(fill="x", padx=10)

        # ── consensus ────────────────────────────────────────────────────────
        sec("CONSENSUS ENGINE")
        ctk.CTkCheckBox(b, text="Enable consensus (Ollama + Cloud agree or judge)",
                        variable=self.cons_var,
                        font=ctk.CTkFont(FN, 11), text_color=C["text"],
                        checkbox_width=18, checkbox_height=18,
                        fg_color=C["accent2"]).pack(anchor="w", padx=20)
        sub("Judge model (Ollama tag, e.g. llava)")
        ctk.CTkEntry(b, textvariable=self.judge_var,
                     placeholder_text="llava",
                     font=ctk.CTkFont(FN, 11)).pack(fill="x", padx=10)

        # ── voice / TTS ──────────────────────────────────────────────────────
        sec("NEURAL VOICE (edge-tts)")
        sub("Voice name (e.g. en-US-AndrewNeural, en-GB-SoniaNeural)")
        ctk.CTkEntry(b, textvariable=self.tts_var,
                     font=ctk.CTkFont(FN, 11)).pack(fill="x", padx=10)

        # ── session history ──────────────────────────────────────────────────
        sec("SESSION HISTORY")
        self._hist_box = ctk.CTkTextbox(b, height=110,
                                        font=ctk.CTkFont(FN, 9), wrap="word")
        self._hist_box.pack(fill="x", padx=10)
        self._hist_box.configure(state="disabled")

        # ── status + buttons ─────────────────────────────────────────────────
        self._status = ctk.CTkLabel(b, text="",
                                    font=ctk.CTkFont(FN, 11),
                                    text_color=C["success"], anchor="w")
        self._status.pack(fill="x", pady=(10, 0), padx=10)

        br = ctk.CTkFrame(b, fg_color="transparent")
        br.pack(fill="x", pady=(8, 4), padx=10)
        ctk.CTkButton(br, text="Save & Activate",
                      command=self._save, width=190,
                      font=ctk.CTkFont(FN, 12, "bold"),
                      fg_color="#10B981", hover_color="#059669",
                      corner_radius=6).pack(side="left")
        ctk.CTkButton(br, text="Hide to Tray",
                      command=self.win.withdraw, width=150,
                      font=ctk.CTkFont(FN, 11),
                      fg_color="#16161f", hover_color="#22222f",
                      corner_radius=6).pack(side="right")

        self._poll_history()

    # ── provider add-form ─────────────────────────────────────────────────────
    def _on_type_pick(self, choice: str):
        """Build/replace the input form when a provider type is chosen."""
        if self._form_frame:
            self._form_frame.destroy()
            self._form_frame = None
        if choice == PROVIDER_OPTIONS[0]:
            return

        ptype = self._ptype_from_label(choice)
        self._form_key_var.set("")
        self._form_model_var.set("")
        self._form_url_var.set("")

        frame = ctk.CTkFrame(self._form_container, fg_color=C["bg2"], corner_radius=6)
        frame.pack(fill="x", pady=4)
        self._form_frame = frame

        def sub(t):
            ctk.CTkLabel(frame, text=t, font=ctk.CTkFont(FN, 9),
                         text_color=C["muted"], anchor="w").pack(
                             fill="x", padx=10, pady=(6, 1))

        is_ollama = (ptype == "ollama")

        if not is_ollama:
            sub("API Key")
            ctk.CTkEntry(frame, textvariable=self._form_key_var,
                         placeholder_text="Paste your key here…",
                         show="•", font=ctk.CTkFont(FN, 11)).pack(
                             fill="x", padx=10)

        if ptype == "custom":
            sub("Base URL (e.g. https://openrouter.ai/api/v1)")
            ctk.CTkEntry(frame, textvariable=self._form_url_var,
                         placeholder_text="https://…",
                         font=ctk.CTkFont(FN, 11)).pack(fill="x", padx=10)

        sub("Model")
        model_row = ctk.CTkFrame(frame, fg_color="transparent")
        model_row.pack(fill="x", padx=10, pady=(0, 2))

        # start with safe models; user can fetch live ones
        self._model_menu = ctk.CTkOptionMenu(
            model_row,
            variable=self._form_model_var,
            values=SAFE_MODELS,
            font=ctk.CTkFont(FN, 11),
            width=260,
        )
        self._model_menu.pack(side="left", expand=True)
        self._form_model_var.set(SAFE_MODELS[0])

        def do_fetch():
            key  = self._form_key_var.get().strip()
            burl = self._form_url_var.get().strip()
            fetch_btn.configure(state="disabled", text="Fetching…")
            def _bg():
                models = fetch_models(ptype, key=key, base_url=burl)
                def _ui():
                    if models:
                        self._model_menu.configure(values=models)
                        self._form_model_var.set(models[0])
                    fetch_btn.configure(state="normal", text="↺ Fetch Models")
                self.win.after(0, _ui)
            threading.Thread(target=_bg, daemon=True).start()

        fetch_btn = ctk.CTkButton(model_row, text="↺ Fetch Models",
                                  command=do_fetch, width=120,
                                  font=ctk.CTkFont(FN, 10),
                                  fg_color=C["accent2"],
                                  hover_color="#574fcc", corner_radius=5)
        fetch_btn.pack(side="right", padx=(6, 0))

        # manual entry fallback
        ctk.CTkEntry(frame, textvariable=self._form_model_var,
                     placeholder_text="Or type model name manually…",
                     font=ctk.CTkFont(FN, 10)).pack(fill="x", padx=10, pady=(2, 4))

        add_btn = ctk.CTkButton(frame, text=f"+ Add {choice}",
                                command=lambda: self._add_provider(ptype, choice),
                                fg_color="#10B981", hover_color="#059669",
                                font=ctk.CTkFont(FN, 11, "bold"),
                                corner_radius=5)
        add_btn.pack(pady=(2, 8))

    def _ptype_from_label(self, label: str) -> str:
        lbl = label.lower()
        if "gemini"    in lbl: return "gemini"
        if "openai"    in lbl: return "openai"
        if "anthropic" in lbl: return "anthropic"
        if "grok"      in lbl: return "grok"
        if "deepseek"  in lbl: return "deepseek"
        if "ollama"    in lbl: return "ollama"
        return "custom"

    def _add_provider(self, ptype: str, label: str):
        key   = self._form_key_var.get().strip()
        model = self._form_model_var.get().strip()
        burl  = self._form_url_var.get().strip()
        if ptype != "ollama" and not key:
            self._status.configure(text="⚠ API Key is required.", text_color=C["error"])
            return
        if not model:
            self._status.configure(text="⚠ Model name is required.", text_color=C["error"])
            return
        entry: dict = {"type": ptype, "model": model, "label": label}
        if key:  entry["key"] = key
        if burl: entry["base_url"] = burl
        self.providers.append(entry)
        self._refresh_prov_list()
        # clear form
        self._form_key_var.set(""); self._form_model_var.set(""); self._form_url_var.set("")
        self._form_type_var.set(PROVIDER_OPTIONS[0])
        if self._form_frame:
            self._form_frame.destroy(); self._form_frame = None
        self._status.configure(text=f"✓ Added {label} ({model})", text_color=C["success"])

    def _remove_provider(self, idx: int):
        if 0 <= idx < len(self.providers):
            self.providers.pop(idx)
            self._refresh_prov_list()

    def _refresh_prov_list(self):
        for w in self._prov_list.winfo_children():
            w.destroy()
        if not self.providers:
            tk.Label(self._prov_list, text="  No providers yet — add one above.",
                     bg=C["bg"], fg=C["muted"],
                     font=(FN, 9)).pack(anchor="w", padx=10, pady=8)
            return
        for i, p in enumerate(self.providers):
            row = ctk.CTkFrame(self._prov_list, fg_color=C["bg2"], corner_radius=4)
            row.pack(fill="x", padx=6, pady=3)
            icon = {"gemini":"◈","openai":"⬡","anthropic":"♦",
                    "grok":"✦","deepseek":"◉","ollama":"⊛","custom":"⬟"
                    }.get(p.get("type",""), "▪")
            lbl  = f"{icon}  {p.get('label', p.get('type','?').capitalize())}  ·  {p.get('model','?')}"
            tk.Label(row, text=lbl, bg=C["bg2"], fg=C["text"],
                     font=(FN, 10)).pack(side="left", padx=8, pady=4)
            rem = tk.Label(row, text="✕", bg=C["bg2"], fg=C["muted"],
                           cursor="hand2", font=(FN, 10))
            rem.pack(side="right", padx=8)
            rem.bind("<Button-1>", lambda _, idx=i: self._remove_provider(idx))
            rem.bind("<Enter>",    lambda _, r=rem: r.config(fg=C["error"]))
            rem.bind("<Leave>",    lambda _, r=rem: r.config(fg=C["muted"]))

    # ── save ──────────────────────────────────────────────────────────────────
    def _save(self):
        self.cfg["hotkey"]           = self.hk_var.get().strip().lower() or "alt+s"
        self.cfg["voice_hotkey"]     = self.vhk_var.get().strip().lower() or "alt+v"
        self.cfg["lens_radius"]      = self.lens_var.get()
        self.cfg["capture_size"]     = self.cap_var.get()
        self.cfg["active_providers"] = self.providers
        self.cfg["use_ollama"]       = self.oll_var.get()
        self.cfg["ollama_model"]     = self.oll_model.get().strip()
        self.cfg["consensus"]        = self.cons_var.get()
        self.cfg["judge_model"]      = self.judge_var.get().strip()
        self.cfg["tts_voice"]        = self.tts_var.get().strip()
        save_cfg(self.cfg)
        self.on_save(self.cfg)
        self._hdr_hk.configure(text=self.cfg["hotkey"].upper())
        self._status.configure(
            text=f"✓ Saved!  {self.cfg['hotkey'].upper()} to analyse  ·  {self.cfg['voice_hotkey'].upper()} to talk.",
            text_color=C["success"])
        self.win.after(2500, self.win.withdraw)

    # ── history poll ──────────────────────────────────────────────────────────
    def _poll_history(self):
        if self.history_fn:
            items = self.history_fn()
            if items:
                lines = "\n".join(
                    f"[{e['time']}] {'✓' if e['status']=='success' else '✗'}  {e['text']}"
                    for e in reversed(items[-10:])
                )
                self._hist_box.configure(state="normal")
                self._hist_box.delete("0.0", "end")
                self._hist_box.insert("end", lines)
                self._hist_box.configure(state="disabled")
        self.win.after(3000, self._poll_history)

    def run(self): self.win.mainloop()


# ─────────────────────────────────────────────────────────────────────────────
#  AUDIO  (pygame — silent background playback, no media player)
# ─────────────────────────────────────────────────────────────────────────────
class AudioPlayer:
    def __init__(self, tts_voice: str = "en-US-AndrewNeural"):
        self.voice = tts_voice
        self._lock = threading.Lock()

    def speak(self, text: str, on_done: Optional[Callable] = None):
        threading.Thread(target=self._speak_bg,
                         args=(text, on_done), daemon=True).start()

    def _speak_bg(self, text: str, on_done):
        if not HAS_EDGE_TTS:
            print(f"[TTS] {text}")
            if on_done: on_done()
            return
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        tmp = None
        try:
            communicate = _edge_tts.Communicate(text, self.voice)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                tmp = f.name
            loop.run_until_complete(communicate.save(tmp))
            if HAS_PYGAME:
                with self._lock:
                    _pygame.mixer.music.load(tmp)
                    _pygame.mixer.music.play()
                    while _pygame.mixer.music.get_busy():
                        time.sleep(0.05)
                    _pygame.mixer.music.unload()
            else:
                # silent fallback: just wait approximate duration
                size = os.path.getsize(tmp)
                time.sleep(max(1.0, size / 16000))
        except Exception as e:
            print(f"[TTS] Error: {e}")
        finally:
            loop.close()
            if tmp and os.path.exists(tmp):
                try: os.unlink(tmp)
                except: pass
            if on_done: on_done()


# ─────────────────────────────────────────────────────────────────────────────
#  APP — master controller
# ─────────────────────────────────────────────────────────────────────────────
class App:
    def __init__(self):
        self.cfg     = load_cfg()
        self.engine  = AIEngine(self.cfg)
        self._busy   = False
        self._vbusy  = False
        self.history: List[dict] = []

        # Audio
        self.audio = AudioPlayer(self.cfg.get("tts_voice", "en-US-AndrewNeural"))

        # Whisper
        self._whisper = None
        if HAS_WHISPER:
            print("[MouseLens] Loading Whisper 'tiny'…")
            try:
                self._whisper = _whisper.load_model("tiny")
            except Exception as e:
                print(f"[MouseLens] Whisper load failed: {e}")

        # SR
        self._recognizer = sr.Recognizer() if HAS_SR else None
        self._mic        = sr.Microphone() if HAS_SR else None

        # Build UI
        self.settings = SettingsWindow(
            self.cfg, on_save=self._reload,
            history_fn=lambda: self.history,
        )
        # Overlay attaches to settings CTk root
        self.overlay = Overlay(self.settings.win, self.cfg)
        self.settings.overlay = self.overlay   # link for live slider

        self._bind_hotkeys()

    # ── hotkeys ───────────────────────────────────────────────────────────────
    def _bind_hotkeys(self):
        keyboard.unhook_all()
        hk  = self.cfg.get("hotkey",       "alt+s").lower()
        vhk = self.cfg.get("voice_hotkey", "alt+v").lower()
        keyboard.add_hotkey(hk,  self._on_screen, suppress=True)
        keyboard.add_hotkey(vhk, self._on_voice,  suppress=True)
        print(f"[MouseLens] Hotkeys → {hk.upper()} (screen)  {vhk.upper()} (voice)")

    def _reload(self, cfg: dict):
        self.cfg    = cfg
        self.engine = AIEngine(cfg)
        self.audio  = AudioPlayer(cfg.get("tts_voice", "en-US-AndrewNeural"))
        # Rebuild overlay
        for attr in ("_lw", "_fw", "_bw"):
            try: getattr(self.overlay, attr).destroy()
            except: pass
        self.overlay = Overlay(self.settings.win, cfg)
        self.settings.overlay = self.overlay
        self._bind_hotkeys()
        print("[MouseLens] Reloaded.")

    # ── screen analysis ───────────────────────────────────────────────────────
    def _on_screen(self):
        if self._busy: return
        self._busy = True
        mx, my = pyautogui.position()
        self.settings.win.after(0, lambda: self._screen_begin(mx, my))

    def _screen_begin(self, mx, my):
        self.overlay.show_loading()
        threading.Thread(target=self._screen_worker, args=(mx, my), daemon=True).start()

    def _screen_worker(self, mx, my):
        try:
            half = self.cfg.get("capture_size", 400) // 2
            img  = ImageGrab.grab(bbox=(max(0, mx-half), max(0, my-half),
                                        mx+half, my+half))
            text, status = self.engine.analyze(img)
        except Exception as e:
            text, status = f"Capture error:\n{e}", "error"
            print(f"[MouseLens] Screen error: {e}")
        finally:
            self._busy = False

        def ui():
            self.overlay.show_result(text, status)
            if status == "success":
                try:
                    self.settings.win.clipboard_clear()
                    self.settings.win.clipboard_append(text)
                except: pass
            self.history.append({"time": datetime.now().strftime("%H:%M:%S"),
                                  "text": text[:200], "status": status})
        self.settings.win.after(0, ui)

    # ── voice command ─────────────────────────────────────────────────────────
    def _on_voice(self):
        if self._vbusy or not HAS_SR: return
        self._vbusy = True
        self.settings.win.after(0, self.overlay.show_loading)
        threading.Thread(target=self._voice_worker, daemon=True).start()

    def _voice_worker(self):
        text_q = None
        try:
            with self._mic as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.4)
                print("[Voice] Listening…")
                audio = self._recognizer.listen(source, timeout=8, phrase_time_limit=6)
            # Google first
            try:
                text_q = self._recognizer.recognize_google(audio)
                print(f"[Voice] Google: {text_q}")
            except Exception:
                text_q = None
            # Whisper fallback
            if not text_q and self._whisper:
                print("[Voice] Trying Whisper…")
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(audio.get_wav_data()); tmp = f.name
                try:
                    res = self._whisper.transcribe(tmp, fp16=False)
                    text_q = res["text"].strip()
                    print(f"[Voice] Whisper: {text_q}")
                finally:
                    try: os.unlink(tmp)
                    except: pass
        except Exception as e:
            print(f"[Voice] Mic error: {e}")

        if not text_q:
            result, status = "I didn't catch that — please try again.", "error"
        else:
            result, status = self.engine.analyze_text(text_q)

        def ui():
            self.overlay.show_result(result, status)
            self.overlay.set_state("talking")
            self.audio.speak(result, on_done=lambda: self.settings.win.after(
                0, lambda: self.overlay.set_state("idle")))
            if status == "success":
                try:
                    self.settings.win.clipboard_clear()
                    self.settings.win.clipboard_append(result)
                except: pass
            self.history.append({"time": datetime.now().strftime("%H:%M:%S"),
                                  "text": result[:200], "status": status})
            self._vbusy = False
        self.settings.win.after(0, ui)

    def run(self):
        hk  = self.cfg.get("hotkey",       "alt+s").upper()
        vhk = self.cfg.get("voice_hotkey", "alt+v").upper()
        print(f"[MouseLens] Ready  ·  {hk} = screen  ·  {vhk} = voice")
        self.settings.run()


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    App().run()
