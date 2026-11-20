# Security and Privacy Architecture — India-First Design

**Status:** design only. This document records target controls and does not claim that they are implemented.

## Current state on main

Main has local, read-only CSV ingestion, a mock read-only connector, versioned ontology registry contracts, explicit source roles, safe diagnostics, and simulated-only ActionType guards. It has no OIDC adapter, central policy decision point, tenant isolation, consent/erasure workflow, external audit anchor, real connector, credentials service, or external write-back.

## ADR-002 — identity and authorization

Use OIDC identity at the service boundary with an offline adapter for local development. Authorization combines RBAC (role) and ABAC (project, tenant, source role, sensitivity, purpose, retention, and operation). A central policy decision point returns a deny-by-default decision; enforcement points run at import, binding, simulation-input, report-export, and future action boundaries. Identity, policy version, decision, and subject/resource identifiers are audit fields.

## ADR-003 — tenancy and data protection

Start single-tenant, but include tenant/project scope in contracts and fingerprints so a later multi-tenant deployment cannot silently cross scopes. Purpose limitation and retention derive from `sensitivity`, `purpose`, and `retention` metadata. Personal data requires declared purpose and retention before downstream use. Design a consent record, erasure request, retention expiry, legal hold, and audit trail; deletion must preserve safe audit evidence without retaining the erased value.

India-first review aligns the engineering controls with the Digital Personal Data Protection Act, 2023 and applicable rules. This is an engineering design, not a legal-compliance certification.

## ADR-004 — audit, secrets, and integrity

Audit events are append-only, safe of raw personal/sensitive values, and hash-chained (`previous_hash`, canonical event, current hash). An external anchor may be added later. Secrets live in an approved secret store or environment boundary, never in code, fixtures, logs, manifests, fingerprints, or exception text. Rotate and revoke credentials; use separate identities for read, review, approval, and any future action.

## Delivery stages and exit tests

1. **Identity adapter:** valid/expired/revoked tokens and offline mode fail closed.
2. **Policy boundary:** RBAC+ABAC decisions cover import, binding, simulation input, and export; cross-tenant and sensitivity downgrades are denied.
3. **Privacy lifecycle:** purpose/retention, consent, erasure, legal hold, and breach logging have deterministic tests.
4. **Audit integrity:** hash-chain tampering, missing links, replay, and safe redaction are detected.
5. **Operational hardening:** secret rotation, least privilege, dependency review, backup/restore, and incident response are tested.

No stage authorizes real drivers, credentials, network access, external write-back, or real personal data. Any such capability needs a separate owner-approved design and threat model.
