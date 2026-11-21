# Agora Rung Status

**Assessment base:** `main` at `25231d68b6f9d5684b76b6204265cd225cc29449` (21 November 2026), including merged PRs #51–#80 and the earlier merged implementation history.

**Status terms:** Demonstrated means merged implementation has direct test/CI evidence for the stated slice. Partial means meaningful contracts or components exist but the rung exit criteria are not complete. Not implemented means no operational capability is claimed.

## Current six-rung assessment

| Rung | Status | Merged evidence on this base | Remaining exit gaps |
|---|---|---|---|
| 1 — Foundation | **Mostly demonstrated** | Reproducible local project/runtime foundations, neutral-start and resume regression coverage, and the four-job Ubuntu/Windows × Python 3.11/3.12 CI matrix. Recent exact-head workflows for #53, #54, #55, #56, #57 and #58 each passed all four matrix jobs (runs #164, #165, #175, #173, #174 and #172 respectively); #63 run 201 and #66 run 198 also passed all four jobs. | Owner-operated local reset remains outside repository execution where applicable. Continue exact-head CI, independent review and mutation evidence for each implementation slice. |
| 2 — Ontology | **Demonstrated for the current typed-binding slice** | Binding contract and implementation (#23–#24), tabular bound validation (#25), synthetic retail/civic domain-pack proofs (#30, #40), pilot data contract (#41), and policy enforcement on governed binding paths (#43). | Broader ontology governance and complete domain coverage remain future work; do not equate the current typed contract with a general enterprise ontology service. |
| 3 — Ingestion with provenance | **Demonstrated for local structured snapshots; broader connectors remain partial** | Read-only snapshot commands (#28), scenario-input adapter and fixture proofs (#31/#41), provenance store (#35), policy wiring (#43), report provenance (#44), and opt-in `require_policy` on import/binding/scenario-input (#79). | No real database drivers, network connector framework or write-back. `require_policy` still defaults to `False`; the scenario-input package remains disconnected from `agora/sim/engine.py`. |
| 4 — Simulation as decision engine | **Partial** | Scenario-input contract/adapter (#29, #31), run provenance store (#35), report provenance export (#44), and governed-pipeline synthetic end-to-end test (#46). The test does not run the simulation engine. | Scenario-input provenance is **not wired into** `agora/sim/engine.py`: new runs do not yet prepare and persist the input envelope before population creation, and resume does not yet call `Store.assert_resume_input` before `World.load`. Matched-run validity and observed-outcome separation remain distinct evidence requirements. No simulation wiring is authorised by this status update. |
| 5 — Decisions and actions | **Partial; no operational action execution** | Decision schema/store (#37), approval state machine (#42), report provenance (#44), append-only observed-outcome store and independent outcome review lifecycle (#53), and binding purpose/retention propagation into the PDP (#54). #53 rejects simulation-only evidence for observed outcomes and preserves corrections/reviews append-only. | No action executor or external write-back exists. Dependency review markers for changed source/evidence are not implemented. Decision-store and audit-chain writes remain separate transactions; reconciliation queue/worker/repair are specified in #57 but not implemented. An approved decision or recorded outcome is not permission to execute an external action. |
| 6 — Security and deployment | **Partial; not an enterprise security/deployment capability** | Deny-by-default PDP (#39), audit chain (#38), principal foundation (#58), local-sidecar anchor (#63), Windows lock fix (#66), outcome wrappers (#70), anchored writer wiring (#71/#74/#75), principal-bound `principal_policy()` and opt-in missing-policy denial (#78), data-boundary `require_policy` flag (#79), and principal-native `approve_as()` (#80). | Public role-string `approve()` remains; outcome wrappers still bridge to legacy APIs; `PolicyCallable` is operation/resource only; `require_policy=False` and `require_anchored=False` remain defaults; `audit=None` can fall back to an unanchored local chain. Trust is `local_sidecar`. OIDC, external anchoring, reconciliation, outcome markers, backup/restore, incident response and fleet deployment remain incomplete. |

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
- **#71:** anchored writer factory and policy-denial/data-boundary wiring (Stages A/D) merged at `5f8fb6abc4ecd6fb1182cf971aea536f4af0b013`; exact-head CI run 211 ([44926109220](https://github.com/Post2Drive/Agora/actions/runs/44926109220)) passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. Decision lifecycle/outcome append wiring is present via #74; protected gates are limited to the named principal entry points.
- **#74:** anchored decision lifecycle and outcome/review append wiring plus opt-in `require_anchored=True` gates on three Principal entry points; exact-head CI run 221 (`44928837108`) passed all four matrix jobs.
- **#75:** structural `AuditAppender` protocol used by decision/outcome lifecycle code; no change to optional `audit=None` behaviour. Exact-head CI run 224 (`44929428177`) passed all four matrix jobs.
- **#77:** five readiness documents refreshed and merged; exact-head documentation CI run 235 (`44931495436`) passed all four matrix jobs.
- **#78:** `principal_policy(principal, required_role)` binds a synthetic Principal to a policy callback; `enforce_policy(..., require_policy=True)` denies a missing policy. Exact-head CI run 233 (`44930549886`) passed all four matrix jobs.
- **#79:** `require_policy` is threaded through `ingest_csv()`, `materialize_instances()` and `build_scenario_input()`, but defaults remain `False`. Exact-head CI run 236 (`44931670540`) passed all four jobs after a transient Windows 3.11 SQLite lock failure was rerun successfully.
- **#80:** `authorize_decision_approval_principal()` and `approve_as()` are principal-native; legacy `approve()` remains public and role-string based. Exact-head CI run 239 (`44934473818`) passed all four matrix jobs.
- **#66:** Windows audit-log lock fix merged; exact-head CI run 198 passed all four matrix jobs.

Earlier merged foundations remain as recorded in the prior rung assessment: #23–#47 cover typed binding, ingestion/provenance, decisions, audit chain, PDP, approval, retention, report provenance and governed-pipeline tests.

## Open gaps to keep visible

1. **Simulation wiring:** scenario-input provenance is not connected to `agora/sim/**`. No edit to that path is authorised by this document; implementation requires Claude's written approval and a separate owner-approved execution step.
2. **Identity migration:** #80 makes `approve_as()` principal-native, but the public role-string `approve()` remains callable; #70 outcome wrappers still delegate to legacy role-string functions. The shared `PolicyCallable(operation, resource)` can be bound to a Principal with #78, but data-boundary `require_policy` is opt-in (#79) and does not default on. OIDC remains a later, separately approved integration.
3. **Outcome dependency review:** #53 records and reviews outcomes, but source-change/erasure dependency review markers remain unimplemented.
4. **Audit anchoring:** #71/#74 wire the writer through policy/data boundaries and lifecycle/outcome append points; `require_anchored=True` remains opt-in on the three principal wrappers. Legacy lifecycle methods and `audit=None` remain possible; the policy-denial path falls back to an unanchored project-local chain when no writer is supplied. `local_sidecar` cannot detect coordinated rollback of both stores; the Linux lock-removal mutation gap remains.
5. **Cross-store consistency:** decision records/outcomes and the shared audit chain use separate SQLite stores. A write to one is not atomic with a write to the other. #57 specifies reconciliation; the queue, detector and repair workflow are not implemented.
6. **Purpose and retention:** #54 closes the binding-hook propagation gap by accepting and forwarding declared purpose/retention. Callers must supply those values; do not claim that every call site or all data paths have been migrated.
7. **Enterprise controls:** OIDC, proven tenant isolation, external audit anchoring, operational backup/restore, incident response and fleet deployment are not complete.
8. **Pilot boundary:** #56 is a synthetic rehearsal runbook only. Scenario-input-to-engine wiring remains absent; no live pilot, real data, or external action is authorised.

## Evidence and interpretation rules

- Earlier exact-head GitHub Actions evidence: #53 run 164, #54 run 165, #55 run 175, #56 run 173, #57 run 174, #58 run 172, #63 run 201 (`44917009154`), #66 run 198 (`44912719682`), #70 run 209 (`44923562288`) and #71 run 211 (`44926109220`).
- Newer exact-head runs: #77 run 235 (`44931495436`), #78 run 233 (`44930549886`), #79 run 236 (`44931670540`) and #80 run 239 (`44934473818`) each passed all four Ubuntu/Windows × Python 3.11/3.12 jobs.
- CI note: #79's first Windows 3.11 attempt failed with SQLite `database is locked`; the rerun passed. The cause is not confirmed and remains a concurrency-hardening item.
- The PR descriptions report clean-checkout test/mutation evidence for implementation slices #53 and #58. CI success is additional evidence, not a substitute for independent code review or owner approval.
- The governed-pipeline tests use synthetic fixtures only. They prove integration boundaries and fail-closed paths; they do not run `agora/sim/**` or establish predictive validity.
- Report provenance keeps exploratory outputs visibly simulated. `VALIDATED_PREDICTION_ENABLED` remains `False`.
- No simulated preference, action, conversion, or report is observed demand, a real sale, or validated prediction.
- No simulations, calibration, backtests, forecasts, study mutations, real data, credentials, drivers, network connectors, or external write-back are authorised by this status document.
- Review/merge gate: do not infer owner approval from green CI or a draft PR. ChatGPT must not request review, approve, mark ready, or merge without the owner's explicit `review` instruction.

## Process note

This assessment is a documentation snapshot of the merged mainline at `25231d68b6f9d5684b76b6204265cd225cc29449`.
