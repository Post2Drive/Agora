"""Machine-checkable action preconditions: grammar, pack validation, proposal and admission behaviour."""
import copy
from decimal import Decimal

import pytest

import test_ontology_action_proposals as proposals
from agora.ontology import OntologyError, parse_domain_pack, preconditions as pc, propose_action
from agora.ontology.actions import proposal_digest
from agora.ontology import actions as actions_module

from test_ontology_action_admission import _admit
from test_ontology_action_approvals import _decide, catalog  # noqa: F401
from test_ontology_action_proposals import _allow, _propose, _values, world  # noqa: F401

CID = "backup:Customer.id"
CNT, AMT, DUE, URG, CH = (f"backup:Request.{n}" for n in ("count", "amount", "due", "urgent", "channel"))


class P:  # a property stand-in
    def __init__(self, data_type):
        self.data_type = data_type


PROPS = {CID: P("identifier"), "backup:Customer.email": P("string"), CNT: P("integer"), AMT: P("decimal"),
         DUE: P("date"), URG: P("boolean"), CH: P("enum"), "backup:Request.at": P("timestamp"),
         "backup:Request.blob": P("structured_object")}


def values(actor="C-1", target="C-2", **param):
    base = {CNT: 2, AMT: "10.50", DUE: "2026-12-01", URG: False, CH: "phone"}
    return {"actor": {CID: actor}, "target": {CID: target}, "param": {**base, **param}}


@pytest.mark.parametrize("text,ok", [
    (f"expr: param.{CNT} >= 1", True), (f"expr: param.{CNT} > 2", False), (f"expr: param.{CNT} <= 2", True),
    (f"expr: param.{CNT} < 2", False), (f"expr: param.{CNT} == 2", True), (f"expr: param.{CNT} != 2", False),
    (f"expr: param.{AMT} < 10.51", True), (f"expr: param.{AMT} == 10.5", True), (f"expr: param.{AMT} > 10.50", False),
    (f"expr: param.{DUE} >= \"2026-12-01\"", True), (f"expr: param.{DUE} < \"2026-12-01\"", False),
    (f"expr: param.{URG} == false", True), (f"expr: param.{URG} == true", False),
    (f"expr: param.{CH} == \"phone\"", True), (f"expr: param.{CH} != \"phone\"", False),
    (f"expr: actor.{CID} != target.{CID}", True), (f"expr: actor.{CID} == target.{CID}", False),
    (f"expr: target.{CID} == \"C-2\" and param.{CNT} == 2", True),
    (f"expr: target.{CID} == \"C-2\" and param.{CNT} == 3", False),
    (f"expr: target.{CID} == \"x and y\"", False),
    (f"expr: param.{CNT} == 2 and param.{CNT} == 2 and param.{CNT} >= 0", True),
    (f"expr: param.{CNT} == null", False), (f"expr: param.{CNT} != null", True),
])
def test_expressions_evaluate(text, ok):
    pc.validate(_action(text), OBJECTS, PROPS)
    assert pc.evaluate(text, PROPS, values()) is ok


OBJECTS = {"backup:Customer": (CID, "backup:Customer.email")}


def _action(*texts):
    class A:
        actor_type_id = target_type_id = "backup:Customer"
        inputs = (CNT, AMT, DUE, URG, CH, "backup:Request.at", "backup:Request.blob")
        preconditions = texts
    return A


@pytest.mark.parametrize("raw,expected", [(None, False), ("2", False), (True, False), (2.0, False)])
def test_null_and_wrong_typed_values_fail_closed(raw, expected):
    scope = values()
    scope["param"][CNT] = raw
    for op in (">=", "<=", "==", ">", "<"):
        assert pc.evaluate(f"expr: param.{CNT} {op} 2", PROPS, scope) is (op in ("==", "<=", ">=") and raw == "2")


def test_null_equals_null_only_for_a_null_value():
    scope = values()
    scope["param"][CNT] = None
    assert pc.evaluate(f"expr: param.{CNT} == null", PROPS, scope) is True
    assert pc.evaluate(f"expr: param.{CNT} != null", PROPS, scope) is False
    assert pc.evaluate(f"expr: param.{CNT} >= 1", PROPS, scope) is False
    assert pc.evaluate(f"expr: param.{CNT} < 1", PROPS, scope) is False


def test_a_missing_or_malformed_stored_value_is_false_not_an_error():
    scope = values()
    scope["actor"] = {}
    assert pc.evaluate(f"expr: actor.{CID} == \"C-1\"", PROPS, scope) is False
    scope = values(**{DUE: "2026-13-45"})
    assert pc.evaluate(f"expr: param.{DUE} >= \"2026-01-01\"", PROPS, scope) is False
    scope = values(**{AMT: "ten"})
    assert pc.evaluate(f"expr: param.{AMT} > 1", PROPS, scope) is False
    scope = values(**{URG: "false"})
    assert pc.evaluate(f"expr: param.{URG} == false", PROPS, scope) is False
    scope = values(**{CH: 5})
    assert pc.evaluate(f"expr: param.{CH} == \"phone\"", PROPS, scope) is False


@pytest.mark.parametrize("text", [
    "", "expr:", "expr: ", f"param.{CNT} == 1", "expr: __import__('os')", f"expr: param.{CNT}",
    f"expr: param.{CNT} == 1 or param.{CNT} == 2", f"expr: param.{CNT} == 1 and", f"expr: and param.{CNT} == 1",
    f"expr: param.{CNT} = 1", f"expr: param.{CNT} === 1", f"expr: param.{CNT} == 1 == 1",
    f"expr: param.{CNT} + 1 == 2", f"expr: other.{CNT} == 1", f"expr: param.{CNT} == 'a'",
    f"expr: param.{CNT} == \"unterminated", f"expr: param.{CNT} == 01", f"expr: param.{CNT} == 1.", "expr: 1 == 1.5.2",
    f"expr: param.{CNT} == \"café\"", "expr: " + "param.x == 1 and " * 8 + "param.x == 1",
    "expr: param." + "a" * 201 + " == 1", "expr: param.x == " + "9" * 19,
])
def test_text_outside_the_grammar_is_refused(text):
    with pytest.raises(pc.PreconditionError):
        pc.parse(text)


@pytest.mark.parametrize("text", [
    f"expr: param.nope == 1", f"expr: actor.backup:Customer.nope == \"a\"", f"expr: param.backup:Request.blob == null",
    f"expr: param.backup:Request.at == \"2026-01-01T00:00:00Z\"", f"expr: param.{CNT} == \"1\"",
    f"expr: param.{CNT} == true", f"expr: param.{CH} < \"z\"", f"expr: param.{URG} > false", f"expr: param.{CNT} < null",
    f"expr: param.{DUE} == 3", f"expr: param.{CNT} == param.{CH}", f"expr: param.{AMT} == param.{DUE}",
    f"expr: param.{CH} >= \"a\"",
])
def test_a_pack_with_an_ill_fitting_expression_is_refused(text):
    with pytest.raises(pc.PreconditionError):
        pc.validate(_action(text), OBJECTS, PROPS)


def test_free_text_preconditions_are_not_checked_or_evaluated():
    pc.validate(_action("target_exists", "expr: param.%s >= 1" % CNT), OBJECTS, PROPS)
    assert not pc.is_expression("target_exists") and not pc.is_expression(None)


def test_ordering_works_on_dates_against_a_literal_and_on_number_pairs():
    pc.validate(_action(f"expr: param.{DUE} >= \"2026-01-01\"", f"expr: param.{CNT} < param.{AMT}"), OBJECTS, PROPS)
    assert pc.evaluate(f"expr: param.{CNT} < param.{AMT}", PROPS, values()) is True


def test_numbers_compare_exactly():
    assert Decimal("0.1") + Decimal("0.2") == Decimal("0.3")
    scope = values(**{AMT: "0.30"})
    assert pc.evaluate(f"expr: param.{AMT} == 0.3", PROPS, scope) is True
    assert pc.evaluate(f"expr: param.{AMT} > 0.29", PROPS, scope) is True


# ---- unknown values never satisfy a comparison

def _with(role, name, value="__absent__"):
    scope = values()
    if value == "__absent__":
        del scope[role][name]
    else:
        scope[role][name] = value
    return scope


@pytest.mark.parametrize("value", [None, "__absent__"])
@pytest.mark.parametrize("name,literal", [(CH, '"frozen"'), (CNT, "5"), (AMT, "1.5"), (DUE, '"2026-12-25"'),
                                          (URG, "true")])
def test_an_unknown_value_is_not_unequal_to_a_literal(value, name, literal):
    scope = _with("param", name, value)
    for text in (f"expr: param.{name} != {literal}", f"expr: {literal} != param.{name}",
                 f"expr: param.{name} == {literal}"):
        assert pc.evaluate(text, PROPS, scope) is False


@pytest.mark.parametrize("left", [None, "__absent__", "C-1"])
@pytest.mark.parametrize("right", [None, "__absent__", "C-2"])
def test_references_with_an_unknown_side_are_neither_equal_nor_unequal(left, right):
    if left == "C-1" and right == "C-2":
        return
    scope = {"actor": {} if left == "__absent__" else {CID: left},
             "target": {} if right == "__absent__" else {CID: right}, "param": {}}
    for op in ("==", "!="):
        assert pc.evaluate(f"expr: actor.{CID} {op} target.{CID}", PROPS, scope) is False


def test_a_property_that_was_never_read_does_not_count_as_null():
    for scope in (_with("target", CID), {"actor": {}, "param": {}}):
        for text in (f"expr: target.{CID} == null", f"expr: null == target.{CID}", f"expr: target.{CID} != null"):
            assert pc.evaluate(text, PROPS, scope) is False


def test_the_literal_null_still_tests_a_stored_null_from_either_side():
    scope = values(target=None)
    assert pc.evaluate(f"expr: null == target.{CID}", PROPS, scope) is True
    assert pc.evaluate(f"expr: null != target.{CID}", PROPS, scope) is False
    assert pc.evaluate(f"expr: null != target.{CID}", PROPS, values()) is True


@pytest.mark.parametrize("raw", ["NaN", "sNaN", "Infinity", "-Infinity"])
def test_a_non_finite_number_is_false_not_an_error(raw):
    for op in ("==", "!=", "<", ">", "<=", ">="):
        assert pc.evaluate(f"expr: param.{AMT} {op} 1", PROPS, values(**{AMT: raw})) is False
    assert pc.evaluate(f"expr: param.{AMT} != null", PROPS, values(**{AMT: raw})) is False


@pytest.mark.parametrize("text", [
    f" expr: param.{CNT} >= 1", f"Expr: param.{CNT} >= 1", f"EXPR:param.{CNT} >= 1", f"expr : param.{CNT} >= 1",
    f"\texpr: param.{CNT} >= 1",
])
def test_text_that_only_looks_like_an_expression_is_refused(text):
    with pytest.raises(pc.PreconditionError, match="exactly expr:"):
        pc.validate(_action(text), OBJECTS, PROPS)


@pytest.mark.parametrize("text", [
    f"expr: param.{DUE} < \"2026-99-99\"", f"expr: \"2026-02-30\" > param.{DUE}",
    f"expr: param.{DUE} != \"2025-02-29\"",
])
def test_an_impossible_date_literal_is_refused(text):
    with pytest.raises(pc.PreconditionError, match="not a real date"):
        pc.validate(_action(text), OBJECTS, PROPS)


# ---- through a real pack, proposal, approval and admission

def _with_preconditions(monkeypatch, *texts):
    def patched():
        import copy as _copy
        from test_ontology_link_source_refs import _pack_data
        data = _copy.deepcopy(_pack_data())
        data["pack_id"] = "action-pack"
        for name, kind, nullable, sensitivity, allowed in proposals._EXTRA:
            prop = {"property_id": f"backup:Request.{name}", "version": "1.0.0", "name": name, "data_type": kind,
                    "required": True, "nullable": nullable, "sensitivity": sensitivity}
            if allowed:
                prop["allowed_values"] = allowed
            data["property_types"].append(prop)
        action = proposals._action("backup:FollowUp", proposals._NAMES)
        action["preconditions"] = list(texts)
        data["action_types"] = [action, proposals._action("backup:Ping", []), proposals._action("backup:Blob", ["backup:Request.blob"]),
                                proposals._action("backup:Free", ["whatever_text"])]
        return parse_domain_pack(data)

    monkeypatch.setattr(proposals, "_action_pack", patched)


@pytest.fixture
def met(monkeypatch):
    _with_preconditions(monkeypatch, f"expr: actor.{CID} != target.{CID}", f"expr: param.{CNT} >= 1")


@pytest.fixture
def unmet(monkeypatch):
    _with_preconditions(monkeypatch, f"expr: param.{CNT} >= 5")


@pytest.fixture
def mixed(monkeypatch):
    _with_preconditions(monkeypatch, f"expr: param.{CNT} >= 1", "target_exists")


@pytest.fixture
def due_is_not_christmas(monkeypatch):
    _with_preconditions(monkeypatch, f'expr: param.{DUE} != "2026-12-25"')


def test_a_null_input_refuses_a_not_equal_proposal_and_records_nothing(due_is_not_christmas, world):
    with pytest.raises(OntologyError, match="precondition is not met"):
        _propose(world, parameters=_values(due=None))
    assert proposals._proposed_events(world) == 0
    assert _propose(world).document["preconditions_evaluated"] is True


def test_a_met_precondition_is_recorded_in_the_proposal(met, world):
    proposal = _propose(world)
    d = proposal.document
    assert d["preconditions_met"] == [f"expr: actor.{CID} != target.{CID}", f"expr: param.{CNT} >= 1"]
    assert d["preconditions_evaluated"] is True and d["executed"] is False
    assert proposal.digest == proposal_digest(d)


def test_an_unmet_precondition_refuses_the_proposal_and_records_nothing(unmet, world):
    with pytest.raises(OntologyError, match="precondition is not met"):
        _propose(world)
    assert proposals._proposed_events(world) == 0


def test_the_values_are_not_in_the_refusal(unmet, world):
    with pytest.raises(OntologyError) as err:
        _propose(world)
    assert "C-1" not in str(err.value) and "10.50" not in str(err.value)


def test_free_text_beside_an_expression_keeps_evaluated_false(mixed, world):
    d = _propose(world).document
    assert d["preconditions_met"] == [f"expr: param.{CNT} >= 1"] and d["preconditions_evaluated"] is False


def test_packs_without_expressions_produce_the_documents_they_always_did(world):
    d = _propose(world).document
    assert "preconditions_met" not in d and d["preconditions_evaluated"] is False


def test_a_proposal_for_a_pack_whose_expression_would_now_fail_is_not_admitted(met, world, monkeypatch):
    proposal = _propose(world)
    _decide(world, proposal)
    # the stored object no longer satisfies the precondition: the rebuilt proposal must refuse
    real = actions_module.preconditions.evaluate
    monkeypatch.setattr(actions_module.preconditions, "evaluate", lambda *a, **k: False)
    with pytest.raises(OntologyError):
        _admit(world, proposal)
    monkeypatch.setattr(actions_module.preconditions, "evaluate", real)
    _admit(world, proposal)


def test_a_pack_with_a_bad_expression_is_refused_at_registration(world):
    from test_ontology_link_source_refs import _pack_data
    data = copy.deepcopy(_pack_data())
    action = proposals._action("backup:FollowUp", [])
    action["preconditions"] = ["expr: param.missing == 1"]
    data["action_types"] = [action]
    with pytest.raises(OntologyError, match="precondition is not valid"):
        parse_domain_pack(data)
    action["preconditions"] = [f"expr: actor.{CID} == \"C-1\""]
    parse_domain_pack(data)


def test_comparison_signs_inside_a_string_literal_are_text():
    scope = values(target="a<=b == c")
    assert pc.evaluate(f"expr: target.{CID} == \"a<=b == c\"", PROPS, scope) is True
    assert pc.evaluate(f"expr: target.{CID} != \"a<=b == c\"", PROPS, scope) is False


def test_evaluation_never_orders_values_of_different_kinds_or_booleans():
    # evaluate() can be called without validate(); it must still not raise or order such values
    assert pc.evaluate(f"expr: param.{CNT} < \"5\"", PROPS, values()) is False
    assert pc.evaluate(f"expr: param.{URG} > false", PROPS, values(**{URG: True})) is False
    assert pc.evaluate(f"expr: param.{URG} >= true", PROPS, values(**{URG: True})) is False


def test_a_malformed_value_is_not_unequal_to_null():
    assert pc.evaluate(f"expr: param.{AMT} != null", PROPS, values(**{AMT: "ten"})) is False
    assert pc.evaluate(f"expr: param.{AMT} == null", PROPS, values(**{AMT: "ten"})) is False


def test_only_the_extended_iso_date_form_counts():
    assert pc.evaluate(f"expr: param.{DUE} >= \"2026-01-01\"", PROPS, values(**{DUE: "20261201"})) is False
    assert pc.evaluate(f"expr: param.{DUE} >= \"2026-01-01\"", PROPS, values(**{DUE: "2026-12-01"})) is True
