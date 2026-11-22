# Red-Team Plan — Synthetic Governance Integrity

**Status:** Plan only. No attack has been executed as part of this document. This is the synthetic governance-integrity track; it is separate from predictive validation. M2 remains in progress and M3 is proposal-only.

**Baseline:** main `1719d4c552d22e88109cee7623b3b7146ee5ef39` (22 November 2026). #138 exact source/copy sequence/head comparison and manifest binding are merged (CI `45009045175`, 4/4), but no writer-side lock; manifest re-read gap remains. #139 B13 path normalization is merged (CI `45011493565`, 4/4). RT13 still needs a deterministic concurrent-writer test; full run provenance and clean-install remain open.

## 1. Objective and rules

Attempt to bypass identity, policy, approval, audit, anchor, backup and path protections using synthetic fixtures and isolated temporary directories only. The goal is to demonstrate that attacks are detected, denied before protected reads/writes, and leave no partial or silently rewritten state.

- Use only checked-in synthetic fixtures and disposable temporary copies.
- No real data, personal/customer data, credentials, network, connectors, cloud storage, external write-back or production systems.
- Do not touch NCC, Nutrivance, P2D source data, the seven neutral NCC runs or E0_C0_D0.
- Do not edit `agora/sim/**` for this red-team track.
- Do not repair, re-anchor, reset or delete an attacked source. Preserve evidence and stop.
- Every test records exact repository SHA, test name, attack setup, expected code/status, observed code/status, exit code, before/after hashes and whether any protected read/write occurred.
- A test passes only if expected denial/detection occurs and no prohibited side effect occurs. A traceback, silent success, fallback, partial write or unexpected read is a failure.

## 2. Attack matrix

| ID | Attack | Synthetic attack setup | Expected detection code/status | Required proof / side-effect assertion |
|---|---|---|---|---|
| RT01 | Forge identity | Construct Principal with missing/empty identity fields, invalid role, invalid assurance, expired or malformed claims; attempt to mint/use protected policy through an untrusted route. | `IdentityError` from Principal construction/validation; protected operation denied as `PolicyEnforcementError` if policy check is reached. | No protected source read or decision mutation; denial is anchored-audited where required; no caller-supplied role string is trusted. |
| RT02 | Forge trusted policy capability | Pass raw callable, lambda, duck-typed object or directly constructed/subclassed capability to protected `enforce_policy()`. | `PolicyEnforcementError` with `policy_not_principal_bound` on protected path. | No protected read/write; denial event has stable operation/reason metadata and no raw identity claims. |
| RT03 | Skip approval | Attempt to approve a draft directly, approve a non-proposed decision, reuse stale version/fingerprint, self-approve, use expired review window, or call protected transition without required anchored writer. | `ApprovalTransitionError` for invalid transition/separation/stale state; `AnchorRequiredError` or its protected denial path when writer is absent/not cleanly anchored. | Decision state/version unchanged on pre-transition denial; no approval event; any denial audit event is anchored. |
| RT04 | Post-hoc decision record edit | Alter committed decision payload, version history or fingerprint in a disposable copy; rerun reconciliation. | Reconciliation findings `FINGERPRINT_MISMATCH`, `VERSION_HISTORY_GAP`, `RECORD_PAYLOAD_INVALID` or `TRANSITION_STATUS_MISMATCH`, according to exact mutation. | No repair, rewrite or reclassification as clean; original copy unchanged; report opaque decision ID and finding only. |
| RT05 | Post-hoc run-record edit | Change recorded fixture hash, repository SHA, run status, input reference or provenance field in disposable run copy; run strict loader/verification path. | Strict loader rejection. A single public stable refusal code for every mutation must be pinned by Claude before this row is treated as a code-level pass. | No run resume, report or export; original run-record hash unchanged; no raw payload printed. |
| RT06 | Audit-chain truncation | Remove or truncate a tail event in copied audit database while retaining original anchor. | `ANCHOR_TRUNCATION` from reconciliation, or verifier status `truncation_detected` / CLI `NOT INTACT`. | Protected append and repair remain blocked; no auto-bootstrap; both source files preserved. |
| RT07 | Anchor rollback | Replace anchor with older checkpoint, alter checkpoint hash, break sequence linkage or change chain ID. | `ANCHOR_MISMATCH`, `ANCHOR_TRUNCATION` or `ANCHOR_INVALID` from reconciliation according to verifier result; `NOT INTACT` from audit verify. | No protected append, reset or backward anchor movement; preserve attacked pair. |
| RT08 | Backup file tampering | Change, remove or add a file in disposable backup; alter checksum or manifest membership. | `BACKUP_FILE_MODIFIED`, `BACKUP_FILE_MISSING`, `BACKUP_EXTRA_FILE`, `BACKUP_MANIFEST_INVALID` or `BACKUP_MANIFEST_MISSING`. | Verification/restore blocks; no target published; original backup hash unchanged. |
| RT09 | Backup audit-pair tampering | Change audit database or anchor in a backup while keeping manifest, or mismatch the pair. | `BACKUP_NOT_INTACT` or `BACKUP_FILE_MODIFIED`; manifest/schema faults return `BACKUP_MANIFEST_INVALID`. | Restore blocked; no auto-repair/re-anchor; no partial target. |
| RT10 | Restore copy tampering | Change a staged non-audit file during restore or mutate staged audit/anchor pair after pre-verification. | `RESTORED_NOT_INTACT` on restored-file or chain/anchor verification failure. | Staged target removed; original backup unchanged; no partially restored project reported successful. |
| RT11 | Symlink inside project/backup | Place symlink in a synthetic project tree or backup tree pointing outside temporary root. | `UNSAFE_PATH`. | Outside sentinel is neither read nor copied; no backup/restore target created. |
| RT12 | Symlink root and parent-path tricks | Make project root, backup root, restore target or any ancestor a symlink; use `..`, absolute paths, repeated separators or path replacement between validation and use. | Direct root symlink/reparse-point paths return `UNSAFE_PATH` under #134; #135 closes ordinary workdir-ancestor coverage and #136 adds backup parent/pre-read/lstat-error guards. #139 closes lexical `..` refusal in both backup and pilot walkers (CI `45011493565`, 4/4). Remaining coverage: pilot workdir intermediate-ancestor lstat failure and plain-`..` pilot case. | Outside sentinel bytes/timestamps unchanged; no file created outside disposable root; no partial destination. |
| RT13 | Source snapshot race | Interleave a legitimate synthetic anchored append between source verification and database/anchor pair capture. | #138 compares copied-chain sequence/head with the source verdict and records/verifies manifest head; mismatch returns `SNAPSHOT_CHANGED`. It does not hold a writer-side lock, and verify/restore re-read the manifest after validation. The current test mocks verifier output; require a barrier-controlled real writer and one immutable validated manifest snapshot. | Captured chain ID, sequence and head hash must match source verdict exactly; no success with a mixed pair or a manifest replaced between validation and use. |
| RT14 | Reconciliation anchor bypass | Corrupt or remove sidecar anchor, then call reconciliation. | `ANCHOR_INVALID`, `ANCHOR_TRUNCATION`, `ANCHOR_MISMATCH` or `ANCHOR_UNANCHORED_TAIL` as mapped by verifier; no findings classified when verification is blocked. | No repair, queue or source mutation; preserve stores. |
| RT15 | Held-outcome store failure | Supply missing, unreadable or malformed held-outcome store. | `STORE_NOT_FOUND` or `STORE_UNREADABLE`. | No held item silently treated as clear; no store creation or mutation. |

## 3. Current-code caveats to retain as open findings

These are not attack results; they are review targets to be tested by Claude against the exact code head:

- #127 defines stable backup codes including `SOURCE_NOT_SYNTHETIC`, `UNSAFE_PATH`, `SNAPSHOT_CHANGED`, `BACKUP_MANIFEST_INVALID`, `BACKUP_FILE_MODIFIED`, `BACKUP_EXTRA_FILE`, `BACKUP_NOT_INTACT` and `RESTORED_NOT_INTACT`. #135 implements workdir-ancestor refusal; #136 adds backup ancestor/pre-read/fail-closed lstat checks; #138 adds copied-chain sequence/head and manifest-head detection; #139 closes B13 lexical `..` refusal. Remaining gaps: manifest read-once validation, deterministic real-writer proof and pilot intermediate-ancestor lstat-failure coverage.
- #127/#134 post-copy backup verification still compares anchored-verifier validity/status only; it does not hold one anchor lock across source verification and pair copy or require exact chain ID, sequence and head equality.
- #130 validates required run-record fields and non-empty workdirs; #132 adds fixture manifest pinning and direct fixture/workdir-root symlink refusal; #135 adds workdir-ancestor refusal and linked-fixture catalogue filtering. Remaining strictness questions include empty/unknown run-record identifiers, nested fixture hash shape, manifest cross-checks, complete input provenance and failure-atomic publication. Clean-install proof remains open.
- The marker/audit cross-store commit-failure case remains a separate implementation concern. This plan does not assume it has been fixed.
- A local sidecar anchor cannot detect coordinated rollback of both audit database and anchor by an actor able to rewrite both. Record this as a trust limitation; do not label coordinated rollback as detected unless an independent checkpoint is actually used.

## 4. Evidence record template

| Field | Value |
|---|---|
| Attack ID / title | TBD |
| Exact main/PR head SHA | TBD |
| Test name and command | TBD |
| Synthetic fixture / disposable path | TBD |
| Attack setup and mutation description | TBD |
| Expected status/code | TBD |
| Observed status/code and exit code | TBD |
| Before/after source hashes | TBD |
| Outside-root sentinel before/after | TBD |
| Protected source read occurred? | Must be no where denial is pre-read |
| Protected write or partial destination occurred? | Must be no |
| Audit event reference / chain verification | TBD |
| CI workflow and exact-head run ID | TBD |
| Result | Not run |
| Reviewer / date | TBD |
| Residual limitation / issue link | TBD |

## 5. Pass criteria and stop rules

A red-team case passes only when expected typed failure or stable code occurs, the action is denied at the intended boundary, all protected source/store hashes remain unchanged where required, and no outside-root sentinel or secret is accessed.

A case fails if it silently succeeds, uses fallback, returns traceback instead of safe failure, reads protected data before denial, writes partial state, advances/rewrites an anchor, resumes a tampered run, or reports a held outcome as clear.

Do not retry by cleaning the source. Preserve the disposable copy and evidence. Any attack that unexpectedly touches a real file, network, credential, connector, P2D source or protected study is an immediate stop and escalation.

**No red-team attack has been executed and no security result is claimed by this plan.**
