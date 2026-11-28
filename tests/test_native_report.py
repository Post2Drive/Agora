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


def _seeded_store():
    from agora.society import SocietyStore
    import sqlite3
    soc = SocietyStore.attach(sqlite3.connect(":memory:"))
    soc.adjust_relationship(1, 2, round=0, trust_delta=0.7, familiarity_delta=0.4, cause_message_id=None,
                            reason="seed: link L1 knows v1.0.0", initial_trust=0.0, initial_familiarity=0.0)
    soc.adjust_relationship(2, 1, round=0, trust_delta=0.5, familiarity_delta=0.2, cause_message_id=None,
                            reason="seed: link L2 knows v1.0.0", initial_trust=0.0, initial_familiarity=0.0)
    cid = soc.direct(1, 3, round=1)
    mid = soc.post(cid, 1, round=1, text="hello", reason="r")
    soc.adjust_relationship(1, 3, round=1, familiarity_delta=0.05, cause_message_id=mid, reason="sent a private message")
    soc.adjust_relationship(1, 2, round=2, familiarity_delta=0.05, cause_message_id=mid, reason="sent a private message")
    return soc


def test_report_has_no_seed_section_when_nothing_was_seeded():
    from agora.society import SocietyStore, society_report
    import sqlite3
    assert "seeded_relationships" not in society_report(SocietyStore.attach(sqlite3.connect(":memory:")))


def test_report_counts_seeded_edges_apart_from_ones_formed_in_the_run():
    from agora.society import society_report
    s = society_report(_seeded_store())["seeded_relationships"]
    assert s["edges_seeded"] == 2 and s["seeded_edges_changed_later"] == 1
    assert s["edges_now"] == 3 and s["edges_formed_during_run"] == 1
    assert s["basis"].startswith("assumption")
    assert "seed_hash" not in s


def test_report_adds_the_run_record_but_never_link_ids():
    import json
    from agora.society import society_report
    rec = {"seed_hash": "h1", "counts": {"links_read": 4, "links_used": 3, "other_import": 1, "not_mapped": 0,
                                         "same_agent": 0, "not_active": 0, "junk": 9}}
    s = society_report(_seeded_store(), seed_record=rec)["seeded_relationships"]
    assert s["seed_hash"] == "h1" and s["link_counts"]["links_used"] == 3 and "junk" not in s["link_counts"]
    text = json.dumps(society_report(_seeded_store(), seed_record=rec))
    assert "L1" not in text and "knows" not in text


def test_a_run_record_with_no_edges_still_shows_the_seed_was_applied():
    from agora.society import SocietyStore, society_report
    import sqlite3
    s = society_report(SocietyStore.attach(sqlite3.connect(":memory:")), seed_record={"seed_hash": "h", "counts": {}})
    assert s["seeded_relationships"]["edges_seeded"] == 0


def test_only_a_first_change_with_no_cause_and_the_seed_reason_counts_as_seeded():
    from agora.society import society_report
    soc = _seeded_store()
    cid = soc.direct(4, 5, round=1)
    mid = soc.post(cid, 4, round=1, text="hi", reason="r")
    soc.adjust_relationship(4, 5, round=1, familiarity_delta=0.1, cause_message_id=mid, reason="seed: link X t v1")
    soc.adjust_relationship(6, 7, round=1, familiarity_delta=0.1, cause_message_id=None, reason="seedling contact")
    assert society_report(soc)["seeded_relationships"]["edges_seeded"] == 2
