# Identity Adapter Specification

**Status:** Design specification; not implementation approval  
**Rung:** 6 — trusted identity boundary  
**Scope:** Documentation only. Synthetic fixtures and local tests are the only permitted initial implementation context.

## 1. Problem and security objective

The current approval boundary accepts a caller-supplied `role`. That makes the caller's assertion of authority indistinguishable from an authenticated identity claim. A caller must not be able to grant itself an approver role, choose a broader tenant/project scope, or raise its assurance level by constructing an ordinary request object.

Introduce a trusted-principal boundary. Authorization decisions consume a principal issued by a configured identity adapter, not a free-form role string. The policy decision point (PDP) remains responsible for evaluating whether the principal's verified claims permit the requested operation on the target resource.

This specification does not claim that an identity provider, OIDC integration, or production authentication exists today.

## 2. Principal contract

Define an immutable, validated principal value with at least:

| Field | Contract |
| --- | --- |
| `subject_id` | Stable, non-empty subject identifier from the verified issuer; never a display name. |
| `tenant_id` | Explicit tenant boundary. Required where the deployment is tenant-scoped; no implicit wildcard. |
| `project_ids` | Explicit set of project scopes. Empty means no project access, not all projects. |
| `roles` | Normalised set of internal Agora roles derived by the adapter from verified claims and configured mappings. |
| `assurance_level` | Normalised assurance value from a configured mapping; unknown values are rejected, not promoted. |
| `issuer` | Exact configured issuer identifier that authenticated the subject. |
| `expires_at` | Expiry timestamp in UTC; the principal is invalid at or after expiry. |

Recommended additional provenance fields: `issued_at`, `authentication_method`, `claims_version`, and a non-secret `credential_id` or token identifier suitable for correlation. Never retain raw bearer tokens, passwords, private keys, or unrestricted raw claims in the principal or audit record.

The principal must be immutable after construction. Validation must reject missing required fields, malformed timestamps, empty subject/issuer, unknown roles, invalid scope shapes, expired credentials, and unsupported assurance values. Use explicit typed values/enums for roles and assurance levels.

## 3. Trust boundary and role derivation

1. An adapter validates the credential's authenticity, issuer, audience/client, expiry, and applicable token constraints before constructing a principal.
2. The adapter maps verified issuer claims through a configured allow-list of claim names and values to internal Agora roles. The mapping is configuration, not caller input.
3. Scope is derived from verified claims and constrained by server-side tenant/project membership. A request may narrow scope but may not enlarge it.
4. Assurance is derived from verified authentication context using an explicit mapping. Missing or unrecognised assurance maps to the lowest permitted state or causes rejection, according to the operation's policy; it must never be silently elevated.
5. The PDP evaluates the resulting principal against operation, resource, tenant/project scope, sensitivity, and assurance requirements.

A request body field such as `role="approver"` must never be accepted as evidence of authority. Do not merge caller-supplied roles into an adapter-issued principal.

## 4. Adapter design

### 4.1 Local synthetic test adapter — first implementation

Provide a test-only adapter that issues principals from clearly synthetic fixtures. It must be unavailable in production configuration and must not accept arbitrary client-supplied role/scope values in a production request path.

The test adapter should require an explicit fixture identity key and resolve that key to a fixed fixture definition maintained by the test. Tests should be able to construct reviewer, approver, ordinary-user, expired, wrong-tenant, wrong-project, and insufficient-assurance principals without real credentials or personal data.

### 4.2 OIDC adapter — later, separate stage

An OIDC adapter is a future integration, not part of the first implementation. It must validate signature using trusted issuer metadata/JWKS, issuer, audience, expiry/not-before, permitted algorithms, and required authentication context. Key rotation and issuer/JWKS unavailability need explicit handling. Never accept an unsigned token, a token from an unconfigured issuer, or an unverified decoded claim set.

OIDC deployment requires a separate threat review, configuration and secret-management plan, integration tests, and owner approval.

## 5. Authorization API changes

The target API shape is principal-based:

- `decide(principal: Principal, operation: str, resource: Resource, ...)`
- `approve(principal: Principal, decision_id: str, expected_version: int, ...)`

The exact parameter order and compatibility strategy should follow the current module interfaces during implementation. The key invariant is that neither function accepts a caller-controlled role as its authorization source.

The PDP must check, at minimum:

- principal validity and expiry at decision time;
- issuer is configured and trusted by the selected adapter;
- required role is present in the adapter-derived role set;
- tenant and project scope contain the target resource;
- assurance level meets the operation's minimum;
- decision state/version and separation-of-duties requirements remain satisfied.

Approval must use the same trusted principal contract as the PDP. A principal that proposed a decision must not approve it where policy requires independent approval. Missing principal or adapter failure denies the operation.

### Migration

1. Add the principal type and test adapter without changing production authorization behaviour.
2. Add principal-based PDP and approval entry points, with tests proving role/scope/assurance are derived from fixtures.
3. Migrate all internal call sites to pass adapter-issued principals.
4. Remove or hard-fail legacy role-string authorization. Do not keep a silent fallback that trusts caller-supplied roles.
5. Only after separate approval, design and implement an OIDC adapter.
6. Update documentation and operational configuration to identify the trusted adapter and issuer allow-list.

During migration, any compatibility shim must be internal-only, explicitly marked deprecated, and incapable of authorizing production requests from an untrusted role string.

## 6. Audit requirements

Authorization and approval audit events should record only allow-listed, non-secret identity metadata needed for accountability:

- event type and timestamp;
- subject identifier and issuer;
- tenant/project scope identifiers required to explain the authorization;
- normalised roles and assurance level at decision time;
- operation, resource identifier, decision identifier/version where applicable;
- allow/deny outcome and stable policy reason code;
- adapter identifier and claims/configuration version.

Do not place bearer tokens, raw claims, credentials, personal notes, or unrestricted free text in the audit chain. Audit data must describe the principal as evaluated at the time; later role changes must not rewrite historical events.

## 7. Failure behaviour

Fail closed for missing/invalid/expired principal, untrusted issuer, invalid audience, unknown role mapping, missing scope, scope mismatch, insufficient assurance, adapter outage, malformed claims, and policy evaluation failure. Return a stable denial/error category without exposing token-validation internals to the caller. Do not downgrade to anonymous or caller-supplied role authorization.

## 8. Acceptance tests

Use synthetic fixtures only.

1. Valid fixture maps to the exact expected subject, tenant, projects, roles, issuer, assurance, and expiry.
2. Caller-supplied `role="approver"` cannot elevate an ordinary fixture.
3. Unknown claim values and unknown internal roles are rejected.
4. Expired and malformed principals are rejected.
5. Wrong tenant and wrong project are denied.
6. Insufficient assurance is denied for a sensitive operation.
7. Missing principal and adapter errors fail closed.
8. An ordinary user cannot approve; an authorized approver can approve only within scope and subject to separation-of-duties rules.
9. Decision version mismatch remains denied.
10. Audit events contain the expected allow-listed identity fields and no token/raw-claim/free-text leakage.
11. Legacy role-string path cannot authorize a production request.
12. Local synthetic adapter is disabled by production configuration.

## 9. Mutation proofs

The test suite should demonstrate that these deliberate regressions are caught:

- Replace adapter-derived roles with caller-supplied roles.
- Skip issuer or expiry validation.
- Treat empty scope as wildcard.
- Skip tenant/project comparison.
- Ignore assurance requirements.
- Permit a proposer to self-approve where prohibited.
- Fall back to a legacy role string when principal is absent.
- Add raw token or unrestricted claims to an audit event.
- Enable the local synthetic adapter in production mode.

Each mutation must fail at least one named test. Mutation execution belongs to the implementation/verification step, not this documentation task.

## 10. Explicit non-goals and gates

- No production identity provider or OIDC integration is implemented by this document.
- No credentials, real user identities, network calls, or external identity systems are used.
- This document does not authorize changes to source code, policy behaviour, or deployment configuration.
- The first implementation must use synthetic fixtures and be opened as a draft PR for review.
- Production identity integration requires a separate threat review and explicit project-owner approval.
