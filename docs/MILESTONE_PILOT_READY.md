# Governed Synthetic Pilot — Milestone Readiness

**Status:** Evidence-based readiness assessment; not pilot or production authorisation  
**Assessment date:** 21 November 2026  
**Main base:** `d0cb5c7260f3d18643cd6a93fd6fdd4e9cbd43c9`  
**Scope:** Local synthetic-data governance pipeline only

## 1. Executive assessment

The documentation queue is now merged through PRs #59–#61 and #64, and the first synthetic principal approval slice (#58) remains available. This is progress in the documented design and limited API surface, **not** evidence that the callable synthetic governed pipeline is complete.

Main still does not provide one entry point that orchestrates import → bind → decision → principal approval → anchored audit → observed outcome/review → simulated-labelled report. CSV import is a CLI; binding, scenario-input construction, decision approval and outcomes are separate Python APIs; the scenario-input package is not wired into the simulation engine. Principal approval is a limited synthetic bridge and other policy/outcome call sites still use caller-supplied role strings. The audit-anchor implementation is still open/draft PR #63 and is not on main or wired. Reconciliation and outcome dependency markers remain specifications only.

This assessment does not authorise simulation, calibration, backtest, forecast, study mutation, real data, credentials, network access, production use or external write-back.

## 2. Evidence basis and merged documentation

Assessment base: `d0cb5c7260f3d18643cd6a93fd6fdd4e9cbd43c9`.

Confirmed merged documentation PRs:
- #59 — principal call-site migration plan.
- #60 — outcome dependency review-marker specification.
- #61 — pilot-readiness assessment.
- #62 — rung-status refresh.
- #64 — audit-anchor wiring and recovery plan.

Earlier merged design/runbook documents remain:
- #51 identity adapter specification; #52 audit-anchor specification.
- #55 deployment-hardening specification; #56 synthetic pilot runbook; #57 decision/audit reconciliation specification.

Implementation evidence includes #53 append-only observed outcomes/review API, #54 binding purpose/retention propagation, and #58 the first synthetic principal slice. The audit-anchor implementation PR #63 is still open/draft at head `b135fdadd17bebfac4ab3137554bb4519070d5f9`; it is not part of this mainline assessment. Its PR description reports tests and CI, but those claims do not make the code merged or wired.

## 3. Current capability assessment

| Capability | Status | Evidence and limitation |
|---|---|---|
| Local structured CSV snapshot import | **Available — CLI** | #28 and later provenance/policy work. Local only; no external connectors/write-back. |
| Ontology binding | **Available — Python API, partial governance** | #31/#43 and #54; policy callback still uses legacy role-string authority. |
| Scenario-input package | **Available — Python API, disconnected** | #31/#41; exact import and provenance package, not consumed by `agora/sim/engine.py`. |
| Decision record/store and lifecycle | **Available — Python API** | #37/#42 and audit events #47. No single end-to-end command. |
| Principal-based approval | **Available — limited synthetic slice** | #58 adds immutable Principal, test-only SyntheticFixtureAdapter, decide_principal and approve_as(). approve_as bridges to legacy approve(); other role-string call sites remain. No OIDC/production authentication. |
| Audit hash chain | **Available — local chain only** | #38/#47; verifies its own chain but is not independently anchored. |
| Anchored audit chain | **Not available on main** | #52 is a specification. #63 remains open/draft; no merged implementation or call-site wiring. |
| Observed outcome recording/review | **Available — Python API, partial governance** | #53; observed-only source contract and independent review. Current role/subject arguments are caller supplied; no CLI. |
| Outcome dependency review markers | **Not implemented** | #60 is a specification only; no marker store/worker/propagation. |
| Decision/audit reconciliation | **Not implemented** | #57 is a specification only; no queue, detector, worker or repair command. |
| Simulated-labelled report | **Available — separate exploratory/mock path** | Existing report CLI path; not connected to the scenario-input package or decision/outcome workflow. |
| Single callable end-to-end pipeline | **Not implemented** | No orchestrator joins all required stages with principal-first authorization and anchored audit. |
| Integrated pilot readiness | **Not ready** | Implementation, wiring, operational and approval gates remain open. |

## 4. Pull request status snapshot

| PR | Scope | State at this assessment |
|---|---|---|
| #59 | Principal migration plan | Merged |
| #60 | Outcome dependency review-marker specification | Merged |
| #61 | Pilot-readiness checklist | Merged |
| #62 | Rung-status refresh | Merged |
| #63 | Local audit-anchor implementation | Open / Draft; not merged |
| #64 | Audit-anchor wiring plan | Merged |

Main is `d0cb5c7260f3d18643cd6a93fd6fdd4e9cbd43c9`. The exact live PR metadata check confirms #59, #60, #61 and #64 merged; #63 remains open/draft. Do not treat its populated merge_commit_sha field as merge confirmation: the authoritative PR state reports `merged=false`, `state=open`, and `merged_at=null`.

## 5. Required exit gates before the milestone can be declared reached

- [x] Principal migration plan, outcome-marker specification and pilot-readiness checklist merged (#59–#61).
- [x] Audit-anchor wiring plan merged (#64); it is a plan, not implementation.
- [x] First synthetic principal approval slice merged (#58); remaining call-site migration is still open.
- [ ] Local audit-anchor implementation merged and independently verified, including cross-process locking, permissions/atomic durability, close lifecycle, crash recovery and residual local-sidecar limitations.
- [ ] Anchored writer wired into decision lifecycle, outcomes/reviews and policy-denial append boundaries; protected operations fail closed when anchoring is unavailable.
- [ ] Principal-first migration completed for decision/PDP/policy enforcement/outcome recording/review call sites; caller-supplied roles no longer confer authority.
- [ ] Windows audit-log lock flake fixed and evidenced on exact reviewed head.
- [ ] Decision/audit reconciliation implemented, or a documented manual recovery procedure approved and tested.
- [ ] Outcome dependency markers implemented, or a documented manual hold/review procedure approved and tested.
- [ ] A callable CLI/API entry point runs the synthetic example end to end: import, bind, decision, principal approval, anchored audit, observed outcome/review and simulated-labelled report, using exact immutable IDs.
- [ ] Exact-head CI is green on final reviewed implementation heads; required mutation proofs and clean-checkout review evidence are recorded.
- [ ] Claude logs the exact milestone confirmation with main SHA, four green CI jobs, merged implementation PR numbers, exact end-to-end command/example, and all readiness rows Done except simulation wiring and owner-only items.
- [ ] Only after that confirmation, the owner separately approves any synthetic rehearsal. Scenario-input-to-engine wiring remains blocked until Claude's written approval and a separate owner approval.

Passing these gates means only that a scoped synthetic rehearsal may be considered. It does not establish predictive validity, real demand, sales performance, production security or permission for external actions.

## 6. Documentation status

This assessment is refreshed against main after #59–#61 and #64 merged. `docs/PIPELINE_HOWTO.md` is a component-by-component guide: it labels each step available/not available and explicitly states that the integrated callable entry point does not yet exist. This document does not promote design specifications or draft PRs to implemented capabilities.

## 7. Permanent safety boundaries

- Keep `VALIDATED_PREDICTION_ENABLED=False`.
- Do not run simulations, calibration, backtests or forecasts as part of this documentation task.
- Do not mutate existing studies, study folders, NCC Park Square or E0_C0_D0.
- Do not use real data, personal/customer records, credentials, real drivers, network access or external write-back.
- Do not edit `agora/sim/**` without Claude's written approval and separate owner approval.
- A green CI run does not authorise a PR merge, ready-for-review transition or external action.
