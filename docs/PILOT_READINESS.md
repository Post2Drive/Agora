# Pilot Readiness — Engineering Gate

**Assessment base:** `main` at `81361c7` (PRs #30, #32, and #33 merged;
scenario-input implementation PR #31 remains under review).

This is an engineering readiness document for a first external pilot in India
with one customer. It permits synthetic data or customer-supplied non-personal
data only. It is not a marketing claim, production approval, or authorization
to use personal data, external write-back, or validated prediction.

## What exists on main

| Rung | Present capability | Evidence on main |
| --- | --- | --- |
| 1 — Foundation | Reproducible project identity, deterministic seed/resume checks, safe local run store, supported Python/OS CI matrix | `tests/test_engine.py`; merged Rung 1 evidence in `docs/RUNG_1_3_STATUS.md` |
| 2 — Ontology | Versioned ontology registry, fingerprints, fail-closed ActionType simulation guards, binding validation/materialization, synthetic retail pack | PRs #21, #24, #30; `domain_packs/retail_in/`; 377-test clean-checkout proof for #30 |
| 3 — Ingestion/provenance | Typed CSV snapshots, immutable imports, source/file provenance, stable record identity, sensitivity and policy checks, read-only binding materialization | PRs #18–#20, #24, #30; `agora/tabular.py`, `agora/ontology/binding.py` |
| 4 — Scenario bridge | Contract and design for explicit snapshot-derived scenario inputs and run provenance; implementation is not yet merged | `docs/SCENARIO_INPUTS_SPEC.md`, `docs/RUN_PROVENANCE_SPEC.md`; PR #31 under review |
| 5 — Decision records | Design contract for evidence links, approvals, and outcome separation | `docs/DECISION_RECORD_SPEC.md` (PR #26) |
| 6 — Security architecture | Design contract for identity, policy, audit, erasure, and breach controls; runtime controls are not implemented | `docs/SECURITY_ARCHITECTURE.md` (PR #27) |

## Gaps, in required order

1. **Finish the scenario-input bridge.** Merge PR #31 only after its CI and
   privacy mutation proofs pass. The adapter must remain limited to `context`
   and `scenario_input`, require explicit property authorization, and redact
   unlisted sensitive values without retaining raw values or reversible hashes.

   Exit test: the full suite passes; calibration, validation, and holdout roles
   fail closed; authorized properties remain available; unlisted sensitive
   properties are represented only by the fixed redaction marker and trace
   metadata.

2. **Implement run-record provenance.** The existing run store must persist the
   scenario-input manifest and `scenario_hash` append-only, verify tampering,
   block resume after any input change, and label old records as legacy. Do not
   guess the storage location: implementation must name the actual store file
   or table from the code before editing it.

   Exit test: an unchanged input resumes; changed snapshot/schema/binding/
   ontology/policy/parameters fail safely; the original record is unchanged;
   reports contain exact import ID, scenario hash, provenance fingerprints, and
   an exploratory label; legacy records cannot resume through this path.

3. **Complete the pilot data contract.** For the first customer, accept only
   synthetic or customer-supplied non-personal data through the typed tabular
   schema and an approved domain-pack binding. No personal columns, credentials,
   network connectors, or write-back are in pilot scope.

   Exit test: a clean-room fixture with the customer-approved schema imports,
   validates, materializes, and produces stable provenance; malformed rows,
   schema drift, unknown columns, unsafe roles, and missing policy metadata fail
   closed with non-sensitive diagnostics.

4. **Exercise decision-record and security gates.** Before any external pilot,
   define the owner, data-use purpose, retention, approval record, incident
   path, and deletion/erasure procedure in the merged design contracts. These
   are governance prerequisites, not features inferred from simulation output.

   Exit test: a dry-run approval record links an exact scenario hash, binding,
   source snapshot, and report; an expired or mismatched approval is rejected;
   an erasure request has a documented, testable impact on dependent records.

5. **Keep output exploratory.** `agora/report/writer.py` keeps
   `VALIDATED_PREDICTION_ENABLED = False`. The pilot must not present simulated
   preferences or actions as observed demand, sales, forecasts, or validated
   predictions. Any real-world outcome must be collected separately with its
   own consent and evidence lineage.

   Exit test: report tests assert exploratory labelling and reject validated
   prediction mode; simulated event counts remain separate from observed
   outcomes and customer decisions.

## Pilot boundary

Until all gaps above have passing exit tests, the safe pilot boundary is a
local, read-only, exploratory run using synthetic or non-personal customer data
with explicit snapshot IDs. No personal-data prompts or memory, no calibration,
backtests, forecasts, external drivers, credentials, network connectors,
write-back, or production decisions are included.
