# Ontology Object Store Implementation Plan

> **For agentic workers:** Implement this plan task by task. Keep the scope on O1 and use the existing ontology design contract.

**Goal:** Persist versioned ontology definitions, source-backed object identities, and typed links, then expose safe scoped object/link queries without copying imported row payloads.

**Architecture:** Add a project-local SQLite sidecar at `data/ontology.sqlite3`. Store immutable pack/binding snapshots, object references, and link records; resolve imported property values through the exact immutable `tabular.sqlite3` import and binding. Keep simulation state and source snapshot payloads outside the ontology database.

**Tech Stack:** Python, SQLite, existing `agora.ontology` registry/binding contracts, existing principal-bound policy enforcement and anchored audit APIs.

**Spec:** `docs/ONTOLOGY_OBJECT_STORE_DESIGN.md`, with invariants from `docs/DOMAIN_ONTOLOGY_MODEL.md` and `docs/ONTOLOGY_DATA_BINDING.md`.

## Global Constraints

- Use the accepted modular-monolith architecture.
- Never use an implicit `latest` pack, binding, or import.
- Do not copy raw imported row payloads into the ontology database.
- Preserve source snapshot immutability and stable record keys.
- Require principal-bound policy and anchored audit for protected reads and writes.
- No external write-back, feed activation, simulation-engine edits, 2020 holdout access, or prediction-flag changes.
- Type definitions and historical object/link versions are append-only and fingerprinted.

## Review Focus

- A caller selects an import or schema different from the stored binding; reject it before snapshot rows are read.
- Two type versions with the same ID appear within a pack; reject before registration.
- Cross-project or wrong-type link endpoints are supplied; reject within the link transaction.
- Concurrent link insertions violate one-to-one/one-to-many cardinality; serialize and reject the losing write.
- A sealed, missing, or unauthorized import is requested; deny before row access and record the denial through the anchored audit path.

---

### Task 1: Durable immutable pack and binding catalog

**Files:**
- Create: `agora/ontology/store.py`
- Modify: `agora/ontology/__init__.py`
- Test: `tests/test_ontology_store.py`

**Interfaces:**
- `OntologyObjectStore(project: str | Path)` opens `project/data/ontology.sqlite3`, enables foreign keys, and applies explicit transactional schema migrations.
- `register_pack(pack: OntologyPack) -> str` stores canonical pack JSON and its fingerprint; repeated identical registration is idempotent; same fingerprint with different content is rejected.
- `register_binding(pack_fingerprint: str, binding: DataBinding) -> str` stores the exact binding snapshot and fingerprint after validating the pack reference.
- `get_pack(pack_fingerprint: str) -> OntologyPack` and `get_binding(binding_fingerprint: str) -> DataBinding` use exact fingerprints only.

- [ ] **Step 1: Add tests** for new database creation, schema version, idempotent registration, same-version content conflict, exact retrieval, and explicit rejection of unknown fingerprints.
- [ ] **Step 2: Implement** the pack/binding catalog tables, append-only triggers, canonical serialization, and transactional registration.
- [ ] **Step 3: Verify** Task 1 with the focused store tests and existing ontology-registry suite.
- [ ] **Step 4: Commit** the catalog slice independently.

### Task 2: Source-backed object identity and retrieval

**Files:**
- Modify: `agora/ontology/store.py`
- Modify: `agora/ontology/binding.py` only if a narrow reusable helper is required
- Test: `tests/test_ontology_store.py`

**Interfaces:**
- `materialize_binding(pack_fingerprint: str, binding_fingerprint: str, import_id: str, *, policy, audit, purpose, retention) -> int` validates the exact stored pack, binding, import manifest, and policy, then records one immutable object reference per row without copying row payload values.
- `get_object(pack_fingerprint: str, type_id: str, type_version: str, record_key: str, import_id: str, *, policy, audit) -> dict` reads the reference, resolves the exact snapshot row via the existing binding contract, and returns typed values plus provenance and sensitivity.

- [ ] **Step 1: Add tests** for stable record identity across two imports, distinct row-version identities, exact import selection, provenance fields, policy denial before snapshot access, sealed holdout denial, and snapshot immutability.
- [ ] **Step 2: Implement** immutable object-reference rows and exact-snapshot materialization by reusing `materialize_instances`.
- [ ] **Step 3: Verify** no row payload is stored in `ontology.sqlite3`; verify focused tests and binding tests.
- [ ] **Step 4: Commit** the object-reference slice independently.

### Task 3: Typed, temporal links

**Files:**
- Modify: `agora/ontology/store.py`
- Test: `tests/test_ontology_store.py`

**Interfaces:**
- `add_link(pack_fingerprint: str, link_type_id: str, link_version: str, source_ref: str, target_ref: str, valid_from: str, valid_to: str | None, *, actor: str, reason: str, provenance: Mapping[str, Any], policy, audit) -> str` validates exact pack/type/endpoints, temporal interval, project scope, cardinality, and policy in one transaction, appending an immutable link and audit event.
- `supersede_link(link_id: str, occurred_at: str, reason: str, *, actor, policy, audit) -> str` appends a successor record; it does not update or delete the original.

- [ ] **Step 1: Add tests** for endpoint type/version checks, temporal bounds, each cardinality, overlapping validity, concurrent insertion, idempotency, policy denial, and append-only supersession.
- [ ] **Step 2: Implement** typed link storage and transaction-scoped cardinality checks.
- [ ] **Step 3: Verify** allowed and denied link writes and audit behavior.
- [ ] **Step 4: Commit** the link slice independently.

### Task 4: Scoped object queries and link traversal

**Files:**
- Modify: `agora/ontology/store.py`
- Test: `tests/test_ontology_store.py`

**Interfaces:**
- `query_objects(pack_fingerprint: str, type_id: str, type_version: str, import_id: str, filters: Mapping[str, Any], page_size: int, cursor: str | None, *, policy, audit) -> QueryPage` accepts only known property IDs and typed operators, enforces a maximum page size, and uses a stable key tie-break.
- `traverse_links(pack_fingerprint: str, link_type_id: str, link_version: str, endpoint_ref: str, import_id: str, page_size: int, cursor: str | None, *, policy, audit) -> QueryPage` returns only exact-version links visible to the caller.

- [ ] **Step 1: Add tests** for filters, stable pagination, unknown property/operator rejection, wrong pack/import rejection, link traversal scope, and policy denial.
- [ ] **Step 2: Implement** parameterized bounded queries and cursor encoding bound to pack/import/type fingerprints.
- [ ] **Step 3: Verify** stable results across repeated queries and that errors do not expose restricted values.
- [ ] **Step 4: Commit** query and traversal.

### Task 5: Migration, recovery, and contract documentation

**Files:**
- Modify: `agora/ontology/store.py`
- Modify: `docs/ONTOLOGY_OBJECT_STORE_DESIGN.md`
- Modify: `docs/ONTOLOGY_DATA_BINDING.md`
- Test: `tests/test_ontology_store.py`

**Interfaces:**
- `backup(path: str | Path) -> Path` creates a consistent project-local ontology-store backup.
- `verify_integrity() -> IntegrityReport` validates foreign keys, pack/binding fingerprints, object source references, link endpoints, and audit references.

- [ ] **Step 1: Add tests** for transactional migration, backup/restore, missing source snapshots, corrupt fingerprints, and read-only behavior after restore.
- [ ] **Step 2: Implement** forward-only versioned migrations and an integrity report; do not migrate existing graph or run databases.
- [ ] **Step 3: Verify** restore and integrity checks against a disposable project fixture.
- [ ] **Step 4: Update** docs with exact implemented capability evidence and known limitations.
- [ ] **Step 5: Commit** migration/recovery work independently.

## Execution notes

Tasks 1–4 are separate reviewable PRs. Task 1 must merge before Task 2; Task 2 before Task 3; Task 3 before Task 4. Task 5 follows after the query contract stabilizes. Each PR stays within `agora/ontology/**`, its focused tests, and the explicitly listed docs. No general REST API, generated SDK, hosted deployment, or external action is part of this plan.
