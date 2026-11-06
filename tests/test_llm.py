import pytest

from agora.llm import LLMConfig, LLMError, is_blocked, make_backend, parse_json
from agora.llm.base import is_private_host


@pytest.mark.parametrize("raw,want", [
    ('{"a": 1}', {"a": 1}),
    ('```json\n{"a": 1}\n```', {"a": 1}),
    ('Sure! Here you go: {"a": {"b": 2}} hope that helps', {"a": {"b": 2}}),
    ('{"a": 1} trailing } junk', {"a": 1}),
    ("not json at all", {}),
    ("", {}),
])
def test_parse_json(raw, want):
    assert parse_json(raw) == want


@pytest.mark.parametrize("model,blocked", [
    ("qwen2.5:7b", True), ("deepseek-r1:8b", True), ("hf.co/someone/Qwen3-4B", True),
    ("yi:6b", True), ("glm4", True),
    ("llama3.2:3b", False), ("gemma3:4b", False), ("phi4-mini", False), ("mistral:7b", False),
])
def test_blocklist(model, blocked):
    assert is_blocked(model) is blocked


def test_blocked_model_refused():
    with pytest.raises(LLMError):
        make_backend({"backend": "ollama", "model": "qwen2.5:3b"})


def test_remote_host_refused_unless_allowed():
    with pytest.raises(LLMError):
        make_backend({"backend": "openai", "url": "https://api.example.com", "model": "x"})
    make_backend({"backend": "openai", "url": "https://api.example.com", "model": "x",
                  "allow_remote": True})


@pytest.mark.parametrize("url,ok", [
    ("http://localhost:11434", True), ("http://192.168.1.20:8000", True),
    ("http://10.0.0.5", True), ("http://172.20.1.1", True), ("http://gpu-box.local:8080", True),
    ("http://8.8.8.8", False), ("https://example.com", False),
])
def test_private_hosts(url, ok):
    assert is_private_host(url) is ok


def test_cache_replays(tmp_path):
    be = make_backend(LLMConfig(backend="mock"), cache_path=tmp_path / "c.db")
    msgs = [{"role": "user", "content": "hi"}]
    a = be.generate(msgs, seed=1, meta={"default_text": "hello"})
    b = be.generate(msgs, seed=1, meta={"default_text": "something else"})
    assert a == b == "hello"
    assert be.calls == 1 and be.hits == 1
