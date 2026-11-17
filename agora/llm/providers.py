"""Optional cloud models: Claude (Anthropic) and ChatGPT (OpenAI).

Agora is local by default. Choosing one of these providers is an explicit opt-in: the
prompts for that step (documents, personas, posts) are sent to the provider. API keys
live only on this machine, in ~/.agora/keys.json or the usual environment variables,
never in a study's files, so a study folder can be shared without leaking a key.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

PROVIDERS = {
    "claude": {"label": "Claude (Anthropic)", "backend": "anthropic", "url": "https://api.anthropic.com",
               "env": "ANTHROPIC_API_KEY", "model": "claude-haiku-5-5",
               "models": ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"],
               "keys_url": "https://console.anthropic.com/settings/keys", "parallel": 4},
    "chatgpt": {"label": "ChatGPT (OpenAI)", "backend": "openai", "url": "https://api.openai.com",
                "env": "OPENAI_API_KEY", "model": "gpt-6-luna",
                "models": ["gpt-6-luna", "gpt-6.1-sol", "gpt-5.4-mini"],
                "keys_url": "https://platform.openai.com/api-keys", "parallel": 4},
}


def home() -> Path:
    return Path(os.environ.get("AGORA_HOME") or Path.home() / ".agora")


def _keys_file() -> Path:
    return home() / "keys.json"


def _load() -> dict:
    try:
        return json.loads(_keys_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def get_key(provider: str) -> str:
    p = PROVIDERS[provider]
    return os.environ.get(p["env"], "") or str(_load().get(provider, ""))


def set_key(provider: str, key: str) -> None:
    if provider not in PROVIDERS:
        raise KeyError(provider)
    data = _load()
    key = key.strip()
    if key:
        data[provider] = key
    else:
        data.pop(provider, None)
    f = _keys_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data), encoding="utf-8")
    try:
        os.chmod(f, 0o600)
    except OSError:
        pass


def key_status() -> dict:
    out = {}
    for name, p in PROVIDERS.items():
        k = get_key(name)
        out[name] = {"label": p["label"], "set": bool(k), "hint": (k[:7] + "…" + k[-4:]) if len(k) > 14 else "",
                     "from_env": bool(os.environ.get(p["env"])), "model": p["model"],
                     "models": p["models"], "keys_url": p["keys_url"]}
    return out


def resolve(cfg: dict) -> dict:
    """Turn {"backend": "claude"|"chatgpt", "model": ...} into a concrete backend config."""
    name = str(cfg.get("backend", "")).lower()
    if name not in PROVIDERS:
        return cfg
    p = PROVIDERS[name]
    out = dict(cfg)
    out.update({"backend": p["backend"], "url": p["url"], "allow_remote": True, "provider": name,
                "api_key": cfg.get("api_key") or get_key(name)})
    out["model"] = cfg.get("model") or p["model"]
    out.setdefault("parallel", p["parallel"])
    if int(out.get("parallel") or 1) < 2:
        out["parallel"] = p["parallel"]
    return out
