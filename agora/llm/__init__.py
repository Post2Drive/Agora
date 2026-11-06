from .base import (LLMBackend, LLMConfig, LLMError, RECOMMENDED_MODELS, is_blocked,
                   parse_json)
from .cache import CachedBackend


def make_backend(cfg: LLMConfig | dict, cache_path=None) -> LLMBackend:
    if isinstance(cfg, dict):
        cfg = LLMConfig.from_dict(cfg)
    kind = cfg.backend.lower()
    if kind == "ollama":
        from .ollama import OllamaBackend as B
    elif kind in ("openai", "llamacpp", "lmstudio", "vllm"):
        from .openai_compat import OpenAICompatBackend as B
    elif kind == "mock":
        from .mock import MockBackend as B
    else:
        raise LLMError(f"Unknown backend '{cfg.backend}'. Use ollama, openai or mock.")
    be = B(cfg)
    if cfg.cache and cache_path:
        be = CachedBackend(be, cache_path)
    return be


__all__ = ["LLMBackend", "LLMConfig", "LLMError", "RECOMMENDED_MODELS", "is_blocked",
           "parse_json", "make_backend", "CachedBackend"]
