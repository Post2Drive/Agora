# Agora Synthetic Pilot Runbook

**Status:** Controlled synthetic rehearsal using merged capabilities only  
**Purpose:** Exercise the local snapshot, binding, scenario-input package, simulation/report and decision approval boundaries without real personal data or external actions.

## 1. Scope and important limitations

This runbook is not an integrated data-to-simulation workflow. On the assessed mainline:

- CSV snapshot import and read-only catalogue commands exist.
- Ontology binding and scenario-input package builders exist as Python APIs.
- The scenario-input package is **not wired into** `agora/sim/engine.py`; the package must not be described as the input consumed by a simulation run.
- The decision record store and approval lifecycle exist as Python APIs.
- The decision-outcome recording/review implementation is not yet merged on this runbook's assessed base. Outcome review is therefore a **blocked follow-on stage**, not an executable step.
- The approval API still accepts a caller-supplied role string. Use synthetic identities only; this is not production authentication or trusted authorization.
- Purpose/retention propagation at the binding hook remains an open integration gap on this base. Keep the pilot dataset to public/internal synthetic columns. Do not use personal or sensitive fields.
- No end-to-end pilot command orchestrates all these stages.

Do not use Nutrivance, NCC Park Square, customer records, real sales, personal data, credentials or production decisions. No external write-back. `VALIDATED_PREDICTION_ENABLED` remains `False`.

## 2. Roles and separation

Assign named people before the rehearsal:

- **Pilot operator:** prepares the synthetic project, runs the commands and preserves outputs.
- **Data steward:** checks schema, sensitivity labels, exact import ID and source hashes.
- **Decision proposer:** prepares the decision record.
- **Independent reviewer:** checks the decision evidence and scope; must differ from proposer.
- **Approver:** separate from proposer and reviewer under the decision lifecycle; for this synthetic rehearsal, role input remains caller-supplied and is not a trusted identity assertion.
- **Observer/owner:** watches stop conditions and signs off the rehearsal report.

One person may hold multiple operational roles only where this does not violate decision separation-of-duties constraints. Do not let the proposer approve their own record or the reviewer act as approver.

## 3. Preconditions and synthetic fixtures

Create a disposable project directory and a separate evidence directory. Prepare:

1. a UTF-8 CSV with a stable synthetic record ID and a small number of rows;
2. a versioned YAML/JSON schema with strict row policy, declared types and sensitivity labels of `public` or `internal`;
3. a versioned ontology pack and binding file whose IDs and property mappings are exact;
4. an explicit project scope used consistently in policy checks and the decision record;
5. a synthetic scenario file for the standalone engine smoke test;
6. a temporary directory for the tabular, decision and audit SQLite files.

Do not include names, emails, phone numbers, addresses, government identifiers, secrets, tokens, free-text personal notes or any real-world record. Keep the fixture minimal and review it before import.

## 4. Step A — import an immutable CSV snapshot

The merged CLI exposes these commands:

```bash
agora data import-csv --project ./pilot-project --csv ./fixtures/pilot.csv --schema ./fixtures/pilot-schema.yaml --role scenario_input
agora data snapshots --project ./pilot-project
agora data show --project ./pilot-project --import-id <EXACT_IMPORT_ID>
agora data rejected --project ./pilot-project --import-id <EXACT_IMPORT_ID>
```

Use the exact `import_id` printed by the import command. Never substitute `latest`.

Expected artefacts:

- `pilot-project/data/tabular.sqlite3`;
- immutable import manifest with schema/file hashes, parser version, data role and row counts;
- rejected-row diagnostics containing row number, column and stable error code only.

Verify that accepted plus rejected row counts reconcile with parsed records. Confirm that no raw row values appear in diagnostics. If import fails, stop and correct the synthetic fixture/schema; do not weaken validation.

## 5. Step B — validate and materialize an ontology binding

The binding path is a Python API, not a dedicated `agora binding` CLI command:

- `agora.ontology.binding.load_binding(...)`
- `agora.ontology.binding.validate_binding(pack, snapshot_manifest, binding)`
- `agora.ontology.binding.materialize_instances(binding, pack, project, import_id, policy=...)`

Use the exact imported snapshot ID and a reviewed, versioned ontology pack/binding. Supply a policy callable that evaluates the `binding` operation through the central policy enforcement path. Do not omit the policy callable in this governed rehearsal.

Expected artefact: an in-memory list of provenance-rich instances carrying row/import IDs, source locator, schema and binding fingerprints, ontology property values and sensitivity metadata. The API does not itself provide a complete pilot CLI/export workflow.

Stop if the binding references an unknown property/version, the snapshot columns do not match, policy denies, or any personal/sensitive field is discovered. This runbook's base does not close the purpose/retention propagation gap at this hook.

## 6. Step C — build a deterministic scenario-input package

The available API is:

```python
from agora.scenario_inputs import build_scenario_input

package = build_scenario_input(
    binding, ontology_pack, project_path, exact_import_id,
    scenario_parameters=synthetic_parameters,
    transformation_policy=None,
    policy=policy_callable,
)
```

Use only public/internal synthetic fields for this runbook. The API rejects `latest`, verifies the committed import, validates the binding, and returns a package containing a manifest, scenario hash, instances and run-record metadata. A policy callable should evaluate the `simulation_input` operation.

Expected artefacts are in-memory: `package["manifest"]`, `package["scenario_hash"]`, `package["instances"]` and `package["run_record"]`. Persisting/consuming this package through the simulation engine is not implemented on this base.

**Hard stop:** do not claim that the next simulation uses these package instances. Simulation wiring remains a separate, unimplemented stage. Do not edit `agora/sim/**` as part of this runbook.

## 7. Step D — standalone synthetic engine smoke test (not connected to Step C)

Use an independent hand-written synthetic scenario, not the scenario-input package:

```bash
agora new ./engine-smoke --from demo
agora check ./engine-smoke --mock
agora run ./engine-smoke --mock
agora status ./engine-smoke
agora report ./engine-smoke --mock
```

This is a separate smoke test of the existing engine/report path. The demo is a template; inspect and replace it with a small synthetic scenario approved for the rehearsal if its contents do not fit the test objective.

Expected artefacts include the project scenario/database, completed round status and exploratory report outputs. Preserve the run ID, scenario hash where available, report provenance and mode labels. A completed mock run demonstrates software-path execution only; it is not evidence of real demand, sales, predictive validity or causal effects.

Stop if the report gate rejects provenance, the output is not clearly exploratory/simulated, or any step attempts to access real data or external systems.

## 8. Step E — create and approve a synthetic decision record

There is no dedicated decision-record CLI workflow. Use a reviewed local Python harness with the merged APIs:

- `agora.decisions.schema.load_decision_record(payload)`
- `agora.decisions.store.DecisionRecordStore(path)`
- `agora.decisions.approval.propose(...)`
- `agora.decisions.approval.approve(...)`
- `agora.audit_chain.AuditChainStore(path)`

Prepare a valid version-1 draft with non-empty project scope, statement, alternatives, exact evidence references, rationale, assumptions, uncertainty, outcome measures, proposer, reviewer, timestamps and review date. Reference only immutable IDs/fingerprints; never use `latest`. Append the draft, propose it as the named proposer, and approve only the exact current version/fingerprint/scope/evidence with distinct synthetic actors and an audit store supplied.

The approval API currently accepts `role` and `subject` as caller-supplied arguments. The central PDP checks role, scope and sensitivity, but the identity adapter is not implemented. Therefore this step is only a synthetic API-path demonstration, not proof of authenticated or production authorization.

Expected artefacts: immutable decision versions and approval event history in the decision store, plus allow-listed lifecycle/approval events in the audit chain when the optional audit store is supplied. The decision and audit stores are separate SQLite files; a failed audit append after a stored transition requires reconciliation and must not be represented as one atomic transaction.

Verify the audit chain with `AuditChainStore.verify()`. A valid internal hash chain does not detect tail truncation without an independent anchor.

## 9. Step F — observed outcome review (blocked; do not execute on this base)

The outcome contract is specified in `docs/DECISION_OUTCOMES_SPEC.md`, but its implementation is not merged on this assessed mainline. Do not import or call code from an unmerged PR and do not fabricate an outcome table or review command.

When a separately reviewed implementation is merged, a future runbook revision may add the exact record/review APIs, evidence registry prerequisites, policy operation, actor separation and reconciliation steps. Any outcome must be observed evidence with an immutable source reference; simulated preferences/actions are never observed outcomes.

## 10. Deny cases to demonstrate

Use isolated synthetic fixtures and record only stable reason codes/event IDs:

1. Unknown CSV column or missing required column — import must fail closed.
2. Malformed row or invalid type — import must reject without exposing raw values.
3. `sealed_holdout` import used for scenario input — construction must deny.
4. `latest` supplied instead of exact `import_id` — scenario-input builder must reject.
5. Binding references wrong schema/property version — validation/materialization must deny.
6. Missing/invalid policy callable — enforcement must deny where a policy hook is supplied.
7. Policy scope mismatch or missing sensitivity metadata — PDP must deny.
8. Personal/sensitive field without approved transformation policy — scenario-input construction must deny; do not bypass the policy.
9. Decision approval with stale version/fingerprint/evidence, expired review date, wrong scope, non-approver role, or proposer/reviewer/approver overlap — approval must deny.
10. Audit-chain tampering in a disposable copy — verification must report invalid chain; do not repair the evidence copy.

Do not test a deny case by weakening the policy, altering production files, or injecting real data.

## 11. Logging and evidence bundle

Record:

- runbook version, Git commit, operator and synthetic fixture IDs;
- schema, import ID, file hash, binding fingerprint and ontology pack fingerprint;
- scenario-input manifest/hash and explicit note that it was not consumed by the engine;
- standalone engine scenario/run identifiers, mock backend, rounds and report mode;
- decision ID/version/fingerprint, synthetic actor labels and policy decision reason codes;
- audit-chain verification result, entry count and head hash;
- all denials, stop events, exceptions and deviations using redacted metadata only.

Do not record raw CSV rows, personal values, credentials, tokens, private keys or unrestricted free text in logs or audit events.

## 12. Stop conditions and sign-off

Stop immediately if:

- any real/personal/sensitive data or secret enters the fixture;
- an exact immutable import ID, schema, binding or provenance hash cannot be verified;
- a policy denial is bypassed or a policy hook is omitted;
- a holdout snapshot reaches scenario input;
- anyone claims the scenario-input package was consumed by the simulation engine;
- a report is missing exploratory/simulated labels or fails provenance checks;
- a decision transition is stale, out of scope, unauthorised or not auditable;
- audit verification fails or a decision/audit store mismatch appears;
- any external network, connector, write-back or production action is attempted.

The pilot operator signs the execution record; the data steward signs the snapshot/binding review; the independent reviewer and approver sign the decision record; the system owner signs the final rehearsal outcome. Sign-off means only that the synthetic rehearsal followed this runbook. It does not validate predictions or authorise a live pilot.

## 13. Current capability references

This runbook describes only merged mainline modules: data snapshot CLI (#28), scenario-input adapter and binding (#31, #43), run provenance contract (#35), decision schema/store (#37), audit-chain store (#38), PDP (#39), approval state machine (#42), report provenance gate (#44), retention/erasure design (#45), and governed-pipeline synthetic test (#46). Identity and audit-anchor design specs are merged (#51–#52), but their implementations are not claimed here.

The scenario-input-to-engine bridge is still not wired. Decision outcomes/review are not implemented on this runbook base. The purpose/retention propagation fix is still pending merge. No simulation wiring, calibration, backtest, forecast, study mutation, real data, credentials, network, or external write-back is part of this runbook.
