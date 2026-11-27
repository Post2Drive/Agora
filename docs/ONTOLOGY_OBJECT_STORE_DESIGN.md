# Ontology Object Store and Query Design

**Status:** design contract with partial O1 implementation. The project-local store includes immutable definitions, source-backed object references, typed temporal links, bounded object queries, link traversal, a consistent local SQLite backup, and local integrity verification. The dependency-manifest operation binds exact backup bytes to the source-snapshot file hashes referenced by stored objects. It does not package or verify that those external files are available. Feature-specific tests and full recovery evidence remain outstanding. This is not an O1 completion claim and does not enable external actions.

## Intent

Give Agora a durable, queryable ontology layer that connects versioned type definitions and immutable imported snapshots to stable object identities and typed links. Keep the source snapshot as the authoritative record for imported property values; store ontology identity and relationships without copying raw dataset rows.

The design follows Agora's accepted modular-monolith direction and existing project-local SQLite pattern. Its aim is a durable object and link layer with complete source lineage, explicit snapshot selection, portable definitions, and fail-closed policy as Agora's measurable strengths.

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

Object-reference indexing streams source rows in bounded batches after binding policy authorization. Single-object reads resolve exactly one recorded row ID from the selected immutable import and then verify its stable key and provenance before returning typed values. A missing or mismatched source row fails closed. Reads also recompute the import ID and each row ID that is read; see the snapshot content checks and their limits in [ONTOLOGY_DATA_BINDING.md](ONTOLOGY_DATA_BINDING.md#snapshot-content-checks-on-read).
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

Links are assertions, not evidence of causation. They carry valid-time start/end and transaction-created time separately. Endpoints are immutable; correcting a relationship appends a superseding link record and preserves the old one. Source-backed links require provenance; manually asserted links require an actor, reason, and audit event. When a source-backed link is written, each of its `source_refs` (at most 100) is checked against the project tabular snapshot: the import must be committed and hold its recorded number of rows, `file_sha256` must equal the stored file hash, and `locator`, in the form `row:<source record number>`, must name an accepted record in that import. The check runs after write authorization, and the cited import IDs are part of the resource the policy decides on. Under the protected defaults each cited import's current content must also have its ingest record in the anchored audit chain; row payloads are hashed for that digest and are never parsed or returned. The record is local and unsigned (see `ONTOLOGY_DATA_BINDING.md`). The check does not show that the cited record supports the relationship, or revisit links stored earlier. Other provenance kinds may not carry `source_refs`. All times are UTC, with source-local time retained as provenance where relevant.

Cardinality constraints apply to active links over overlapping valid-time intervals. Updates use one transaction so concurrent writes cannot violate a one-to-one or one-to-many rule.

### Normative link contract

- **Endpoint identity:** a link pins the project ID, pack fingerprint, object type ID/version, import ID, and stable record key for both endpoints. Both exact object references must exist in that project and pack. A link cannot resolve an endpoint through another import, pack, project, or implicit `latest` selector.
- **Time intervals:** valid time uses half-open intervals `[valid_from, valid_to)`; a null end is unbounded. Timestamps must include a timezone and are normalized to UTC before comparison. Empty or reversed intervals are rejected. Creation time is transaction time and never substitutes for valid time.
- **Cardinality:** `one_to_one` permits at most one active target per source and one active source per target at any overlapping instant. `one_to_many` permits multiple targets per source but at most one source per target at an overlapping instant. `many_to_many` adds no endpoint uniqueness restriction. Non-overlapping intervals do not conflict.
- **Identity for cardinality:** cardinality counts stable objects, not exact endpoints: object type ID plus record key, which includes the dataset identity. The same record read from two imports is one endpoint. To restate a relationship from a newer import, supersede the old link; adding a second link over overlapping time is refused for `one_to_one` and `one_to_many`. This does not resolve entities across datasets (different dataset IDs give different record keys), and cardinality is still scoped to one pack fingerprint and link-type version, so it is not enforced across pack versions.
- **Links stored before this rule:** they are never rewritten. `verify_integrity` reports them as `link_cardinality: "conflicts"`, with the number of links involved and up to 100 of their IDs; `ok` stays true so such a store can still be backed up and restored. A conflict is corrected by superseding a link when there is a truthful replacement, or by retracting one when there is none. A stored link whose type is not in its pack fails verification.
- **Correction and concurrency:** a correction appends a successor that names the exact superseded link ID; the original row remains immutable. A link may have at most one direct successor. Cardinality checks and insertion run in the same write transaction, and superseded and retracted assertions are excluded from the active set. Conflicting or ambiguous corrections fail closed.
- **Authority to correct:** a correction withdraws the old assertion, so it needs write authority over that link as well as the new one. The first decision names the link ID and is taken before the link is looked up. The final decision also names the old and new endpoints and is taken at the highest classification among all of them.
- **Retraction:** `retract_link` withdraws an active link without asserting anything in its place. See [Link retraction](#link-retraction).
- **Authority and evidence:** actor identity comes from the principal-bound policy decision, never from a caller-provided actor field. Writes require `ontology_write`, an anchored audit event, a non-empty reason, and canonical provenance. Source-backed provenance must identify the exact source snapshot/import; a manually asserted relationship must be labeled as an assertion and must not be presented as observed source data.

These rules are the implementation contract for the typed-link slice. They do not authorize external write-back, live feeds, simulation changes, or public APIs.

## Link retraction

Superseding needs a replacement assertion. Without retraction, a link entered in error could only be replaced by another claim, which may not be true.

**Choice.** A retraction is a row in its own append-only table, `ontology_link_retractions` (migration v4), holding the link ID, recorded time, actor, reason and provenance. Rejected: a status column on the link (it would rewrite an immutable row), and a "retraction" successor link (it would be an assertion with endpoints and valid time that every reader had to know to ignore).

- **Meaning.** The whole assertion is withdrawn, for all of its valid time, from the time the retraction is recorded. It does not say the relationship was false, and it is not how a relationship ends: for that, supersede the link with an earlier `valid_to`. A partial withdrawal is also a supersession.
- **Only active links.** A superseded or already retracted link is refused, and a retracted link cannot be superseded. The write transaction checks both, and database triggers refuse both mixed states. `verify_integrity` refuses a store holding a link that is both superseded and retracted.
- **No undo, no revival.** Retractions are immutable. Asserting the relationship again is a new link. Retracting a successor does not bring back the link it superseded.
- **Effect.** A retracted link leaves the default `get_links` result, the cardinality check and the stored-conflict report. `get_links(include_superseded=True)` also returns retracted links.
- **Labels.** Every link record from `get_links` and `traverse_links` has `status` (`active`, `superseded` or `retracted`) and `retraction` (null unless retracted). Traversal has always returned superseded links too, so callers must read `status`. On traversal both are given as of the time the first page was requested.
- **Authority and evidence.** Same contract as a link write: `ontology_write`, decided at the endpoints' highest stored sensitivity, a principal-bound actor, a non-empty reason and canonical provenance. A first decision is made before the link is looked up. Source-backed citations are checked like those of a link, are part of the policy resource, and their imports are included in the backup dependency manifest and content attestation.
- **Older stores and backups.** Opening a v3 store applies v4 without touching existing rows. A backup written at v3 is still verified against the v3 schema, can be restored, and is migrated when next opened. Code from before v4 refuses a v4 store; there is no downgrade.

Limits: library level only; no service or command calls it. It needs no second approver and is allowed to whoever may write links. Retraction does not mark runs, results or decisions that used the link. As with link creation times, the recorded time is taken just before commit and from the local clock, so "as of" is by recorded time, not commit order. The traversal cursor is not signed, so its time can be altered by whoever holds it.

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

The sidecar implementation is in `agora/ontology/store.py` and uses checksummed, forward-only migrations through schema v4. Existing graph and run databases are not altered. Opening the store applies pending migrations transactionally. `backup(path, policy, audit)` creates an atomic, project-local SQLite backup and checks its database integrity, foreign keys, and ontology metadata before publishing it. It publishes with a hard link, so it never replaces a file, including one created while the backup runs, and it refuses names ending in `-wal`, `-shm` or `-journal`, which SQLite may reset or delete beside a database. The file system must support hard links, as restore already requires. It can still create any other absent file inside the project, and a process killed mid-backup can leave a uniquely named `.tmp` file that a later backup does not remove. `verify_integrity(policy, audit)` checks SQLite integrity, foreign keys, migration checksums, pack and binding fingerprints, object-reference metadata, and link and retraction record shape, and reports stored cardinality conflicts. `backup_dependency_manifest(backup_path, policy, audit)` returns a canonical, hash-bound inventory of the backup, pack/binding fingerprints, and exact external snapshot file hashes referenced by ontology objects and source-backed links, without source row values. Restore publishes a verified project-local ontology backup into an empty destination without replacing an existing store. The current link schema also does not store an audit-event ID.

**Recovery authentication.** The dependency manifest (format `agora-ontology-backup-dependencies/v2`) records, for every import referenced by objects or source-backed links, a content digest (`agora-import-content-sha256/v1`): SHA-256 over the stored import record and every one of its rows, including payloads, as canonical JSON lines. It covers logical content rather than database file bytes, so later unrelated imports do not invalidate it. `restore(backup_path, dependency_manifest, expected_manifest_sha256, policy, audit)` always requires `expected_manifest_sha256`, a digest the operator retained separately when the manifest was created. That digest pins the manifest, which pins the exact backup bytes and each referenced import's content. Restore copies the backup to a private file, verifies that copy (bytes, integrity, project IDs, target-side import metadata, row locators, and content digests), and publishes that same copy. A backup with a non-empty `-wal` or `-journal` beside it is refused by both operations, because SQLite would read data the file hash does not cover. Digesting row payloads requires an `ontology_write` decision at `sensitive` sensitivity, made before any payload is read; digests, never values, are returned.

Limits of this check: it is a digest comparison, not a signature, so it is only as trustworthy as the place the operator keeps the digest. It shows that the content matches what existed when the manifest was created, not that the content matched the original source file at ingestion. Anyone holding a manifest and the other row metadata could test guesses of low-entropy row values against a digest, so manifests should be handled as internal records. It says nothing about imports the backup does not reference, or about changes after restore. It does not copy the tabular database or original source files. A disaster-recovery rehearsal on separate storage remains outstanding. Queries still fail closed when an exact referenced snapshot cannot be resolved.

**Anchored backup.** `create_anchored_backup(path, policy, audit)` makes the backup from the existing live store, builds the manifest and appends an `ontology_backup_anchored` event carrying the manifest and backup-file digests to the anchored audit chain. `restore_anchored(backup_path, dependency_manifest, policy, audit)` takes the digest from that chain and accepts only the newest backup anchored for the project; older backups need `restore` with a separately retained digest, and `restore` is unchanged. Both new operations require an anchored writer (the test-only anchoring relaxation does not apply), an `ontology_write` decision at `sensitive` sensitivity and an identified actor. A failed anchoring removes the new backup file. If the event was committed but the anchor write failed, later audited operations refuse until an operator reconciles the anchor; after that the newest anchor names a removed file, so make a new anchored backup.

Limits: the anchor is a local file, so someone who can rewrite both the audit database and the anchor, or who can run code in the service process, can forge it. The chain and anchor must be stored and configured apart from the backup set; if they are lost with the project, only the retained-digest path remains. Projects are told apart by directory name within one chain. It records what the live store held at backup time, not that the content was correct. The manifest is not signed, and no service or command calls these operations yet.

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

## Schema object verification

Integrity checks (`verify_integrity` and backup verification) compare every table, index, view and trigger (whitespace-normalised DDL, excluding SQLite statistics and sequence tables) with the schema this code creates. A store or backup with a missing, changed or added schema object, including a removed immutability trigger, is refused. Binding ID and version columns must match the binding content. Limit: this does not detect an internally consistent rewrite of row data, or removing a trigger, editing rows and restoring the identical trigger. Detecting that needs a separately retained digest or signature.
