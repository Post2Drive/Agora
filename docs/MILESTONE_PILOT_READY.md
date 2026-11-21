# Governed Synthetic Pilot — Milestone Readiness

**Status:** Evidence-based readiness assessment; not pilot or production authorisation  
**Assessment date:** 21 November 2026  
**Main base:** `90789ccfd866c038ce67753645b5e258134b9af3`  
**Scope:** Local synthetic-data governance pipeline only

## 1. Executive assessment

The documentation and implementation queue is now merged through PRs #59–#66. Main includes the local-sidecar audit-anchor implementation (#63) and the Windows audit-log lock fix (#66), alongside the earlier principal and outcome slices. This is meaningful implementation progress, **not** evidence that the callable synthetic governed pipeline is complete.

Main still does not provide one entry point that orchestrates import → bind → decision → principal approval → anchored audit → observed outcome/review → simulated-labelled report. CSV import is a CLI; binding, scenario-input construction, decision approval and outcomes are separate APIs; the scenario-input package is not wired into the simulation engine. Principal approval remains a limited synthetic bridge and other policy/outcome call sites still use caller-supplied role strings.

The anchor implementation provides a local JSONL sidecar and a fail-closed append wrapper, but it is not wired into decision, outcome or policy call sites. Its trust level is `local_sidecar`: it cannot detect coordinated rollback of both local stores. PR #63's Linux mutation proof does not detect removal of the cross-process lock; lock coverage is therefore supported by implementation design and CI, not that mutation test.

Decision/audit reconciliation (#57) and outcome dependency review markers (#60) remain specifications only. The manual procedures being prepared are proposals for owner approval and rehearsal; they are not approved, tested or implemented features.

This assessment does not authorise simulation, calibration, backtest, forecast, study mutation, real data, credentials, network access, production use or external write-back.

## 2. Evidence basis and merged documentation

Assessment base: `90789ccfd866c038ce67753645b5e258134b9af3`.

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
- #63 — local-sidecar audit-anchor implementation; not wired into protected call sites.
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
| Principal-based approval | **Available — limited synthetic slice** | #58 adds immutable Principal, test-only SyntheticFixtureAdapter, decide_principal and approve_as(). The bridge still delegates to legacy role-string approval; other call sites remain unmigrated. No OIDC/production authentication. |
| Audit hash chain | **Available — local chain only** | #38/#47; verifies its own chain but cannot independently detect a removed tail. |
| Anchored audit chain | **Available — local-sidecar API, not wired** | #63 adds AnchorStore, AnchoredAuditChain, bootstrap_anchor() and verify_anchored(). It is local-sidecar trust only and is not connected to decision, outcome or policy append boundaries. |
| Observed outcome recording/review | **Available — Python API, partial governance** | #53; observed-only source contract and independent review. Current role/subject arguments are caller supplied; no CLI. |
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

Main is `90789ccfd866c038ce67753645b5e258134b9af3`. The repository open-PR search returned no open PRs at this check.

## 5. Required exit gates before the milestone can be declared reached

- [x] Principal migration plan, outcome-marker specification and pilot-readiness checklist merged (#59–#61).
- [x] Audit-anchor wiring plan merged (#64); it remains a plan, not implementation.
- [x] First synthetic principal approval slice merged (#58); remaining call-site migration is still open.
- [x] Local audit-anchor implementation merged (#63), with all four exact-head CI jobs green. Trust remains local-sidecar; the Linux lock-removal mutation proof did not detect the mutation.
- [x] Windows audit-log lock fix merged (#66), with all four exact-head CI jobs green.
- [ ] Anchored writer wired into decision lifecycle, outcomes/reviews and policy-denial append boundaries; protected operations fail closed when anchoring is unavailable.
- [ ] Principal-first migration completed for decision/PDP/policy enforcement/outcome recording/review call sites; caller-supplied roles no longer confer authority.
- [ ] Decision/audit reconciliation implemented, or a documented manual recovery procedure approved and rehearsed. The manual procedure draft is not approval or evidence of a tested repair path.
- [ ] Outcome dependency markers implemented, or a documented manual hold/review procedure approved and rehearsed. The manual procedure draft is not an implemented marker/propagation system.
- [ ] A callable CLI/API entry point runs the synthetic example end to end: import, bind, decision, principal approval, anchored audit, observed outcome/review and simulated-labelled report, using exact immutable IDs.
- [ ] Exact-head CI is green on final reviewed implementation heads; required mutation proofs and clean-checkout review evidence are recorded.
- [ ] Claude logs the exact milestone confirmation with main SHA, four green CI jobs, merged implementation PR numbers, exact end-to-end command/example, and all readiness rows Done except simulation wiring and owner-only items.
- [ ] Only after that confirmation, the owner separately approves any synthetic rehearsal. Scenario-input-to-engine wiring remains blocked until Claude's written approval and a separate owner approval.

Passing these gates means only that a scoped synthetic rehearsal may be considered. It does not establish predictive validity, real demand, sales performance, production security or permission for external actions.

## 6. Documentation status

This assessment is refreshed against main `90789ccfd866c038ce67753645b5e258134b9af3`, after #63 and #66 merged. `docs/PIPELINE_HOWTO.md` now distinguishes the merged local-sidecar anchor API from the still-missing protected call-site wiring and end-to-end orchestrator. The proposed reconciliation and outcome hold/review procedures are separate documentation drafts; they require owner approval and rehearsal before they can satisfy a milestone gate.

## 7. Permanent safety boundaries

- Keep `VALIDATED_PREDICTION_ENABLED=False`.
- Do not run simulations, calibration, backtests or forecasts as part of this documentation task.
- Do not mutate existing studies, study folders, NCC Park Square or E0_C0_D0.
- Do not use real data, personal/customer records, credentials, real drivers, network access or external write-back.
- Do not edit `agora/sim/**`; scenario-input-to-engine wiring remains blocked pending Claude's written approval and separate owner approval.
- A green CI run does not authorise a PR merge, ready-for-review transition or external action.
