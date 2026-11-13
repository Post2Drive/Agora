"""User-level settings: where Agora sends model requests.

These live in the user's own home folder (or AGORA_HOME), never inside a study, so a study that is
shared, zipped or forked carries no server address, no key and no permission to leave your network."""
from __future__ import annotations

import getpass
import json
import os
from pathlib import Path

from .llm.base import is_private_host

LOCAL_URL = "http://localhost:11434"
MODEL_KEYS = ("backend", "model", "url", "parallel", "api_key", "allow_remote", "cache", "timeout", "context")


class SettingsError(Exception):
    """A settings problem the user can fix; shown as a plain message."""


def home() -> Path:
    base = os.environ.get("AGORA_HOME")
    return Path(base) if base else Path.home() / ".agora"


def settings_path() -> Path:
    return home() / "settings.json"


def load() -> dict:
    p = settings_path()
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SettingsError(f"Could not read {p}: {e}. Fix or delete it, then run: agora setup") from e
    return d if isinstance(d, dict) else {}


def save(d: dict) -> None:
    home().mkdir(parents=True, exist_ok=True)
    p = settings_path()
    p.write_text(json.dumps(d, indent=1), encoding="utf-8")
    try:
        os.chmod(p, 0o600)            # only you can read the key (limited effect on Windows)
    except OSError:
        pass


def active_name() -> str:
    return str(load().get("active") or "")


def profile(name: str | None = None) -> dict:
    """The settings of one profile; {} when the user never ran `agora setup` (Agora then uses local Ollama)."""
    d = load()
    name = name or d.get("active")
    if not name:
        return {}
    p = (d.get("profiles") or {}).get(name)
    if not p:
        raise SettingsError(f"No profile called '{name}'. Run: agora setup   (agora setup --show lists them)")
    return dict(p)


def llm_overrides(name: str | None = None) -> dict:
    """Model settings from the profile, ready to pass to the backend."""
    p = profile(name)
    out = {k: p[k] for k in MODEL_KEYS if p.get(k) not in (None, "")}
    if "api_key" not in out and p.get("allow_remote") and os.environ.get("AGORA_API_KEY"):
        out["api_key"] = os.environ["AGORA_API_KEY"]
    return out


def prices(name: str | None = None):
    """(price per million input tokens, per million output tokens) entered by the user, or None."""
    p = profile(name)
    pi, po = p.get("price_in"), p.get("price_out")
    return (float(pi), float(po)) if pi is not None and po is not None else None


def safe_study_llm(d: dict | None) -> dict:
    """A study may say which model it was made with, but never where to send data or with which key."""
    cfg = dict(d or {})
    for k in ("api_key", "allow_remote"):
        cfg.pop(k, None)
    url = cfg.get("url")
    if url and not is_private_host(str(url)):
        cfg.pop("url")
    return cfg


def use(name: str) -> None:
    d = load()
    if name not in (d.get("profiles") or {}):
        raise SettingsError(f"No profile called '{name}'. Run: agora setup")
    d["active"] = name
    save(d)


def describe() -> list[str]:
    d = load()
    profs = d.get("profiles") or {}
    if not profs:
        return ["No settings yet: Agora uses Ollama on this computer. Run: agora setup"]
    lines = [f"Settings file: {settings_path()}"]
    for n, p in sorted(profs.items()):
        mark = "*" if n == d.get("active") else " "
        key = "key set" if p.get("api_key") else "no key"
        lines.append(f"{mark} {n:<7} {p.get('kind', '')}: {p.get('backend')} {p.get('model')} at {p.get('url')} "
                     f"({key}, cache {'on' if p.get('cache', True) else 'off'})")
    lines.append("* = in use")
    return lines


def _url(s: str, scheme: str) -> str:
    s = s.strip().rstrip("/")
    if s and not s.startswith(("http://", "https://")):
        s = f"{scheme}://{s}"
    return s


def _int(s: str, default: int) -> int:
    try:
        return max(1, int(s.strip())) if s.strip() else default
    except ValueError:
        return default


def _float(s: str):
    try:
        return float(s.strip()) if s.strip() else None
    except ValueError:
        return None


def wizard(ask=input, secret=getpass.getpass, out=print) -> dict:
    """Ask where the model should run and save it. Local is the default; cloud needs an explicit YES."""
    out("Where should Agora run the AI model?")
    out("  1) This computer (Ollama). Free and private, but the slowest.")
    out("  2) My own server on my network (llama.cpp, vLLM, LM Studio...). Private.")
    out("  3) A cloud API (any OpenAI-compatible service). Fast and paid; your prompts leave your network.")
    pick = ask("Choose 1, 2 or 3 [1]: ").strip() or "1"
    if pick == "1":
        from . import hardware
        default = hardware.detect().model
        model = ask(f"Model [{default}]: ").strip() or default
        name, prof = "local", {"kind": "local", "backend": "ollama", "url": LOCAL_URL, "model": model}
    elif pick == "2":
        url = _url(ask("Server address, for example http://192.168.1.50:8000 : "), "http")
        if not url or not is_private_host(url):
            raise SettingsError(f"'{url}' is not on this computer or your private network. "
                                "Choose option 3 for a cloud service.")
        model = ask("Model name on that server: ").strip()
        if not model:
            raise SettingsError("A model name is needed.")
        name = "server"
        prof = {"kind": "server", "backend": "openai", "url": url, "model": model,
                "parallel": _int(ask("Requests at once [8]: "), 8)}
    elif pick == "3":
        url = _url(ask("Service address, for example https://api.example.com : "), "https")
        model = ask("Model name: ").strip()
        if not url or not model:
            raise SettingsError("An address and a model name are needed.")
        key = secret("API key (typing is hidden; leave empty to use the AGORA_API_KEY variable): ").strip()
        par = _int(ask("Requests at once [16]: "), 16)
        pin = _float(ask("Price per million input tokens (optional, for cost estimates): "))
        pout = _float(ask("Price per million output tokens (optional): "))
        out("The contents of your documents, the personas and the prompts will be sent to this service.")
        if ask("Type YES to allow that: ").strip() != "YES":
            raise SettingsError("Not saved: you did not allow data to leave your network.")
        name = "cloud"
        prof = {"kind": "cloud", "backend": "openai", "url": url, "model": model, "parallel": par,
                "allow_remote": True}
        if key:
            prof["api_key"] = key
        if pin is not None and pout is not None:
            prof["price_in"], prof["price_out"] = pin, pout
    else:
        raise SettingsError("Please choose 1, 2 or 3.")
    if ask("Keep a cache of model replies inside each study? It makes resume exact. [Y/n]: ").strip().lower() in ("n", "no"):
        prof["cache"] = False
    d = load()
    d.setdefault("profiles", {})[name] = prof
    d["active"] = name
    save(d)
    out(f"Saved the '{name}' profile and switched to it. Settings file: {settings_path()}")
    out("The key and server address stay on this computer, never inside your study files.")
    return prof


def public() -> dict:
    """Profiles for the website: everything except the API key itself."""
    try:
        d = load()
    except SettingsError as e:
        return {"error": str(e), "active": "", "profiles": {}}
    profs = {}
    for n, p in (d.get("profiles") or {}).items():
        q = {k: v for k, v in p.items() if k != "api_key"}
        q["has_key"] = bool(p.get("api_key"))
        profs[n] = q
    return {"active": d.get("active") or "", "profiles": profs}


def save_profile(kind: str, *, model="", url="", api_key="", parallel=None, price_in=None, price_out=None,
                 cache=True, consent=False) -> dict:
    """Save one profile (local, server or cloud) and switch to it. Same rules as the setup wizard."""
    model = str(model or "").strip()
    if kind == "local":
        from . import hardware
        prof = {"kind": "local", "backend": "ollama", "url": LOCAL_URL,
                "model": model or hardware.detect().model}
    elif kind == "server":
        url = _url(str(url or ""), "http")
        if not url or not is_private_host(url):
            raise SettingsError(f"'{url}' is not on this computer or your private network. "
                                "Choose a cloud service for remote addresses.")
        if not model:
            raise SettingsError("A model name is needed.")
        prof = {"kind": "server", "backend": "openai", "url": url, "model": model,
                "parallel": int(parallel) if parallel else 8}
    elif kind == "cloud":
        url = _url(str(url or ""), "https")
        if not url or not model:
            raise SettingsError("An address and a model name are needed.")
        if not consent:
            raise SettingsError("Not saved: you did not allow data to leave your network.")
        old = ((load().get("profiles") or {}).get("cloud")) or {}
        key = str(api_key or "").strip() or old.get("api_key", "")      # empty keeps the saved key
        prof = {"kind": "cloud", "backend": "openai", "url": url, "model": model,
                "parallel": int(parallel) if parallel else 16, "allow_remote": True}
        if key:
            prof["api_key"] = key
        if price_in is not None and price_out is not None:
            prof["price_in"], prof["price_out"] = float(price_in), float(price_out)
    else:
        raise SettingsError("Choose this computer, your own server, or a cloud API.")
    if not cache:
        prof["cache"] = False
    d = load()
    d.setdefault("profiles", {})[kind] = prof
    d["active"] = kind
    save(d)
    return prof

