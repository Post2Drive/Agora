# Governed Synthetic Pilot — Milestone Readiness

**Status:** Evidence-based readiness assessment; not pilot or production authorisation  
**Assessment date:** 21 November 2026  
**Main base:** 19f51d84d3ecc8392eb8713e392f93cb58a736bf  
**Scope:** Local synthetic-data governance pipeline only

## 1. Executive assessment

The repository has a meaningful governed-data and decision-record foundation, but it is **not yet ready for an integrated data-to-simulation pilot or any live/production pilot**.

Decision records, approval lifecycle, decision outcomes, report provenance and policy boundaries have merged implementation evidence. Important end-to-end gates remain incomplete: the scenario-input package is not wired into the simulation engine; the trusted-principal slice (#58, merged) is synthetic and covers approval only, with role-string call sites still on main; independent audit anchoring (implementation in review as #63) and cross-store reconciliation are not implemented; outcome dependency review markers do not exist. The hardening, runbook and reconciliation documents (#55-#57) are merged but are specifications/drafts of procedure, not executed evidence.

This assessment does not authorise a simulation, calibration, backtest, forecast, study mutation, use of real data, credentials, network access or external write-back.

## 2. Evidence basis

The assessment is based on main at 19f51d84d3ecc8392eb8713e392f93cb58a736bf and direct GitHub PR/CI metadata checked on 21 November 2026. Relevant merged evidence includes:

- #28 — local read-only snapshot CLI.
- #31 and #41 — scenario-input adapter, binding and pilot data contract.
- #37 — immutable decision schema/store.
- #38 and #47 — append-only audit-chain store and decision lifecycle/approval-denial audit events.
- #39 and #43 — deny-by-default PDP and enforcement at import, binding and scenario-input boundaries.
- #42 — decision approval state machine.
- #44 — report provenance export and validated-prediction gate.
- #45 — retention/erasure design.
- #49 — simulation-wiring proposal only; it does not wire the simulation engine.
- #51 — trusted-principal identity design specification.
- #52 — independent audit-anchor design specification.
- #53 — append-only decision outcomes and review API.
- #54 — binding purpose/retention propagation fix.
- #55 — deployment hardening specification.
- #56 — synthetic pilot runbook.
- #57 — decision/audit reconciliation specification.
- #58 — first synthetic trusted-principal slice (Principal, SyntheticFixtureAdapter, approve_as()).

The identity and audit-anchor specifications (#51–#52) are design evidence, not proof of production identity or independent anchoring. The decision outcome implementation (#53) stores observed outcomes and review events, but it does not provide dependency review markers or a reconciliation worker.

## 3. Current capability assessment

| Capability | Status | Evidence and limitation |
|---|---|---|
| Local project and test foundation | Demonstrated for current repository scope | Existing four-job Ubuntu/Windows × Python 3.11/3.12 CI matrix and merged foundation work. CI proves repository tests, not production operations. |
| Snapshot import and provenance | Partial | #28, #31, #41 and #43 provide local structured snapshot, provenance and policy-boundary foundations. No real database drivers, external connectors or write-back. |
| Binding and scenario-input package | Partial | Binding/scenario-input APIs and #54 purpose/retention propagation are on main. The package is not consumed by agora/sim/engine.py. |
| Simulation engine integration | Not implemented | #49 is a proposal only. New runs do not prepare/persist the scenario-input envelope before population creation, and resume does not verify the input envelope before loading the world. |
| Decision record and approval lifecycle | Demonstrated for local API slice | #37 and #42 provide immutable decision records and approval transitions with exact-version/fingerprint/scope/evidence checks. This is not an external action executor. |
| Observed decision outcomes | Demonstrated for local API slice | #53 adds append-only outcome/review records with observed-source requirements. No CLI, dependency review-marker propagation or cross-store reconciliation queue. Simulated preferences/actions remain exploratory. |
| Trusted identity | Partial | #51 design and #58 synthetic principal slice are merged. approve_as() derives the role from a Principal, but legacy role-string approve(), outcomes and policy-callback call sites remain. No OIDC or production authentication. |
| Audit chain | Partial | #38 and #47 provide the local append-only chain and lifecycle events. #52 is only the anchor specification; an anchor implementation is an open draft (#63) and is not on main. |
| Decision/audit reconciliation | Not implemented | #57 is a merged specification. No queue, worker, repair command or automatic reconciliation exists. |
| Outcome dependency review markers | Not implemented | This specification is proposed separately; no marker store or downstream propagation exists on main. |
| Report provenance | Demonstrated for current local report-export slice | #44 provides provenance export and fail-closed validated-prediction gate. Keep outputs labelled exploratory/simulated. |
| Retention and erasure | Design only | #45 defines a design; operational erasure workflow and backup-expiry automation are not demonstrated. |
| Deployment hardening | Design only / draft | #55 is a merged specification. No hardened deployment platform or verified host/VM controls are claimed. |
| Synthetic pilot runbook | Documented, not executed | #56 is merged and reflects #53/#54; the runbook has not been executed. |
| Integrated pilot sign-off | Not ready | Multiple implementation and operational gates below remain open. |

## 4. Pull request status snapshot

PRs #55, #56, #57 and #58 are merged on main 19f51d8; each had all four Ubuntu/Windows × Python 3.11/3.12 jobs green at its reviewed head. Open drafts at the time of writing:

| PR | Scope | State |
|---|---|---|
| #63 — audit anchor implementation | agora/audit_anchor.py, tests/test_audit_anchor.py | Draft, owner review pending; not on main. |
| #62 — rung status refresh | docs/RUNG_STATUS.md | Docs draft. |
| #59, #60 | principal migration plan, outcome review markers spec | Docs drafts. |

CI status is a point-in-time observation; re-fetch the exact head before any later readiness claim.

## 5. Required exit gates before a controlled synthetic pilot

- [ ] The owner confirms the precise pilot scope, operators, data directory, stop conditions and permitted commands.
- [x] The pilot runbook (#56) is reviewed, corrected against main and merged (Done; execution still requires approval).
- [ ] The deployment-hardening specification (#55) is merged (Done); the required local host/VM, permissions, backup and restore checks are evidenced.
- [ ] The synthetic principal slice (#58) is merged (Partial); all governed operations use adapter-issued principals rather than caller-supplied role strings.
- [ ] The audit-anchor implementation is built and independently verified against crash, restore and tamper cases. A local sidecar is not represented as protection against an attacker who can rewrite both local stores.
- [ ] Decision-store/audit-chain reconciliation (specified in #57; Not started as code) is implemented or a documented manual recovery procedure is approved and tested.
- [ ] Outcome dependency review markers are implemented or a documented manual hold/review process is approved; disputed/corrected outcomes cannot silently continue to support dependent reports or decisions.
- [ ] The exact scenario-input-to-engine integration has separate Claude written approval and separate owner approval before any change to agora/sim/**. New-run and resume paths must both be covered.
- [ ] Exact-head CI is green on the final reviewed implementation heads; required mutation proofs and clean-checkout review evidence are recorded.
- [ ] A synthetic rehearsal is executed only after its own explicit approval, with public/internal synthetic fields, temporary local stores and no external systems.
- [ ] The rehearsal report records artifacts, source hashes, decision versions, approval actors, audit verification, failures, stop conditions and unresolved gaps.
- [ ] No real personal/customer data, Nutrivance/NCC Park Square data, credentials, external drivers, network connectors or write-back are used.

Passing these gates means only that a scoped synthetic rehearsal may be considered. It does not establish predictive validity, real demand, sales performance, production security or permission for external actions.

## 6. Documentation refresh

docs/RUNG_STATUS.md is being refreshed against current main in draft PR #62. Until it merges, main's copy predates #53-#58.

## 7. Permanent safety boundaries

- Keep VALIDATED_PREDICTION_ENABLED=False.
- Do not run simulations, calibration, backtests or forecasts as part of this assessment.
- Do not mutate existing studies, study folders, NCC Park Square or E0_C0_D0.
- Do not use real data, personal/customer records, credentials, real drivers, network access or external write-back.
- Do not edit agora/sim/** without Claude's written approval and separate owner approval.
- A green CI run does not authorise a PR merge, ready-for-review transition or external action.
