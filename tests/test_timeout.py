from agora.pipeline import make_llm, public_cfg


def test_timeout_from_the_scenario_reaches_the_model(tmp_path):
    cfg = public_cfg({"backend": "ollama", "model": "llama3.2:3b", "timeout": 1800})
    assert cfg["timeout"] == 1800
    llm_cfg, _ = make_llm(tmp_path, cfg)
    assert llm_cfg.timeout == 1800


def test_default_timeout_is_unchanged_when_the_scenario_is_silent(tmp_path):
    llm_cfg, _ = make_llm(tmp_path, public_cfg({"backend": "ollama", "model": "llama3.2:3b"}))
    assert llm_cfg.timeout == 600.0
