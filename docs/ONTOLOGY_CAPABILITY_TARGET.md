# Agora Ontology Capability Target

**Status:** Strategy and staged delivery proposal with partial O1 implementation. O1 remains incomplete; this document claims no capability beyond the evidence listed below and does not authorize data acquisition, external integrations, action execution, or deployment.

**Strategic direction:** Build Agora's ontology layer as a transparent, portable and governed semantic foundation for decision work, distinguished by complete provenance, portable schemas, explicit human authority and independently verifiable behavior. This is a target, not a present capability claim.

## Capability areas

The target is defined from Agora's own requirements: a shared versioned vocabulary, durable source-backed records, governed actions, stable contracts for applications, enforced access control, and honest separation of observed facts from model-generated or simulated content. Each area below states what must be demonstrated, not what any other product offers. Where a requirement cannot be assessed fairly from available evidence, mark it unknown rather than assume.

## Current Agora evidence

At main commit `3b907e5fb384de67a4ce78bece78e400e23c1531`, Agora contains:

- Domain-pack parsing and versioned `ObjectType`, `PropertyType`, `LinkType`, and `ActionType` definitions in `agora/ontology/registry.py`.
- A fingerprinted, version-aware registry that rejects conflicting reuse of the same type ID/version. Registry state is currently in memory.
- A project-local SQLite store persists immutable, fingerprinted pack and binding definitions, source-row references, exact source-backed object reads, and typed temporal links. Link writes enforce exact endpoints, declared cardinality, endpoint sensitivity, policy, principal-derived actor, and audit. Bounded keyset object queries and direction-aware link traversal are now implemented with exact import scope, typed filters, stable cursors, and bounded pages. Repository CI passed for the implementation, but feature-specific tests remain outstanding.
- YAML/JSON loading with duplicate-key rejection.
- Read-only tabular snapshot bindings that check exact dataset/schema/import identity, property mappings, types, sensitivity, and provenance, then materialize instances in memory.
- Registry and binding tests, including stable cross-snapshot record identity and rejection of type/sensitivity mismatches.
- Domain packs and fixtures.

These are real early ontology capabilities, not an integrated ontology platform. A durable project-local ontology object-reference and link store with bounded internal queries and traversal now exists, but no public graph query service, stable external ontology API or generated SDK, managed object/link editing workflow, ontology authoring/browser UI, or complete identity and authorization layer is established. Action definitions are constrained to simulation-only, but there is not yet a general action runtime over persistent ontology objects. A permission field or design contract alone is not an enforced boundary.

## Product goals

1. **Shared semantic layer:** applications and decision engines use one versioned vocabulary for objects, properties, links, events, and permitted actions.
2. **Operational data model:** source-backed, authored, derived, observed, and simulated records remain distinct and linked through explicit lineage.
3. **Usable contracts:** typed schemas and stable APIs/SDKs let independent applications query and safely act on ontology data.
4. **Governed actions:** actions have typed inputs, preconditions, effects, policy checks, approvals where required, idempotency, audit, and recoverable outcomes.
5. **Enterprise controls:** identity, tenant boundaries, classification, purpose/retention, permissions, audit integrity, and deployment behavior are enforced and demonstrated.
6. **Measured strengths:** every claimed strength has a test or operational proof. Target strengths include complete provenance, portable ontology packs, explicit human authority, and clear separation of observed facts from model-generated or simulated content.

## Design principles

- Treat provenance, time, sensitivity, and confidence as core semantics, not optional metadata.
- Keep observations, human assertions, derived claims, forecasts, and simulated events distinct.
- Use stable IDs, immutable versions, explicit migrations, and historical readability.
- Require explicit snapshot and version selection; never resolve `latest` implicitly for governed decisions.
- Keep ontology definitions portable and serializable, with a documented schema and export path.
- Enforce policy at service boundaries. UI state, caller-supplied labels, and ontology metadata are not authorization.
- Keep single-user local operation useful; add shared tenants only with demonstrated isolation.
- Default to no real-world write-back. Simulation-only actions cannot call external systems.
- Preserve the modular-monolith direction until measured needs justify another architecture.
- An ontology does not grant data-use rights.

## Capability scorecard

| Capability | Requirement | Agora evidence today | Target and proof |
|---|---|---|---|
| Semantic types | Versioned object, property, link and action types shared by every application | Versioned pack definitions and parser | Portable schemas; independent domain packs use one contract; compatible evolution and explicit breaking changes |
| Identity and links | Stable object identity and typed relationships that applications can rely on | Durable source-backed object references and immutable typed temporal links with project/pack/type/import identity | Feature-specific integrity coverage, merge/split history, and cross-project identity rules |
| Data connection and lineage | Every object traceable to an exact source snapshot | Explicit snapshot binding contract, source IDs, hashes, locators, read-only materialization | Repeatable imports, full row lineage, schema evolution, reconciliation, retention/deletion handling, and connector boundaries |
| Query and application APIs | Versioned, typed, paginated access for independent applications | No general ontology API/SDK established | Versioned query/mutation APIs, typed SDK, pagination, filters, consistency rules, compatibility promises, and API security evidence |
| Actions and workflows | Declared, policy-checked actions with approval, audit and recovery | Action contracts, a simulated-only boundary and library-only [action proposals](ONTOLOGY_ACTION_PROPOSALS.md) over stored objects, with a recorded approval by a different approver that expires, can be withdrawn, admits once (requiring a signed approval statement under the protected defaults, test keys only) and records one simulation outcome, reported or computed by a runner that calls a caller-supplied simulator (no action is executed); no general persistent-object action service | Policy-enforced transactions, validation, idempotency, audit, recovery, human approval, explicit side-effect boundaries |
| Governance and security | Enforced identity, scope and least-privilege access with tamper-evident audit | Project scopes and policy concepts; service-level enforcement remains incomplete | Identity, RBAC+ABAC, tenant isolation, least privilege, revocation, and integrity-tested audit |
| Authoring and usability | Domain experts can inspect, review and change definitions safely | YAML/JSON pack files and documentation | Clear authoring, inspection, lineage, permission review, change review, and action review for domain experts |
| Portability and transparency | Open formats and no hidden identity or provenance semantics | Local-first Python contracts and serializable packs | Open export/import format, no hidden identity/provenance semantics, conformance suite, and clear migration path |
| Reliability and operations | Recoverable, observable, upgradeable operation, including private deployment | Local stores, partial audit and event primitives | Backup/restore, migrations, observability, concurrency, recovery, release compatibility, private/on-prem deployment proof |

## Delivery sequence

### O0 — Reconcile and harden the ontology core

- Refresh the platform roadmap against live main and link this target.
- Compare registry and binding code against existing acceptance criteria.
- Close gaps in uniqueness, referential integrity, cardinality, time semantics, version compatibility, and canonical fingerprints. In particular, reject multiple versions of one type ID inside a pack: current references use IDs without version qualifiers, so allowing concurrent versions in one pack is ambiguous. Preserve old definitions as separate immutable pack snapshots selected by exact version/fingerprint.
- Publish portable domain-pack and binding schemas, examples, and compatibility policy.
  - Structural schemas and conformance vectors: [ONTOLOGY_PORTABLE_SCHEMAS.md](ONTOLOGY_PORTABLE_SCHEMAS.md). Compatibility check: [ONTOLOGY_COMPATIBILITY.md](ONTOLOGY_COMPATIBILITY.md). Examples: `domain_packs/`.
- Exit when civic and commerce packs validate against the same contract and schema/version differences are detected deterministically.

#### O0 audit — 27 November 2026

| Item | Finding |
|---|---|
| Roadmap refresh and link | Done: [PLATFORM_ROADMAP.md](PLATFORM_ROADMAP.md). |
| Binding and registry checked against acceptance criteria | Gaps found and closed: a binding override could lower the classification the policy was asked about; mistyped override keys were ignored; `assigned` object types could be bound by record key; pack nullability and allowed values were not applied to source rows; a repeated binding key was not refused by `materialize_instances`; an object type could repeat a property. Rules: [ONTOLOGY_DATA_BINDING.md](ONTOLOGY_DATA_BINDING.md). |
| Portable schemas, examples, compatibility policy | Published (links above). No third-party use. |
| Cardinality across imports | Found open in this audit; closed afterwards at library level: cardinality now compares object type and record key, and `verify_integrity` reports earlier conflicting links. Link retraction was added later (schema v4). Rules and limits (no cross-dataset entity resolution, no enforcement across pack versions): [ONTOLOGY_OBJECT_STORE_DESIGN.md](ONTOLOGY_OBJECT_STORE_DESIGN.md). |
| Closed later: allowed value types | Pack parsing now refuses an `allowed_values` entry that does not match the property's `data_type`. Rules: [ONTOLOGY_PORTABLE_SCHEMAS.md](ONTOLOGY_PORTABLE_SCHEMAS.md) section 2a. |
| Closed later: pack-declared uniqueness | An object type may declare `unique_keys`, checked within one exact import (not across imports or datasets). Rules: [ONTOLOGY_PORTABLE_SCHEMAS.md](ONTOLOGY_PORTABLE_SCHEMAS.md) section 2b. |
| Not covered | Rung 2 criteria about scenario, agent and run mapping to ontology instances were not audited. |

The exit test is met at library level by the `civic_in` and `retail_in` pack tests and the compatibility tests. The gaps this audit found are closed at library level, within the limits in the rows above. This is not a service or production claim, and the item under "Not covered" is still unaudited.

### O1 — Persistent ontology records and query

- Follow the detailed [Ontology Object Store and Query Design](ONTOLOGY_OBJECT_STORE_DESIGN.md) for the proposed storage boundary, identity, links, query contract, and governance controls.
- The task-by-task implementation sequence is in [the O1 implementation plan](superpowers/plans/2026-11-26-ontology-object-store.md).
- Persist versioned object instances, links, provenance, and validity intervals with stable identity.
- Add scoped queries with explicit versions/snapshots, pagination, filters, and predictable consistency.
- Prove integrity constraints, backup/restore, target-side source-import availability, source snapshot content attestation against a separately retained digest (implemented as a digest comparison, not a signature; separate-storage recovery rehearsal still open), and migration behavior without silently reinterpreting existing graph records.
- Keep writes limited to local ontology storage and approved simulated workflows.

### O2 — Governed action layer

- Implement actions as declared, versioned transactions over ontology objects.
- Enforce policy at the service boundary; bind approval to exact actor, scope, object versions, evidence, and parameters.
- Add idempotency, append-only audit, failure states, retry/reconciliation, and safe cancellation where possible.
- Demonstrate replay, stale-approval, cross-scope, partial-failure, and unauthorized-action behavior.
- Keep external write-back disabled until a separate threat model, owner approval, consent/privacy review, and rollback plan pass.
- First slice: [action proposals](ONTOLOGY_ACTION_PROPOSALS.md) bind exact objects, parameters and cited records to one digest. Second slice: one approval or rejection per digest by a different approver, recorded in the anchored chain, with a stale-checking verification step. Third slice: approvals expire, can be withdrawn, and admit an action for simulation at most once. Fourth slice: the admitter records one reported outcome (succeeded or failed, with a result digest) per admission. Under the protected defaults, admission requires a signed approval statement (test keys only). Fifth slice: a [runner](ONTOLOGY_ACTION_PROPOSALS.md#simulation-runner-o2-fifth-slice) calls a caller-supplied simulator once per admission and computes the recorded result digest. It does not isolate or identify the simulator. No proposal store, statement issuer, built-in simulator or execution yet.

### O3 — Stable application API and SDK

- Expose versioned read APIs and only approved action contracts.
- Generate typed clients from ontology schemas; publish compatibility and deprecation rules.
- Provide local developer tooling and machine-readable API specifications.
- Prove least-privilege access, schema compatibility, and non-leaking errors.

### O4 — Authoring, governance, and operations

- Provide a clear way to inspect and review types, lineage, permissions, changes, and action effects.
- Add ontology change proposals, reviews, activation, deprecation, and migration reports.
- Demonstrate tenant isolation, audit integrity, backup/restore, monitoring, secret handling, and controlled upgrades.
- Add live feeds or hosted deployment only under the separately approved security and cost gates recorded by the owner.

## Non-goals and guardrails

- Do not copy third-party interfaces, branding or terminology.
- Do not claim a capability from a document, class, API stub, or demo.
- Do not add a general action executor before query, identity, authorization, audit, and recovery guarantees exist.
- Do not connect live feeds, real customer systems, payments, messaging, or accounts as part of O0–O3.
- Do not use the 2020 holdout or change prediction status as part of ontology work.
- Do not expand simulation-engine paths without separate explicit approval.

## Success definition

Claim a capability only when implementation evidence, a documented contract, conformance tests, capability-appropriate security/failure evidence, and a verified release exist. Any claim of advantage over an alternative additionally needs a measurable, fair benchmark.
