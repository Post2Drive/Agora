# Rung 1–3 Exit-Test Evidence

**Assessment base:** `main` at `e8380ab2`, after PRs #18, #19, #20, #21, #23, #24, #25, #26, #27, #28, #29, and #30 were merged. Evidence below is limited to tests and checks present on this base.

**Status terms:** `Demonstrated` means the cited test or independent proof passed on merged code. `Partial` means the contract or implementation exists but a required capability is still outstanding.

| Rung | Exit check | Evidence | Status |
|---|---|---|---|
| 1 — Foundation | Clean supported environment, test suite, and OS/Python CI matrix | Main clean-checkout suite: 356 passed. PR #19 workflow `44759452586` and PR #20 workflow `44759343168` passed Ubuntu/Python 3.11, Ubuntu/Python 3.12, Windows/Python 3.11, and Windows/Python 3.12. | Demonstrated |
| 1 — Foundation | Same seed is deterministic; interrupted runs resume safely | `tests/test_engine.py::test_same_seed_same_result`, `test_resume_matches_uninterrupted`, `test_crash_mid_round_leaves_no_trace_and_resumes`, and `test_scenario_change_blocks_resume` passed in the merged baseline suite. | Demonstrated |
| 2 — Ontology | Ontology schema and domain model are documented | `docs/ONTOLOGY_SPEC.md` and `docs/DOMAIN_ONTOLOGY_MODEL.md` define the model and governance contract. | Demonstrated |
| 2 — Ontology | Two domain packs validate against one contract; versions and fingerprints are detectable | Merged PR #21 (`6e2f5c5f8b93e858437cacb6dd9df770ce22a7ac`) includes commerce/civic validation, version-change detection, and same-version definition drift rejection. Its exact-head workflow `44747769879` passed all four jobs. | Demonstrated |
| 2 — Ontology | ActionType fails closed unless all simulation-only guards are exact | PR #21 mutation proof: disabling the guard caused 3 invalid-value cases to fail; restored code passed 5/5. | Demonstrated |
| 2 — Ontology | Unknown keys and missing sensitivity fail closed | PR #21 mutation proofs: bypassing unknown-key rejection caused 5 failures; defaulting sensitivity caused the missing-sensitivity test to fail. Restored tests passed. PR #24 adds explicit binding validation, effective sensitivity, stored `column_types`, and read-only materialization; its three mutation proofs cover sensitivity downgrade, type mismatch, and row-id-derived identity. | Demonstrated |
| 3 — Ingestion | Ingestion contract defines typed rows, identity, provenance, sensitivity, and storage boundaries | Merged PR #18 provides `docs/INGESTION_SPEC.md`; PR #19 implements the contract on main. | Demonstrated |
| 3 — Ingestion | CSV import preserves typed values and provenance, does not truncate 2,001+ rows, and rejects unsafe values without leakage | Merged PR #19 (`3052cbed00ab7161cbeae1dd466312545f27577a`) passed 323 tests in clean checkout and workflow `44759452586`. Tests include typed import, 2,001-row preservation, idempotency, safe diagnostics, schema drift/history, concurrent idempotency, typed bounds, malformed CSV, and shared identity. Mutation proof: deleting the logger definition failed both audit-failure tests. | Demonstrated |
| 3 — Ingestion | Read-only connector enforces allowlists, typed ordering, no partial results, redaction, and stable identity | Merged PR #20 (`62f06af0765ec8c598e45883142aa1800bbeef8b`) passed 325 tests in clean checkout and workflow `44759343168`. Mutation proof: adding `snapshot_id` to the stable key failed 3 tests; restored code passed 33. NUL domain separators are covered. | Demonstrated |
| 3 — Exit | Every derived record traces to a declared ontology property and source snapshot | PR #24 (`cad95450`) provides validated, read-only binding/materialization with stable record keys, effective per-property sensitivity, explicit import IDs, and source/file provenance. PR #30 (`e8380ab2`, workflow `44846848758`, 377 passed) adds the synthetic retail-in end-to-end pack demonstration; its two mutation proofs passed. | Demonstrated |

## Scope and remaining work

- PR #22 is docs-only and records the evidence now on merged main.
- PR #20 SQL guard and allowlist mutation proofs remain part of the merged ingestion evidence: adding `snapshot_id` to stable identity fails the identity tests; removing the SQL/allowlist protections fails the connector safety tests.
- PR #24 introduced additive manifest field `column_types`; snapshots imported before that change fail closed during binding validation because type information is absent.
- Rung 4 remains Partial until scenario-inputs are wired into run records and run-record provenance is persisted (design in merged PR #29; implementation PR #31 is under review).
- Rungs 5 and 6 have merged design records (#26 and #27); no implementation code is claimed.
- No simulation, calibration, backtest, forecast, real driver, credential flow, network connector, external write-back, or study mutation is covered or authorized by this document.
