# Principal Migration Plan

**Status:** Documentation plan only; no implementation or production-authentication approval  
**Assessment base:** `main` at `5a579eb2c75257764ec8752273f3241544cf4bf8` (22 November 2026; #147 marker-open outbox merged, recovery partial).
**Related design:** docs/IDENTITY_ADAPTER_SPEC.md (merged PR #51)

## 1. Objective and security invariant

Move every governed authorization boundary from caller-supplied role strings and subject mappings to an immutable principal issued by a trusted identity adapter. The policy decision point (PDP) must derive roles, tenant/project scope, assurance and actor identity from that principal. Request parameters must never be able to grant themselves an approver, operator or reviewer role.

The migration must preserve the current deny-by-default policy semantics, decision-version checks, evidence fingerprints, separation of duties, append-only records and allow-listed audit events. A missing, expired, malformed, untrusted or out-of-scope principal must fail closed.

This plan does not implement identity, enable OIDC, authorise network access, change production configuration or approve source-code work.

## 2. Verified current inventory

The following inventory was checked against main at the assessment SHA:

| Boundary | Current mainline interface | Migration concern |
|---|---|---|
| PDP | `decide(subject, role, operation, resource)` / `authorize(...)` remain role-string compatibility APIs; #78 adds `principal_policy(principal, required_role)`. #99 removes the direct `require_policy` override from `enforce_policy()` and requires an anchored writer for protected denial events. |
| Approval permission adapter | `authorize_decision_approval(subject, role, resource)` remains legacy; #80 adds `authorize_decision_approval_principal(principal, resource)` requiring the `approver` role. | Both adapters exist; the role-string adapter remains callable and the principal-native path is used by `approve_as()`. |
| Decision approval | `approve_as(..., principal=...)` is principal-native after #80/#84; #109 also guards `propose()`, `reject()`, `expire()` and `supersede()` with `require_anchored(audit)` before state mutation when `ANCHOR_REQUIRED=True`. Legacy `approve(... actor, role, subject, ...)` remains in source but is disabled outside the test-only flag. | #96 removes anchor opt-out kwargs from `approve_as()` and public outcome wrappers. #97 removes the env switch; legacy `approve()` is enabled only through the test-only `LEGACY_APPROVE_ENABLED` module flag. |
| Outcome recording | `record_outcome_as(..., principal=...)` is the only public route (#70/#86/#89/#92/#96). | #92 removes the public role-string export; #96 removes the public `require_anchored` opt-out kwarg. The wrapper derives actor and scope from Principal/stored decision. |
| Outcome review | `review_outcome_as(..., principal=...)` is the only public route (#70/#86/#89/#92/#96). | #92 removes the public role-string export; #96 removes the public `require_anchored` opt-out kwarg. The wrapper derives reviewer and scope from Principal/stored decision. |
| Shared enforcement hook | `BoundPolicy` from `principal_policy()` and `enforce_policy(policy, *, project, operation, resource, audit=None)` (#113). | Protected mode rejects raw callables via `PRINCIPAL_BOUND_REQUIRED=True`; `BoundPolicy` re-checks its Principal on each call. The protected gate is implemented by #113; `BoundPolicy` rechecks the bound Principal at each call. The identity adapter remains synthetic-fixture-only. Test-only relaxation remains fixture-controlled. |
| Data-boundary callers | `ingest_csv()`, `materialize_instances()` and `build_scenario_input()` (#79/#89/#96). | #96 removes caller-supplied `require_policy` kwargs; #99 also hardens direct helper calls. Principal-aware migration of the role-string PDP compatibility surface remains separate. |

### 2.1 Principal implementation status

PR #58 established the synthetic Principal/PDP foundation. #111 restricts role-string PDP/permission imports to the internal allowlist and makes the legacy approval authorizer private. #113 adds `BoundPolicy`, changes `principal_policy()` to return it, and makes protected `enforce_policy()` reject arbitrary callables under `PRINCIPAL_BOUND_REQUIRED=True`; the capability re-checks issuer, expiry, scope and role on each invocation. The protected Principal-bound policy gate is implemented by #113. The adapter remains synthetic-only; no real identity provider, credentials or network access are part of this milestone. The synthetic identity adapter remains the only adapter; no real identity integration is implied.

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

**Current implementation on main:** #111 restricts role-string PDP/permission imports to the internal allowlist and makes the legacy role-string approval authorizer private. #113 adds `BoundPolicy`; `principal_policy()` returns that typed capability, and protected `enforce_policy()` requires it under `PRINCIPAL_BOUND_REQUIRED=True`, rejects arbitrary callables and re-evaluates the bound Principal on every call. #96/#97/#99 preserve required-policy and anchored-denial defaults; #109 guards the remaining decision-lifecycle mutations with an anchored writer. This closes the M1 protected Principal-bound policy gate. The only identity adapter remains `SyntheticFixtureAdapter`; no OIDC or production identity provider is claimed.

**M1 acceptance evidence:** #113 exact-head Actions run `44979668275` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. Its mutation proofs reject a skipped BoundPolicy check, a forged `is_principal_bound` result, a disabled default, a skipped Principal re-check and a passing `None` policy. #111 makes the role-string approval authorizer private and limits direct PDP imports to the internal allowlist.

1. `principal_policy(principal, required_role=...)` returns a `BoundPolicy` carrying the Principal; callers do not supply authority through resource fields or role strings.
2. Protected `enforce_policy()` accepts only `BoundPolicy`; missing policy, raw callables, invalid issuers, expired principals, wrong scope and insufficient role/assurance deny.
3. Preserve evaluation before source bytes or snapshot databases are read in `agora/tabular.py`, `agora/ontology/binding.py` and `agora/scenario_inputs.py`.
4. Preserve explicit purpose/retention propagation at the binding hook (#54).
5. Keep legacy `approve()` disabled except through the test-only `LEGACY_APPROVE_ENABLED` flag; keep role-string PDP compatibility functions internal and allowlisted by #111.
6. Treat the synthetic fixture adapter as test/pilot identity only. Production identity, OIDC and credentials are not implemented or authorised.

**Acceptance:** the merged #111/#113 implementation and exact-head CI close the M1 policy-binding gate; the identity trust boundary remains synthetic-only.

**Mutation proofs:** the #113 PR records five caught mutations covering the BoundPolicy gate, default-on flag, Principal re-check and missing-policy denial. The #111 PR records import-allowlist and private-export mutations. Do not re-open this as an unimplemented M1 gate; any production identity integration is separate future scope.

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

## Current migration status — main `5a579eb2c75257764ec8752273f3241544cf4bf8` (22 November 2026)

Verified on main:
- **#78/#79/#89/#96/#99:** protected data-boundary functions no longer accept caller-supplied `require_policy` opt-out kwargs. #97 removes the unanchored fallback when `audit=None`; #99 removes the direct helper override and validates supplied denial writers with `require_anchored()`. Role-string PDP compatibility functions remain only as internal allowlisted compatibility surfaces after #111; protected callbacks require Principal-bound `BoundPolicy` after #113. The adapter remains synthetic-only.
- **#80/#84/#89/#96:** `approve_as()` is principal-native, ignores caller-supplied policy resource fields, and no longer accepts a public `require_anchored` opt-out kwarg.
- **#82/#97:** legacy role-string `approve()` remains in source but the environment switch is removed; only the test-only `LEGACY_APPROVE_ENABLED` module flag enables it.
- **#70/#86/#89/#92/#96:** public outcome writes route through `record_outcome_as()` / `review_outcome_as()`; #92 retires role-string exports and #96 removes public anchor opt-out kwargs. Private helpers still accept optional audit internally.
- **#88/#123/#125/#130/#132/#135:** `agora pilot --workdir <new-empty-directory>` remains the M1 guided synthetic path; #125 adds the checked-in fixture and `agora pilot list/start`. #130 adds partial run-record validation; #132 pins the fixture manifest, rejects direct fixture symlinks/empty versions and a direct symlinked workdir root; #135 rejects symlink/reparse-point workdir ancestors and filters linked fixture directories. #144/#145 prove clean-checkout install/start plus exact run-record/false-flag/console-script no-engine assertions (head 6338c5a5; exact-head CI 45021238785 passed 4/4); full RUN_PROVENANCE_SPEC fields, strict nested validation and failure-atomic publication remain outstanding.
- **#89:** default-True policy/anchor parameters passed exact-head CI run `44948055801` (4/4).
- **#92:** public role-string outcome exports retired; merged at `a191b587`, exact-head CI run `44950576945` passed 4/4.
- **#94:** `agora.cli` lazy-loads `.sim.engine` only inside simulation-dependent handlers; fresh-process tests cover CLI import and pilot help dispatch. Exact-head CI run `44955653075` passed 4/4.
- **#96:** removes `require_policy` / `require_anchored` opt-out kwargs from six protected public entry points; exact-head CI run `44956724553` passed 4/4.
- **#97:** removes the legacy approval env switch and defaults direct policy enforcement from `POLICY_REQUIRED`; exact-head CI run `44958568446` passed 4/4.
- **#99:** removes the direct `require_policy` override and requires an anchored writer for protected policy-denial events; exact-head CI run `44960946006` passed 4/4.
- **#109:** adds pre-mutation anchored-writer guards to `propose()`, `reject()`, `expire()` and `supersede()` when `ANCHOR_REQUIRED=True`; exact-head CI run `44975437439` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs.
 - **#100/#104:** adds and hardens the read-only decision lifecycle/audit detector; #104 validates immutable source transition metadata, expected audit operation/exact resource IDs and partial-open cleanup (run `44968039923`, 4/4). #119 adds read-only sidecar-anchor verification before decision reconciliation classification; #115 adds a separate API-only missing-decision-event repair. #147 adds marker-open outbox persistence, but crash-window replay still fails against the real chain's duplicate event-ID guard; transition-event recovery, concurrent delivery and legacy-row backfill remain open. Stable correlation queue and outcome/review audit reconciliation remain unimplemented. #102/#106 provide a separate read-only held-outcome list; #116 adds the first marker slice but not reconciliation.

**Review coverage gap:** `tests/test_protected_defaults.py` checks the six signature defaults, but the runtime no-anchor test does not call `approve_as()` despite its name; runtime default-denial coverage for `materialize_instances()` and `build_scenario_input()` is not present in that file. The autouse fixture in `tests/conftest.py` relaxes these defaults for unmarked tests, so the protected-default marker is essential.

**Current blockers:** the public role-string approval authorizer is private and role-string PDP imports are restricted to the internal allowlist by #111; `BoundPolicy` is required by protected `enforce_policy()` under #113. The remaining identity limitation is that `SyntheticFixtureAdapter` is synthetic-only; no OIDC, production identity provider, credential handling or real-data connector is implemented or authorised. Claude's exact 09:05 IST log entry confirms M1 reached. The current owner instruction approves local synthetic M2 implementation only, after the post-M1 hardening sequence (closed by merged #122); no production identity, OIDC, credentials, network access or other prohibited scope is authorised. Do not treat the remaining internal role-string compatibility functions as public authorization surfaces.