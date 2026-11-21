# Governed Synthetic Pilot — Milestone Readiness

**Status:** Evidence-based readiness assessment; not pilot or production authorisation  
**Assessment date:** 22 November 2026  
**Main base:** `1fbde112d00fc4fc579e9be6385104d655a9ced4`
**Scope:** Local synthetic-data governance pipeline only

## 1. Executive assessment

Main is `1fbde112d00fc4fc579e9be6385104d655a9ced4` after merged #92. #88 provides the guided local synthetic `agora pilot --workdir <new-empty-directory>` flow; #89 sets default-True policy/anchor flags on six protected APIs; #92 retires public role-string `record_outcome()` / `review_outcome()` and leaves the Principal wrappers as the only public outcome routes. Exact-head Actions run `44950576945` for #92 passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. Explicit `False` bypasses, direct `enforce_policy()` default-off, the unanchored `audit=None` policy-denial fallback and the runtime legacy-approval switch remain. The pilot embeds its synthetic CSV/schema/binding, does not call `build_scenario_input()`, and does not persist the M2 run record.

The `agora pilot` command is a guided local entry point. #92 retires the public role-string outcome exports: `record_outcome_as()` / `review_outcome_as()` are the public routes and derive actor identity from Principal. Remaining protected-mode gaps are explicit `require_policy=False` / `require_anchored=False`, direct `enforce_policy()` defaulting to `False`, unanchored policy-denial logging when `audit=None`, and legacy `approve()` runtime-enableable through `AGORA_TEST_ONLY_LEGACY_APPROVE=1`. `agora.cli` still imports `.sim.engine` at module scope before dispatch; the `agora.pilot` module itself does not call the engine. Scenario-input remains disconnected from the engine.

The anchor remains a local JSONL sidecar with `local_sidecar` trust; coordinated rollback of both local stores is not detected, and the Linux lock-removal mutation gap remains. #89 makes the three Principal write wrappers default to anchored audit, but explicit `require_anchored=False` remains possible. Policy-denial `audit=None` still writes to an unanchored local chain. #92 retires public role-string outcome exports, although private outcome helpers still have optional audit internals. Universal protected-mode enforcement is therefore incomplete.

Decision/audit reconciliation (#57) and outcome dependency review markers (#60) remain specifications only. The manual procedures being prepared are proposals for owner approval and rehearsal; they are not approved, tested or implemented features.

This assessment does not authorise simulation, calibration, backtest, forecast, study mutation, real data, credentials, network access, production use or external write-back.

## 2. Evidence basis and merged documentation

Assessment base: `1fbde112d00fc4fc579e9be6385104d655a9ced4`.

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

- #89 — default-on policy/anchor parameters on six protected entry points; merged at `1fbde112d00fc4fc579e9be6385104d655a9ced4`. Exact-head Actions run `44948055801` passed all four matrix jobs.
- #92 — retires public role-string `record_outcome()` / `review_outcome()` exports and routes public writes through Principal wrappers; merged as `1fbde112d00fc4fc579e9be6385104d655a9ced4`. Exact-head Actions run `44950576945` passed all four matrix jobs.
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
| Ontology binding | **Available — Python API, partial governance** | Main defaults `require_policy=True` after #89. Explicit `False` remains accepted; policy-denial `audit=None` still uses an unanchored local chain. |
| Shared policy enforcement | **Available — partial** | The three data-boundary callers now default `require_policy=True`; direct `enforce_policy()` still defaults off, and `audit=None` fallback remains unanchored. |
| Scenario-input package | **Available — Python API, disconnected** | #31/#41; exact import ID and provenance package, not consumed by `agora/sim/engine.py`. |
| Decision record/store and lifecycle | **Available — Python API** | #37/#42 and audit events #47. No single end-to-end command. |
| Principal-based approval and outcome wrappers | **Available — partial synthetic migration** | #80/#84 provide principal-native `approve_as()`; #89 defaults its anchor check on. #82 retains the runtime-enableable legacy approval switch. #92 retires public role-string outcome exports; explicit anchor opt-out remains. |
| Audit hash chain | **Available — local chain only** | #38/#47; verifies its own chain but cannot independently detect a removed tail. |
| Anchored audit chain | **Available — local-sidecar API; partial protected mode** | #89 defaults anchor checks on for three Principal write wrappers. Explicit `False`, private optional-audit internals and unanchored policy-denial `audit=None` remain. Trust remains `local_sidecar`. |
| Observed outcome recording/review | **Available — Principal public API; protected mode partial** | #92 removes public role-string exports; `record_outcome_as()` / `review_outcome_as()` are the public routes. Explicit `require_anchored=False` still bypasses the wrapper gate, and the private store helpers accept optional audit internally. |
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
| #88 | Guided synthetic `agora pilot --workdir` entry point | Merged (`6e2d766`); exact-head CI run `44945307064` passed 4/4 |
| #89 | Default-on policy/anchor parameters on six protected entry points | Merged (`87c7cc95`); exact-head CI run `44948055801` passed 4/4 |
| #91 | Documentation refresh after #88/#89 | Merged; exact-head CI run `44949947675` passed 4/4 |

Main is `1fbde112d00fc4fc579e9be6385104d655a9ced4` (merge of #92). #85/#86/#88/#89/#91/#92 are merged; no ChatGPT-owned docs PR was open at the start of this refresh.

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
- [ ] Make protected policy and anchor requirements non-bypassable at governed boundaries; #89 supplies True defaults on six APIs, but explicit False overrides, direct `enforce_policy()` default-off and unanchored policy-denial `audit=None` remain, so universal protected mode is not complete.
- [ ] Principal-first migration completed for all decision/PDP/shared policy enforcement and outcome call sites; #92 retires the public role-string outcome exports, but legacy `approve()` remains runtime-enableable and the PDP/data-boundary bypasses remain.
- [ ] Decision/audit reconciliation implemented, or a documented manual recovery procedure approved and rehearsed. The manual procedure draft is not approval or evidence of a tested repair path.
- [ ] Outcome dependency markers implemented, or a documented manual hold/review procedure approved and rehearsed. The manual procedure draft is not an implemented marker/propagation system.
- [x] A callable CLI/API entry point runs the synthetic example end to end: PR #88 provides `agora pilot --workdir <new-empty-directory>` with import, bind, decision, principal approval, anchored audit, observed outcome/review and a synthetic-labelled report; it does not call the engine.
- [ ] Exact-head CI is green on final reviewed implementation heads; required mutation proofs and clean-checkout review evidence are recorded.
- [ ] Claude logs the exact milestone confirmation with main SHA, four green CI jobs, merged implementation PR numbers, exact end-to-end command/example, and all readiness rows Done except simulation wiring and owner-only items.
- [ ] Only after that confirmation, the owner separately approves any synthetic rehearsal. Scenario-input-to-engine wiring remains blocked until Claude's written approval and a separate owner approval.

Passing these gates means only that a scoped synthetic rehearsal may be considered. It does not establish predictive validity, real demand, sales performance, production security or permission for external actions.

## 6. Documentation status

This assessment is refreshed against main `1fbde112d00fc4fc579e9be6385104d655a9ced4`, after #91 docs and #92 outcome-API retirement merged. No ChatGPT docs PR is currently open.

## 7. Permanent safety boundaries

- Keep `VALIDATED_PREDICTION_ENABLED=False`.
- Do not run simulations, calibration, backtests or forecasts as part of this documentation task.
- Do not mutate existing studies, study folders, NCC Park Square or E0_C0_D0.
- Do not use real data, personal/customer records, credentials, real drivers, network access or external write-back.
- Do not edit `agora/sim/**`; scenario-input-to-engine wiring remains blocked pending Claude's written approval and separate owner approval.
- A green CI run does not authorise a PR merge, ready-for-review transition or external action.
