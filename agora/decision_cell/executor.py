"""Run FORK_FROM_EVENT, FORK_FROM_EARLIER, CONTINUE or RERUN_FROM_START and record what the result rests on, as one call (DECISION_CELL_SPEC 3, 3A, 5).

``execute_event_fork`` forks the study twice from the verified snapshot at the event round (with the item's
statements added, and without them). ``execute_earlier_fork`` does the same from a snapshot before the event round, with the
statements added in the round after that earlier one. ``execute_continuation`` forks it once from the verified snapshot at the
last committed round, with the statements added at the next round. ``execute_rerun`` runs the study again from
the start in a new project, with the statements added in the round after the event round the request names.
All four ask the gate immediately before acting,
run on the mock backend, record the result with ``record_run_result`` and only then make the output visible.
``read_event_fork``, ``read_earlier_fork``, ``read_continuation`` and ``read_rerun`` return a recorded result together with its stamps.

Rules chosen here:

* Only FORK_FROM_EVENT, FORK_FROM_EARLIER, CONTINUE and RERUN_FROM_START, each through its own call. Every other option is refused before the gate.
* FORK_FROM_EARLIER places the item EARLIER than it happened: both branches start from the snapshot at
  ``request.from_round`` and the with-event branch gets the statements in the round after it. This is a
  what-if about timing ("what if this had reached people sooner"), and the manifest says so
  (``event_placement``). Adding them after the event round instead would, on a deterministic backend, only
  repeat FORK_FROM_EVENT. Nothing models a different response; only the item's arrival moves. The event
  round may not be later than the last committed round, and a source holding added events after the earlier
  round is refused.
* CONTINUE never writes the source: "keep the agents' state" means the same state, restored into a new project
  from the snapshot at the last committed round. A request that names an event round is refused, because a
  continuation always adds at the next round and an unused value would still enter the action fingerprint.
  It runs one branch with no baseline, so it shows no difference the item made and claims none.
* What is added is not chosen by the caller: every listed statement of the item becomes one news event, in
  its recorded wording, in the round after the start round (the event round, the chosen earlier round, or for CONTINUE the
  last committed round), with no opinion shift. The gate has checked the
  wording against the recorded list and hashed the labels into the action fingerprint, so a second approval
  covers what runs. Leaving a statement out is a CHANGE_INPUTS matter and is not built.
* The cost (remaining rounds times agents, per branch) and the snapshot probe are worked out here from the
  source project, not taken from the caller. The probe is a real ``fork_from`` into a throwaway directory.
* The study's current round must equal the source's last committed round. A source holding added events
  after the event round is refused, because a fork would silently drop them from both branches.
* RERUN_FROM_START needs no snapshot. It takes from the source only the scenario (whose hash must equal the one
  the source recorded when it was first prepared), the seed in it, and the knowledge graph file if there is one,
  as it is now (nothing records what it was at the start, so its digest goes in the manifest). No agent state,
  reply cache or round is copied. It is refused for a governed source, and for a source that holds any added
  event, which the rerun would silently drop. ``request.event_round`` is the round the person picked for the
  event, with the same meaning as for a fork: the statements are added in the round after it. It may not be later
  than the last committed round, and the rerun cannot place the item in the first round.
* A fork's two branches are ONE result: the comparison. It rests on the item, so a retraction stamps it. The
  without-event branch is not recorded or offered as a result of its own: a stamp on it alone would be false.
* Output is built in a staging directory. It reaches its final place only after every branch finished, the
  result was recorded and its stamps were read. On any failure the staging directory this call created is
  removed. If recording succeeded and a later step failed, the record stays, no output is released, and that
  result id cannot be used again.
* The kill switch is polled before the gate, before every round and before recording. Anything other than
  exactly False stops the run.

Limits. Library only: no service, command or screen calls it. ``source``, ``out_dir``, ``study``, the kill
switch, the statements' sources and judgments and the other basis ids are trusted service-layer inputs; nothing
here proves that ``source`` is the project of that study. Mock backend only, so the output is a rehearsal of
the machinery and not a forecast. A process that dies mid-run leaves the staging directory, which blocks that
result id until an operator removes it. Anyone who can write ``out_dir`` can change the files afterwards;
the read calls detect a changed manifest or branch database, not a changed reply cache or other file.
Reads perform no caller permission check.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from agora.audit_anchor import AnchoredAuditChain
from agora.decision_cell.evidence import StatementEvidence, request_labelled_option
from agora.decision_cell.options import (
    DecisionCellError,
    Escalation,
    GateResult,
    InputGrant,
    Option,
    OptionRequest,
    StudyState,
)
from agora.decision_cell.project_store import _canonical, _identifier, _writer
from agora.decision_cell.run_results import (
    RunResultBasis,
    load_run_result,
    record_run_result,
    run_result_stamps,
)
from agora.principal import Principal

RESULT_FILE = "result.json"
SCHEMA = "agora.decision-cell.event-fork/1"
CONTINUATION_SCHEMA = "agora.decision-cell.continuation/1"
RERUN_SCHEMA = "agora.decision-cell.rerun/1"
EARLIER_FORK_SCHEMA = "agora.decision-cell.earlier-fork/1"
WITH_EVENT = "with-event"
WITHOUT_EVENT = "without-event"
CONTINUED = "continued"
RERUN = "rerun"
# schema -> the branch directories a result of that kind holds. Code, not the manifest, says what is verified.
_KINDS = {SCHEMA: (WITH_EVENT, WITHOUT_EVENT), EARLIER_FORK_SCHEMA: (WITH_EVENT, WITHOUT_EVENT),
          CONTINUATION_SCHEMA: (CONTINUED,), RERUN_SCHEMA: (RERUN,)}
_STAGING_SUFFIX = ".executing"


class ExecutionError(DecisionCellError):
    """A refused or failed execution. ``code`` is stable and safe to log. ``gate`` is set if the gate blocked."""

    def __init__(self, code: str, detail: str = "", gate: GateResult | None = None) -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.gate = gate


@dataclass(frozen=True)
class ExecutionResult:
    path: Path                              # holds result.json and the branch projects
    manifest: dict                          # the parsed result.json; its SHA-256 is basis.result_hash
    basis: RunResultBasis
    stamps: tuple[tuple[str, str], ...]     # as read now; whoever shows the result must show these


EventForkResult = ExecutionResult           # the name the first executor shipped with


def _result_dir(out_dir: Path, tenant_id: str, project_id: str, study_id: str, result_id: str) -> Path:
    # Hashed, so no id can name a path, and ids differing only in case do not share a directory on Windows.
    key = _canonical([tenant_id, project_id, study_id, result_id])
    return out_dir / ("result-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:32])


def _stopped(kill_switch_on: Callable[[], bool]) -> bool:
    try:
        return kill_switch_on() is not False
    except Exception:
        return True


def _read_only(database: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)


def _source_facts(source: Path) -> tuple[int, int, int, int]:
    """(rounds in the scenario, last committed round, agents, latest round with an added event or -1)."""
    from agora import scenario as scenario_mod
    from agora.sim.engine import DB_FILE, SCENARIO_FILE

    try:
        rounds = scenario_mod.load(source / SCENARIO_FILE).rounds
        conn = _read_only(source / DB_FILE)
        try:
            last, agents, added = (conn.execute(query).fetchone()[0] for query in (
                "SELECT MAX(round) FROM rounds", "SELECT COUNT(*) FROM agents",
                "SELECT MAX(round) FROM injected"))
        finally:
            conn.close()
    except Exception as exc:
        raise ExecutionError("SOURCE_UNREADABLE", "the source study could not be read") from exc
    if last is None or not agents:
        raise ExecutionError("SOURCE_NOT_RUN", "the source study has no committed round")
    return rounds, int(last), int(agents), -1 if added is None else int(added)


def fork_branch_cost(source: str | Path, event_round: int) -> int:
    """Agent-rounds one branch forked after ``event_round`` will run (for an earlier fork, pass its from-round).

    The gate prices a fork as two of these; use it to show the cost.
    """
    rounds, _, agents, _ = _source_facts(Path(source))
    return max(rounds - 1 - event_round, 0) * agents


def rerun_cost(source: str | Path) -> int:
    """Agent-rounds a rerun from the start will run: every round of the scenario. Use it to show the cost."""
    rounds, _, agents, _ = _source_facts(Path(source))
    return rounds * agents


def _check_rerun_source(source: Path) -> str:
    """Refuse a source whose run a fresh project built from its scenario would not stand for.

    Returns the scenario hash the source started with; the rerun project must run exactly that.
    """
    from agora import scenario as scenario_mod
    from agora.llm import LLMConfig
    from agora.sim.engine import DB_FILE, SCENARIO_FILE, safe_study_llm

    try:
        sc = scenario_mod.load(source / SCENARIO_FILE)
        raw, backend = sc.raw, LLMConfig.from_dict(safe_study_llm(sc.llm)).backend.lower()
        scenario_hash = hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest()[:16]
        conn = _read_only(source / DB_FILE)
        try:
            meta = dict(conn.execute(
                "SELECT key, value FROM meta WHERE key IN ('scenario_hash', 'input_provenance')").fetchall())
        finally:
            conn.close()
        started_with = json.loads(meta["scenario_hash"]) if "scenario_hash" in meta else None
    except Exception as exc:
        raise ExecutionError("SOURCE_UNREADABLE", "the source study could not be read") from exc
    if "input_provenance" in meta:
        raise ExecutionError("SOURCE_GOVERNED", "rerunning a governed study needs separate approval")
    if started_with != scenario_hash:
        raise ExecutionError("SOURCE_SCENARIO_CHANGED", "the scenario is not the one the source study started with")
    if backend != "mock":  # refused here so that no gate entry or population is made for it
        raise ExecutionError("BACKEND_NOT_DETERMINISTIC", "only the mock backend may run a rerun")
    return scenario_hash


def _new_rerun_project(source: Path, project: Path, added: list[dict]) -> dict:
    """A fresh project at ``project``: the source's scenario and graph, its own population, plus ``added``."""
    from agora.sim.engine import DB_FILE, SCENARIO_FILE, Simulation, _canon as canon, _file_digest

    project.mkdir()
    shutil.copyfile(source / SCENARIO_FILE, project / SCENARIO_FILE)
    graph_digest = None
    if (source / "graph.db").exists():
        origin, copy = _read_only(source / "graph.db"), sqlite3.connect(str(project / "graph.db"))
        try:
            origin.backup(copy)  # not a file copy: that would miss changes still in the write-ahead log
        finally:
            copy.close()
            origin.close()
        graph_digest = _file_digest(project / "graph.db")
    sim = Simulation(project)
    try:
        sim.prepare()
        with sim.store.db:
            sim.store.db.executemany("INSERT INTO injected (round, event) VALUES (?, ?)",
                                     [(e["round"], canon(e)) for e in added])
        scenario_hash = sim.scenario_hash
    finally:
        sim.close()
    return {"scenario_hash": scenario_hash, "graph_sha256": graph_digest,
            "events_sha256": hashlib.sha256(canon(added).encode("utf-8")).hexdigest()}


def _run_branch(project: Path, kill_switch_on: Callable[[], bool]) -> str:
    """Run one forked project to its last round and return the digest of its final state."""
    from agora.sim.engine import Simulation

    sim = Simulation(project)
    try:
        if not sim.replay_is_deterministic:
            raise ExecutionError("BACKEND_NOT_DETERMINISTIC", "only the mock backend may run a fork")
        sim.prepare()
        end = sim.run(should_stop=lambda: _stopped(kill_switch_on))
        if end != sim.sc.rounds or sim.store.last_round() != sim.sc.rounds - 1:
            raise ExecutionError("STOPPED_BY_KILL_SWITCH", "the run was stopped; nothing is released")
        return sim.state_digest()
    finally:
        sim.close()


def execute_event_fork(
    principal: Principal | None, request: OptionRequest, *, statements: tuple[StatementEvidence, ...],
    tenant_id: str, project_id: str, study: StudyState, result_id: str, source: str | Path,
    out_dir: str | Path, kill_switch_on: Callable[[], bool], audit: AnchoredAuditChain,
    escalation: Escalation = Escalation(), grants: tuple[InputGrant, ...] = (),
    parent_result_ids: tuple[str, ...] = (), other_item_ids: tuple[str, ...] = (),
    now: datetime | None = None,
) -> ExecutionResult:
    """Gate, fork, run and record one FORK_FROM_EVENT. Raises; no output is released unless it returns.

    A blocked choice raises ``ExecutionError("GATE_BLOCKED")`` with the gate's result; the gate has audited
    it. The item is ``request.event_id``. ``parent_result_ids`` must name any recorded result that ``source``
    was itself produced from, or a retraction behind it is not carried into this one.
    """
    return _execute(Option.FORK_FROM_EVENT, SCHEMA, principal, request, statements=statements,
                    tenant_id=tenant_id, project_id=project_id, study=study, result_id=result_id, source=source,
                    out_dir=out_dir, kill_switch_on=kill_switch_on, audit=audit, escalation=escalation,
                    grants=grants, parent_result_ids=parent_result_ids, other_item_ids=other_item_ids, now=now)


def execute_earlier_fork(
    principal: Principal | None, request: OptionRequest, *, statements: tuple[StatementEvidence, ...],
    tenant_id: str, project_id: str, study: StudyState, result_id: str, source: str | Path,
    out_dir: str | Path, kill_switch_on: Callable[[], bool], audit: AnchoredAuditChain,
    escalation: Escalation = Escalation(), grants: tuple[InputGrant, ...] = (),
    parent_result_ids: tuple[str, ...] = (), other_item_ids: tuple[str, ...] = (),
    now: datetime | None = None,
) -> ExecutionResult:
    """Gate, fork, run and record one FORK_FROM_EARLIER. Same refusals and release rule as ``execute_event_fork``.

    ``request.from_round`` and ``request.event_round`` are both required, the first earlier than the second.
    Both branches start from the snapshot at ``from_round``; the with-event branch gets the statements in the
    round after it, so the item arrives earlier than it did. Use ``fork_branch_cost(source, from_round)``
    for the cost of one branch.
    """
    return _execute(Option.FORK_FROM_EARLIER, EARLIER_FORK_SCHEMA, principal, request, statements=statements,
                    tenant_id=tenant_id, project_id=project_id, study=study, result_id=result_id, source=source,
                    out_dir=out_dir, kill_switch_on=kill_switch_on, audit=audit, escalation=escalation,
                    grants=grants, parent_result_ids=parent_result_ids, other_item_ids=other_item_ids, now=now)


def execute_rerun(
    principal: Principal | None, request: OptionRequest, *, statements: tuple[StatementEvidence, ...],
    tenant_id: str, project_id: str, study: StudyState, result_id: str, source: str | Path,
    out_dir: str | Path, kill_switch_on: Callable[[], bool], audit: AnchoredAuditChain,
    escalation: Escalation = Escalation(), grants: tuple[InputGrant, ...] = (),
    parent_result_ids: tuple[str, ...] = (), other_item_ids: tuple[str, ...] = (),
    now: datetime | None = None,
) -> ExecutionResult:
    """Gate, run and record one RERUN_FROM_START. Same release rule as ``execute_event_fork``.

    ``request.event_round`` is required: the statements are added in the round after it, in a new project that
    starts at round 0. No snapshot is needed; the source is only read.
    """
    return _execute(Option.RERUN_FROM_START, RERUN_SCHEMA, principal, request, statements=statements,
                    tenant_id=tenant_id, project_id=project_id, study=study, result_id=result_id, source=source,
                    out_dir=out_dir, kill_switch_on=kill_switch_on, audit=audit, escalation=escalation,
                    grants=grants, parent_result_ids=parent_result_ids, other_item_ids=other_item_ids, now=now)


def execute_continuation(
    principal: Principal | None, request: OptionRequest, *, statements: tuple[StatementEvidence, ...],
    tenant_id: str, project_id: str, study: StudyState, result_id: str, source: str | Path,
    out_dir: str | Path, kill_switch_on: Callable[[], bool], audit: AnchoredAuditChain,
    escalation: Escalation = Escalation(), grants: tuple[InputGrant, ...] = (),
    parent_result_ids: tuple[str, ...] = (), other_item_ids: tuple[str, ...] = (),
    now: datetime | None = None,
) -> ExecutionResult:
    """Gate, run and record one CONTINUE. Same refusals and release rule as ``execute_event_fork``.

    The statements are added in the round after the last committed one, in a new project; the source is
    only read. ``request.event_round`` must be None.
    """
    return _execute(Option.CONTINUE, CONTINUATION_SCHEMA, principal, request, statements=statements,
                    tenant_id=tenant_id, project_id=project_id, study=study, result_id=result_id, source=source,
                    out_dir=out_dir, kill_switch_on=kill_switch_on, audit=audit, escalation=escalation,
                    grants=grants, parent_result_ids=parent_result_ids, other_item_ids=other_item_ids, now=now)


def _execute(option, schema, principal, request, *, statements, tenant_id, project_id, study, result_id, source,
             out_dir, kill_switch_on, audit, escalation, grants, parent_result_ids, other_item_ids,
             now) -> ExecutionResult:
    from agora.sim.engine import Simulation

    writer = _writer(audit)
    if not isinstance(request, OptionRequest) or request.option is not option:
        raise ExecutionError("OPTION_NOT_EXECUTABLE", f"this call executes only {option.value}")
    if not isinstance(study, StudyState) or not callable(kill_switch_on):
        raise ExecutionError("INPUT_INVALID", "a StudyState and a kill-switch probe are required")
    if not all(_identifier(v) for v in (tenant_id, project_id, study.study_id, result_id)):
        raise ExecutionError("INPUT_INVALID", "ids must be exact non-empty strings")
    if not isinstance(parent_result_ids, tuple) or not isinstance(other_item_ids, tuple):
        raise ExecutionError("INPUT_INVALID", "give parent results and other items as tuples")
    forking, rerunning = option is Option.FORK_FROM_EVENT, option is Option.RERUN_FROM_START
    earlier = option is Option.FORK_FROM_EARLIER
    placed = forking or earlier or rerunning  # the options for which the person names the event round
    if placed and (type(request.event_round) is not int or request.event_round < 0):
        raise ExecutionError("INPUT_INVALID", "a fork or a rerun needs the event round")
    if earlier and (type(request.from_round) is not int or request.from_round < 0):
        raise ExecutionError("INPUT_INVALID", "an earlier fork needs the round to fork from")
    if not placed and request.event_round is not None:
        raise ExecutionError("INPUT_INVALID", "a continuation adds at the next round; give no event round")
    source, out_dir = Path(source), Path(out_dir)
    key = dict(tenant_id=tenant_id, project_id=project_id, study_id=study.study_id)

    rounds, last_round, agents, last_added = _source_facts(source)
    if study.current_round != last_round:
        raise ExecutionError("STUDY_ROUND_MISMATCH", "the study state does not match the source's last round")
    # The statements are added in the round after this one. A fork or continuation also starts from its snapshot.
    start_round = (request.from_round if earlier else request.event_round) if placed else last_round
    if (rerunning or earlier) and request.event_round > last_round:
        raise ExecutionError("EVENT_ROUND_NOT_REACHED", "the event round is later than the study has reached")
    if start_round + 1 >= rounds:
        raise ExecutionError("NO_ROUND_LEFT", "there is no round left to add the item to")
    if rerunning:
        if last_added >= 0:
            raise ExecutionError("SOURCE_HAS_ADDED_EVENTS", "a rerun would drop events added to the source")
        started_with = _check_rerun_source(source)
    elif last_added > start_round:
        raise ExecutionError("SOURCE_HAS_LATER_EVENTS", "a fork would drop events added after its start round")
    rounds_to_run = rounds if rerunning else max(rounds - 1 - start_round, 0)
    if out_dir.resolve().is_relative_to(source.resolve()):
        raise ExecutionError("OUTPUT_INSIDE_SOURCE", "the source study is never written")
    # Checked before the gate so that a run is not spent on a record that must be refused.
    for parent_id in parent_result_ids:
        if load_run_result(result_id=parent_id, audit=writer, **key) is None:
            raise ExecutionError("PARENT_NOT_RECORDED", "record the parent result first")
    final = _result_dir(out_dir, tenant_id, project_id, study.study_id, result_id)
    if load_run_result(result_id=result_id, audit=writer, **key) is not None:
        raise ExecutionError("RESULT_ALREADY_RECORDED", "a result id is used once")
    if _stopped(kill_switch_on):
        raise ExecutionError("STOPPED_BY_KILL_SWITCH", "the kill switch is on or cannot be read")

    staging = final.with_name(final.name + _STAGING_SUFFIX)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        staging.mkdir()  # exclusive: one execution per result id at a time
    except FileExistsError as exc:
        raise ExecutionError("OUTPUT_EXISTS", "an execution of this result id is in progress or was left") from exc
    try:
        if final.exists() or final.is_symlink():
            raise ExecutionError("OUTPUT_EXISTS", "output for this result id already exists")

        def snapshot_verifies(_study_id: str, snapshot_round: int) -> bool:
            with tempfile.TemporaryDirectory() as scratch:
                Simulation.fork_from(source, snapshot_round, Path(scratch) / "probe")
            return True

        decided = request_labelled_option(
            principal, request, statements=statements, tenant_id=tenant_id, project_id=project_id,
            audit=writer, study=study, branch_cost_units=rounds_to_run * agents,
            snapshot_verifies=snapshot_verifies, escalation=escalation, grants=grants, now=now)
        gate, evidence = decided.gate, decided.evidence
        if not gate.executable:
            raise ExecutionError("GATE_BLOCKED", ",".join(gate.failures), gate)

        added = [{"type": "news", "text": s.statement_text, "round": start_round + 1}
                 for s in sorted(statements, key=lambda s: s.statement_id)]
        branches = {}
        for name in _KINDS[schema]:
            project = staging / name
            if rerunning:
                made = _new_rerun_project(source, project, added)
                if made["scenario_hash"] != started_with:  # judged on the copy that is about to run
                    raise ExecutionError("SOURCE_CHANGED", "the scenario changed while the rerun was being built")
                branches[name] = {"final_state_digest": _run_branch(project, kill_switch_on), **made}
                continue
            Simulation.fork_from(source, start_round, project, events=[] if name == WITHOUT_EVENT else added)
            forked = json.loads((project / "fork.json").read_text(encoding="utf-8"))
            branches[name] = {"final_state_digest": _run_branch(project, kill_switch_on),
                              "snapshot_meta_digest": forked["snapshot_meta_digest"],
                              "events_sha256": forked["events_sha256"]}
        if not rerunning and len({branch["snapshot_meta_digest"] for branch in branches.values()}) != 1:
            raise ExecutionError("SOURCE_CHANGED", "the two branches did not start from the same snapshot")

        manifest = {
            "schema": schema, **key, "result_id": result_id, "item_id": request.event_id,
            "gate_event_id": gate.audit_event_id, "action_fingerprint": gate.action_fingerprint,
            "evidence_hash": evidence.evidence_hash,
            # Labels as the gate judged them: shown beside the result, not updated afterwards.
            "statement_labels": {i: s.label.value for i, s in evidence.statements},
            "primary_source_exception_ids": list(evidence.primary_source_exception_ids),
            **({"event_round": request.event_round, "forked_from_round": start_round,
                "event_placement": "hypothetical-earlier"} if earlier else
               {("continued_from_round" if option is Option.CONTINUE else "event_round"): start_round}),
            "added_in_round": start_round + 1, "cost_units": gate.cost_units,
            "llm_backend": "mock", "validated_prediction_enabled": False, "branches": branches,
        }
        raw = _canonical(manifest).encode("utf-8")
        (staging / RESULT_FILE).write_bytes(raw)
        if _stopped(kill_switch_on):
            raise ExecutionError("STOPPED_BY_KILL_SWITCH", "the kill switch came on; nothing is released")
        basis = record_run_result(
            result_id=result_id, gate_event_id=gate.audit_event_id, audit=writer,
            result_hash=hashlib.sha256(raw).hexdigest(), other_item_ids=other_item_ids,
            parent_result_ids=parent_result_ids, **key)
        stamps = run_result_stamps(result_id=result_id, audit=writer, **key)
        staging.rename(final)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return ExecutionResult(final, json.loads(raw), basis, stamps)


def read_event_fork(*, tenant_id: str, project_id: str, study_id: str, result_id: str,
                    out_dir: str | Path, audit: AnchoredAuditChain) -> ExecutionResult:
    """A recorded comparison with its current stamps. A trusted service-side read.

    Refuses an unrecorded result, one of another kind, and one whose manifest or branch databases differ from
    what was recorded.
    """
    return _read(SCHEMA, tenant_id=tenant_id, project_id=project_id, study_id=study_id,
                 result_id=result_id, out_dir=out_dir, audit=audit)


def read_earlier_fork(*, tenant_id: str, project_id: str, study_id: str, result_id: str,
                      out_dir: str | Path, audit: AnchoredAuditChain) -> ExecutionResult:
    """A recorded earlier fork with its current stamps; the same refusals as ``read_event_fork``."""
    return _read(EARLIER_FORK_SCHEMA, tenant_id=tenant_id, project_id=project_id, study_id=study_id,
                 result_id=result_id, out_dir=out_dir, audit=audit)


def read_continuation(*, tenant_id: str, project_id: str, study_id: str, result_id: str,
                      out_dir: str | Path, audit: AnchoredAuditChain) -> ExecutionResult:
    """A recorded continuation with its current stamps; the same refusals as ``read_event_fork``."""
    return _read(CONTINUATION_SCHEMA, tenant_id=tenant_id, project_id=project_id, study_id=study_id,
                 result_id=result_id, out_dir=out_dir, audit=audit)


def read_rerun(*, tenant_id: str, project_id: str, study_id: str, result_id: str,
               out_dir: str | Path, audit: AnchoredAuditChain) -> ExecutionResult:
    """A recorded rerun with its current stamps; the same refusals as ``read_event_fork``."""
    return _read(RERUN_SCHEMA, tenant_id=tenant_id, project_id=project_id, study_id=study_id,
                 result_id=result_id, out_dir=out_dir, audit=audit)


def _read(schema, *, tenant_id, project_id, study_id, result_id, out_dir, audit) -> ExecutionResult:
    from agora.sim.engine import DB_FILE, _state_digest

    key = dict(tenant_id=tenant_id, project_id=project_id, study_id=study_id)
    basis = load_run_result(result_id=result_id, audit=audit, **key)
    if basis is None:
        raise ExecutionError("RESULT_NOT_RECORDED", "an unrecorded result is not shown")
    path = _result_dir(Path(out_dir), tenant_id, project_id, study_id, result_id)
    try:
        raw = (path / RESULT_FILE).read_bytes()
    except OSError as exc:
        raise ExecutionError("OUTPUT_MISSING", "the recorded result has no readable output") from exc
    if hashlib.sha256(raw).hexdigest() != basis.result_hash:
        raise ExecutionError("OUTPUT_CHANGED", "the manifest is not the one recorded")
    try:
        manifest = json.loads(raw)
        if manifest["schema"] != schema:
            raise ExecutionError("WRONG_RESULT_KIND", "this result was not made by the call that pairs with this read")
        for name in _KINDS[schema]:
            conn = _read_only(path / name / DB_FILE)  # not "immutable": that would skip the write-ahead log
            try:
                digest = _state_digest(conn)
            finally:
                conn.close()
            if digest != manifest["branches"][name]["final_state_digest"]:
                raise ExecutionError("OUTPUT_CHANGED", "a branch database is not the one recorded")
    except ExecutionError:
        raise
    except Exception as exc:
        raise ExecutionError("OUTPUT_CHANGED", "the recorded output could not be verified") from exc
    return ExecutionResult(path, manifest, basis,
                           run_result_stamps(result_id=result_id, audit=audit, **key))


__all__ = ["ExecutionError", "ExecutionResult", "EventForkResult", "execute_continuation", "execute_earlier_fork",
           "execute_event_fork", "execute_rerun", "fork_branch_cost", "read_continuation", "read_earlier_fork",
           "read_event_fork", "read_rerun", "rerun_cost"]
