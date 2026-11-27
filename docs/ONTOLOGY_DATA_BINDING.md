# Ontology Data Binding — Rung 2/3 Contract

**Status:** design contract with a partial implementation. Main includes binding parsing, validation, and read-only materialization against explicitly selected tabular snapshots. It does not add a general connector framework, migrate storage, mutate snapshots, or enable simulation or external write-back.

## Current implementation status — 26 November 2026

The matching implementation is in `agora/ontology/binding.py` and is covered by `tests/test_ontology_binding.py`. Materialization returns in-memory instances; this contract does not establish a persistent ontology object store or general query/API service. See [ONTOLOGY_CAPABILITY_TARGET.md](ONTOLOGY_CAPABILITY_TARGET.md) for staged capability targets.

## 1. Purpose and boundaries

A binding maps one versioned ontology `ObjectType` and its `PropertyType` definitions to an explicit tabular dataset snapshot. It is the boundary where typed imported records become typed ontology instances while retaining source provenance and sensitivity controls.

The caller must name an explicit snapshot/import. A binding never resolves `latest`. All materialization is read-only and produces in-memory instances; it does not update the snapshot tables, graph store, source registry, or external systems.

## 2. Binding shape

Bindings are versioned, serialisable YAML or JSON documents:

```yaml
binding_id: commerce.customer.v1
binding_version: 1.0.0
object_type_id: customer
object_type_version: 1.0.0
dataset_id: customers
schema_id: customers-v1
schema_version: 1.0.0
column_map:
  customer_id: customer_id
  email: email
  joined_on: joined_on
identity:
  strategy: record_key
  primary_key_column: customer_id
property_sensitivity:
  customer_id: personal
  email: personal
  joined_on: internal
fingerprint: sha256:...
```

Required binding keys are `binding_id`, `binding_version`, `object_type_id`, `object_type_version`, `dataset_id`, `schema_id`, `schema_version`, `column_map`, and `identity`. Unknown keys fail closed. The canonical fingerprint covers the complete validated binding, including the column map and versions.

## 3. Snapshot scope and identity

`validate_binding` receives an explicit snapshot manifest containing at least `import_id`, `dataset_id`, `schema_id`, `schema_version`, schema fingerprint, file SHA-256, source registry ID, and row storage reference. The manifest must match the binding's dataset and schema identity exactly.

For a primary-key-backed binding, `record_key` is `agora.identity.stable_record_key(dataset_id, primary_key_value)`. It is stable across snapshots and independent of import ID, file hash, schema fingerprint, row number, and non-key values. Each materialized instance also carries the snapshot-scoped `row_id`; the same record across snapshots therefore has one enduring `record_key` and distinct immutable row versions.

Consumers must provide `import_id` explicitly. An omitted, ambiguous, or `latest` selector is rejected.

## 4. Column and type contract

Every mapped column must exist exactly once in the snapshot schema and map to an existing property on the declared ObjectType. Missing, extra, duplicate, or differently named columns fail closed. The binding does not silently infer mappings.

The implementation accepts these tabular-to-ontology compatibility pairs:

| Tabular type | Compatible ontology type |
|---|---|
| string | string, identifier, enum |
| integer | integer, decimal |
| decimal | decimal |
| boolean | boolean |
| date | date |
| timestamp | timestamp |
| enum | enum, string |

Nullability, enum values, decimal precision/scale, date/timestamp timezone, and bounds remain enforced by the ingestion schema. A value that is valid in the snapshot but incompatible with the PropertyType is a binding validation error; no coercion through binary floating point or silent stringification is permitted.

## 5. Sensitivity, purpose, and retention

Binding may not lower sensitivity. The effective instance sensitivity is at least the snapshot column sensitivity and must satisfy the ontology property's classification. A `personal` column may map only to a `personal` or `sensitive` property. A `sensitive` column may not map to a less restrictive property. Purpose and retention metadata must remain present for personal data before downstream use; the binding cannot waive those requirements.

## 6. Provenance on every instance

Each materialized instance carries:

- `object_type_id` and version;
- `property_values` keyed by `property_id`;
- `record_key` when the binding declares a primary key;
- snapshot `row_id`;
- `import_id`, dataset/schema IDs and versions;
- `source_registry_id` and full file SHA-256;
- source locator, including the source record number and primary-key locator;
- binding ID/version and binding fingerprint;
- property sensitivity metadata.

The provenance fields are copied from the explicit manifest and row data, never reconstructed from a filename or an implicit latest snapshot.

## 7. API and safety contract

The current implementation provides:

- `load_binding(path_or_payload)` — parse and validate the binding shape and fingerprint;
- `validate_binding(pack, snapshot_manifest, binding)` — validate object/property existence, schema identity, mappings, stored-schema types, sensitivity, purpose, retention, and identity strategy;
- `materialize_instances(binding, pack, project, import_id)` — load the stored manifest, call `validate_binding` itself, then call `agora.tabular.read_snapshot` for the named import and return read-only instances with provenance. Materialization must fail closed when the binding or pack is unknown or invalid; callers may not bypass validation.

`materialize_instances` must reject unknown bindings, missing imports, missing stored type information, schema drift, sealed-holdout misuse, missing primary keys, and `latest` selectors. Type information comes from the stored schema associated with the explicit import, never from a caller-edited manifest. Each instance carries effective per-property sensitivity (the maximum of source-column and ontology-property sensitivity), even when no binding override is supplied. It must not call a real driver, open a network connection, write to a snapshot, mutate a project database, or invoke `agora/sim/**`.

### Rules added by the O0 close-out audit

- `property_sensitivity` may name only mapped property IDs. A mistyped key is refused, not ignored.
- An override may raise a property's classification and never lower it below the pack's declared value, even when the source column is less sensitive. The policy decision made before any read uses the highest declared classification of the mapped properties.
- The ObjectType must use the `record_key` identity strategy. An `assigned` type cannot be bound.
- Every row read must satisfy the property's `nullable` rule and, when listed, its `allowed_values`. Decimals compare numerically; other values must have the same type. Errors name the property and never the value. `iter_source_object_refs` checks rows as it yields them, so a caller that indexes them must do so in one transaction, as the object store does.
- An object type's declared `unique_keys` are checked over the whole import by `materialize_instances` and `iter_source_object_refs`; a single-row read cannot check them. Scope and comparison rules: [ONTOLOGY_PORTABLE_SCHEMAS.md](ONTOLOGY_PORTABLE_SCHEMAS.md) section 2b.
- `materialize_instances` refuses a snapshot in which the binding's key column repeats. `iter_source_object_refs` does not keep every key in memory; the object store refuses the conflicting reference.
- `OntologyObjectStore.register_binding` refuses a binding that breaks the identity or classification rules above.

These checks run on new reads and registrations. They do not revisit object references already stored.

## 8. Acceptance tests and mutation proofs

The implementation must test both the commerce and civic ontology fixtures with one CSV-backed snapshot each. Tests must demonstrate:

1. valid bindings load and materialize typed instances;
2. the same primary key across two snapshots has the same `record_key` and different `row_id`;
3. sensitivity downgrade is rejected;
4. incompatible types are rejected;
5. missing, extra, duplicate, or unknown binding keys are rejected;
6. missing or mismatched dataset/schema identity is rejected;
7. every instance contains the provenance fields above;
8. explicit `import_id` is required and `latest` is rejected;
9. sealed-holdout snapshots cannot be materialized for an unauthorized role;
10. snapshot tables and manifests are unchanged after materialization.

Required scratch mutations, never committed:

- remove the sensitivity comparison; the downgrade test must fail;
- bypass the type compatibility check; the mismatch test must fail;
- compute `record_key` from `row_id`; the cross-snapshot identity test must fail.

## Snapshot content checks on read

Every ontology read of a snapshot (in-memory materialization, object-reference indexing, and single-object reads) checks what it reads and refuses on a mismatch:

- The requested `import_id` is recomputed from the stored manifest's dataset ID, file SHA-256, schema fingerprint, parser version and data role, and the source registry ID is recomputed from three of them. Relabelling an import's data role, for example `sealed_holdout` to `context`, is refused.
- Each row's `row_id` is recomputed from its stored values and record number together with those manifest facts, and its source locator must match exactly.
- Reads of a whole import also require the stored row count to equal `accepted_records`.

Limits. These are unkeyed hashes, not signatures. A single-object read compares against the row ID pinned in the ontology store, so a changed row is refused even if its row ID was recomputed, as long as the ontology store itself was not rewritten. Before a row ID is pinned, someone who can write `tabular.sqlite3` can forge values together with a matching row ID, or delete rows and adjust `accepted_records`, and these checks alone will not notice; object-reference indexing also requires the ingest record described below. The stored values are not re-derived from the original file bytes. Column types, column sensitivity and column policies in the manifest are covered by neither identifier.

## Ingest record in the audit chain

Under the protected defaults, `ingest_csv` needs an anchored audit writer. Before it commits a new snapshot it appends a `tabular_import_attested` event holding the SHA-256 of the import record and every row (`agora-import-content-sha256/v1`). The digest is computed from the parsed values in memory and must equal the digest of what the database holds. If the check or the append fails, no rows are imported.

`materialize_binding` (object-reference indexing) refuses unless the import's current digest has such an event in the same cleanly anchored chain, the row IDs it pinned are the rows in that digest, and the binding is valid for the recorded manifest.

- **Imports made without a record cannot be indexed.** This includes every import made before this change. Importing the same bytes again is a no-op and deliberately records nothing, because that would attest whatever is stored now. To index such data, import the source file into a new project.
- The same chain must be supplied at ingest and at indexing.
- Only object-reference indexing requires the record. In-memory materialization, scenario inputs, link source references and single-object reads do not check it.
- This is not a signature. Someone who can append to the chain and its anchor, or run code in the service process, can record a forged snapshot. It does not show that the source file was correct.
- A commit that fails after the event was appended leaves an event for content that was never stored.

## 9. Governance and non-goals

Bindings preserve the existing source-role and privacy controls. They do not grant permission to calibrate, validate, export, or write back. Rungs 2–4 remain simulation-only, and `VALIDATED_PREDICTION_ENABLED` remains `False`. Real personal data, credentials, network access, external drivers, simulations, calibration, backtests, and study changes are outside this contract.
