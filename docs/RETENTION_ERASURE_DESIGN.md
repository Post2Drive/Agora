# Retention and Erasure Design — Immutable Snapshot Data

**Status:** design proposal only. No deletion, tombstone, retention scheduler, personal-data workflow, or production control is implemented by this document.

**Purpose:** define a controlled, auditable way to respond to an approved erasure request while preserving immutable import history and the safety of dependent artifacts. This is an engineering design aligned for India-first review under the Digital Personal Data Protection Act, 2023 and applicable rules; it is not legal advice or a compliance certification.

## 1. Design principles

1. **Immutable history is the default.** Imports, manifests, row IDs, source hashes, bindings, scenario-input manifests, run provenance, decision versions, and audit-chain entries are append-only. Ordinary correction never overwrites a historical snapshot.
2. **Erasure is a distinct, approved exception.** It purges payloads that must no longer be retained while preserving a minimal tombstone and integrity evidence. It is never disguised as an ordinary update or re-import.
3. **Minimise retained information.** Retain only identifiers and hashes that are necessary, proportionate, access-controlled, and approved for the stated purpose. Do not retain raw values, reversible encodings, value-derived previews, or lookup tables in the tombstone.
4. **Do not silently rewrite dependencies.** A source erasure or retention expiry invalidates downstream reliance. Dependent bindings, scenario inputs, runs, reports, and decisions are marked for review through new append-only status records; historical contents are not silently rewritten.
5. **Separate request, approval, and execution.** The requester cannot approve their own request or execute the purge. A designated data steward verifies the request; a distinct authorized approver authorizes the scoped purge; a least-privilege erasure worker performs it.
6. **Preserve audit integrity without preserving the erased value.** Audit records use opaque request/tombstone identifiers, action codes, timestamps, actor IDs and safe resource IDs. They never contain the subject's raw personal data.

## 2. Why snapshots remain append-only

The tabular ingestion contract makes each import an immutable full snapshot. Its manifest binds the exact file SHA-256, schema fingerprint, source-registry ID, parser version, data role, row counts and import ID. Snapshot-scoped row IDs preserve historical lineage; cross-snapshot record keys connect versions of a domain record.

Mutating an old snapshot during ordinary operations would destroy evidence of what was imported, make source hashes and row locators misleading, and weaken reproducibility. Therefore:

- corrections create a new import/snapshot and, where needed, an explicit reconciliation record;
- retention expiry and erasure are represented by a separate tombstone record and append-only audit event;
- a purge worker may remove designated payload bytes only after valid approval and a legal-hold check;
- the original manifest and file hash remain as integrity evidence, marked with an erasure/retention status that does not imply the payload still exists;
- the tombstone records what was purged and which dependencies require review, not the erased content.

The tombstone is a controlled privacy-lifecycle record, not a new version that pretends the original import never existed.

## 3. Data classes and proposed treatment

| Data/artifact | Proposed treatment on approved erasure |
|---|---|
| Original uploaded/source file bytes and managed duplicates | Purge from active storage and controlled working copies; retain only approved manifest/hash metadata and tombstone. |
| Imported typed row payloads | Purge the row payload. Replace with a fixed tombstone marker only if the storage schema requires a non-null payload field; never leave a partial or redacted copy of the original value. |
| row_id, source record number, import ID, schema fingerprint, file hash, source registry ID | Retain only where the approved retention basis permits and the identifiers do not themselves reveal or enable reconstruction of the erased value. |
| record_key | Retain only as an approved irreversible placeholder. The current deterministic hash of dataset identity plus primary-key value must not automatically be assumed anonymous: low-entropy identifiers may be guessable or linkable. Threat-assess it. If it fails the irreversibility test, replace the active reference with a random opaque erasure token and destroy the mapping; do not retain the original key in the tombstone. |
| Current dataset-record pointer/index | Remove or tombstone the pointer for the erased record so ordinary reads cannot retrieve a payload. Historical references remain marked erased/review-required, not silently redirected to a different person. |
| Import manifest | Retain the minimal manifest, original file hash, schema fingerprint, counts and source lineage needed for integrity and accountability. Add an explicit erasure status/tombstone reference in a separate append-only record; do not rewrite the original manifest. |
| Source registry content | Purge retained source bytes and personal metadata covered by the request. Retain only approved safe provenance fields and a tombstone; do not leave a second copy in registry attachments or caches. |
| Binding definitions and ontology packs | Definitions normally contain no row payload and may remain. Mark dependent materializations/bindings review-required where the erased record or source was used. Never rewrite a binding fingerprint in place. |
| Scenario-input manifests | Preserve the immutable historical manifest/hash as provenance, but mark the dependent input artifact review-required/erased through a separate record. Do not rebuild it from a different or moving latest selector. |
| Run records and exports | Preserve historical run records and exact provenance for audit only where lawful and necessary. Mark the run/report review-required and suppress affected payloads or exports from normal use. Never relabel simulated output as observed evidence. |
| Decision records and observed outcomes | Preserve prior versions. Append a review-required transition/version through the decision state machine when evidence is erased or invalidated. Do not delete or rewrite a prior approval silently. |
| Audit chain | Append request, approval, purge, dependency-invalidation and completion events. Retain only allow-listed identifiers and non-sensitive reason codes; never append raw personal values. |
| Backups, caches and temporary files | Record each location and expiry. Purge or cryptographically expire copies under the approved backup schedule; verify restore procedures cannot reintroduce erased payloads into active use. |

## 4. Request and approval workflow

### 4.1 Intake and verification

1. Receive an erasure/retention request through an approved owner-controlled channel. Create an opaque request ID.
2. Verify the requester's identity and authority using the organization's approved identity process. Identity evidence stays outside the Agora tombstone and ordinary audit event.
3. Record the requested scope (project, dataset/import, subject reference, and known source records) using opaque identifiers. Do not put raw personal values in the request record or GitHub issue.
4. A designated data steward determines the data locations and dependencies from the source registry, import manifest, row locators and controlled identity index. Do not use broad text search that copies personal values into logs.
5. Check the declared purpose, retention deadline, contractual duties, legal holds, dispute requirements and applicable statutory exceptions. If a valid hold or retention basis prevents erasure, deny or defer the purge, restrict use, record the reason code, and set a review date.

### 4.2 Independent approval

6. The requester cannot approve their own request. The verifier/data steward cannot be the sole purge approver.
7. A distinct privacy/data approver confirms the legal basis, exact scope, dependent artifacts, purge plan, backup plan and permitted retained metadata.
8. Approval is a versioned decision record with exact request fingerprint, scope fingerprint, evidence references, expiry, approver identity and separation-of-duties checks. A changed scope or expired approval requires a new approval.
9. The approval record authorizes only the named purge scope. It does not call a connector or execute deletion by itself.

### 4.3 Execution and verification

10. The least-privilege erasure worker re-checks approval fingerprint, scope, expiry and legal-hold status immediately before purge.
11. Append an erasure-start event, create the tombstone, purge the approved payload locations transactionally where possible, and append dependency review markers.
12. Verify that ordinary read APIs cannot retrieve the erased payload, the original manifest/hash remains internally consistent, the audit chain verifies, and all dependent artifacts are marked for review.
13. Record backup expiry/cryptographic-erasure tasks and their due dates. Do not report completion until all in-scope active copies are purged and backup handling is scheduled and evidenced.
14. Append a completion or partial-completion event. Notify the requester through the approved channel without disclosing other subjects' data.

If a purge partially fails, stop further processing, keep the request in a visible pending/partial state, preserve safe diagnostics, and require manual reconciliation. Never mark a partially purged request complete.

## 5. Tombstone contract

The later implementation should define a versioned tombstone with fields similar to:

- tombstone_id: opaque random identifier;
- request_id: opaque request reference;
- project_id, dataset_id, import_id: exact scope identifiers;
- source_registry_id, file_sha256, schema_fingerprint: retained integrity references, subject to the retention decision;
- row_id and an approved irreversible record-key placeholder, where safe;
- purge_scope: enumerated data locations/classes, not raw values;
- status: proposed, approved, pending, partially_purged, completed, denied, or held;
- reason_code: controlled non-sensitive code;
- verified_by, approved_by, executed_by: distinct actor identifiers;
- approval_fingerprint, scope_fingerprint, created_at, approved_at, executed_at, review_at;
- purge_evidence: counts and safe storage references, not copies of erased content;
- dependency_review_ids: opaque references to append-only review markers;
- backup_expiry_at and backup verification status.

The tombstone must not contain a name, email, phone, address, raw primary key, rejected value, value preview, reversible hash of a low-entropy identifier, or a mapping back to the subject.

A tombstone is append-only. Status changes append a new tombstone version or transition event; they do not update or delete prior audit history.

## 6. Dependency invalidation

Erasure changes the admissibility of downstream evidence. It does not automatically rewrite downstream artifacts.

- **Source registry/import:** append a source-erased or retention-expired status record linked to the tombstone. The original file hash and manifest remain only as approved integrity metadata.
- **Bindings/materializations:** mark affected binding/materialization references review-required. Keep binding definitions and fingerprints unchanged; re-materialization requires a new approved snapshot and explicit import ID.
- **Scenario inputs:** append a review marker against the exact scenario hash/import ID. Do not mutate the historical manifest or rebuild it from a moving latest selector.
- **Runs/reports:** append a run review marker and mark derived reports as affected. Prevent affected exports from being presented as current evidence. Preserve historical simulation output only where retention is lawful and necessary; otherwise purge the affected payload while retaining safe provenance/tombstone metadata.
- **Decision records:** append a review-required transition/version through the decision state machine. Never silently change evidence references or overwrite the approval version.
- **Observed outcomes:** invalidate or mark review-required any outcome whose source snapshot is erased or no longer valid. Simulated events remain ineligible as observed outcomes.
- **Audit chain:** append dependency invalidation events with opaque IDs and controlled reason codes. The chain must remain verifiable after payload purge.

No downstream artifact may be treated as validated merely because its historical hash still verifies. Hash integrity proves that retained metadata has not changed; it does not prove that erased data remains lawful or suitable for use.

## 7. Legal hold, retention expiry and backups

- A legal hold blocks the purge for its exact scope until released by an authorized role. Access and processing remain restricted to the hold purpose.
- Retention expiry is evaluated per declared purpose/data class, not by a global arbitrary timer. A scheduled expiry creates a review task; it does not delete automatically until required authority and hold checks pass.
- The backup inventory must identify backup location, encryption/key scope, creation date, retention deadline and restore owner.
- A backup that cannot support selective erasure must have a documented expiry or cryptographic-erasure mechanism approved by the data owner. Restoring a backup must replay tombstones before restored data becomes available to users or jobs.
- Temporary uploads, local caches, exports, derived files and test artifacts are part of the purge inventory. A source file is not erased if an uncontrolled duplicate remains in an active location.
- Secret rotation, least privilege, dependency review, backup/restore and incident response remain separate operational-hardening controls under stage 5 of the Security Architecture; this design does not claim those controls are implemented.

## 8. Roles and permissions

| Role | Permitted responsibility | Must not do |
|---|---|---|
| Requester/data principal or representative | Submit a request and provide scope/verification evidence through the approved channel | Approve or execute their own purge |
| Data steward/verifier | Verify authority, identify source locations and dependencies, prepare scope | Solely approve and execute the same request |
| Privacy/data approver | Approve, deny, or place a hold on the exact scoped request | Modify payloads directly or approve a stale scope |
| Erasure worker | Execute an approved, unexpired, scope-matched purge; append audit evidence | Expand scope, override a hold, or change approval records |
| Auditor/reviewer | Verify approval separation, purge evidence, dependency markers and chain integrity | Read erased payloads without a separately approved lawful basis |
| System operator | Maintain availability and backups under least privilege | Bypass approval, restore tombstoned payloads into active use, or alter audit history |

## 9. Required implementation tests

The later code PR must include deterministic synthetic fixtures only.

1. **Approval and separation**
   - unverified requester, unknown role, requester self-approval and verifier self-approval are denied;
   - approver must be distinct from requester, verifier and executor;
   - stale scope/fingerprint, expired approval and changed dependency inventory are rejected;
   - legal hold blocks execution and leaves a visible held status.
2. **Tombstone and purge**
   - approved purge removes original payload from imported rows, source registry content, active exports and controlled temporary copies;
   - manifest, original file hash and safe source lineage remain intact;
   - retained record keys pass a documented irreversibility check; otherwise only random opaque placeholders remain;
   - tombstone contains no raw personal/sensitive value or reversible low-entropy identifier;
   - partial purge remains pending/partial and cannot be reported complete.
3. **Dependency invalidation**
   - bindings/materializations, scenario inputs, runs/reports, decision versions and observed outcomes are marked review-required;
   - invalidation appends new records and does not rewrite earlier manifests, fingerprints, approvals or audit events;
   - affected artifacts cannot be consumed as current evidence until re-reviewed.
4. **Audit and recovery**
   - request, approval, hold, purge, completion and dependency events are allow-listed and hash-chain verified;
   - duplicate/replayed purge requests are idempotent and do not duplicate destructive work;
   - restore applies tombstones before active use and cannot resurrect erased payloads;
   - backup expiry/cryptographic-erasure evidence is recorded.
5. **Boundary**
   - no real personal data, real customer identifiers, network calls, credentials, external drivers or write-back in tests;
   - validated prediction remains disabled.

### Required mutation proofs (scratch only; never commit)

- Remove the legal-hold check: test_legal_hold_blocks_erasure must fail.
- Remove requester/approver separation: test_requester_cannot_approve_erasure must fail.
- Skip payload purge: test_approved_erasure_removes_payload_and_keeps_manifest_hash must fail.
- Skip dependency invalidation: test_erasure_marks_all_dependent_artifacts_review_required must fail.
- Skip tombstone redaction/irreversibility enforcement: test_tombstone_contains_no_personal_values_or_reversible_keys must fail.
- Allow restore to expose a tombstoned payload: test_restore_replays_tombstones_before_data_is_available must fail.

Every mutation must be applied only in a disposable scratch checkout, restored before the normal suite, and leave an empty final diff.

## 10. Sequencing and open design decisions

This document is design-only. A future implementation must be split into separately reviewed work:

1. approve the threat model, data inventory, retention schedule, legal-hold rules and role mapping;
2. implement request/approval/tombstone schemas and append-only state transitions;
3. implement storage-specific payload purge and source-registry erasure;
4. implement dependency invalidation for bindings, scenario inputs, runs, reports, decisions and outcomes;
5. implement backup/restore tombstone replay and operational verification;
6. run the four-job CI matrix and all mutation proofs on exact heads;
7. obtain independent review and explicit owner approval before any production erasure action.

**Not decided by this document:** legal retention periods, statutory exceptions, identity-verification provider, legal-hold authority, backup retention duration, and whether the existing deterministic record_key can safely be retained after erasure. These require owner/legal/security review. No production deletion is authorized.
