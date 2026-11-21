# Governed Synthetic Pilot — Milestone Readiness

**Status:** Evidence-based readiness assessment; not pilot or production authorisation  
**Assessment date:** 21 November 2026  
**Main base:** `7778b37ddd1b115f3a15ad35673e430ba22ac869`  
**Scope:** Local synthetic-data governance pipeline only

## 1. Executive assessment

The documentation and implementation queue is now merged through PR #74. Main includes the principal-first outcome bridge (#70) and the anchored-writer factory plus policy-denial wiring (#71, stages A and D), in addition to the earlier local-sidecar anchor (#63) and Windows lock fix (#66). These are meaningful implementation slices, **not** evidence that decision/outcome anchoring, complete principal migration or the callable synthetic governed pipeline is complete.

Main still does not provide one entry point that orchestrates import → bind → decision → principal approval → anchored audit → observed outcome/review → simulated-labelled report. CSV import is a CLI; binding, scenario-input construction, decision approval and outcomes are separate APIs; the scenario-input package is not wired into the simulation engine. #70 adds principal-gated outcome wrappers, but they bridge to legacy role-string APIs. #71 wires an anchored writer into policy-denial/import/binding/scenario-input paths only; decision lifecycle and outcome/review append paths remain unwired.

The anchor implementation provides a local JSONL sidecar and fail-closed append wrapper. #71 adds `open_anchored_audit()` and threads an optional anchored writer through policy denial, CSV import, ontology materialization and scenario-input construction. #74 wires decision lifecycle and outcome/review append boundaries and adds opt-in protected gates on three principal entry points; legacy/unprotected paths remain. Trust remains `local_sidecar`: coordinated rollback of both local stores is not detected. The Linux lock-removal mutation gap remains.

Decision/audit reconciliation (#57) and outcome dependency review markers (#60) remain specifications only. The manual procedures being prepared are proposals for owner approval and rehearsal; they are not approved, tested or implemented features.

This assessment does not authorise simulation, calibration, backtest, forecast, study mutation, real data, credentials, network access, production use or external write-back.

## 2. Evidence basis and merged documentation

Assessment base: `7778b37ddd1b115f3a15ad35673e430ba22ac869`.

Confirmed merged documentation PRs:
- #59 — principal call-site migration plan.
- #60 — outcome dependency review-marker specification.
- #61 — pilot-readiness checklist.
- #62 — rung-status refresh.
- #64 — audit-anchor wiring and recovery plan.
- #65 — callable-pipeline capability guide.

Confirmed merged implementation PRs:
- #53 — append-only observed outcomes and review API.
- #54 — binding purpose/retention propagation into the policy hook.
- #58 — first synthetic principal approval slice; remaining call sites are not migrated.
- #63 — local-sidecar audit-anchor primitive; #71 adds the writer factory and policy-denial/data-boundary wiring (Stages A/D). Decision lifecycle and outcomes remain unwired.
- #66 — Windows audit-log lock fix.

Earlier merged design/runbook documents remain:
- #51 identity adapter specification; #52 audit-anchor specification.
- #55 deployment-hardening specification; #56 synthetic pilot runbook; #57 decision/audit reconciliation specification.

Exact-head GitHub Actions evidence:
- #63 head `ef1f0ee430598c018a3cccd2ba2627a733f123f5`, run [44917009154](https://github.com/Post2Drive/Agora/actions/runs/44917009154): all four Ubuntu/Windows × Python 3.11/3.12 jobs passed.
- #66 head `6e0b483d628e5b4317e2cd3296a0bf0604d403f6`, run [44912719682](https://github.com/Post2Drive/Agora/actions/runs/44912719682): all four matrix jobs passed.
- #65 head `039beae59e0d3478d5412260d34a1f83618571e8`, run [44910310968](https://github.com/Post2Drive/Agora/actions/runs/44910310968): all four matrix jobs passed.

These are GitHub Actions results, not local test runs. No current-main PR-triggered workflow run was returned by the workflow lookup.

## 3. Current capability assessment

| Capability | Status | Evidence and limitation |
|---|---|---|
| Local structured CSV snapshot import | **Available — CLI** | #28 and later provenance/policy work. Local only; no external connectors/write-back. |
| Ontology binding | **Available — Python API, partial governance** | #31/#43 and #54; policy callback still uses legacy role-string authority. |
| Scenario-input package | **Available — Python API, disconnected** | #31/#41; exact import ID and provenance package, not consumed by `agora/sim/engine.py`. |
| Decision record/store and lifecycle | **Available — Python API** | #37/#42 and audit events #47. No single end-to-end command. |
| Principal-based approval and outcome wrappers | **Available — partial synthetic slices** | #58 adds `Principal`, test-only `SyntheticFixtureAdapter`, `decide_principal()` and `approve_as()`; #70 adds `required_role` and principal-gated `record_outcome_as()` / `review_outcome_as()`. The wrappers still bridge to legacy role-string APIs. Principal-first migration for shared policy enforcement and decision lifecycle is not complete. No OIDC/production authentication. |
| Audit hash chain | **Available — local chain only** | #38/#47; verifies its own chain but cannot independently detect a removed tail. |
| Anchored audit chain | **Available — local-sidecar API; partial wiring** | #63 local-sidecar writer; #71 policy/data-boundary injection; #74 lifecycle/outcome append wiring and opt-in `require_anchored=True` gates on `approve_as()`, `record_outcome_as()` and `review_outcome_as()`. Legacy optional-audit paths remain. Trust remains `local_sidecar`. |
| Observed outcome recording/review | **Available — Python API, partial principal migration** | #53 provides append-only observed outcomes/reviews; #70 adds principal-gated `record_outcome_as()` / `review_outcome_as()` with operator/reviewer checks. These wrappers still delegate to legacy role-string functions and their audit parameter remains optional; no anchored outcome wiring or CLI. |
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
| #72 | Earlier documentation refresh based on pre-#71 main | Open draft; superseded by this refresh |

Main is `7778b37ddd1b115f3a15ad35673e430ba22ac869`. PR #71 is merged. PR #72, the superseded pre-#71 documentation draft, is closed. PR #73 is the current documentation refresh, open/draft/unmerged.

## 5. Required exit gates before the milestone can be declared reached

- [x] Principal migration plan, outcome-marker specification and pilot-readiness checklist merged (#59–#61).
- [x] Audit-anchor wiring plan merged (#64); it remains a plan, not implementation.
- [x] First synthetic principal approval slice merged (#58); remaining call-site migration is still open.
- [x] Local audit-anchor implementation merged (#63), with all four exact-head CI jobs green. Trust remains local-sidecar; the Linux lock-removal mutation proof did not detect the mutation.
- [x] Windows audit-log lock fix merged (#66), with all four exact-head CI jobs green.
- [x] Anchored writer factory and policy-denial/import/binding/scenario-input wiring merged (#71, Stages A/D), with all four exact-head CI jobs green.
- [x] Lifecycle/outcome append wiring added by #74; protected gates fail closed on the three named principal entry points. Universal protected-mode coverage remains open.
- [ ] Principal-first migration completed for decision/PDP/shared policy enforcement and outcome recording/review call sites; #70 is only a principal-gated outcome bridge, and #71 does not yet make policy enforcement principal-native or require a principal.
- [ ] Decision/audit reconciliation implemented, or a documented manual recovery procedure approved and rehearsed. The manual procedure draft is not approval or evidence of a tested repair path.
- [ ] Outcome dependency markers implemented, or a documented manual hold/review procedure approved and rehearsed. The manual procedure draft is not an implemented marker/propagation system.
- [ ] A callable CLI/API entry point runs the synthetic example end to end: import, bind, decision, principal approval, anchored audit, observed outcome/review and simulated-labelled report, using exact immutable IDs.
- [ ] Exact-head CI is green on final reviewed implementation heads; required mutation proofs and clean-checkout review evidence are recorded.
- [ ] Claude logs the exact milestone confirmation with main SHA, four green CI jobs, merged implementation PR numbers, exact end-to-end command/example, and all readiness rows Done except simulation wiring and owner-only items.
- [ ] Only after that confirmation, the owner separately approves any synthetic rehearsal. Scenario-input-to-engine wiring remains blocked until Claude's written approval and a separate owner approval.

Passing these gates means only that a scoped synthetic rehearsal may be considered. It does not establish predictive validity, real demand, sales performance, production security or permission for external actions.

## 6. Documentation status

This assessment is refreshed against main `7778b37ddd1b115f3a15ad35673e430ba22ac869`, after #70 and #71 merged. Stages A/D of anchor wiring are implemented; Stages B/C, principal migration slice 2, protected-mode enforcement and the single callable orchestrator remain open. The reconciliation and outcome hold/review procedures are documentation proposals only and still require owner approval and rehearsal before they can satisfy a milestone gate.

## 7. Permanent safety boundaries

- Keep `VALIDATED_PREDICTION_ENABLED=False`.
- Do not run simulations, calibration, backtests or forecasts as part of this documentation task.
- Do not mutate existing studies, study folders, NCC Park Square or E0_C0_D0.
- Do not use real data, personal/customer records, credentials, real drivers, network access or external write-back.
- Do not edit `agora/sim/**`; scenario-input-to-engine wiring remains blocked pending Claude's written approval and separate owner approval.
- A green CI run does not authorise a PR merge, ready-for-review transition or external action.


## Current mainline correction — PR #74 (21 November 2026)

This section supersedes earlier status text in this document that described Stages B/C as unwired. Main is `7778b37ddd1b115f3a15ad35673e430ba22ac869`, the merge of #75 (which includes #74). PR #74 merged at exact head `ca92a206219bb7da6de4b4f50a157b74ac6103c7`; exact-head Actions run 221 (`44928837108`) passed all four Ubuntu/Windows × Python 3.11/3.12 jobs.

Main now has `require_anchored()` and `require_anchored=True` on `approve_as()`, `record_outcome_as()` and `review_outcome_as()`, checked before state mutation. Decision lifecycle and outcome/review append helpers accept the audit writer; anchor failures surface as typed partial-failure errors after business state may already be committed. This is partial Stage B/C, not universal protected mode: legacy lifecycle APIs and optional `audit=None` paths remain. Principal wrappers still bridge to legacy role-string APIs. PR #75 is now merged at exact head `ae1b50577047eb7ef1435bcf231037f566eed77d`; exact-head Actions run 224 (`44929428177`) passed all four matrix jobs. Its `AuditAppender` Protocol/type annotations make the writer contract structural; it does not add broader protected gates beyond #74. Reconciliation (#57), outcome markers (#60) and the callable end-to-end pipeline remain incomplete.
