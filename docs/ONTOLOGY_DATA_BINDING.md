# Ontology Data Binding — Rung 2/3 Contract

**Status:** design specification only. This document defines a read-only binding contract; it does not add a connector, migrate storage, mutate snapshots, or enable simulation or external write-back.

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

The implementation PR will provide:

- `load_binding(path_or_payload)` — parse and validate the binding shape and fingerprint;
- `validate_binding(pack, snapshot_manifest, binding)` — validate object/property existence, schema identity, mappings, stored-schema types, sensitivity, purpose, retention, and identity strategy;
- `materialize_instances(binding, pack, project, import_id)` — load the stored manifest, call `validate_binding` itself, then call `agora.tabular.read_snapshot` for the named import and return read-only instances with provenance. Materialization must fail closed when the binding or pack is unknown or invalid; callers may not bypass validation.

`materialize_instances` must reject unknown bindings, missing imports, missing stored type information, schema drift, sealed-holdout misuse, missing primary keys, and `latest` selectors. Type information comes from the stored schema associated with the explicit import, never from a caller-edited manifest. Each instance carries effective per-property sensitivity (the maximum of source-column and ontology-property sensitivity), even when no binding override is supplied. It must not call a real driver, open a network connection, write to a snapshot, mutate a project database, or invoke `agora/sim/**`.

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

## 9. Governance and non-goals

Bindings preserve the existing source-role and privacy controls. They do not grant permission to calibrate, validate, export, or write back. Rungs 2–4 remain simulation-only, and `VALIDATED_PREDICTION_ENABLED` remains `False`. Real personal data, credentials, network access, external drivers, simulations, calibration, backtests, and study changes are outside this contract.
