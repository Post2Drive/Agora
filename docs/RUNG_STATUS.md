# Agora Rung Status

**Assessment base:** `main` at `cd28916ae9d2ba4408205ac70c1b6e082ebe1af5` (21 November 2026), including merged PRs #23–#47.

**Status terms:** Demonstrated means merged implementation has direct test/CI evidence for the stated slice. Partial means meaningful contracts or components exist but the rung exit criteria are not complete. Not implemented means no operational capability is claimed.

## Current six-rung assessment

| Rung | Status | Merged evidence on this base | Remaining exit gaps |
|---|---|---|---|
| 1 — Foundation | **Mostly demonstrated** | Reproducible local project/runtime foundations, neutral-start and resume regression coverage, and the four-job Ubuntu/Windows × Python 3.11/3.12 CI matrix. PR #46's exact-head workflow #148 passed all four jobs; its clean-checkout report records 468 passing tests. | The owner-operated local reset remains outside repository execution where applicable. Continue to require exact-head CI and independent Claude review before merge. |
| 2 — Ontology | **Demonstrated for the current typed-binding slice** | Binding contract and implementation (#23–#24), tabular bound validation (#25), synthetic retail/civic domain-pack proofs (#30, #40), and the pilot data contract (#41). | Broader ontology governance, identity integration, and complete domain coverage remain future work; do not equate the current typed contract with a general enterprise ontology service. |
| 3 — Ingestion with provenance | **Demonstrated for local structured snapshots; broader connectors remain partial** | Read-only snapshot commands (#28), scenario-input adapter and fixture proofs (#31, #41), append-only run input provenance (#35), and policy wiring for import/binding/scenario-input boundaries (#43). | No real database drivers, network connector framework, or external write-back. Continue to prove source lineage, safe diagnostics, and read-only behavior. |
| 4 — Simulation as decision engine | **Partial** | Scenario-input contract/adapter (#29, #31), run provenance store (#35), report provenance export (#44), and governed-pipeline end-to-end test (#46). The test is synthetic and does not run the simulation engine. | Scenario-input provenance is **not wired into** `agora/sim/engine.py`: new runs do not yet prepare and persist the input envelope before population creation, and resume does not yet call `Store.assert_resume_input` before `World.load`. Matched-run validity and observed-outcome separation remain distinct evidence requirements. |
| 5 — Decisions and actions | **Partial; no operational action execution** | Decision record specification/plan (#26, #36), immutable schema/store (#37), approval state machine (#42), and report provenance (#44). | Decision outcomes and review linkage are not implemented. No action executor or external write-back exists. An approved decision record is not permission to execute an external action. |
| 6 — Security and deployment | **Partial; not an enterprise security/deployment capability** | Deny-by-default policy decision point (#39), standalone redacted hash-chain audit store (#38), policy enforcement on three governed data paths (#43), report validated-prediction gate (#44), retention/erasure design (#45), and decision lifecycle and approval-denial events written to the audit chain when an audit store is supplied (#47). | Identity adapter is absent; caller-supplied approver `role` is not a trusted identity assertion; binding and scenario-input policy hooks do not themselves pass all `purpose`/`retention` metadata; audit-chain tail truncation is undetectable without an external anchor; decision-store and audit-chain writes are separate transactions. OIDC, proven tenant isolation, deployment fleet controls, backup/restore and operational incident controls are not complete. |

## Merged implementation and design PRs

All PRs below are closed and merged on the assessed history:

- **#23–#25:** ontology binding contract, read-only binding/materialization, and tabular bounds.
- **#26–#27:** decision-record and security/privacy design specifications.
- **#28–#31:** read-only snapshot commands, scenario-input specification, synthetic retail proof, and fail-closed scenario-input adapter.
- **#32–#34:** prior rung-status evidence, run-provenance specification, and engineering pilot readiness gates.
- **#35–#36:** append-only run input provenance and decision-record implementation plan.
- **#37–#40:** immutable decision schema/store, standalone audit hash chain, deny-by-default policy decision point, and synthetic civic domain-pack proof.
- **#41–#45:** pilot data contract, decision approval state machine, policy wiring, report provenance exports, and retention/erasure design.
- **#46–#47:** synthetic governed-pipeline end-to-end test with stage denial paths, and audit-chain events for decision lifecycle transitions and approval denials (opt-in `audit` argument).

## Open gaps to keep visible

1. **Simulation wiring:** no edit to `agora/sim/**` is authorised by these documents. The proposal is in [SIM_WIRING_PROPOSAL.md](SIM_WIRING_PROPOSAL.md); implementation requires Claude's written approval and a separate owner-approved execution step.
2. **Decision outcomes:** no observed outcome may be inferred from simulated preferences/actions. The proposed append-only contract is in [DECISION_OUTCOMES_SPEC.md](DECISION_OUTCOMES_SPEC.md).
3. **Identity and role trust:** the approval API currently accepts a caller-supplied role. A future identity adapter must derive roles from a trusted authenticated principal; callers must not self-assert approver authority.
4. **Purpose and retention propagation:** the binding and scenario-input enforcement hooks do not pass the complete column-level purpose/retention contract to the PDP. Current callers may need a policy wrapper; this is a known integration gap, not a completed control.
5. **Audit integrity:** hash-chain verification detects internal tampering/reordering but cannot detect tail truncation without an independently stored external anchor.
6. **Cross-store consistency:** decision records and the shared audit chain use separate SQLite stores. An audit append can fail after a decision transition is committed; reconciliation is required and the two writes must not be described as one transaction.
7. **Enterprise controls:** OIDC, tenant isolation, external audit anchoring, backup/restore hardening, incident response, and fleet deployment are not complete.

## Evidence and interpretation rules

- The Block 26 tests use synthetic fixtures only. They prove integration boundaries and fail-closed paths; they do not run `agora/sim/**` or establish predictive validity.
- The report provenance contract keeps exploratory outputs visibly simulated. `VALIDATED_PREDICTION_ENABLED` remains `False`.
- No simulated preference, action, conversion, or report is observed demand, a real sale, or validated prediction.
- No simulations, calibration, backtests, forecasts, study mutations, real data, credentials, drivers, network connectors, or external write-back are authorised by this status document.
- Merge rule: a PR is merged only at an exact reviewed head with four green CI jobs after Claude's independent clean-checkout review and mutation proofs (owner delegation of 21 November 2026). Green CI alone is not sufficient.

## Process note

PR #46 (test only) was merged at `6a8208f8` on the owner's explicit instruction ("merge 46") after four green CI jobs. Under the owner's standing delegation, Claude reviews and merges approved heads; ChatGPT works on documentation and specifications that need no test execution, and Claude implements and verifies code.
