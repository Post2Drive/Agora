# Governed Synthetic Pilot — Milestone Readiness

**Status:** Evidence-based readiness assessment; not pilot or production authorisation  
**Assessment date:** 22 November 2026  
**Main base:** `1ea27efb1dae9993a825a9a1a5388e0f5f82a20b`
**Scope:** Local synthetic-data governance pipeline only

## 1. Executive assessment

Main is `1ea27efb1dae9993a825a9a1a5388e0f5f82a20b` after merged PRs #97, #99, #100, #101, #102, #103 and #104. #99 removes the direct policy-helper opt-out and requires an anchored writer for protected denial events (exact-head run 44960946006, 4/4). #100 adds read-only decision lifecycle/audit reconciliation (run 44963254416, 4/4); #104 hardens it by checking transition/status/actor/method/timestamp against the immutable decision payload, requiring the expected audit operation and exact resource IDs, and closing acquired read-only connections on partial open (exact-head run 44968039923, 4/4). #102 adds a separate read-only held-outcome listing (run 44965953082, 4/4). Neither command verifies the sidecar anchor or provides a reviewed queue/repair workflow. The pilot still embeds its synthetic CSV/schema/binding, does not call `build_scenario_input()`, and does not persist the M2 run record.

The `agora pilot` command is a guided local entry point. #92 retires public role-string outcome exports; #94 keeps pilot/data dispatch engine-import-free; #96 removes public policy/anchor opt-out kwargs; #97 removes the legacy approval environment switch; and #99 closes the direct policy-helper opt-out and requires an anchored writer for protected denial writes. #100 adds only a read-only decision-lifecycle reconciliation detector; #102 adds `agora outcomes held --decisions <db>` for disputed, unreviewed or invalid review histories and orphan review rows. The held list is not a dependency marker or propagation system. Scenario-input remains disconnected from the engine.

The anchor remains a local JSONL sidecar with `local_sidecar` trust; coordinated rollback of both local stores is not detected, and the Linux lock-removal mutation gap remains. #96 removes public Principal-wrapper anchor opt-outs, #97 removes the legacy approval environment switch, and #99 closes the direct `enforce_policy()` bypass and rejects missing/plain denial writers when anchoring is required. Decision lifecycle methods still accept optional audit parameters in their low-level APIs, and private outcome helpers retain optional audit internals; the local-sidecar trust limitation is unchanged.

#100 implements the read-only decision lifecycle/approval detector; #104 adds immutable source-transition validation, exact audit operation/resource-ID checks and safe partial-open connection cleanup. The detector still does not verify the sidecar anchor, reconcile outcome/review rows, persist a queue or repair gaps. #102 adds a read-only held-outcome list, but no marker store, source-dependency propagation or automatic downstream flagging. The manual recovery procedure is not approved or rehearsed.

This assessment does not authorise simulation, calibration, backtest, forecast, study mutation, real data, credentials, network access, production use or external write-back.

## 2. Evidence basis and merged documentation

Assessment base: `1ea27efb1dae9993a825a9a1a5388e0f5f82a20b`.

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
- #97 — removes the legacy approval environment switch, defaults direct policy enforcement from `POLICY_REQUIRED=True`, and refuses the unanchored fallback when `audit=None`; exact-head CI run `44958568446` passed 4/4.
- #99 — removes the direct `require_policy` override and requires an anchored writer for protected policy-denial events; exact-head CI run `44960946006` passed 4/4.
- #100 — adds the read-only decision/audit reconciliation detector; exact-head CI run `44963254416` passed 4/4.
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
| Ontology binding | **Available — Python API, protected boundary** | #96 removes the public `require_policy` opt-out kwarg from `materialize_instances()`; #99 removes the direct helper override and requires an anchored writer for protected denial events. Principal/identity migration remains a separate concern. |
| Shared policy enforcement | **Available — protected by default** | #96 removes public caller opt-outs; #97 removes the unanchored `audit=None` fallback; #99 removes the direct `require_policy` override and validates denial writers with `require_anchored()`. Test-only protection flags remain confined to the test fixture. |
| Scenario-input package | **Available — Python API, disconnected** | #31/#41; exact import ID and provenance package, not consumed by `agora/sim/engine.py`. |
| Decision record/store and lifecycle | **Available — Python API** | #37/#42 and audit events #47. No single end-to-end command. |
| Principal-based approval and outcome wrappers | **Available — partial synthetic migration** | #96 removes public `require_anchored` opt-out kwargs; #97 removes the legacy approval env switch and leaves only the test-only module flag. Private internals remain implementation details. |
| Audit hash chain | **Available — local chain only** | #38/#47; verifies its own chain but cannot independently detect a removed tail. |
| Anchored audit chain | **Available — local-sidecar API; lifecycle writer requirement remains partial** | #99 requires an anchored writer for protected policy-denial events. Low-level decision lifecycle methods still accept optional audit arguments; the anchor remains `local_sidecar`, and coordinated rollback plus the Linux lock-removal mutation gap remain limitations. |
| Observed outcome recording/review | **Available — Principal public routes; private internals remain** | #92 retires public role-string exports and #96 removes public anchor opt-outs. #102 adds a separate read-only held-outcome list; it does not create dependency markers or change outcomes. Private helpers still have optional audit internals. |
| Outcome dependency review markers | **Not implemented** | #60 remains a design specification; #102 only lists disputed/unreviewed/invalid outcomes and orphan review rows. No marker store, dependency graph, propagation or marker lifecycle exists. |
| Decision/audit reconciliation | **Partial — hardened read-only detector** | #100 adds `agora reconcile` for decision lifecycle/approval rows; #104 validates source transition/status/actor/method/timestamp against the immutable payload, validates audit operation and exact resource IDs, and closes connections safely on partial open (run `44968039923`, 4/4). It still has no sidecar-anchor verification, queue, repair or outcome/review reconciliation. #102's held list is separate. |
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
| #97 | Remove legacy approval env switch and unanchored denial fallback | Merged; exact-head CI run `44958568446` passed 4/4 |
| #99 | Remove direct policy-helper override and require anchored denial writer | Merged; exact-head CI run `44960946006` passed 4/4 |
| #100 | Read-only decision/audit reconciliation detector | Merged; exact-head CI run `44963254416` passed 4/4 |
| #101 | M1/M2 documentation refresh after #100 | Merged; exact-head CI run `44965464662` passed 4/4 |
| #102 | Read-only `agora outcomes held` listing | Merged; exact-head CI run `44965953082` passed 4/4 |

Main is `1ea27efb1dae9993a825a9a1a5388e0f5f82a20b` after merged PRs #97, #99, #100, #101, #102, #103 and #104. #99 removes the direct policy-helper opt-out and requires an anchored writer for protected denial events (exact-head run 44960946006, 4/4). #100 adds read-only decision lifecycle/audit reconciliation (run 44963254416, 4/4); #104 hardens it by checking transition/status/actor/method/timestamp against the immutable decision payload, requiring the expected audit operation and exact resource IDs, and closing acquired read-only connections on partial open (exact-head run 44968039923, 4/4). #102 adds a separate read-only held-outcome listing (run 44965953082, 4/4). Neither command verifies the sidecar anchor or provides a reviewed queue/repair workflow. The pilot still embeds its synthetic CSV/schema/binding, does not call `build_scenario_input()`, and does not persist the M2 run record.

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
- [ ] Make policy and anchor requirements non-bypassable at every governed boundary. #99 closes the direct `enforce_policy()` override and enforces an anchored denial writer, but low-level decision lifecycle methods still accept optional audit parameters and private outcome helpers retain optional audit internals. Add protected-service call-site proofs and negative tests/mutation proofs for missing/plain writers across all lifecycle transitions.
- [ ] Principal-first migration completed for all decision/PDP/shared policy enforcement and outcome call sites; public outcome-role exports are retired and legacy approval is test-only, but role-string PDP/permission compatibility APIs remain in source and the trusted-identity adapter is synthetic-only.
 - [ ] Complete decision/audit reconciliation or obtain approval for a manual recovery procedure and rehearse it. #104 completes the minimal detector's immutable source-transition checks and partial-open connection cleanup. Remaining gaps are sidecar-anchor verification, stable correlation, a reviewed queue/repair workflow or approved manual procedure, and outcome/review reconciliation.
- [ ] Outcome dependency markers implemented, or a documented manual hold/review procedure approved and rehearsed. #102 now lists disputed, unreviewed, invalid-history and orphan-review cases read-only, but it does not create dependency markers, check source-hash changes, propagate holds or implement the manual procedure.
- [x] A callable CLI/API entry point runs the synthetic example end to end: PR #88 provides `agora pilot --workdir <new-empty-directory>` with import, bind, decision, principal approval, anchored audit, observed outcome/review and a synthetic-labelled report; it does not call the engine.
- [x] The CLI module no longer imports the simulation engine for pilot/data dispatch; #94 lazy-loads it only in engine-dependent handlers and passes exact-head CI 4/4. Fresh-process coverage is for `--help`, not a complete `--workdir` invocation.
- [ ] Exact-head CI is green on final reviewed implementation heads; required mutation proofs and clean-checkout review evidence are recorded.
- [ ] Claude logs the exact milestone confirmation with main SHA, four green CI jobs, merged implementation PR numbers, exact end-to-end command/example, and all readiness rows Done except simulation wiring and owner-only items.
- [ ] Only after that confirmation, the owner separately approves any synthetic rehearsal. Scenario-input-to-engine wiring remains blocked until Claude's written approval and a separate owner approval.

Passing these gates means only that a scoped synthetic rehearsal may be considered. It does not establish predictive validity, real demand, sales performance, production security or permission for external actions.

## 6. Documentation status

This assessment is refreshed against main `1ea27efb1dae9993a825a9a1a5388e0f5f82a20b` after #104 merged. Exact-head CI for #99, #100, #102 and #104 passed all four matrix jobs; no PR was open at the start of this documentation refresh.

## 7. Permanent safety boundaries

- Keep `VALIDATED_PREDICTION_ENABLED=False`.
- Do not run simulations, calibration, backtests or forecasts as part of this documentation task.
- Do not mutate existing studies, study folders, NCC Park Square or E0_C0_D0.
- Do not use real data, personal/customer records, credentials, real drivers, network access or external write-back.
- Do not edit `agora/sim/**`; scenario-input-to-engine wiring remains blocked pending Claude's written approval and separate owner approval.
- A green CI run does not authorise a PR merge, ready-for-review transition or external action.
