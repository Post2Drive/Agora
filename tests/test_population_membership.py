from collections import Counter

from agora.scenario import Scenario, Segment, Space
from agora.sim.population import build


def test_exclusive_home_spaces_share_resident_population_by_capacity():
    sc = Scenario(
        name="two-apartment-membership-test",
        topic="sampling proposal",
        question="What do residents think?",
        context="Test only.",
        seed=42,
        llm_agents=13,
        crowd_agents=0,
        segments=[
            Segment(
                name="residents",
                share=1.0,
                persona="Apartment resident",
                platforms=["whatsapp"],
                names=["Resident"],
            )
        ],
        spaces=[
            Space(platform="whatsapp", name="Lakeview Residents", size=260, exclusive="home"),
            Space(platform="whatsapp", name="Palm Grove Residents", size=340, exclusive="home"),
        ],
    )

    world, _, memberships = build(sc)
    residents = [a for a in world.agents if a.kind == "llm"]
    home_memberships = [
        (agent_id, space)
        for agent_id, platform, space in memberships
        if platform == "whatsapp" and space in {"Lakeview Residents", "Palm Grove Residents"}
    ]
    counts = Counter(space for _, space in home_memberships)

    assert len(residents) == 13
    assert counts["Lakeview Residents"] + counts["Palm Grove Residents"] == 13
    assert counts["Lakeview Residents"] > 0
    assert counts["Palm Grove Residents"] > 0
    assert len({agent_id for agent_id, _ in home_memberships}) == 13
    assert counts == {"Lakeview Residents": 6, "Palm Grove Residents": 7}
