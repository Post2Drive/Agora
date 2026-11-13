"""Claude through Anthropic's Messages API (opt-in cloud model)."""
from __future__ import annotations

from .base import LLMBackend, LLMError
from .http import get_json, post_json

VERSION = "2023-06-01"


class AnthropicBackend(LLMBackend):
    name = "claude"

    @property
    def headers(self) -> dict:
        return {"x-api-key": self.cfg.api_key, "anthropic-version": VERSION}

    def _complete(self, messages, *, max_tokens, temperature, json_mode, seed, meta) -> str:
        if not self.cfg.api_key:
            raise LLMError("No Claude API key. Add one in Settings (console.anthropic.com).")
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        msgs = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
        if json_mode:
            system = (system + "\n\n" if system else "") + "Reply with a single JSON object only, no other text."
        body = {"model": self.cfg.model, "max_tokens": max(16, int(max_tokens)),
                "temperature": max(0.0, min(1.0, float(temperature))), "messages": msgs}
        if system:
            body["system"] = system
        out = post_json(self.cfg.url.rstrip("/") + "/v1/messages", body,
                        timeout=self.cfg.timeout, headers=self.headers)
        try:
            return "".join(b.get("text", "") for b in out["content"] if b.get("type") == "text")
        except (KeyError, TypeError) as e:
            raise LLMError(f"Unexpected reply: {str(out)[:200]}") from e

    def status(self) -> tuple[bool, str]:
        if not self.cfg.api_key:
            return False, "No Claude API key. Add one in Settings."
        try:
            models = get_json(self.cfg.url.rstrip("/") + "/v1/models", headers=self.headers, timeout=10)
        except LLMError as e:
            return False, f"Could not reach Claude: {e}"
        ids = [m.get("id", "") for m in models.get("data", [])]
        if ids and self.cfg.model not in ids:
            return False, f"Claude has no model '{self.cfg.model}'. Available: {ids[:6]}"
        return True, f"Claude ready: {self.cfg.model}"
