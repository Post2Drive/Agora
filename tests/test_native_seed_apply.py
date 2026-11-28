"""Applying a seed plan to a run: written once, before round 0, with a reason that names the source link."""
import pytest

from agora.sim.engine import Simulation
from agora.society.seed_plan import SeedCounts, SeedEdge, SeedPlan
from conftest import make_project

COUNTS = SeedCounts(links_read=4, links_used=3, other_import=1, not_mapped=0, same_agent=0, not_active=0)


def _plan(edges=None, seed_hash="h1"):
    edges = edges if edges is not None else (
        SeedEdge(0, 1, 0.7, 0.4, ("L1",), (("L1", "knows", "1.0.0"),)),
        SeedEdge(1, 0, 0.7, 0.4, ("L1", "L2"), (("L1", "knows", "1.0.0"), ("L2", "knows", "1.0.0"))),
    )
    return SeedPlan(seed_hash, "ab" * 32, tuple(edges), COUNTS)


@pytest.fixture
def native(tmp_path):
    p = make_project(tmp_path, communication="native", contact="relationship", contact_budget=1)
    return Simulation(p)


def test_edges_are_written_with_values_and_reason(native):
    assert native.seed_relationships(_plan()) is True
    soc = native.society
    r = soc.relationship(0, 1)
    assert (r["trust"], r["familiarity"]) == (0.7, 0.4)
    h = soc.relationship_history(0, 1)
    assert len(h) == 1 and h[0]["cause_message_id"] is None and h[0]["round"] == 0
    assert h[0]["reason"] == "seed: link L1 knows v1.0.0"
    assert (h[0]["trust_delta"], h[0]["familiarity_delta"]) == (0.7, 0.4)


def test_several_links_for_one_pair_are_named_in_the_reason(native):
    native.seed_relationships(_plan())
    assert native.society.relationship_history(1, 0)[0]["reason"] == "seed: link L1 knows v1.0.0 (+1 more)"


def test_run_record_keeps_hash_and_counts(native):
    native.seed_relationships(_plan())
    rec = native.store.get_meta("relationship_seed")
    assert rec["seed_hash"] == "h1" and rec["pack_fingerprint"] == "ab" * 32 and rec["edges"] == 2
    assert rec["counts"] == {"links_read": 4, "links_used": 3, "other_import": 1, "not_mapped": 0,
                             "same_agent": 0, "not_active": 0}


def test_same_seed_again_does_not_reseed(native):
    native.seed_relationships(_plan())
    assert native.seed_relationships(_plan()) is False
    assert len(native.society.relationship_history(0, 1)) == 1


def test_resume_in_a_new_process_does_not_reseed(native, tmp_path):
    native.seed_relationships(_plan())
    native.run(rounds=1)
    again = Simulation(native.dir)
    assert again.seed_relationships(_plan()) is False
    assert again.store.get_meta("relationship_seed")["edges"] == 2


def test_a_different_seed_is_refused(native):
    native.seed_relationships(_plan())
    with pytest.raises(ValueError, match="different relationship seed"):
        native.seed_relationships(_plan(seed_hash="h2"))


def test_seeding_after_the_first_round_is_refused(native):
    native.run(rounds=1)
    with pytest.raises(ValueError, match="before the first round"):
        native.seed_relationships(_plan())


def test_platform_runs_cannot_be_seeded(project):
    with pytest.raises(ValueError, match="communication: native"):
        Simulation(project).seed_relationships(_plan())


def test_state_digest_covers_the_seeded_edges(tmp_path):
    a = Simulation(make_project(tmp_path, "a", communication="native", contact="relationship", contact_budget=1))
    b = Simulation(make_project(tmp_path, "b", communication="native", contact="relationship", contact_budget=1))
    a.prepare(); b.prepare()
    assert a.state_digest() == b.state_digest()
    b.seed_relationships(_plan())
    assert a.state_digest() != b.state_digest()


def test_a_second_apply_never_overwrites_an_existing_edge(native):
    from agora.society import apply_seed_plan
    apply_seed_plan(native.society, _plan())
    with pytest.raises(ValueError, match="already exists"):
        apply_seed_plan(native.society, _plan())


def test_seeded_edges_open_contact_that_was_silent(tmp_path):
    """The reason for seeding: with no spaces or ties, relationship contact gives nothing until edges exist."""
    def contacts(seeded):
        p = make_project(tmp_path, "s" if seeded else "n", communication="native", contact="relationship",
                         contact_budget=2, spaces={}, events=[], conversions=[])
        sim = Simulation(p)
        if seeded:
            sim.prepare()
            crowd = [x.id for x in sim.world.agents if not x.is_llm and x.kind != "account"][:8]
            sim.seed_relationships(_plan([SeedEdge(i, j, 0.8, 0.5, (), ()) for i in crowd for j in crowd if i != j]))
        sim.run(rounds=3)
        return sim.society._q("SELECT COUNT(*) FROM society_messages").fetchone()[0]
    assert contacts(True) > contacts(False)
