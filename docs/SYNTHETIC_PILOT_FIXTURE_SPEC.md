# Synthetic Operator-Pilot Fixture Specification

**Status:** Draft specification for Claude and owner review; no fixture files are added by this document.  
**Assessment base:** `7afa1414acd9c2e68361faab81a5d246597a5919` (22 November 2026)  
**Data class:** Invented synthetic records only

## 1. Purpose

Define a small, deterministic, checked-in fixture set for the future operator-usable synthetic pilot. The fixture must exercise import, schema validation, ontology binding, scenario-input construction and governed decision boundaries without representing real people, customers, organisations, locations, demand or sales.

The paths below are proposed and were verified absent on the assessed mainline:

- `fixtures/pilot.csv`
- `fixtures/pilot-schema.yaml`
- `fixtures/pilot-binding.yaml`

This document does not add data or authorise a simulation, engine call, external connector or write-back.

## 2. Fixture contents

Use a compact dataset (suggested 6–10 rows) with deterministic identifiers and deliberately fictional categories. Avoid names, email addresses, phone numbers, street addresses, precise locations, dates of birth, demographic inference or any data copied from a real source.

Suggested CSV columns, subject to the existing import schema contract:

| Field | Purpose | Constraint |
|---|---|---|
| `record_id` | Immutable row identity | Unique fixed token, e.g. `syn-row-001` |
| `cohort_code` | Synthetic grouping | Values such as `cohort-a` / `cohort-b` |
| `category_code` | Domain category | Small enumerated synthetic vocabulary |
| `quantity` | Numeric measure | Fixed small non-negative number |
| `unit_code` | Measure unit | Controlled token, not free text |
| `source_ref` | Fixture provenance | Fixed synthetic source token |
| `sensitivity` | Declared data class | `public` or `internal` only |

Do not add any row that resembles a real customer, hospital, apartment, person, sale or Nutrivance/NCC record. Do not describe fixture values as observed outcomes.

## 3. Schema and binding contract

- The schema must declare every column, type, required/optional status, allowed values, null handling and numeric bounds.
- Reject unknown columns, duplicate IDs, malformed tokens, out-of-range values and undeclared categories.
- The binding must map each source column to an exact typed target field and declare purpose/retention only where the target contract requires them.
- The binding must use a pinned ontology/domain-pack version and immutable binding ID; no "latest" aliases.
- The importer must produce an exact immutable import ID and manifest hash. Re-importing changed content must produce a distinguishable snapshot, not overwrite an earlier one.
- Store fixture/schema/binding content hashes in the run record. Never invent or pre-fill hashes in documentation.

## 4. Determinism and provenance

- Keep fixture rows, schema and binding under version control; review changes as code.
- Pin a fixture-set identifier and version in the operator command.
- Compute SHA-256 over the exact bytes of each fixture artefact at runtime; persist the values in the provenance envelope described by `docs/RUN_PROVENANCE_SPEC.md`.
- The run must record repository SHA, fixture-set ID, schema hash, binding hash, import ID, manifest hash, ontology/binding fingerprints, policy fingerprint and an exploratory/synthetic label.
- A changed fixture must change its content hash and therefore the recorded run identity.
- Never log raw row values or sensitive payloads in the audit chain; log stable IDs, hashes and allow-listed event metadata only.

## 5. Required tests (future implementation)

1. Clean-checkout test confirms all three exact fixture paths exist and are parseable.
2. Golden-schema test proves required fields, types, enumerations and bounds.
3. Mutation tests remove a required column, duplicate an ID, add an unknown column, alter a pinned binding target, change the fixture bytes without updating the expected hash, and replace an exact ID with `latest`; each must fail closed.
4. Import test proves immutable snapshot/manifest IDs and that a changed fixture does not overwrite the prior snapshot.
5. Policy-denial sentinel proves denied access does not read protected source/snapshot payloads beyond the explicitly documented metadata preflight.
6. Provenance test verifies the fixture/schema/binding hashes and all required run-envelope fields.
7. No test may call `agora/sim/**`, run a simulation, use real data, access credentials/network services or perform external write-back.

## 6. Acceptance

- Only invented synthetic data is checked in.
- Fixture/schema/binding IDs and hashes are exact and reproducible.
- Schema and binding are pinned and reviewed.
- Tests cover invalid input, mutation resistance, immutable import and provenance.
- The operator workflow consumes these fixtures without invoking the simulation engine.
- The milestone remains unreached until Claude records the exact confirmation required by the milestone checklist and the owner separately approves any owner-only rehearsal.
