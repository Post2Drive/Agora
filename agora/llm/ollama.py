"""Ollama backend (default). https://ollama.com - runs models locally on Windows, Mac, Linux."""
from __future__ import annotations

from .base import LLMBackend, LLMError
from .http import get_json, post_json


class OllamaBackend(LLMBackend):
    name = "ollama"

    @property
    def base(self) -> str:
        return self.cfg.url.rstrip("/")

    def _complete(self, messages, *, max_tokens, temperature, json_mode, seed, meta) -> str:
        options = {"temperature": temperature, "num_predict": max_tokens,
                   "num_ctx": self.cfg.context}
        if seed is not None:
            options["seed"] = int(seed)
        body = {"model": self.cfg.model, "messages": messages, "stream": False,
                "options": options, "keep_alive": "30m"}
        if json_mode:
            body["format"] = "json"
        out = post_json(f"{self.base}/api/chat", body, timeout=self.cfg.timeout)
        msg = out.get("message") or {}
        if "content" not in msg:
            raise LLMError(f"Unexpected Ollama reply: {str(out)[:200]}")
        return msg["content"]

    def status(self) -> tuple[bool, str]:
        try:
            tags = get_json(f"{self.base}/api/tags")
        except LLMError:
            return False, "Ollama is not running. Start the Ollama app, or run: ollama serve"
        names = [m.get("name", "") for m in tags.get("models", [])]
        want = self.cfg.model if ":" in self.cfg.model else self.cfg.model + ":latest"
        if want not in names:
            return False, f"Model not downloaded. Run: ollama pull {self.cfg.model}"
        return True, f"Ollama ready: {self.cfg.model}"
