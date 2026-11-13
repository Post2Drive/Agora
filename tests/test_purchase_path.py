
"""Isolated technical test for the Nutrivance purchase conversion path.

Uses pytest's temporary project fixture. Does not modify Proof-5.
"""
import numpy as np

from agora.sim.engine import RoundOutput, Simulation


def test_purchase_action_eligibility_and_sqlite_persistence(project):
    sim = Simulation(project)

    try:
        world = sim.prepare()

        residents = [a for a in world.agents if a.kind == "llm"]
        assert len(residents) >= 2, "Need two LLM residents for this test"

        unregistered, registered = residents[:2]

        # 1. An unregistered resident must not be offered or complete buy.
        unregistered_opens = sim._open_conversions(unregistered, 48)
        assert not any(c.name == "buy" for c in unregistered_opens)

        rejected_out = RoundOutput()
        rejected = sim._apply(
            unregistered,
            {"type": "buy"},
            48,
            24.0,
            unregistered_opens,
            np.random.default_rng(0),
            rejected_out,
        )
        assert rejected is None
        assert rejected_out.conversions == []

        # 2. Simulate a valid prior registration.
        # The scenario defines requires as "any one" registration.
        registered.converted.add("register_lakeview")

        opens = sim._open_conversions(registered, 48)
        assert any(c.name == "buy" for c in opens), (
            "A registered resident should be eligible to buy in round 48"
        )

        # 3. Submit the actual buy action through the normal action handler.
        out = RoundOutput()
        result = sim._apply(
            registered,
            {"type": "buy"},
            48,
            24.0,
            opens,
            np.random.default_rng(0),
            out,
        )

        assert result is not None
        assert (registered.id, "buy") in out.conversions
        assert "buy" in registered.converted

        # 4. Persist the conversion through the normal SQLite round commit.
        stats = {
            "active": 1,
            "llm_calls": 0,
            "cache_hits": 0,
            "seconds": 0.0,
        }

        sim.store.commit_round(
            48,
            sim_time=sim.now(48).isoformat(),
            agents=world.agents,
            posts=out.posts,
            engagements=out.engagements,
            follows=out.follows,
            conversions=out.conversions,
            thoughts=out.thoughts,
            polls=out.polls,
            poll_results=out.poll_results,
            events=out.events,
            stats=stats,
        )

        rows = sim.store.rows(
            "SELECT round, agent, name FROM conversions WHERE agent=? AND name=?",
            (registered.id, "buy"),
        )
        assert rows == [(48, registered.id, "buy")]

        # 5. The normal eligibility check must prevent a second purchase.
        second_opens = sim._open_conversions(registered, 49)
        assert not any(c.name == "buy" for c in second_opens)

        second_out = RoundOutput()
        second_result = sim._apply(
            registered,
            {"type": "buy"},
            49,
            24.0,
            second_opens,
            np.random.default_rng(0),
            second_out,
        )
        assert second_result is None
        assert second_out.conversions == []

        # 6. Verify SQLite also ignores a duplicate conversion record.
        sim.store.commit_round(
            49,
            sim_time=sim.now(49).isoformat(),
            agents=world.agents,
            posts=[],
            engagements=[],
            follows=[],
            conversions=[(registered.id, "buy")],
            thoughts=[],
            polls=[],
            poll_results=[],
            events=[],
            stats=stats,
        )

        count = sim.store.rows(
            "SELECT COUNT(*) FROM conversions WHERE agent=? AND name=?",
            (registered.id, "buy"),
        )[0][0]
        assert count == 1

    finally:
        sim.close()

