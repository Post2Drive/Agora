# Principal Migration Plan

**Status:** Documentation plan only; no implementation or production-authentication approval  
**Assessment base:** main at 98850910559d0e4d72be127d1412dddcc5326cb8 (21 November 2026)  
**Related design:** docs/IDENTITY_ADAPTER_SPEC.md (merged PR #51)

## 1. Objective and security invariant

Move every governed authorization boundary from caller-supplied role strings and subject mappings to an immutable principal issued by a trusted identity adapter. The policy decision point (PDP) must derive roles, tenant/project scope, assurance and actor identity from that principal. Request parameters must never be able to grant themselves an approver, operator or reviewer role.

The migration must preserve the current deny-by-default policy semantics, decision-version checks, evidence fingerprints, separation of duties, append-only records and allow-listed audit events. A missing, expired, malformed, untrusted or out-of-scope principal must fail closed.

This plan does not implement identity, enable OIDC, authorise network access, change production configuration or approve source-code work.

## 2. Verified current inventory

The following inventory was checked against main at the assessment SHA:

| Boundary | Current mainline interface | Migration concern |
|---|---|---|
| PDP | agora/policy.py: decide(subject, role, operation, resource) and authorize(subject, role, operation, resource) | The role is a string supplied by the caller of the PDP. |
| Approval permission adapter | agora/decisions/permissions.py: authorize_decision_approval(subject, role, resource) | Passes the caller's role directly to decide(). |
| Decision approval | agora/decisions/approval.py: approve(... actor, role, subject, ...) | Actor and role are separate caller inputs; the subject mapping is checked against actor but is not an authenticated principal. |
| Outcome recording | agora/decisions/outcomes.py: record_outcome(... recorder, role, subject, ...) | Recorder identity and operator role are caller-supplied values. |
| Outcome review | agora/decisions/outcomes.py: review_outcome(... reviewer, role, subject, ...) | Reviewer identity and reviewer role are caller-supplied values. |
| Shared enforcement hook | agora/policy_enforcement.py: PolicyCallable(operation, resource) and enforce_policy(policy, ...) | The callback can close over identity/role; enforce_policy itself receives no principal. policy=None is currently a no-op. |
| Data-boundary callers | agora/tabular.py, agora/ontology/binding.py, agora/scenario_inputs.py | Ingestion, binding and scenario-input policy calls must receive the same trusted principal context and must not silently bypass a required policy. |

### 2.1 Principal implementation status

PR #58, branch feat/identity-principal, is an open draft at head 84d6805ec8023a16ef139bf8af04253e0c6f8193. Its exact-head workflow run 44902246519 completed successfully across all four Ubuntu/Windows × Python 3.11/3.12 jobs. It is not merged and must not be described as mainline capability.

That draft adds agora/principal.py with an immutable Principal, Assurance, a test-only SyntheticFixtureAdapter, decide_principal(), and approve_as(). The synthetic adapter refuses production mode. The current approve_as() implementation is a bridge: it derives the role from the principal, then delegates to the existing role-string approve() implementation. It does not complete the migration of the public approval path or other call sites.

Do not build later steps on the assumption that PR #58 is merged. Re-read its final merged head and tests before implementation begins.

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

1. Independently review PR #58 at its final head; confirm the four exact-head CI jobs and the named mutation proofs.
2. Merge only through the owner's review process. A green CI run alone is not approval.
3. Preserve the test-only boundary on SyntheticFixtureAdapter and its production-mode refusal.
4. Reconcile this plan against the merged implementation; do not assume branch-only APIs exist on main.

**Exit gate:** Principal contract and synthetic adapter are merged, reviewed and covered by exact-head CI. No OIDC or production adapter is implied.

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

1. Make the public approval entry point accept Principal and derive the approver ID from principal.subject_id.
2. Remove actor/role/subject as independent authority inputs. Do not merely wrap the old function while leaving an untrusted role parameter reachable.
3. Preserve exact decision version, fingerprint, scope and evidence-reference checks.
4. Preserve the review window and separation of duties: approver differs from proposer and reviewer.
5. Audit denials using allow-listed subject, operation, resource IDs, policy version and stable reason code only.
6. Ensure the decision-store transition is not reported as fully audited if the separate audit append fails.

**Acceptance tests:** an ordinary principal cannot approve; a forged request role cannot approve; missing/expired/out-of-scope principals deny without changing the decision store; proposer/reviewer self-approval remains denied; stale version/fingerprint/scope/evidence remains denied; audit failure is surfaced.

**Mutation proof:** bypass the principal PDP or remove each separation check; the corresponding approval test must fail.

### Stage 3 — migrate shared policy enforcement and data-boundary callers

1. Replace the current operation/resource-only PolicyCallable contract with a principal-aware contract. The callback must receive the exact Principal used by the request and call the principal-native PDP.
2. Make enforce_policy validate the principal and preserve the current safe denial audit behaviour.
3. Distinguish genuinely ungoverned legacy/test calls from governed operations. A protected import, binding or scenario-input operation must not become a no-op because policy=None was passed.
4. Migrate the policy call sites in agora/tabular.py, agora/ontology/binding.py and agora/scenario_inputs.py to pass an adapter-issued principal.
5. Keep evaluation before source bytes or snapshot databases are read. Do not weaken the existing early-denial tests.
6. Preserve explicit purpose/retention propagation at the binding hook (#54); the principal migration must not drop those resource fields.

**Acceptance tests:** each boundary passes the same principal through the enforcement callback; absent principal and absent required policy deny before source/database reads; wrong project/tenant denies; policy exceptions deny and produce only safe audit metadata; public/internal synthetic fixtures continue to work under explicit test configuration.

**Mutation proofs:** remove principal validation, allow policy=None on a protected path, or move enforcement after the source read; the corresponding fail-closed/early-denial test must fail.

### Stage 4 — migrate outcome recording and review

1. Change record_outcome() to accept Principal; derive recorder from principal.subject_id and require the operator permission from principal.roles.
2. Change review_outcome() to accept Principal; derive reviewer from principal.subject_id and require the reviewer permission.
3. Remove caller-supplied role and subject mappings from the public outcome APIs.
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

**Exit gate:** no untrusted request can supply its own role, actor, tenant, project scope or assurance; every governed boundary consumes an adapter-issued principal; the legacy path is unreachable in production and then removed.

## 5. Rollout and deprecation gates

| Gate | Required evidence | Do not proceed if |
|---|---|---|
| G0 — principal foundation | Merged/reviewed principal slice, exact-head CI, mutation proofs | PR #58 is still draft or its head changed without re-verification. |
| G1 — PDP | Principal-only authorization tests and mutation proofs | Any request field can elevate role, scope or assurance. |
| G2 — approval | Exact version/fingerprint/scope/evidence and separation tests | Legacy approve() remains reachable from an untrusted path. |
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
