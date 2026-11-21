# Principal Migration Plan

**Status:** Documentation plan only; no implementation or production-authentication approval  
**Assessment base:** main at 87c7cc95b3e7c231f52dca4924d6fc433c698462 (22 November 2026), including merged #58, #70, #71, #74, #78, #79, #80, #82, #84, #85, #86, #88 and #89; #91 is the open ChatGPT docs draft.
**Related design:** docs/IDENTITY_ADAPTER_SPEC.md (merged PR #51)

## 1. Objective and security invariant

Move every governed authorization boundary from caller-supplied role strings and subject mappings to an immutable principal issued by a trusted identity adapter. The policy decision point (PDP) must derive roles, tenant/project scope, assurance and actor identity from that principal. Request parameters must never be able to grant themselves an approver, operator or reviewer role.

The migration must preserve the current deny-by-default policy semantics, decision-version checks, evidence fingerprints, separation of duties, append-only records and allow-listed audit events. A missing, expired, malformed, untrusted or out-of-scope principal must fail closed.

This plan does not implement identity, enable OIDC, authorise network access, change production configuration or approve source-code work.

## 2. Verified current inventory

The following inventory was checked against main at the assessment SHA:

| Boundary | Current mainline interface | Migration concern |
|---|---|---|
| PDP | `decide(subject, role, operation, resource)` / `authorize(...)` remain role-string APIs; #78 adds `principal_policy(principal, required_role)` to bind a Principal into the operation/resource callback. | The callback can derive authority from a bound Principal, but `PolicyCallable` still receives only operation/resource and `require_policy=False` remains the default. |
| Approval permission adapter | `authorize_decision_approval(subject, role, resource)` remains legacy; #80 adds `authorize_decision_approval_principal(principal, resource)` requiring the `approver` role. | Both adapters exist; the role-string adapter remains callable and the principal-native path is used by `approve_as()`. |
| Decision approval | `approve_as(..., principal=...)` is principal-native after #80/#84; `approve(... actor, role, subject, ...)` remains a compatibility API. | #89 makes `require_anchored=True` the default on `approve_as()`, but explicit `False` remains accepted. Legacy `approve()` still has the runtime-enableable `AGORA_TEST_ONLY_LEGACY_APPROVE=1` switch (#82). |
| Outcome recording | `record_outcome()` legacy API plus `record_outcome_as(..., principal=...)` (#70/#86/#89) | The wrapper ignores caller resource data and defaults to anchored audit, but still delegates to the public role-string function. Explicit `require_anchored=False` remains accepted. |
| Outcome review | `review_outcome_as(..., principal=...)` plus legacy `review_outcome()` (#70/#86/#89) | The wrapper ignores caller resource data and defaults to anchored audit, but still delegates to the public role-string function. Explicit `require_anchored=False` remains accepted. |
| Shared enforcement hook | `PolicyCallable(operation, resource)` and `enforce_policy(..., require_policy=False, audit=...)` (#78/#89) | The three data-boundary callers now default `require_policy=True`. Direct `enforce_policy()` still defaults off; explicit False remains accepted, and `audit=None` denial logging uses an unanchored project-local chain. |
| Data-boundary callers | `ingest_csv()`, `materialize_instances()` and `build_scenario_input()` (#79/#89) | All three now default `require_policy=True` on main. Explicit `False` remains accepted; missing-policy denial still permits `audit=None` and an unanchored chain. |

### 2.1 Principal implementation status

PR #58 established the synthetic Principal/PDP foundation. #70 added principal-gated outcome wrappers, but they still delegate to legacy role-string outcome functions. #78 added `principal_policy(principal, required_role)`, which binds a Principal into the existing operation/resource callback, and `require_policy=True` denial in `enforce_policy()`. #79 threaded `require_policy` through import, binding and scenario-input boundaries; at the #79 merge point all three defaults remained `False`, then merged #89 changed them to `True`. Explicit `require_policy=False` remains an opt-out, and `audit=None` policy-denial logging remains unanchored. #80 added `authorize_decision_approval_principal(principal, resource)` and made `approve_as()` use it once, deriving the actor from the Principal. #82 makes legacy role-string `approve()` fail closed unless the explicit test-only environment switch is set. #74's anchor gates were initially opt-in; #89 now defaults the three Principal wrappers to anchored audit. These are partial synthetic migration slices, not a completed identity boundary.

Before each stage, re-read agora/principal.py and its tests on current main; do not assume APIs beyond what is merged.

## 3. Target contract

A principal used by a governed operation must provide, at minimum:

- Stable subject identifier.
- Explicit tenant ID and an explicit set of project IDs; an empty project set grants no access.
- Adapter-derived internal roles; never merge request-supplied roles into the principal.
- Normalised assurance level.
- Exact trusted issuer identifier.
- Time-bounded expiry, checked at the time of each decision.

The principal is immutable. The adapter validates the credential or synthetic fixture before issuing it. The PDP checks issuer trust, expiry, required assurance, role permission, tenant/project scope, operation and resource sensitivity/purpose/retention. Unknown or ambiguous values deny.

The first implementation slice remains synthetic-fixture-only. OIDC, real credentials, issuer discovery, JWKS/network access and production identity configuration require a separate threat review and owner-approved scope.

## 4. Ordered migration sequence

### Stage 0 — establish the trusted-principal foundation

1. PR #58 is merged; its review, four exact-head CI jobs and mutation proofs are recorded on that PR.
2. Re-read the merged agora/principal.py and tests/test_principal.py before starting Stage 1.
3. Preserve the test-only boundary on SyntheticFixtureAdapter and its production-mode refusal.
4. Keep this plan aligned with the merged implementation as later slices land.

**Exit gate (met for the synthetic slice):** Principal contract and synthetic adapter are merged, reviewed and covered by exact-head CI. No OIDC or production adapter is implied.

### Stage 1 — make the PDP principal-first

1. Add or promote a principal-native PDP entry point that accepts Principal plus operation/resource, not a caller-supplied role.
2. Derive candidate roles only from principal.roles. Apply the operation's role matrix, issuer trust, expiry, assurance and explicit tenant/project scope before returning an allow.
3. Preserve the current sensitivity, source-role, purpose and retention checks. Missing purpose/retention for personal or sensitive downstream use remains a denial.
4. Make the audit-safe decision identify the principal subject and policy version without storing credentials or raw claims.
5. Migrate authorize() and the approval permission adapter to the principal-native path.
6. Keep the old role-string PDP only as a temporary internal compatibility surface during migration; it must not be reachable from an untrusted or production request path.

**Acceptance tests:** missing principal, expired principal, untrusted issuer, unknown role, insufficient assurance, empty project scope, wrong project, wrong tenant, missing sensitivity, sensitivity downgrade, missing purpose/retention and unsupported operation all deny. A request-supplied role cannot change the result.

**Mutation proofs:** remove each issuer, expiry, scope, assurance or role-membership check in turn; its named denial test must fail.

### Stage 2 — migrate decision approval

**Current implementation:** #80 merges a principal-native `authorize_decision_approval_principal(principal, resource)` gate requiring `approver`; `approve_as()` calls it and derives actor only from `principal.subject_id`. The separate public `approve(... actor, role, subject, ...)` API remains role-string based and is the next legacy-retirement gate.

1. Make the public approval entry point accept Principal and derive the approver ID from principal.subject_id.
2. Remove actor/role/subject as independent authority inputs. Do not merely wrap the old function while leaving an untrusted role parameter reachable.
3. Preserve exact decision version, fingerprint, scope and evidence-reference checks.
4. Preserve the review window and separation of duties: approver differs from proposer and reviewer.
5. Audit denials using allow-listed subject, operation, resource IDs, policy version and stable reason code only.
6. Ensure the decision-store transition is not reported as fully audited if the separate audit append fails.

**Acceptance tests:** an ordinary principal cannot approve; a forged request role cannot approve; missing/expired/out-of-scope principals deny without changing the decision store; proposer/reviewer self-approval remains denied; stale version/fingerprint/scope/evidence remains denied; audit failure is surfaced.

**Mutation proof:** bypass the principal PDP or remove each separation check; the corresponding approval test must fail.

### Stage 3 — migrate shared policy enforcement and data-boundary callers

**Current implementation on main:** #78/#79 provide the Principal-bound policy helper and three data-boundary hooks; #89 makes their public defaults `require_policy=True`. Explicit `False` is still accepted, `enforce_policy()` itself defaults `require_policy=False`, and `audit=None` still falls back to an unanchored local chain. The callback signature remains `(operation, resource)`, so the Principal is bound by the helper rather than passed as a first-class argument. This stage is not complete.

1. Replace the current operation/resource-only PolicyCallable contract with a principal-aware contract. The callback must receive the exact Principal used by the request and call the principal-native PDP.
2. Make enforce_policy validate the principal and preserve the current safe denial audit behaviour.
3. Distinguish genuinely ungoverned legacy/test calls from governed operations. A protected import, binding or scenario-input operation must not become a no-op because policy=None was passed.
4. Migrate the policy call sites in agora/tabular.py, agora/ontology/binding.py and agora/scenario_inputs.py to pass an adapter-issued principal.
5. Keep evaluation before source bytes or snapshot databases are read. Do not weaken the existing early-denial tests.
6. Preserve explicit purpose/retention propagation at the binding hook (#54); the principal migration must not drop those resource fields.

**Acceptance tests:** each boundary passes the same principal through the enforcement callback; absent principal and absent required policy deny before source/database reads; wrong project/tenant denies; policy exceptions deny and produce only safe audit metadata; public/internal synthetic fixtures continue to work under explicit test configuration.

**Mutation proofs:** remove principal validation, allow policy=None on a protected path, or move enforcement after the source read; the corresponding fail-closed/early-denial test must fail.

### Stage 4 — migrate outcome recording and review

**Current status: PARTIALLY IMPLEMENTED by merged PRs #70/#86/#89; exit gate remains open. #86 ignores caller-supplied resource data and #89 defaults the Principal wrappers to anchored audit, but they still delegate to public role-string outcome functions.**

- `record_outcome_as(store, *, principal, **kwargs)` derives recorder/actor from Principal and calls `decide_principal(..., required_role="operator")`.
- `review_outcome_as(store, decision_id, decision_version, outcome_id, *, principal, **kwargs)` derives reviewer/actor from Principal and requires `reviewer`.
- Both wrappers reject caller-supplied `recorder`/`reviewer`, `role` and `subject` authority fields.
- Both wrappers delegate to the legacy `record_outcome()` / `review_outcome()` role-string functions internally. The legacy APIs have not been removed or made unreachable from production-capable paths.
- #74 wires outcome append helpers to the supplied audit writer and adds an opt-in `require_anchored=True` gate on principal outcome wrappers; other legacy paths remain optional.

**Remaining Stage 4 work:**

1. Migrate the underlying outcome store/API so Principal is the authority source at the actual write boundary, not only a wrapper around a role-string function.
2. Remove caller-supplied role/subject mappings from every production-capable outcome path; keep legacy compatibility only in explicitly ungoverned/test contexts.
3. Require the configured anchored writer in protected outcome and review paths; no `audit=None` or plain-chain fallback.
4. Preserve exact approved decision-version linkage, measure allow-list, source hash, observed-only provenance, measurement window and append-only correction semantics.
5. Preserve separation of duties: the principal reviewing an outcome must differ from its recorder.
6. Keep outcome values, units, notes and reviewer rationale out of the shared audit chain.

**Acceptance tests:** simulated evidence remains rejected as observed; missing/invalid principal denies; a recorder cannot review their own outcome; a reader/approver cannot record or review unless the PDP explicitly grants the operation; exact source and approved-version checks remain intact; audit failures remain visible.

**Mutation proofs:** remove the observed-provenance check, reviewer separation, exact decision-version check or principal role check; the corresponding test must fail.

### Stage 5 — complete call-site migration and retire role-string authority

1. Search the complete repository for calls to decide(), authorize(), approve(), authorize_decision_approval(), record_outcome(), review_outcome() and policy callbacks.
2. Classify each remaining role-string use as test fixture, migration-only compatibility, or an actual authorization boundary. Record the owner and removal PR for every exception.
3. Migrate all production-capable call sites before changing the legacy API.
4. Deprecate the old role-string interfaces for one explicitly bounded migration window, with no production opt-in or caller-controlled fallback.
5. After the repository has no production-capable legacy callers, make legacy authorization fail closed and remove the compatibility interface in a separate reviewed change.
6. Re-run code search and the full CI matrix after each migration slice. Do not infer completion from a passing unit test alone.

**Stage 4 exit gate:** every governed outcome write/review consumes an adapter-issued Principal at the underlying authority boundary; actor, role and subject cannot be caller-selected; exact decision/version and observed-only provenance checks remain; reviewer differs from recorder; anchored audit is required in protected mode; legacy role-string paths are unreachable from production-capable calls and then removed in a separately reviewed change.

## 5. Rollout and deprecation gates

| Gate | Required evidence | Do not proceed if |
|---|---|---|
| G0 — principal foundation | Merged/reviewed principal slice, exact-head CI, mutation proofs | Met by merged #58 (synthetic slice only); do not proceed if principal.py changes without re-review. |
| G1 — PDP | Principal-only authorization tests and mutation proofs | Any request field can elevate role, scope or assurance. |
| G2 — approval | Exact version/fingerprint/scope/evidence and separation tests; no production-capable caller role assertion | `approve()` is disabled by default but remains in source behind the runtime environment variable `AGORA_TEST_ONLY_LEGACY_APPROVE=1`; prove non-test runtimes cannot enable it, or remove the compatibility path. |
| G3 — data boundaries | Early-denial tests for import, binding and scenario input | policy=None or a missing principal bypasses a governed path. |
| G4 — outcomes | Observed-only, exact-source and independent-review tests | Recorder/reviewer identity or role is caller-supplied. |
| G5 — retirement | Repository-wide call-site inventory and no production legacy callers | Any unresolved production-capable role-string call site remains. |

Deprecation must not create a temporary production escape hatch. If a compatibility wrapper is retained for tests, it must be restricted to synthetic fixtures and must not accept arbitrary role strings as proof of authority.

## 6. Non-goals and safety boundaries

- No OIDC implementation, identity-provider network access, real credentials, secrets or production authentication in this plan.
- No real personal/customer data, external drivers, network connectors or write-back.
- No simulation, calibration, backtest, forecast or study mutation.
- No changes to agora/sim/** without Claude's written approval and separate owner approval.
- Keep VALIDATED_PREDICTION_ENABLED=False.
- No changes to NCC Park Square, E0_C0_D0 or any existing study folder.
- This document is a migration plan, not permission to start any implementation stage. Each implementation slice requires its own scoped approval and draft PR.


## Current migration status — main 87c7cc95b3e7c231f52dca4924d6fc433c698462 (22 November 2026)

Verified on main:
- **#78/#79/#89:** `ingest_csv()`, `materialize_instances()` and `build_scenario_input()` now default to `require_policy=True`. Explicit `False` remains accepted. `enforce_policy()` itself defaults off, and its `audit=None` denial path still writes to an unanchored local `AuditChainStore`.
- **#80/#84/#89:** `approve_as()` is principal-native, ignores caller-supplied policy resource fields, and now defaults to `require_anchored=True`; explicit `False` remains accepted.
- **#82:** legacy role-string `approve()` remains in source and can be re-enabled by setting `AGORA_TEST_ONLY_LEGACY_APPROVE=1`; this is default-deny, not structurally test-only.
- **#86/#89:** Principal outcome wrappers ignore caller resource data and default to anchored audit, but still delegate to public role-string `record_outcome()` / `review_outcome()` APIs. Those legacy functions remain callable and accept optional audit.
- **#88:** `agora pilot --workdir <new-empty-directory>` runs a local synthetic sequence with explicit policy/anchor arguments, per-stage results, first-denial stop, audit verification and synthetic-labelled report. It does not persist the M2 run-record envelope or call `build_scenario_input()` / the simulation engine. Exact-head CI run `44945307064` passed 4/4.
- **#89:** merged at `87c7cc95`; default-True policy/anchor parameters passed exact-head CI run `44948055801` (4/4).

**Review coverage gap:** `tests/test_protected_defaults.py` checks the six signature defaults, but the runtime no-anchor test does not call `approve_as()` despite its name; runtime default-denial coverage for `materialize_instances()` and `build_scenario_input()` is not present in that file. The autouse fixture in `tests/conftest.py` relaxes these defaults for unmarked tests, so the protected-default marker is essential.

**Current blockers:** public role-string outcome APIs remain and the Principal wrappers still delegate to them; legacy `approve()` has a runtime environment escape; explicit False overrides remain; policy-denial `audit=None` is unanchored. Reconciliation (#57) and outcome dependency markers (#60) remain specifications only. No M1/M2 confirmation exists.

No OIDC, real credentials, network identity, simulation, real data or write-back is authorised. Keep `VALIDATED_PREDICTION_ENABLED=False`.