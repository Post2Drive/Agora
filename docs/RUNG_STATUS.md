# Agora Rung Status

**Assessment base:** `main` at `112030a219e2d6f7278a46a95be2468634bf563a` (22 November 2026), including merged implementation PRs through #106; ChatGPT's docs-only draft PR #105 is the only open PR.

**Status terms:** Demonstrated means merged implementation has direct test/CI evidence for the stated slice. Partial means meaningful contracts or components exist but the rung exit criteria are not complete. Not implemented means no operational capability is claimed.

## Current six-rung assessment

| Rung | Status | Merged evidence on this base | Remaining exit gaps |
|---|---|---|---|
| 1 — Foundation | **Mostly demonstrated** | Reproducible local project/runtime foundations, neutral-start and resume regression coverage, and the four-job Ubuntu/Windows × Python 3.11/3.12 CI matrix. Recent exact-head workflows for #53, #54, #55, #56, #57 and #58 each passed all four matrix jobs (runs #164, #165, #175, #173, #174 and #172 respectively); #63 run 201 and #66 run 198 also passed all four jobs. | Owner-operated local reset remains outside repository execution where applicable. Continue exact-head CI, independent review and mutation evidence for each implementation slice. |
| 2 — Ontology | **Demonstrated for the current typed-binding slice** | Binding contract and implementation (#23–#24), tabular bound validation (#25), synthetic retail/civic domain-pack proofs (#30, #40), pilot data contract (#41), and policy enforcement on governed binding paths (#43). | Broader ontology governance and complete domain coverage remain future work; do not equate the current typed contract with a general enterprise ontology service. |
| 3 — Ingestion with provenance | **Demonstrated for local structured snapshots; broader connectors remain partial** | Read-only snapshot commands (#28), scenario-input adapter/fixture proofs (#31/#41), provenance store (#35), policy wiring (#43), report provenance (#44), default-on data-boundary hooks (#79/#89), public opt-out removal (#96) and direct-helper/anchored-writer hardening (#99). | No real drivers/connectors/write-back. Protected policy denial requires an anchored writer; test-only relaxation remains confined to the test fixture. |
| 4 — Simulation as decision engine | **Partial** | Scenario-input contract/adapter (#29, #31), run provenance store (#35), report provenance export (#44), and governed-pipeline synthetic end-to-end test (#46). The test does not run the simulation engine. | Scenario-input provenance is **not wired into** `agora/sim/engine.py`: new runs do not yet prepare and persist the input envelope before population creation, and resume does not yet call `Store.assert_resume_input` before `World.load`. Matched-run validity and observed-outcome separation remain distinct evidence requirements. No simulation wiring is authorised by this status update. |
| 5 — Decisions and actions | **Partial; no operational action execution** | Decision schema/store (#37), approval state machine (#42), append-only outcomes/reviews (#53), Principal wrappers (#70/#86/#92/#96), test-only legacy approval boundary (#97), guided synthetic pilot (#88), read-only decision/audit reconciliation (#100/#104) and read-only held-outcome listing (#102/#106). | No action executor or external write-back. Outcome dependency markers (#60) remain unimplemented. #104 validates immutable transition metadata, exact audit operation/resource IDs and partial-open cleanup; reconciliation still lacks sidecar-anchor verification, a reviewed queue/repair workflow and outcome/review coverage. Decision-store and audit-chain writes remain separate transactions. |
| 6 — Security and deployment | **Partial; not an enterprise security/deployment capability** | Deny-by-default PDP (#39), audit chain/anchor (#38/#63), writer/lifecycle wiring (#71/#74/#75), Principal policy (#78), data-boundary hooks (#79/#89/#96), approval (#80/#84/#97), outcome routes (#70/#86/#92/#96), protected policy-helper hardening (#99), guided pilot (#88), CLI import isolation (#94), decision/audit detector and hardening (#100/#104), and held-outcome list (#102/#106). | `local_sidecar` is not an independent security anchor and cannot detect coordinated rollback of both local stores; the Linux lock-removal mutation gap remains. Low-level lifecycle audit arguments remain optional; outcome markers, anchor verification, reconciliation queue/repair, backup/restore, incident response and fleet deployment remain incomplete. |

## Merged implementation and design PRs

The following newer slices are confirmed merged on the assessed mainline:

- **#51:** trusted identity adapter specification.
- **#52:** independent audit-anchor specification.
- **#53:** append-only decision outcomes and review implementation.
- **#54:** binding purpose/retention propagation into the policy hook.
- **#55:** deployment hardening specification.
- **#56:** synthetic-data pilot runbook.
- **#57:** read-only decision lifecycle/audit detector implemented by #100 and hardened by #104 (immutable source metadata, exact audit operation/resource IDs and partial-open cleanup); no anchor verification, queue, repair or outcome/review reconciliation.
- **#58:** first synthetic trusted-principal implementation slice; principal-based approval is available through `approve_as()`, while legacy role-string approval and other call-site migration remain.
- **#63:** local-sidecar audit-anchor implementation merged; exact-head CI run 201 passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. It has `local_sidecar` trust only.
- **#70:** principal-gated outcome record/review wrappers and exact required-role filtering merged; exact-head CI run 209 ([44923562288](https://github.com/Post2Drive/Agora/actions/runs/44923562288)) passed all four matrix jobs. The wrappers still bridge to legacy role-string outcome functions.
- **#71:** anchored writer factory and policy-denial/data-boundary wiring (Stages A/D) merged at `5f8fb6abc4ecd6fb1182cf971aea536f4af0b013`; exact-head CI run 211 ([44926109220](https://github.com/Post2Drive/Agora/actions/runs/44926109220)) passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. Decision lifecycle/outcome append wiring is present via #74; protected gates are limited to the named principal entry points.
- **#74:** anchored decision lifecycle and outcome/review append wiring plus opt-in `require_anchored=True` gates on three Principal entry points; exact-head CI run 221 (`44928837108`) passed all four matrix jobs.
- **#75:** structural `AuditAppender` protocol used by decision/outcome lifecycle code; no change to optional `audit=None` behaviour. Exact-head CI run 224 (`44929428177`) passed all four matrix jobs.
- **#77:** five readiness documents refreshed and merged; exact-head documentation CI run 235 (`44931495436`) passed all four matrix jobs.
- **#78:** `principal_policy(principal, required_role)` binds a synthetic Principal to a policy callback; `enforce_policy(..., require_policy=True)` denies a missing policy. Exact-head CI run 233 (`44930549886`) passed all four matrix jobs.
- **#79:** `require_policy` was threaded through `ingest_csv()`, `materialize_instances()` and `build_scenario_input()`. At the #79 merge point the defaults remained `False`; merged #89 later changed the three public defaults to `True`. Exact-head CI run 236 (`44931670540`) passed all four jobs after a transient Windows 3.11 SQLite lock failure was rerun successfully.
- **#80:** `authorize_decision_approval_principal()` and `approve_as()` are principal-native. Exact-head CI run 239 (`44934473818`) passed all four matrix jobs.
- **#82/#97:** legacy role-string `approve()` was initially guarded by `AGORA_TEST_ONLY_LEGACY_APPROVE`; #97 removes that environment switch and leaves only the test-only `agora.protection.LEGACY_APPROVE_ENABLED` flag. Exact-head CI runs `44937162200` (#82) and `44958568446` (#97) passed all four matrix jobs.
- **#84:** `approve_as()` ignores caller-supplied policy resource data and derives its PDP resource from stored decision scope plus fixed baseline sensitivity `internal`; precise `AnchorRequiredError`/unchanged-state coverage was added. Exact-head CI run `44939812441` passed all four matrix jobs.
- **#85:** ChatGPT documentation refresh and operator run-record field map merged; exact-head CI run `44945012741` passed all four jobs.
- **#86:** outcome `_as` wrappers ignore caller resource data; exact-head CI run `44942485500` passed all four jobs.
- **#88:** guided synthetic `agora pilot --workdir` entry point merged; exact-head CI run `44945307064` passed all four jobs. It does not persist the M2 run-record envelope or invoke the scenario-input adapter/engine.
- **#89:** default-True policy/anchor parameters merged at `87c7cc95`; exact-head CI run `44948055801` passed all four jobs. #96 removes public opt-out kwargs; #99 closes the direct-helper override and validates anchored denial writers.
- **#92:** public role-string `record_outcome()` / `review_outcome()` exports were retired; `record_outcome_as()` / `review_outcome_as()` are the public routes. Exact-head run `44950576945` passed all four matrix jobs.
- **#94:** `agora.cli` no longer imports `.sim.engine` at module scope; engine imports are lazy inside simulation handlers. Exact-head run `44955653075` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs.
- **#96:** removes caller-controlled policy/anchor opt-out kwargs from six protected public entry points; exact-head CI run `44956724553` passed 4/4.
- **#97:** removes the legacy approval env switch and the unanchored `audit=None` fallback; exact-head CI run `44958568446` passed 4/4.
- **#99:** removes direct `enforce_policy()` opt-out and requires `require_anchored()` for protected denial writes; exact-head CI run `44960946006` passed 4/4.
- **#100/#104:** read-only `agora reconcile` detector plus immutable source metadata, exact audit operation/resource-ID validation and partial-open cleanup; #104 exact-head CI run `44968039923` passed 4/4.
- **#101:** documentation-only refresh after #100; merged at main parent `f84d9804`, exact-head docs CI run `44965464662` passed 4/4.
- **#102/#106:** #102 adds `agora outcomes held --decisions <db>`; #106 maps connection-open SQLite errors to `STORE_UNREADABLE` / exit 2. Exact-head runs `44965953082` and `44970435296` passed all four matrix jobs; no marker propagation or source-dependency check.

**At the assessed main snapshot, ChatGPT's docs-only PR #105 is the only open PR.** Implementation PRs #94–#104 and #106 are merged; the current documentation refresh is based on main `112030a219e2d6f7278a46a95be2468634bf563a`.
- **#66:** Windows audit-log lock fix merged; exact-head CI run 198 passed all four matrix jobs.

Earlier merged foundations remain as recorded in the prior rung assessment: #23–#47 cover typed binding, ingestion/provenance, decisions, audit chain, PDP, approval, retention, report provenance and governed-pipeline tests.

## Open gaps to keep visible

1. **Simulation wiring:** scenario-input provenance is not connected to `agora/sim/**`. No edit to that path is authorised by this document; implementation requires Claude's written approval and a separate owner-approved execution step.
2. **Identity migration:** #80/#84 make `approve_as()` principal-native; #92 retires public role-string outcome exports; #96 removes public anchor opt-outs; #97 makes legacy `approve()` test-only. #99 closes direct policy-helper bypasses. Role-string PDP/permission compatibility APIs remain in source, and the synthetic fixture adapter is not production authentication. OIDC remains a later, separately approved integration.
3. **Outcome dependency review:** #53 records and reviews outcomes, and #102 lists disputed/unreviewed/invalid histories read-only. Source-change/erasure dependency markers, explicit dependency traversal and downstream propagation remain unimplemented.
4. **Audit anchoring:** #96 removes `require_anchored=False` kwargs from public Principal wrappers; #97 removes the `audit=None` unanchored fallback; #99 validates the supplied denial writer with `require_anchored()`. `local_sidecar` still cannot detect coordinated rollback of both stores; the Linux lock-removal mutation gap and low-level lifecycle audit-optional APIs remain.
5. **Cross-store consistency:** #100 adds the read-only decision lifecycle/audit detector; #104 validates source transition/status/actor/method/timestamp, audit operation and exact resource IDs, and closes partial-open connections. It still does not verify the anchor, cover outcomes/reviews, persist a queue or repair gaps. #102 is a separate held-outcome list, not outcome/audit reconciliation.
6. **Purpose and retention:** #54 closes the binding-hook propagation gap by accepting and forwarding declared purpose/retention. Callers must supply those values; do not claim that every call site or all data paths have been migrated.
7. **Enterprise controls:** OIDC, proven tenant isolation, external audit anchoring, operational backup/restore, incident response and fleet deployment are not complete.
8. **Pilot boundary:** #88 adds `agora pilot --workdir` for a local synthetic guided flow with per-step results and first-denial stop, no engine call. Its CSV/schema/binding are embedded in code, not a checked-in fixture set; it does not persist the M2 run record. No live pilot, real data, engine call or external action is authorised.

## Evidence and interpretation rules

- Earlier exact-head GitHub Actions evidence: #53 run 164, #54 run 165, #55 run 175, #56 run 173, #57 run 174, #58 run 172, #63 run 201 (`44917009154`), #66 run 198 (`44912719682`), #70 run 209 (`44923562288`) and #71 run 211 (`44926109220`).
- Newer exact-head runs: #77 run 235 (`44931495436`), #78 run 233 (`44930549886`), #79 run 236 (`44931670540`), #80 run 239 (`44934473818`), #82 run `44937162200`, #84 run `44939812441`, #85 run `44945012741`, #86 run `44942485500`, #88 run `44945307064` and merged #89 run `44948055801` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs.
- CI note: #79's first Windows 3.11 attempt failed with SQLite `database is locked`; the rerun passed. The cause is not confirmed and remains a concurrency-hardening item.
- The PR descriptions report clean-checkout test/mutation evidence for implementation slices #53 and #58. CI success is additional evidence, not a substitute for independent code review or owner approval.
- The governed-pipeline tests use synthetic fixtures only. They prove integration boundaries and fail-closed paths; they do not run `agora/sim/**` or establish predictive validity.
- Report provenance keeps exploratory outputs visibly simulated. `VALIDATED_PREDICTION_ENABLED` remains `False`.
- No simulated preference, action, conversion, or report is observed demand, a real sale, or validated prediction.
- No simulations, calibration, backtests, forecasts, study mutations, real data, credentials, drivers, network connectors, or external write-back are authorised by this status document.
- Review/merge gate: do not infer owner approval from green CI or a draft PR. ChatGPT must not request review, approve, mark ready, or merge without the owner's explicit `review` instruction.

## Process note

This assessment is a documentation snapshot of merged main at `112030a219e2d6f7278a46a95be2468634bf563a`; #94–#104 are merged. ChatGPT's draft docs-only PR #105 is the only open PR at this refresh.
