# Deployment Hardening Specification

**Status:** Proposed operational controls; design only, not an implementation or security certification  
**Scope:** Single-host and single-VM deployments of Agora. No production deployment is approved by this document.

## 1. Objectives and deployment boundary

Define a conservative baseline for a locally operated Agora instance that stores projects, immutable tabular snapshots, run databases, decision records and audit events. Treat the host, project directory and operator account as security boundaries. A VM is a deployment boundary, not proof of tenant isolation.

The baseline is deny-by-default: no public listener, no inbound access except an explicitly approved operator path, and no outbound network egress except a specifically documented dependency or local model endpoint. Prefer a local model service on loopback or a private host-only network.

## 2. Single-host controls

- Run Agora under a dedicated, non-administrator OS account with no interactive administrative privileges.
- Keep source code, virtual environment, model cache, project data, backups and secrets in separate directories with separate permissions.
- Restrict the project root to the service/operator group. Do not make project directories world-readable or world-writable.
- Bind the web UI to loopback only. The current README describes the UI as listening on `127.0.0.1`; do not reverse-proxy or expose it to a LAN/WAN without a separate security review.
- Disable automatic startup until service identity, working directory, file ownership, logs, shutdown and recovery behaviour are configured.
- Enable full-disk encryption where supported. Encrypt backup media separately and protect encryption keys outside the backup directory.
- Apply OS security updates through a controlled maintenance window; preserve a tested rollback path.

## 3. VM controls

- Use a minimal supported guest OS image; remove unused packages, accounts, services and listening ports.
- Use a dedicated VM identity and security group/firewall policy. Default-deny inbound and outbound traffic.
- Permit inbound administration only from an approved management network and approved identity path. Do not expose the Agora UI directly.
- Permit outbound traffic only to explicitly approved package mirrors during maintenance and to the configured local/private model endpoint at runtime. If the model endpoint is on the same VM, bind it to loopback.
- Keep VM snapshots and backups encrypted and access-controlled. A VM snapshot is not a substitute for application-consistent database backup.
- Do not share writable host folders with the VM unless the exact path and access need are approved.

## 4. File and database permissions

Protect all project databases and their parent directories. Known data includes:

- `<project>/agora.db` — simulation run state;
- `<project>/data/tabular.sqlite3` — imported tabular snapshots and manifests;
- the configured decision-record SQLite file;
- the configured audit-chain SQLite file;
- future audit-anchor sidecar/history files, once implemented.

Recommended baseline:

- Directories: owner and dedicated service group only; no access for other users.
- SQLite files: readable/writable only by the service identity and explicitly authorised backup operator.
- SQLite journal/WAL/SHM files: inherit the same protected directory permissions.
- Backups: separate backup identity, encrypted at rest, no general developer access.
- Never rely on file permissions alone for isolation between projects or tenants.

The exact decision-store and audit-chain paths are configuration-dependent; inventory and document them before deployment. Do not assume a path that is not explicitly configured.

## 5. Backup and restore

### 5.1 Backup set

A backup set must identify one consistent recovery point and include, as applicable:

1. project scenario and immutable project metadata;
2. `agora.db` and any related run metadata;
3. `data/tabular.sqlite3`, source snapshot files and source registry metadata;
4. ontology packs, binding definitions and transformation-policy records needed to interpret the snapshots;
5. decision-record store and its append-only version/event history;
6. audit-chain database and verification output;
7. audit-anchor history paired with the exact audit-chain state, once anchoring is implemented;
8. configuration needed to restore operation, excluding live secrets and private keys.

Use SQLite's supported online backup mechanism or a coordinated quiesce/backup procedure. Do not copy a live SQLite database file blindly while it may be writing. For a multi-store backup, stop writes or establish a documented checkpoint protocol and record the backup set ID and each database's integrity result.

### 5.2 Backup schedule and retention

Define RPO/RTO with the system owner before deployment. Suggested initial posture: daily encrypted full backup, more frequent protected copies for actively changing stores, and a tested restore at least quarterly. These are proposed defaults, not current product behaviour.

Keep backup encryption keys separately. Restrict deletion rights and use immutable/object-lock storage only where independently administered. Record backup creation, verification, expiry and deletion as operational events without including secrets or personal values.

### 5.3 Restore sequence

1. Declare maintenance mode and stop all Agora writers.
2. Identify the exact backup-set ID and verify its integrity and encryption metadata.
3. Restore to an isolated staging directory with restrictive permissions.
4. Restore the audit-chain database and its matching anchor history as a pair. Never pair a chain with an unrelated or older anchor. Until the anchor implementation exists, record that independent tail-truncation protection is unavailable.
5. Run SQLite integrity checks on every restored database and the audit-chain verifier. Verify the anchor against the restored chain when available.
6. Verify snapshot manifests, exact import IDs, file hashes, binding fingerprints and run provenance references.
7. Verify decision-record version chains and cross-store reconciliation status. Do not silently repair mismatches.
8. Run the synthetic smoke checks in the pilot runbook.
9. Obtain operator sign-off before switching traffic or resuming writes.
10. Preserve the failed environment and diagnostic evidence until the incident owner authorises disposal.

A restore must not silently resurrect erased payloads. Apply the approved retention/erasure procedure and check backup expiry obligations before returning restored data to active use.

## 6. Secrets and sensitive configuration

- Do not commit API keys, passwords, tokens, private keys, database credentials or encryption keys to Git, scenario files, fixtures, logs, reports or Notion.
- Prefer an OS secret store or a deployment secret manager. If environment variables are unavoidable, scope them to the service process and prevent them from appearing in process diagnostics or support bundles.
- Separate development, test and production credentials. Rotate exposed credentials immediately and record rotation without recording the secret.
- Do not put credentials in model prompts, source documents, CSV files or audit event payloads.
- Use synthetic fixtures for development and pilot validation. The current pilot data contract rejects credentials and direct personal columns.

## 7. Network egress policy

Default-deny outbound network access. The application is described as local-first, but local operation does not by itself prove that every dependency or configured backend is offline.

Before enabling any egress, document the destination, port, protocol, purpose, data classes sent, owner, expiry and logging. Permit only the configured model endpoint and controlled maintenance dependencies. Do not enable external databases, telemetry, webhooks, identity providers, package downloads at runtime or external write-back as an implicit convenience.

The current repository does not provide a complete host firewall, VM egress policy, service mesh, central egress proxy or verified network isolation control. These remain deployment responsibilities.

## 8. Upgrade and rollback

1. Pin the application release/commit and dependency lock state for each deployment.
2. Review release notes, schema changes and migration requirements before upgrade.
3. Take and verify a complete backup set before modifying application code or databases.
4. Upgrade in staging using a copy of synthetic data; run the full test suite and restore rehearsal.
5. Deploy to the target host during a maintenance window. Keep writers stopped during any required migration.
6. Verify database integrity, audit-chain integrity, policy denial paths, report provenance and a synthetic end-to-end smoke check.
7. If verification fails, stop writers and roll back application code and databases together to the same verified recovery point. Do not run an older application against a newer schema unless compatibility is documented and tested.
8. Record the release, commit, dependency set, backup-set ID, operator, verification results and rollback decision.

No automatic database migration/rollback safety should be assumed unless a specific migration tool and compatibility contract are added and tested.

## 9. Incident response

| Trigger | Immediate response | Recovery gate |
| --- | --- | --- |
| Spike in policy denials | Stop the affected workflow; preserve safe event IDs/reason codes; check scope, policy version and configuration changes. Do not weaken policy to restore throughput. | Independent policy review and a synthetic deny/allow regression check. |
| Audit-chain verification failure | Stop protected writes; preserve database and logs read-only; capture first broken sequence and chain hash. | Integrity investigation, anchor comparison when available, documented recovery approval. |
| Anchor mismatch or unanchored tail | Stop protected operations; preserve both stores; do not auto-advance or reset the anchor. | Reconcile from a verified checkpoint under two-person approval. |
| Audit append failure after decision transition | Treat the transition as stored but not fully audited; preserve both stores and flag reconciliation. | Explicit reconciliation record and operator sign-off; never rewrite the original transition. |
| Suspected credential exposure | Revoke/rotate credential, restrict egress, preserve evidence and inspect access logs. | Credential rotation verified and exposure scope reviewed. |
| Suspected data loss or erasure regression | Stop writes and restores that could reintroduce data; preserve evidence and consult the retention/erasure procedure. | Data steward/privacy approval before recovery or reactivation. |

## 10. Current implementation status — do not overclaim

The repository contains local SQLite stores, an append-only hash-chain audit store, a deny-by-default PDP, report provenance gates and a retention/erasure design. These do not amount to a hardened deployment platform.

Not implemented or not demonstrated by the repository on the assessed mainline:

- host/VM provisioning, hardened service account or OS-level file ACL enforcement;
- enforced firewall rules or default-deny network egress;
- secret manager integration, key rotation or central credential policy;
- encrypted backup orchestration, tested coordinated restore, RPO/RTO controls;
- implemented audit-anchor storage and external immutable anchoring;
- automated cross-store reconciliation;
- production OIDC, enterprise tenant isolation or fleet controls;
- operational incident alerting, on-call procedures or compliance certification;
- automated, proven database migration and rollback.

The audit-anchor design is specified separately in `docs/AUDIT_ANCHOR_SPEC.md`; the retention/erasure proposal is in `docs/RETENTION_ERASURE_DESIGN.md`. Both are design references, not proof that those controls are operational.

## 11. Verification checklist before any production pilot

- [ ] Named system owner, operator and data steward.
- [ ] Dedicated service identity and least-privilege file permissions verified on host.
- [ ] UI bound to loopback; inbound and outbound firewall policy reviewed.
- [ ] Model endpoint and any allowed egress explicitly documented.
- [ ] No secrets in repository, fixtures, logs, scenario files or reports.
- [ ] All SQLite database paths inventoried; permissions and journal files checked.
- [ ] Encrypted backup set created and restore rehearsal passed.
- [ ] Audit chain verifies; anchor pair checked if implemented.
- [ ] Retention/erasure obligations and backup expiry reviewed.
- [ ] Upgrade and rollback rehearsal completed.
- [ ] Synthetic pilot runbook completed with all expected denials.
- [ ] Explicit owner sign-off recorded before production data or external connectivity.

This document is a proposed hardening plan. It does not authorise production data, credentials, network access, external write-back, or any change to `VALIDATED_PREDICTION_ENABLED` (which remains `False`).
