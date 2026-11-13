"""Website: where the model runs (settings), the plan, and a study cannot redirect your data."""
import base64
import json

from test_web import DOC, call, web  # noqa: F401  (web is a fixture)


def test_settings_start_empty_and_never_reveal_the_key(web):
    base, _ = web
    s = call(base, "GET", "/api/settings")[1]
    assert s["active"] == "" and s["profiles"] == {}
    cloud = {"kind": "cloud", "model": "m1", "url": "https://api.example.com", "api_key": "sk-secret"}
    assert call(base, "POST", "/api/settings", cloud)[0] == 400                   # no consent given
    st, r = call(base, "POST", "/api/settings", {**cloud, "consent": True, "price_in": 1, "price_out": 2})
    assert st == 200 and r["active"] == "cloud" and r["profiles"]["cloud"]["has_key"] is True
    assert "sk-secret" not in json.dumps(r)
    info = call(base, "GET", "/api/info")[1]
    assert "sk-secret" not in json.dumps(info) and info["llm_default"]["url"] == "https://api.example.com"


def test_switch_profiles(web):
    base, _ = web
    assert call(base, "POST", "/api/settings", {"kind": "local", "model": "llama3.2:3b"})[1]["active"] == "local"
    call(base, "POST", "/api/settings", {"kind": "cloud", "model": "m1", "url": "https://api.example.com",
                                          "consent": True})
    assert call(base, "GET", "/api/settings")[1]["active"] == "cloud"
    assert call(base, "POST", "/api/settings", {"use": "local"})[1]["active"] == "local"
    assert call(base, "POST", "/api/settings", {"use": "nothing"})[0] == 400


def test_own_server_must_be_private(web):
    base, _ = web
    assert call(base, "POST", "/api/settings", {"kind": "server", "model": "m", "url": "https://api.example.com"})[0] == 400
    st, r = call(base, "POST", "/api/settings", {"kind": "server", "model": "m", "url": "192.168.1.50:8000"})
    assert st == 200 and r["profiles"]["server"]["url"] == "http://192.168.1.50:8000"


def test_a_study_form_cannot_choose_a_remote_address(web):
    base, app = web
    body = {"name": "x", "prompt": "q?", "files": [{"name": "plan.md", "data": base64.b64encode(DOC).decode()}],
            "options": {"backend": "ollama", "url": "https://evil.example.com"}}
    st, r = call(base, "POST", "/api/projects", body)
    assert st == 400 and "Settings" in r["error"]
    assert not any(p.is_dir() for p in app.ws.iterdir())          # nothing left behind


def test_plan_endpoint(web):
    base, _ = web
    pid = call(base, "POST", "/api/projects/demo")[1]["id"]
    st, r = call(base, "GET", f"/api/projects/{pid}/plan")
    assert st == 200 and r["calls"] > 0 and r["source"] == "rough" and r["time_text"]
    r2 = call(base, "GET", f"/api/projects/{pid}/plan?agents=1000&scenarios=2")[1]
    assert r2["calls"] > r["calls"] and set(r2["presets"]) == {"Quick", "Overnight", "Weekend"}
