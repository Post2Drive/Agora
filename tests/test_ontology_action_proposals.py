"""An action proposal binds exact objects, parameters and evidence, and executes nothing."""
import copy
import hashlib
import sqlite3

import pytest

from agora.identity import stable_record_key
from agora.ontology import OntologyError, parse_domain_pack, propose_action, recheck_action_proposal
from agora.ontology.actions import proposal_digest
from agora.policy import decide
from agora.tabular import ingest_csv

from test_ontology_link_source_refs import _pack_data
from test_ontology_store import _SCHEMA, _allow, _binding, catalog  # noqa: F401

_CSV = "customer_id,email\nC-1,one@example.test\nC-2,two@example.test\n"
_EXTRA = [  # (name, data_type, nullable, sensitivity, allowed_values)
    ("channel", "enum", False, "public", ["phone", "visit"]),
    ("count", "integer", False, "public", None),
    ("amount", "decimal", False, "public", None),
    ("due", "date", True, "public", None),
    ("at", "timestamp", False, "public", None),
    ("urgent", "boolean", False, "public", None),
    ("note", "string", False, "public", None),
    ("code", "identifier", False, "public", None),
    ("blob", "structured_object", False, "public", None),
]
_NAMES = [f"backup:Request.{x[0]}" for x in _EXTRA if x[0] != "blob"]


def _action(action_id, inputs):
    return {"action_type_id": action_id, "version": "1.0.0", "name": "x",
            "actor_type_id": "backup:Customer", "target_type_id": "backup:Customer",
            "inputs": inputs, "preconditions": ["target_exists"], "effects": ["follow_up_recorded"],
            "permissions": ["synthetic_test_only"], "simulated_only": True,
            "execution_mode": "simulation_only", "external_writeback": "prohibited"}


def _action_pack():
    data = copy.deepcopy(_pack_data())
    data["pack_id"] = "action-pack"
    for name, kind, nullable, sensitivity, allowed in _EXTRA:
        prop = {"property_id": f"backup:Request.{name}", "version": "1.0.0", "name": name,
                "data_type": kind, "required": True, "nullable": nullable,
                "sensitivity": sensitivity}
        if allowed:
            prop["allowed_values"] = allowed
        data["property_types"].append(prop)
    data["action_types"] = [
        _action("backup:FollowUp", _NAMES),
        _action("backup:Ping", []),
        _action("backup:Blob", ["backup:Request.blob"]),
        _action("backup:Free", ["whatever_text"]),
    ]
    return parse_domain_pack(data)


def _values(**changes):
    values = {"channel": "phone", "count": 2, "amount": "10.50", "due": "2026-12-01",
              "at": "2026-11-27T09:00:00+05:30", "urgent": False, "note": "call back", "code": "A-1"}
    values.update(changes)
    return {f"backup:Request.{k}": v for k, v in values.items()}


@pytest.fixture
def world(catalog):  # noqa: F811
    project, store, audit, _, _ = catalog
    pack_fp = store.register_pack(_action_pack(), policy=_allow, audit=audit)
    binding_fp = store.register_binding(pack_fp, _binding(), policy=_allow, audit=audit)
    source = project / "customers.csv"
    source.write_bytes(_CSV.encode())
    import_id = ingest_csv(project, source, _SCHEMA, data_role="context",
                           policy=_allow, audit=audit)["import_id"]
    store.materialize_binding(pack_fp, binding_fp, import_id, policy=_allow, audit=audit,
                              purpose="account support", retention="90 days")

    class World:
        pass

    w = World()
    w.project, w.store, w.audit, w.pack, w.import_id = project, store, audit, pack_fp, import_id
    w.sha = hashlib.sha256(_CSV.encode()).hexdigest()

    def end(key):
        return {"project_id": store.project_id, "pack_fingerprint": pack_fp,
                "type_id": "backup:Customer", "type_version": "1.0.0", "import_id": import_id,
                "record_key": stable_record_key("customers", key)}

    w.end = end
    w.evidence = [{"import_id": import_id, "file_sha256": w.sha, "locator": "row:2"}]
    return w


def _propose(w, policy=_allow, **changes):
    request = {"action_type_id": "backup:FollowUp", "action_type_version": "1.0.0",
               "actor": w.end("C-1"), "target": w.end("C-2"), "parameters": _values(),
               "evidence": w.evidence, "reason": "missed appointment"}
    request.update(changes)
    return propose_action(w.store, w.pack, **request, policy=policy, audit=w.audit,
                          purpose="account support", retention="90 days")


def _recheck(w, document, digest, policy=_allow):
    recheck_action_proposal(w.store, document, digest, policy=policy, audit=w.audit,
                            purpose="account support", retention="90 days")


def _recording(effect):
    seen = []

    def policy(operation, resource):
        seen.append((operation, list(resource["resource_ids"]), resource["source_sensitivity"]))
        return effect(operation, resource, len(seen))

    return policy, seen


def _deny(operation, resource):
    return {**_allow(operation, resource), "decision": "deny"}


def _proposed_events(w):
    conn = sqlite3.connect(w.project / "data" / "audit_chain.sqlite3")
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        return sum(str(row).count("ontology_action_proposed")
                   for table in tables for row in conn.execute(f"SELECT * FROM {table}"))
    finally:
        conn.close()


def test_a_proposal_binds_objects_parameters_and_evidence_and_executes_nothing(world):
    before = _proposed_events(world)
    proposal = _propose(world)
    d = proposal.document
    assert proposal.digest == proposal_digest(d)
    assert (d["executed"], d["preconditions_evaluated"]) == (False, False)
    assert (d["execution_mode"], d["external_writeback"]) == ("simulation_only", "prohibited")
    assert d["proposed_by"] == "ontology-test-operator"
    assert d["actor"]["file_sha256"] == d["target"]["file_sha256"] == world.sha
    assert d["actor"]["values_sha256"] != d["target"]["values_sha256"]
    assert d["parameters"]["backup:Request.at"] == "2026-11-27T03:30:00.000000Z"
    assert d["evidence"] == world.evidence
    assert d["sensitivity"] == "sensitive"
    assert "example.test" not in proposal.content
    assert _proposed_events(world) > before
    d["reason"] = "changed copy"
    assert proposal.document["reason"] == "missed appointment"
    assert _propose(world).digest == proposal.digest
    assert _propose(world, parameters=_values(count=3)).digest != proposal.digest


def test_evidence_order_does_not_change_the_digest(world):
    two = world.evidence + [{**world.evidence[0], "locator": "row:3"}]
    assert _propose(world, evidence=two).digest == _propose(world, evidence=two[::-1]).digest


def test_a_denied_caller_learns_nothing_about_what_exists(world):
    with pytest.raises(OntologyError, match="policy denied"):
        _propose(world, policy=_deny, action_type_id="backup:Missing", parameters={})


def test_the_first_decision_comes_before_any_lookup(world):
    policy, seen = _recording(lambda o, r, n: _allow(o, r))
    with pytest.raises(OntologyError, match="action type/version does not resolve"):
        _propose(world, policy=policy, action_type_id="backup:Missing")
    assert seen[0][0] == "ontology_action_propose" and "backup:Missing" in seen[0][1]


def test_the_final_decision_uses_the_highest_classification_and_can_refuse(world):
    policy, seen = _recording(
        lambda o, r, n: _deny(o, r) if r["source_sensitivity"] == "sensitive" else _allow(o, r))
    with pytest.raises(OntologyError, match="policy denied"):
        _propose(world, policy=policy)
    mine = [x[2] for x in seen if x[0] == "ontology_action_propose"]
    assert mine == ["internal", "sensitive"]
    assert not any(x[0] == "binding" for x in seen)  # refused before any source read


def test_an_unknown_identity_is_refused(world):
    anonymous = lambda o, r: {**_allow(o, r), "subject_id": "unknown"}
    with pytest.raises(OntologyError, match="principal-bound identity"):
        _propose(world, policy=anonymous)


def test_only_operators_may_propose_under_the_central_roles():
    resource = {"project_id": "p", "resource_ids": ["x"], "source_sensitivity": "internal"}
    allowed = {role for role in ("operator", "reviewer", "approver", "reader")
               if decide({"subject_id": "s", "project_id": "p"}, role,
                         "ontology_action_propose", resource)["decision"] == "allow"}
    assert allowed == {"operator"}


@pytest.mark.parametrize("name,value", [
    ("channel", "email"), ("channel", ""), ("channel", None),
    ("count", True), ("count", 2.0), ("count", "2"), ("count", 2**63),
    ("amount", 10.5), ("amount", "1e5"), ("amount", "NaN"), ("amount", "01.5"), ("amount", " 1"),
    ("due", "20261201"), ("due", "2026-13-01"),
    ("at", "2026-11-27T09:00:00"), ("at", "yesterday"),
    ("urgent", 0), ("note", 7), ("code", ""), ("code", " A-1"), ("note", "x" * 4097), ("note", "\ud800"),
])
def test_a_badly_typed_parameter_is_refused_without_echoing_it(world, name, value):
    with pytest.raises(OntologyError, match="parameter value is not valid") as error:
        _propose(world, parameters=_values(**{name: value}))
    assert str(error.value).endswith(f"backup:Request.{name}")


def test_a_nullable_parameter_may_be_null(world):
    assert _propose(world, parameters=_values(due=None)).document["parameters"][
        "backup:Request.due"] is None


@pytest.mark.parametrize("parameters", [
    {}, {**_values(), "backup:Request.extra": 1},
    {k: v for k, v in _values().items() if not k.endswith("note")},
])
def test_parameters_must_match_the_declared_inputs_exactly(world, parameters):
    with pytest.raises(OntologyError, match="exactly the action type inputs"):
        _propose(world, parameters=parameters)


@pytest.mark.parametrize("action,parameters,message", [
    ("backup:Blob", {"backup:Request.blob": {}}, "structured_object are not supported"),
    ("backup:Free", {"whatever_text": "x"}, "not a pack property"),
])
def test_inputs_nothing_can_type_are_refused(world, action, parameters, message):
    with pytest.raises(OntologyError, match=message):
        _propose(world, action_type_id=action, parameters=parameters)


@pytest.mark.parametrize("role", ["actor", "target"])
def test_the_actor_and_target_must_match_the_action_type(world, role):
    wrong = {**world.end("C-1"), "type_id": "backup:Other"}
    with pytest.raises(OntologyError, match=f"{role} object does not match"):
        _propose(world, **{role: wrong})


def test_a_missing_object_is_refused(world):
    with pytest.raises(OntologyError, match="not materialized"):
        _propose(world, target=world.end("C-404"))


@pytest.mark.parametrize("change,message", [
    ({"file_sha256": "b" * 64}, "does not match the cited import"),
    ({"locator": "row:99"}, "does not resolve"),
    ({"import_id": "latest"}, "exact import identifier"),
    ({"note": "extra"}, "carry only"),
])
def test_evidence_must_resolve_exactly(world, change, message):
    with pytest.raises(OntologyError, match=message):
        _propose(world, evidence=[{**world.evidence[0], **change}])


@pytest.mark.parametrize("evidence,message", [([], "exact source_refs"), ("twice", "twice")])
def test_a_proposal_needs_distinct_evidence(world, evidence, message):
    if evidence == "twice":
        evidence = world.evidence * 2
    with pytest.raises(OntologyError, match=message):
        _propose(world, evidence=evidence)


@pytest.mark.parametrize("reason", ["", " padded ", None])
def test_a_reason_is_required(world, reason):
    with pytest.raises(OntologyError, match="reason must be"):
        _propose(world, reason=reason)


def test_recheck_accepts_the_same_content_from_a_reader(world):
    proposal = _propose(world)

    def other_reader(operation, resource):
        assert operation in {"ontology_read", "binding"}
        return {**_allow(operation, resource), "subject_id": "second-person",
                "policy_version": "v2"}

    _recheck(world, proposal.document, proposal.digest, policy=other_reader)


def test_recheck_refuses_a_changed_document_under_the_retained_digest(world):
    proposal = _propose(world)
    changed = {**proposal.document, "proposed_by": "someone-else"}
    with pytest.raises(OntologyError, match="expected digest"):
        _recheck(world, changed, proposal.digest)


@pytest.mark.parametrize("path,value", [
    (("executed",), True), (("executed",), 0), (("declared_effects",), []),
    (("sensitivity",), "public"), (("actor", "values_sha256"), "sha256:" + "0" * 64),
    (("action_type", "fingerprint"), "sha256:" + "0" * 64), (("approved",), True),
])
def test_recheck_refuses_forged_content_even_with_its_own_digest(world, path, value):
    document = _propose(world).document
    node = document
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(OntologyError, match="no longer matches"):
        _recheck(world, document, proposal_digest(document))


def test_recheck_notices_a_source_row_edited_after_the_proposal(world):
    proposal = _propose(world)
    conn = sqlite3.connect(world.project / "data" / "tabular.sqlite3")
    try:
        triggers = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'")]
        for name in triggers:
            conn.execute(f'DROP TRIGGER "{name}"')
        columns = [r[1] for r in conn.execute("PRAGMA table_info(import_rows)")]
        changed = 0
        for column in columns:
            changed += conn.execute(
                f"UPDATE import_rows SET {column}=replace({column}, 'two@', 'xyz@') "
                f"WHERE instr({column}, 'two@')>0").rowcount
        conn.commit()
    finally:
        conn.close()
    assert changed >= 1
    with pytest.raises(OntologyError, match="does not match its row ID"):
        world.store.get_object(
            world.pack, "backup:Customer", "1.0.0", world.end("C-2")["record_key"],
            world.import_id, policy=_allow, audit=world.audit,
            purpose="account support", retention="90 days",
        )
    with pytest.raises(OntologyError, match="does not match its row ID"):
        _recheck(world, proposal.document, proposal.digest)
