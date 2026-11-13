"""User-level settings: where the model runs. Local by default; cloud only with an explicit YES."""
from types import SimpleNamespace

import pytest

from agora import settings
from agora.cli import _llm_override


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AGORA_API_KEY", raising=False)


def says(*answers):
    it = iter(answers)
    return lambda prompt="": next(it)


def run_wizard(*answers, key="sk-test"):
    return settings.wizard(ask=says(*answers), secret=lambda prompt="": key, out=lambda m: None)


def test_no_settings_means_local_defaults():
    assert settings.llm_overrides() == {}
    assert settings.describe()[0].startswith("No settings yet")


def test_local_profile():
    run_wizard("1", "llama3.2:3b", "")
    o = settings.llm_overrides()
    assert o["backend"] == "ollama" and o["model"] == "llama3.2:3b" and "allow_remote" not in o
    assert "cache" not in o


def test_cache_can_be_turned_off():
    run_wizard("1", "llama3.2:3b", "n")
    assert settings.llm_overrides()["cache"] is False


def test_own_server_must_be_private():
    with pytest.raises(settings.SettingsError):
        run_wizard("2", "https://api.example.com")
    run_wizard("2", "192.168.1.50:8000", "m1", "", "")
    o = settings.llm_overrides()
    assert o["url"] == "http://192.168.1.50:8000" and o["backend"] == "openai" and o["parallel"] == 8


def test_cloud_needs_explicit_yes():
    with pytest.raises(settings.SettingsError):
        run_wizard("3", "https://api.example.com", "m1", "", "", "", "no")
    assert settings.llm_overrides() == {}               # nothing was saved
    run_wizard("3", "https://api.example.com", "m1", "", "0.5", "1.5", "YES", "")
    o = settings.llm_overrides()
    assert o["allow_remote"] is True and o["api_key"] == "sk-test" and o["parallel"] == 16
    assert settings.prices() == (0.5, 1.5)


def test_mock_ignores_the_profile():
    run_wizard("3", "https://api.example.com", "m1", "", "", "", "YES", "")
    assert _llm_override(SimpleNamespace(mock=True)) == {"backend": "mock"}
    o = _llm_override(SimpleNamespace())
    assert o["allow_remote"] is True and o["url"] == "https://api.example.com"


def test_a_study_cannot_choose_where_data_goes():
    d = settings.safe_study_llm({"backend": "openai", "model": "m", "parallel": 4, "api_key": "sk-x",
                                 "allow_remote": True, "url": "https://evil.example.com"})
    assert d == {"backend": "openai", "model": "m", "parallel": 4}
    d = settings.safe_study_llm({"url": "http://192.168.0.5:8000", "allow_remote": True})
    assert d == {"url": "http://192.168.0.5:8000"}


def test_unknown_profile_is_a_clear_error():
    run_wizard("1", "llama3.2:3b", "")
    with pytest.raises(settings.SettingsError):
        settings.use("cloud")
