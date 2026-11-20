# Ontology Specification — Rung 2

**Status:** design specification only. This document does not implement a new ontology, migrate data, or change the existing graph database.

## 1. Purpose and boundaries

Define a stable, versionable meaning for the information already represented by Agora's document graph, and a path for connecting that graph to scenarios and simulation evidence.

The specification distinguishes:
- **Current implementation:** the SQLite graph in `graph.db`, with documents, chunks, nodes, edges, node-to-chunk links and metadata.
- **Proposed logical model:** the object and relationship vocabulary below. It is a target contract, not a claim that all fields or controls exist today.

The existing graph remains usable. No graph rewrite or migration is implied by this specification.

## 2. Core objects

| Object | Meaning | Core properties |
|---|---|---|
| SourceDocument | One ingested source file | stable source ID, original name, content hash, media type, byte size, ingestion time, source URI or provenance note |
| DocumentChunk | A bounded text passage derived from a source | stable chunk ID, source ID, ordinal, text, character range when available, extraction status |
| Entity | A named real-world or conceptual item extracted from source material | stable entity ID, canonical name, entity type, description, aliases |
| Relation | A typed assertion connecting two entities | stable relation ID, subject ID, predicate, object ID, optional fact text, source evidence |
| Scenario | A versioned description of the simulated world and interventions | scenario ID, version, content hash, configuration, created time |
| SimulationRun | One execution of a scenario | run ID, scenario version/hash, seed, engine version, model/backend metadata, start/end times, completion state |
| Agent | A simulated participant or account in a run | agent ID scoped to run, handle, kind, segment, initial stance and other scenario-derived attributes |
| EvidenceRecord | A source-backed or run-produced observation | evidence ID, evidence type, source/run reference, locator, content hash, recorded time |

IDs must be stable within their declared scope. A display name is not an identifier.

## 3. Relationships and cardinality

- SourceDocument **has many** DocumentChunks; each chunk belongs to one source document.
- DocumentChunk **mentions** zero or more Entities; an entity may be mentioned by many chunks.
- Relation **connects** one subject Entity to one object Entity and may be supported by one or more chunks.
- Scenario **uses** zero or more SourceDocuments as context, calibration input or other explicitly labelled data roles.
- SimulationRun **executes** exactly one immutable Scenario version.
- SimulationRun **contains** many Agents and produces many EvidenceRecords.
- EvidenceRecord **is derived from** a source document, document chunk, simulation run, or another explicitly identified evidence record.
- Entity and Relation records may be reused across scenario versions only when their identity and provenance remain valid; otherwise create a new version or a distinct entity.

Relationships must not silently imply causation. A relation predicate describes the assertion; causal interpretation requires separately documented evidence and method.

## 4. Properties and data conventions

1. Store canonical IDs separately from names, aliases and display labels.
2. Use explicit types for entity and relation categories; preserve the original extracted label as provenance when normalising it.
3. Represent dates and timestamps in UTC using ISO 8601.
4. Store hashes as lowercase hexadecimal SHA-256 values where content integrity is required.
5. Preserve source locators (file name, page, chunk ordinal, row or other available location) so a claim can be traced to its evidence.
6. Keep unknown values absent or null; do not substitute inferred values without recording the inference and method.
7. Keep simulation outputs distinct from observed real-world outcomes. A simulated conversion is not a real sale.

## 5. Versioning and identity

- Version the ontology schema independently from the application release and database schema.
- Each schema version must define object types, property names and types, relationship predicates, required/optional status, and migration compatibility.
- Scenario versions are immutable once a SimulationRun references them. A changed scenario creates a new version and content hash.
- Entity merges, splits and canonical-name changes must retain an alias or supersession record; do not reuse a retired ID for a different real-world object.
- A migration must be explicit, repeatable, backed up, and accompanied by validation of record counts and referential integrity.
- Existing `graph.db` files are not automatically migrated by this document.

## 6. Provenance and lineage

Every extracted Entity and Relation should be traceable to one or more DocumentChunks and therefore to a SourceDocument. Preserve:
- source content hash and ingestion metadata;
- chunk identifier and source locator;
- extraction/parser/model version where available;
- review or correction status where available;
- transformation or normalisation steps;
- links from scenario inputs to their source records;
- links from run outputs to the exact scenario version, seed and engine/model metadata.

Derived summaries must retain links to their supporting evidence. If evidence is removed or replaced, downstream records should be marked as needing review rather than silently treated as current.

## 7. Permissions and governance hooks

The logical model reserves hooks for:
- owner/tenant and project scope;
- source access classification and permitted data role;
- read, write, review, approve and export permissions;
- consent, retention and deletion policy metadata;
- audit events for ingestion, extraction, correction, approval, export and deletion.

These are design hooks only. This specification does not claim that the current graph database enforces user-level permissions, consent, retention or approval workflows. Enforcement must be implemented at the application/service boundary and tested before any protected-data use.

## 8. Mapping from the current `agora/graph/` implementation

Current SQLite tables in `agora/graph/store.py`:

| Current table | Current role | Logical mapping |
|---|---|---|
| `documents` | document ID, name, character count, chunk count | SourceDocument (partial) |
| `chunks` | auto-increment ID, document ID, ordinal, text, status, raw payload | DocumentChunk (partial) |
| `nodes` | key, name, type, description, aliases, mentions | Entity (partial) |
| `edges` | source node, destination node, type, fact, chunk | Relation (partial) |
| `node_chunks` | node-to-chunk association | Entity–DocumentChunk mention link |
| `meta` | key/value metadata | graph-level metadata and future schema-version marker |

Current implementation notes:
- `GraphStore` creates the tables above and exposes basic metadata and row access.
- `agora/graph/ingest.py` copies supported source files into the project, derives a file ID from a SHA-256 digest (currently truncated to 16 hexadecimal characters), extracts text and stores chunks.
- `agora/graph/retrieve.py` builds a fact index from edge facts and node descriptions.
- The current tables do not yet provide the complete logical IDs, full hashes, temporal versions, explicit scenario/run links, evidence records or permission enforcement described above.
- The current schema uses integer row IDs for nodes, edges and chunks in places; a future migration must preserve stable cross-reference mapping.

## 9. Phased adoption proposal

1. **Inventory:** document actual table constraints, writers/readers and existing database variants.
2. **Compatibility layer:** define typed application objects and explicit mapping to the current tables without changing persisted data.
3. **Provenance completion:** retain full source hashes, extraction metadata and stable chunk locators.
4. **Scenario/run lineage:** link scenario versions and SimulationRuns to source evidence and outputs.
5. **Governance enforcement:** implement and test project-scoped permissions, approval and audit hooks.
6. **Migration:** only after compatibility tests, backup/restore tests and a reviewed migration plan.

Each phase requires a separate implementation proposal and owner approval. No code, database migration, or simulation is authorised by this document.

## 10. Acceptance questions for review

- Are the object boundaries and relationship cardinalities sufficient for the current graph and planned scenario/run lineage?
- Which IDs must remain stable across project copies and database migrations?
- Which provenance fields are mandatory at ingestion versus extraction?
- What permission model is required before multi-user or sensitive-source workflows?
- What backward-compatibility guarantees are required for existing `graph.db` files?
