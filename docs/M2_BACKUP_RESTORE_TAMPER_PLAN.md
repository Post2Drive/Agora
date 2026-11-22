# M2 Backup, Restore and Tamper Drills — Planning Specification

**Status:** #120 backup/verify/restore CLI and #127/#134/#135/#136/#138/#139 path/synthetic/manifest hardening are merged. #138 exact source/copy sequence/head comparison and manifest binding passed exact-head CI `45009045175` (4/4); no writer-side lock was added. #139 closes B13 on backup and pilot path walkers (head `2d3a0e7f`, CI `45011493565`, 4/4). Remaining: `verify_backup()` reads the manifest through `_read_manifest()` then reads it again for head fields; `restore()` verifies and then reads the manifest again for hashes. Reuse one validated immutable manifest snapshot, validate exact sequence type (`type(value) is int`, not bool) and 64-lowercase-hex head, and add manifest-replacement plus barrier-controlled concurrent-writer proofs. Operator command test and separately approved tamper rehearsal remain open.
**Boundary:** M1 was confirmed by Claude's 09:05 IST log entry. Local synthetic M2 implementation is owner-approved. Temporary local synthetic stores only; no simulation, real data, credentials, connectors, write-back or protected study mutation.

## 1. Backup consistency contract

The audit SQLite database and its JSONL anchor are one logical integrity pair. A backup must capture a mutually consistent snapshot of both while writers are quiesced or under a reviewed snapshot/locking mechanism. Copying them at unrelated times is not an acceptable backup.

A backup manifest should record:
- Backup ID and UTC timestamp.
- Chain ID and exact paths/relative names.
- SQLite integrity-check result.
- Anchor verification status, sequence and head hash.
- SHA-256 of the backup database and anchor bytes.
- Tool/runtime version and synthetic fixture/run ID.
- Whether writers were quiesced and how the snapshot was obtained.

Never include event payload values, personal data, credentials or secrets in the manifest.

## 2. Restore procedure — CLI and hardening merged; operator validation pending

Merged command surface (#120; exact-head Actions run `44986367729` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs):

```bash
agora backup --project <project-dir> --dest <new-empty-backup-dir>
agora backup verify --backup <backup-dir>
agora restore --backup <backup-dir> --target <new-empty-target-dir>
```

The merged #127/#134 patches change the prior #120 behavior as follows:
- Backup requires `run_record.json` with `data_class == "synthetic"`; otherwise it blocks with `SOURCE_NOT_SYNTHETIC`.
- Symlinks in the source/backup tree and unsafe manifest-relative paths are refused with `UNSAFE_PATH`.
- The manifest validator requires version 1, `synthetic_only is True`, a nonblank chain ID and a safe relative-path-to-lowercase-SHA256 mapping; malformed manifests block with `BACKUP_MANIFEST_INVALID`.
- After copying the source files, backup re-verifies the copied chain/anchor; a changed or invalid pair blocks with `SNAPSHOT_CHANGED` and removes the incomplete destination.
- #134 checks direct project/destination/backup-root/data/manifest/restore-target components for symlink or Windows reparse-point paths. Merged PR #136 adds ancestor walking, nested pre-read refusal and fail-closed lstat handling (exact-head CI `45006493190`, 4/4 passed). Its `_is_link()` first calls `os.path.abspath()`, which can normalize away a symlink component before a following `..`; reject `..` or inspect the original path components and add a no-outside-read/write regression.
- #138 compares exact source/copy chain sequence/head and stores both in the manifest; it is detection-only, with no writer-side `AnchorStore.lock()`. Its test monkeypatches verifier output, not a real concurrent append. `verify_backup()` reads the manifest twice; `restore()` calls verify then re-reads it for hashes. Reuse one validated immutable manifest snapshot through verify/restore; validate `chain_sequence` with `type(value) is int` (not bool) and `chain_head_hash` as 64 lowercase hex; add manifest-replacement-between-phases and barrier-controlled concurrent-writer mutation tests.
- Restore re-hashes every copied file against the manifest before success; a mismatch blocks with `RESTORED_NOT_INTACT`.

#127 adds tests and mutation proofs for the synthetic gate, in-tree symlink refusal, manifest validation, snapshot re-verification and restore re-hashing. #134 adds four direct-root symlink/reparse-point tests; exact-head CI run `44999538699` passed 4/4. #135 adds workdir-ancestor and fixture-catalogue protections; exact-head CI `45001811790` passed 4/4. PR #136's backup ancestor/pre-read/lstat-error cases are merged; exact-head CI `45006493190` passed 4/4. Review gaps: the lstat-error test injects failure only at the project root, not an intermediate ancestor; the pre-read mutation test covers `run_record.json` but not chain/anchor paths. Add ancestor-specific lstat and parameterized run_record/chain/anchor no-read proofs, plus the `..`-through-symlink regression. Source-pair snapshot-lock/head-equality proof remains outstanding. The operator command test and tamper rehearsal are still outstanding; no operator rehearsal is claimed.

1. Stop all writers and preserve the current pair unchanged.
2. Verify the backup manifest and both component hashes.
3. Restore both files to a new isolated directory; never overwrite the source pair in place.
4. Run SQLite integrity checks and the read-only chain/anchor verifier.
5. Require the expected chain ID, sequence and head hash.
6. Compare the restored pair to the backup manifest.
7. Record the restore result and operator identity in a separate protected record.
8. Resume writes only after a clean verification and explicit approval.

A missing or invalid anchor is an incident, not permission to bootstrap a replacement. Never move an anchor backwards to make a restored chain appear valid.

## 3. Tamper drill matrix

Planned synthetic-only cases:
- Modify an audit event byte/field: chain verification must fail.
- Delete or reorder an audit row: chain verification must fail.
- Truncate the chain below the anchor: verification must fail.
- Remove, corrupt or alter the anchor: anchor verification must fail.
- Supply the wrong chain ID: verification must fail.
- Restore a chain from backup with a different anchor: mismatch must be detected.
- Restore a mutually consistent older chain+anchor pair: document that a local sidecar cannot detect coordinated rollback by an actor able to rewrite both files. This is a known trust limitation, not a passing security control.
- Simulate an unanchored tail: protected appends and repair must stop; preserve both stores.
- Interleave a legitimate synthetic anchored append between source verification and pair copy: expect `SNAPSHOT_CHANGED` with no retained destination. #138 detects a changed copied head but has no writer-side lock; its test mocks verifier output. Add a barrier-controlled real writer interleaving (no timing sleep) and prove no mixed pair can be accepted.
- Mutate a non-audit backup file after pre-verification but before/during restore copy: restore must fail, remove its staged target, and preserve the original backup.
- Point backup at an unmarked/non-synthetic project: expect `SOURCE_NOT_SYNTHETIC` and no destination.
- Place a symlink inside the source or backup tree, or use an unsafe relative manifest path: expect `UNSAFE_PATH` and no outside-target read/copy.
- Direct symlink/reparse-point project, backup, data/manifest or restore-target roots block with `UNSAFE_PATH` under #134. #136 adds parent-component and nested `run_record.json`/chain/anchor pre-read checks plus fail-closed lstat handling. Add a `..`-through-symlink regression to ensure `os.path.abspath()` cannot normalize away the linked component; prove no outside sentinel read/write and no partial destination.
- Tamper `manifest_version`, set `synthetic_only` false, replace `files` with a list, or corrupt `chain_id`/digest values: expect `BACKUP_MANIFEST_INVALID`, never an uncaught exception.
- Change the copied chain/anchor during backup: expect `SNAPSHOT_CHANGED` and no retained partial backup.
- Mutate a non-audit file after backup verification but before/during restore copy: expect `RESTORED_NOT_INTACT` and no published target.

## 4. Acceptance evidence

- Automated tests operate only on temporary local files and synthetic fixtures.
- Each tamper case asserts a stable blocked/error status and no silent repair.
- Restore tests verify exact hashes, chain ID, sequence and head.
- Failure tests prove original stores and backup bytes remain unchanged.
- #127 CI/mutation evidence covers the synthetic gate, in-tree path refusal, manifest schema, copied chain/anchor re-verification and restored-file re-hashing; #134's exact-head CI `44999538699` and #135's `45001811790` passed 4/4. PR #136 is merged with exact-head CI `45006493190` passed 4/4; its `..` path-normalization regression and source-pair lock/head-equality proofs remain required.
- The current synthetic gate is the `run_record.json` `data_class=synthetic` check; this is not equivalent to a separately pinned fixture-hash allowlist for every file in a project. Keep the scope distinction explicit.
- The automated runbook command test must exercise backup/verify/restore and each stable refusal code in temporary synthetic directories.
- A separately approved rehearsal log records command, SHA, fixture hashes, results and operator sign-off.

## 5. Explicit non-goals

No production backup target, cloud storage, network connector, external write-back, real data, credentials, simulation or mutation of existing studies.
