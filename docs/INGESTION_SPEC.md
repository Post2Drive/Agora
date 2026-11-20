# Rung 3 Ingestion Specification

**Status:** design specification only. No implementation, database driver, network client, schema migration or study mutation is included in this document.

**Baseline:** GitHub `main` at `33f44c18cfc1eebd24074694c6cfbe963200380a`.

## 1. Purpose and boundaries

Rung 3 adds typed, repeatable ingestion while preserving source identity, complete-file integrity, row-level lineage and audit history.

The implementation must add structured tabular ingestion as a new path beside the existing document/text graph ingestion. The existing document path remains unchanged. In particular, the existing 2,000-row text-reader cap remains confined to that legacy text path; structured CSV ingestion must never silently truncate.

### In scope

- Local CSV file ingestion with an explicit schema contract.
- Typed columns, nullable values, deterministic row IDs and source-row locators.
- Full-file SHA-256 and immutable import manifests.
- Explicit malformed-row and schema-drift handling.
- Idempotent re-import and safe cleanup after partial failure.
- Source registry integration using existing data roles.
- Audit events for import lifecycle and rejected rows.
- A read-only database connector interface, tested with a mock connector only.
- Provenance and governance acceptance tests.

### Out of scope

- Real PostgreSQL, MySQL, SQL Server or external SQLite drivers.
- Network access, remote file URLs, cloud object storage or watched folders.
- INSERT, UPDATE, DELETE, DDL, stored procedures or any external write-back.
- Credentials or secrets in source files, logs, manifests, provenance or test fixtures.
- Changes to the existing document-ingestion behaviour.
- Simulation runs, calibration, backtests, forecasts or study-folder mutations.

## 2. CSV ingestion architecture

Add a dedicated tabular ingestion module and API. It must not route structured CSV rows through the existing text chunker.

Suggested conceptual stages:

1. Validate the source file and schema contract.
2. Read and hash the exact original file bytes.
3. Parse the header and records using a standards-compliant CSV parser.
4. Validate every row and convert values to declared types.
5. Generate stable row IDs and source locators.
6. Stage rows and an import manifest in a temporary/transactional area.
7. Register the source and import provenance.
8. Commit the complete snapshot and audit success atomically.
9. On failure, roll back staged rows and record a failed operation; do not leave a partially visible import.

The module should expose a stable API such as `ingest_csv(project, source_path, schema, *, data_role, mode="snapshot")`. Exact names may be adjusted to match repository conventions, but the contract below is normative.

## 3. Schema contract

Use a versioned, serialisable YAML or JSON schema. The first implementation should accept the following logical shape:

```yaml
schema_id: customers-v1
schema_version: 1.0.0
dataset_name: customers
encoding: utf-8
delimiter: ","
quotechar: '"'
header: true
columns:
  - name: customer_id
    type: string
    nullable: false
    primary_key: true
  - name: created_at
    type: timestamp
    nullable: true
    timezone: UTC
  - name: amount
    type: decimal
    nullable: true
    precision: 12
    scale: 2
  - name: active
    type: boolean
    nullable: false
    allowed_values: [true, false]
  - name: segment
    type: enum
    nullable: true
    allowed_values: [standard, priority, unknown]
row_policy:
  malformed: fail
  unknown_columns: reject
  missing_columns: reject
```

This is an illustrative contract, not an implementation file. The parser must validate the schema itself before reading data.

### Supported logical types for the first implementation

- `string`
- `integer` (base-10 integer; reject fractional values)
- `decimal` (exact decimal conversion; do not use binary float as the canonical stored value)
- `boolean` (explicit accepted literals only)
- `date` (ISO-8601 date)
- `timestamp` (ISO-8601; timezone required or an explicit schema timezone)
- `enum` (string value constrained to declared allowed values)

Every column declares `name`, `type`, `nullable` and `sensitivity`. The `sensitivity` value must be one of `public`, `internal`, `personal` or `sensitive`; it defaults to `internal` only when explicitly supplied by the schema author, never by inference. Optional constraints include `primary_key`, `allowed_values`, `precision`, `scale`, `timezone`, `minimum`, `maximum` and a documented format. Unknown schema keys should be rejected unless a future schema version explicitly supports them.

### Schema validation rules

- Column names are unique after the documented normalisation rule; do not silently merge duplicate headers.
- Required columns must be present exactly once.
- Unknown columns are rejected by default; explicit ignore/mapping rules require a future reviewed extension.
- Null/empty-string handling is explicit per column; empty text must not silently become null unless the contract says so.
- Decimal precision, date/time formats, enum membership and numeric bounds are validated.
- Header order may vary only if mapping is by exact declared column name.
- Schema version and canonical schema fingerprint are recorded in the manifest.
- A changed schema for the same dataset is schema drift; require a new schema version or an explicit reviewed migration.

## 4. Row identity and provenance

### Full-file identity

Compute SHA-256 over the exact original file bytes before decoding or normalisation. Store the lowercase 64-character digest on every import snapshot and in the source registry.

### Deterministic row identity

For each accepted row, compute a stable identifier from a canonical serialisation of:

- dataset identity;
- source registry ID;
- full-file SHA-256;
- schema ID and schema version;
- parsed row values in declared column order, using canonical type representations;
- source row number.

Use a versioned, domain-separated hash input (for example `agora-row-v1\0...`) so the algorithm can evolve without collisions with other identifiers. The same source bytes, schema and parser contract must produce the same row IDs. A changed source snapshot receives a different content hash and therefore a distinct row identity; do not silently overwrite historical snapshots.

### Cross-snapshot record identity

The snapshot-scoped `row_id` above intentionally changes when the source file hash or snapshot changes. It must not be used as the enduring identity of a real-world domain record.

For datasets with a declared primary key, also compute:

- `record_key`: a versioned, domain-separated hash of dataset identity plus the canonical declared primary-key value. It is independent of the file hash, import ID, row number and mutable non-key values.
- `row_id`: the snapshot-scoped identifier described above, retaining source hash, schema fingerprint, canonical row and source record number.

The same dataset identity and primary-key value must yield the same `record_key` across snapshots, while each distinct source snapshot retains its own `row_id`. The ontology's enduring instance identity for primary-key-backed imported records is `record_key`; provenance and historical values remain attached to each snapshot-scoped `row_id`.

Duplicate primary-key values within one snapshot fail the import by default. Across snapshots, the same key resolves to the same `record_key` with a new immutable row version; it must not overwrite the earlier snapshot. A changed primary-key value creates a new `record_key`; do not automatically infer that it is the same entity. Any key correction or merge requires an explicit, audited reconciliation mapping. Datasets without a declared primary key retain snapshot-scoped `row_id` only and cannot claim cross-snapshot entity identity.

### Row locator

Every accepted row stores a source locator containing at minimum:

- `source_registry_id`;
- `file_sha256`;
- `source_row_number` (1-based physical CSV record number, with the header row explicitly accounted for);
- `dataset_id` / import ID;
- optional primary-key value, if declared.

The locator is provenance metadata, not a substitute for row identity. Embedded newlines mean physical line numbers and CSV record numbers differ; use the record number and document the counting rule.

### Import manifest

Every attempt writes an immutable manifest with:

- import ID and manifest version;
- dataset ID/name;
- original filename (not a trusted path);
- full-file SHA-256 and byte length;
- schema ID/version/fingerprint, including each column's sensitivity classification;
- parser and application version;
- encoding, delimiter, quote and newline policy;
- data role and source registry ID;
- started/completed timestamps and terminal status;
- total parsed, accepted and rejected record counts;
- first/last source record numbers;
- row-ID algorithm version;
- duplicate/idempotency result;
- error summary and rejection references (without leaking secrets or personal/sensitive values);
- snapshot/storage reference and audit-event IDs.

A successful manifest must reconcile counts: parsed records = accepted + rejected. A failed atomic import must not expose a partial successful snapshot.

## 5. Malformed-row and schema-drift policy

Default behaviour is fail-closed: one malformed row, invalid conversion, duplicate key or structural mismatch fails the import and rolls back the staged snapshot.

A later opt-in `malformed: reject` policy may be supported only if it explicitly records each rejected record with source row number, stable error code and safe diagnostic. It must not silently skip rows. For columns classified `personal` or `sensitive`, diagnostics, audit events and error messages must contain only the source row number, column name and stable error code; never include the rejected value, a substring of it, or a value-derived preview. The manifest must include rejected count and references. A rejected row must never be represented as accepted data.

The following are structural errors and fail closed by default:

- empty file or header-only file when at least one data row is required;
- invalid encoding or undecodable bytes;
- duplicate, blank, missing or unexpected headers;
- uneven row widths;
- invalid quoting or malformed CSV syntax;
- invalid typed value or nullability violation;
- duplicate declared primary key;
- schema fingerprint mismatch without an explicit migration;
- parser/resource limit exceeded.

If a file is too large for configured resource limits, reject it with an explicit error; never truncate it. Limits must be configurable and reported in the manifest.

## 6. Idempotency and snapshot semantics

- Exact re-import of the same source bytes, schema fingerprint, parser contract and mode must return the existing successful import identity or a documented no-op result; it must not duplicate rows, graph objects or audit source registrations.
- A changed file hash is a new immutable snapshot, even if its filename is unchanged.
- A changed schema fingerprint is a new schema version or a rejected drift event, never an implicit reinterpretation.
- Import IDs and row IDs must be stable for the same deterministic inputs.
- Concurrent duplicate imports must be serialised or protected by a uniqueness constraint so only one snapshot is committed.
- A failed import may be retried; temporary rows from the failed attempt must not remain visible.
- Do not implement append/upsert/replace semantics in the first release. The first release is immutable full-snapshot import only.

## 7. Source registry and audit integration

Use the existing source registry contract and its allowed roles:

- `context`
- `scenario_input`
- `calibration`
- `validation`
- `sealed_holdout`

The caller must explicitly select a role. Do not infer it from the filename, dataset name or import command. Existing role enforcement for calibration/validation/holdout must remain authoritative.

Register the exact original file content and SHA-256, parser version, acquisition timestamp, source URL/publisher/author/licence when supplied, quality flags and extraction status. The import manifest links to the resulting `source_registry_id`.

Audit events must record import started, validation completed, import committed or failed, and explicit row-rejection summary where applicable. A pending operation left by a crash must be visible for manual reconciliation; do not auto-retry or silently mark it committed.

Every imported row and every downstream object derived from it must be traceable to the source registry ID, full file hash and row locator. Preserve lineage through transformations.

## 8. Read-only database connector contract (mock only)

Define an interface for future relational source adapters, but implement only an in-memory/mock connector in the first contract PR. No real drivers, network sockets or credentials.

The logical interface should support:

- discover allowlisted schemas/tables/columns;
- validate a structured query plan against an allowlist;
- execute parameterised SELECT-only queries;
- return typed rows in deterministic pages;
- expose stable primary-key row identity and source locators;
- return a query fingerprint and snapshot/extraction metadata;
- enforce timeout and cancellation;
- report extraction failure without exposing partial successful snapshots.

### Read-only enforcement

The contract must reject any statement or operation that is not a single permitted read. At minimum reject:

- INSERT, UPDATE, DELETE, MERGE, REPLACE;
- CREATE, ALTER, DROP, TRUNCATE, GRANT, REVOKE;
- CALL/EXEC, stored procedures and multi-statement payloads;
- access to non-allowlisted tables, schemas or columns;
- unparameterised user values in query predicates.

Prefer a structured query plan over accepting arbitrary SQL. If SQL text is used internally, parse it with a conservative allowlist; keyword substring checks alone are not sufficient because comments, quoted identifiers, CTEs and multiple statements can bypass naïve checks.

### Allowlist and pagination

- The connector receives an explicit set of allowed tables and columns.
- The caller cannot expand the allowlist through query input.
- Pagination order must be deterministic and include a unique stable key as a tie-breaker.
- Offset pagination is acceptable only for the mock contract; document that production adapters should prefer keyset pagination where supported.
- Every page is bounded by a configured maximum.
- Stable row IDs derive from connector identity, schema/table identity, primary-key values and extraction snapshot identity.
- Missing or non-unique primary keys fail closed unless a separately designed stable-key strategy is approved.

### Provenance and security

The query fingerprint is a hash of a canonical, parameter-redacted query plan plus the allowlist and connector configuration fingerprint. Do not include secret values in the fingerprint.

Credentials must never appear in logs, exception messages, manifests, provenance or test snapshots. The mock connector must use synthetic credentials only if it needs to test redaction. No real secrets are required. For all columns classified `personal` or `sensitive`, apply the same value-redaction rule to rejected-row diagnostics, audit events and exception text: row number, column name and error code only. The sensitivity classification must be included in the import manifest. Any `personal` column must have a declared processing purpose and retention policy before the imported data is used beyond the import/validation boundary; missing purpose or retention metadata fails closed. Apply India-first privacy review aligned with the Digital Personal Data Protection Act, 2023 and applicable rules; this specification is an engineering control, not a legal-compliance certification.

Every extracted row links to connector ID, source system label, schema/table, primary key locator, query fingerprint, extraction timestamp, snapshot identifier and source registry record/hash. Timeout, cancellation and partial extraction must leave no committed partial snapshot.

## 9. Acceptance tests

### CSV parsing and schema

- UTF-8 and UTF-8 BOM.
- Quoted delimiters, escaped quote characters and embedded newlines.
- Empty file and header-only file.
- Malformed quoting and invalid encoding.
- Duplicate, blank, missing and unexpected headers.
- Uneven row lengths.
- Nullability and explicit empty-string semantics.
- Integer, exact decimal, boolean, date, timestamp/timezone and enum conversion.
- Precision/scale, range and allowed-value failures.
- Duplicate primary keys.
- Schema drift and version changes.
- 2,001+ rows: every valid row is imported; no silent truncation.
- Configured size/row limits fail explicitly rather than truncating.

### Identity, provenance and idempotency

- Deterministic snapshot-scoped row IDs for identical bytes/schema/parser version.
- Stable `record_key` across different snapshots for the same dataset and declared primary key.
- Same primary key across snapshots retains one ontology identity with immutable row versions; changed keys require explicit reconciliation and are not automatically merged.
- Different file hash creates a new immutable snapshot.
- Source row locator points to the correct CSV record when fields contain embedded newlines.
- Full-file SHA-256 matches the original bytes and appears in every snapshot manifest.
- Sensitivity classifications appear in schema and manifest; personal/sensitive values never leak into rejection, audit or exception diagnostics.
- Personal columns cannot be used beyond import without a declared purpose and retention policy.
- Source role is explicitly selected and enforced.
- Duplicate exact import creates no duplicate rows or source registration.
- Concurrent duplicate import commits at most one snapshot.
- Manifest counts reconcile parsed/accepted/rejected records.
- Failed import leaves no visible partial snapshot and records a failed audit operation.
- Re-import after failure succeeds without duplicate residue.
- Mutation proof: temporarily remove the no-truncation guard; the 2,001+ row test must fail. Do not commit the mutation.
- Mutation proof: temporarily remove the idempotency guard; duplicate-import test must fail. Do not commit the mutation.

### Mock database connector

- Read-only SELECT succeeds against allowlisted mock tables.
- INSERT, UPDATE, DELETE, MERGE, DDL, stored procedure and multi-statement attempts are rejected.
- Unallowlisted tables and columns are rejected.
- Parameterised query inputs are handled without interpolation.
- Pagination is deterministic and does not duplicate/skip rows.
- Stable primary-key row IDs and row locators are preserved.
- Query fingerprint is recorded and secret values are redacted.
- Timeout and cancellation are enforced.
- Partial extraction rolls back and leaves no committed partial snapshot.
- Mutation proof: temporarily remove the read-only enforcement; a write attempt test must fail. Do not commit the mutation.

### Governance and cross-cutting

- Parser/connector version and configuration fingerprint are recorded.
- Every import links to source registry ID and full SHA-256.
- Source role is checked before calibration, validation or holdout use.
- Audit records start, success/failure and rejected-row summaries.
- Interrupted operations remain pending for manual reconciliation.
- Repeated imports are idempotent.
- No code path can call a real database driver, open a network connection or perform external write-back in this first implementation.

## 10. Storage, consumption and coexistence with current calibration files

### Initial storage target

The first structured CSV implementation stores imported snapshots in a project-level SQLite database, separate from the existing graph store. Use a dedicated project data file (for example, `data/tabular.sqlite3`) so the import transaction, manifest and accepted/rejected record references share one SQLite transaction boundary. Do not create or migrate tables in the existing `graph.db` as part of the first release.

Minimum logical tables:

- `datasets`: dataset ID, schema ID/version/fingerprint, dataset identity policy and creation metadata.
- `imports`: import ID, dataset ID, source registry ID, file SHA-256, manifest JSON/version, status, timestamps and counts; unique idempotency key.
- `import_rows`: snapshot-scoped `row_id`, cross-snapshot `record_key` where available, import ID, typed canonical row payload, source record number and source locator; unique constraints prevent duplicate row IDs and duplicate primary keys within an import.
- `rejected_rows`: import ID, source record number, column name, stable error code and safe diagnostic only; never store personal/sensitive rejected values.
- `dataset_records` (or an equivalent indexed view): latest-record pointer by dataset ID and `record_key`, without deleting prior `import_rows` snapshots. Updating this pointer is transactional and must not alter historical snapshots.

The import manifest is stored as canonical JSON in the `imports` row and may also be exported as a file for inspection. SQLite foreign keys must be enabled on every connection. Use transactions and uniqueness constraints for atomicity and idempotency. Schema migration for this new database must be versioned and backed up; it must not mutate existing project databases.

### Consumption contract

- Simulation/scenario loaders consume an explicit, approved dataset snapshot or immutable snapshot ID. They must not implicitly read a moving "latest" pointer during a run.
- Calibration and validation consume only rows whose source role and dataset purpose pass the existing governance checks; sealed holdout restrictions remain authoritative.
- Ontology instance identity uses `record_key` for primary-key-backed records; each version links to its snapshot `row_id`, import manifest and source locator.
- Consumers receive typed values and provenance metadata through a read-only repository/query API. No consumer writes back into imported source records.
- No automatic conversion of imported rows into graph entities is required in this first implementation.

### Coexistence with existing calibration files

The current `agora/calibrate/project.py` flow reads project-level `data/observations.csv` and `data/reviews.csv`. This flow must continue to work unchanged. The new structured ingestion module must not rewrite, rename, delete, shadow or automatically migrate these files, and must not change the existing calibration parser or its call sites in the CSV-ingestion PR. If future calibration integration is desired, it must be a separate reviewed PR with parity tests and a migration plan. For now, an imported dataset may be read by a new explicit adapter, but the existing observations/reviews path remains the source of truth for the current calibration workflow.

## 11. Implementation sequencing

1. Review and approve this specification.
2. Implement structured CSV ingestion in its own pull request, without changing the existing document ingestion path.
3. Implement the read-only connector interface and mock connector in a separate pull request.
4. Run the full four-job CI matrix on each exact final pull-request head.
5. Demonstrate the required mutation proofs without committing mutation changes.
6. Merge neither pull request until Claude has approved the exact head and all repository governance gates pass.
7. After both are merged, publish a rung 1–3 exit-test status report.

No rung 3 implementation is authorised by this document alone; the implementation begins only after the specification is reviewed and the owner-approved sequence is satisfied.

## 12. Decisions for the owner

Defaults are proposed so implementation can proceed without avoidable ambiguity. The owner may amend them during review.

| Decision | Proposed default | Owner input needed now? |
|---|---|---|
| Schema format | Versioned YAML on disk; accept parsed JSON internally if useful | No |
| First import mode | Immutable full snapshot only; no append/upsert/replace | No |
| Malformed-row policy | Fail the entire import and roll back; add explicit reject mode only in a later reviewed change | No |
| Header matching | Exact column names; order may vary; duplicate/unknown/missing columns fail | No |
| Snapshot row identity | Versioned SHA-256 over source ID, file hash, schema fingerprint, canonical row and source record number | No |\n| Cross-snapshot identity | Versioned `record_key` hash of dataset identity plus declared primary key; no automatic key reconciliation | No |\n| Storage | Separate project-level `data/tabular.sqlite3` with imports, rows, rejected-row references and dataset identity tables | No |\n| Sensitivity | Required per-column classification: public, internal, personal or sensitive; personal data needs purpose and retention metadata before downstream use | No |
| Primary key | Optional for CSV row identity; required for mock DB extraction unless a future stable-key design is approved | No |
| Data role | Caller must explicitly choose one of the existing registry roles; never infer | No |
| Large-file limits | Configurable, with explicit failure and no truncation; set a conservative initial default in implementation | No |
| Database adapter | Mock only; no real drivers, network access or credentials | No |
| Remote sources | Out of scope for rung 3 first release | No |
| Append/upsert semantics | Defer until snapshot semantics and lineage are proven | No |
| External write-back | Prohibited for rungs 2–4 | No |

