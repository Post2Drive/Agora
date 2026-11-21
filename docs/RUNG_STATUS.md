# Agora Rung Status

**Assessment base:** `main` at `19f51d84d3ecc8392eb8713e392f93cb58a736bf` (21 November 2026), including merged PRs #51–#58 and the earlier merged implementation history.

**Status terms:** Demonstrated means merged implementation has direct test/CI evidence for the stated slice. Partial means meaningful contracts or components exist but the rung exit criteria are not complete. Not implemented means no operational capability is claimed.

## Current six-rung assessment

| Rung | Status | Merged evidence on this base | Remaining exit gaps |
|---|---|---|---|
| 1 — Foundation | **Mostly demonstrated** | Reproducible local project/runtime foundations, neutral-start and resume regression coverage, and the four-job Ubuntu/Windows × Python 3.11/3.12 CI matrix. Recent exact-head workflows for #53, #54, #55, #56, #57 and #58 each passed all four matrix jobs (runs #164, #165, #175, #173, #174 and #172 respectively). | Owner-operated local reset remains outside repository execution where applicable. Continue exact-head CI, independent review and mutation evidence for each implementation slice. |
| 2 — Ontology | **Demonstrated for the current typed-binding slice** | Binding contract and implementation (#23–#24), tabular bound validation (#25), synthetic retail/civic domain-pack proofs (#30, #40), pilot data contract (#41), and policy enforcement on governed binding paths (#43). | Broader ontology governance and complete domain coverage remain future work; do not equate the current typed contract with a general enterprise ontology service. |
| 3 — Ingestion with provenance | **Demonstrated for local structured snapshots; broader connectors remain partial** | Read-only snapshot commands (#28), scenario-input adapter and fixture proofs (#31, #41), append-only run input provenance (#35), policy wiring for import/binding/scenario-input boundaries (#43), and report provenance export (#44). | No real database drivers, network connector framework, or external write-back. Scenario-input provenance is not yet wired into the simulation engine. |
| 4 — Simulation as decision engine | **Partial** | Scenario-input contract/adapter (#29, #31), run provenance store (#35), report provenance export (#44), and governed-pipeline synthetic end-to-end test (#46). The test does not run the simulation engine. | Scenario-input provenance is **not wired into** `agora/sim/engine.py`: new runs do not yet prepare and persist the input envelope before population creation, and resume does not yet call `Store.assert_resume_input` before `World.load`. Matched-run validity and observed-outcome separation remain distinct evidence requirements. No simulation wiring is authorised by this status update. |
| 5 — Decisions and actions | **Partial; no operational action execution** | Decision schema/store (#37), approval state machine (#42), report provenance (#44), append-only observed-outcome store and independent outcome review lifecycle (#53), and binding purpose/retention propagation into the PDP (#54). #53 rejects simulation-only evidence for observed outcomes and preserves corrections/reviews append-only. | No action executor or external write-back exists. Dependency review markers for changed source/evidence are not implemented. Decision-store and audit-chain writes remain separate transactions; reconciliation queue/worker/repair are specified in #57 but not implemented. An approved decision or recorded outcome is not permission to execute an external action. |
| 6 — Security and deployment | **Partial; not an enterprise security/deployment capability** | Deny-by-default PDP (#39); standalone redacted hash-chain audit store (#38); policy enforcement on governed data paths (#43); report validated-prediction gate (#44); retention/erasure design (#45); decision lifecycle/approval-denial audit events (#47); trusted-principal design (#51); audit-anchor design (#52); deployment hardening specification (#55); synthetic pilot runbook (#56); reconciliation specification (#57); and first synthetic trusted-principal implementation slice (#58). #58 adds immutable `Principal`, a test-only `SyntheticFixtureAdapter` that refuses production mode, principal-based PDP evaluation and `approve_as()` without a caller-supplied role parameter. | #58 is only the first identity slice: legacy role-string `approve()` remains, call-site migration is pending, and OIDC/production authentication is not implemented. Audit anchoring is specified but no independent anchor implementation exists. Reconciliation is specified but no queue, detector, worker or repair command exists. Purpose/retention must be supplied by callers at the binding hook; broader call-site propagation still needs verification. OIDC, proven tenant isolation, backup/restore operations, incident response, and fleet deployment controls are not complete. |

## Merged implementation and design PRs

The following newer slices are confirmed merged on the assessed mainline:

- **#51:** trusted identity adapter specification.
- **#52:** independent audit-anchor specification.
- **#53:** append-only decision outcomes and review implementation.
- **#54:** binding purpose/retention propagation into the policy hook.
- **#55:** deployment hardening specification.
- **#56:** synthetic-data pilot runbook.
- **#57:** decision-store/audit-chain reconciliation specification.
- **#58:** first synthetic trusted-principal implementation slice; principal-based approval is available through `approve_as()`, while legacy role-string approval and other call-site migration remain.

Earlier merged foundations remain as recorded in the prior rung assessment: #23–#47 cover typed binding, ingestion/provenance, decisions, audit chain, PDP, approval, retention, report provenance and governed-pipeline tests.

## Open gaps to keep visible

1. **Simulation wiring:** scenario-input provenance is not connected to `agora/sim/**`. No edit to that path is authorised by this document; implementation requires Claude's written approval and a separate owner-approved execution step.
2. **Identity migration:** #58 provides a synthetic trusted-principal boundary for the approval slice only. Migrate remaining role-string call sites (decision, policy enforcement, outcomes and other privileged operations) in ordered, separately tested steps. OIDC remains a later, separately approved integration.
3. **Outcome dependency review:** #53 records and reviews outcomes, but source-change/erasure dependency review markers remain unimplemented.
4. **Audit anchoring:** #52 specifies an independent anchor contract; no independent anchor implementation is claimed.
5. **Cross-store consistency:** decision records/outcomes and the shared audit chain use separate SQLite stores. A write to one is not atomic with a write to the other. #57 specifies reconciliation; the queue, detector and repair workflow are not implemented.
6. **Purpose and retention:** #54 closes the binding-hook propagation gap by accepting and forwarding declared purpose/retention. Callers must supply those values; do not claim that every call site or all data paths have been migrated.
7. **Enterprise controls:** OIDC, proven tenant isolation, external audit anchoring, operational backup/restore, incident response and fleet deployment are not complete.
8. **Pilot boundary:** #56 is a synthetic rehearsal runbook only. Scenario-input-to-engine wiring remains absent; no live pilot, real data, or external action is authorised.

## Evidence and interpretation rules

- Recent exact-head GitHub Actions evidence: #53 run 164, #54 run 165, #55 run 175, #56 run 173, #57 run 174, and #58 run 172. Each run completed successfully with all four Ubuntu/Windows × Python 3.11/3.12 jobs green.
- The PR descriptions report clean-checkout test/mutation evidence for implementation slices #53 and #58. CI success is additional evidence, not a substitute for independent code review or owner approval.
- The governed-pipeline tests use synthetic fixtures only. They prove integration boundaries and fail-closed paths; they do not run `agora/sim/**` or establish predictive validity.
- Report provenance keeps exploratory outputs visibly simulated. `VALIDATED_PREDICTION_ENABLED` remains `False`.
- No simulated preference, action, conversion, or report is observed demand, a real sale, or validated prediction.
- No simulations, calibration, backtests, forecasts, study mutations, real data, credentials, drivers, network connectors, or external write-back are authorised by this status document.
- Review/merge gate: do not infer owner approval from green CI or a draft PR. ChatGPT must not request review, approve, mark ready, or merge without the owner's explicit `review` instruction.

## Process note

This assessment is a documentation snapshot of the merged mainline at the SHA stated above. Reassess it after material merges; do not silently promote partial rungs to demonstrated based only on specifications or CI.
