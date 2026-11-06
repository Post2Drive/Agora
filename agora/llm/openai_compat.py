"""Any OpenAI-compatible server: llama.cpp `llama-server`, LM Studio, vLLM, LocalAI,
text-generation-webui, etc. Point `url` at the server root (e.g. http://localhost:8080)."""
from __future__ import annotations

from .base import LLMBackend, LLMError
from .http import get_json, post_json


class OpenAICompatBackend(LLMBackend):
    name = "openai"

    @property
    def base(self) -> str:
        u = self.cfg.url.rstrip("/")
        return u if u.endswith("/v1") else u + "/v1"

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.cfg.api_key}"} if self.cfg.api_key else {}

    def __init__(self, cfg):
        super().__init__(cfg)
        self._json_supported = True

    def _complete(self, messages, *, max_tokens, temperature, json_mode, seed, meta) -> str:
        body = {"model": self.cfg.model, "messages": messages,
                "max_tokens": max_tokens, "temperature": temperature}
        if seed is not None:
            body["seed"] = int(seed)
        if json_mode and self._json_supported:
            body["response_format"] = {"type": "json_object"}
        try:
            out = post_json(f"{self.base}/chat/completions", body,
                            timeout=self.cfg.timeout, headers=self.headers)
        except LLMError as e:
            if json_mode and self._json_supported and "HTTP 400" in str(e):
                self._json_supported = False      # server lacks JSON mode; rely on prompt
                body.pop("response_format", None)
                out = post_json(f"{self.base}/chat/completions", body,
                                timeout=self.cfg.timeout, headers=self.headers)
            else:
                raise
        try:
            return out["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as e:
            raise LLMError(f"Unexpected reply: {str(out)[:200]}") from e

    def status(self) -> tuple[bool, str]:
        try:
            models = get_json(f"{self.base}/models", headers=self.headers)
        except LLMError:
            return False, f"No OpenAI-compatible server at {self.cfg.url}"
        ids = [m.get("id", "") for m in models.get("data", [])]
        if ids and self.cfg.model not in ids:
            return False, f"Server is up but has no model '{self.cfg.model}'. Available: {ids[:5]}"
        return True, f"Server ready: {self.cfg.model}"
