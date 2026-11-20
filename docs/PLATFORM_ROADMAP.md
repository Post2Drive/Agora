# AGORA Platform Roadmap

**Status:** architecture and delivery baseline. This document records the accepted direction and current capability evidence; it does not claim that planned capabilities are implemented.

**Baseline:** GitHub `main` at `33f44c18cfc1eebd24074694c6cfbe963200380a` (20 November 2026). Status statements below are assessed against that commit, not against later unmerged pull requests.

## Product direction

AGORA is a governed decision platform. Data is integrated with provenance, represented through a domain ontology, used by one or more decision engines (including exploratory simulation), and connected to decisions whose inputs, approvals and outcomes can be audited.

The product is built as a modular monolith with stable internal contracts first. Do not create a fleet of microservices or independently branded subsystem products prematurely. The previous proposed subsystem names are dropped; use capability and domain language in architecture, code and user-facing documentation.

## Six-rung capability ladder

Each rung has an explicit exit test. A rung is not complete because a module or document exists; its exit test must be demonstrated by implementation and evidence.

| Rung | Capability | Exit test |
|---|---|---|
| 1. Foundation | Reproducible project/runtime foundation, modular boundaries, stable project identity and safe local operation | A clean supported environment installs and runs the suite; the same code, scenario/configuration hash, seed and deterministic inputs reproduce the same result; interrupted work can resume safely; CI protects the supported OS/Python matrix. |
| 2. Ontology | Versioned object, property, link and action definitions; stable identities; typed relationships; source bindings | Two different domain packs validate against the same ontology contract; type/version changes are detectable; object/link identity and constraints validate; every source-backed object resolves to a source registry ID and locator; every rung 2–4 ActionType is simulated-only. |
| 3. Ingestion with provenance | Typed, repeatable data ingestion with source hashes, row/record locators, manifests, schema validation and audit | CSV and mock database imports preserve typed values and deterministic row identity; 2,001+ rows are not silently truncated; re-import is idempotent; rejected rows/failures are explicit; every derived record traces to source ID, full SHA-256 and source locator; connector tests prove read-only behaviour. |
| 4. Simulation as decision engine | Scenario and agent simulation used as one decision-analysis engine, with controlled inputs, repeatable runs and evidence separation | Runs are reproducible and comparable under matched inputs; events and metrics have defined denominators and lineage; simulated preferences/actions remain visibly distinct from observed real-world outcomes; exploratory output is not represented as validated prediction. |
| 5. Decisions and actions | Decision records, alternatives, rationale, evidence, human approval, controlled execution and outcome tracking | A decision is immutable/versioned with linked evidence and an approval trail; actions are permission-checked, idempotent, auditable and recoverable; any future external write-back is disabled by default and requires a separately approved design, consent controls and a dedicated threat model. |
| 6. Security and deployment | Identity, authorisation, tenant isolation, data protection, audit, release and fleet/deployment controls | Security tests prove least privilege, tenant isolation, protected secrets, audit integrity and fail-closed behaviour; supported local/on-prem/private-cloud deployments can be installed, upgraded, monitored and rolled back reproducibly. |

**Scope rule:** focus delivery on rungs 1–4 until their exit tests pass. Rungs 5–6 remain architecture constraints and design work, not permission to expand into operational write-back or enterprise deployment prematurely.

## Accepted architecture decisions (ADR-001 to ADR-006)

The owner-approved architecture baseline accepts these six ADRs as design constraints. Acceptance does not mean every facility is already implemented.

| ADR | Accepted decision | Current evidence at baseline | Status |
|---|---|---|---|
| ADR-001 | Modular monolith with isolated workers | Python package, CLI and local web application; worker/process isolation is not yet a general platform facility | Partial; keep the modular-monolith direction |
| ADR-002 | OIDC identity with an offline/local adapter | Local host/access controls exist; no OIDC identity provider integration | Missing; retain as a future security requirement |
| ADR-003 | Hybrid RBAC + ABAC, central policy decision point and boundary policy enforcement points | No central policy decision/enforcement service or enterprise role/attribute model | Missing; define contracts before implementation |
| ADR-004 | Tenant-aware contracts; isolated single-tenant first | Project-scoped local data exists; proven tenant isolation and shared multi-tenant runtime do not | Partial at project boundary; do not claim tenant isolation |
| ADR-005 | Relational source of truth, object evidence and versioned ontology | SQLite project/graph stores, document ingestion and source registry exist; a versioned operational ontology is not implemented on baseline main | Partial; avoid premature vendor selection |
| ADR-006 | Versioned events, outbox, idempotent consumers and protected audit ledger | JSONL event queue and local hash-chained audit log exist; transactional outbox and externally anchored protected ledger do not | Partial; retain contracts and defer infrastructure |

## Four platform pillars

The four pillars are capability groupings, not separate products or independent subsystem brands.

| Pillar | Purpose | Evidence at baseline | Gap |
|---|---|---|---|
| Data integration | Connect, ingest, validate, transform, catalogue and trace data | File/document ingestion, RSS/event intake, source registry and provenance hooks | Typed tabular ingestion, robust row lineage, general connector framework and shared catalogue/lineage service |
| Ontology | Represent domain objects, properties, links, events and action contracts | Extracted entity/relation graph and graph persistence | Versioned operational ontology connecting data, permissions, actions and workflows |
| Operational actions | Turn approved decisions into controlled work and record outcomes | Simulation events/actions and local reports | General decision/workflow runtime, human approval and governed source-system execution |
| AI layer | Provide model adapters, agents, tools, evaluation and policy-bound reasoning | Multiple model adapters, cached LLM calls, simulation agents and report agent | Central model gateway and general policy-bound agent/tool runtime |

**Cross-cutting security:** identity, least-privilege authorisation, tenant isolation, secret handling, consent, audit integrity, data classification, privacy and human oversight.

**Cross-cutting deployment:** local-first operation, on-premise/private-cloud options, controlled upgrades, observability, backup/restore, release management and rollback. These are requirements, not current enterprise capabilities.

## Capability status at main 33f44c1

| Rung | Status | Evidence and limitation |
|---|---|---|
| 1. Foundation | Mostly in place; one owner-operated reset remains outside repository execution | Canonical main, four-matrix CI, governance foundation, reproducibility/neutral-start regression tests. The remaining local reset is an owner-operated step outside repository execution. |
| 2. Ontology | Design documents merged; no implementation yet | The artefact ontology specification (`ONTOLOGY_SPEC.md`) and domain ontology design (`DOMAIN_ONTOLOGY_MODEL.md`) are merged. No operational type registry, typed instance store or ontology enforcement is implemented yet. |
| 3. Ingestion with provenance | Partial | `agora/graph/ingest.py` handles document ingestion; CSV/TSV currently enter the text path and are capped at 2,000 rows. `agora/sources/registry.py` and `agora/governance.py` provide source hashes, roles, operation records and audit hooks, but are not a typed tabular ingestion system or external database connector framework. |
| 4. Simulation as decision engine | Partial | The simulation engine, scenario/event model, reports, calibration/backtesting facilities and governance foundations exist. Reproducibility and neutral-start tests are present. Exploratory simulation is not validated prediction, and baseline measurement/causal limitations must be reported. |
| 5. Decisions and actions | Not started as a governed real-world execution capability | Simulation actions/events exist; there is no approved general decision record, human approval workflow or external write-back runtime. Real-system write-back remains prohibited for rungs 2–4. |
| 6. Security and deployment | Not started as enterprise capability | Local host protections and project-level controls exist; OIDC, central RBAC/ABAC, proven tenant isolation, fleet deployment and enterprise release/rollback are absent. |

### Relevant implementation references

- `agora/governance.py`: operation journal, source registration, audit event hooks and source-role helpers.
- `agora/sources/registry.py`: source identity, SHA-256, role and provenance metadata.
- `agora/events.py`: queued event intake, deduplication, source registration and sync to a running study.
- `agora/graph/ingest.py`: current document/text ingestion path; CSV/TSV are not yet a structured row store.
- `agora/validation/audit_log.py`: local audit log foundation.
- `agora/report/writer.py`: `VALIDATED_PREDICTION_ENABLED = False`; keep this fail-closed.
- `tests/`: regression and governance test suite; baseline main test count is 264.

## Simulation and prediction policy

1. **Exploratory Simulation** is the default. Outputs are hypotheses and synthetic agent behaviour; they are not actual public opinion, demand, votes, purchases or sales.
2. **Validated Prediction** is domain- and target-specific. It requires reliable ground truth, independent holdout data, relevant baselines, predeclared metrics and thresholds, reproducibility, uncertainty reporting and documented limitations.
3. Validation in one domain never transfers automatically to another.
4. The domain validation registry must record scope, data provenance, holdout design, baselines, metrics, results, uncertainty, limitations, version and permitted claims.
5. `VALIDATED_PREDICTION_ENABLED` remains `False` until a separately approved qualification process has passed. Do not enable it by renaming features, adding a UI mode or relying on simulation results.

## Action and write-back boundary

For rungs 2–4, all ActionTypes must carry:

- `simulated_only: true`
- `execution_mode: simulation_only`
- `external_writeback: prohibited`

A simulated event may update only its own simulation state/event store. It must not call a business API, create a real order, send a message, modify a customer/account record, initiate payment or reserve inventory.

Rung 5 is the earliest possible point for considering real-system write-back. It requires a separate architecture decision, threat model, explicit owner approval, scoped permissions, consent/legal review where applicable, human approval, idempotency, audit, rollback and incident handling. Nothing in this roadmap authorises that work now.

## Delivery sequence

1. Complete and review the ontology design (rung 2).
2. Review and approve the ingestion specification before any rung 3 code.
3. Implement structured CSV ingestion as a separate path; preserve the existing document ingestion path.
4. Implement a read-only connector contract with a mock connector only; no real database drivers or network access in the first implementation.
5. After the ingestion specification is approved and merged, deliver the CSV and mock database contract as separate, independently tested pull requests.
6. Reassess rung 1–3 exit tests and publish a concise evidence-based status before expanding scope.

## Governance

- No simulations, calibration, backtests, forecasts or study mutations are started by a documentation task.
- No real database drivers, network access or credentials are introduced by the rung 3 mock connector work.
- No changes to `agora/sim/**`, `agora/examples/**`, study folders, `.agora_governance_*` or backup folders are allowed in the documentation pull requests.
- Each pull request must contain only its named files, be updated to current main, pass all four required CI jobs on its exact final head, retain at least the 264-test baseline, and receive independent reviewer approval for that exact head before merge.
- Merge only at the exact reviewed head, after recording the owner's applicable approval.
