# Ontology Object Store and Query Design

**Status:** design proposal. This document defines O1 for owner review; it does not implement storage, migrate existing databases, or enable external actions.

## Intent

Give Agora a durable, queryable ontology layer that connects versioned type definitions and immutable imported snapshots to stable object identities and typed links. Keep the source snapshot as the authoritative record for imported property values; store ontology identity and relationships without copying raw dataset rows.

The design follows Agora's accepted modular-monolith direction and existing project-local SQLite pattern. It targets comparable core ontology capabilities to operational object platforms, with complete source lineage, explicit snapshot selection, portable definitions, and fail-closed policy as Agora's measurable differentiators.

## Goals

- Persist immutable ontology-pack versions, binding versions, source-backed object references, and typed link instances.
- Query objects and traverse links using stable type/property IDs and explicit versions.
- Return each object's source locator, dataset/import identity, content SHA-256, binding fingerprint, and effective sensitivity.
- Enforce type, link, cardinality, temporal, project-scope, and policy constraints at the storage/service boundary.
- Preserve snapshot immutability and keep simulation data in the simulation store.

## Non-goals

- No migration or mutation of `graph.db`, `tabular.sqlite3`, or the run database.
- No copying of source row payloads into the ontology store.
- No general action executor, external write-back, feed integration, live service, or hosted deployment.
- No user-level tenant sharing until identity and isolation controls are implemented and verified.
- No implicit `latest` selectors.

## Approaches considered

1. **Add ontology tables to the simulation database.** Rejected: it couples general domain data to the simulation engine and broadens the simulation store's responsibilities.
2. **Copy full source rows into a new object database.** Rejected: it duplicates sensitive values, creates competing sources of truth, and complicates provenance and deletion.
3. **Use a dedicated project-local ontology database as a catalog and relationship store, with immutable source-row references.** Recommended: it preserves modular boundaries and snapshot immutability while providing durable object identities, links, and query indexes. Imported properties are resolved through their exact binding and import snapshot; user-authored ontology records can be stored in the ontology database with their own provenance.

## Storage boundary

Use a project-local SQLite sidecar, proposed path `data/ontology.sqlite3`, with foreign keys enabled, WAL mode, explicit schema version, transactional migrations, and backup/restore support.

The logical tables are:

- **ontology_packs:** pack ID, schema version, canonical pack fingerprint, serialized definition snapshot, lifecycle state, and creation metadata. A fingerprint is immutable; the same pack/version cannot be replaced with different content.
- **bindings:** binding ID/version/fingerprint, exact object type ID/version, dataset ID, schema ID/version, and the compatible pack fingerprint.
- **object_refs:** project ID, pack fingerprint, type ID/version, binding fingerprint if source-backed, exact import ID, dataset ID, stable record key, snapshot row ID, schema fingerprint, source hash/locator, and effective sensitivity. Unique identities are enforced in the declared scope. References contain no imported property values.

Object-reference indexing streams source rows in bounded batches after binding policy authorization. Single-object reads resolve exactly one recorded row ID from the selected immutable import and then verify its stable key and provenance before returning typed values. A missing or mismatched source row fails closed.
- **links:** link ID/version, pack fingerprint, link type ID/version, exact source and target object identities, valid-time interval, assertion status, source/provenance reference, actor, created-time, and audit-event reference.
- **store_meta / schema_migrations:** schema version, integrity metadata, and applied migration IDs.

Imported property values remain in the selected immutable snapshot. A query must name the exact `import_id` and binding fingerprint, then materialize values through the existing binding contract. It must fail if the snapshot or binding has changed, is unavailable, or is not authorized for the requested purpose. User-authored objects may store values locally, but those records still require versioned types, provenance, sensitivity, and an audit event.

## Identity and versioning

- Every query names an exact project, pack fingerprint, type ID/version, and import/binding identity where applicable.
- Source-backed object identity derives from the existing stable record key plus its dataset and type scope. Snapshot row IDs identify immutable row versions; they do not replace stable identity.
- User-authored or scenario-derived identities use a distinct namespace and origin marker; they cannot be mistaken for observed source records.
- A pack contains one definition version per type ID. Historic versions remain independently addressable by pack fingerprint.
- Changes append new pack, binding, object, or link versions; they never rewrite a historical definition or source snapshot.
- Link endpoint references include enough exact identity to prevent resolving a row through a different import or binding.

## Link and temporal semantics

Each link instance resolves to one LinkType definition in the selected pack and to source/target ObjectTypes present in that same pack. The database enforces the declared cardinality and rejects endpoints with mismatched project, type, or version.

Links are assertions, not evidence of causation. They carry valid-time start/end and transaction-created time separately. Endpoints are immutable; correcting a relationship appends a superseding link record and preserves the old one. Source-backed links require provenance; manually asserted links require an actor, reason, and audit event. All times are UTC, with source-local time retained as provenance where relevant.

Cardinality constraints apply to active links over overlapping valid-time intervals. Updates use one transaction so concurrent writes cannot violate a one-to-one or one-to-many rule.

### Normative link contract

- **Endpoint identity:** a link pins the project ID, pack fingerprint, object type ID/version, import ID, and stable record key for both endpoints. Both exact object references must exist in that project and pack. A link cannot resolve an endpoint through another import, pack, project, or implicit `latest` selector.
- **Time intervals:** valid time uses half-open intervals `[valid_from, valid_to)`; a null end is unbounded. Timestamps must include a timezone and are normalized to UTC before comparison. Empty or reversed intervals are rejected. Creation time is transaction time and never substitutes for valid time.
- **Cardinality:** `one_to_one` permits at most one active target per source and one active source per target at any overlapping instant. `one_to_many` permits multiple targets per source but at most one source per target at an overlapping instant. `many_to_many` adds no endpoint uniqueness restriction. Non-overlapping intervals do not conflict.
- **Correction and concurrency:** a correction appends a successor that names the exact superseded link ID; the original row remains immutable. A link may have at most one direct successor. Cardinality checks and insertion run in the same write transaction, and superseded assertions are excluded from the active set. Conflicting or ambiguous corrections fail closed.
- **Authority and evidence:** actor identity comes from the principal-bound policy decision, never from a caller-provided actor field. Writes require `ontology_write`, an anchored audit event, a non-empty reason, and canonical provenance. Source-backed provenance must identify the exact source snapshot/import; a manually asserted relationship must be labeled as an assertion and must not be presented as observed source data.

These rules are the implementation contract for the typed-link slice. They do not authorize external write-back, live feeds, simulation changes, or public APIs.

## Query contract

The first API is internal to the modular monolith and read-only for source-backed values:

- `get_object(project_id, pack_fingerprint, type_id, type_version, object_key, import_id)`
- `query_objects(project_id, pack_fingerprint, type_id, type_version, import_id, filters, page_size, cursor)`
- `traverse_links(project_id, pack_fingerprint, link_type_id, link_version, endpoint, import_id, page_size, cursor)`

Queries are parameterized, scoped, paginated, and bounded. Filters name known property IDs and use typed operators validated against PropertyType. Ordering has a stable key tie-break. Returned pages include provenance and effective sensitivity. Unknown fields, unsupported operators, stale fingerprints, missing imports, ambiguous versions, and `latest` are refused.

No public REST endpoint or generated SDK is exposed in O1; those belong to O3 after the data and policy contract stabilizes.

## Governance and failure behavior

The first catalog slice uses separate `ontology_read` and `ontology_write` policy operations; it does not label ontology changes as `binding`. The current role matrix grants both operations to `operator`, read access to `reviewer` and `reader`, and no ontology writes to those read-oriented roles. Every operation is project-scoped, sensitivity-checked, principal-bound, and recorded through the anchored audit writer in protected mode. The policy version changes when these operation grants change.


- Require a principal-bound policy decision before protected reads or writes. No caller can bypass it with a flag or unbound callback.
- Audit pack registration, binding registration, object/link insertion, supersession, denied queries, and export attempts through the anchored audit path.
- Apply least privilege at project and resource scope. Never return values above the principal's clearance or for an unauthorized data purpose.
- Sealed holdouts are not materializable by the operator path. Separate evaluator access requires a distinct, reviewed custody contract.
- Denials fail before source rows are read. Audit failure prevents the protected operation from proceeding.
- Enforce retention and deletion through explicit, audited workflows that preserve required non-sensitive integrity evidence without retaining restricted payloads.
- Read and write operations are atomic within the ontology store. Cross-database source references are verified before commit; no cross-file transaction is assumed.

## Migration and operations

Create the sidecar only when O1 implementation is separately approved. Schema migrations are explicit, forward-only, checksummed, and transactional. Existing databases are not automatically altered. Backups include the ontology database and its referenced snapshot manifests; restore verification checks pack, binding, link, and source-reference integrity. If a referenced snapshot is missing, queries fail closed and return an actionable provenance error.

## Acceptance evidence for implementation

An O1 implementation is ready only when evidence demonstrates:

1. Two independent domain packs register and query under the same contract.
2. Exact pack and binding fingerprints are required; ambiguous or implicit version selection is rejected.
3. Source-backed object identity remains stable across imports while row-version identity changes.
4. Links enforce endpoint types, project scope, declared cardinality, and overlapping temporal intervals under concurrent insertion.
5. Queries return typed values from the named snapshot with exact source locator, hash, binding fingerprint, and effective sensitivity.
6. Missing, changed, sealed, or unauthorized snapshots fail before protected row access.
7. Policy denials and allowed writes are audited; failure to anchor audit prevents writes.
8. Snapshot files and manifests remain unchanged; source values are never duplicated in the ontology database.
9. Backup/restore and schema migration preserve integrity and historical reads.
10. External systems, the simulation engine, and `VALIDATED_PREDICTION_ENABLED` remain untouched.

Implementation scope, module boundaries, and execution authorization remain a separate review step.