# Domain Ontology Model — Rung 2 Design

**Status:** target logical model and acceptance contract. Main now includes a partial implementation of versioned domain-pack parsing, an in-memory type registry, and read-only snapshot bindings. This document remains the target contract; it does not imply that persistent ontology storage, graph queries, general action execution, user-level authorization, data migration, general connectors, or external write-back are complete.

**Relationship to the existing specification:** this document extends the Agora artefact ontology in [ONTOLOGY_SPEC.md](ONTOLOGY_SPEC.md). The existing SourceDocument, DocumentChunk, Entity, Relation, Scenario, SimulationRun, Agent and EvidenceRecord concepts remain valid. This proposal adds a user-defined domain ontology that scenarios and runs can instantiate.

## Current implementation status — 26 November 2026

The registry, loader, binding module, domain packs, and their tests are present in main. The registry is in-memory and materialized bound instances are read-only/in-memory. See [ONTOLOGY_CAPABILITY_TARGET.md](ONTOLOGY_CAPABILITY_TARGET.md) for the current capability scorecard and remaining staged work.

## 1. Goals and non-goals

The domain ontology gives a project a versioned vocabulary for:

- object types and their properties;
- typed links between object instances;
- action types, inputs, preconditions, effects and permissions;
- backing data sources and provenance;
- mappings from Agora scenarios, segments, accounts, agents and simulated events into ontology instances.

It must keep four categories distinct:

1. **Source facts:** content imported from an external source and linked to provenance.
2. **Domain objects:** typed records describing the project domain.
3. **Simulation state:** synthetic agents, scenario conditions and simulated events.
4. **Observed outcomes:** real-world measurements and events, with their own source provenance and validation status.

A simulation output is never a real-world fact merely because it is stored in the same project.

Non-goals for rungs 2–4:

- no writes, updates, registrations, purchases, votes, messages, bookings or other side effects against real external systems;
- no live CRM, payment, commerce, social-media, messaging or customer-account mutation;
- no automatic promotion of simulated actions into real operational actions;
- no claim that a design-only permission field is an enforced security boundary.

## 2. Versioned type registry

Each project has a logical ontology registry with an explicit schema version. The registry contains four versioned definitions:

| Registry | Purpose | Required identity |
|---|---|---|
| ObjectType | Defines a class of domain object | type_id + version |
| PropertyType | Defines a typed attribute | property_id + version |
| LinkType | Defines a directed relationship and cardinality | link_type_id + version |
| ActionType | Defines an allowed action contract | action_type_id + version |

Every type definition should include:

- stable, namespaced ID (not a display name);
- semantic version and lifecycle status (draft, active, deprecated);
- human-readable name and description;
- owning project / tenant scope;
- schema version and compatibility policy;
- created/updated metadata and reviewer where applicable;
- references to the source registry records that justify the definition, where relevant.

Type IDs are never reused for a different meaning. A breaking change creates a new major version or a new type ID. Deprecated versions remain readable for historical runs.\n\n**Pack reference rule:** each domain-pack snapshot contains at most one definition version for each ObjectType, PropertyType, LinkType, or ActionType ID. References within that pack use the stable ID and resolve only to that sole definition; the pack schema version and fingerprint pin the complete definition set. Historical versions are retained by registering later pack snapshots, not by mixing multiple versions of one ID into a single pack. A consumer must select an explicit pack version/fingerprint and must never resolve an unqualified reference to an implicit latest version. Reject a pack that contains multiple versions of the same ID.

### 2.1 ObjectType

An ObjectType definition declares:

- required and optional PropertyTypes;
- uniqueness rules and identity strategy;
- allowed LinkTypes as source and target;
- backing data source references;
- sensitivity / classification;
- retention and deletion policy references;
- project and tenant scope;
- whether instances are source-backed, user-authored, scenario-derived or simulation-generated.

Illustrative domain-neutral example pack:

- Customer
- Site
- Product
- Campaign
- Order
- Observation

These are examples, not a claim that they exist in the current codebase. Projects may define different packs without changing Agora's core ontology contract.

### 2.2 PropertyType

Each PropertyType declares:

- primitive or structured data type (string, integer, decimal, boolean, date, timestamp, enum, identifier, structured object);
- required / nullable status;
- validation rules and allowed values;
- units, precision and timezone where relevant;
- sensitivity classification;
- whether the value is observed, imported, user-entered, derived or simulated;
- source locator and transformation metadata where applicable.

Unknown values remain unknown. The model must not silently infer a missing value and store it as observed truth.

### 2.3 LinkType

Each LinkType declares:

- source ObjectType and target ObjectType;
- predicate / relationship meaning;
- direction and cardinality (one-to-one, one-to-many, many-to-many);
- temporal validity where applicable;
- provenance requirements;
- permission scope for creating, reading and retiring the link;
- whether the link is observed, imported, manually asserted or simulation-generated.

Examples: Customer located_at Site; Campaign promotes Product; Order contains Product; Observation records an outcome for a Campaign. These examples illustrate relationship semantics only; they do not imply a particular business vertical.

A relationship does not by itself establish causation.

### 2.4 ActionType

Each ActionType defines an action contract:

- action_type_id and version;
- actor ObjectType and target ObjectType;
- required inputs and typed parameters;
- preconditions and validation rules;
- declared state transition / effects;
- required permission scope;
- audit fields and idempotency key;
- execution mode;
- explicit simulated-only flag;
- external write-back policy.

For every ActionType in rungs 2–4, the required values are:

- simulated_only: true
- execution_mode: simulation_only
- external_writeback: prohibited

The simulated-only status must be explicit in the registry and in every generated action record. It must not be inferred from the action name or calling code.

Illustrative ActionTypes:

| ActionType | Meaning inside Agora | Simulated-only? | External write-back |
|---|---|---:|---|
| RegisterInterest | A synthetic agent records interest in a simulated object or offer | Yes | Prohibited |
| PlaceOrder | A synthetic agent records a simulated order event | Yes | Prohibited |
| CastVote | A synthetic agent records a simulated poll / choice response | Yes | Prohibited |
| RequestService | A synthetic agent records a simulated service request | Yes | Prohibited |

These examples represent simulation events only. They do not register a real person, create a real order, charge a payment method, send a message, book a service or reserve inventory.

## 3. Backing data sources and provenance

Each ObjectType must declare one or more backing source references where data is imported or derived. A source reference points to a source registry ID, not merely a filename or a human-readable URL.

Minimum source binding:

- source_registry_id;
- source content SHA-256;
- data role (context, scenario_input, calibration, validation or sealed_holdout);
- source locator (file, table, sheet, row, page, chunk or record key);
- acquisition timestamp and publication timestamp where known;
- publisher / author and licence where known;
- parser / connector version;
- extraction status and quality flags;
- transformation or normalisation version;
- reviewer / approval reference when required.

A source registry record describes provenance; it does not itself grant permission to use the data for every purpose. Data role and approval checks remain purpose-specific.

For multiple sources, retain all contributing source IDs and the transformation lineage. A derived value must be labelled as derived and must retain its source references and method.

## 4. Mapping Agora artefacts into domain ontology instances

The following mapping is proposed for rung 2. It is a logical mapping contract, not a current database migration.

| Agora concept | Ontology mapping | Identity scope | Important constraints |
|---|---|---|---|
| Scenario segment | Segment ObjectType instance | scenario_id + segment_id | Preserve configured segment name, share and declared attributes |
| Account | Account ObjectType instance | scenario_id + account_id | Keep account separate from a human resident unless explicitly modelled |
| Agent | Agent ObjectType instance | run_id + agent_id | Synthetic participant; preserve kind, segment, initial state and run reference |
| Scenario | Scenario ObjectType instance | scenario_id + version | Immutable once referenced by a run |
| Simulation run | SimulationRun ObjectType instance | run_id | Links exact scenario hash, seed, engine/model version and runtime metadata |
| Simulated event | ActionRecord / EvidenceRecord | run_id + event_id | Must carry ActionType ID and simulated_only=true |
| Imported source file | SourceDocument ObjectType instance | source_registry_id | Must link full source hash and source locator |
| Extracted graph entity | Entity ObjectType instance | project_id + entity_id | Must retain source chunk / evidence links |

Account and Agent are distinct concepts: an account is a configured actor identity in a scenario; an Agent is an instantiated participant in a particular run. If an account is instantiated as an agent, the mapping must preserve both identities and the link between them.

A segment is a scenario-defined population category. An agent's segment assignment is a run-scoped link, not a claim that a real person belongs to that segment.

## 5. Permission scope per type

Permissions are declared at project, type and instance scope. The logical permission vocabulary is:

- read;
- create;
- update;
- retire;
- review;
- approve;
- export;
- execute_simulation.

The design must distinguish read permissions for source data from permission to use that source for calibration, validation, export or simulation context.

Proposed minimum policy:

| Type / record | Default allowed scope | Restricted operation |
|---|---|---|
| SourceDocument / SourceRecord | Project-scoped read, subject to source classification | Export or reuse for calibration/validation requires role and approval checks |
| ObjectType / PropertyType / LinkType | Project ontology maintainers may draft and review | Activate or deprecate requires review and audit |
| Scenario / Segment / Account | Project-scoped read; scenario editor may create versions | Published scenario versions are immutable |
| Agent / simulated event | Read within its run | No mutation of historical run evidence |
| ActionType | Project ontology maintainers may draft; simulation runtime may invoke active simulated types | No external write-back or real-system execution |
| EvidenceRecord / PurchaseObservation | Read subject to data role and classification | Validation / approval / export requires explicit scope and provenance |

This table is a target policy only. The current specification does not establish that user-level access control is implemented. Enforcement must be added at the application/service boundary and tested before multi-user or sensitive-source use.

## 6. Action execution boundary and write-back prohibition

For rungs 2, 3 and 4:

1. ActionTypes describe modelled state transitions and simulated events only.
2. The execution engine may append a simulated event to the run's own event store.
3. The event must include run_id, agent_id, action_type_id, action_type_version, timestamp / round, input payload, resulting simulated state reference, provenance and simulated_only=true.
4. No action may call an external business API, write to a customer database, create an order, initiate payment, send a message, alter a real account or reserve real stock.
5. An attempt to request external write-back must fail closed and produce an audit record.
6. Any future real-world integration requires a separate design, threat model, permission model, consent review, owner approval and implementation rung. It is not implied by this ontology document.

## 7. Versioning, identity and lineage

- Ontology schema versions are independent of application releases and graph database schema versions.
- Each run stores the ontology schema version and content fingerprint used at run creation.
- Scenario versions are immutable once referenced by a run.
- Object identity must be stable within its declared project / scenario / run scope.
- Entity merges, splits and canonical-name changes retain alias or supersession history.
- Link changes must preserve prior validity intervals or an explicit supersession record.
- ActionType contract changes are versioned; old run events retain the exact ActionType version used.
- Migrations are explicit, repeatable, backed up and validated for counts, IDs, referential integrity and provenance.
- No existing graph.db is migrated by this specification.

## 8. Rung 2 acceptance criteria

Rung 2 is accepted only when the design and a future implementation can demonstrate:

1. The four registries (ObjectType, PropertyType, LinkType, ActionType) have stable IDs and versioned definitions.
2. ObjectType definitions validate required properties, types, nullability and uniqueness rules.
3. LinkType definitions validate source/target types and cardinality.
4. Every source-backed ObjectType can resolve its backing source_registry_id and source locator.
5. Scenario segments, accounts and run-scoped agents map to distinct, stable ontology instances with explicit links.
6. SimulationRun references an immutable scenario version, ontology version, seed and model/engine metadata.
7. Every simulated action resolves to a registered ActionType version and has simulated_only=true.
8. Every registered ActionType in rungs 2–4 has simulated_only: true, execution_mode: simulation_only and external_writeback: prohibited. Tests demonstrate these invariants against at least two example packs from different domains (for example, a commerce pack using Customer, Product and Order, and a civic-feedback pack using Participant, Proposal and Ballot). No example ActionType can write to an external system.
9. Permission checks distinguish read, review, approve, export and execute_simulation scopes.
10. Provenance links can be followed from an ontology instance to its source record, hash and locator, or to the run/event that generated it.
11. A schema version change is detectable and does not silently reinterpret historical run data.
12. The documentation and tests explicitly demonstrate that rungs 2–4 have no real-system write-back.

## 9. Relationship to later rungs

- **Rung 2 — Domain ontology:** type registry, typed instances and links, source bindings, action contracts and permission design.
- **Rung 3 — Ingestion with provenance:** implement source adapters and typed ingestion while preserving source IDs, hashes, locators, connector/parser versions and audit history.
- **Rung 4 — Governed simulation actions:** enforce simulated ActionType contracts, scoped permissions, audit and fail-closed behavior inside Agora.
- **Rung 5 — Approved decisions and actions:** a future capability may introduce carefully bounded real-world write-back only through a separate design, explicit owner approval, user/subject consent where applicable, human approval gates, and a dedicated threat model. This document does not specify or authorise that capability.

Rungs 2–4 do not include write-back to real systems. The ontology must not be interpreted as permission to operate external systems.

## 10. Open design questions for review

- Which ObjectTypes should be part of the first domain pack versus project-defined extensions?
- Should ontology definitions be stored as versioned YAML/JSON files, database rows, or both?
- Which source fields are mandatory at ingestion versus extraction?
- What identity strategy is required for records with no stable external key?
- What is the minimum permission model for single-user local projects versus future multi-user workspaces?
- Which event schema fields are mandatory for every simulated ActionType?
- How should ontology version fingerprints be embedded in run metadata and reports?
- What separate threat model, approval workflow, consent controls, audit guarantees and rollback strategy would be required before rung 5 could introduce any real-system write-back?
