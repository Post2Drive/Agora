# Operator Runbook — Governed Synthetic Pilot

**Status:** Draft skeleton only; not an executable runbook, rehearsal record or readiness declaration. Claude confirmed M1 in the 09:05 IST log entry; #111, #113, #115, #116, #119 and #120 are merged. The current owner instruction approves local synthetic M2 implementation; the 10:50 owner decision prioritised the three post-M1 hardening fixes, now closed by merged #122. Runbook tests and rehearsal remain incomplete.  
**Assessment base:** `527476bb4e0450050843dd23a2aa6d5417627ded` (22 November 2026).
**Milestone dependency:** the owner-approved scope checklist `docs/MILESTONE_OPERATOR_PILOT.md` and the synthetic fixture specification are merged documentation. This file remains a provisional status map, not an executable runbook or rehearsal authorisation.

## 1. Scope and safety

Local synthetic data and local stores only. No real data, personal/customer records, credentials, network connectors, external write-back, simulation, calibration, backtest, forecast or study mutation is authorised here. Do not touch `agora/sim/**`. Keep `VALIDATED_PREDICTION_ENABLED=False`. NCC and Nutrivance are out of scope.

A green CI run, a draft runbook or a component API does not authorise an operator rehearsal. Only Claude's exact milestone confirmation can declare a milestone reached; owner-only actions require separate explicit approval.

## 2. M2 operator capability checklist

| M2 requirement | Mainline status at `527476bb4e0450050843dd23a2aa6d5417627ded` | Evidence / missing item |
|---|---|---|
| One-command install/start | **NOT YET** | `agora pilot --workdir <new-empty-directory>` exists (#88), but it is not a one-command installer/start or clean-checkout setup workflow. |
| Checked-in synthetic dataset | **NOT YET** | #88 embeds `SYNTHETIC_CSV`, schema and binding in `agora/pilot.py`; `fixtures/pilot.csv`, `fixtures/pilot-schema.yaml` and `fixtures/pilot-binding.yaml` remain absent on main. |
| Guided end-to-end run with per-step results and clear gate-denial stops | **AVAILABLE — partial M2 evidence** | #88 merges `agora pilot --workdir`; it reports nine stages, stops at the first denial/failure and marks later stages skipped. Exact-head CI run `44945307064` passed 4/4. It does not persist the M2 run record or use a checked-in fixture set. |
| Anchor and policy checks enabled by default everywhere | **DONE for protected policy paths; local trust limitation remains** | #113 requires `BoundPolicy` under `PRINCIPAL_BOUND_REQUIRED=True`; #111 restricts role-string PDP imports and makes the role-string approval authorizer private. #96/#97/#99/#109 keep protected defaults and anchored-writer guards. #119 verifies the sidecar before reconcile classification. Identity remains synthetic-only and anchor trust remains `local_sidecar`; reconcile has a TOCTOU hardening item. |
| Legacy paths removed or test-only | **PARTIAL — public authorizer private/allowlisted; test-only legacy approval remains** | #92 retires public role-string outcome exports; #111 makes the role-string approval authorizer private and restricts PDP imports to the internal allowlist; #96 removes public wrapper opt-outs; #97 confines legacy approval enablement to the test-only module flag. |
| Readable audit timeline and plain-language chain/anchor verification | **COMPONENTS AVAILABLE (#107, #119); runbook test pending** | `agora audit timeline` lists one decision's stored transitions and related audit events after hash-chain verification; `agora audit verify` compares the chain with the local sidecar. `agora reconcile --decisions <db> --audit <db> --anchor <file> --chain-id <id>` (#119) also requires an anchored-verified chain before classification. The trust level remains `local_sidecar`; the reconcile TOCTOU review finding remains open. |
| Backup/restore and tamper drill | **CLI AVAILABLE — operator procedure incomplete (#120)** | `agora backup --project P --dest D`, `agora backup verify --backup D`, and `agora restore --backup D --target T` are implemented. Exact-head Actions run `44986367729` passed 4/4. Source pair locking, post-copy restored-file rehash, synthetic-source allowlisting/symlink rejection and manifest-schema validation remain hardening gaps; the runbook command test and logged tamper drill are not complete. Do not use the current CLI against any non-synthetic or unmarked project. |
| Minimal reconciliation and held-outcome listing | **PARTIAL — detector, repair API, held list and marker slice exist** | #100/#104 detect decision lifecycle gaps; #119 checks the sidecar anchor before classification; #115 repairs missing decision events by an approver-authorised API only. #102/#106 list held outcomes read-only. #116 adds explicit-edge marker propagation for disputed/corrected/source-hash-mismatch triggers. Outcome/review audit reconciliation, marker/audit reconciliation, repair CLI and unanchored-tail recovery remain open; a reconcile TOCTOU review finding remains. |
| Run records per `docs/RUN_PROVENANCE_SPEC.md` (no engine call) | **NOT YET** | #88 returns an in-memory `PilotResult`; it does not persist and verify the immutable M2 run-record envelope. |
| Operator runbook commands executed by a test | **NOT YET** | This skeleton has no executable command set and no test that executes it. |
| Logged dress rehearsal | **NOT YET** | No rehearsal is recorded or authorised by this draft. |

## 3. Existing components (not a complete operator workflow)

- **AVAILABLE — local CSV import CLI:** `agora data import-csv`, `agora data snapshots`, `agora data show` and `agora data rejected`.
- **AVAILABLE — Python APIs:** ontology binding/materialization, scenario-input construction, decision records, principal-native `approve_as()`, outcome/review APIs and local anchored-audit primitives.
- **PROTECTED — policy enforcement:** #96 removes public `require_policy` opt-out kwargs; #97 removes the unanchored `audit=None` fallback; #99 removes the direct helper override and requires an anchored writer for protected denial events.
- **PARTIAL — principal approval:** #80/#84 provide `approve_as()` with server-derived policy inputs; #96 removes its public anchor opt-out kwarg. #97 removes the legacy approval env switch; only the test-only `LEGACY_APPROVE_ENABLED` flag remains.
- **PARTIAL — anchored audit:** #71/#74/#75 wire append points; #96 removes public `require_anchored=False` kwargs, #92 retires public role-string outcome exports, #97 removes the unanchored denial fallback, #99 validates the policy-denial writer, and #109 guards the remaining decision lifecycle transitions before mutation. Trust remains `local_sidecar`; low-level lifecycle signatures retain optional annotations but protected calls refuse missing/plain writers, while private outcome helpers remain internal.
- **AVAILABLE — guided synthetic command:** `agora pilot --workdir <new-empty-directory>` (#88) runs nine stages and stops on first denial without invoking the engine. #94 keeps CLI pilot/data dispatch engine-import-free; fresh-process coverage exercises `--help`, not a complete `--workdir` invocation.
- **AVAILABLE — read-only audit commands (#107):** `agora audit timeline` lists one decision's transitions/related audit events after hash-chain verification; `agora audit verify` compares the chain with the local anchor and reports the local-sidecar trust limitation. They do not write, repair or bootstrap.
- **PARTIAL — reconciliation and held outcomes:** #100/#104/#119 provide a read-only decision lifecycle detector that verifies the sidecar before classification; #115 adds API-only, approver-authorised repair of missing decision audit events. #102/#106 provide the separate read-only held-outcome list. #116 adds explicit-edge markers, but review found audit-before-commit and same-target supersession gaps in `advance_marker_as()`; retention/erasure triggers, automatic report/run edges, marker/audit reconciliation and a repair CLI remain open. The #119 verify/read TOCTOU window also remains open.

Do not execute a component command as though it were the full M2 workflow.

## 4. Future operator sequence — NOT EXECUTABLE

The following headings reserve the runbook structure. Each step must be replaced with exact, tested commands only after the relevant interface exists and Claude's M2 milestone specification is available.

1. **Preflight and installation — NOT YET:** verify supported Python/runtime, one-command install/start, clean local workspace and explicit synthetic-only mode.
2. **Fixture selection — NOT YET:** select the checked-in synthetic dataset and record exact immutable fixture/schema/binding IDs and hashes.
3. **Policy and anchor verification — NOT YET:** verify principal, scope, required policy, anchored writer, chain ID and anchor state before any protected read or write.
4. **Guided import/bind/scenario-input — PARTIAL:** #88 guides import and binding with per-step results and first-denial stop, but does not call `build_scenario_input()`; no simulation-engine call is in scope.
5. **Decision and principal approval — DEFAULT-ON SYNTHETIC PRINCIPAL PATH:** #80/#84 make `approve_as()` Principal-native; #96 removes its public anchor opt-out kwarg. #97 removes the legacy approval environment switch; `approve()` remains disabled by default and can be enabled only through the test-only `agora.protection.LEGACY_APPROVE_ENABLED` module flag. #92 retires public role-string outcome APIs; #111 makes the role-string approval authorizer private and restricts PDP imports to the internal allowlist; #113 requires `BoundPolicy` in protected `enforce_policy()`. Identity remains synthetic-fixture-only.
6. **Audit timeline and verification — COMPONENTS AVAILABLE (#107; runbook test pending):**

   ```bash
   agora audit timeline --decisions <db> --audit <db> --decision-id <opaque-decision-id>
   agora audit verify --audit <db> --anchor <file> --chain-id <chain-id>
   ```

   The timeline command verifies the hash chain and lists the selected decision's stored transitions and related audit events; it does not compare the anchor. Run verify separately for the chain-vs-local-anchor check. Exit codes: timeline `0` listed, `1` not found, `2` blocked; verify `0` intact, `1` not intact, `2` blocked. The verify output explicitly states the `local_sidecar` trust limitation. These commands remain provisional runbook entries until a test executes them.
7. **Reconciliation and held outcomes — PARTIAL:** `agora reconcile --decisions <db> --audit <db> --anchor <file> --chain-id <id>` (#100/#104/#119) verifies the hash chain and local sidecar read-only before classifying decision lifecycle/audit gaps; it fails closed unless the verdict is `anchored_verified`. #104 validates immutable transition metadata, expected audit operation/resource IDs and partial-open cleanup. Exit 0 intact, 1 gaps, 2 blocked. #115 adds a separate API-only, approver-authorised, anchored, exact-head repair for missing decision audit events; no CLI, outcome/review reconciliation or unanchored-tail recovery. `agora outcomes held --decisions <db>` (#102/#106) remains a separate read-only list; #116 adds explicit-edge markers for disputed/corrected/source-hash-mismatch triggers. Marker lifecycle audit failure and supersession-scope gaps plus the #119 verify/read TOCTOU finding must be fixed before operator reliance.
8. **Backup/restore and tamper drill — CLI COMPONENT AVAILABLE (#120); validation pending:**

   ```bash
   agora backup --project <project-dir> --dest <new-empty-backup-dir>
   agora backup verify --backup <backup-dir>
   agora restore --backup <backup-dir> --target <new-empty-target-dir>
   ```

   These commands are not yet an operator-validated procedure. Before reliance, require a verified synthetic project marker/fixture allowlist, reject symlinks and unapproved files, harden source verification plus chain/anchor copying under one `AnchorStore.lock()`, validate manifest schema, re-hash every restored file against the manifest after copying, and add deterministic scope/concurrency/tamper tests. Do not run these commands against an unmarked project; no command was run for this documentation update.
9. **Run record and report — PARTIAL:** #88 writes a synthetic-labelled report but does not persist the immutable run-record envelope defined in `docs/RUN_PROVENANCE_SPEC.md`.
10. **Dress rehearsal — NOT YET:** only after the M2 checklist, tested runbook, exact-head CI and separate owner approval; log the exact command, SHA, fixture hashes, stage results, denials and operator sign-off.

## 5. Mandatory stop conditions

Stop immediately on a missing/invalid Principal, wrong tenant/project, missing required policy, missing/invalid anchor, chain mismatch, non-exact import ID, provenance mismatch, unexpected source read before policy denial, real/personal/sensitive data, credentials, network access, write-back, a simulation/engine call, an unlabelled exploratory output or any attempt to modify a protected study.

Never repair a reconciliation gap by rewriting a decision version or audit event. Preserve ambiguous cases for independent human review. Never treat a simulated preference, agent action, conversion or report metric as an observed outcome.

## 6. Evidence to record when the runbook becomes executable

Record the repository SHA, exact command and CLI version, operator identity reference, synthetic fixture IDs and hashes, schema/binding/ontology fingerprints, import ID, scenario-input hash, decision ID/version/fingerprint, policy version and denial codes, audit chain ID/head, anchor verification result, run-record hash, report ID/mode and backup/restore/tamper drill outcomes. Do not log raw rows, sensitive values, credentials or unrestricted free text.

M1 was explicitly confirmed by Claude in the 09:05 IST log entry on main `83d0645`; this skeleton does not declare M2 reached and does not authorise a rehearsal.
