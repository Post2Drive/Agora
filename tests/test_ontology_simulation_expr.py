"""The expression preconditions that held at the run appear in the simulation result."""
from test_ontology_preconditions import CID, CNT, met  # noqa: F401
from test_ontology_action_admission import RUNNER, _admit
from test_ontology_action_approvals import _decide, catalog  # noqa: F401
from test_ontology_action_proposals import _propose, world  # noqa: F401
from test_ontology_simulation import _run


def test_the_expressions_that_held_are_listed_in_the_result(met, world):
    proposal = _propose(world)
    _decide(world, proposal)
    _admit(world, proposal)
    result = _run(world, proposal)["result"]
    assert result["preconditions_met"] == [f"expr: actor.{CID} != target.{CID}", f"expr: param.{CNT} >= 1"]
