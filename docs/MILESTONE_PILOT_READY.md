# Governed Synthetic Pilot — Milestone Readiness

**Status:** Evidence-based readiness assessment; not pilot or production authorisation  
**Assessment date:** 21 November 2026  
**Main base:** 98850910559d0e4d72be127d1412dddcc5326cb8  
**Scope:** Local synthetic-data governance pipeline only

## 1. Executive assessment

The repository has a meaningful governed-data and decision-record foundation, but it is **not yet ready for an integrated data-to-simulation pilot or any live/production pilot**.

Decision records, approval lifecycle, decision outcomes, report provenance and policy boundaries have merged implementation evidence. Important end-to-end gates remain incomplete: the scenario-input package is not wired into the simulation engine; the trusted-principal implementation is still an open draft; independent audit anchoring and cross-store reconciliation are not implemented; outcome dependency review markers do not exist; and the runbook/deployment-hardening documents are still draft PRs.

This assessment does not authorise a simulation, calibration, backtest, forecast, study mutation, use of real data, credentials, network access or external write-back.

## 2. Evidence basis

The assessment is based on main at 98850910559d0e4d72be127d1412dddcc5326cb8 and direct GitHub PR/CI metadata checked on 21 November 2026. Relevant merged evidence includes:

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
| Trusted identity | Partial | #51 is a merged design specification. PR #58 is an open draft implementation slice; caller-supplied role strings remain on main. No OIDC or production authentication. |
| Audit chain | Partial | #38 and #47 provide the local append-only chain and lifecycle events. #52 is only the anchor specification; independent anchoring is not implemented. |
| Decision/audit reconciliation | Not implemented | PR #57 is an open draft specification. No queue, worker, repair command or automatic reconciliation exists. |
| Outcome dependency review markers | Not implemented | This specification is proposed separately; no marker store or downstream propagation exists on main. |
| Report provenance | Demonstrated for current local report-export slice | #44 provides provenance export and fail-closed validated-prediction gate. Keep outputs labelled exploratory/simulated. |
| Retention and erasure | Design only | #45 defines a design; operational erasure workflow and backup-expiry automation are not demonstrated. |
| Deployment hardening | Design only / draft | PR #55 is an open draft specification. No hardened deployment platform or verified host/VM controls are claimed. |
| Synthetic pilot runbook | Draft | PR #56 is open. Its current branch text reflects merged #53/#54, but the runbook is not yet merged or executed. |
| Integrated pilot sign-off | Not ready | Multiple implementation and operational gates below remain open. |

## 4. Open pull requests and exact-head CI snapshot

All four PRs below were open and draft when checked. None was marked ready or merged in this assessment.

| PR | Scope and exact head | Base SHA | Exact-head workflow evidence at check time |
|---|---|---|---|
| #55 — deployment hardening | docs/DEPLOYMENT_HARDENING_SPEC.md; d3ece4659f7aab9e16d7df91accc53862335717e | 9c7a0a89cb5e4622a893152b0ffff588edea56c2 | Run 44902320266: Ubuntu 3.11 and 3.12 passed; Windows 3.11 and 3.12 were still running. |
| #56 — synthetic pilot runbook | docs/PILOT_RUNBOOK.md; c0acccc263c9888a2cdc32ba4c179d4d882d4bb4 | 98850910559d0e4d72be127d1412dddcc5326cb8 | Run 44902292375: Ubuntu 3.11 and 3.12 passed; Windows 3.11 and 3.12 were still running. |
| #57 — reconciliation specification | docs/RECONCILIATION_SPEC.md; 35adac8455755b677f47664d30297332306556b2 | 9c7a0a89cb5e4622a893152b0ffff588edea56c2 | Run 44902293651: Ubuntu 3.11 and 3.12 passed; Windows 3.11 and 3.12 were still running. |
| #58 — principal implementation slice | agora/principal.py, agora/decisions/approval.py and tests/test_principal.py; 84d6805ec8023a16ef139bf8af04253e0c6f8193 | 98850910559d0e4d72be127d1412dddcc5326cb8 | Run 44902246519: all four Ubuntu/Windows × Python 3.11/3.12 jobs passed. PR remains draft and unmerged. |

At this snapshot, #55 and #57 still recorded the earlier base 9c7a0a89, while #56 and #58 were based on current main 9885091. Do not silently treat the older-base branches as current-main branches. The latest collaboration instruction was not to edit #55–#57 further unless a defect is found; any base refresh must follow the agreed owner/Claude workflow.

No PR comments were returned by the checked PR discussion timelines. CI status is a point-in-time observation; re-fetch the exact head and run before making any later merge/readiness claim. No local tests were run in this assessment.

## 5. Required exit gates before a controlled synthetic pilot

- [ ] The owner confirms the precise pilot scope, operators, data directory, stop conditions and permitted commands.
- [ ] The pilot runbook (#56) is reviewed, corrected against current main and merged.
- [ ] The deployment-hardening controls (#55) are reviewed and the required local host/VM, permissions, backup and restore checks are evidenced.
- [ ] The trusted-principal implementation is merged and reviewed; all governed operations use adapter-issued principals rather than caller-supplied role strings.
- [ ] The audit-anchor implementation is built and independently verified against crash, restore and tamper cases. A local sidecar is not represented as protection against an attacker who can rewrite both local stores.
- [ ] Decision-store/audit-chain reconciliation is implemented or a documented manual recovery procedure is approved and tested.
- [ ] Outcome dependency review markers are implemented or a documented manual hold/review process is approved; disputed/corrected outcomes cannot silently continue to support dependent reports or decisions.
- [ ] The exact scenario-input-to-engine integration has separate Claude written approval and separate owner approval before any change to agora/sim/**. New-run and resume paths must both be covered.
- [ ] Exact-head CI is green on the final reviewed implementation heads; required mutation proofs and clean-checkout review evidence are recorded.
- [ ] A synthetic rehearsal is executed only after its own explicit approval, with public/internal synthetic fields, temporary local stores and no external systems.
- [ ] The rehearsal report records artifacts, source hashes, decision versions, approval actors, audit verification, failures, stop conditions and unresolved gaps.
- [ ] No real personal/customer data, Nutrivance/NCC Park Square data, credentials, external drivers, network connectors or write-back are used.

Passing these gates means only that a scoped synthetic rehearsal may be considered. It does not establish predictive validity, real demand, sales performance, production security or permission for external actions.

## 6. Deferred documentation refresh

docs/RUNG_STATUS.md on main still has an older assessment base (cd28916ae9d2ba4408205ac70c1b6e082ebe1af5) and predates the merged outcome (#53) and purpose/retention (#54) changes. The collaboration log explicitly defers its refresh until PRs #55, #56 and #57 have actually merged. Therefore this task does not edit RUNG_STATUS.md or claim it is current.

After those PRs are confirmed merged, refresh RUNG_STATUS.md against the then-current main SHA, reconcile every rung with merged evidence, and keep PR #58 marked in-review until its actual merge is verified.

## 7. Permanent safety boundaries

- Keep VALIDATED_PREDICTION_ENABLED=False.
- Do not run simulations, calibration, backtests or forecasts as part of this assessment.
- Do not mutate existing studies, study folders, NCC Park Square or E0_C0_D0.
- Do not use real data, personal/customer records, credentials, real drivers, network access or external write-back.
- Do not edit agora/sim/** without Claude's written approval and separate owner approval.
- A green CI run does not authorise a PR merge, ready-for-review transition or external action.
