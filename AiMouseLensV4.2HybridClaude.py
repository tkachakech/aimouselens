"""
╔══════════════════════════════════════════════════════════════════╗
║      AI MOUSE-LENS  ·  CONSENSUS EDITION  v4.2                   ║
║  Mode 1: Screen Analysis  ·  Mode 2: Voice Q&A                   ║
║  Mode 3: Contextual Voice Chat  ·  Narrate Toggle                ║
║  True Silent Failover  ·  Dynamic Voice Dropdown                 ║
║  API Key Auto-Detection  ·  Pygame silent audio                  ║
╚══════════════════════════════════════════════════════════════════╝

pip install customtkinter pillow pyautogui keyboard requests
         speechrecognition edge-tts openai-whisper pyaudio pygame

python main.py
"""

# ── Suppress pygame noise BEFORE importing it ────────────────────────────────
import os, warnings
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"
warnings.filterwarnings("ignore", category=UserWarning, module="pygame")

# ── stdlib ───────────────────────────────────────────────────────────────────
import asyncio, base64, difflib, io, json, math, sys
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
    _pygame.mixer.pre_init(44100, -16, 2, 512)
    _pygame.mixer.init()
    HAS_PYGAME = True
except Exception as _pe:
    HAS_PYGAME = False
    print(f"[MouseLens] pygame unavailable ({_pe}) – pip install pygame")

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
CONFIG_PATH   = Path.home() / ".ai_mouselens_v4_config.json"
BUBBLE_W      = 380
AUTO_HIDE_SEC = 15
TRACK_MS      = 16   # ~62 fps

FACE = {
    "idle":     "( •_•)",
    "fast":     "(⊙_⊙)",
    "thinking": "(－‸－)",
    "success":  "(＾▽＾)",
    "error":    "(╯°□°）╯",
    "talking":  "( ◦0◦)",
    "listening":"( •ᴗ•)",
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
    "warning":   "#ffaa33",
    "lens_ring": "#00c8ff",
    "transp":    "#010101",
}

def _sans():
    if sys.platform.startswith("win"):    return "Segoe UI"
    if sys.platform.startswith("darwin"): return "Helvetica"
    return "Ubuntu"

FN = _sans()
F_NORM  = (FN, 11)
F_BOLD  = (FN, 11, "bold")
F_SMALL = (FN, 9)
F_HEAD  = (FN, 20, "bold")

# ── Prompts ──────────────────────────────────────────────────────────────────
PROMPT_SCREEN = (
    "You are AI Mouse-Lens, an ultra-concise screen analyst. "
    "The image shows a screenshot region under the user's cursor. "
    "In 2–4 short sentences: describe what is visible, then give one sharp "
    "actionable insight. Be direct. No preamble."
)
PROMPT_VOICE = (
    "You are AI Mouse-Lens, a witty cursor companion. "
    "Answer the user's spoken question in 1–2 concise sentences. "
    "Be friendly and direct. No preamble."
)
PROMPT_CONTEXT_TPL = (
    "You are AI Mouse-Lens. The user is looking at a screenshot region and "
    "has asked: \"{question}\"\n"
    "Answer their question about what is visible in the image in 2–4 "
    "concise sentences. Be direct and helpful. No preamble."
)
PROMPT_OLLAMA = (
    "You are a visual analysis specialist. "
    "Describe what is in the image and give one actionable insight. "
    "No gibberish."
)
PROMPT_JUDGE = (
    "You are a fair judge reviewing two AI responses. "
    "Pick the better, more accurate answer and output ONLY the final "
    "2–4 sentence response."
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
    "hotkey":            "alt+s",
    "voice_hotkey":      "alt+v",
    "context_hotkey":    "alt+j",
    "lens_radius":       38,
    "capture_size":      400,
    "active_providers":  [],
    "use_ollama":        False,
    "ollama_model":      "moondream",
    "consensus":         True,
    "judge_model":       "llava",
    "tts_voice":         "en-US-AndrewNeural",
    "read_screen_results": False,
}

# ── Smart Quick‑Add providers ────────────────────────────────────────────────
SMART_PROVIDERS = {
    "Gemini Flash": {"type": "gemini", "model": "gemini-1.5-flash", "base_url": ""},
    "Groq (Fast Voice)": {"type": "custom", "model": "llama-3.3-70b-versatile", "base_url": "https://api.groq.com/openai/v1"},
    "SambaNova (Qwen)": {"type": "custom", "model": "Qwen2.5-72B-Instruct", "base_url": "https://api.sambanova.ai/v1"},
    "DeepSeek": {"type": "deepseek", "model": "deepseek-chat", "base_url": "https://api.deepseek.com/v1/chat/completions"}
}

# ── Auto-detection rules: (prefix, type, model, base_url, display_label) ────
KEY_AUTODETECT = [
    # Anthropic check MUST come before generic sk- check
    ("sk-ant-",  "anthropic", "claude-3-5-sonnet-20241022", "",    "Anthropic (auto)"),
    ("AIza",     "gemini",    "gemini-1.5-flash",           "",    "Gemini (auto)"),
    ("gsk_",     "custom",    "llama-3.3-70b-versatile",
                              "https://api.groq.com/openai/v1",    "Groq (auto)"),
    ("sk-",      "openai",    "gpt-4o-mini",                "",    "OpenAI (auto)"),
]

def detect_key_provider(key: str) -> Optional[dict]:
    """
    Inspect the key prefix and return a pre-filled provider dict,
    or None if the prefix is unrecognised.
    """
    k = key.strip()
    for prefix, ptype, model, base_url, label in KEY_AUTODETECT:
        if k.startswith(prefix):
            entry = {"label": label, "type": ptype, "model": model, "key": k}
            if base_url:
                entry["base_url"] = base_url
            return entry
    return None

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
#  ERROR TRANSLATION
# ─────────────────────────────────────────────────────────────────────────────
def _friendly_error(raw: str) -> Tuple[str, str]:
    """
    Returns (user_message, severity).
    severity: 'rate_limit' | 'billing' | 'generic'
    """
    s = str(raw)
    if "429" in s:
        return "Rate limited (429) — please wait or use Ollama.", "rate_limit"
    if "402" in s:
        return "Out of credits (402) — check provider billing.", "billing"
    if "401" in s:
        return "Unauthorized (401) — check your API key.", "generic"
    if "404" in s:
        return "Model not found (404) — check model name in Settings.", "generic"
    return s, "generic"


# ─────────────────────────────────────────────────────────────────────────────
#  AI ENGINE
# ─────────────────────────────────────────────────────────────────────────────
class AIEngine:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    # ── utils ────────────────────────────────────────────────────────────────
    @staticmethod
    def _b64(img) -> str:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    @staticmethod
    def _sim(a: str, b: str) -> float:
        if not a or not b: return 0.0
        return difflib.SequenceMatcher(None, a[:200], b[:200]).ratio()

    # ── image providers (accept custom_prompt) ───────────────────────────────
    def _gemini_img(self, b64: str, p: dict, prompt: str) -> str:
        model = p.get("model", "gemini-1.5-flash")
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={p['key']}")
        body = {"contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": "image/png", "data": b64}},
        ]}]}
        r = _req.post(url, json=body, timeout=30)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

    def _openai_img(self, b64: str, p: dict, prompt: str,
                    base_url: str = "") -> str:
        model = p.get("model", "gpt-4o-mini")
        url   = base_url or "https://api.openai.com/v1/chat/completions"
        body  = {"model": model, "max_tokens": 350,
                 "messages": [{"role": "user", "content": [
                     {"type": "text",      "text": prompt},
                     {"type": "image_url", "image_url": {
                         "url": f"data:image/png;base64,{b64}"}},
                 ]}]}
        r = _req.post(url, headers={"Authorization": f"Bearer {p['key']}",
                                    "Content-Type": "application/json"},
                      json=body, timeout=30)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    def _anthropic_img(self, b64: str, p: dict, prompt: str) -> str:
        model = p.get("model", "claude-3-haiku-20240307")
        body  = {"model": model, "max_tokens": 350,
                 "messages": [{"role": "user", "content": [
                     {"type": "text",  "text": prompt},
                     {"type": "image", "source": {
                         "type": "base64",
                         "media_type": "image/png",
                         "data": b64}},
                 ]}]}
        r = _req.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": p["key"],
                                "anthropic-version": "2023-06-01",
                                "Content-Type": "application/json"},
                      json=body, timeout=30)
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()

    def _grok_img(self, b64, p, prompt):
        return self._openai_img(b64, p, prompt,
                                "https://api.x.ai/v1/chat/completions")

    def _deepseek_img(self, b64, p, prompt):
        return self._openai_img(b64, p, prompt,
                                "https://api.deepseek.com/v1/chat/completions")

    def _ollama_img(self, b64: str, p: dict, prompt: str) -> str:
        model = p.get("model", self.cfg.get("ollama_model", "moondream"))
        r = _req.post("http://localhost:11434/api/generate",
                      json={"model": model, "prompt": prompt,
                            "images": [b64], "stream": False}, timeout=60)
        r.raise_for_status()
        return r.json()["response"].strip()

    # ── text providers ───────────────────────────────────────────────────────
    def _gemini_txt(self, q: str, p: dict) -> str:
        model = p.get("model", "gemini-1.5-flash")
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={p['key']}")
        r = _req.post(url, json={"contents": [{"parts": [
            {"text": PROMPT_VOICE + "\nUser: " + q}]}]}, timeout=30)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

    def _openai_txt(self, q: str, p: dict, base_url: str = "") -> str:
        model = p.get("model", "gpt-4o-mini")
        url   = base_url or "https://api.openai.com/v1/chat/completions"
        r = _req.post(url, headers={"Authorization": f"Bearer {p['key']}",
                                    "Content-Type": "application/json"},
                      json={"model": model, "max_tokens": 200,
                            "messages": [
                                {"role": "system", "content": PROMPT_VOICE},
                                {"role": "user",   "content": q}]},
                      timeout=30)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    def _anthropic_txt(self, q: str, p: dict) -> str:
        model = p.get("model", "claude-3-haiku-20240307")
        r = _req.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": p["key"],
                                "anthropic-version": "2023-06-01",
                                "Content-Type": "application/json"},
                      json={"model": model, "max_tokens": 200,
                            "system": PROMPT_VOICE,
                            "messages": [{"role": "user", "content": q}]},
                      timeout=30)
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()

    def _grok_txt(self, q, p):
        return self._openai_txt(q, p, "https://api.x.ai/v1/chat/completions")

    def _deepseek_txt(self, q, p):
        return self._openai_txt(q, p,
                                "https://api.deepseek.com/v1/chat/completions")

    def _ollama_txt(self, q: str, p: dict) -> str:
        model = p.get("model", self.cfg.get("ollama_model", "moondream"))
        r = _req.post("http://localhost:11434/api/generate",
                      json={"model": model,
                            "prompt": PROMPT_VOICE + "\nUser: " + q,
                            "stream": False}, timeout=60)
        r.raise_for_status()
        return r.json()["response"].strip()

    # ── dispatch ─────────────────────────────────────────────────────────────
    def _call_img(self, b64: str, p: dict,
                  custom_prompt: Optional[str] = None) -> str:
        prompt = custom_prompt or PROMPT_SCREEN
        t = p.get("type", "")
        # Groq / SambaNova + any OpenAI-compatible: route through OpenAI handler
        if t in ["openai", "grok", "deepseek", "custom", "groq", "sambanova"]:
            target_url = p.get("base_url") or "https://api.openai.com/v1/chat/completions"
            return self._openai_img(b64, p, prompt, target_url)

        if t == "gemini":    return self._gemini_img(b64, p, prompt)
        if t == "anthropic": return self._anthropic_img(b64, p, prompt)
        if t == "ollama":    return self._ollama_img(b64, p, prompt)
        raise ValueError(f"Unknown provider type: {t}")

    def _call_txt(self, q: str, p: dict) -> str:
        t = p.get("type", "")
        if t == "gemini":    return self._gemini_txt(q, p)
        if t == "openai":    return self._openai_txt(q, p)
        if t == "anthropic": return self._anthropic_txt(q, p)
        if t == "grok":      return self._grok_txt(q, p)
        if t == "deepseek":  return self._deepseek_txt(q, p)
        if t == "ollama":    return self._ollama_txt(q, p)
        if t == "custom":
            return self._openai_txt(q, p, p.get("base_url", ""))
        raise ValueError(f"Unknown provider type: {t}")

    # ── ollama emergency fallback ─────────────────────────────────────────────
    def _try_ollama_fallback(self, b64_or_q: str,
                             is_image: bool,
                             custom_prompt: Optional[str] = None) -> Optional[str]:
        """Attempt local Ollama as last resort when cloud providers fail."""
        providers = self.cfg.get("active_providers", [])
        ollama_p  = next((p for p in providers if p.get("type") == "ollama"), None)
        if not ollama_p and not self.cfg.get("use_ollama", False):
            return None
        if not ollama_p:
            ollama_p = {"type": "ollama",
                        "model": self.cfg.get("ollama_model", "moondream")}
        try:
            print("[MouseLens] ⚡ Ollama emergency fallback…")
            if is_image:
                return self._ollama_img(b64_or_q, ollama_p,
                                        custom_prompt or PROMPT_OLLAMA)
            else:
                return self._ollama_txt(b64_or_q, ollama_p)
        except Exception as e:
            print(f"[MouseLens] Ollama fallback failed: {e}")
            return None

    # ── judge ─────────────────────────────────────────────────────────────────
    def _judge(self, b64: str, a: str, b_txt: str,
               text_mode: bool = False) -> str:
        model  = self.cfg.get("judge_model", "llava")
        prompt = (f"{PROMPT_JUDGE}\nResponse A: {a}\n"
                  f"Response B: {b_txt}\nFinal answer:")
        try:
            body: dict = {"model": model, "prompt": prompt, "stream": False}
            if not text_mode and b64:
                body["images"] = [b64]
            r = _req.post("http://localhost:11434/api/generate",
                          json=body, timeout=60)
            r.raise_for_status()
            return r.json()["response"].strip()
        except Exception as e:
            print(f"[Judge] {e}")
            return a if len(a) >= len(b_txt) else b_txt

    # ── silent error classifier ───────────────────────────────────────────────
    @staticmethod
    def _is_soft_error(exc_str: str) -> bool:
        """Return True for 429/402 — errors we silently skip over."""
        return "429" in exc_str or "402" in exc_str

    # ── parallel consensus (silent failover) ─────────────────────────────────
    def _consensus(self, call_fn, providers, b64_or_q,
                   text_mode: bool = False,
                   custom_prompt: Optional[str] = None):
        """
        Runs Ollama + best available cloud provider in parallel.
        Cloud slot silently iterates through providers on 429/402.
        UI stays in Thinking… throughout; only returns None to let
        _sequential handle the case where nothing worked.
        """
        ollama_ps = [p for p in providers if p.get("type") == "ollama"]
        cloud_ps  = [p for p in providers
                     if p.get("type") != "ollama"
                     and (p.get("key") or "").strip()]
        if not ollama_ps or not cloud_ps:
            return None

        op = ollama_ps[0]
        results: dict = {}

        def run_ollama():
            try:
                if text_mode:
                    results["ollama"] = call_fn(b64_or_q, op)
                else:
                    results["ollama"] = call_fn(b64_or_q, op, custom_prompt)
            except Exception as e:
                print(f"[Consensus] Ollama error: {e}")

        def run_cloud():
            for cp in cloud_ps:
                name = cp.get("label") or cp.get("type", "?").capitalize()
                try:
                    print(f"[Consensus] → {name} ({cp.get('model','?')})…")
                    if text_mode:
                        results["cloud"] = call_fn(b64_or_q, cp)
                    else:
                        results["cloud"] = call_fn(b64_or_q, cp, custom_prompt)
                    print(f"[Consensus] ✓ {name}")
                    return
                except Exception as e:
                    s = str(e)
                    if self._is_soft_error(s):
                        print(f"[Consensus] ⇢ {name} soft-error ({s[:60]}), "
                              f"silently trying next…")
                    else:
                        print(f"[Consensus] ✗ {name}: {s[:80]}")

        t1 = threading.Thread(target=run_ollama, daemon=True)
        t2 = threading.Thread(target=run_cloud,  daemon=True)
        t1.start(); t2.start(); t1.join(30); t2.join(30)

        if "ollama" in results and "cloud" in results:
            if self._sim(results["ollama"], results["cloud"]) > 0.5:
                return results["cloud"], "success"
            print("[Consensus] Conflict → judge")
            b64 = "" if text_mode else b64_or_q
            return self._judge(b64, results["ollama"],
                                results["cloud"], text_mode), "success"
        if "cloud"  in results: return results["cloud"],  "success"
        if "ollama" in results: return results["ollama"], "success"
        return None   # all failed — let _sequential handle final error

    # ── sequential fallback (true silent failover) ───────────────────────────
    def _sequential(self, call_fn, providers, b64_or_q,
                    is_image: bool = True,
                    custom_prompt: Optional[str] = None) -> Tuple[str, str]:
        """
        Iterates every cloud provider.  429/402 errors are caught silently
        (terminal log only — UI stays in Thinking…).  After all cloud
        providers are exhausted, tries Ollama emergency fallback.
        Only if everything fails does it return a single calm error.
        """
        if not providers:
            return ("No providers configured — add one in Settings.", "error")

        cloud_providers = [p for p in providers if p.get("type") != "ollama"]

        for p in cloud_providers:
            name = p.get("label") or p.get("type", "?").capitalize()
            try:
                print(f"[MouseLens] → {name} ({p.get('model','?')})…")
                if is_image:
                    result = call_fn(b64_or_q, p, custom_prompt)
                else:
                    result = call_fn(b64_or_q, p)
                print(f"[MouseLens] ✓ {name}")
                return result, "success"
            except Exception as exc:
                s = str(exc)
                friendly, _ = _friendly_error(s)
                if self._is_soft_error(s):
                    # Silent skip — terminal log only, UI remains in Thinking…
                    print(f"[MouseLens] ⇢ {name} soft-error ({friendly}), "
                          f"silently trying next provider…")
                else:
                    print(f"[MouseLens] ✗ {name}: {friendly}")

        # ── Ollama emergency fallback ────────────────────────────────────────
        print("[MouseLens] All cloud providers exhausted — trying Ollama…")
        fb = self._try_ollama_fallback(b64_or_q, is_image, custom_prompt)
        if fb:
            return fb, "success"

        # ── Everything failed — one calm message shown/spoken ────────────────
        return "All AI providers are currently unavailable.", "error"

    # ── public API ────────────────────────────────────────────────────────────
    def _active(self) -> List[dict]:
        return self.cfg.get("active_providers", [])

    def analyze(self, img,
                custom_prompt: Optional[str] = None) -> Tuple[str, str]:
        b64 = self._b64(img)
        if self.cfg.get("consensus", True):
            r = self._consensus(self._call_img, self._active(), b64,
                                custom_prompt=custom_prompt)
            if r is not None: return r
        return self._sequential(self._call_img, self._active(), b64,
                                is_image=True, custom_prompt=custom_prompt)

    def analyze_text(self, q: str) -> Tuple[str, str]:
        if self.cfg.get("consensus", True):
            r = self._consensus(self._call_txt, self._active(), q,
                                text_mode=True)
            if r is not None: return r
        return self._sequential(self._call_txt, self._active(), q,
                                is_image=False)


# ─────────────────────────────────────────────────────────────────────────────
#  FETCH MODELS
# ─────────────────────────────────────────────────────────────────────────────
def fetch_models(ptype: str, key: str = "", base_url: str = "") -> List[str]:
    try:
        fetch_url = ""
        headers = {}

        if ptype == "gemini" and key:
            fetch_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
        elif ptype == "ollama":
            fetch_url = "http://localhost:11434/api/tags"
        elif key:
            fetch_url = base_url.rstrip("/") + "/models" if base_url else "https://api.openai.com/v1/models"
            headers = {"Authorization": f"Bearer {key}"}

        if fetch_url:
            r = _req.get(fetch_url, headers=headers, timeout=10)
            if r.ok:
                data = r.json()
                if "models" in data:
                    return [m.get("name", m.get("id")).split("/")[-1] for m in data["models"] if ptype != "gemini" or "generateContent" in m.get("supportedGenerationMethods", [])]
                if "data" in data:
                    return sorted([m["id"] for m in data["data"]])
    except Exception as e:
        print(f"[Models] Fetch failed for {ptype}: {e}")
    return SAFE_MODELS[:]


# ─────────────────────────────────────────────────────────────────────────────
#  OVERLAY
# ─────────────────────────────────────────────────────────────────────────────
class Overlay:
    def __init__(self, root: tk.Misc, cfg: dict):
        self.root = root
        self.cfg  = cfg
        self._state   = "idle"
        self._mx = self._my = 0
        self._last_mx = self._last_my = 0
        self._speed   = 0.0
        self._bubble_vis = False
        self._hide_job   = None
        self._phi        = 0.0
        self.lens_r = int(cfg.get("lens_radius", 38))
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
        cv = tk.Canvas(w, width=S, height=S,
                       bg=C["transp"], highlightthickness=0)
        cv.pack()
        self._lw = w; self._lc = cv; self._ls = S
        self._draw_lens(C["lens_ring"], 2)

    def _draw_lens(self, color: str, w: int = 2):
        if not self._lw.winfo_exists(): return
        cv = self._lc; S = self._ls; r = self.lens_r
        pad = 6; t = max(4, r // 6)
        cv.delete("all")
        cv.create_oval(pad-3, pad-3, S-pad+3, S-pad+3,
                       outline=color, width=1, dash=(3, 7), stipple="gray25")
        cv.create_oval(pad, pad, S-pad, S-pad, outline=color, width=w)
        cx, cy = S // 2, S // 2
        for dx, dy, ex, ey in [
            (-r, 0, -r+t, 0), (r-t, 0, r, 0),
            (0, -r, 0, -r+t), (0, r-t, 0, r)
        ]:
            cv.create_line(cx+dx, cy+dy, cx+ex, cy+ey, fill=color, width=1)

    def _build_face(self):
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-transparentcolor", C["transp"])
        w.configure(bg=C["transp"])
        lbl = tk.Label(w, text=FACE["idle"], fg=C["accent"],
                       bg=C["transp"], font=(FN, 11, "bold"), padx=4, pady=1)
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
        hdr = tk.Frame(inner, bg=C["bg"], padx=10, pady=7)
        hdr.pack(fill="x")
        self._dot = tk.Label(hdr, text="◉", fg=C["accent"],
                             bg=C["bg"], font=(FN, 10, "bold"))
        self._dot.pack(side="left")
        self._bubble_title = tk.Label(hdr, text="  AI Mouse-Lens",
                                      fg=C["text"], bg=C["bg"],
                                      font=(FN, 10, "bold"))
        self._bubble_title.pack(side="left")
        xb = tk.Label(hdr, text=" ✕ ", fg=C["muted"],
                      bg=C["bg"], cursor="hand2", font=(FN, 10))
        xb.pack(side="right")
        xb.bind("<Button-1>", lambda _: self.hide_bubble())
        xb.bind("<Enter>",    lambda _: xb.config(fg=C["text"]))
        xb.bind("<Leave>",    lambda _: xb.config(fg=C["muted"]))
        tk.Frame(inner, bg=C["border"], height=1).pack(fill="x")
        body = tk.Frame(inner, bg=C["bg2"], padx=12, pady=10)
        body.pack(fill="both", expand=True)
        self._btxt = tk.Label(body, text="", fg=C["text"], bg=C["bg2"],
                              font=F_SMALL, wraplength=BUBBLE_W - 36,
                              justify="left", anchor="nw")
        self._btxt.pack(fill="both", expand=True)
        ftr = tk.Frame(inner, bg=C["bg2"], padx=12)
        ftr.pack(fill="x", pady=(0, 7))
        self._btimer = tk.Label(ftr, text="", fg=C["muted"],
                                bg=C["bg2"], font=(FN, 8))
        self._btimer.pack(side="left")
        self._mode_lbl = tk.Label(ftr, text="", fg=C["accent2"],
                                  bg=C["bg2"], font=(FN, 8))
        self._mode_lbl.pack(side="right")
        self._bw = w

    # ── state API ─────────────────────────────────────────────────────────────
    def set_state(self, state: str):
        self._state = state
        fc = {
            "idle":      C["accent"],
            "fast":      C["accent"],
            "thinking":  C["thinking"],
            "success":   C["success"],
            "error":     C["error"],
            "talking":   C["accent"],
            "listening": C["warning"],
        }.get(state, C["accent"])
        if self._fw.winfo_exists():
            self._fl.config(text=FACE.get(state, FACE["idle"]), fg=fc)
        rc = {
            "thinking":  C["thinking"],
            "success":   C["success"],
            "error":     C["error"],
            "listening": C["warning"],
        }.get(state, C["lens_ring"])
        self._draw_lens(rc, w=3 if state in ("thinking", "listening") else 2)

    def show_loading(self, mode_label: str = "Mode 1"):
        self.set_state("thinking")
        if not self._bw.winfo_exists(): return
        self._dot.config(fg=C["thinking"])
        self._btxt.config(text="Analyzing…", fg=C["thinking"])
        self._btimer.config(text="")
        self._mode_lbl.config(text=mode_label)
        self._bubble_vis = True
        self._bw.deiconify(); self._bw.lift()
        self._place_bubble()

    def show_listening(self):
        self.set_state("listening")
        if not self._bw.winfo_exists(): return
        self._dot.config(fg=C["warning"])
        self._btxt.config(text="Listening for your question…", fg=C["warning"])
        self._btimer.config(text="")
        self._mode_lbl.config(text="Mode 3")
        self._bubble_vis = True
        self._bw.deiconify(); self._bw.lift()
        self._place_bubble()

    def show_result(self, text: str, status: str,
                    mode_label: str = ""):
        self.set_state(status)
        if not self._bw.winfo_exists(): return
        col = C["success"] if status == "success" else C["error"]
        self._dot.config(fg=col)
        self._btxt.config(text=text, fg=C["text"])
        self._btimer.config(text=f"auto-close {AUTO_HIDE_SEC}s")
        if mode_label:
            self._mode_lbl.config(text=mode_label)
        self._bubble_vis = True
        self._bw.deiconify(); self._bw.lift()
        self._place_bubble()
        if self._hide_job: self.root.after_cancel(self._hide_job)
        self._hide_job = self.root.after(AUTO_HIDE_SEC * 1000,
                                          self.hide_bubble)

    def hide_bubble(self):
        if self._hide_job:
            self.root.after_cancel(self._hide_job)
            self._hide_job = None
        if self._bw.winfo_exists(): self._bw.withdraw()
        self._bubble_vis = False
        self.set_state("idle")

    # ── placement ─────────────────────────────────────────────────────────────
    def _place_bubble(self):
        if not self._bw.winfo_exists(): return
        self._bw.update_idletasks()
        bh = self._bw.winfo_reqheight() or 130
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
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

        if self._state == "idle" and self._fw.winfo_exists():
            self._fl.config(
                text=FACE["fast"] if self._speed > 18 else FACE["idle"],
                fg=C["accent"])

        if self._lw.winfo_exists():
            S = self._ls
            self._lw.geometry(f"{S}x{S}+{mx - S//2}+{my - S//2}")

        if self._fw.winfo_exists():
            self._fw.update_idletasks()
            fw = max(self._fw.winfo_reqwidth(), 70)
            fh = max(self._fw.winfo_reqheight(), 20)
            self._fw.geometry(
                f"{fw}x{fh}+{mx - fw//2}+{my + self.lens_r + 5}")

        if self._bubble_vis: self._place_bubble()

        if self._state in ("thinking", "listening") and self._lw.winfo_exists():
            self._phi = (self._phi + 0.14) % (2 * math.pi)
            try:
                self._lw.attributes("-alpha",
                                    0.72 + 0.23 * math.sin(self._phi))
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
        self._lw.geometry(
            f"{S}x{S}+{self._mx - S//2}+{self._my - S//2}")


# ─────────────────────────────────────────────────────────────────────────────
#  SETTINGS WINDOW
# ─────────────────────────────────────────────────────────────────────────────
class SettingsWindow:
    def __init__(self, cfg: dict, on_save,
                 overlay: Optional[Overlay] = None,
                 history_fn: Optional[Callable[[], List[dict]]] = None):
        self.cfg        = cfg
        self.on_save    = on_save
        self.overlay    = overlay
        self.history_fn = history_fn
        self.providers: List[dict] = list(cfg.get("active_providers", []))

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.win = ctk.CTk()
        self.win.title("AI Mouse-Lens  ·  Settings  v4")
        self.win.geometry("560x900")
        self.win.resizable(False, True)
        self._init_vars()
        self._build()

    def _init_vars(self):
        cfg = self.cfg
        self.hk_var      = tk.StringVar(value=cfg.get("hotkey",         "alt+s"))
        self.vhk_var     = tk.StringVar(value=cfg.get("voice_hotkey",   "alt+v"))
        self.ctx_hk_var  = tk.StringVar(value=cfg.get("context_hotkey", "alt+j"))
        self.lens_var    = tk.IntVar(value=int(cfg.get("lens_radius",  38)))
        self.cap_var     = tk.IntVar(value=int(cfg.get("capture_size", 400)))
        self.lens_str    = tk.StringVar(value=str(self.lens_var.get()))
        self.cap_str     = tk.StringVar(value=str(self.cap_var.get()))
        self.oll_var     = tk.BooleanVar(value=cfg.get("use_ollama", False))
        self.oll_model   = tk.StringVar(value=cfg.get("ollama_model", "moondream"))
        self.cons_var    = tk.BooleanVar(value=cfg.get("consensus", True))
        self.judge_var   = tk.StringVar(value=cfg.get("judge_model", "llava"))
        self.tts_var     = tk.StringVar(value=cfg.get("tts_voice", "en-US-AndrewNeural"))
        self.narrate_var = tk.BooleanVar(value=cfg.get("read_screen_results", False))

    # ── layout ────────────────────────────────────────────────────────────────
    def _build(self):
        w = self.win
        hdr = ctk.CTkFrame(w, fg_color="#07070e", corner_radius=0, height=60)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="◉  AI Mouse-Lens",
                     font=ctk.CTkFont(FN, 20, "bold"),
                     text_color=C["accent"]).pack(side="left", padx=18)
        self._hdr_hk = ctk.CTkLabel(
            hdr, text=self.cfg["hotkey"].upper(),
            font=ctk.CTkFont(FN, 10), text_color=C["muted"])
        self._hdr_hk.pack(side="right", padx=18)

        scroll = ctk.CTkScrollableFrame(w, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=6, pady=4)
        b = scroll

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
        sub("Mode 1 · Screen Analysis")
        ctk.CTkEntry(b, textvariable=self.hk_var,
                     placeholder_text="alt+s",
                     font=ctk.CTkFont(FN, 11)).pack(fill="x", padx=10)
        sub("Mode 2 · Voice Q&A")
        ctk.CTkEntry(b, textvariable=self.vhk_var,
                     placeholder_text="alt+v",
                     font=ctk.CTkFont(FN, 11)).pack(fill="x", padx=10)
        sub("Mode 3 · Contextual Voice Chat (screenshot + voice)")
        ctk.CTkEntry(b, textvariable=self.ctx_hk_var,
                     placeholder_text="alt+j",
                     font=ctk.CTkFont(FN, 11)).pack(fill="x", padx=10)

        # ── lens + capture ───────────────────────────────────────────────────
        sec("LENS & CAPTURE")
        sub("Lens ring radius (px)")

        def on_lens(val):
            v = int(float(val)); self.lens_str.set(str(v))
            if self.overlay: self.overlay.update_lens_radius(v)

        row1 = ctk.CTkFrame(b, fg_color="transparent")
        row1.pack(fill="x", padx=10)
        ctk.CTkSlider(row1, from_=20, to=80, variable=self.lens_var,
                      number_of_steps=60, command=on_lens,
                      width=300).pack(side="left")
        ctk.CTkLabel(row1, textvariable=self.lens_str,
                     text_color=C["accent"],
                     font=ctk.CTkFont(FN, 11, "bold"),
                     width=40).pack(side="left", padx=6)

        sub("Capture area (square side, px)")

        def on_cap(val):
            self.cap_str.set(str(int(float(val))))

        row2 = ctk.CTkFrame(b, fg_color="transparent")
        row2.pack(fill="x", padx=10)
        ctk.CTkSlider(row2, from_=100, to=1000, variable=self.cap_var,
                      number_of_steps=18, command=on_cap,
                      width=300).pack(side="left")
        ctk.CTkLabel(row2, textvariable=self.cap_str,
                     text_color=C["accent"],
                     font=ctk.CTkFont(FN, 11, "bold"),
                     width=50).pack(side="left", padx=6)

        # ── QUICK‑ADD API KEYS ─────────────────────────────────────────────
        sec("QUICK-ADD API KEYS")
        sub("Smart Paste — auto-detects Gemini (AIza…), Anthropic (sk-ant-…), "
            "OpenAI (sk-…), Groq (gsk_…)")

        smart_row = ctk.CTkFrame(b, fg_color="transparent")
        smart_row.pack(fill="x", padx=10, pady=(2, 6))

        self._smart_key_var = tk.StringVar()
        self._smart_detect_lbl = tk.StringVar(value="Provider: —")

        smart_entry = ctk.CTkEntry(
            smart_row,
            textvariable=self._smart_key_var,
            placeholder_text="Paste any API key here…",
            show="•",
            height=32,
            font=ctk.CTkFont(FN, 11),
        )
        smart_entry.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            smart_row, text="+ Auto-Add", width=90, height=32,
            font=ctk.CTkFont(FN, 11, "bold"),
            fg_color="#10B981", hover_color="#059669",
            command=self._smart_auto_add,
        ).pack(side="right", padx=(6, 0))

        # Live detection label — updates as the user types / pastes
        self._detect_lbl = ctk.CTkLabel(
            b, textvariable=self._smart_detect_lbl,
            font=ctk.CTkFont(FN, 9), text_color=C["accent"],
            anchor="w",
        )
        self._detect_lbl.pack(fill="x", padx=10, pady=(0, 4))
        self._smart_key_var.trace_add("write", self._on_key_paste)

        # ── Named quick-add rows (kept for power users) ──────────────────
        sub("— or use a named provider —")
        self.smart_entries = {}
        for name in SMART_PROVIDERS.keys():
            row = ctk.CTkFrame(b, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(row, text=name, width=120, anchor="w",
                         font=ctk.CTkFont(FN, 11, "bold")).pack(side="left")
            key_var = tk.StringVar()
            self.smart_entries[name] = key_var
            ctk.CTkEntry(row, textvariable=key_var,
                         placeholder_text="Paste Key…", show="•",
                         height=24).pack(side="left", fill="x",
                                         expand=True, padx=5)
            ctk.CTkButton(
                row, text="+ Add", width=50, height=24,
                fg_color="#10B981", hover_color="#059669",
                command=lambda n=name, v=key_var: self._quick_add(n, v.get()),
            ).pack(side="right")

        # ── active list ──────────────────────────────────────────────────────
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
        ctk.CTkCheckBox(b,
                        text="Enable consensus (Ollama + Cloud agree or judge)",
                        variable=self.cons_var,
                        font=ctk.CTkFont(FN, 11), text_color=C["text"],
                        checkbox_width=18, checkbox_height=18,
                        fg_color=C["accent2"]).pack(anchor="w", padx=20)
        sub("Judge model (Ollama, e.g. llava)")
        ctk.CTkEntry(b, textvariable=self.judge_var,
                     placeholder_text="llava",
                     font=ctk.CTkFont(FN, 11)).pack(fill="x", padx=10)

        # ── neural voice / tts ───────────────────────────────────────────────
        sec("NEURAL VOICE  (edge-tts + pygame)")
        sub("Voice (fetching English voices in background…)")

        tts_row = ctk.CTkFrame(b, fg_color="transparent")
        tts_row.pack(fill="x", padx=10)

        # Dropdown — starts with the saved voice; populated once list arrives
        self._tts_menu = ctk.CTkOptionMenu(
            tts_row,
            variable=self.tts_var,
            values=[self.tts_var.get()],
            font=ctk.CTkFont(FN, 11),
            width=300,
            dynamic_resizing=False,
        )
        self._tts_menu.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            tts_row, text="▶ Test", width=70, height=28,
            font=ctk.CTkFont(FN, 11),
            fg_color=C["accent2"], hover_color="#4a44cc",
            command=self._test_voice,
        ).pack(side="right", padx=(6, 0))

        # Kick off background voice-list fetch
        threading.Thread(target=self._fetch_voices_bg, daemon=True).start()

        ctk.CTkCheckBox(b,
                        text="Narrate screen analysis results out loud (Mode 1)",
                        variable=self.narrate_var,
                        font=ctk.CTkFont(FN, 11), text_color=C["text"],
                        checkbox_width=18, checkbox_height=18,
                        fg_color=C["accent2"]).pack(anchor="w", padx=20,
                                                    pady=(6, 0))

        # ── history ──────────────────────────────────────────────────────────
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

    # ── API Key Auto-Detection helpers ───────────────────────────────────────
    def _on_key_paste(self, *_):
        """Trace callback — update the live detection label as the user types."""
        key = self._smart_key_var.get().strip()
        if not key:
            self._smart_detect_lbl.set("Provider: —")
            return
        entry = detect_key_provider(key)
        if entry:
            self._smart_detect_lbl.set(
                f"Detected → {entry['label']}  ·  model: {entry['model']}"
            )
            self._detect_lbl.configure(text_color=C["success"])
        else:
            self._smart_detect_lbl.set("Provider: unrecognised prefix")
            self._detect_lbl.configure(text_color=C["warning"])

    def _smart_auto_add(self):
        """Read the smart paste field, detect provider, and add to active list."""
        key = self._smart_key_var.get().strip()
        if not key:
            self._status.configure(text="⚠ Paste an API key first.",
                                   text_color=C["error"])
            return
        entry = detect_key_provider(key)
        if not entry:
            self._status.configure(
                text="⚠ Unrecognised key prefix. Use a named row below.",
                text_color=C["warning"])
            return
        self.providers.append(entry)
        self._refresh_prov_list()
        self._smart_key_var.set("")
        self._smart_detect_lbl.set("Provider: —")
        self._detect_lbl.configure(text_color=C["accent"])
        self._status.configure(
            text=f"✓ Auto-added {entry['label']} ({entry['model']})",
            text_color=C["success"])

    # ── Smart Quick‑Add logic (named rows) ───────────────────────────────────
    def _quick_add(self, name: str, key: str):
        if not key.strip():
            self._status.configure(text=f"⚠ Please paste a key for {name}.", text_color=C["error"])
            return
            
        config = SMART_PROVIDERS[name]
        entry = {
            "label": name,
            "type": config["type"],
            "key": key.strip(),
            "model": config["model"]
        }
        if config["base_url"]:
            entry["base_url"] = config["base_url"]
            
        self.providers.append(entry)
        self._refresh_prov_list()
        self.smart_entries[name].set("")  # clear the entry field
        self._status.configure(text=f"✓ Added {name} successfully!", text_color=C["success"])

    def _remove_provider(self, idx: int):
        if 0 <= idx < len(self.providers):
            self.providers.pop(idx); self._refresh_prov_list()

    def _refresh_prov_list(self):
        for w in self._prov_list.winfo_children(): w.destroy()
        if not self.providers:
            tk.Label(self._prov_list,
                     text="  No providers yet — add one above.",
                     bg=C["bg"], fg=C["muted"],
                     font=(FN, 9)).pack(anchor="w", padx=10, pady=8)
            return
        ICONS = {"gemini":"◈","openai":"⬡","anthropic":"♦",
                 "grok":"✦","deepseek":"◉","ollama":"⊛","custom":"⬟"}
        for i, p in enumerate(self.providers):
            row = ctk.CTkFrame(self._prov_list,
                               fg_color=C["bg2"], corner_radius=4)
            row.pack(fill="x", padx=6, pady=3)
            icon = ICONS.get(p.get("type", ""), "▪")
            txt  = (f"{icon}  "
                    f"{p.get('label', p.get('type','?').capitalize())}  ·  "
                    f"{p.get('model','?')}")
            tk.Label(row, text=txt, bg=C["bg2"], fg=C["text"],
                     font=(FN, 10)).pack(side="left", padx=8, pady=4)
            rem = tk.Label(row, text="✕", bg=C["bg2"], fg=C["muted"],
                           cursor="hand2", font=(FN, 10))
            rem.pack(side="right", padx=8)
            rem.bind("<Button-1>", lambda _, j=i: self._remove_provider(j))
            rem.bind("<Enter>",    lambda _, r=rem: r.config(fg=C["error"]))
            rem.bind("<Leave>",    lambda _, r=rem: r.config(fg=C["muted"]))

    # ── voice list fetch (background) ────────────────────────────────────────
    def _fetch_voices_bg(self):
        """Fetch English edge-tts voices in a background thread and update
        the dropdown once done.  Silently skips if edge_tts unavailable."""
        if not HAS_EDGE_TTS:
            return
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            voices = loop.run_until_complete(_edge_tts.list_voices())
            loop.close()
            en_voices = sorted(
                v["ShortName"]
                for v in voices
                if v.get("ShortName", "").startswith("en-")
            )
            if en_voices:
                current = self.tts_var.get()
                # Make sure the current selection is always in the list
                if current not in en_voices:
                    en_voices = [current] + en_voices
                # Schedule UI update on main thread
                self.win.after(0, lambda vl=en_voices: self._apply_voice_list(vl))
        except Exception as e:
            print(f"[TTS] Voice list fetch failed: {e}")

    def _apply_voice_list(self, voices: list):
        """Update the OptionMenu with the fetched voice list (called on main thread)."""
        try:
            self._tts_menu.configure(values=voices)
            # Keep current value selected
            current = self.tts_var.get()
            if current not in voices:
                self.tts_var.set(voices[0])
            print(f"[TTS] Loaded {len(voices)} English voices into dropdown.")
        except Exception as e:
            print(f"[TTS] Could not update voice dropdown: {e}")

    def _test_voice(self):
        """Play a short test phrase with the currently selected voice."""
        voice = self.tts_var.get().strip()
        if not voice:
            self._status.configure(text="⚠ No voice selected.", text_color=C["error"])
            return
        self._status.configure(text=f"▶ Testing voice: {voice}…", text_color=C["accent"])
        # Use a temporary AudioPlayer so it respects the preview voice immediately
        preview = AudioPlayer(voice)
        preview.speak("Voice test successful.",
                       on_done=lambda: self.win.after(
                           0, lambda: self._status.configure(
                               text=f"✓ Voice preview done: {voice}",
                               text_color=C["success"])))

    def _save(self):
        self.cfg["hotkey"]             = self.hk_var.get().strip().lower()  or "alt+s"
        self.cfg["voice_hotkey"]       = self.vhk_var.get().strip().lower() or "alt+v"
        self.cfg["context_hotkey"]     = self.ctx_hk_var.get().strip().lower() or "alt+j"
        self.cfg["lens_radius"]        = self.lens_var.get()
        self.cfg["capture_size"]       = self.cap_var.get()
        self.cfg["active_providers"]   = self.providers
        self.cfg["use_ollama"]         = self.oll_var.get()
        self.cfg["ollama_model"]       = self.oll_model.get().strip()
        self.cfg["consensus"]          = self.cons_var.get()
        self.cfg["judge_model"]        = self.judge_var.get().strip()
        self.cfg["tts_voice"]          = self.tts_var.get().strip()
        self.cfg["read_screen_results"]= self.narrate_var.get()
        save_cfg(self.cfg)
        self.on_save(self.cfg)
        self._hdr_hk.configure(text=self.cfg["hotkey"].upper())
        self._status.configure(
            text=(f"✓ Saved!  "
                  f"{self.cfg['hotkey'].upper()} · "
                  f"{self.cfg['voice_hotkey'].upper()} · "
                  f"{self.cfg['context_hotkey'].upper()}"),
            text_color=C["success"])
        self.win.after(2500, self.win.withdraw)

    def _poll_history(self):
        if self.history_fn:
            items = self.history_fn()
            if items:
                lines = "\n".join(
                    f"[{e['time']}] "
                    f"{'✓' if e['status']=='success' else '✗'}"
                    f"  [{e.get('mode','?')}]  {e['text']}"
                    for e in reversed(items[-10:])
                )
                self._hist_box.configure(state="normal")
                self._hist_box.delete("0.0", "end")
                self._hist_box.insert("end", lines)
                self._hist_box.configure(state="disabled")
        self.win.after(3000, self._poll_history)

    def run(self): self.win.mainloop()


# ─────────────────────────────────────────────────────────────────────────────
#  AUDIO  (pygame — silent background, no media player window)
# ─────────────────────────────────────────────────────────────────────────────
class AudioPlayer:
    def __init__(self, voice: str = "en-US-AndrewNeural"):
        self.voice = voice
        self._lock = threading.Lock()

    def speak(self, text: str, on_done: Optional[Callable] = None):
        threading.Thread(target=self._bg, args=(text, on_done),
                         daemon=True).start()

    def _bg(self, text: str, on_done):
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
                size = os.path.getsize(tmp)
                time.sleep(max(1.0, size / 16000))
        except Exception as e:
            print(f"[TTS] {e}")
        finally:
            loop.close()
            if tmp and os.path.exists(tmp):
                try: os.unlink(tmp)
                except: pass
            if on_done: on_done()


# ─────────────────────────────────────────────────────────────────────────────
#  SPEECH  (mic capture helper — shared by Mode 2 & 3)
# ─────────────────────────────────────────────────────────────────────────────
class SpeechCapture:
    def __init__(self, whisper_model=None):
        self._rec    = sr.Recognizer() if HAS_SR else None
        self._mic    = sr.Microphone() if HAS_SR else None
        self._whisper = whisper_model

    def listen(self) -> Optional[str]:
        """Blocking — call from a background thread. Returns transcription or None."""
        if not HAS_SR or not self._rec: return None
        try:
            with self._mic as source:
                self._rec.adjust_for_ambient_noise(source, duration=0.4)
                print("[Voice] Listening…")
                audio = self._rec.listen(source, timeout=8,
                                          phrase_time_limit=6)
            try:
                text = self._rec.recognize_google(audio)
                print(f"[Voice] Google: {text}")
                return text
            except Exception:
                pass
            if self._whisper:
                print("[Voice] Trying Whisper…")
                with tempfile.NamedTemporaryFile(suffix=".wav",
                                                 delete=False) as f:
                    f.write(audio.get_wav_data()); tmp = f.name
                try:
                    res  = self._whisper.transcribe(tmp, fp16=False)
                    text = res["text"].strip()
                    print(f"[Voice] Whisper: {text}")
                    return text if text else None
                finally:
                    try: os.unlink(tmp)
                    except: pass
        except Exception as e:
            print(f"[Voice] Mic error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  APP
# ─────────────────────────────────────────────────────────────────────────────
class App:
    def __init__(self):
        self.cfg    = load_cfg()
        self.engine = AIEngine(self.cfg)
        self._busy  = False
        self._vbusy = False
        self._cbusy = False
        self.history: List[dict] = []

        self.audio = AudioPlayer(self.cfg.get("tts_voice", "en-US-AndrewNeural"))

        self._whisper_mdl = None
        if HAS_WHISPER:
            print("[MouseLens] Loading Whisper 'tiny'…")
            try:   self._whisper_mdl = _whisper.load_model("tiny")
            except Exception as e: print(f"[MouseLens] Whisper: {e}")

        self._speech = SpeechCapture(self._whisper_mdl)

        self.settings = SettingsWindow(
            self.cfg, on_save=self._reload,
            history_fn=lambda: self.history)
        self.overlay = Overlay(self.settings.win, self.cfg)
        self.settings.overlay = self.overlay

        self._bind_hotkeys()

    def _bind_hotkeys(self):
        keyboard.unhook_all()
        hk  = self.cfg.get("hotkey",         "alt+s").lower()
        vhk = self.cfg.get("voice_hotkey",   "alt+v").lower()
        chk = self.cfg.get("context_hotkey", "alt+j").lower()
        keyboard.add_hotkey(hk,  self._on_screen,  suppress=True)
        keyboard.add_hotkey(vhk, self._on_voice,   suppress=True)
        keyboard.add_hotkey(chk, self._on_context, suppress=True)
        print(f"[MouseLens] {hk.upper()} screen  "
              f"| {vhk.upper()} voice  "
              f"| {chk.upper()} context")

    def _reload(self, cfg: dict):
        self.cfg    = cfg
        self.engine = AIEngine(cfg)
        self.audio  = AudioPlayer(cfg.get("tts_voice", "en-US-AndrewNeural"))
        for attr in ("_lw", "_fw", "_bw"):
            try: getattr(self.overlay, attr).destroy()
            except: pass
        self.overlay = Overlay(self.settings.win, cfg)
        self.settings.overlay = self.overlay
        self._bind_hotkeys()
        print("[MouseLens] Reloaded.")

    def _capture(self, mx: int, my: int):
        half = self.cfg.get("capture_size", 400) // 2
        return ImageGrab.grab(bbox=(max(0, mx-half), max(0, my-half),
                                    mx+half, my+half))

    def _on_screen(self):
        if self._busy: return
        self._busy = True
        mx, my = pyautogui.position()
        self.settings.win.after(0, lambda: self._screen_begin(mx, my))

    def _screen_begin(self, mx, my):
        self.overlay.show_loading("Mode 1 · Screen")
        threading.Thread(target=self._screen_worker, args=(mx, my),
                         daemon=True).start()

    def _screen_worker(self, mx, my):
        try:
            img  = self._capture(mx, my)
            text, status = self.engine.analyze(img)
        except Exception as e:
            text, status = f"Capture error:\n{e}", "error"
            print(f"[Mode1] {e}")
        finally:
            self._busy = False

        def ui():
            self.overlay.show_result(text, status, "Mode 1")
            if status == "success" and self.cfg.get("read_screen_results"):
                self.overlay.set_state("talking")
                self.audio.speak(text, on_done=lambda:
                    self.settings.win.after(
                        0, lambda: self.overlay.set_state("success")))
            if status == "success":
                try:
                    self.settings.win.clipboard_clear()
                    self.settings.win.clipboard_append(text)
                except: pass
            self.history.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "mode": "Screen",
                "text": text[:200],
                "status": status,
            })
        self.settings.win.after(0, ui)

    def _on_voice(self):
        if self._vbusy or not HAS_SR: return
        self._vbusy = True
        self.settings.win.after(0, lambda: self.overlay.show_loading("Mode 2 · Voice"))
        threading.Thread(target=self._voice_worker, daemon=True).start()

    def _voice_worker(self):
        q = self._speech.listen()
        if not q:
            result, status = "Didn't catch that — please try again.", "error"
        else:
            result, status = self.engine.analyze_text(q)

        def ui():
            self.overlay.show_result(result, status, "Mode 2")
            self.overlay.set_state("talking")
            self.audio.speak(result, on_done=lambda:
                self.settings.win.after(
                    0, lambda: self.overlay.set_state("idle")))
            if status == "success":
                try:
                    self.settings.win.clipboard_clear()
                    self.settings.win.clipboard_append(result)
                except: pass
            self.history.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "mode": "Voice",
                "text": result[:200],
                "status": status,
            })
            self._vbusy = False
        self.settings.win.after(0, ui)

    def _on_context(self):
        if self._cbusy or not HAS_SR: return
        self._cbusy = True
        mx, my = pyautogui.position()
        self.settings.win.after(0, lambda: self._context_begin(mx, my))

    def _context_begin(self, mx, my):
        self.overlay.show_loading("Mode 3 · Context")
        threading.Thread(target=self._context_worker, args=(mx, my),
                         daemon=True).start()

    def _context_worker(self, mx: int, my: int):
        try:
            img = self._capture(mx, my)
        except Exception as e:
            self.settings.win.after(
                0, lambda: self.overlay.show_result(
                    f"Capture failed:\n{e}", "error", "Mode 3"))
            self._cbusy = False
            return

        self.settings.win.after(0, self.overlay.show_listening)
        question = self._speech.listen()
        if not question:
            question = "What is shown in this image?"

        ctx_prompt = PROMPT_CONTEXT_TPL.format(question=question)
        self.settings.win.after(
            0, lambda: self.overlay.show_loading("Mode 3 · Analyzing"))

        try:
            result, status = self.engine.analyze(img, custom_prompt=ctx_prompt)
        except Exception as e:
            result, status = f"Analysis error:\n{e}", "error"
            print(f"[Mode3] {e}")
        finally:
            self._cbusy = False

        def ui():
            self.overlay.show_result(result, status, "Mode 3")
            self.overlay.set_state("talking")
            self.audio.speak(result, on_done=lambda:
                self.settings.win.after(
                    0, lambda: self.overlay.set_state("idle")))
            if status == "success":
                try:
                    self.settings.win.clipboard_clear()
                    self.settings.win.clipboard_append(result)
                except: pass
            self.history.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "mode": "Context",
                "text": f"Q: {question[:80]}  →  {result[:120]}",
                "status": status,
            })
        self.settings.win.after(0, ui)

    def run(self):
        hk  = self.cfg.get("hotkey",         "alt+s").upper()
        vhk = self.cfg.get("voice_hotkey",   "alt+v").upper()
        chk = self.cfg.get("context_hotkey", "alt+j").upper()
        print(f"[MouseLens] Ready\n"
              f"  {hk}  → Mode 1: Screen Analysis\n"
              f"  {vhk}  → Mode 2: Voice Q&A\n"
              f"  {chk}  → Mode 3: Contextual Voice Chat")
        self.settings.run()


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    App().run()
