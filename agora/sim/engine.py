"""The simulation loop.

Each round (a few simulated hours):
  1. scheduled events fire (news, official posts, polls/decisions)
  2. agents wake up depending on their activity level and the time of day
  3. every active agent gets a feed built from the round-start snapshot
  4. LLM voices decide what to think and do (in parallel); crowd agents update their
     opinion with the opinion-dynamics rule and like / vote / share
  5. all actions are applied in a fixed order and the round is saved atomically

Because feeds come from a snapshot, every random draw is seeded by (seed, round) and
model replies are cached, an interrupted run resumes to exactly the same result.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from typing import Callable, Iterable, Mapping

import numpy as np

from .. import scenario as scenario_mod
from ..llm import LLMConfig, LLMError, make_backend, parse_json
from ..store import Store
from ..settings import safe_study_llm
from . import llm_agent, opinion, population
from ..platforms import REGISTRY, is_spaced, resolve
from .platforms import FeedIndex, where_options
from .memory import WorldMemory
from .timing import Rhythm
from .world import Agent, Post, World, dm_people, dm_space

SCENARIO_FILE = "scenario.yaml"
DB_FILE = "agora.db"
CACHE_FILE = "llm_cache.db"


def _seed(*parts) -> int:
    return int(hashlib.sha256(json.dumps(parts).encode()).hexdigest()[:8], 16)


class RoundOutput:
    def __init__(self):
        self.posts: list[Post] = []
        self.engagements: list[tuple[int, int, str]] = []
        self.follows: list[tuple[int, int]] = []
        self.conversions: list[tuple[int, str]] = []
        self.thoughts: list[tuple[int, str]] = []
        self.polls: list[tuple[str, int, int, str]] = []
        self.poll_results: list[tuple[str, int, int, bool]] = []
        self.events: list[tuple[str, dict]] = []
        self.unfollows: list[tuple[str, int, int]] = []
        self.choices: list[tuple[int, str]] = []
        self.intentions: list[tuple[str, str, int]] = []
        self.mutes: list[tuple[int, int]] = []


class GovernedInputError(RuntimeError):
    """A governed run was started or resumed with input that is missing, altered or unverifiable."""


class SnapshotError(RuntimeError):
    """A snapshot or fork was refused (missing, corrupt, incomplete, mismatched or not replayable). Nothing is written."""


SNAPSHOT_DIR = "snapshots"
SNAPSHOT_SCHEMA = 2
# Columns that record timing or call statistics, not simulation state; excluded from the state digest.
_VOLATILE_COLUMNS = {"rounds": {"seconds", "finished_at", "llm_calls", "cache_hits"}, "injected": {"added_at"}}
_NON_STATE_TABLES = {"chats"}
_EVENT_TYPES = {"news", "post", "poll"}  # the event types step() acts on


def _canon(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False, default=str)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _state_digest(conn: sqlite3.Connection) -> str:
    """Digest every simulation-state table, preserving load order and excluding only timing/call statistics."""
    h = hashlib.sha256()
    names = sorted(r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'") if r[0] not in _NON_STATE_TABLES)
    for t in names:
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{t}")') if r[1] not in _VOLATILE_COLUMNS.get(t, ())]
        quoted = ",".join(f'"{c}"' for c in cols)
        # Preserve row order: World.load and event processing use insertion order for several tables.
        # Sorting rows here would make reordered event/membership records hash as the same state.
        rows = [_canon(list(r)) for r in conn.execute(f'SELECT {quoted} FROM "{t}" ORDER BY rowid')]
        h.update(_canon([t, cols, rows]).encode("utf-8"))
    return h.hexdigest()


def _cache_digest(path: Path) -> str | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return _sha(_canon(sorted(conn.execute("SELECT k, v FROM cache").fetchall())))
    except sqlite3.Error as exc:
        raise SnapshotError(f"model reply cache is unreadable: {exc}") from exc
    finally:
        conn.close()


def _llm_identity(cfg: LLMConfig) -> dict:
    """Everything about the model backend that can change what a replayed run says (no keys, URLs or timeouts)."""
    return {"backend": cfg.backend, "model": cfg.model, "context": cfg.context, "extra": cfg.extra}


def _engine_digest() -> str:
    """Bind snapshots to Agora Python source and deterministic runtime versions."""
    root = Path(__file__).resolve().parents[1]
    h = hashlib.sha256()
    h.update(_canon([sys.version_info.major, sys.version_info.minor, np.__version__]).encode("utf-8"))
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        source = path.read_bytes().replace(b"\\r\\n", b"\\n")
        h.update(_canon([relative, hashlib.sha256(source).hexdigest()]).encode("utf-8"))
    return h.hexdigest()


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _open_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)


def _snapshot_state_digest(path: Path) -> str:
    conn = _open_ro(path)
    try:
        return _state_digest(conn)
    finally:
        conn.close()


class Simulation:
    bad_replies = 0       # model replies that stayed unusable after retries (that agent did nothing)
    retried_replies = 0   # replies that needed a second try

    def __init__(self, project: str | Path, llm_override: dict | None = None,
                 governed_input: Mapping | None = None, snapshot_rounds: Iterable[int] = ()):
        """governed_input (optional, M3): {"package": <scenario-input package>, "mapping": <declared mapping>}.

        When given, the population comes from the approved, hash-verified package and the run
        carries an append-once provenance envelope. When None, behaviour is exactly the legacy path.
        """
        self.dir = Path(project)
        # Rounds after whose commit an immutable, verifiable snapshot is written (default none: legacy behaviour).
        rounds = tuple(snapshot_rounds)
        if any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in rounds):
            raise ValueError("snapshot_rounds must contain non-negative integer rounds")
        self.snapshot_rounds = frozenset(rounds)
        self.sc = scenario_mod.load(self.dir / SCENARIO_FILE)
        if any(r >= self.sc.rounds for r in self.snapshot_rounds):
            raise ValueError("snapshot_rounds must be inside the scenario run")
        self.governed: dict | None = None
        self.base_scenario_hash = self.scenario_hash  # scenario.yaml as loaded, before any projection
        if governed_input is not None:
            self.governed = self._verify_governed(governed_input, self.sc, self.dir.name)
            self.sc = self.governed["scenario"]
        cfg = safe_study_llm(self.sc.llm)
        cfg.update(llm_override or {})
        self.llm_cfg = LLMConfig.from_dict(cfg)
        self.llm = make_backend(self.llm_cfg, cache_path=self.dir / CACHE_FILE)
        self.store = Store(self.dir / DB_FILE)
        self.world: World | None = None
        self._rhythm = Rhythm(self.sc.time)
        self._to_reflect: list[Agent] = []
        self.facts = None
        gpath = self.dir / "graph.db"
        if gpath.exists():
            from ..graph import GraphStore
            from ..graph.retrieve import FactIndex
            gs = GraphStore(gpath)
            self.facts = FactIndex.from_graph(gs) or None
            gs.close()
        self._post_clock = 0

    # ---------------------------------------------------------------- setup
    @property
    def scenario_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.sc.raw, sort_keys=True, default=str)
                              .encode()).hexdigest()[:16]

    def _projected_scenario_hash(self, projection: Mapping) -> str:
        """Effective-scenario hash: scenario.yaml hash bound to the projection (rows, mapping, segments).

        scenario.raw does not carry the projected segments, so self.scenario_hash alone cannot see them.
        """
        return hashlib.sha256(json.dumps({"base_scenario_hash": self.base_scenario_hash,
                                          "projection_hash": projection["projection_hash"]},
                                         sort_keys=True).encode()).hexdigest()[:16]

    @staticmethod
    def _receipt_scope(manifest: Mapping, project_id: str) -> dict:
        from ..scenario_inputs import manifest_hash
        try:
            return {"project_id": project_id, "import_id": manifest["import_id"],
                    "binding_id": manifest["binding_id"], "manifest_hash": manifest_hash(manifest),
                    "scenario_hash": manifest["scenario_hash"]}
        except (KeyError, TypeError, ValueError):
            raise GovernedInputError("package manifest lacks the fields an authorization receipt binds") from None

    @staticmethod
    def _check_receipt(receipt, scope: Mapping) -> None:
        """Fail closed unless receipt is a genuine Principal-bound allow for exactly this package and project."""
        from ..principal import IdentityError, verify_simulation_receipt
        try:
            verify_simulation_receipt(receipt, **scope)
        except IdentityError as exc:
            raise GovernedInputError(f"authorization refused: {exc}") from exc

    _BUILDER_FIELDS = ("dataset_id", "schema_id", "schema_version", "file_sha256", "data_role", "run_provenance_reference")

    @staticmethod
    def _input_origin(package: Mapping, manifest: Mapping) -> str:
        """Where the package came from: 'builder' (carries every field build_scenario_input writes) or 'synthetic_demo'
        (hand-built and explicitly declared so). Anything else is refused.

        This is a LABEL, not a security boundary: a caller in the same process can imitate either form. It makes a
        hand-built input visible and un-silent; unforgeable authorization needs a signed receipt from a policy service.
        """
        if (all(k in manifest for k in Simulation._BUILDER_FIELDS) and manifest["data_role"] in {"context", "scenario_input"}
                and manifest["run_provenance_reference"] == f"scenario:{manifest.get('scenario_hash')}"):
            return "builder"
        if package.get("synthetic_demo") is True:
            return "synthetic_demo"
        raise GovernedInputError("input package was not produced by the scenario-input builder and is not declared synthetic_demo")

    @staticmethod
    def _verify_governed(governed_input: Mapping, base, project_id: str) -> dict:
        """Verify the package and derive the scenario here; nothing from the caller is trusted."""
        from ..scenario_inputs import recompute_scenario_hash
        from ..scenario_projection import ProjectionError, project_segments
        if not isinstance(governed_input, Mapping) or set(governed_input) != {"package", "mapping", "receipt"}:
            raise GovernedInputError("governed_input must be exactly {package, mapping, receipt}")
        package, mapping = governed_input["package"], governed_input["mapping"]
        if not isinstance(package, Mapping) or package.get("validated_prediction_enabled") is not False:
            raise GovernedInputError("package must be a scenario-input package with validated_prediction_enabled False")
        manifest = package.get("manifest")
        try:
            recomputed = recompute_scenario_hash(manifest)
        except (KeyError, TypeError, ValueError):
            raise GovernedInputError("package manifest is incomplete") from None
        if not (manifest.get("scenario_hash") == recomputed == package.get("scenario_hash")):
            raise GovernedInputError("package scenario_hash does not match its manifest")
        scope = Simulation._receipt_scope(manifest, project_id)
        Simulation._check_receipt(governed_input["receipt"], scope)  # before any projection/write
        origin = Simulation._input_origin(package, manifest)
        try:
            derived, record = project_segments(package, mapping, base)
        except ProjectionError as exc:
            raise GovernedInputError(f"projection refused: {exc}") from exc
        return {"scenario": derived, "manifest": {**dict(manifest), "projection": record, "input_origin": origin},
                "receipt": governed_input["receipt"], "receipt_scope": scope}

    def _guard_provenance(self) -> None:
        """Governed runs are append-once and never forceable; legacy runs cannot adopt or ignore an envelope."""
        stored = self.store.get_meta("input_provenance")
        if self.governed is None:
            if stored is not None:
                raise GovernedInputError("this run is governed: resume it with its governed input")
            return
        self._check_receipt(self.governed["receipt"], self.governed["receipt_scope"])  # expiry re-checked before any write
        manifest_projection = self.governed["manifest"]["projection"]
        manifest = {**self.governed["manifest"], "base_scenario_hash": self.base_scenario_hash,
                    "projected_scenario_hash": self._projected_scenario_hash(manifest_projection)}
        if self.store.is_initialised():
            if self.store.get_input_provenance().get("provenance_status") != "verified":
                raise GovernedInputError("legacy run has no input provenance and cannot resume as governed")
        try:
            # idempotent when identical; raises (original left byte-identical) when anything differs
            self.store.set_input_provenance(manifest)
        except (RuntimeError, ValueError) as exc:
            raise GovernedInputError(f"governed input does not match this run: {exc}") from exc

    def prepare(self, force: bool = False) -> World:
        """Create the population on first run, or reload it to resume."""
        self._guard_provenance()  # before any population write; --force never reaches this check
        if not self.store.is_initialised():
            (self.dir / "decisions.jsonl").unlink(missing_ok=True)
            w, follows, members = population.build(self.sc)
            # accounts that post into groups by schedule are members of those groups
            for ev in self.sc.events:
                if ev.type != "post" or not is_spaced(ev.platform):
                    continue
                aid = w.by_handle[ev.account].id
                names = [s.name for s in self.sc.spaces_on(ev.platform)]
                for space in (names if (not ev.spaces or "*" in ev.spaces) else ev.spaces):
                    if space not in w.member_of[aid][ev.platform]:
                        w.add_member(aid, ev.platform, space)
                        members.append((aid, ev.platform, space))
            self.store.write_population(w.agents, follows, members)
            self.store.set_meta("scenario_hash", self.scenario_hash)
            self.store.set_meta("seed", self.sc.seed)
            self.store.db.commit()
            self.world = w
        else:
            old = self.store.get_meta("scenario_hash")
            if old != self.scenario_hash and not force:
                raise RuntimeError(
                    "scenario.yaml changed since this run started. Start a fresh project "
                    "(or delete agora.db), or resume anyway with --force.")
            self.world = World.load(self.store)
        self.memory = WorldMemory.load(self.sc, self.world, self.store)
        return self.world

    # ---------------------------------------------------------------- running
    def run(self, rounds: int | None = None, progress: Callable[[dict], None] | None = None,
            force: bool = False, should_stop: Callable[[], bool] | None = None) -> int:
        w = self.world or self.prepare(force=force)
        start = self.store.last_round() + 1
        end = self.sc.rounds if rounds is None else min(self.sc.rounds, start + rounds)
        for r in range(start, end):
            if should_stop and should_stop():
                return r
            t_start = time.time()
            c0, h0 = self.llm.calls, getattr(self.llm, "hits", 0)
            out, active = self.step(r)
            self.memory.add_round(w, r, out.posts, out.conversions, out.events)
            stats = {"active": active, "llm_calls": self.llm.calls - c0,
                     "cache_hits": getattr(self.llm, "hits", 0) - h0,
                     "seconds": round(time.time() - t_start, 2)}
            self.store.commit_round(
                r, sim_time=self.now(r).isoformat(), agents=w.agents, posts=out.posts,
                engagements=out.engagements, follows=out.follows, conversions=out.conversions,
                thoughts=out.thoughts, polls=out.polls, poll_results=out.poll_results,
                events=out.events, stats=stats, unfollows=out.unfollows, mutes=out.mutes,
                choices=out.choices, intentions=out.intentions)
            if r in self.snapshot_rounds:
                self.take_snapshot(r)
            if progress:
                progress({"round": r, "of": self.sc.rounds, "posts": len(out.posts),
                          "conversions": len(out.conversions), "bad_replies": self.bad_replies, "retried": self.retried_replies, **stats})
        return end

    # ---------------------------------------------------------------- snapshots and forks
    def state_digest(self) -> str:
        """Digest the current database state without committing or otherwise mutating it."""
        return _state_digest(self.store.db)

    @property
    def live_llm_calls(self) -> int:
        """Model calls this process made that were not answered from the reply cache."""
        return int(getattr(self.llm, "calls", 0))

    @property
    def replay_is_deterministic(self) -> bool:
        """True only if this run's model replies are reproducible: the mock backend (a pure function of its input) or
        a run whose every reply came from the reply cache. A live model run beyond a snapshot is never claimed so."""
        return self.llm_cfg.backend.lower() == "mock"

    def take_snapshot(self, r: int) -> Path:
        """Write an immutable snapshot of the committed state after round r (only at a committed round boundary).

        The snapshot is a copy of the run database and the model reply cache plus a write-once metadata file whose
        presence marks it complete. An existing snapshot is never overwritten.
        """
        if isinstance(r, bool) or not isinstance(r, int):
            raise SnapshotError("snapshot round must be an integer")
        if r != self.store.last_round():
            raise SnapshotError("snapshots are taken only at the last committed round boundary")
        base = self.dir / SNAPSHOT_DIR / f"round-{r:05d}"
        base.parent.mkdir(exist_ok=True)
        db_path, cache_path, graph_path, meta_path = (
            base.with_name(base.name + e) for e in (".db", ".cache.db", ".graph.db", ".json"))
        if self.store.db.in_transaction:
            raise SnapshotError("snapshots are allowed only after the round transaction has committed")
        digest = _state_digest(self.store.db)
        if meta_path.exists():
            try:
                old = json.loads(meta_path.read_text(encoding="utf-8"))
                body = {k: v for k, v in old.items() if k != "meta_digest"}
                valid = (old.get("meta_digest") == _sha(_canon(body))
                         and old.get("state_digest") == digest
                         and old.get("engine_sha256") == _engine_digest()
                         and _snapshot_state_digest(db_path) == digest
                         and old.get("cache_digest") == _cache_digest(cache_path)
                         and old.get("graph_digest") == (_file_digest(graph_path) if graph_path.exists() else None))
            except (OSError, ValueError, sqlite3.Error, SnapshotError):
                valid = False
            if not valid:
                raise SnapshotError(f"snapshot for round {r} already exists but failed integrity verification")
            return meta_path
        for stale in (db_path, cache_path, graph_path):  # an incomplete earlier attempt (no metadata) is replaced
            if stale.exists():
                os.chmod(stale, 0o644)
                stale.unlink()
        tmp = db_path.with_name(db_path.name + ".tmp")
        tmp.unlink(missing_ok=True)
        dst = sqlite3.connect(str(tmp))
        try:
            self.store.db.backup(dst)
            dst.execute("PRAGMA journal_mode=DELETE")
            dst.commit()
        finally:
            dst.close()
        os.replace(tmp, db_path)
        cache_src = self.dir / CACHE_FILE
        cache_digest = None
        if cache_src.exists():
            ctmp = cache_path.with_name(cache_path.name + ".tmp")
            ctmp.unlink(missing_ok=True)
            src, dstc = sqlite3.connect(str(cache_src)), sqlite3.connect(str(ctmp))
            try:
                src.backup(dstc)
                dstc.execute("PRAGMA journal_mode=DELETE")
                dstc.commit()
            finally:
                src.close()
                dstc.close()
            os.replace(ctmp, cache_path)
            cache_digest = _cache_digest(cache_path)
        graph_src = self.dir / "graph.db"
        graph_digest = None
        if graph_src.exists():
            gtmp = graph_path.with_name(graph_path.name + ".tmp")
            gtmp.unlink(missing_ok=True)
            gsrc, gdst = sqlite3.connect(str(graph_src)), sqlite3.connect(str(gtmp))
            try:
                gsrc.backup(gdst)
                gdst.execute("PRAGMA journal_mode=DELETE")
                gdst.commit()
            finally:
                gsrc.close()
                gdst.close()
            os.replace(gtmp, graph_path)
            graph_digest = _file_digest(graph_path)
        check = _open_ro(db_path)
        try:
            if _state_digest(check) != digest:
                raise SnapshotError("snapshot copy does not match the committed state")
        finally:
            check.close()
        meta = {"schema": SNAPSHOT_SCHEMA, "round": r, "sim_time": self.now(r).isoformat(),
                "scenario_hash": self.base_scenario_hash, "seed": self.sc.seed,
                "state_digest": digest, "cache_digest": cache_digest, "graph_digest": graph_digest,
                "engine_sha256": _engine_digest(),
                "llm_identity_sha256": _sha(_canon(_llm_identity(self.llm_cfg))),
                "governed": self.governed is not None}
        meta["meta_digest"] = _sha(_canon(meta))
        with open(meta_path, "x", encoding="utf-8") as f:  # write-once; its existence marks the snapshot complete
            f.write(_canon(meta))
        for p in (db_path, cache_path, graph_path, meta_path):
            if p.exists():
                os.chmod(p, 0o444)
        return meta_path

    @staticmethod
    def fork_from(source: str | Path, round: int, dest: str | Path, *, events: Iterable[Mapping] = (),
                  llm_override: dict | None = None) -> Path:
        """Create a new project at ``dest`` that resumes from the verified snapshot of ``source`` after ``round``.

        ``events`` replaces the set of user-injected events for later rounds. The source run is only read.
        Refuses (SnapshotError, nothing left at ``dest``) when the snapshot is missing, corrupt, incomplete, from a
        different scenario or model configuration, from a governed run, or when the restored state does not digest
        to the recorded value. Model replies up to the snapshot are replayed from the snapshot's reply cache; replies
        after it are produced again. Forks therefore require the deterministic mock backend; live model backends
        are refused because unseen post-snapshot prompts cannot be guaranteed to hit the copied cache.
        """
        if isinstance(round, bool) or not isinstance(round, int):
            raise SnapshotError("fork round must be an integer")
        src, dest = Path(source), Path(dest)
        base = src / SNAPSHOT_DIR / f"round-{round:05d}"
        db_path, cache_path, graph_path, meta_path = (
            base.with_name(base.name + e) for e in (".db", ".cache.db", ".graph.db", ".json"))
        if not meta_path.exists() or not db_path.exists():
            raise SnapshotError(f"no complete snapshot for round {round}")
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            body = {k: v for k, v in meta.items() if k != "meta_digest"}
            ok = (meta.get("schema") == SNAPSHOT_SCHEMA and meta.get("round") == int(round)
                  and meta.get("meta_digest") == _sha(_canon(body))
                  and all(k in meta for k in ("scenario_hash", "state_digest", "cache_digest", "graph_digest",
                                                "engine_sha256", "sim_time", "llm_identity_sha256", "governed")))
        except (ValueError, TypeError, OSError):
            ok = False
        if not ok:
            raise SnapshotError("snapshot metadata is corrupt, incomplete or of an unknown version")
        if meta["governed"]:
            raise SnapshotError("forking a governed run needs separate approval and is not supported")
        if meta["engine_sha256"] != _engine_digest():
            raise SnapshotError("engine implementation differs from the snapshot; deterministic replay is not established")
        conn = _open_ro(db_path)
        try:
            if _state_digest(conn) != meta["state_digest"]:
                raise SnapshotError("snapshot state does not match its recorded digest")
            row = conn.execute("SELECT round, sim_time FROM rounds ORDER BY round DESC LIMIT 1").fetchone()
            if row is None or row[0] != int(round):
                raise SnapshotError("snapshot database does not contain its declared committed round")
        except sqlite3.Error as exc:
            raise SnapshotError(f"snapshot database is unreadable: {exc}") from exc
        finally:
            conn.close()
        if meta["cache_digest"] is not None:
            if not cache_path.exists() or _cache_digest(cache_path) != meta["cache_digest"]:
                raise SnapshotError("snapshot model reply cache is missing or does not match its recorded digest")
        if meta["graph_digest"] is not None:
            if not graph_path.exists() or _file_digest(graph_path) != meta["graph_digest"]:
                raise SnapshotError("snapshot graph context is missing or does not match its recorded digest")
        sc = scenario_mod.load(src / SCENARIO_FILE)
        if _sha(json.dumps(sc.raw, sort_keys=True, default=str))[:16] != meta["scenario_hash"]:
            raise SnapshotError("scenario.yaml changed since the snapshot was taken")
        if sc.seed != meta["seed"] or (sc.start + timedelta(hours=int(round) * sc.round_hours)).isoformat() != meta["sim_time"]:
            raise SnapshotError("snapshot clock or seed does not match the scenario")
        cfg = safe_study_llm(sc.llm)
        cfg.update(llm_override or {})
        if _sha(_canon(_llm_identity(LLMConfig.from_dict(cfg)))) != meta["llm_identity_sha256"]:
            raise SnapshotError("model backend or configuration differs from the snapshot; replay would not be reproducible")
        # A new event can create unseen prompts. A copied cache cannot make a live backend deterministic
        # on cache misses, so only the deterministic mock backend is eligible for a fork.
        if LLMConfig.from_dict(cfg).backend.lower() != "mock":
            raise SnapshotError("forking with a live or unverified LLM backend cannot guarantee deterministic replay")
        fields = scenario_mod.Event.__dataclass_fields__
        injected = []
        for ev in events:
            ev = dict(ev)
            if set(ev) - set(fields) or not isinstance(ev.get("round"), int) or isinstance(ev.get("round"), bool):
                raise SnapshotError("injected events must use known event fields and an integer round")
            if not int(round) < ev["round"] < sc.rounds:
                raise SnapshotError("injected events must fall after the snapshot round and inside the run")
            if ev.get("type") not in _EVENT_TYPES:
                raise SnapshotError(f"injected event type must be one of {sorted(_EVENT_TYPES)}")
            try:
                scenario_mod.Event(**ev)
            except (TypeError, ValueError) as exc:
                raise SnapshotError(f"invalid injected event: {exc}") from exc
            injected.append(ev)
        injected.sort(key=lambda e: (e["round"], _canon(e)))
        if dest.exists() or dest.is_symlink():
            raise SnapshotError("destination already exists; a fork never overwrites")
        src_resolved, dest_resolved = src.resolve(), dest.resolve()
        if dest_resolved == src_resolved or dest_resolved.is_relative_to(src_resolved):
            raise SnapshotError("fork destination must be outside the source project")
        work = dest.with_name(dest.name + ".forking")
        if work.exists() or work.is_symlink():
            raise SnapshotError("fork staging path already exists; refusing to remove existing data")
        work.mkdir(parents=True, exist_ok=False)
        try:
            shutil.copyfile(src / SCENARIO_FILE, work / SCENARIO_FILE)
            shutil.copyfile(db_path, work / DB_FILE)
            os.chmod(work / DB_FILE, 0o644)
            if meta["cache_digest"] is not None:
                shutil.copyfile(cache_path, work / CACHE_FILE)
                os.chmod(work / CACHE_FILE, 0o644)
            if meta["graph_digest"] is not None:
                shutil.copyfile(graph_path, work / "graph.db")
                if _file_digest(work / "graph.db") != meta["graph_digest"]:
                    raise SnapshotError("restored graph context does not match the snapshot digest")
            restored = sqlite3.connect(str(work / DB_FILE))
            try:
                if _state_digest(restored) != meta["state_digest"]:
                    raise SnapshotError("restored state does not match the snapshot digest")
                with restored:
                    restored.execute("DELETE FROM injected WHERE round > ?", (int(round),))
                    restored.executemany("INSERT INTO injected (round, event) VALUES (?, ?)",
                                         [(e["round"], _canon(e)) for e in injected])
            finally:
                restored.close()
            manifest = {"forked_from": src.name, "round": int(round), "state_digest": meta["state_digest"],
                        "snapshot_meta_digest": meta["meta_digest"], "events_sha256": _sha(_canon(injected))}
            (work / "fork.json").write_text(_canon(manifest), encoding="utf-8")
            os.replace(work, dest)
        except BaseException:
            shutil.rmtree(work, ignore_errors=True)
            raise
        return dest

    def now(self, r: int):
        return self.sc.start + timedelta(hours=r * self.sc.round_hours)

    def step(self, r: int) -> tuple[RoundOutput, int]:
        sc, w = self.sc, self.world
        rng = np.random.default_rng([sc.seed, r, 1])
        out = RoundOutput()
        sc._vote_open_now = self._vote_open(r)
        t0 = r * sc.round_hours
        now = self.now(r)
        self._post_clock = 0

        # 1. scheduled events, plus any the user added while the run was going
        for ev in [e for e in sc.events if e.round == r] + self._injected(r):
            if ev.when and not self._when_ok(ev.when):
                out.events.append(("skipped", {"type": ev.type, "why": ev.when}))
                continue
            if ev.type == "news":
                w.news.append(ev.text)
                out.events.append(("news", {"text": ev.text}))
                if ev.shift:
                    self._shock(ev.shift, rng)
            elif ev.type == "post":
                self._event_post(ev, r, t0, out)
            elif ev.type == "poll":
                self._poll(ev, r, now, rng, out)

        # 1b. experiences of people who converted (e.g. they tried the product)
        self._experiences(r, now, rng, out)

        # 2. who is awake
        rhythm = self._rhythm
        draws = rng.random(len(w.agents))
        active = [a for a in w.agents
                  if not (a.kind == "account" and not a.attrs.get("llm", True))
                  and draws[a.id] < a.activity * rhythm.factor(now.hour, a.attrs.get("active_hours"))]

        # 3. feeds from the snapshot
        index = self._index = FeedIndex(w, t0, feeds=sc.feeds)
        feeds = {a.id: [w.posts[p] for p in index.feed(a, sc.feed_size, rng)] for a in active}
        opens = {a.id: self._open_conversions(a, r) for a in active}

        # 4a. LLM decisions in parallel
        voices = [a for a in active if a.is_llm]
        decisions = self._decide_all(voices, feeds, opens, r, now)

        # 4b + 5. apply in id order
        for a in active:
            feed = feeds[a.id]
            if a.is_llm:
                d = decisions.get(a.id)
                if d is None:
                    continue
                prev = a.stance
                if sc.choice and d.get("prefs"):
                    for o, v in d["prefs"].items():
                        if o in a.prefs:
                            a.prefs[o] = float(np.clip(a.prefs[o] + (1 - a.stubbornness) * (v - a.prefs[o]), -1, 1))
                    a.stance = a.favourite()[1]
                else:
                    a.stance = float(np.clip(a.stance + (1 - a.stubbornness) * (d["stance"] - a.stance), -1, 1))
                if d["thoughts"]:
                    out.thoughts.append((a.id, d["thoughts"]))
                done = [self._apply(a, x, r, t0, opens[a.id], rng, out) for x in d["actions"]]
                self._diag(r, a, stance_before=round(prev, 3), stance_reported=round(d["stance"], 3),
                           stance_after=round(a.stance, 3), thoughts=d["thoughts"],
                           actions=[x.get("type") for x in d["actions"]],
                           # Preserve full action payloads and outcomes for later audit.
                           # "actions" remains the legacy list of action types.
                           action_results=[
                               {"type": x.get("type"), "payload": x, "accepted": res is not None,
                                "result": res}
                               for x, res in zip(d["actions"], done)
                           ],
                           offered=[c.name for c in opens[a.id]],
                           ignored=[x for x, res in zip(d["actions"], done) if res is None])
                self._remember(a, feed, [x for x in done if x], d["thoughts"], now)
            else:
                if sc.choice:
                    a.prefs = opinion.update_prefs(w, a, feed, rng, mu=sc.persuasion)
                    a.stance = a.favourite()[1]
                else:
                    a.stance = opinion.update_stance(w, a, feed, rng, mu=sc.persuasion)
                for x in opinion.crowd_engagement(w, a, feed, rng):
                    self._apply(a, x, r, t0, opens[a.id], rng, out)
                for c in opens[a.id]:
                    logit = c.base + c.stance_weight * a.stance + c.exposure_weight * math.log1p(len(feed))
                    if rng.random() < opinion.sig(logit):
                        self._convert(a, c.name, out)
            a.last_seen = t0
        if sc.choice:
            self._vote(r, active, rng, out)
            out.intentions = self._intentions()
        self._reflect_all(r, now)
        return out, len(active)

    def _diag(self, r: int, a, **info) -> None:
        """One line per decision, kept next to the study: what the person was offered, thought and did.
        Evidence only; the simulation never reads it."""
        try:
            with open(self.dir / "decisions.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"round": r, "agent": a.handle, "segment": a.segment, **info},
                                   default=str, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _shock(self, shift: dict, rng) -> None:
        """A news shock moves everyone a little, more for the open-minded."""
        for a in self.world.agents:
            if a.kind == "account":
                continue
            k = (1 - a.stubbornness) * float(np.clip(rng.normal(1.0, 0.3), 0, 2))
            for o, d in sorted(shift.items()):
                if o == "stance":
                    a.stance = float(np.clip(a.stance + k * d, -1, 1))
                elif o in a.prefs:
                    a.prefs[o] = float(np.clip(a.prefs[o] + k * d, -1, 1))
            if a.prefs:
                a.stance = a.favourite()[1]

    def _vote_open(self, r: int) -> bool:
        ch = self.sc.choice
        return bool(ch) and ch.open_round <= r <= ch.close_round

    def _vote(self, r: int, active: list[Agent], rng, out: RoundOutput) -> None:
        ch = self.sc.choice
        if not self._vote_open(r):
            return
        # voting happens offline: everyone may vote, not only people online this round
        seg_turnout = {g.name: g.turnout for g in self.sc.segments}
        draws = rng.random(len(self.world.agents))
        for a in self.world.agents:
            if a.choice or a.kind == "account" or not a.prefs:
                continue
            fav, u = a.favourite()
            p = opinion.sig(ch.turnout_base + ch.turnout_weight * max(0.0, u) + seg_turnout.get(a.segment, 0.0))
            if draws[a.id] < p:
                self._cast(a, fav, out)

    def _cast(self, a: Agent, option: str, out: RoundOutput) -> bool:
        if a.choice or a.kind == "account" or option not in (self.sc.choice.options if self.sc.choice else []):
            return False
        a.choice = option
        out.choices.append((a.id, option))
        return True

    def _intentions(self) -> list[tuple[str, str, int]]:
        ch = self.sc.choice
        counts: dict[tuple[str, str], int] = {}
        for a in self.world.agents:
            if a.kind == "account" or not a.prefs:
                continue
            fav, u = a.favourite()
            key = (a.segment, fav if u >= ch.undecided_below else "undecided")
            counts[key] = counts.get(key, 0) + 1
        return [(g, o, n) for (g, o), n in sorted(counts.items())]

    def _injected(self, r: int) -> list:
        evs = []
        for (raw,) in self.store.rows("SELECT event FROM injected WHERE round = ? ORDER BY id", (r,)):
            d = json.loads(raw)
            evs.append(scenario_mod.Event(**{k: v for k, v in d.items()
                                             if k in scenario_mod.Event.__dataclass_fields__}))
        return evs

    def _experiences(self, r, now, rng, out: RoundOutput) -> None:
        exps = [c for c in self.sc.conversions if c.experience]
        if not exps:
            return
        when_converted = {}
        if any("after" in c.experience for c in exps):
            for aid, name, cr in self.store.rows("SELECT agent, name, round FROM conversions"):
                when_converted[(aid, name)] = cr
            for aid, name in out.conversions:
                when_converted[(aid, name)] = r
        for c in exps:
            e = c.experience
            hit = []
            for a in self.world.agents:
                if c.name not in a.converted:
                    continue
                if "at_round" in e and r == int(e["at_round"]):
                    hit.append(a)
                elif "after" in e and when_converted.get((a.id, c.name), -10**9) + int(e["after"]) == r:
                    hit.append(a)
            for a in hit:
                shift = rng.normal(float(e.get("stance_mean", 0.0)), float(e.get("stance_sd", 0.2)))
                a.stance = float(np.clip(a.stance + shift, -1, 1))
                if e.get("note") and a.is_llm:
                    feel = ("it went well" if shift > 0.1 else "you did not notice much"
                            if shift > -0.1 else "you were disappointed")
                    a.memory.append(f"{now:%a %d %b}: {e['note']} Honestly, {feel}.")
            if hit:
                out.events.append(("experience", {"conversion": c.name, "agents": len(hit)}))

    # ---------------------------------------------------------------- LLM calls
    def _decide_all(self, voices: list[Agent], feeds, opens, r, now) -> dict[int, dict]:
        if not voices:
            return {}
        sc, w = self.sc, self.world
        bad: list[int] = []
        retried: list[int] = []

        def one(a: Agent):
            facts = []
            if self.facts:
                texts = " ".join(w.posts[p.root if p.kind in ("repost", "forward") else p.id].text
                                 for p in feeds[a.id])
                facts = self.facts.search(f"{sc.topic} {texts} {a.persona}", k=3)
            trending = {p: self._index.trends(p) for p in a.platforms if REGISTRY[p].kind == "feed"}
            recalled = []
            if sc.world_memory and getattr(self, "memory", None) is not None:
                recalled = self.memory.recall(f"{sc.topic} {texts if self.facts else ''} " +
                                              " ".join(p.text for p in feeds[a.id]), r,
                                              {p.id for p in feeds[a.id]} | {p.root for p in feeds[a.id]})
            msgs = llm_agent.decision_messages(w, sc, a, feeds[a.id], now, opens[a.id], facts, trending,
                                               recalled)
            meta = llm_agent.decision_meta(w, sc, a, feeds[a.id], opens[a.id])
            d = None
            for attempt in range(3):             # an unusable reply is asked again with a different seed
                seed = _seed(sc.seed, r, a.id) if attempt == 0 else _seed(sc.seed, r, a.id, attempt)
                if attempt:
                    retried.append(a.id)
                try:
                    raw = self.llm.generate(msgs, max_tokens=350, temperature=0.8, json_mode=True,
                                            seed=seed, meta=meta)
                except LLMError as e:
                    return a.id, None, str(e)
                d = llm_agent.parse_decision(raw, a)
                if d["ok"]:
                    break
            else:
                bad.append(a.id)                 # still unusable: this person does nothing this round
            return a.id, d, None

        with ThreadPoolExecutor(max_workers=max(1, self.llm_cfg.parallel)) as ex:
            results = list(ex.map(one, voices))
        self.bad_replies += len(bad)
        self.retried_replies += len(retried)
        errors = [e for _, _, e in results if e]
        if errors and len(errors) > len(voices) / 2:
            raise LLMError(f"Most model calls failed this round ({len(errors)}/{len(voices)}). "
                           f"First error: {errors[0]}")
        return {aid: d for aid, d, e in results if d is not None}

    def _poll(self, ev, r, now, rng, out: RoundOutput) -> None:
        w = self.world
        voters = [a for a in w.agents if a.segment in ev.voters or a.handle in ev.voters]

        def one(a: Agent):
            if not a.is_llm:
                return a.id, int(rng.random() < opinion.sig(3 * a.stance)), ""
            msgs = llm_agent.poll_messages(w, self.sc, a, ev.question, now)
            try:
                raw = self.llm.generate(msgs, max_tokens=120, temperature=0.7, json_mode=True,
                                        seed=_seed(self.sc.seed, r, a.id, ev.name),
                                        meta={"task": "poll", "stance": a.stance})
            except LLMError:
                return a.id, int(a.stance > 0), "model unavailable; voted by stance"
            d = parse_json(raw)
            vote = str(d.get("vote", "")).strip().lower().startswith("y")
            return a.id, int(vote), str(d.get("reason", ""))[:300]

        crowd = [v for v in voters if not v.is_llm]
        llm_v = [v for v in voters if v.is_llm]
        results = [one(a) for a in crowd]          # uses rng: keep sequential & ordered
        with ThreadPoolExecutor(max_workers=max(1, self.llm_cfg.parallel)) as ex:
            results += list(ex.map(one, llm_v))
        results.sort()
        yes = sum(v for _, v, _ in results)
        no = len(results) - yes
        passed = bool(results) and yes / len(results) >= ev.threshold
        if ev.name in self.sc.fixed_polls:          # outcome already known in real life
            passed = bool(self.sc.fixed_polls[ev.name])
        w.poll_results[ev.name] = passed
        for aid, v, why in results:
            out.polls.append((ev.name, aid, v, why))
            if w.agents[aid].is_llm:
                w.agents[aid].memory.append(f"{now:%a %d %b}: you voted {'YES' if v else 'NO'} on: {ev.question}")
        out.poll_results.append((ev.name, yes, no, passed))
        out.events.append(("poll", {"name": ev.name, "yes": yes, "no": no, "passed": passed}))

    # ---------------------------------------------------------------- actions
    def _new_post(self, a: Agent, r, t0, platform, space, kind, text, stance, parent=None,
                  root=None, out: RoundOutput | None = None) -> Post:
        w = self.world
        option = ""
        if self.sc.choice:
            if kind in ("repost", "forward") and root is not None:
                option, stance = w.posts[root].option, w.posts[root].stance
            elif a.prefs:
                # people talk about the option they feel most strongly about (for or against)
                option = max(sorted(a.prefs), key=lambda k: abs(a.prefs[k]))
                stance = a.prefs[option]
        self._post_clock += 1
        t = t0 + self.sc.round_hours * min(0.99, 0.01 + 0.0005 * self._post_clock)
        pid = w.next_post_id
        p = Post(id=pid, round=r, t=t, platform=platform, space=space, author=a.id,
                 parent=parent, root=pid if root is None else root, kind=kind,
                 text=text.strip()[:1000], stance=round(float(stance), 4), option=option)
        w.add_post(p)
        if out is not None:
            out.posts.append(p)
        return p

    def _event_post(self, ev, r, t0, out) -> None:
        w = self.world
        a = w.by_handle[ev.account]
        targets: list[tuple[str, str]] = []
        if not is_spaced(ev.platform):
            targets = [(ev.platform, "")]
        else:
            names = [s.name for s in self.sc.spaces_on(ev.platform)]
            chosen = names if (not ev.spaces or "*" in ev.spaces) else ev.spaces
            targets = [(ev.platform, s) for s in chosen]
        for plat, space in targets:
            self._new_post(a, r, t0, plat, space, "post", ev.text, a.stance, out=out)
        out.events.append(("post", {"account": a.handle, "platform": ev.platform,
                                    "spaces": [s for _, s in targets]}))

    def _target(self, a: Agent, ref) -> Post | None:
        w = self.world
        try:
            pid = int(str(ref).strip().lstrip("p").lstrip("#"))
        except ValueError:
            return None
        if not 0 <= pid < len(w.posts):
            return None
        p = w.posts[pid]
        if p.platform not in a.platforms:
            return None
        if p.kind == "dm":
            pair = dm_people(p.space)
            if not pair or a.id not in pair:
                return None
        elif p.space and p.space not in w.member_of.get(a.id, {}).get(p.platform, []):
            return None
        return p

    def _apply(self, a: Agent, x: dict, r, t0, opens, rng, out: RoundOutput) -> str | None:
        """Apply one action; returns a short description for memory, or None if invalid."""
        w = self.world
        kind = str(x.get("type", "")).lower().strip()
        text = str(x.get("text", "") or "").strip()
        open_names = {c.name.lower(): c.name for c in opens}
        if kind in open_names:                     # the model wrote the action's own name as the type
            x = {**x, "type": "convert", "name": open_names[kind]}
            kind = "convert"
        if kind == "post":
            where = str(x.get("where") or x.get("platform") or "").strip()
            plat_part, sep, space_part = where.partition(":")
            plat = resolve(plat_part) or plat_part
            where = plat + (sep + space_part.strip() if sep else "")
            options = where_options(w, a)
            if where not in options:
                # "whatsapp" alone is fine when the agent is in exactly one such group
                mine = [o for o in options if o.startswith(plat + ":")]
                if sep or len(mine) != 1:
                    return None
                where = mine[0]
            if not text:
                return None
            plat, _, space = where.partition(":")
            text = text[:REGISTRY[plat].max_len]
            self._new_post(a, r, t0, plat, space, "post", text, a.stance, out=out)
            return f"you posted on {REGISTRY[plat].label}{' in ' + space if space else ''}: \"{text[:120]}\""
        if kind == "convert":
            name = self._match_conversion(str(x.get("name") or x.get("action") or ""), opens)
            if name:
                self._convert(a, name, out)
                return f"you decided to {name.replace('_', ' ')}"
            return None
        if kind in ("dm", "message", "private message", "pm"):
            return self._dm(a, x, r, t0, out)
        if kind in ("vote", "choose"):
            if self._vote_open(r) and self._cast(a, str(x.get("option", "")).strip(), out):
                return f"you voted for {a.choice}"
            return None
        if kind == "search":
            return self._search(a, str(x.get("query", "")))
        if kind in ("mute", "block", "unfollow"):
            ref = str(x.get("target", ""))
            if ref.startswith("@"):
                dst = w.by_handle.get(ref[1:])
            else:
                p = self._target(a, ref)
                dst = w.agents[p.author] if p else None
            if dst is None or dst.id == a.id:
                return None
            if kind == "unfollow":
                plat = resolve(x.get("platform") or "") or next(
                    (q for q in a.platforms if dst.id in w.following[q].get(a.id, ())), None)
                if plat and w.remove_follow(plat, a.id, dst.id):
                    out.unfollows.append((plat, a.id, dst.id))
                    return f"you unfollowed @{dst.handle}"
                return None
            if w.mute(a.id, dst.id):
                out.mutes.append((a.id, dst.id))
                return f"you muted @{dst.handle}"
            return None
        if kind in ("follow", "subscribe", "connect", "add friend"):
            ref = str(x.get("target", ""))
            plat = resolve(x.get("platform") or x.get("where") or "")
            if ref.startswith("@"):
                dst = w.by_handle.get(ref[1:])
            else:
                p = self._target(a, ref)
                dst = w.agents[p.author] if p else None
                plat = plat or (p.platform if p else None)
            if plat is None:     # follow on the first feed app both use
                plat = next((q for q in a.platforms if REGISTRY[q].kind == "feed"
                             and dst is not None and q in dst.platforms), None)
            if (dst is None or plat is None or REGISTRY[plat].kind != "feed"
                    or plat not in a.platforms or plat not in dst.platforms):
                return None
            if w.add_follow(plat, a.id, dst.id):
                out.follows.append((plat, a.id, dst.id))
                return f"you followed @{dst.handle} on {REGISTRY[plat].label}"
            return None

        p = self._target(a, x.get("target"))
        if p is None or p.author == a.id:
            return None
        pkind = REGISTRY[p.platform].kind
        if kind in ("quote", "quote post", "quote tweet"):
            if not text or pkind != "feed" or "quote" not in REGISTRY[p.platform].actions:
                return None
            self._new_post(a, r, t0, p.platform, "", "quote", text[:REGISTRY[p.platform].max_len],
                           a.stance, parent=p.id, out=out)
            return f"you quoted {w.agents[p.author].name}: \"{text[:120]}\""
        if p.kind == "dm" and kind in ("reply", "comment", "answer"):
            return self._dm(a, {"to": f"@{w.agents[p.author].handle}", "text": text,
                                "platform": p.platform}, r, t0, out)
        if kind in ("reply", "comment", "answer"):
            if not text:
                return None
            root = p.root if p.kind == "reply" else p.id
            self._new_post(a, r, t0, p.platform, p.space, "reply", text[:REGISTRY[p.platform].max_len],
                           a.stance, parent=p.id, root=root, out=out)
            return f"you replied to {w.agents[p.author].name}: \"{text[:120]}\""
        if kind in ("like", "upvote", "downvote", "react", "heart"):
            if pkind == "forum":
                kind = "downvote" if kind == "downvote" else "upvote"
            elif kind == "downvote":
                return None
            else:
                kind = "like"
            if w.engage(a.id, p.id, kind):
                out.engagements.append((a.id, p.id, kind))
                return f"you {kind}d a post by {w.agents[p.author].name}"
            return None
        if kind in ("repost", "forward", "share", "retweet", "share to story"):
            src_id = p.root if p.kind in ("repost", "forward") else p.id
            src = w.posts[src_id]
            if pkind == "feed":
                if not w.engage(a.id, src_id, f"repost:{p.platform}"):
                    return None
                out.engagements.append((a.id, src_id, f"repost:{p.platform}"))
                self._new_post(a, r, t0, p.platform, "", "repost", "", src.stance, parent=p.id,
                               root=src_id, out=out)
                return f"you shared {w.agents[src.author].name}'s post on {REGISTRY[p.platform].label}"
            if pkind == "chat":
                groups = [g for g in w.member_of.get(a.id, {}).get(p.platform, []) if g != p.space]
                if not groups:
                    return None
                to = str(x.get("to", ""))
                if to not in groups:
                    to = groups[int(rng.integers(len(groups)))]
                if not w.engage(a.id, src_id, f"forward:{p.platform}:{to}"):
                    return None
                out.engagements.append((a.id, src_id, f"forward:{p.platform}:{to}"))
                self._new_post(a, r, t0, p.platform, to, "forward", "", src.stance,
                               parent=p.id, root=src_id, out=out)
                return f"you forwarded a message to {to}"
        return None

    def _dm(self, a: Agent, x: dict, r, t0, out: RoundOutput) -> str | None:
        w = self.world
        to = str(x.get("to") or x.get("target") or "").strip()
        dst = w.by_handle.get(to.lstrip("@")) if to.startswith("@") or to in w.by_handle else None
        if dst is None and to:
            p = self._target(a, to)
            dst = w.agents[p.author] if p else None
        text = str(x.get("text") or "").strip()
        if dst is None or dst.id == a.id or not text:
            return None
        want = resolve(x.get("platform") or "")
        shared = [q for q in a.platforms if q in dst.platforms and REGISTRY[q].dms]
        plat = want if want in shared else (shared[0] if shared else None)
        if plat is None:
            return None
        self._new_post(a, r, t0, plat, dm_space(a.id, dst.id), "dm", text[:REGISTRY[plat].max_len],
                       a.stance, out=out)
        return f"you messaged {dst.name} privately on {REGISTRY[plat].label}: \"{text[:100]}\""

    def _search(self, a: Agent, query: str) -> str | None:
        """Look something up: the best matching recent posts go straight into memory."""
        from ..graph.retrieve import tokens
        q = set(tokens(query))
        if not q:
            return None
        w = self.world
        scored = []
        for p in w.posts[-2000:]:
            if p.kind not in ("post", "reply", "quote") or not p.text or p.kind == "dm":
                continue
            if p.space and p.space not in w.member_of.get(a.id, {}).get(p.platform, []):
                continue
            hit = len(q & set(tokens(p.text)))
            if hit:
                scored.append((hit, p.t, p.id))
        scored.sort(reverse=True)
        found = [w.posts[pid] for _, _, pid in scored[:3]]
        if not found:
            return f"you searched for \"{query[:60]}\" and found nothing"
        res = "; ".join(f"{w.agents[p.author].name}: \"{p.text[:80]}\"" for p in found)
        return f"you searched for \"{query[:60]}\" and found: {res}"

    @staticmethod
    def _match_conversion(raw: str, opens: list) -> str | None:
        """Which open action did the person mean? The exact name, or one clear match (for example
        "register" when only one register_* is open to them). Anything else is not an action."""
        s = raw.lower().strip().replace(" ", "_").replace("-", "_")
        for c in opens:
            if c.name.lower() == s:
                return c.name
        hits = [c.name for c in opens if len(s) >= 4 and c.name.lower().startswith(s)]
        return hits[0] if len(hits) == 1 else None

    def _convert(self, a: Agent, name: str, out: RoundOutput) -> None:
        if name not in a.converted:
            a.converted.add(name)
            out.conversions.append((a.id, name))

    def _open_conversions(self, a: Agent, r: int) -> list:
        # Named accounts represent brands, committees and organisations, not
        # individual households. They may post and vote, but must not register
        # a household sample or make a household purchase.
        if a.kind == "account":
            return []
        res = []
        for c in self.sc.conversions:
            if not c.open_round <= r <= c.close_round or c.name in a.converted:
                continue
            if c.requires and not a.converted.intersection(c.requires):
                continue
            if c.when and not self._when_ok(c.when):
                continue
            if c.eligible_segments and a.segment not in c.eligible_segments:
                continue
            if c.eligible_spaces:
                mine = {s for spaces in self.world.member_of.get(a.id, {}).values() for s in spaces}
                if not mine.intersection(c.eligible_spaces):
                    continue
            res.append(c)
        return res

    def _when_ok(self, cond: dict) -> bool:
        if "any" in cond:
            return any(self._when_ok(c) for c in cond["any"])
        name = cond.get("poll")
        if name not in self.world.poll_results:
            return False
        want = str(cond.get("result", "yes")).lower() in ("yes", "true", "pass", "passed")
        return self.world.poll_results[name] == want

    def _remember(self, a: Agent, feed: list[Post], done: list[str], thoughts: str, now) -> None:
        stamp = f"{now:%a %I%p}".replace(" 0", " ")
        w = self.world
        for p in feed[:2]:
            src = w.posts[p.root] if p.kind in ("repost", "forward") else p
            line = f"saw {w.agents[src.author].name}: \"{src.text[:90]}\""
            if src.text and not any(m.endswith(line) for m in a.memory):
                a.memory.append(f"{stamp}: {line}")
        for d in done:
            a.memory.append(f"{stamp}: {d}")
        if thoughts:
            a.memory.append(f"{stamp}: you thought: {thoughts[:120]}")
        keep = self.sc.memory_size * 2
        if len(a.memory) > keep:
            if self.sc.reflection:
                self._to_reflect.append(a)       # summarised after this round's decisions
            else:
                del a.memory[: len(a.memory) - keep]

    def _reflect_all(self, r: int, now) -> None:
        """Compress older memories into a short 'looking back' note, in the agent's own words."""
        todo = list({a.id: a for a in self._to_reflect}.values())
        self._to_reflect = []
        if not todo:
            return
        keep = self.sc.memory_size

        def one(a: Agent):
            old = a.memory[: len(a.memory) - keep]
            prev = old[0] if old and old[0].startswith("Looking back:") else ""
            items = [m for m in old if not m.startswith("Looking back:")]
            msgs = [{"role": "system", "content": f"You are {a.name}. {a.persona}"},
                    {"role": "user", "content": (f"{prev}\nThese are things you did and saw recently:\n"
                     + "\n".join(f"- {m}" for m in items)
                     + f"\n\nIn 2-3 sentences, in the first person, sum up what matters to you about "
                       f"{self.sc.topic}: who you trust, what you decided, what you still doubt.")}]
            default = (prev.replace("Looking back:", "").strip() + " " + " ".join(i.split(": ", 1)[-1] for i in items[-3:]))[:400]
            try:
                txt = self.llm.generate(msgs, max_tokens=160, temperature=0.4, seed=_seed(self.sc.seed, r, a.id, "reflect"),
                                        meta={"default_text": default}).strip()
            except LLMError:
                txt = default
            return a, "Looking back: " + " ".join(txt.split())[:500]

        with ThreadPoolExecutor(max_workers=max(1, self.llm_cfg.parallel)) as ex:
            results = list(ex.map(one, sorted(todo, key=lambda x: x.id)))
        for a, note in results:
            a.memory = [note] + a.memory[len(a.memory) - keep:]

    def close(self) -> None:
        self.store.close()
        if hasattr(self.llm, "close"):
            self.llm.close()
