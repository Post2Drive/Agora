# Operator Runbook — Governed Synthetic Pilot

**Status:** Provisional operator runbook; command-test and rehearsal gates remain incomplete. Claude confirmed M1 in the 09:05 IST log entry; owner-approved scope is local synthetic M2 only. #138 exact sequence/head + manifest binding is merged (CI `45009045175`, 4/4); no writer-side lock, and verify/restore re-read the manifest after validation. #139 B13 is open at `2d3a0e7f`, CI `45011493565` 4/4, not on main. M2 still needs single-read manifest validation, deterministic writer proof, full provenance/atomic publication, held-outcome/reconcile commands, executable runbook test and logged rehearsal.
**Assessment base:** `main` at `fd888ab9cf158681a000699c071909d38a165024` (22 November 2026).
**Milestone dependency:** the owner-approved scope checklist `docs/MILESTONE_OPERATOR_PILOT.md` and checked-in fixture are the source of the M2 boundary. The command-test contract is `docs/M2_RUNBOOK_COMMAND_INVENTORY.md`; the rehearsal script/evidence template is `docs/M2_DRESS_REHEARSAL_PLAN.md`. This file remains a provisional status map, not an executable runbook or rehearsal authorisation.

## 1. Scope and safety

Local synthetic data and local stores only. No real data, personal/customer records, credentials, network connectors, external write-back, simulation, calibration, backtest, forecast or study mutation is authorised here. Do not touch `agora/sim/**`. Keep `VALIDATED_PREDICTION_ENABLED=False`. NCC and Nutrivance are out of scope.

A green CI run, a draft runbook or a component API does not authorise an operator rehearsal. Only Claude's exact milestone confirmation can declare a milestone reached; owner-only actions require separate explicit approval.

## 2. M2 operator capability checklist

| M2 requirement | Mainline status at `fd888ab9cf158681a000699c071909d38a165024` | Evidence / missing item |
|---|---|---|
| One-command install/start | **PARTIAL — fixture-selected start exists, clean-install proof absent** | Main includes `agora pilot start --fixture ID --workdir D` (#125). #132 rejects a directly symlinked workdir root; #135 now rejects symlink/reparse-point ancestors and filters linked fixture directories. Clean package installation from a checkout is still unproven. |
| Checked-in synthetic dataset | **AVAILABLE — fixture integrity hardening merged (#132); test coverage follow-up remains** | #132 independently pins the manifest digest, rejects symlinked fixture directory/manifest/payload paths and empty fixture versions. The test suite does not separately exercise symlinked `schema.json` and `binding.json`. Clean-install proof is absent. |
| Guided end-to-end run with per-step results and clear gate-denial stops | **AVAILABLE — partial M2 evidence** | #88 is on main; #125 adds fixture-selected `start`; #132 rejects direct workdir-root symlinks. Parent-component symlink checks and clean-checkout proof remain open. |
| Anchor and policy checks enabled by default everywhere | **DONE for protected policy paths; local trust limitation remains** | #113 requires `BoundPolicy` under `PRINCIPAL_BOUND_REQUIRED=True`; #111 restricts role-string PDP imports and makes the role-string approval authorizer private. #96/#97/#99/#109 keep protected defaults and anchored-writer guards. #119/#122 verify the sidecar under the shared lock before reconcile classification. The original TOCTOU gap is closed; the lock helper may still create a `.lock` metadata file and the concurrency test uses a fixed sleep. Identity remains synthetic-only and anchor trust remains `local_sidecar`. |
| Legacy paths removed or test-only | **PARTIAL — public authorizer private/allowlisted; test-only legacy approval remains** | #92 retires public role-string outcome exports; #111 makes the role-string approval authorizer private and restricts PDP imports to the internal allowlist; #96 removes public wrapper opt-outs; #97 confines legacy approval enablement to the test-only module flag. |
| Readable audit timeline and plain-language chain/anchor verification | **COMPONENTS AVAILABLE (#107, #119, #122); runbook test pending** | `agora audit timeline` lists one decision's stored transitions/events after hash-chain verification; `agora audit verify` compares the chain with the local sidecar. `agora reconcile` (#119/#122) holds the anchor lock across verification/classification. Trust remains `local_sidecar`; the lock helper may create a `.lock` metadata file and the race test uses a fixed sleep, so read-only semantics/test determinism need clarification. |
| Backup/restore and tamper drill | **MERGED SYNTHETIC CLI (#120/#127/#134/#136/#138); operator procedure incomplete** | #138 compares exact sequence/head and binds them in the manifest (CI `45009045175`, 4/4); no writer-side lock, manifest re-read gap remains. #139 B13 is open with 4/4 CI but not on main. Single-read manifest validation, deterministic writer proof, command test and logged tamper drill remain incomplete. |
| Minimal reconciliation and held-outcome listing | **PARTIAL — detector, repair API, held list and marker slice exist** | #100/#104/#119 detect decision lifecycle gaps; #122 holds the anchor lock across verify/classify; #115 repairs missing decision events through an approver-authorised API. #102/#106 list held outcomes; #116/#122 provide explicit-edge markers and primary lifecycle hardening. Residuals: lock-file creation/read-only semantics and fixed-sleep race test; marker DB commit failure after successful audit append; outcome/review and marker-audit reconciliation, repair CLI and unanchored-tail recovery remain open. |
| Run records per `docs/RUN_PROVENANCE_SPEC.md` | **PARTIAL — #123/#125/#130 merged** | #130 adds required-field/type, synthetic-only, false-engine/prediction and hash-format checks. Full input_provenance, exact repository SHA, fixture-block/map validation, timestamps/status enums, cross-field hashes, failure-atomic publication and pre-stage failure records remain open. |
| Operator runbook commands executed by a test | **NOT YET** | This skeleton has no executable command set and no test that executes it. |
| Logged dress rehearsal | **NOT YET** | No rehearsal is recorded or authorised by this draft. |

## 3. Existing components (not a complete operator workflow)

- **AVAILABLE — local CSV import CLI:** `agora data import-csv`, `agora data snapshots`, `agora data show` and `agora data rejected`.
- **AVAILABLE — Python APIs:** ontology binding/materialization, scenario-input construction, decision records, principal-native `approve_as()`, outcome/review APIs and local anchored-audit primitives.
- **PROTECTED — policy enforcement:** #96 removes public `require_policy` opt-out kwargs; #97 removes the unanchored `audit=None` fallback; #99 removes the direct helper override and requires an anchored writer for protected denial events.
- **PARTIAL — principal approval:** #80/#84 provide `approve_as()` with server-derived policy inputs; #96 removes its public anchor opt-out kwarg. #97 removes the legacy approval env switch; only the test-only `LEGACY_APPROVE_ENABLED` flag remains.
- **PARTIAL — anchored audit:** #71/#74/#75 wire append points; #96 removes public `require_anchored=False` kwargs, #92 retires public role-string outcome exports, #97 removes the unanchored denial fallback, #99 validates the policy-denial writer, and #109 guards the remaining decision lifecycle transitions before mutation. Trust remains `local_sidecar`; low-level lifecycle signatures retain optional annotations but protected calls refuse missing/plain writers, while private outcome helpers remain internal.
- **AVAILABLE — guided synthetic command:** `agora pilot --workdir <new-empty-directory>` (#88) runs nine stages and stops on first denial without invoking the engine. #125 adds `agora pilot list/start --fixture <id>` using the checked-in fixture. #132 pins the manifest, rejects direct fixture directory/manifest/payload symlinks and empty versions, and refuses a directly symlinked workdir root; workdir ancestors are refused since #135; clean-install proof remains open. #94 keeps pilot/data dispatch engine-import-free.
- **AVAILABLE — read-only audit commands (#107):** `agora audit timeline` lists one decision's transitions/related audit events after hash-chain verification; `agora audit verify` compares the chain with the local anchor and reports the local-sidecar trust limitation. They do not write, repair or bootstrap.
- **PARTIAL — reconciliation and held outcomes:** #100/#104/#119 provide the anchored decision lifecycle detector; #122 holds the lock across verification/classification, with a lock-file metadata side effect and a fixed-sleep race-test caveat. #115 is API-only repair for missing decision events. #102/#106 list held outcomes; #116/#122 provide explicit-edge markers and primary lifecycle hardening. A marker-store commit failure after successful audit append still needs reconciliation semantics; retention/erasure triggers, automatic report/run edges, marker/audit reconciliation and a repair CLI remain open.

Do not execute a component command as though it were the full M2 workflow.

## 4. Future operator sequence — NOT EXECUTABLE

The following headings reserve the runbook structure. Each step must be replaced with exact, tested commands only after the relevant interface exists and Claude's M2 milestone specification is available.

1. **Preflight and installation — NOT YET:** verify supported Python/runtime, one-command install/start, clean local workspace and explicit synthetic-only mode.
2. **Fixture selection — AVAILABLE (#125/#132), direct-path integrity hardened:** use `agora pilot list`, then `agora pilot start --fixture <id> --workdir <new-empty-directory>`. Main independently pins the checked-in manifest digest, rejects direct fixture directory/manifest/payload symlinks and empty fixture versions, and rejects a directly symlinked workdir root. #135 rejects symlink/reparse-point workdir ancestors and #135's tests cover `schema.json` and `binding.json` symlinks. Prove clean package installation from a clean checkout.
3. **Policy and anchor verification — NOT YET:** verify principal, scope, required policy, anchored writer, chain ID and anchor state before any protected read or write.
4. **Guided import/bind/scenario-input — PARTIAL:** #88 guides import and binding with per-step results and first-denial stop, but does not call `build_scenario_input()`; no simulation-engine call is in scope.
5. **Decision and principal approval — DEFAULT-ON SYNTHETIC PRINCIPAL PATH:** #80/#84 make `approve_as()` Principal-native; #96 removes its public anchor opt-out kwarg. #97 removes the legacy approval environment switch; `approve()` remains disabled by default and can be enabled only through the test-only `agora.protection.LEGACY_APPROVE_ENABLED` module flag. #92 retires public role-string outcome APIs; #111 makes the role-string approval authorizer private and restricts PDP imports to the internal allowlist; #113 requires `BoundPolicy` in protected `enforce_policy()`. Identity remains synthetic-fixture-only.
6. **Audit timeline and verification — COMPONENTS AVAILABLE (#107; runbook test pending):**

   ```bash
   agora audit timeline --decisions <db> --audit <db> --decision-id <opaque-decision-id>
   agora audit verify --audit <db> --anchor <file> --chain-id <chain-id>
   ```

   The timeline command verifies the hash chain and lists the selected decision's stored transitions and related audit events; it does not compare the anchor. Run verify separately for the chain-vs-local-anchor check. Exit codes: timeline `0` listed, `1` not found, `2` blocked; verify `0` intact, `1` not intact, `2` blocked. The verify output explicitly states the `local_sidecar` trust limitation. These commands remain provisional runbook entries until a test executes them.
7. **Reconciliation and held outcomes — PARTIAL:** `agora reconcile --decisions <db> --audit <db> --anchor <file> --chain-id <id>` (#100/#104/#119/#122) verifies the hash chain and sidecar before classification and holds the anchor lock across both phases. #104 validates immutable transition metadata and partial-open cleanup. Exit 0 intact, 1 gaps, 2 blocked. #115 remains API-only repair for missing decision events; #102/#106 are the separate held-outcome list; #116/#122 add explicit-edge markers and primary lifecycle/supersession hardening. Residuals: lock-file creation under the read-only contract, fixed-sleep concurrency test, marker-store commit failure after successful audit append, and no outcome/review marker-audit reconciliation or unanchored-tail recovery.
8. **Backup/restore and tamper drill — HARDENED CLI COMPONENTS (#120/#127); operator test pending:**

   ```bash
   agora backup --project <synthetic-project-dir> --dest <new-empty-backup-dir>
   agora backup verify --backup <backup-dir>
   agora restore --backup <backup-dir> --target <new-empty-target-dir>
   ```

    #127 requires a run record marked `data_class=synthetic`; otherwise backup returns `SOURCE_NOT_SYNTHETIC`. In-tree symlinks/unsafe relative paths return `UNSAFE_PATH`; malformed manifest schema returns `BACKUP_MANIFEST_INVALID`; a copied chain/anchor that no longer verifies returns `SNAPSHOT_CHANGED`. #134 rejects direct project/destination/backup-root/data/manifest/restore-target symlink or Windows reparse-point paths (`UNSAFE_PATH`; CI `44999538699`, 4/4). #136 adds ancestor-component, nested `run_record.json`/chain/anchor pre-read and fail-closed lstat guards (CI `45006493190`, 4/4 passed). Its `os.path.abspath()` normalization may hide a symlink before `..`; add a deterministic regression. The current lstat-error mutation test injects failure only at the project root, not an intermediate ancestor; the pre-read test covers `run_record.json` but not chain/anchor paths. Add those proofs and the `..`-through-symlink regression. A shared source-pair lock and exact chain ID/sequence/head equality are still required; Claude has claimed this next code slice. Restore re-hashes every restored file. Use only the checked-in synthetic pilot project and new temporary destinations. The automated command inventory test and logged operator tamper drill remain outstanding; no command was run for this documentation update.
9. **Run record and report — PARTIAL:** #123 persists an initial immutable `run_record.json`; #125 adds fixture ID/version/manifest/file hashes; #130 adds required-field/type/hash validation. The mainline record still omits the full RUN_PROVENANCE_SPEC `input_provenance` envelope, exact cross-field hash/schema validation and failure-atomic publication; pre-stage failures can bypass record creation.
10. **Dress rehearsal — NOT YET:** only after the M2 checklist, tested runbook, exact-head CI and separate owner approval; log the exact command, SHA, fixture hashes, stage results, denials and operator sign-off.

## 5. Mandatory stop conditions

Stop immediately on a missing/invalid Principal, wrong tenant/project, missing required policy, missing/invalid anchor, chain mismatch, non-exact import ID, provenance mismatch, unexpected source read before policy denial, real/personal/sensitive data, credentials, network access, write-back, a simulation/engine call, an unlabelled exploratory output or any attempt to modify a protected study.

Never repair a reconciliation gap by rewriting a decision version or audit event. Preserve ambiguous cases for independent human review. Never treat a simulated preference, agent action, conversion or report metric as an observed outcome.

## 6. Evidence to record when the runbook becomes executable

Record the repository SHA, exact command and CLI version, operator identity reference, synthetic fixture IDs and hashes, schema/binding/ontology fingerprints, import ID, scenario-input hash, decision ID/version/fingerprint, policy version and denial codes, audit chain ID/head, anchor verification result, run-record hash, report ID/mode and backup/restore/tamper drill outcomes. Do not log raw rows, sensitive values, credentials or unrestricted free text.

M1 was explicitly confirmed by Claude in the 09:05 IST log entry on main `83d0645`; this skeleton does not declare M2 reached and does not authorise a rehearsal.
