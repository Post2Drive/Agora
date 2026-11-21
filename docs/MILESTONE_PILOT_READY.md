# Governed Synthetic Pilot — Milestone Readiness

**Status:** Evidence-based readiness assessment; not pilot or production authorisation  
**Assessment date:** 22 November 2026  
**Main base:** `a191b587876e5a26a73b716098c8f36eb561ea37`
**Scope:** Local synthetic-data governance pipeline only

## 1. Executive assessment

Main is `a191b587876e5a26a73b716098c8f36eb561ea37` after merged PR #97. #88 provides the guided local synthetic `agora pilot --workdir <new-empty-directory>` flow; #92 retires public role-string outcome exports; #94 makes pilot/data CLI dispatch engine-import-free; #96 removes caller-controlled policy/anchor opt-out kwargs from six public entry points; and #97 removes the legacy approval environment switch, defaults direct policy enforcement from `POLICY_REQUIRED=True`, and refuses the unanchored fallback when `audit=None`. It does not validate a caller-supplied writer: any object with `.append()` is accepted, so a plain `AuditChainStore` can still receive an unanchored denial. Exact-head CI for #94 (`44955653075`), #96 (`44956724553`) and #97 (`44958568446`) passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. One direct-helper gap remains on main: `enforce_policy(..., require_policy=False)` is still accepted and returns a no-op when policy is missing; tests prove the default omission path but not the explicit-False call. The pilot embeds its synthetic CSV/schema/binding, does not call `build_scenario_input()`, and does not persist the M2 run record.

The `agora pilot` command is a guided local entry point. #92 makes `record_outcome_as()` / `review_outcome_as()` the public outcome routes. #96 removes explicit policy/anchor opt-out kwargs from `ingest_csv()`, `materialize_instances()`, `build_scenario_input()`, `approve_as()`, `record_outcome_as()` and `review_outcome_as()`; those public entry points no longer accept caller-supplied False overrides. #97 removes the legacy `AGORA_TEST_ONLY_LEGACY_APPROVE` environment switch and makes direct `enforce_policy()` default to the protected module flag. However, the helper still accepts explicit `require_policy=False`, which bypasses a missing-policy denial; this remains a fail-closed gap. #94 lazy-loads `.sim.engine` only inside simulation-dependent CLI handlers; fresh-process coverage proves CLI import and `agora pilot --help` do not load the engine. Scenario-input remains disconnected from the engine.

The anchor remains a local JSONL sidecar with `local_sidecar` trust; coordinated rollback of both local stores is not detected, and the Linux lock-removal mutation gap remains. #96 removes public Principal-wrapper `require_anchored=False` opt-outs. #97 makes policy-denial `audit=None` fail closed rather than writing an unanchored chain, and removes the legacy approval environment switch. However, `enforce_policy()` does not validate a supplied writer with `require_anchored()`; a plain `AuditChainStore` is accepted. Private outcome helpers still have optional audit internals; the direct `enforce_policy(..., require_policy=False)` bypass also remains. Universal protected-mode enforcement is therefore incomplete.

Decision/audit reconciliation (#57) and outcome dependency review markers (#60) remain specifications only. The manual procedures being prepared are proposals for owner approval and rehearsal; they are not approved, tested or implemented features.

This assessment does not authorise simulation, calibration, backtest, forecast, study mutation, real data, credentials, network access, production use or external write-back.

## 2. Evidence basis and merged documentation

Assessment base: `a191b587876e5a26a73b716098c8f36eb561ea37`.

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
- #82 — initially gates legacy role-string `approve()` behind an environment switch; #97 removes that environment variable and moves test-only enablement to `agora.protection.LEGACY_APPROVE_ENABLED`.
- #84 — `approve_as()` ignores the caller-supplied resource and builds PDP inputs from the stored decision scope plus fixed baseline sensitivity `internal`; precise `AnchorRequiredError` tests replace the broad exception assertion. Exact-head CI run `44939812441` passed all four matrix jobs.
- #88 — adds the `agora pilot --workdir <new-empty-directory>` guided synthetic workflow, with per-stage results, first-denial stop, anchored audit verification and synthetic-labelled report; exact-head CI run `44945307064` passed all four jobs.

- #89 — default-on policy/anchor parameters on six protected entry points; merged at `87c7cc95b3e7c231f52dca4924d6fc433c698462`. Exact-head Actions run `44948055801` passed all four matrix jobs.
- #92 — retires public role-string `record_outcome()` / `review_outcome()` exports and routes public writes through Principal wrappers; merged before #94 (mainline merge `1fbde112`). Exact-head Actions run `44950576945` passed all four matrix jobs.
- #94 — lazy-loads `.sim.engine` only in engine-dependent CLI handlers; fresh-process tests cover `import agora.cli` and `agora pilot --help`. Exact-head Actions run `44955653075` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs.
- #96 — removes explicit `require_policy` / `require_anchored` opt-out kwargs from six protected public entry points; exact-head CI run `44956724553` passed 4/4.
- #97 — removes the legacy approval env switch, defaults direct policy enforcement from `POLICY_REQUIRED`, and refuses the local unanchored fallback when `audit=None`; a supplied plain `AuditChainStore` is still accepted and remains a gap. Exact-head CI run `44958568446` passed 4/4.
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
| Ontology binding | **Available — Python API, partial governance** | #96 removes the public `require_policy` opt-out kwarg from `materialize_instances()`; direct `enforce_policy()` defaults on after #97 but still accepts explicit `require_policy=False`, which bypasses a missing-policy denial. |
| Shared policy enforcement | **Available — partial** | #96 removes caller opt-out kwargs from the three protected data-boundary entry points; #97 defaults direct `enforce_policy()` to `POLICY_REQUIRED=True` and refuses the unanchored fallback when `audit=None`. The helper still accepts explicit `require_policy=False` and any supplied append-capable writer, including a plain `AuditChainStore`; both gaps need negative tests and mutation proofs. |
| Scenario-input package | **Available — Python API, disconnected** | #31/#41; exact import ID and provenance package, not consumed by `agora/sim/engine.py`. |
| Decision record/store and lifecycle | **Available — Python API** | #37/#42 and audit events #47. No single end-to-end command. |
| Principal-based approval and outcome wrappers | **Available — partial synthetic migration** | #96 removes public `require_anchored` opt-out kwargs; #97 removes the legacy approval env switch and leaves only the test-only module flag. Private internals remain implementation details. |
| Audit hash chain | **Available — local chain only** | #38/#47; verifies its own chain but cannot independently detect a removed tail. |
| Anchored audit chain | **Available — local-sidecar API; partial protected mode** | Public Principal wrappers no longer accept `require_anchored=False` after #96. #97 makes missing anchored writers fail closed for policy-denial events; trust remains `local_sidecar`, and private helpers retain optional audit internals. |
| Observed outcome recording/review | **Available — Principal public API; protected mode partial** | #92 retires public role-string exports; #96 removes public `require_anchored` opt-out kwargs. Private store helpers remain implementation details with optional audit arguments; the direct policy helper explicit-False bypass remains separate. |
| Outcome dependency review markers | **Not implemented** | #60 is a specification only; no marker store/propagation worker. |
| Decision/audit reconciliation | **Not implemented** | #57 is a specification only; no queue, detector, worker or repair command. |
| Simulated-labelled report | **Available — separate exploratory/mock path** | Existing report CLI path; not connected to the scenario-input/decision/outcome workflow. |
| Single callable end-to-end pipeline | **Available — guided synthetic CLI, partial M1 evidence** | #88 adds `agora pilot --workdir <new-empty-directory>` with per-stage results and first-denial stop; #94 keeps CLI pilot/data dispatch engine-import-free. It still does not persist the M2 run record or call `build_scenario_input()` / the engine. |
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
| #92 | Public role-string outcome API retirement | Merged; exact-head CI run `44950576945` passed 4/4 |
| #94 | Lazy-load simulation engine only in engine-dependent CLI handlers | Merged; exact-head CI run `44955653075` passed 4/4 |
| #95 | M1/M2 documentation refresh after #94 | Merged; exact-head docs CI run `44958100514` passed 4/4 |
| #96 | Remove public policy/anchor opt-out kwargs | Merged; exact-head CI run `44956724553` passed 4/4 |
| #97 | Remove legacy approval env switch and unanchored denial fallback; protect direct policy default | Merged; exact-head CI run `44958568446` passed 4/4 |

Main is `a191b587876e5a26a73b716098c8f36eb561ea37` (merge of #97). PRs #94–#97 are merged; no open PR existed at the start of this documentation refresh.

## 5. Required exit gates before the milestone can be declared reached

- [x] Principal migration plan, outcome-marker specification and pilot-readiness checklist merged (#59–#61).
- [x] Audit-anchor wiring plan merged (#64); it remains a plan, not implementation.
- [x] First synthetic principal approval slice merged (#58); remaining call-site migration is still open.
- [x] Local audit-anchor implementation merged (#63), with all four exact-head CI jobs green. Trust remains local-sidecar; the Linux lock-removal mutation proof did not detect the mutation.
- [x] Windows audit-log lock fix merged (#66), with all four exact-head CI jobs green.
- [x] Anchored writer factory and policy-denial/import/binding/scenario-input wiring merged (#71, Stages A/D), with all four exact-head CI jobs green.
- [x] Lifecycle/outcome append wiring added by #74; protected gates fail closed on the three named principal entry points. Universal protected-mode coverage remains open.
- [x] Principal-native decision approval path merged in #80: `approve_as()` uses the adapter-issued Principal and no caller role/subject parameter.
- [x] Legacy role-string `approve()` is disabled by default; #97 removes the environment-variable switch and confines enablement to the test-only module flag `LEGACY_APPROVE_ENABLED`, reset by test fixtures. Exact-head CI passed 4/4.
- [x] #84 closes the `approve_as()` caller-resource downgrade path by ignoring the supplied resource and using stored decision scope plus fixed baseline sensitivity; its precise anchor-error/no-state-change coverage passed exact-head CI.
- [ ] Make protected policy and anchor requirements non-bypassable at every governed boundary; #96 removes public opt-out kwargs and #97 defaults direct `enforce_policy()` on and removes the unanchored denial fallback, but the direct helper still accepts explicit `require_policy=False` and returns a no-op when policy is missing; it also accepts a supplied plain `AuditChainStore` without validating that it is anchored. Add negative tests and mutation proofs for both paths.
- [ ] Principal-first migration completed for all decision/PDP/shared policy enforcement and outcome call sites; public role-string outcome exports are retired and legacy approval is test-only, but the direct `enforce_policy(..., require_policy=False)` bypass and acceptance of a supplied plain `AuditChainStore` remain.
- [ ] Decision/audit reconciliation implemented, or a documented manual recovery procedure approved and rehearsed. The manual procedure draft is not approval or evidence of a tested repair path.
- [ ] Outcome dependency markers implemented, or a documented manual hold/review procedure approved and rehearsed. The manual procedure draft is not an implemented marker/propagation system.
- [x] A callable CLI/API entry point runs the synthetic example end to end: PR #88 provides `agora pilot --workdir <new-empty-directory>` with import, bind, decision, principal approval, anchored audit, observed outcome/review and a synthetic-labelled report; it does not call the engine.
- [x] The CLI module no longer imports the simulation engine for pilot/data dispatch; #94 lazy-loads it only in engine-dependent handlers and passes exact-head CI 4/4. Fresh-process coverage is for `--help`, not a complete `--workdir` invocation.
- [ ] Exact-head CI is green on final reviewed implementation heads; required mutation proofs and clean-checkout review evidence are recorded.
- [ ] Claude logs the exact milestone confirmation with main SHA, four green CI jobs, merged implementation PR numbers, exact end-to-end command/example, and all readiness rows Done except simulation wiring and owner-only items.
- [ ] Only after that confirmation, the owner separately approves any synthetic rehearsal. Scenario-input-to-engine wiring remains blocked until Claude's written approval and a separate owner approval.

Passing these gates means only that a scoped synthetic rehearsal may be considered. It does not establish predictive validity, real demand, sales performance, production security or permission for external actions.

## 6. Documentation status

This assessment is refreshed against main `a191b587876e5a26a73b716098c8f36eb561ea37` after #97 merged. PRs #94–#97 have green exact-head CI; no open PR existed at the start of this docs refresh.

## 7. Permanent safety boundaries

- Keep `VALIDATED_PREDICTION_ENABLED=False`.
- Do not run simulations, calibration, backtests or forecasts as part of this documentation task.
- Do not mutate existing studies, study folders, NCC Park Square or E0_C0_D0.
- Do not use real data, personal/customer records, credentials, real drivers, network access or external write-back.
- Do not edit `agora/sim/**`; scenario-input-to-engine wiring remains blocked pending Claude's written approval and separate owner approval.
- A green CI run does not authorise a PR merge, ready-for-review transition or external action.
