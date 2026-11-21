# Governed Synthetic Pilot — Milestone Readiness

**Status:** Evidence-based readiness assessment; not pilot or production authorisation  
**Assessment date:** 22 November 2026  
**Main base:** `6e2d76623fae909c062ee950781e9ed673416f3f`
**Scope:** Local synthetic-data governance pipeline only

## 1. Executive assessment

Main is at `6e2d76623fae909c062ee950781e9ed673416f3f` (22 November 2026). Merged PR #88 adds `agora pilot --workdir <new-empty-directory>` through `agora.cli.main()` and `agora.pilot.run_pilot()`: per-stage results, first-denial stop, explicit policy/anchor requirements inside the pilot, anchored audit verification and a synthetic-labelled report. Exact-head Actions run `44945307064` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. The pilot uses an in-module synthetic CSV/schema/binding, does not call `build_scenario_input()`, and does not persist the immutable operator run record required by the M2 field map.

The `agora pilot` command is now a single guided local entry point, but lower-level APIs on main still default `require_policy=False` and `require_anchored=False`. Legacy `approve()` remains runtime-enableable through `AGORA_TEST_ONLY_LEGACY_APPROVE=1`; public `record_outcome()` / `review_outcome()` remain role-string APIs and the Principal wrappers still delegate to them. The scenario-input package remains disconnected from the simulation engine. PR #89 proposes default-True policy/anchor parameters but is still open/draft, not on main; its exact-head Actions run `44948055801` passed all four jobs. The PR still accepts explicit `False` overrides and does not remove the unanchored `audit=None` policy-denial fallback.

The anchor remains a local JSONL sidecar with `local_sidecar` trust; coordinated rollback of both local stores is not detected, and the Linux lock-removal mutation gap remains. Main's data-boundary policy-denial path still permits `audit=None` and creates an unanchored project-local chain. PR #89 proposes default-on checks for the six named policy/Principal entry points, but it is not merged and does not make the data-boundary denial writer mandatory or remove explicit opt-outs.

Decision/audit reconciliation (#57) and outcome dependency review markers (#60) remain specifications only. The manual procedures being prepared are proposals for owner approval and rehearsal; they are not approved, tested or implemented features.

This assessment does not authorise simulation, calibration, backtest, forecast, study mutation, real data, credentials, network access, production use or external write-back.

## 2. Evidence basis and merged documentation

Assessment base: `6e2d76623fae909c062ee950781e9ed673416f3f`.

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
- #88 — adds the `agora pilot --workdir <new-empty-directory>` guided synthetic workflow, with per-stage results, first-denial stop, anchored audit verification and synthetic-labelled report; exact-head CI run `44945307064` passed all four jobs.

Open draft implementation PR (not counted as merged mainline evidence):
- #89 — proposes default-True policy/anchor parameters on six protected entry points. Exact head `543f3b49dbb5617e73102db876231e824358999d`; run `44948055801` passed all four jobs. It remains open/draft; explicit `False` overrides and unanchored policy-denial fallback remain review gaps.

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
| Ontology binding | **Available — Python API, partial governance** | Main still defaults `require_policy=False`; #89 proposes `True` but is open/draft and not merged. The policy callback can be Principal-bound with #78; `audit=None` remains an unanchored denial path. |
| Shared policy enforcement | **Available — partial** | On main, data-boundary `require_policy=False` remains the default. #89 proposes default-on at three callers but is unmerged; explicit opt-out and `audit=None` fallback remain. |
| Scenario-input package | **Available — Python API, disconnected** | #31/#41; exact import ID and provenance package, not consumed by `agora/sim/engine.py`. |
| Decision record/store and lifecycle | **Available — Python API** | #37/#42 and audit events #47. No single end-to-end command. |
| Principal-based approval and outcome wrappers | **Available — partial synthetic migration** | #80/#84 provide principal-native `approve_as()` with stored-decision-derived policy input; #82 still has a runtime-enableable legacy approval switch. #86 removes caller resource influence from outcome wrappers, but they still delegate to public role-string outcome APIs. |
| Audit hash chain | **Available — local chain only** | #38/#47; verifies its own chain but cannot independently detect a removed tail. |
| Anchored audit chain | **Available — local-sidecar API; partial protected mode** | Main still defaults `require_anchored=False` on the three Principal write paths. #89 proposes `True` but remains open/draft; explicit `False` is still accepted, and policy-denial `audit=None` still falls back to an unanchored chain. Trust remains `local_sidecar`. |
| Observed outcome recording/review | **Available — Python API, partial principal migration** | #86 ignores caller resource data, but Principal wrappers still delegate to public role-string `record_outcome()` / `review_outcome()`. Main's anchor default remains off; #89 proposes default-on but is unmerged. |
| Outcome dependency review markers | **Not implemented** | #60 is a specification only; no marker store/propagation worker. |
| Decision/audit reconciliation | **Not implemented** | #57 is a specification only; no queue, detector, worker or repair command. |
| Simulated-labelled report | **Available — separate exploratory/mock path** | Existing report CLI path; not connected to the scenario-input/decision/outcome workflow. |
| Single callable end-to-end pipeline | **Available — guided synthetic CLI, partial M1 evidence** | #88 adds `agora pilot --workdir <new-empty-directory>` with per-stage results, first-denial stop, explicit policy/anchor calls and a synthetic report. It does not persist the M2 run-record envelope or call `build_scenario_input()`/the engine. |
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
| #85 | Nine-document readiness refresh and operator run-record field map | Merged; exact-head CI run `44945012741` passed four jobs |
| #86 | Outcome `_as` resource derivation and anchored denial tests | Merged (`a0777c1`); four exact-head jobs green, run `44942485500` |
| #88 | Guided synthetic `agora pilot --workdir` entry point | Merged (`6e2d766`); four exact-head jobs green, run `44945307064` |
| #89 | Default-on policy/anchor parameter proposal | Open draft; exact-head CI run `44948055801` passed 4/4, but changes are not on main |

Main is `6e2d76623fae909c062ee950781e9ed673416f3f` (merge of #88). #85 and #86 are merged; #88 adds the guided pilot entry point. #89 is the only open implementation PR and remains draft despite four green exact-head CI jobs. There is no open ChatGPT docs PR at this assessment point; this refresh is proposed separately.

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
- [ ] Make protected policy and anchor requirements default-on at governed boundaries; main still has False defaults, while #89 proposes True defaults but is unmerged, permits explicit False overrides, and leaves policy-denial `audit=None` unanchored.
- [ ] Principal-first migration completed for all decision/PDP/shared policy enforcement and outcome call sites; #80 covers `approve_as()` and #82 test-gates legacy `approve()`, but #70 outcome wrappers still bridge to legacy functions.
- [ ] Decision/audit reconciliation implemented, or a documented manual recovery procedure approved and rehearsed. The manual procedure draft is not approval or evidence of a tested repair path.
- [ ] Outcome dependency markers implemented, or a documented manual hold/review procedure approved and rehearsed. The manual procedure draft is not an implemented marker/propagation system.
- [x] A callable CLI/API entry point runs the synthetic example end to end: PR #88 provides `agora pilot --workdir <new-empty-directory>` with import, bind, decision, principal approval, anchored audit, observed outcome/review and a synthetic-labelled report; it does not call the engine.
- [ ] Exact-head CI is green on final reviewed implementation heads; required mutation proofs and clean-checkout review evidence are recorded.
- [ ] Claude logs the exact milestone confirmation with main SHA, four green CI jobs, merged implementation PR numbers, exact end-to-end command/example, and all readiness rows Done except simulation wiring and owner-only items.
- [ ] Only after that confirmation, the owner separately approves any synthetic rehearsal. Scenario-input-to-engine wiring remains blocked until Claude's written approval and a separate owner approval.

Passing these gates means only that a scoped synthetic rehearsal may be considered. It does not establish predictive validity, real demand, sales performance, production security or permission for external actions.

## 6. Documentation status

This assessment is refreshed against main `6e2d76623fae909c062ee950781e9ed673416f3f`, after #85/#86/#88 merged; #89 remains an open draft and is not counted as implemented.

## 7. Permanent safety boundaries

- Keep `VALIDATED_PREDICTION_ENABLED=False`.
- Do not run simulations, calibration, backtests or forecasts as part of this documentation task.
- Do not mutate existing studies, study folders, NCC Park Square or E0_C0_D0.
- Do not use real data, personal/customer records, credentials, real drivers, network access or external write-back.
- Do not edit `agora/sim/**`; scenario-input-to-engine wiring remains blocked pending Claude's written approval and separate owner approval.
- A green CI run does not authorise a PR merge, ready-for-review transition or external action.
