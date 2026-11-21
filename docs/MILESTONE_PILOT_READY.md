# Governed Synthetic Pilot — Milestone Readiness

**Status:** Evidence-based readiness assessment; not pilot or production authorisation  
**Assessment date:** 22 November 2026  
**Main base:** `7afa1414acd9c2e68361faab81a5d246597a5919`
**Scope:** Local synthetic-data governance pipeline only

## 1. Executive assessment

Main is at `7afa1414acd9c2e68361faab81a5d246597a5919` (22 November 2026). It includes #78's Principal-bound `principal_policy()` helper, #79's opt-in `require_policy` threading, #80's principal-native `approve_as()`, #82's default-deny legacy role-string approval gate, and #84's stored-decision-only approval policy resource. #84 closes the caller-resource downgrade finding for `approve_as()`. Principal migration remains incomplete: `require_policy` and `require_anchored` still default to `False`, outcome wrappers still delegate to legacy role-string functions, and the approval compatibility switch remains runtime-enableable by environment variable.

Main still does not provide one entry point that orchestrates import → bind → decision → principal approval → anchored audit → observed outcome/review → simulated-labelled report. CSV import is a CLI; binding, scenario-input construction, decision approval and outcomes are separate APIs; the scenario-input package is not wired into the simulation engine. `approve_as()` is principal-native (#80) and now ignores caller-supplied policy resource fields (#84); legacy `approve()` fails closed unless `AGORA_TEST_ONLY_LEGACY_APPROVE=1` (#82), while #70 outcome wrappers still bridge to legacy role-string APIs. The #79 `require_policy` option remains opt-in and defaults to `False`.

The anchor implementation provides a local JSONL sidecar and fail-closed append wrapper. #71 adds `open_anchored_audit()` and optional writer threading through policy denial, CSV import, ontology materialization and scenario-input construction. #74 wires decision lifecycle and outcome/review append boundaries and adds opt-in `require_anchored=True` gates on three principal entry points. #84 adds a precise `AnchorRequiredError` test for `approve_as()` when an anchored writer is absent or a plain chain is supplied; the public default is still `require_anchored=False`. Trust remains `local_sidecar`: coordinated rollback of both local stores is not detected. The Linux lock-removal mutation gap remains.

Decision/audit reconciliation (#57) and outcome dependency review markers (#60) remain specifications only. The manual procedures being prepared are proposals for owner approval and rehearsal; they are not approved, tested or implemented features.

This assessment does not authorise simulation, calibration, backtest, forecast, study mutation, real data, credentials, network access, production use or external write-back.

## 2. Evidence basis and merged documentation

Assessment base: `7afa1414acd9c2e68361faab81a5d246597a5919`.

Confirmed merged documentation PRs:
- #59 — principal call-site migration plan.
- #60 — outcome dependency review-marker specification.
- #61 — pilot-readiness checklist.
- #62 — rung-status refresh.
- #64 — audit-anchor wiring and recovery plan.
- #65 — callable-pipeline capability guide.
- #77 — five-document readiness refresh, merged after rebasing on #78; exact-head docs CI run 235 passed all four matrix jobs.
- #83 — M1/M2 readiness refresh, synthetic fixture specification and provisional operator runbook; merged after exact-head docs CI passed all four matrix jobs.

Confirmed merged implementation PRs:
- #53 — append-only observed outcomes and review API.
- #54 — binding purpose/retention propagation into the policy hook.
- #58 — first synthetic principal approval slice; remaining call sites are not migrated.
- #63 — local-sidecar audit-anchor primitive; #71 adds the writer factory and policy-denial/data-boundary wiring (Stages A/D); #74/#75 add lifecycle/outcome append wiring and the structural `AuditAppender` contract. Protected gates remain opt-in.
- #74 — anchored decision lifecycle and outcome/review append wiring, with opt-in anchor gates on three principal entry points.
- #75 — structural `AuditAppender` protocol for decision/outcome audit writers; no change to optional `audit=None` behaviour.
- #66 — Windows audit-log lock fix.
- #78 — `principal_policy(principal, required_role)` and `enforce_policy(..., require_policy=True)`; exact-head CI run 233 (`44930549886`) passed all four matrix jobs.
- #79 — opt-in `require_policy` on `ingest_csv()`, `materialize_instances()` and `build_scenario_input()`; exact-head CI run 236 (`44931670540`) passed all four matrix jobs after one Windows 3.11 database-lock failure was rerun successfully.
- #80 — principal-native `authorize_decision_approval_principal()` and `approve_as()`; exact-head CI run 239 (`44934473818`) passed all four matrix jobs.
- #82 — legacy role-string `approve()` fails closed unless `AGORA_TEST_ONLY_LEGACY_APPROVE=1`; exact-head CI run `44937162200` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs.
- #84 — `approve_as()` ignores the caller-supplied resource and builds PDP inputs from the stored decision scope plus fixed baseline sensitivity `internal`; precise `AnchorRequiredError` tests replace the broad exception assertion. Exact-head CI run `44939812441` passed all four matrix jobs.

Earlier merged design/runbook documents remain:
- #51 identity adapter specification; #52 audit-anchor specification.
- #55 deployment-hardening specification; #56 synthetic pilot runbook; #57 decision/audit reconciliation specification.

Exact-head GitHub Actions evidence:
- #63 head `ef1f0ee430598c018a3cccd2ba2627a733f123f5`, run [44917009154](https://github.com/Post2Drive/Agora/actions/runs/44917009154): all four Ubuntu/Windows × Python 3.11/3.12 jobs passed.
- #66 head `6e0b483d628e5b4317e2cd3296a0bf0604d403f6`, run [44912719682](https://github.com/Post2Drive/Agora/actions/runs/44912719682): all four matrix jobs passed.
- #74 head `ca92a206219bb7da6de4b4f50a157b74ac6103c7`, run [44928837108](https://github.com/Post2Drive/Agora/actions/runs/44928837108): all four matrix jobs passed.
- #75 head `ae1b50577047eb7ef1435bcf231037f566eed77d`, run [44929428177](https://github.com/Post2Drive/Agora/actions/runs/44929428177): all four matrix jobs passed.
- #65 head `039beae59e0d3478d5412260d34a1f83618571e8`, run [44910310968](https://github.com/Post2Drive/Agora/actions/runs/44910310968): all four matrix jobs passed.

These are exact-head GitHub Actions results, not local test runs. PR #77's documentation CI run 235 also passed all four matrix jobs. The #79 Windows 3.11 first attempt had a transient SQLite `database is locked` failure; its rerun passed, and the cause remains a hardening item.

## 3. Current capability assessment

| Capability | Status | Evidence and limitation |
|---|---|---|
| Local structured CSV snapshot import | **Available — CLI** | #28 and later provenance/policy work. Local only; no external connectors/write-back. |
| Ontology binding | **Available — Python API, partial governance** | #31/#43/#54; #79 adds opt-in `require_policy=True`, but the default remains `False` and `policy=None` is still a no-op on legacy calls. The callback can be principal-bound with #78's `principal_policy()`, but a principal is not required by default. |
| Shared policy enforcement | **Available — partial** | #78 adds principal-bound `principal_policy()` and a missing-policy denial when `require_policy=True`; #79 threads that flag through three data boundaries. `require_policy=False` remains the default, and `audit=None` uses the legacy unanchored project-local chain. |
| Scenario-input package | **Available — Python API, disconnected** | #31/#41; exact import ID and provenance package, not consumed by `agora/sim/engine.py`. |
| Decision record/store and lifecycle | **Available — Python API** | #37/#42 and audit events #47. No single end-to-end command. |
| Principal-based approval and outcome wrappers | **Available — partial synthetic migration** | #80 makes `approve_as()` use the principal-native gate; #84 ignores caller-supplied resource policy fields and fixes baseline sensitivity to `internal`. Legacy `approve()` still exists and can be re-enabled by `AGORA_TEST_ONLY_LEGACY_APPROVE=1`; #70 outcome wrappers still delegate to legacy role-string APIs. No OIDC/production authentication. |
| Audit hash chain | **Available — local chain only** | #38/#47; verifies its own chain but cannot independently detect a removed tail. |
| Anchored audit chain | **Available — local-sidecar API; partial wiring** | #63 local-sidecar writer; #71 policy/data-boundary injection; #74 lifecycle/outcome append wiring; #75 structural `AuditAppender` protocol; opt-in `require_anchored=True` on three principal entry points. The anchor gate remains opt-in; legacy optional-audit paths remain. Trust remains `local_sidecar`. |
| Observed outcome recording/review | **Available — Python API, partial principal migration** | #53 append-only store; #70 principal wrappers require operator/reviewer but still delegate to legacy role-string functions; #74 adds opt-in anchor gates. The underlying API and audit writer remain optional; no CLI. |
| Outcome dependency review markers | **Not implemented** | #60 is a specification only; no marker store/propagation worker. |
| Decision/audit reconciliation | **Not implemented** | #57 is a specification only; no queue, detector, worker or repair command. |
| Simulated-labelled report | **Available — separate exploratory/mock path** | Existing report CLI path; not connected to the scenario-input/decision/outcome workflow. |
| Single callable end-to-end pipeline | **Not implemented** | No orchestrator joins all required stages with principal-first authorization and anchored audit. |
| Integrated pilot readiness | **Not ready** | Implementation, wiring, operational and approval gates remain open. |

## 4. Pull request status snapshot

| PR | Scope | State at this assessment |
|---|---|---|
| #59 | Principal migration plan | Merged |
| #60 | Outcome dependency review-marker specification | Merged |
| #61 | Pilot-readiness checklist | Merged |
| #62 | Rung-status refresh | Merged |
| #63 | Local audit-anchor implementation | Merged |
| #64 | Audit-anchor wiring plan | Merged |
| #65 | Pipeline capability guide and readiness refresh | Merged |
| #66 | Windows audit-log lock fix | Merged |
| #67–#69 | Readiness and manual-procedure documentation | Merged |
| #70 | Principal-first outcome record/review bridge | Merged |
| #71 | Anchored writer factory and policy-denial wiring (Stages A/D) | Merged |
| #72 | Earlier documentation refresh based on pre-#71 main | Closed; superseded |
| #74 | Anchored lifecycle/outcome append wiring and opt-in principal anchor gates | Merged |
| #75 | Structural `AuditAppender` protocol for lifecycle/outcome writers | Merged |
| #77 | Five-document readiness refresh | Merged |
| #78 | Principal-bound policy helper and missing-policy gate | Merged |
| #79 | Opt-in policy requirement on import/binding/scenario-input | Merged |
| #80 | Principal-native decision approval gate | Merged |
| #83 | M1/M2 readiness refresh, fixture specification and provisional operator runbook | Merged |
| #84 | Approval policy-resource derivation and precise anchor-error regression tests | Merged |
| #85 | Nine-document readiness refresh and operator run-record field map | Open draft; exact-head CI run `44942480339` is in progress |
| #86 | Outcome `_as` resource derivation and anchored denial tests | Open draft; exact-head CI run `44942485500` is in progress |

Main is `7afa1414acd9c2e68361faab81a5d246597a5919` (merge of #84). PRs #77, #81 and #83 (documentation refreshes), #78 (Principal-bound policy helper), #79 (opt-in data-boundary policy gate), #80 (principal-native approval), #82 (default-deny legacy approval gate) and #84 (stored-decision-only approval policy resource) are merged. Open PRs #85 (ChatGPT docs) and #86 (Claude outcome `_as` slice 3d) are drafts and unmerged; their exact-head four-job CI runs are in progress. #72 and #76 remain closed superseded docs drafts.

## 5. Required exit gates before the milestone can be declared reached

- [x] Principal migration plan, outcome-marker specification and pilot-readiness checklist merged (#59–#61).
- [x] Audit-anchor wiring plan merged (#64); it remains a plan, not implementation.
- [x] First synthetic principal approval slice merged (#58); remaining call-site migration is still open.
- [x] Local audit-anchor implementation merged (#63), with all four exact-head CI jobs green. Trust remains local-sidecar; the Linux lock-removal mutation proof did not detect the mutation.
- [x] Windows audit-log lock fix merged (#66), with all four exact-head CI jobs green.
- [x] Anchored writer factory and policy-denial/import/binding/scenario-input wiring merged (#71, Stages A/D), with all four exact-head CI jobs green.
- [x] Lifecycle/outcome append wiring added by #74; protected gates fail closed on the three named principal entry points. Universal protected-mode coverage remains open.
- [x] Principal-native decision approval path merged in #80: `approve_as()` uses the adapter-issued Principal and no caller role/subject parameter.
- [x] Legacy role-string `approve()` fails closed by default behind `AGORA_TEST_ONLY_LEGACY_APPROVE=1` (#82); this is still an environment-variable escape hatch, not a structural test-only boundary, so remove it after test callers migrate.
- [x] #84 closes the `approve_as()` caller-resource downgrade path by ignoring the supplied resource and using stored decision scope plus fixed baseline sensitivity; its precise anchor-error/no-state-change coverage passed exact-head CI.
- [ ] Make protected policy and anchor requirements default-on at governed boundaries; #79's `require_policy` and #74/#80's `require_anchored` remain opt-in, and legacy `audit=None` paths remain.
- [ ] Principal-first migration completed for all decision/PDP/shared policy enforcement and outcome call sites; #80 covers `approve_as()` and #82 test-gates legacy `approve()`, but #70 outcome wrappers still bridge to legacy functions.
- [ ] Decision/audit reconciliation implemented, or a documented manual recovery procedure approved and rehearsed. The manual procedure draft is not approval or evidence of a tested repair path.
- [ ] Outcome dependency markers implemented, or a documented manual hold/review procedure approved and rehearsed. The manual procedure draft is not an implemented marker/propagation system.
- [ ] A callable CLI/API entry point runs the synthetic example end to end: import, bind, decision, principal approval, anchored audit, observed outcome/review and simulated-labelled report, using exact immutable IDs.
- [ ] Exact-head CI is green on final reviewed implementation heads; required mutation proofs and clean-checkout review evidence are recorded.
- [ ] Claude logs the exact milestone confirmation with main SHA, four green CI jobs, merged implementation PR numbers, exact end-to-end command/example, and all readiness rows Done except simulation wiring and owner-only items.
- [ ] Only after that confirmation, the owner separately approves any synthetic rehearsal. Scenario-input-to-engine wiring remains blocked until Claude's written approval and a separate owner approval.

Passing these gates means only that a scoped synthetic rehearsal may be considered. It does not establish predictive validity, real demand, sales performance, production security or permission for external actions.

## 6. Documentation status

This assessment is refreshed against main `7afa1414acd9c2e68361faab81a5d246597a5919`, after #78, #79, #80, #82, #83 and #84 merged.

## 7. Permanent safety boundaries

- Keep `VALIDATED_PREDICTION_ENABLED=False`.
- Do not run simulations, calibration, backtests or forecasts as part of this documentation task.
- Do not mutate existing studies, study folders, NCC Park Square or E0_C0_D0.
- Do not use real data, personal/customer records, credentials, real drivers, network access or external write-back.
- Do not edit `agora/sim/**`; scenario-input-to-engine wiring remains blocked pending Claude's written approval and separate owner approval.
- A green CI run does not authorise a PR merge, ready-for-review transition or external action.
