# Agora Rung Status

**Assessment base:** `main` at `adacbd71726324de71cdbf9d20943701c553d252` (21 November 2026), including merged PRs #51–#71 and the earlier merged implementation history.

**Status terms:** Demonstrated means merged implementation has direct test/CI evidence for the stated slice. Partial means meaningful contracts or components exist but the rung exit criteria are not complete. Not implemented means no operational capability is claimed.

## Current six-rung assessment

| Rung | Status | Merged evidence on this base | Remaining exit gaps |
|---|---|---|---|
| 1 — Foundation | **Mostly demonstrated** | Reproducible local project/runtime foundations, neutral-start and resume regression coverage, and the four-job Ubuntu/Windows × Python 3.11/3.12 CI matrix. Recent exact-head workflows for #53, #54, #55, #56, #57 and #58 each passed all four matrix jobs (runs #164, #165, #175, #173, #174 and #172 respectively); #63 run 201 and #66 run 198 also passed all four jobs. | Owner-operated local reset remains outside repository execution where applicable. Continue exact-head CI, independent review and mutation evidence for each implementation slice. |
| 2 — Ontology | **Demonstrated for the current typed-binding slice** | Binding contract and implementation (#23–#24), tabular bound validation (#25), synthetic retail/civic domain-pack proofs (#30, #40), pilot data contract (#41), and policy enforcement on governed binding paths (#43). | Broader ontology governance and complete domain coverage remain future work; do not equate the current typed contract with a general enterprise ontology service. |
| 3 — Ingestion with provenance | **Demonstrated for local structured snapshots; broader connectors remain partial** | Read-only snapshot commands (#28), scenario-input adapter and fixture proofs (#31, #41), append-only run input provenance (#35), policy wiring for import/binding/scenario-input boundaries (#43), and report provenance export (#44). | No real database drivers, network connector framework, or external write-back. Scenario-input provenance is not yet wired into the simulation engine. |
| 4 — Simulation as decision engine | **Partial** | Scenario-input contract/adapter (#29, #31), run provenance store (#35), report provenance export (#44), and governed-pipeline synthetic end-to-end test (#46). The test does not run the simulation engine. | Scenario-input provenance is **not wired into** `agora/sim/engine.py`: new runs do not yet prepare and persist the input envelope before population creation, and resume does not yet call `Store.assert_resume_input` before `World.load`. Matched-run validity and observed-outcome separation remain distinct evidence requirements. No simulation wiring is authorised by this status update. |
| 5 — Decisions and actions | **Partial; no operational action execution** | Decision schema/store (#37), approval state machine (#42), report provenance (#44), append-only observed-outcome store and independent outcome review lifecycle (#53), and binding purpose/retention propagation into the PDP (#54). #53 rejects simulation-only evidence for observed outcomes and preserves corrections/reviews append-only. | No action executor or external write-back exists. Dependency review markers for changed source/evidence are not implemented. Decision-store and audit-chain writes remain separate transactions; reconciliation queue/worker/repair are specified in #57 but not implemented. An approved decision or recorded outcome is not permission to execute an external action. |
| 6 — Security and deployment | **Partial; not an enterprise security/deployment capability** | Deny-by-default PDP (#39); redacted hash-chain audit store (#38); policy enforcement (#43); principal foundation and approval bridge (#58); local-sidecar anchor (#63); Windows lock fix (#66); principal-first outcome wrappers (#70); anchored-writer factory and policy-denial wiring (#71). | #70 still bridges outcome operations to legacy role-string APIs. #71 wires anchored audit into policy-denial/import/binding/scenario-input paths (Stages A/D), but decision lifecycle and outcome/review append paths (Stages B/C) remain unwired. The writer remains optional on the API paths; protected-mode enforcement and principal-native policy callback are not complete. Trust remains `local_sidecar`, unable to detect coordinated rollback of both local stores. OIDC, proven tenant isolation, external anchoring, reconciliation implementation, operational backup/restore, incident response and fleet deployment are not complete. |

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
- **#63:** local-sidecar audit-anchor implementation merged; exact-head CI run 201 passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. It has `local_sidecar` trust only.
- **#70:** principal-gated outcome record/review wrappers and exact required-role filtering merged; exact-head CI run 209 ([44923562288](https://github.com/Post2Drive/Agora/actions/runs/44923562288)) passed all four matrix jobs. The wrappers still bridge to legacy role-string outcome functions.
- **#71:** anchored writer factory and policy-denial/data-boundary wiring (Stages A/D) merged at `5f8fb6abc4ecd6fb1182cf971aea536f4af0b013`; exact-head CI run 211 ([44926109220](https://github.com/Post2Drive/Agora/actions/runs/44926109220)) passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. Decision lifecycle and outcomes remain unwired.
- **#66:** Windows audit-log lock fix merged; exact-head CI run 198 passed all four matrix jobs.

Earlier merged foundations remain as recorded in the prior rung assessment: #23–#47 cover typed binding, ingestion/provenance, decisions, audit chain, PDP, approval, retention, report provenance and governed-pipeline tests.

## Open gaps to keep visible

1. **Simulation wiring:** scenario-input provenance is not connected to `agora/sim/**`. No edit to that path is authorised by this document; implementation requires Claude's written approval and a separate owner-approved execution step.
2. **Identity migration:** #58 provides the synthetic approval bridge; #70 adds principal-gated outcome wrappers but they still call legacy role-string functions. #71 adds audit-writer threading, not principal-native policy enforcement. Decision lifecycle, PDP, policy callback and complete outcome call-site migration remain. OIDC remains a later, separately approved integration.
3. **Outcome dependency review:** #53 records and reviews outcomes, but source-change/erasure dependency review markers remain unimplemented.
4. **Audit anchoring:** #71 completes writer factory and policy-denial/import/binding/scenario-input wiring (Stages A/D). Decision lifecycle and outcome/review append boundaries (Stages B/C) remain. `audit=None`/legacy paths are still available outside explicitly anchored calls; protected-mode requirement is not complete. `local_sidecar` cannot detect coordinated rollback of both local stores; external anchoring remains absent. The Linux lock-removal mutation proof did not catch removal of the cross-process lock.
5. **Cross-store consistency:** decision records/outcomes and the shared audit chain use separate SQLite stores. A write to one is not atomic with a write to the other. #57 specifies reconciliation; the queue, detector and repair workflow are not implemented.
6. **Purpose and retention:** #54 closes the binding-hook propagation gap by accepting and forwarding declared purpose/retention. Callers must supply those values; do not claim that every call site or all data paths have been migrated.
7. **Enterprise controls:** OIDC, proven tenant isolation, external audit anchoring, operational backup/restore, incident response and fleet deployment are not complete.
8. **Pilot boundary:** #56 is a synthetic rehearsal runbook only. Scenario-input-to-engine wiring remains absent; no live pilot, real data, or external action is authorised.

## Evidence and interpretation rules

- Recent exact-head GitHub Actions evidence: #53 run 164, #54 run 165, #55 run 175, #56 run 173, #57 run 174, #58 run 172, #63 run 201 ([44917009154](https://github.com/Post2Drive/Agora/actions/runs/44917009154)), #66 run 198 ([44912719682](https://github.com/Post2Drive/Agora/actions/runs/44912719682)), #70 run 209 ([44923562288](https://github.com/Post2Drive/Agora/actions/runs/44923562288)), and #71 run 211 ([44926109220](https://github.com/Post2Drive/Agora/actions/runs/44926109220)). All four Ubuntu/Windows × Python 3.11/3.12 jobs passed for each listed implementation run.
- The PR descriptions report clean-checkout test/mutation evidence for implementation slices #53 and #58. CI success is additional evidence, not a substitute for independent code review or owner approval.
- The governed-pipeline tests use synthetic fixtures only. They prove integration boundaries and fail-closed paths; they do not run `agora/sim/**` or establish predictive validity.
- Report provenance keeps exploratory outputs visibly simulated. `VALIDATED_PREDICTION_ENABLED` remains `False`.
- No simulated preference, action, conversion, or report is observed demand, a real sale, or validated prediction.
- No simulations, calibration, backtests, forecasts, study mutations, real data, credentials, drivers, network connectors, or external write-back are authorised by this status document.
- Review/merge gate: do not infer owner approval from green CI or a draft PR. ChatGPT must not request review, approve, mark ready, or merge without the owner's explicit `review` instruction.

## Process note

This assessment is a documentation snapshot of the merged mainline at the SHA stated above. Reassess it after material merges; do not silently promote partial rungs to demonstrated based only on specifications or CI.


## Current mainline correction — PR #74

Assessment base is `adacbd71726324de71cdbf9d20943701c553d252`. #74 adds anchored lifecycle/outcome append wiring and `require_anchored=True` gates on `approve_as()`, `record_outcome_as()` and `review_outcome_as()`. Exact-head run 221 (`44928837108`) passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. This is partial protected coverage; legacy role-string bridges, optional audit paths, Principal-native shared policy enforcement, reconciliation, outcome markers and the callable pipeline remain incomplete. Open #75 is not merged.
