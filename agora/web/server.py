"""`agora web`: a local website for the whole pipeline, like MiroFish's app.

Runs on http://127.0.0.1:<port> using only the Python standard library. It is meant for
your own machine: it binds to localhost, rejects requests for other host names (DNS
rebinding), requires a custom header on every change (blocks cross-site form posts),
and only touches project folders inside its workspace.
"""
from __future__ import annotations

import base64
import json
import re
import shutil
import sqlite3
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml

from .. import __version__, hardware, scenario as scenario_mod
from ..platforms import REGISTRY
from .jobs import Job, Jobs

MAX_BODY = 300 * 1024 * 1024
PROJECT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
SAFE_FILE = re.compile(r"[^A-Za-z0-9 ._()\-]+")
DEMO = "nutrivance_sampling"


class ApiError(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status = status


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50]
    return s or "study"


def _ro(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    db = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5)
    return db


class App:
    def __init__(self, workspace: Path, port: int):
        self.ws = Path(workspace).expanduser().resolve()
        self.ws.mkdir(parents=True, exist_ok=True)
        self.port = port
        self.jobs = Jobs()
        self.profile = hardware.detect()

    # ---------------------------------------------------------------- helpers
    def project_dir(self, pid: str, must_exist: bool = True) -> Path:
        if not PROJECT_ID.match(pid or ""):
            raise ApiError(404, "No such project")
        p = (self.ws / pid).resolve()
        if p.parent != self.ws:
            raise ApiError(404, "No such project")
        if must_exist and not p.is_dir():
            raise ApiError(404, "No such project")
        return p

    def new_id(self, name: str) -> str:
        base = slugify(name)
        pid, n = base, 2
        while (self.ws / pid).exists():
            pid, n = f"{base}-{n}", n + 1
        return pid

    # ---------------------------------------------------------------- reads
    def info(self) -> dict:
        p = self.profile
        return {"version": __version__, "workspace": str(self.ws),
                "hardware": p.as_dict(),
                "llm_default": {"backend": "ollama", "model": p.model, "url": "http://localhost:11434"},
                "platforms": [{"key": k, "label": s.label, "kind": s.kind} for k, s in REGISTRY.items()]}

    def llm_status(self, q: dict) -> dict:
        from ..llm import LLMError, make_backend
        cfg = {"backend": q.get("backend", "ollama"), "model": q.get("model") or self.profile.model,
               "url": q.get("url") or "http://localhost:11434", "cache": False}
        try:
            ok, msg = make_backend(cfg).status()
        except LLMError as e:
            ok, msg = False, str(e)
        return {"ok": ok, "message": msg}

    def run_state(self, proj: Path) -> dict:
        total = None
        try:
            total = yaml.safe_load((proj / "scenario.yaml").read_text(encoding="utf-8")).get("rounds")
        except Exception:  # noqa: BLE001
            pass
        db = _ro(proj / "agora.db")
        if db is None:
            return {"started": False, "rounds_done": 0, "rounds_total": total}
        try:
            n = db.execute("SELECT COUNT(*) FROM rounds").fetchone()[0]
            agents = db.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
            last = db.execute("SELECT sim_time FROM rounds ORDER BY round DESC LIMIT 1").fetchone()
            t = db.execute("SELECT COALESCE(SUM(seconds),0), COALESCE(SUM(llm_calls),0), "
                           "COALESCE(SUM(cache_hits),0) FROM rounds").fetchone()
        except sqlite3.Error:
            return {"started": False, "rounds_done": 0, "rounds_total": total}
        finally:
            db.close()
        return {"started": agents > 0, "rounds_done": n, "rounds_total": total,
                "sim_time": last[0] if last else None, "seconds": t[0], "llm_calls": t[1],
                "cache_hits": t[2]}

    def list_projects(self) -> list[dict]:
        out = []
        for d in sorted(self.ws.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not d.is_dir() or not PROJECT_ID.match(d.name):
                continue
            if not ((d / "scenario.yaml").exists() or (d / "prompt.txt").exists()):
                continue
            job = self.jobs.current(d.name)
            out.append({"id": d.name, "title": self._title(d), "prompt": self._prompt(d),
                        "has_scenario": (d / "scenario.yaml").exists(),
                        "has_graph": (d / "graph.html").exists(),
                        "run": self.run_state(d), "job": job.as_dict() if job else None,
                        "modified": d.stat().st_mtime})
        return out

    @staticmethod
    def _prompt(d: Path) -> str:
        p = d / "prompt.txt"
        return p.read_text(encoding="utf-8").strip() if p.exists() else ""

    @staticmethod
    def _title(d: Path) -> str:
        meta = d / "agora.json"
        if meta.exists():
            try:
                return json.loads(meta.read_text(encoding="utf-8")).get("title") or d.name
            except ValueError:
                pass
        return d.name

    def project(self, pid: str) -> dict:
        d = self.project_dir(pid)
        info = {"id": pid, "title": self._title(d), "prompt": self._prompt(d),
                "has_graph": (d / "graph.html").exists(), "run": self.run_state(d),
                "job": (j.as_dict() if (j := self.jobs.current(pid)) else None),
                "sources": sorted(p.name for p in (d / "sources").glob("*")) if (d / "sources").exists() else []}
        sp = d / "scenario.yaml"
        info["has_scenario"] = sp.exists()
        info["has_report"] = (d / "report" / "report.html").exists()
        try:
            info["forked_from"] = json.loads((d / "agora.json").read_text(encoding="utf-8")).get("forked_from")
        except (OSError, ValueError):
            info["forked_from"] = None
        if sp.exists():
            try:
                sc = scenario_mod.load(sp)
                info["scenario"] = {
                    "name": sc.name, "topic": sc.topic, "question": sc.question, "context": sc.context,
                    "rounds": sc.rounds, "round_hours": sc.round_hours, "start": sc.start.isoformat(),
                    "llm_agents": sc.llm_agents, "crowd_agents": sc.crowd_agents, "llm": sc.llm,
                    "segments": [{"name": s.name, "share": s.share, "persona": s.persona,
                                  "stance": s.stance_mean, "platforms": s.platforms} for s in sc.segments],
                    "accounts": [{"id": a.id, "name": a.name, "persona": a.persona, "platforms": a.platforms}
                                 for a in sc.accounts],
                    "spaces": [{"platform": s.platform, "name": s.name, "size": s.size} for s in sc.spaces],
                    "events": [{"round": e.round, "type": e.type, "text": e.text or e.question,
                                "account": e.account, "platform": e.platform, "name": e.name,
                                "conditional": bool(e.when)} for e in sc.events],
                    "conversions": [{"name": c.name, "label": c.label, "open": c.open_round,
                                     "close": min(c.close_round, sc.rounds)} for c in sc.conversions],
                    "voices": len(sc.voices)}
                info["scenario_error"] = ""
            except Exception as e:  # noqa: BLE001
                info["scenario_error"] = str(e)
        gdb = _ro(d / "graph.db")
        if gdb is not None:
            try:
                info["graph"] = {
                    "nodes": gdb.execute("SELECT COUNT(*) FROM nodes").fetchone()[0],
                    "edges": gdb.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
                    "documents": gdb.execute("SELECT COUNT(*) FROM documents").fetchone()[0]}
            except sqlite3.Error:
                pass
            finally:
                gdb.close()
        return info

    def live(self, pid: str, q: dict) -> dict:
        d = self.project_dir(pid)
        out = {"run": self.run_state(d), "posts": [], "trend": [], "conversions": [], "polls": [],
               "events": [], "platforms": {}}
        db = _ro(d / "agora.db")
        if db is None:
            return out
        try:
            after = int(q.get("after", -1))
            where, args = ["p.kind NOT IN ('repost')"], []
            if q.get("platform"):
                where.append("p.platform = ?")
                args.append(q["platform"])
            if q.get("space"):
                where.append("p.space = ?")
                args.append(q["space"])
            if after >= 0:
                where.append("p.id > ?")
                args.append(after)
            rows = db.execute(
                "SELECT p.id, p.round, p.platform, p.space, p.kind, p.parent, p.root, p.text, p.stance,"
                " a.name, a.handle, a.kind, a.segment, s.text, sa.name FROM posts p"
                " JOIN agents a ON a.id = p.author LEFT JOIN posts s ON s.id = p.root AND p.kind = 'forward'"
                " LEFT JOIN agents sa ON sa.id = s.author WHERE " + " AND ".join(where) +
                " ORDER BY p.id DESC LIMIT 80", args).fetchall()
            ids = [r[0] for r in rows] + [r[6] for r in rows]
            counts = {}
            if ids:
                marks = ",".join("?" * len(ids))
                for post, typ, n in db.execute(
                        f"SELECT post, substr(type,1,instr(type||':',':')-1), COUNT(*) FROM engagements "
                        f"WHERE post IN ({marks}) GROUP BY post, 2", ids):
                    counts.setdefault(post, {})[typ] = n
                for parent, n in db.execute(
                        f"SELECT parent, COUNT(*) FROM posts WHERE kind='reply' AND parent IN ({marks}) "
                        "GROUP BY parent", ids):
                    counts.setdefault(parent, {})["replies"] = n
            for (pid_, rnd, plat, space, kind, parent, root, text, st, name, handle, akind, seg,
                 src_text, src_name) in rows:
                c = counts.get(root if kind == "forward" else pid_, {})
                to = quoted = None
                if kind == "dm" and space.startswith("@dm:"):
                    x, _, y = space[4:].partition("-")
                    other = int(y) if int(x) == db.execute("SELECT id FROM agents WHERE handle=?", (handle,)).fetchone()[0] else int(x)
                    to = db.execute("SELECT name FROM agents WHERE id=?", (other,)).fetchone()[0]
                    space = ""
                if kind in ("quote", "reply") and parent is not None:
                    pr = db.execute("SELECT a.name, p.text FROM posts p JOIN agents a ON a.id=p.author WHERE p.id=?",
                                    (parent,)).fetchone()
                    quoted = {"author": pr[0], "text": pr[1][:200]} if pr else None
                out["posts"].append({
                    "to": to, "quoted": quoted,
                    "id": pid_, "round": rnd, "platform": plat, "space": space, "kind": kind,
                    "parent": parent, "text": src_text if kind == "forward" else text,
                    "forwarded_from": src_name if kind == "forward" else None, "stance": st,
                    "author": name, "handle": handle, "agent_kind": akind, "segment": seg,
                    "likes": c.get("like", 0), "ups": c.get("upvote", 0), "downs": c.get("downvote", 0),
                    "shares": c.get("repost", 0) + c.get("forward", 0), "replies": c.get("replies", 0)})
            out["trend"] = db.execute(
                "SELECT o.round, a.segment, ROUND(AVG(o.stance), 4) FROM opinions o JOIN agents a "
                "ON a.id = o.agent WHERE a.kind != 'account' GROUP BY o.round, a.segment "
                "ORDER BY o.round").fetchall()
            out["conversions"] = db.execute(
                "SELECT round, name, COUNT(*) FROM conversions GROUP BY round, name ORDER BY round").fetchall()
            out["conversion_base"] = dict(db.execute(
                "SELECT segment, COUNT(*) FROM agents WHERE kind != 'account' GROUP BY segment").fetchall())
            out["polls"] = [{"name": n, "round": r, "yes": y, "no": no, "passed": bool(p)}
                            for n, r, y, no, p in db.execute("SELECT * FROM poll_results")]
            out["events"] = [{"round": r, "kind": k, "detail": json.loads(dt)}
                             for r, k, dt in db.execute("SELECT * FROM event_log ORDER BY rowid")]
            out["platforms"] = dict(db.execute(
                "SELECT platform, COUNT(*) FROM posts WHERE kind NOT IN ('repost','forward') "
                "GROUP BY platform").fetchall())
            out["spaces"] = [list(r) for r in db.execute(
                "SELECT DISTINCT platform, space FROM memberships ORDER BY platform, space")]
        except sqlite3.Error as e:
            out["error"] = str(e)
        finally:
            db.close()
        return out

    # ---------------------------------------------------------------- writes
    def create(self, body: dict) -> dict:
        from ..graph.ingest import SUPPORTED
        from ..pipeline import CreateOptions, create_project
        name = str(body.get("name") or "").strip() or "study"
        prompt = str(body.get("prompt") or "").strip()
        files = body.get("files") or []
        if not prompt:
            raise ApiError(400, "Describe what you want to predict.")
        if not files:
            raise ApiError(400, "Add at least one document.")
        pid = self.new_id(name)
        d = self.project_dir(pid, must_exist=False)
        up = d / "uploads"
        up.mkdir(parents=True)
        paths = []
        for f in files:
            fname = SAFE_FILE.sub("_", Path(str(f.get("name", "file"))).name)[:120] or "file"
            if Path(fname).suffix.lower() not in SUPPORTED:
                shutil.rmtree(d, ignore_errors=True)
                raise ApiError(400, f"{fname}: unsupported file type")
            try:
                data = base64.b64decode(str(f.get("data", "")), validate=True)
            except ValueError:
                shutil.rmtree(d, ignore_errors=True)
                raise ApiError(400, f"{fname}: could not read the upload")
            path = up / fname
            path.write_bytes(data)
            paths.append(path)
        (d / "agora.json").write_text(json.dumps({"title": name}), encoding="utf-8")
        (d / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")
        o = body.get("options") or {}
        llm = {"backend": "mock"} if o.get("mock") else {
            k: o.get(k) for k in ("backend", "model", "url") if o.get(k)}
        opts = CreateOptions(fast=bool(o.get("fast")), personas=o.get("personas", True) is not False,
                             llm_agents=int(o["llm_agents"]) if o.get("llm_agents") else None,
                             crowd=int(o["crowd"]) if o.get("crowd") else None,
                             hours=float(o.get("hours") or 12), llm=llm)

        def work(job: Job):
            create_project(d, paths, prompt, opts, say=job.say, should_stop=lambda: job.stopping)
            shutil.rmtree(up, ignore_errors=True)    # copies now live in sources/

        job = self.jobs.start("create", pid, work)
        return {"id": pid, "job": job.as_dict()}

    def create_demo(self) -> dict:
        pid = self.new_id("nutrivance-demo")
        d = self.project_dir(pid, must_exist=False)
        d.mkdir()
        src = resources.files("agora.examples").joinpath(DEMO, "scenario.yaml")
        (d / "scenario.yaml").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        (d / "agora.json").write_text(json.dumps({"title": "Demo: free probiotic sampling"}),
                                      encoding="utf-8")
        (d / "prompt.txt").write_text(scenario_mod.load(d / "scenario.yaml").question + "\n",
                                      encoding="utf-8")
        return {"id": pid}

    def save_scenario(self, pid: str, body: dict) -> dict:
        d = self.project_dir(pid)
        if self.jobs.busy(pid):
            raise ApiError(409, "Wait for the current job to finish.")
        if self.run_state(d)["started"]:
            raise ApiError(409, "This simulation has already started. Reset it before editing the setup.")
        text = str(body.get("text") or "")
        try:
            scenario_mod.from_dict(yaml.safe_load(text))
        except Exception as e:  # noqa: BLE001
            raise ApiError(400, f"Not saved: {e}")
        if body.get("check_only"):
            return {"ok": True, "message": "Looks good."}
        (d / "scenario.yaml").write_text(text, encoding="utf-8")
        return {"ok": True, "message": "Saved."}

    def start_run(self, pid: str, body: dict) -> dict:
        from ..sim.engine import Simulation
        d = self.project_dir(pid)
        if not (d / "scenario.yaml").exists():
            raise ApiError(400, "This project has no setup yet.")
        override = {"backend": "mock"} if body.get("mock") else {}
        rounds = int(body["rounds"]) if body.get("rounds") else None

        def work(job: Job):
            sim = Simulation(d, override)
            try:
                ok, msg = sim.llm.status()
                if not ok:
                    raise RuntimeError(msg)
                sim.prepare()
                start = sim.store.last_round() + 1
                job.say(f"{'Resuming' if start else 'Starting'} at round {start + 1} of "
                        f"{sim.sc.rounds} with {sim.llm_cfg.backend}:{sim.llm_cfg.model}")

                def prog(p):
                    job.progress = p
                    if p["round"] % 6 == 5 or p["round"] + 1 == p["of"]:
                        job.say(f"Round {p['round'] + 1}/{p['of']}: {p['active']} active, "
                                f"{p['posts']} posts, {p['conversions']} actions, "
                                f"{p['llm_calls']} model calls")

                sim.run(rounds=rounds, progress=prog, should_stop=lambda: job.stopping)
                job.say("Finished." if sim.store.last_round() + 1 >= sim.sc.rounds else "Paused.")
            finally:
                sim.close()

        job = self.jobs.start("run", pid, work)
        return {"job": job.as_dict()}

    # ---------------------------------------------------------------- report + interaction
    def _llm(self, d: Path, mock: bool):
        from ..pipeline import make_llm
        if mock:
            return make_llm(d, {"backend": "mock"})[1]
        sc = scenario_mod.load(d / "scenario.yaml")
        _, llm = make_llm(d, {k: v for k, v in sc.llm.items() if k in ("backend", "model", "url", "parallel")})
        ok, msg = llm.status()
        if not ok:
            raise ApiError(503, msg + " (Tick 'without a model' to try it with placeholder answers.)")
        return llm

    def _need_run(self, d: Path):
        if not self.run_state(d)["started"]:
            raise ApiError(400, "Run the simulation first.")

    def start_report(self, pid: str, body: dict) -> dict:
        from ..report.writer import write_report
        d = self.project_dir(pid)
        self._need_run(d)
        llm = self._llm(d, bool(body.get("mock")))

        def work(job: Job):
            try:
                write_report(d, llm, say=job.say, should_stop=lambda: job.stopping)
            finally:
                if hasattr(llm, "close"):
                    llm.close()

        return {"job": self.jobs.start("report", pid, work).as_dict()}

    def ask(self, pid: str, body: dict) -> dict:
        from ..report.interact import ask
        d = self.project_dir(pid)
        self._need_run(d)
        q = str(body.get("question") or "").strip()
        if not q:
            raise ApiError(400, "Ask a question.")
        return ask(d, self._llm(d, bool(body.get("mock"))), q[:1000])

    def people(self, pid: str, q: dict) -> list:
        from ..report.interact import people
        d = self.project_dir(pid)
        self._need_run(d)
        return people(d, segment=q.get("segment", ""), query=q.get("q", ""))

    def person(self, pid: str, handle: str) -> dict:
        from ..report.interact import profile
        d = self.project_dir(pid)
        self._need_run(d)
        try:
            return profile(d, handle)
        except KeyError as e:
            raise ApiError(404, str(e))

    def chat(self, pid: str, handle: str, body: dict) -> dict:
        from ..report.interact import chat
        d = self.project_dir(pid)
        self._need_run(d)
        msg = str(body.get("message") or "").strip()
        if not msg:
            raise ApiError(400, "Write a message.")
        try:
            return chat(d, self._llm(d, bool(body.get("mock"))), handle, msg[:1500])
        except KeyError as e:
            raise ApiError(404, str(e))

    def start_interview(self, pid: str, body: dict) -> dict:
        from ..report.interact import interview
        d = self.project_dir(pid)
        self._need_run(d)
        q = str(body.get("question") or "").strip()
        if not q:
            raise ApiError(400, "Write the interview question.")
        llm = self._llm(d, bool(body.get("mock")))
        n = max(1, min(40, int(body.get("n") or 8)))

        def work(job: Job):
            job.progress = {"result": interview(d, llm, q[:1000], segment=str(body.get("segment") or ""),
                                                n=n, say=job.say)}

        return {"job": self.jobs.start("interview", pid, work).as_dict()}

    def history(self, pid: str, q: dict) -> list:
        from ..report.interact import history
        d = self.project_dir(pid)
        if not (d / "agora.db").exists():
            return []
        return history(d, q.get("thread", "report"))

    def inject(self, pid: str, body: dict) -> dict:
        from ..report.interact import inject
        d = self.project_dir(pid)
        self._need_run(d)
        try:
            return inject(d, body)
        except ValueError as e:
            raise ApiError(400, str(e))

    def injected(self, pid: str) -> list:
        from ..report.interact import injected
        return injected(self.project_dir(pid))

    def fork(self, pid: str, body: dict) -> dict:
        from ..report.interact import fork
        d = self.project_dir(pid)
        title = str(body.get("title") or "").strip()
        new = self.new_id(title or f"{pid}-variant")
        fork(d, self.project_dir(new, must_exist=False), title=title)
        return {"id": new}

    def compare(self, q: dict) -> dict:
        from ..report.interact import compare
        ids = [x for x in (q.get("ids") or "").split(",") if x][:6]
        if len(ids) < 2:
            raise ApiError(400, "Choose at least two studies.")
        return compare([self.project_dir(i) for i in ids])

    def stop(self, pid: str) -> dict:
        self.project_dir(pid)
        j = self.jobs.current(pid)
        if j and j.state == "running":
            j.stop()
        return {"ok": True}

    def reset(self, pid: str) -> dict:
        d = self.project_dir(pid)
        if self.jobs.busy(pid):
            raise ApiError(409, "Stop the running job first.")
        for f in ("agora.db", "agora.db-wal", "agora.db-shm"):
            (d / f).unlink(missing_ok=True)
        return {"ok": True}

    def delete(self, pid: str) -> dict:
        d = self.project_dir(pid)
        if self.jobs.busy(pid):
            raise ApiError(409, "Stop the running job first.")
        shutil.rmtree(d)
        self.jobs.by_project.pop(pid, None)
        return {"ok": True}


class Handler(BaseHTTPRequestHandler):
    app: App = None  # set by serve()
    server_version = "Agora"

    def log_message(self, fmt, *args):  # quiet
        pass

    # ---------------------------------------------------------------- plumbing
    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        return host in {f"127.0.0.1:{self.app.port}", f"localhost:{self.app.port}"}

    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj):
        self._send(status, json.dumps(obj, default=str).encode(), "application/json; charset=utf-8")

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ApiError(413, "Upload too large (300 MB max).")
        if not n:
            return {}
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            raise ApiError(415, "Expected JSON")
        try:
            return json.loads(self.rfile.read(n))
        except ValueError:
            raise ApiError(400, "Bad JSON")

    def _dispatch(self, method: str):
        if not self._host_ok():
            return self._send(421, b"Misdirected request", "text/plain")
        if method != "GET" and self.headers.get("X-Agora") != "1":
            return self._send(403, b"Missing X-Agora header", "text/plain")
        url = urlparse(self.path)
        q = {k: v[-1] for k, v in parse_qs(url.query).items()}
        parts = [p for p in url.path.split("/") if p]
        try:
            if method == "GET" and not parts:
                html = resources.files("agora.web").joinpath("static", "index.html").read_bytes()
                return self._send(200, html, "text/html; charset=utf-8", {
                    "Content-Security-Policy": "default-src 'self'; script-src 'unsafe-inline'; "
                    "style-src 'unsafe-inline'; img-src 'self' data:; frame-src 'self'; "
                    "connect-src 'self'; frame-ancestors 'none'"})
            if parts[:1] != ["api"]:
                raise ApiError(404, "Not found")
            res = self._route(method, parts[1:], q)
            if isinstance(res, tuple):          # raw response
                return self._send(200, res[0], res[1])
            return self._json(200, res)
        except ApiError as e:
            return self._json(e.status, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            import sys
            import traceback
            print(f"[agora] error on {method} {self.path}:", file=sys.stderr)
            traceback.print_exc()
            return self._json(500, {"error": f"{e.__class__.__name__}: {e}"})

    def _route(self, method: str, p: list[str], q: dict):
        a = self.app
        if method == "GET" and p == ["info"]:
            return a.info()
        if method == "GET" and p == ["llm", "status"]:
            return a.llm_status(q)
        if p == ["projects"]:
            if method == "GET":
                return a.list_projects()
            if method == "POST":
                return a.create(self._body())
        if p == ["projects", "demo"] and method == "POST":
            return a.create_demo()
        if len(p) >= 2 and p[0] == "projects":
            pid, rest = p[1], p[2:]
            if method == "GET" and not rest:
                return a.project(pid)
            if method == "DELETE" and not rest:
                return a.delete(pid)
            if rest == ["scenario"]:
                if method == "GET":
                    f = a.project_dir(pid) / "scenario.yaml"
                    return {"text": f.read_text(encoding="utf-8") if f.exists() else ""}
                if method == "PUT":
                    return a.save_scenario(pid, self._body())
            if rest == ["graph"] and method == "GET":
                f = a.project_dir(pid) / "graph.html"
                if not f.exists():
                    raise ApiError(404, "No graph yet")
                return (f.read_bytes(), "text/html; charset=utf-8")
            if rest == ["live"] and method == "GET":
                return a.live(pid, q)
            if rest == ["run"] and method == "POST":
                return a.start_run(pid, self._body())
            if rest == ["stop"] and method == "POST":
                return a.stop(pid)
            if rest == ["reset"] and method == "POST":
                return a.reset(pid)
            if rest == ["report"] and method == "POST":
                return a.start_report(pid, self._body())
            if rest == ["report"] and method == "GET":
                f = a.project_dir(pid) / "report" / "report.html"
                if not f.exists():
                    raise ApiError(404, "No report yet")
                return (f.read_bytes(), "text/html; charset=utf-8")
            if rest == ["report.md"] and method == "GET":
                f = a.project_dir(pid) / "report" / "report.md"
                if not f.exists():
                    raise ApiError(404, "No report yet")
                return (f.read_bytes(), "text/markdown; charset=utf-8")
            if rest == ["ask"] and method == "POST":
                return a.ask(pid, self._body())
            if rest == ["people"] and method == "GET":
                return a.people(pid, q)
            if len(rest) == 2 and rest[0] == "people" and method == "GET":
                return a.person(pid, rest[1])
            if len(rest) == 3 and rest[0] == "people" and rest[2] == "chat" and method == "POST":
                return a.chat(pid, rest[1], self._body())
            if rest == ["interview"] and method == "POST":
                return a.start_interview(pid, self._body())
            if rest == ["history"] and method == "GET":
                return a.history(pid, q)
            if rest == ["inject"] and method == "POST":
                return a.inject(pid, self._body())
            if rest == ["injected"] and method == "GET":
                return a.injected(pid)
            if rest == ["fork"] and method == "POST":
                return a.fork(pid, self._body())
        if p == ["compare"] and method == "GET":
            return a.compare(q)
        raise ApiError(404, "Not found")

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")


def make_server(workspace: Path, port: int = 8765) -> tuple[ThreadingHTTPServer, App]:
    app = App(workspace, port)
    handler = type("AgoraHandler", (Handler,), {"app": app})
    srv = ThreadingHTTPServer(("127.0.0.1", port), handler)
    srv.daemon_threads = True
    if port == 0:                      # tests: pick a free port
        app.port = srv.server_address[1]
    return srv, app


def serve(workspace: Path, port: int = 8765, open_browser: bool = True) -> None:
    srv, app = make_server(workspace, port)
    url = f"http://127.0.0.1:{app.port}/"
    print(f"Agora is running at {url}\nProjects folder: {app.ws}\nPress Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping... (running jobs save their last finished step)")
        app.jobs.stop_all()
    finally:
        srv.server_close()
