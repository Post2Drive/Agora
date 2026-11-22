# Principal Migration Plan

**Status:** Documentation plan only; no implementation or production-authentication approval  
**Assessment base:** main at `da008656f96a7fee774dbf89781ffbdbbe1adac6` (22 November 2026), including merged #58, #70, #71, #74, #78, #79, #80, #82, #84, #85, #86, #88, #89, #91, #92, #93, #94, #95, #96, #97, #99, #100, #101, #102, #106, #107, #109 and #111.
**Related design:** docs/IDENTITY_ADAPTER_SPEC.md (merged PR #51)

## 1. Objective and security invariant

Move every governed authorization boundary from caller-supplied role strings and subject mappings to an immutable principal issued by a trusted identity adapter. The policy decision point (PDP) must derive roles, tenant/project scope, assurance and actor identity from that principal. Request parameters must never be able to grant themselves an approver, operator or reviewer role.

The migration must preserve the current deny-by-default policy semantics, decision-version checks, evidence fingerprints, separation of duties, append-only records and allow-listed audit events. A missing, expired, malformed, untrusted or out-of-scope principal must fail closed.

This plan does not implement identity, enable OIDC, authorise network access, change production configuration or approve source-code work.

## 2. Verified current inventory

The following inventory was checked against main at the assessment SHA:

| Boundary | Current mainline interface | Migration concern |
|---|---|---|
| PDP | `decide(subject, role, operation, resource)` / `authorize(...)` remain internal role-string compatibility helpers; #111 restricts imports to the three-module allowlist. `principal_policy(principal, required_role)` still returns an ordinary closure. | The protected `PolicyCallable` is not yet a typed Principal capability; #111 does not prevent an arbitrary caller-supplied allow callable from passing `enforce_policy()`. |
| Approval permission adapter | `authorize_decision_approval(subject, role, resource)` was renamed `_legacy_authorize_decision_approval` and removed from `__all__` by #111; `authorize_decision_approval_principal(principal, resource)` remains the governed route. | Legacy role-string approval remains disabled outside the test-only flag; the public role-string authorizer is no longer exported. |
| Decision approval | `approve_as(..., principal=...)` is principal-native after #80/#84; #109 also guards `propose()`, `reject()`, `expire()` and `supersede()` with `require_anchored(audit)` before state mutation when `ANCHOR_REQUIRED=True`. Legacy `approve(... actor, role, subject, ...)` remains in source but is disabled outside the test-only flag. | #96 removes anchor opt-out kwargs from `approve_as()` and public outcome wrappers. #97 removes the env switch; legacy `approve()` is enabled only through the test-only `LEGACY_APPROVE_ENABLED` module flag. |
| Outcome recording | `record_outcome_as(..., principal=...)` is the only public route (#70/#86/#89/#92/#96). | #92 removes the public role-string export; #96 removes the public `require_anchored` opt-out kwarg. The wrapper derives actor and scope from Principal/stored decision. |
| Outcome review | `review_outcome_as(..., principal=...)` is the only public route (#70/#86/#89/#92/#96). | #92 removes the public role-string export; #96 removes the public `require_anchored` opt-out kwarg. The wrapper derives reviewer and scope from Principal/stored decision. |
| Shared enforcement hook | `PolicyCallable(operation, resource)` and `enforce_policy(policy, *, project, operation, resource, audit=None)` (#78/#97/#99). | Missing policy is denied and protected denials require an anchored writer, but any caller-supplied callable is accepted and may return `allow`; the hook does not verify that it is bound to an adapter-issued Principal. `principal_policy()` currently returns an ordinary closure, not a typed policy capability. Test-only protection flags are reset by fixtures. |
| Data-boundary callers | `ingest_csv()`, `materialize_instances()` and `build_scenario_input()` (#79/#89/#96). | #96 removes caller-supplied `require_policy` kwargs; #99 hardens direct helper calls; #111 restricts role-string PDP imports. The remaining gap is typed PrincipalPolicy validation at `enforce_policy()` and propagation through each caller. |

### 2.1 Principal implementation status

PR #58 established the synthetic Principal/PDP foundation. #70 added Principal-gated outcome wrappers; #92 retired public role-string outcome exports, and #96 removed public `require_anchored` opt-out kwargs. #78 added `principal_policy(principal, required_role)`; #79 threaded policy checks through import, binding and scenario-input boundaries; #89 made defaults True. #97 removed the legacy approval environment switch and unanchored `audit=None` fallback. #99 removed the direct `require_policy` override and requires an anchored writer for protected policy-denial events. #109 adds pre-mutation anchored-writer guards to the remaining decision lifecycle transitions; #111 restricts role-string PDP imports to an explicit allowlist and removes the public role-string approval authorizer. The operation/resource `PolicyCallable` is still an ordinary callable, and `principal_policy()` still returns an ordinary closure; typed PrincipalPolicy validation remains the active M1 migration gap.

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
6. #111 now restricts imports of the role-string PDP (`decide`/`authorize`) to the allowlisted internal modules `principal.py`, `decisions/permissions.py` and `decisions/outcomes.py`, and removes the public role-string approval authorizer. Do not expand that allowlist. This does not validate a policy callback's provenance; the typed PrincipalPolicy capability remains the active M1 gap.

**Acceptance tests:** missing principal, expired principal, untrusted issuer, unknown role, insufficient assurance, empty project scope, wrong project, wrong tenant, missing sensitivity, sensitivity downgrade, missing purpose/retention and unsupported operation all deny. A request-supplied role cannot change the result.

**Mutation proofs:** remove each issuer, expiry, scope, assurance or role-membership check in turn; its named denial test must fail.

### Stage 2 — migrate decision approval

**Current implementation:** #80 merges a principal-native `authorize_decision_approval_principal(principal, resource)` gate requiring `approver`; `approve_as()` calls it and derives actor only from `principal.subject_id`. The legacy `approve(... actor, role, subject, ...)` function remains in source but is disabled outside the test-only flag; #111 renames its role-string authorizer private and removes the public export.

1. Make the public approval entry point accept Principal and derive the approver ID from principal.subject_id.
2. Remove actor/role/subject as independent authority inputs. Do not merely wrap the old function while leaving an untrusted role parameter reachable.
3. Preserve exact decision version, fingerprint, scope and evidence-reference checks.
4. Preserve the review window and separation of duties: approver differs from proposer and reviewer.
5. Audit denials using allow-listed subject, operation, resource IDs, policy version and stable reason code only.
6. Ensure the decision-store transition is not reported as fully audited if the separate audit append fails.

**Acceptance tests:** an ordinary principal cannot approve; a forged request role cannot approve; missing/expired/out-of-scope principals deny without changing the decision store; proposer/reviewer self-approval remains denied; stale version/fingerprint/scope/evidence remains denied; audit failure is surfaced.

**Mutation proof:** bypass the principal PDP or remove each separation check; the corresponding approval test must fail.

### Stage 3 — migrate shared policy enforcement and data-boundary callers

**Current implementation on main:** #78/#79/#89/#96 provide Principal-bound policy plumbing and remove caller opt-out kwargs from the three protected data-boundary entry points. #97 removes the legacy approval env switch and unanchored `audit=None` fallback. #99 removes the direct `require_policy` override and validates supplied denial writers with `require_anchored()`. #109 adds pre-mutation anchored-writer guards to `propose()`, `reject()`, `expire()` and `supersede()` when `ANCHOR_REQUIRED=True`; optional signature annotations do not permit missing/plain writers on the protected path. #111 now restricts role-string PDP imports to the allowlisted internal modules and removes the public role-string approval authorizer. The principal-aware policy contract is still incomplete: `PolicyCallable` remains an ordinary `(operation, resource)` callable; `enforce_policy()` accepts any callable and does not prove it is bound to an adapter-issued Principal. `principal_policy()` still returns an ordinary closure, so a caller-supplied always-allow callback can pass the protected presence check. Treat this as an M1 fail-closed gap until the typed PrincipalPolicy capability is enforced and the governed data-boundary callers are migrated.

1. Replace the current operation/resource-only PolicyCallable contract with a principal-aware contract. The callback must receive the exact Principal used by the request and call the principal-native PDP.
2. Make enforce_policy validate the principal and preserve the current safe denial audit behaviour.
3. Distinguish genuinely ungoverned legacy/test calls from governed operations. A protected import, binding or scenario-input operation must not become a no-op because policy=None was passed.
4. Migrate the policy call sites in agora/tabular.py, agora/ontology/binding.py and agora/scenario_inputs.py to pass an adapter-issued principal.
5. Keep evaluation before source bytes or snapshot databases are read. Do not weaken the existing early-denial tests.
6. Preserve explicit purpose/retention propagation at the binding hook (#54); the principal migration must not drop those resource fields.

**Acceptance tests:** each boundary passes the same principal through the enforcement callback; absent principal and absent required policy deny before source/database reads; wrong project/tenant denies; policy exceptions deny and produce only safe audit metadata; public/internal synthetic fixtures continue to work under explicit test configuration.

**Mutation proofs:** remove principal validation, allow policy=None on a protected path, or move enforcement after the source read; the corresponding fail-closed/early-denial test must fail.

### Stage 4 — migrate outcome recording and review

**Current status: PUBLIC ROLE-STRING ROUTES RETIRED by merged #92; public wrapper opt-outs removed by #96; direct policy-helper bypasses closed by #99.** `record_outcome_as()` and `review_outcome_as()` are the only public outcome write/review routes and derive actor identity from Principal. The underlying `_record_outcome()` / `_review_outcome()` helpers remain private implementation details; their optional audit parameters are not a separate public security boundary.
The separate read-only `agora outcomes held --decisions <db>` command (#102) surfaces disputed, unreviewed, invalid-history and orphan-review cases; #106 normalizes connection-open SQLite errors to `STORE_UNREADABLE` / exit 2. Neither changes the Principal write boundary or implements dependency markers/propagation.

- `record_outcome_as(store, *, principal, **kwargs)` derives recorder/actor from Principal and calls `decide_principal(..., required_role="operator")`.
- `review_outcome_as(store, decision_id, decision_version, outcome_id, *, principal, **kwargs)` derives reviewer/actor from Principal and requires `reviewer`.
- Both wrappers reject caller-supplied `recorder`/`reviewer`, `role` and `subject` authority fields.
- #92 changes the internal calls to `_record_outcome()` / `_review_outcome()` and removes the public role-string names from module exports. The private helpers still receive Principal-derived role/subject values; do not treat Python underscore naming as an independent security boundary.
- #74 wires outcome append helpers to the supplied audit writer; #96 removes the `require_anchored` opt-out kwargs from the three public Principal write wrappers. Private helpers can still be called without an audit writer; do not treat Python underscore naming as an independent security boundary.

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
| G2 — approval | Exact version/fingerprint/scope/evidence and separation tests; no production-capable caller role assertion | Legacy `approve()` is disabled by default; #97 removes the environment-variable switch and confines enablement to the test-only `agora.protection.LEGACY_APPROVE_ENABLED` flag. |
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

## Current migration status — main `da008656f96a7fee774dbf89781ffbdbbe1adac6` (22 November 2026)

Verified on main:
- **#78/#79/#89/#96/#99/#111:** protected data-boundary functions no longer accept caller-supplied `require_policy` opt-out kwargs; #97 removes the unanchored fallback when `audit=None`; #99 validates anchored denial writers. #111 restricts role-string PDP imports to allowlisted modules and removes the public role-string approval authorizer. `enforce_policy()` still accepts any callable and `principal_policy()` still returns an ordinary closure, so typed PrincipalPolicy validation remains open.
- **#80/#84/#89/#96:** `approve_as()` is principal-native, ignores caller-supplied policy resource fields, and no longer accepts a public `require_anchored` opt-out kwarg.
- **#82/#97:** legacy role-string `approve()` remains in source but the environment switch is removed; only the test-only `LEGACY_APPROVE_ENABLED` module flag enables it. #111 renames the internal role-string approval authorizer private and removes it from `permissions.__all__`.
- **#70/#86/#89/#92/#96:** public outcome writes route through `record_outcome_as()` / `review_outcome_as()`; #92 retires role-string exports and #96 removes public anchor opt-out kwargs. Private helpers still accept optional audit internally.
- **#88:** `agora pilot --workdir <new-empty-directory>` runs a local synthetic sequence with explicit policy/anchor arguments, per-stage results, first-denial stop, audit verification and synthetic-labelled report. It does not persist the M2 run-record envelope or call `build_scenario_input()` / the simulation engine. Exact-head CI run `44945307064` passed 4/4.
- **#89:** default-True policy/anchor parameters passed exact-head CI run `44948055801` (4/4).
- **#92:** public role-string outcome exports retired; merged at `a191b587`, exact-head CI run `44950576945` passed 4/4.
- **#94:** `agora.cli` lazy-loads `.sim.engine` only inside simulation-dependent handlers; fresh-process tests cover CLI import and pilot help dispatch. Exact-head CI run `44955653075` passed 4/4.
- **#96:** removes `require_policy` / `require_anchored` opt-out kwargs from six protected public entry points; exact-head CI run `44956724553` passed 4/4.
- **#97:** removes the legacy approval env switch and defaults direct policy enforcement from `POLICY_REQUIRED`; exact-head CI run `44958568446` passed 4/4.
- **#99:** removes the direct `require_policy` override and requires an anchored writer for protected policy-denial events; exact-head CI run `44960946006` passed 4/4.
- **#109:** adds pre-mutation anchored-writer guards to `propose()`, `reject()`, `expire()` and `supersede()` when `ANCHOR_REQUIRED=True`; exact-head CI run `44975437439` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs.
 - **#100/#104:** adds and hardens the read-only decision lifecycle/audit detector; #104 validates immutable source transition metadata, expected audit operation/exact resource IDs and partial-open cleanup (run `44968039923`, 4/4). Anchor verification, queue/repair and outcome/review reconciliation remain unimplemented. #102 separately adds a read-only held-outcome list; #106 makes connection-open errors fail closed, not markers.

**Review coverage gap:** `tests/test_protected_defaults.py` checks the six signature defaults, but the runtime no-anchor test does not call `approve_as()` despite its name; runtime default-denial coverage for `materialize_instances()` and `build_scenario_input()` is not present in that file. The autouse fixture in `tests/conftest.py` relaxes these defaults for unmarked tests, so the protected-default marker is essential.

**Current blockers:** typed PrincipalPolicy enforcement and data-boundary migration remain; #111 restricts role-string PDP imports to the allowlist but does not validate callback provenance. #109 closes the pre-mutation lifecycle writer bypass for `propose()`/`reject()`/`expire()`/`supersede()` in protected mode, but it does not complete principal-first policy authority. #100/#104 provide only a read-only decision lifecycle detector with no anchor check or queue/repair workflow; #102/#106 only list held outcomes and fail closed on connection-open errors. #107 provides read-only decision timeline and chain-vs-local-anchor verification; it does not implement backup/restore or tamper recovery. Dependency markers (#60), backup/restore and tamper drill, run-record persistence, checked-in fixture set, tested operator runbook and logged dress rehearsal remain outstanding. No M1/M2 confirmation exists.

No OIDC, real credentials, network identity, simulation, real data or write-back is authorised. Keep `VALIDATED_PREDICTION_ENABLED=False`.