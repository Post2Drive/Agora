"""Common pieces for every language-model backend.

A backend turns a list of chat messages into text. Everything else in Agora talks
to the `LLMBackend` interface only, so swapping Ollama for llama.cpp, LM Studio or
a vLLM GPU server is a one-line config change.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

# Model families Agora refuses to load by default (project policy: no Chinese-origin
# models). Users can override with `allow_blocked_models: true` in their config.
BLOCKED_FAMILIES = (
    "qwen", "deepseek", "yi:", "yi-", "yi1", "glm", "chatglm", "internlm", "baichuan",
    "kimi", "moonshot", "minimax", "ernie", "hunyuan", "codegeex", "aquila",
    "skywork", "seed-oss", "stepfun", "minicpm", "telechat", "xverse", "orion",
)

# Known-good, non-blocked models, smallest first.
RECOMMENDED_MODELS = {
    "tiny": "llama3.2:1b",
    "small": "llama3.2:3b",
    "medium": "gemma3:4b",
    "large": "llama3.1:8b",
    "xlarge": "gemma3:12b",
    "server": "llama3.3:70b",
}

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


class LLMError(RuntimeError):
    """Raised when a backend cannot produce a response."""


def is_blocked(model: str) -> bool:
    m = model.lower().rsplit("/", 1)[-1]
    return any(m.startswith(b) for b in BLOCKED_FAMILIES)


def is_private_host(url: str) -> bool:
    """True for localhost and private LAN addresses (a GPU box on your own network)."""
    host = (urlparse(url).hostname or "").lower()
    if host in LOCAL_HOSTS or host.endswith(".local") or host.endswith(".lan"):
        return True
    parts = host.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        a, b = int(parts[0]), int(parts[1])
        return a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168)
    return False


@dataclass
class LLMConfig:
    backend: str = "ollama"              # ollama | openai | mock
    model: str = RECOMMENDED_MODELS["small"]
    url: str = "http://localhost:11434"
    api_key: str = ""                    # only for OpenAI-compatible servers that need one
    timeout: float = 600.0               # slow laptops need patience
    parallel: int = 1                    # concurrent requests the server can handle
    context: int = 4096
    allow_remote: bool = False           # allow non-private hosts (data leaves your network)
    allow_blocked_models: bool = False
    cache: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict | None) -> "LLMConfig":
        from .providers import resolve          # "claude" / "chatgpt" -> concrete settings
        d = resolve(dict(d or {}))
        known = {k: d.pop(k) for k in list(d) if k in cls.__dataclass_fields__ and k != "extra"}
        return cls(**known, extra=d)

    def validate(self) -> None:
        if self.backend != "mock":
            if not self.allow_remote and not is_private_host(self.url):
                raise LLMError(
                    f"{self.url} is not on this machine or your private network. "
                    "Set llm.allow_remote: true if you really want data to leave your network.")
        if not self.allow_blocked_models and is_blocked(self.model):
            raise LLMError(
                f"Model '{self.model}' is from a blocked family. "
                f"Try {RECOMMENDED_MODELS['small']} or {RECOMMENDED_MODELS['medium']}.")


class LLMBackend:
    """Interface. Subclasses implement `_complete`."""

    name = "base"

    def __init__(self, cfg: LLMConfig):
        cfg.validate()
        self.cfg = cfg
        self.calls = 0
        self.tokens_out = 0

    # -- public API -------------------------------------------------------------
    def generate(self, messages: list[dict], *, max_tokens: int = 300,
                 temperature: float = 0.8, json_mode: bool = False,
                 seed: int | None = None, meta: dict | None = None) -> str:
        """Return the model's reply. `meta` is ignored by real models; the mock
        backend uses it to produce plausible structured output in tests."""
        self.calls += 1
        out = self._complete(messages, max_tokens=max_tokens, temperature=temperature,
                             json_mode=json_mode, seed=seed, meta=meta or {})
        self.tokens_out += max(1, len(out) // 4)
        return out

    def generate_json(self, messages: list[dict], **kw) -> dict:
        raw = self.generate(messages, json_mode=True, **kw)
        return parse_json(raw)

    def status(self) -> tuple[bool, str]:
        return True, f"{self.name}: {self.cfg.model}"

    # -- to implement -----------------------------------------------------------
    def _complete(self, messages, *, max_tokens, temperature, json_mode, seed, meta) -> str:
        raise NotImplementedError


_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def parse_json(raw: str) -> dict:
    """Best-effort JSON extraction; small models often wrap JSON in prose or fences."""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("{"):] if "{" in raw else raw
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {"value": val}
    except json.JSONDecodeError:
        pass
    m = _JSON_BLOCK.search(raw)
    if m:
        chunk = m.group(0)
        for end in range(len(chunk), 0, -1):          # trim trailing junk
            if chunk[end - 1] != "}":
                continue
            try:
                val = json.loads(chunk[:end])
                return val if isinstance(val, dict) else {"value": val}
            except json.JSONDecodeError:
                continue
    return {}
