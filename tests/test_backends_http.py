"""Exercise the real HTTP backends against a fake local server (no model needed)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agora.llm import make_backend

SEEN: list[dict] = []


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send(200, {"models": [{"name": "llama3.2:3b"}]})
        elif self.path == "/v1/models":
            self._send(200, {"data": [{"id": "local-model"}]})
        else:
            self._send(404, {})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append({"path": self.path, **body})
        if self.path == "/api/chat":
            self._send(200, {"message": {"role": "assistant",
                                         "content": 'Sure! {"stance": 0.4, "actions": []}'}})
        elif self.path == "/v1/chat/completions":
            if "response_format" in body:          # server without JSON mode
                self._send(400, {"error": "response_format not supported"})
            else:
                self._send(200, {"choices": [{"message": {"content": '{"stance": -0.2}'}}]})
        else:
            self._send(404, {})


@pytest.fixture(scope="module")
def server():
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_ollama(server):
    be = make_backend({"backend": "ollama", "model": "llama3.2:3b", "url": server})
    assert be.status()[0]
    out = be.generate_json([{"role": "user", "content": "hi"}], seed=5, max_tokens=50)
    assert out == {"stance": 0.4, "actions": []}
    req = SEEN[-1]
    assert req["format"] == "json" and req["options"]["seed"] == 5 and req["options"]["num_predict"] == 50


def test_ollama_missing_model(server):
    be = make_backend({"backend": "ollama", "model": "gemma3:4b", "url": server})
    ok, msg = be.status()
    assert not ok and "ollama pull gemma3:4b" in msg


def test_openai_compat_falls_back_without_json_mode(server):
    be = make_backend({"backend": "openai", "model": "local-model", "url": server})
    assert be.status()[0]
    assert be.generate_json([{"role": "user", "content": "hi"}]) == {"stance": -0.2}
    assert "response_format" not in SEEN[-1]
    be.generate_json([{"role": "user", "content": "again"}])   # remembers: no 400 round-trip
    assert "response_format" not in SEEN[-1]


def test_unreachable_server_reports_cleanly():
    be = make_backend({"backend": "ollama", "url": "http://127.0.0.1:9", "timeout": 1})
    ok, msg = be.status()
    assert not ok and "not running" in msg
