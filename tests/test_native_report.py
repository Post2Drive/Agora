"""The native society report: deterministic, read-only, and quiet about text by default."""
import json

import pytest

from agora.society import SocietyError, SocietyStore, society_report
from agora.society.report import LIMITS, REPORT_FORMAT


def _store():
    soc = SocietyStore(":memory:")
    c1 = soc.direct(1, 2, round=1)
    m1 = soc.post(c1, 1, round=1, text="secret plan alpha", reason="handle @zed on topic roads")
    soc.post(c1, 2, round=2, text="reply beta", reason="answering")
    soc.post(c1, 2, round=2, text="again beta", reason="answering")
    soc.post(c1, 1, round=3, text="thanks", reason="closing")
    c2 = soc.direct(1, 3, round=2)
    m5 = soc.post(c2, 3, round=2, text="hello", reason="hi")
    soc.adjust_relationship(1, 2, round=2, trust_delta=0.2, familiarity_delta=0.1,
                            cause_message_id=m1, reason="private reason one")
    soc.adjust_relationship(1, 2, round=3, trust_delta=-0.05, cause_message_id=m5, reason="private reason two")
    soc.adjust_relationship(3, 1, round=2, trust_delta=-0.3, cause_message_id=m5, reason="private reason three")
    return soc


def test_report_shape_and_counts():
    r = society_report(_store())
    assert r["format"] == REPORT_FORMAT and r["limits"] == list(LIMITS)
    assert r["conversations"] == {"direct": 2}
    assert r["messages"] == {"total": 5, "senders": 3, "first_round": 1, "last_round": 3}
    assert r["activity_by_round"] == [{"round": 1, "messages": 1, "senders": 1},
                                      {"round": 2, "messages": 3, "senders": 2},
                                      {"round": 3, "messages": 1, "senders": 1}]
    assert r["top_senders"] == [{"agent": 1, "messages": 2}, {"agent": 2, "messages": 2},
                                {"agent": 3, "messages": 1}]


def test_pairs_exchanges_and_order():
    pairs = society_report(_store())["top_direct_pairs"]
    assert pairs[0] == {"agents": [1, 2], "messages": 4, "exchanges": 2, "first_round": 1, "last_round": 3}
    assert pairs[1]["agents"] == [1, 3] and pairs[1]["exchanges"] == 0


def test_relationship_moves_ordered_by_size_with_causes():
    r = society_report(_store())["relationship_changes"]
    assert r["total"] == 3
    first, second = r["largest_net_trust_moves"]
    assert (first["source"], first["target"], first["trust_net"]) == (3, 1, -0.3)
    assert (second["source"], second["target"], second["changes"]) == (1, 2, 2)
    assert second["trust_net"] == 0.15 and second["familiarity_net"] == 0.1
    assert second["cause_messages"] == [1, 5] and second["first_round"] == 2 and second["last_round"] == 3


def test_strongest_ties_ordered_by_trust():
    ties = society_report(_store())["strongest_ties"]
    assert [(t["source"], t["target"]) for t in ties] == [(1, 2), (3, 1)]
    assert ties[0]["trust"] == 0.65


def test_text_and_reasons_excluded_by_default():
    blob = json.dumps(society_report(_store()))
    for secret in ("secret plan", "private reason", "@zed", "reply beta"):
        assert secret not in blob
    assert "recent_messages" not in society_report(_store())


def test_reasons_and_text_on_request():
    r = society_report(_store(), include_reasons=True)
    assert r["relationship_changes"]["largest_net_trust_moves"][1]["reasons"] == [
        "private reason one", "private reason two"]
    assert "recent_messages" not in r
    t = society_report(_store(), include_text=True)
    assert t["recent_messages"][0]["text"] == "hello" and "reason" not in t["recent_messages"][0]
    both = society_report(_store(), include_text=True, include_reasons=True)
    assert both["recent_messages"][0]["reason"] == "hi"


def test_digest_binding_and_determinism():
    a, b = _store(), _store()
    assert society_report(a) == society_report(b)
    assert society_report(a)["society_digest"] == a.digest()
    b.post(b.direct(2, 3, round=4), 2, round=4, text="x", reason="y")
    assert society_report(b)["society_digest"] != society_report(a)["society_digest"]


def test_read_only():
    soc = _store()
    before = soc.digest()
    society_report(soc, include_text=True, include_reasons=True)
    assert soc.digest() == before


def test_top_limits_rows_and_validates():
    r = society_report(_store(), top=1)
    assert len(r["top_senders"]) == 1 and len(r["top_direct_pairs"]) == 1
    assert len(r["relationship_changes"]["largest_net_trust_moves"]) == 1
    for bad in (0, 101, True, 2.0, "3", None):
        with pytest.raises(SocietyError):
            society_report(_store(), top=bad)


def test_names_map_labels_and_validates():
    r = society_report(_store(), names={1: "Asha", 2: "Ravi"})
    assert r["top_senders"][0]["agent"] == "Asha" and r["top_senders"][2]["agent"] == 3
    assert r["top_direct_pairs"][0]["agents"] == ["Asha", "Ravi"]
    for bad in ({"1": "a"}, {1: ""}, {1: 5}, [1], {True: "x"}):
        with pytest.raises(SocietyError):
            society_report(_store(), names=bad)


def test_empty_store():
    r = society_report(SocietyStore(":memory:"))
    assert r["messages"] == {"total": 0, "senders": 0, "first_round": None, "last_round": None}
    assert r["top_senders"] == [] and r["strongest_ties"] == [] and r["conversations"] == {}
    assert r["relationship_changes"] == {"total": 0, "largest_net_trust_moves": []}
