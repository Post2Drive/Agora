# Pilot data contract

This contract defines the smallest customer-supplied input accepted by an Agora
read-only pilot. The pilot boundary is local, exploratory, and synthetic or
customer-supplied non-personal data only. It does not authorize real connectors,
credentials, external writes, or production decisions.

## Customer supply

Provide a UTF-8 CSV snapshot, a versioned YAML schema, and a versioned ontology
binding. The schema must declare a stable dataset and schema ID, every column's
type/nullability/sensitivity, one stable identity column, and fail-closed row
rules (`malformed: fail`, `unknown_columns: reject`, `missing_columns: reject`).
The binding maps each CSV column to an exact versioned ontology property and
declares the identity strategy. Use explicit `data_role: context` or
`scenario_input`; moving snapshots are not accepted.

## Schema template

```yaml
schema_id: customer-supplied-v1
schema_version: 1.0.0
dataset_name: synthetic_requests
header: true
row_policy: {malformed: fail, unknown_columns: reject, missing_columns: reject}
columns:
  - {name: record_id, type: string, nullable: false, primary_key: true, sensitivity: internal}
  - {name: category, type: string, nullable: false, sensitivity: public}
```

Allowed types are `string`, `integer`, `decimal`, `boolean`, `date`,
`timestamp`, and `enum`. Sensitivity is required and must be `public`,
`internal`, `personal`, or `sensitive`.

## Forbidden and refused input

Do not supply credentials, secrets, tokens, unredacted logs, or direct personal
columns such as names, email addresses, phone numbers, addresses, or government
identifiers. Personal and sensitive values are not used downstream by default.
An import may be retained only for validation, but downstream binding or
scenario construction fails closed without explicit purpose, retention, and
review policy metadata. `sealed_holdout` is refused at binding and scenario
boundaries.

## Diagnostics and failure behavior

Malformed rows, schema drift, unknown columns, missing columns, invalid types,
missing sensitivity, and missing policy metadata fail closed. The source file
and prior committed snapshot remain unchanged. Diagnostics expose only a stable
error code, source row number, and column name; they never include a personal or
sensitive value, a raw row, a secret, or a value-derived preview.

## Reproducibility and handoff

The import manifest records explicit schema/file hashes, role, parser version,
row counts, and source provenance. Binding and scenario artifacts retain their
fingerprints and explicit import ID. Pilot outputs are exploratory simulation
artifacts, not validated predictions or real demand; `VALIDATED_PREDICTION_ENABLED`
must remain `False`.
