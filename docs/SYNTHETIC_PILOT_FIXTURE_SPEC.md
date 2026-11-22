# Synthetic Operator-Pilot Fixture Specification

**Status:** Main `969a040a497668740d20e1ace83841046639b2d6` includes the checked-in `agora/pilot_fixtures/synthetic-units-v1` fixture from #125 (head `914d570ce62c5d9c1157ec0470d9b948ff17dfc9`, exact-head CI `44993280261` passed 4/4). It verifies per-file hashes against a local manifest, but the manifest digest is not independently pinned and symlinked fixture paths are followed. The workdir guard also accepts unrelated pre-existing content if the `synthetic-pilot` child does not exist.
**Assessment base:** `main` at `969a040a497668740d20e1ace83841046639b2d6` (22 November 2026).
**Data class:** Invented synthetic records only

## 1. Purpose

Define a small, deterministic, checked-in fixture set for the future operator-usable synthetic pilot. The fixture must exercise import, schema validation, ontology binding, scenario-input construction and governed decision boundaries without representing real people, customers, organisations, locations, demand or sales.

The merged #88 pilot originally embedded `SYNTHETIC_CSV`, schema and binding definitions in `agora/pilot.py`. PR #125 now adds the following checked-in fixture paths on main:

- `agora/pilot_fixtures/synthetic-units-v1/units.csv`
- `agora/pilot_fixtures/synthetic-units-v1/schema.json`
- `agora/pilot_fixtures/synthetic-units-v1/binding.json`
- `agora/pilot_fixtures/synthetic-units-v1/manifest.json`

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
- Store fixture/schema/binding content hashes in the run record. #123 currently hashes only the embedded CSV; it must also persist schema, binding and manifest hashes plus ontology/policy fingerprints, and verify the complete envelope on load. Never invent or pre-fill hashes in documentation.

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
3. Mutation tests remove a required column, duplicate an ID, add an unknown column, alter a pinned binding target, change fixture bytes, change the manifest and payload together, alter the independently pinned manifest digest, introduce symlinked fixture paths, and replace an exact ID with `latest`; each must fail closed.
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
