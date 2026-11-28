"""Run FORK_FROM_EVENT and record what it rests on, as one call (DECISION_CELL_SPEC sections 3, 3A and 5).

``execute_event_fork`` asks the gate immediately before acting, forks the study twice from the verified
snapshot at the event round (with the item's statements added, and without them), runs both branches on the
mock backend, records the comparison with ``record_run_result`` and only then makes the output visible.
``read_event_fork`` returns a recorded comparison together with its stamps.

Rules chosen here:

* Only FORK_FROM_EVENT. Every other option is refused before the gate.
* What is added is not chosen by the caller: every listed statement of the item becomes one news event, in
  its recorded wording, in the round after the event round, with no opinion shift. The gate has checked the
  wording against the recorded list and hashed the labels into the action fingerprint, so a second approval
  covers what runs. Leaving a statement out is a CHANGE_INPUTS matter and is not built.
* The cost (remaining rounds times agents, per branch) and the snapshot probe are worked out here from the
  source project, not taken from the caller. The probe is a real ``fork_from`` into a throwaway directory.
* The study's current round must equal the source's last committed round. A source holding added events
  after the event round is refused, because a fork would silently drop them from both branches.
* The two branches are ONE result: the comparison. It rests on the item, so a retraction stamps it. The
  without-event branch is not recorded or offered as a result of its own: a stamp on it alone would be false.
* Output is built in a staging directory. It reaches its final place only after both branches finished, the
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
``read_event_fork`` detects a changed manifest or branch database, not a changed reply cache or other file.
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
WITH_EVENT = "with-event"
WITHOUT_EVENT = "without-event"
_BRANCHES = (WITH_EVENT, WITHOUT_EVENT)
_STAGING_SUFFIX = ".executing"


class ExecutionError(DecisionCellError):
    """A refused or failed execution. ``code`` is stable and safe to log. ``gate`` is set if the gate blocked."""

    def __init__(self, code: str, detail: str = "", gate: GateResult | None = None) -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.gate = gate


@dataclass(frozen=True)
class EventForkResult:
    path: Path                              # holds result.json and the two branch projects
    manifest: dict                          # the parsed result.json; its SHA-256 is basis.result_hash
    basis: RunResultBasis
    stamps: tuple[tuple[str, str], ...]     # as read now; whoever shows the comparison must show these


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
    """Agent-rounds one branch will run. The gate prices a fork as two of these; use it to show the cost."""
    rounds, _, agents, _ = _source_facts(Path(source))
    return max(rounds - 1 - event_round, 0) * agents


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
) -> EventForkResult:
    """Gate, fork, run and record one FORK_FROM_EVENT. Raises; no output is released unless it returns.

    A blocked choice raises ``ExecutionError("GATE_BLOCKED")`` with the gate's result; the gate has audited
    it. The item is ``request.event_id``. ``parent_result_ids`` must name any recorded result that ``source``
    was itself produced from, or a retraction behind it is not carried into this one.
    """
    from agora.sim.engine import Simulation

    writer = _writer(audit)
    if not isinstance(request, OptionRequest) or request.option is not Option.FORK_FROM_EVENT:
        raise ExecutionError("OPTION_NOT_EXECUTABLE", "only FORK_FROM_EVENT can be executed")
    if not isinstance(study, StudyState) or not callable(kill_switch_on):
        raise ExecutionError("INPUT_INVALID", "a StudyState and a kill-switch probe are required")
    if not all(_identifier(v) for v in (tenant_id, project_id, study.study_id, result_id)):
        raise ExecutionError("INPUT_INVALID", "ids must be exact non-empty strings")
    if not isinstance(parent_result_ids, tuple) or not isinstance(other_item_ids, tuple):
        raise ExecutionError("INPUT_INVALID", "give parent results and other items as tuples")
    event_round = request.event_round
    if type(event_round) is not int or event_round < 0:
        raise ExecutionError("INPUT_INVALID", "a fork needs the event round")
    source, out_dir = Path(source), Path(out_dir)
    key = dict(tenant_id=tenant_id, project_id=project_id, study_id=study.study_id)

    rounds, last_round, agents, last_added = _source_facts(source)
    if study.current_round != last_round:
        raise ExecutionError("STUDY_ROUND_MISMATCH", "the study state does not match the source's last round")
    if event_round + 1 >= rounds:
        raise ExecutionError("NO_ROUND_LEFT", "there is no round after the event round to add it to")
    if last_added > event_round:
        raise ExecutionError("SOURCE_HAS_LATER_EVENTS", "a fork would drop events added after the event round")
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
            audit=writer, study=study, branch_cost_units=max(rounds - 1 - event_round, 0) * agents,
            snapshot_verifies=snapshot_verifies, escalation=escalation, grants=grants, now=now)
        gate, evidence = decided.gate, decided.evidence
        if not gate.executable:
            raise ExecutionError("GATE_BLOCKED", ",".join(gate.failures), gate)

        added = [{"type": "news", "text": s.statement_text, "round": event_round + 1}
                 for s in sorted(statements, key=lambda s: s.statement_id)]
        branches = {}
        for name, events in ((WITH_EVENT, added), (WITHOUT_EVENT, [])):
            project = staging / name
            Simulation.fork_from(source, event_round, project, events=events)
            forked = json.loads((project / "fork.json").read_text(encoding="utf-8"))
            branches[name] = {"final_state_digest": _run_branch(project, kill_switch_on),
                              "snapshot_meta_digest": forked["snapshot_meta_digest"],
                              "events_sha256": forked["events_sha256"]}
        if branches[WITH_EVENT]["snapshot_meta_digest"] != branches[WITHOUT_EVENT]["snapshot_meta_digest"]:
            raise ExecutionError("SOURCE_CHANGED", "the two branches did not start from the same snapshot")

        manifest = {
            "schema": SCHEMA, **key, "result_id": result_id, "item_id": request.event_id,
            "gate_event_id": gate.audit_event_id, "action_fingerprint": gate.action_fingerprint,
            "evidence_hash": evidence.evidence_hash,
            # Labels as the gate judged them: shown beside the result, not updated afterwards.
            "statement_labels": {i: s.label.value for i, s in evidence.statements},
            "primary_source_exception_ids": list(evidence.primary_source_exception_ids),
            "event_round": event_round, "added_in_round": event_round + 1, "cost_units": gate.cost_units,
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
    return EventForkResult(final, json.loads(raw), basis, stamps)


def read_event_fork(*, tenant_id: str, project_id: str, study_id: str, result_id: str,
                    out_dir: str | Path, audit: AnchoredAuditChain) -> EventForkResult:
    """A recorded comparison with its current stamps. A trusted service-side read.

    Refuses an unrecorded result, and one whose manifest or branch databases differ from what was recorded.
    """
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
        for name in _BRANCHES:
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
    return EventForkResult(path, manifest, basis,
                           run_result_stamps(result_id=result_id, audit=audit, **key))


__all__ = ["ExecutionError", "EventForkResult", "execute_event_fork", "fork_branch_cost", "read_event_fork"]
