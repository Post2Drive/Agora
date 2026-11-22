# M2 Synthetic Fixture Selection — Planning Specification

**Status:** Claude's PR #125 proposes one checked-in fixture plus `agora pilot list/start`; it remains open at head `914d570ce62c5d9c1157ec0470d9b948ff17dfc9` and is not on main. Exact-head CI run `44993280261`: two Ubuntu jobs passed, two Windows jobs in progress. Review requires an independently pinned manifest digest, symlink rejection and strict empty-workdir enforcement before acceptance.
**Prerequisite:** M1 was explicitly confirmed by Claude in the 09:05 IST log entry; the owner approved local synthetic M2 after #122 merged. Main is `41137618f04cf44c111acfaff565663b25eb5fe3`; #123's run record is partial. #125 is Claude's claimed fixture/start slice; do not duplicate its implementation.
**Boundary:** Invented, checked-in, deterministic fixtures only.

## 1. Fixture catalogue

Use a versioned, repository-owned catalogue. Each fixture entry should declare:
- Stable fixture ID and human-readable purpose.
- Relative paths for CSV/source, schema and ontology binding.
- SHA-256 for every fixture component and a canonical manifest hash.
- Expected schema version, binding version and allowed measures.
- Explicit label `synthetic_fixture`; no source may be labelled observed.
- Fixture compatibility range and deprecation status.

No personal, customer, health, commercial or externally sourced data is permitted.

## 2. Proposed operator UX

Candidate commands (not implemented):

```bash
agora pilot list
(fixture detail/show is not included in PR #125; keep it a later UX slice)
agora pilot start --fixture <fixture-id> --workdir <new-empty-directory>
```

The list view should show fixture ID, purpose, version, size and integrity state. The detail view should show the manifest hash, schema/binding versions and synthetic label. It must not dump source rows by default.

Selection should be explicit and reproducible. Avoid a moving `latest` alias: a run record must pin the exact fixture ID, version and hashes. Interactive selection may be a thin presentation over the same stable IDs; automation must pass the ID directly.

## 3. Validation and fail-closed rules

- Verify all component hashes before parsing/import.
- Reject missing, extra, path-traversing or symlink-escaping files.
- Reject manifest/schema/binding incompatibility.
- Reject a fixture whose declared source class is not synthetic.
- Refuse changed fixture bytes even if the fixture ID is unchanged; independently pin the manifest digest so changing the manifest and payload together cannot self-authorise new bytes.
- Do not mutate the checked-in fixture during a run; reject symlinked fixture directories, manifest and payload files, then copy/read into an isolated work directory.
- Record exact fixture hashes in `docs/RUN_PROVENANCE_SPEC.md`'s run envelope.

## 4. Acceptance evidence

Tests cover catalogue determinism, stable IDs, unknown IDs, hash mismatch, missing/extra files, path traversal, symlink escape, schema mismatch, immutable source bytes and exact run-record linkage. A clean checkout must list and select a fixture without network access.

## 5. Non-goals

No real data, network download, external identity provider, connector, engine execution, simulation or write-back.
