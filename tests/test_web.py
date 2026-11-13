"""Local web app: API flow and the safety checks that keep it local."""
import base64
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from agora.web.server import make_server

DOC = b"Nutrivance Precision Probiotics (NPP) offers a free sample to residents of Lakeview Residency in Guntur."


@pytest.fixture
def web(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))      # never read your real settings
    srv, app = make_server(tmp_path / "ws", port=0)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield f"http://127.0.0.1:{app.port}", app
    app.jobs.stop_all()
    srv.shutdown()
    srv.server_close()


def call(base, method, path, body=None, headers=None):
    h = {"X-Agora": "1", **(headers or {})}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if r.headers.get_content_type() == "application/json" else raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def wait_job(base, pid, timeout=60):
    t = time.time()
    while time.time() - t < timeout:
        _, p = call(base, "GET", f"/api/projects/{pid}")
        if p["job"] and p["job"]["state"] != "running":
            return p
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def test_index_and_info(web):
    base, _ = web
    st, html = call(base, "GET", "/")
    assert st == 200 and b"<title>Agora</title>" in html and b"<script src" not in html
    st, info = call(base, "GET", "/api/info")
    keys = {p["key"] for p in info["platforms"]}
    assert {"instagram", "whatsapp", "facebook", "youtube", "telegram", "linkedin"} <= keys


def test_upload_build_run_flow(web):
    base, _ = web
    body = {"name": "My Study!", "prompt": "Will residents register for the free sample?",
            "files": [{"name": "../../plan.md", "data": base64.b64encode(DOC).decode()}],
            "options": {"mock": True, "llm_agents": 6, "crowd": 120}}
    st, r = call(base, "POST", "/api/projects", body)
    assert st == 200 and r["id"] == "my-study"
    p = wait_job(base, "my-study")
    assert p["job"]["state"] == "done", p["job"]
    assert p["has_graph"] and p["has_scenario"] and p["sources"] == ["plan.md"]   # path stripped
    st, g = call(base, "GET", "/api/projects/my-study/graph")
    assert st == 200 and (b"Lakeview" in g or b"Nutrivance" in g)

    st, y = call(base, "GET", "/api/projects/my-study/scenario")
    bad = y["text"].replace("rounds:", "rounds: -5 #")
    st, r = call(base, "PUT", "/api/projects/my-study/scenario", {"text": bad})
    assert st == 400
    st, r = call(base, "PUT", "/api/projects/my-study/scenario", {"text": y["text"], "check_only": True})
    assert st == 200 and r["ok"]

    st, _ = call(base, "POST", "/api/projects/my-study/run", {"mock": True})
    assert st == 200
    p = wait_job(base, "my-study")
    assert p["job"]["state"] == "done" and p["run"]["rounds_done"] == p["run"]["rounds_total"]
    st, live = call(base, "GET", "/api/projects/my-study/live")
    assert live["posts"] and live["trend"]
    st, _ = call(base, "PUT", "/api/projects/my-study/scenario", {"text": y["text"]})
    assert st == 409                     # cannot edit a started run
    assert call(base, "POST", "/api/projects/my-study/reset", {})[0] == 200
    assert call(base, "PUT", "/api/projects/my-study/scenario", {"text": y["text"]})[0] == 200


def test_demo_and_stop(web):
    base, app = web
    st, r = call(base, "POST", "/api/projects/demo")
    pid = r["id"]
    st, p = call(base, "GET", f"/api/projects/{pid}")
    assert p["scenario"]["rounds"] == 72 and len(p["scenario"]["spaces"]) >= 5
    call(base, "POST", f"/api/projects/{pid}/run", {"mock": True})
    call(base, "POST", f"/api/projects/{pid}/stop", {})
    p = wait_job(base, pid)
    assert p["job"]["state"] in ("stopped", "done")
    assert call(base, "POST", f"/api/projects/{pid}/run", {"mock": True})[0] == 200   # resume
    p = wait_job(base, pid)
    assert p["run"]["rounds_done"] == 72
    assert call(base, "DELETE", f"/api/projects/{pid}")[0] == 200
    assert not (app.ws / pid).exists()


def test_rejects_other_hosts_and_cross_site_writes(web):
    base, _ = web
    assert call(base, "GET", "/api/info", headers={"Host": "attacker.example:80"})[0] == 421
    req = urllib.request.Request(base + "/api/projects/demo", data=b"", method="POST")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=5)              # no X-Agora header, like a form post
    assert e.value.code == 403


@pytest.mark.parametrize("pid", ["..", "..%2F..%2Fetc", "UPPER", "a/b", "%2e%2e"])
def test_no_path_traversal(web, pid):
    base, _ = web
    st, _ = call(base, "GET", f"/api/projects/{pid}/scenario")
    assert st == 404


def test_upload_validation(web):
    base, _ = web
    st, r = call(base, "POST", "/api/projects", {"name": "x", "prompt": "q",
                                                 "files": [{"name": "evil.exe", "data": "AAAA"}]})
    assert st == 400 and "unsupported" in r["error"]
    st, r = call(base, "POST", "/api/projects", {"name": "x", "prompt": "", "files": []})
    assert st == 400


def test_report_and_interaction_endpoints(web):
    base, app = web
    pid = call(base, "POST", "/api/projects/demo")[1]["id"]
    assert call(base, "POST", f"/api/projects/{pid}/report", {"mock": True})[0] == 400   # not run yet
    call(base, "POST", f"/api/projects/{pid}/run", {"mock": True, "rounds": 20})
    wait_job(base, pid)
    assert call(base, "POST", f"/api/projects/{pid}/inject", {"type": "news", "text": "Big news"})[1]["round"] == 20
    assert len(call(base, "GET", f"/api/projects/{pid}/injected")[1]) == 1
    call(base, "POST", f"/api/projects/{pid}/report", {"mock": True})
    p = wait_job(base, pid)
    assert p["job"]["state"] == "done" and p["has_report"]
    st, html = call(base, "GET", f"/api/projects/{pid}/report")
    assert st == 200 and b"Opinion by group" in html
    assert call(base, "GET", f"/api/projects/{pid}/report.md")[0] == 200
    ans = call(base, "POST", f"/api/projects/{pid}/ask", {"question": "Who registered?", "mock": True})[1]
    assert ans["answer"]
    ppl = call(base, "GET", f"/api/projects/{pid}/people")[1]
    h = next(x["handle"] for x in ppl if x["kind"] == "llm")
    assert call(base, "GET", f"/api/projects/{pid}/people/{h}")[1]["handle"] == h
    assert call(base, "POST", f"/api/projects/{pid}/people/{h}/chat", {"message": "hi", "mock": True})[1]["reply"]
    assert call(base, "GET", f"/api/projects/{pid}/people/nobody")[0] == 404
    call(base, "POST", f"/api/projects/{pid}/interview", {"question": "Buy?", "n": 3, "mock": True})
    p = wait_job(base, pid)
    assert len(p["job"]["progress"]["result"]["answers"]) == 3
    new = call(base, "POST", f"/api/projects/{pid}/fork", {"title": "Variant"})[1]["id"]
    assert call(base, "GET", f"/api/projects/{new}")[1]["forked_from"] == pid
    assert call(base, "GET", f"/api/compare?ids={pid}")[0] == 400
    c = call(base, "GET", f"/api/compare?ids={pid},{new}")[1]
    assert len(c["columns"]) == 2
    # a real model that is not running gives a clear 503, not a crash
    import yaml
    sc_path = app.ws / pid / "scenario.yaml"
    d = yaml.safe_load(sc_path.read_text(encoding="utf-8"))
    d.setdefault("llm", {})["url"] = "http://127.0.0.1:9"      # nothing listens here, so it fails fast
    sc_path.write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True), encoding="utf-8")
    st, r = call(base, "POST", f"/api/projects/{pid}/ask", {"question": "x"})
    assert st == 503 and "Ollama" in r["error"]


def test_calibrate_and_forecast_endpoints(web, tmp_path):
    import shutil
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from conftest import make_project
    base, app = web
    src = make_project(tmp_path, "small", rounds=24)
    import yaml
    d = yaml.safe_load((src / "scenario.yaml").read_text(encoding="utf-8"))
    d["population"] = {"llm_agents": 4, "crowd_agents": 120}
    (src / "scenario.yaml").write_text(yaml.safe_dump(d), encoding="utf-8")
    shutil.copytree(src, app.ws / "small")
    st, r = call(base, "POST", "/api/projects/small/data", {"kind": "observations", "text": "day,nonsense\n1,3"})
    assert st == 400 and "Unknown metric" in r["error"]
    st, r = call(base, "POST", "/api/projects/small/data",
                 {"kind": "observations", "text": "day,register_lakeview\n1,5\n2,12\n3,15\n4,16"})
    assert st == 200 and r["points"] == 4
    call(base, "POST", "/api/projects/small/calibrate", {})
    p = wait_job(base, "small", timeout=300)
    assert p["job"]["state"] == "done", p["job"]
    cs = call(base, "GET", "/api/projects/small/calibration")[1]
    assert cs["calibration"]["changes"] and not cs["applied"]
    assert call(base, "POST", "/api/projects/small/calibration/apply", {})[0] == 200
    assert call(base, "GET", "/api/projects/small/calibration")[1]["applied"]
    assert call(base, "GET", "/api/projects/small")[1]["scenario"]["name"]
    call(base, "POST", "/api/projects/small/forecast", {"runs": 5, "sensitivity": False})
    p = wait_job(base, "small", timeout=300)
    assert p["job"]["state"] == "done", p["job"]
    f = call(base, "GET", "/api/projects/small/calibration")[1]["forecast"]
    assert f["calibrated"] and f["monte_carlo"]["runs"] == 5
    assert "action:register_lakeview" in f["monte_carlo"]["summary"]
