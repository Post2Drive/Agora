"""Native society store: conversations, append-only messages, relationships, digest."""
import sqlite3

import pytest

from agora.society import SocietyError, SocietyStore


@pytest.fixture
def store():
    s = SocietyStore(":memory:")
    yield s
    s.close()


def test_direct_conversation_is_unique_per_pair_and_symmetric(store):
    a = store.direct(1, 2, round=0)
    assert store.direct(2, 1, round=5) == a
    assert store.members(a) == [(1, "member"), (2, "member")]
    assert store.direct(1, 3, round=0) != a


def test_direct_needs_two_different_agents(store):
    with pytest.raises(SocietyError):
        store.direct(4, 4, round=0)


def test_message_delivery_to_the_other_party_only(store):
    c = store.direct(1, 2, round=0)
    m = store.post(c, 1, round=1, text="hello", reason="introduce")
    assert [x["message_id"] for x in store.inbox(2)] == [m]
    assert store.inbox(1) == []


def test_non_member_cannot_post_to_direct_or_group(store):
    d = store.direct(1, 2, round=0)
    g = store.create("group", 1, round=0, topic="street")
    for cid in (d, g):
        with pytest.raises(SocietyError, match="not a member"):
            store.post(cid, 9, round=1, text="x", reason="r")


def test_group_membership_and_delivery(store):
    g = store.create("group", 1, round=0, topic="street")
    store.join(g, 2, round=0)
    store.join(g, 3, round=0)
    m = store.post(g, 2, round=1, text="meeting?", reason="organise")
    assert [x["message_id"] for x in store.inbox(1)] == [m]
    assert [x["message_id"] for x in store.inbox(3)] == [m]
    assert store.inbox(2) == []
    with pytest.raises(SocietyError, match="already a member"):
        store.join(g, 2, round=1)


def test_direct_cannot_gain_members(store):
    d = store.direct(1, 2, round=0)
    with pytest.raises(SocietyError, match="fixed members"):
        store.join(d, 3, round=0)


def test_open_discussion_admits_any_agent_on_first_post(store):
    o = store.create("open", 1, round=0, topic="news")
    store.post(o, 7, round=1, text="I saw this", reason="react")
    assert (7, "member") in store.members(o)
    assert len(store.inbox(1)) == 1


def test_broadcast_only_owner_or_moderator_may_post(store):
    b = store.create("broadcast", 1, round=0, topic="notice")
    store.join(b, 2, round=0)
    store.join(b, 3, round=0, role="moderator")
    with pytest.raises(SocietyError, match="owner or moderator"):
        store.post(b, 2, round=1, text="x", reason="r")
    store.post(b, 3, round=1, text="update", reason="announce")
    assert len(store.inbox(2)) == 1


def test_create_refuses_direct_and_unknown_kinds(store):
    for kind in ("direct", "weird"):
        with pytest.raises(SocietyError):
            store.create(kind, 1, round=0, topic="t")


def test_messages_cannot_go_back_in_time_in_a_conversation(store):
    c = store.direct(1, 2, round=0)
    store.post(c, 1, round=5, text="a", reason="r")
    with pytest.raises(SocietyError, match="back in time"):
        store.post(c, 2, round=4, text="b", reason="r")


@pytest.mark.parametrize("bad", [dict(text=""), dict(text="  "), dict(reason=""), dict(text="x" * 8001)])
def test_message_requires_text_and_reason(store, bad):
    c = store.direct(1, 2, round=0)
    kwargs = dict(round=1, text="ok", reason="why")
    kwargs.update(bad)
    with pytest.raises(SocietyError):
        store.post(c, 1, **kwargs)


def test_round_and_ids_must_be_integers(store):
    c = store.direct(1, 2, round=0)
    for bad in (-1, 1.5, "1", True):
        with pytest.raises(SocietyError):
            store.post(c, 1, round=bad, text="x", reason="r")
    with pytest.raises(SocietyError):
        store.post(c, True, round=1, text="x", reason="r")


def test_messages_and_relationship_changes_are_append_only(store):
    c = store.direct(1, 2, round=0)
    m = store.post(c, 1, round=1, text="a", reason="r")
    store.adjust_relationship(2, 1, round=1, trust_delta=0.1, cause_message_id=m, reason="friendly")
    for sql in ("UPDATE society_messages SET text='x'", "DELETE FROM society_messages",
                "UPDATE society_relationship_changes SET reason='x'", "DELETE FROM society_relationship_changes"):
        with pytest.raises(sqlite3.DatabaseError):
            store._conn.execute(sql)


def test_read_cursor_hides_read_messages_and_never_moves_back(store):
    c = store.direct(1, 2, round=0)
    m1 = store.post(c, 1, round=1, text="a", reason="r")
    m2 = store.post(c, 1, round=2, text="b", reason="r")
    store.mark_read(2, m1)
    assert [x["message_id"] for x in store.inbox(2)] == [m2]
    store.mark_read(2, 0)
    assert [x["message_id"] for x in store.inbox(2)] == [m2]
    assert len(store.inbox(2, unread_only=False)) == 2
    with pytest.raises(SocietyError, match="does not exist"):
        store.mark_read(2, 99)


def test_relationship_defaults_clamping_and_history(store):
    c = store.direct(1, 2, round=0)
    m = store.post(c, 1, round=3, text="a", reason="r")
    r = store.adjust_relationship(2, 1, round=3, trust_delta=0.3, familiarity_delta=0.2,
                                  cause_message_id=m, reason="warm")
    assert r["trust"] == pytest.approx(0.8) and r["familiarity"] == pytest.approx(0.2)
    r = store.adjust_relationship(2, 1, round=4, trust_delta=0.9, cause_message_id=m, reason="warmer")
    assert r["trust"] == 1.0
    r = store.adjust_relationship(2, 1, round=2, trust_delta=-1.0, cause_message_id=None, reason="slight")
    assert r["trust"] == 0.0 and r["last_contact_round"] == 4
    history = store.relationship_history(2, 1)
    assert [h["trust_delta"] for h in history] == pytest.approx([0.3, 0.2, -1.0])
    assert history[0]["cause_message_id"] == m
    assert store.relationship(1, 2) is None


@pytest.mark.parametrize("kwargs", [
    dict(trust_delta=1.5), dict(familiarity_delta=-2), dict(trust_delta=True),
    dict(cause_message_id=999), dict(reason=" "),
])
def test_relationship_adjust_validates(store, kwargs):
    base = dict(round=1, cause_message_id=None, reason="why")
    base.update(kwargs)
    with pytest.raises(SocietyError):
        store.adjust_relationship(1, 2, **base)


def test_no_self_relationship(store):
    with pytest.raises(SocietyError):
        store.adjust_relationship(3, 3, round=0, cause_message_id=None, reason="r")


def _scenario(s):
    c = s.direct(1, 2, round=0)
    g = s.create("group", 1, round=0, topic="g")
    s.join(g, 2, round=0)
    m = s.post(c, 1, round=1, text="hi", reason="r")
    s.post(g, 2, round=2, text="all", reason="r")
    s.adjust_relationship(2, 1, round=1, trust_delta=0.1, cause_message_id=m, reason="r")
    s.mark_read(2, m)


def test_digest_is_deterministic_and_covers_every_table(store):
    other = SocietyStore(":memory:")
    _scenario(store)
    _scenario(other)
    base = store.digest()
    assert base == other.digest() and len(base) == 64
    mutations = {
        "conversations": "UPDATE society_conversations SET topic='zz' WHERE conversation_id=2",
        "memberships": "UPDATE society_memberships SET role='moderator' WHERE agent_id=2 AND conversation_id=2",
        "relationships": "UPDATE society_relationships SET trust=0.9",
        "read_cursors": "UPDATE society_read_cursors SET last_read_message_id=2",
    }
    for table, sql in mutations.items():
        copy = SocietyStore(":memory:")
        _scenario(copy)
        copy._conn.execute(sql)
        assert copy.digest() != base, table
        copy.close()
    for table, sql in {
        "messages": "DROP TRIGGER society_messages_no_update;UPDATE society_messages SET text='tampered'",
        "relationship_changes": "DROP TRIGGER society_changes_no_update;UPDATE society_relationship_changes SET reason='tampered'",
    }.items():
        copy = SocietyStore(":memory:")
        _scenario(copy)
        copy._conn.executescript(sql)
        assert copy.digest() != base, table
        copy.close()
    other.close()


def test_digest_differs_for_different_histories(store):
    other = SocietyStore(":memory:")
    _scenario(store)
    _scenario(other)
    c = other.direct(1, 2, round=9)
    other.post(c, 2, round=9, text="extra", reason="r")
    assert store.digest() != other.digest()
    other.close()


def test_persistence_and_reopen(tmp_path):
    path = tmp_path / "data" / "society.sqlite3"
    s = SocietyStore(path)
    _scenario(s)
    digest = s.digest()
    s.close()
    again = SocietyStore(path)
    assert again.digest() == digest
    assert len(again.thread(1)) == 1
    again.close()


def test_symlinked_path_is_refused(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(SocietyError, match="unsafe"):
        SocietyStore(link / "society.sqlite3")


def test_incomplete_schema_is_refused(tmp_path):
    path = tmp_path / "society.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE society_messages(x)")
    conn.commit()
    conn.close()
    with pytest.raises(SocietyError, match="incomplete"):
        SocietyStore(path)


def test_attached_store_shares_the_run_transaction(tmp_path):
    conn = sqlite3.connect(tmp_path / "run.db")
    conn.execute("CREATE TABLE posts(x)")
    conn.commit()
    s = SocietyStore.attach(conn)
    c = s.direct(1, 2, round=0)
    s.post(c, 1, round=1, text="hi", reason="r")
    assert conn.in_transaction  # nothing was committed by the store itself
    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM society_messages").fetchone()[0] == 0
    c = s.direct(1, 2, round=0)
    s.post(c, 1, round=1, text="hi", reason="r")
    conn.commit()
    s.close()  # closing an attached store leaves the run's connection open
    assert conn.execute("SELECT COUNT(*) FROM society_messages").fetchone()[0] == 1
    reopened = SocietyStore.attach(conn)
    assert reopened.thread(c)[0]["text"] == "hi"
    conn.close()
