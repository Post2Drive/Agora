# Operator Runbook — Governed Synthetic Pilot

**Status:** Draft skeleton only; not an executable runbook, rehearsal record, approval or readiness declaration.  
**Assessment base:** `da008656f96a7fee774dbf89781ffbdbbe1adac6` (22 November 2026).
**Milestone dependency:** the owner-approved scope checklist `docs/MILESTONE_OPERATOR_PILOT.md` and the synthetic fixture specification are merged documentation. This file remains a provisional status map, not an executable runbook or rehearsal authorisation.

## 1. Scope and safety

Local synthetic data and local stores only. No real data, personal/customer records, credentials, network connectors, external write-back, simulation, calibration, backtest, forecast or study mutation is authorised here. Do not touch `agora/sim/**`. Keep `VALIDATED_PREDICTION_ENABLED=False`. NCC and Nutrivance are out of scope.

A green CI run, a draft runbook or a component API does not authorise an operator rehearsal. Only Claude's exact milestone confirmation can declare a milestone reached; owner-only actions require separate explicit approval.

## 2. M2 operator capability checklist

| M2 requirement | Mainline status at `da008656` | Evidence / missing item |
|---|---|---|
| One-command install/start | **NOT YET** | `agora pilot --workdir <new-empty-directory>` exists (#88), but it is not a one-command installer/start or clean-checkout setup workflow. |
| Checked-in synthetic dataset | **NOT YET** | #88 embeds `SYNTHETIC_CSV`, schema and binding in `agora/pilot.py`; `fixtures/pilot.csv`, `fixtures/pilot-schema.yaml` and `fixtures/pilot-binding.yaml` remain absent on main. |
| Guided end-to-end run with per-step results and clear gate-denial stops | **AVAILABLE — partial M2 evidence** | #88 merges `agora pilot --workdir`; it reports nine stages, stops at the first denial/failure and marks later stages skipped. Exact-head CI run `44945307064` passed 4/4. It does not persist the M2 run record or use a checked-in fixture set. |
| Anchor and policy checks enabled by default everywhere | **PARTIAL — public entry points guarded** | #96 removes public policy/anchor opt-outs; #97 removes the unanchored fallback; #99 removes the direct helper override and requires `require_anchored()` for protected denial writes. #109 adds pre-mutation guards to `propose()`, `reject()`, `expire()` and `supersede()` when `ANCHOR_REQUIRED=True`; optional annotations do not permit `None` or plain writers on protected paths. #111 restricts role-string PDP imports to allowlisted modules and removes the public role-string approval authorizer; typed PrincipalPolicy enforcement and data-boundary migration remain open, as does the `local_sidecar` trust limitation. |
| Legacy paths removed or test-only | **PARTIAL** | #92 retires public role-string outcome exports; #96 removes public wrapper opt-outs; #97 removes the legacy approval env switch and confines enablement to the test-only module flag; #111 renames the legacy role-string approval authorizer private and removes its public export. |
| Readable audit timeline and plain-language chain/anchor verification | **COMPONENTS AVAILABLE (#107); runbook test pending** | `agora audit timeline --decisions <db> --audit <db> --decision-id <id>` lists one decision's stored transitions and related audit events after hash-chain verification. `agora audit verify --audit <db> --anchor <file> --chain-id <id>` compares the chain with the local sidecar and prints a plain-language verdict plus the `local_sidecar` trust note. Timeline does not itself compare the anchor; run verify separately. |
| Backup/restore and tamper drill | **NOT YET** | Design guidance exists; no operator commands, tested procedure or logged drill is evidenced. |
| Minimal reconciliation and held-outcome listing | **PARTIAL** | #100/#104 list decision lifecycle/audit gaps read-only (exit 0 intact, 1 gaps, 2 blocked); #104 validates immutable source metadata, expected audit operation/exact resource IDs and partial-open cleanup. The detector still does not check the sidecar anchor or repair. #102 lists disputed/unreviewed/invalid-history outcomes and orphan review rows read-only (exit 0 none held, 1 held, 2 blocked); #106 normalizes connection-open SQLite errors to `STORE_UNREADABLE` / exit 2. It does not create markers or propagate source-dependency holds. |
| Run records per `docs/RUN_PROVENANCE_SPEC.md` (no engine call) | **NOT YET** | #88 returns an in-memory `PilotResult`; it does not persist and verify the immutable M2 run-record envelope. |
| Operator runbook commands executed by a test | **NOT YET** | This skeleton has no executable command set and no test that executes it. |
| Logged dress rehearsal | **NOT YET** | No rehearsal is recorded or authorised by this draft. |

## 3. Existing components (not a complete operator workflow)

- **AVAILABLE — local CSV import CLI:** `agora data import-csv`, `agora data snapshots`, `agora data show` and `agora data rejected`.
- **AVAILABLE — Python APIs:** ontology binding/materialization, scenario-input construction, decision records, principal-native `approve_as()`, outcome/review APIs and local anchored-audit primitives.
- **PROTECTED — policy enforcement:** #96 removes public `require_policy` opt-out kwargs; #97 removes the unanchored `audit=None` fallback; #99 removes the direct helper override and requires an anchored writer for protected denial events.
- **PARTIAL — principal approval:** #80/#84 provide `approve_as()` with server-derived policy inputs; #96 removes its public anchor opt-out kwarg. #97 removes the legacy approval env switch; only the test-only `LEGACY_APPROVE_ENABLED` flag remains.
- **PARTIAL — anchored audit:** #71/#74/#75 wire append points; #96 removes public `require_anchored=False` kwargs, #92 retires public role-string outcome exports, #97 removes the unanchored denial fallback, #99 validates the policy-denial writer, and #109 guards the remaining decision lifecycle transitions before mutation; #111 restricts role-string PDP imports to allowlisted modules but does not validate policy callback provenance. Trust remains `local_sidecar`; low-level lifecycle signatures retain optional annotations but protected calls refuse missing/plain writers, while private outcome helpers remain internal.
- **AVAILABLE — guided synthetic command:** `agora pilot --workdir <new-empty-directory>` (#88) runs nine stages and stops on first denial without invoking the engine. #94 keeps CLI pilot/data dispatch engine-import-free; fresh-process coverage exercises `--help`, not a complete `--workdir` invocation.
- **AVAILABLE — read-only audit commands (#107):** `agora audit timeline` lists one decision's transitions/related audit events after hash-chain verification; `agora audit verify` compares the chain with the local anchor and reports the local-sidecar trust limitation. They do not write, repair or bootstrap.
- **PARTIAL — reconciliation and held outcomes:** #100/#104 implement a read-only decision lifecycle detector with immutable source metadata and audit-event validation plus partial-open cleanup; it does not verify the anchor, reconcile outcome/review rows, persist a queue or repair gaps. #102/#106 add read-only held-outcome listing with fail-closed connection-open handling; no dependency marker store or propagation exists.

Do not execute a component command as though it were the full M2 workflow.

## 4. Future operator sequence — NOT EXECUTABLE

The following headings reserve the runbook structure. Each step must be replaced with exact, tested commands only after the relevant interface exists and Claude's M2 milestone specification is available.

1. **Preflight and installation — NOT YET:** verify supported Python/runtime, one-command install/start, clean local workspace and explicit synthetic-only mode.
2. **Fixture selection — NOT YET:** select the checked-in synthetic dataset and record exact immutable fixture/schema/binding IDs and hashes.
3. **Policy and anchor verification — NOT YET:** verify principal, scope, required policy, anchored writer, chain ID and anchor state before any protected read or write.
4. **Guided import/bind/scenario-input — PARTIAL:** #88 guides import and binding with per-step results and first-denial stop, but does not call `build_scenario_input()`; no simulation-engine call is in scope.
5. **Decision and principal approval — DEFAULT-ON PRINCIPAL PATH:** #80/#84 make `approve_as()` Principal-native; #96 removes its public anchor opt-out kwarg. #97 removes the legacy approval environment switch; `approve()` remains disabled by default and can be enabled only through the test-only `agora.protection.LEGACY_APPROVE_ENABLED` module flag. #92 retires the public role-string outcome APIs. #99 closes direct policy-helper bypasses. #111 removes the public role-string approval authorizer and restricts PDP imports to an allowlist; typed PrincipalPolicy validation remains open.
6. **Audit timeline and verification — COMPONENTS AVAILABLE (#107; runbook test pending):**

   ```bash
   agora audit timeline --decisions <db> --audit <db> --decision-id <opaque-decision-id>
   agora audit verify --audit <db> --anchor <file> --chain-id <chain-id>
   ```

   The timeline command verifies the hash chain and lists the selected decision's stored transitions and related audit events; it does not compare the anchor. Run verify separately for the chain-vs-local-anchor check. Exit codes: timeline `0` listed, `1` not found, `2` blocked; verify `0` intact, `1` not intact, `2` blocked. The verify output explicitly states the `local_sidecar` trust limitation. These commands remain provisional runbook entries until a test executes them.
7. **Reconciliation and held outcomes — PARTIAL:** `agora reconcile --decisions <db> --audit <db>` (#100/#104) lists decision lifecycle/audit gaps read-only; #104 validates transition/status/actor/method/timestamp against the immutable payload, audit operation and exact resource IDs, and partial-open cleanup; exit 0 intact, 1 gaps, 2 blocked. It still has no anchor check, queue or repair. `agora outcomes held --decisions <db>` (#102/#106) lists disputed, never-reviewed, invalid-history and orphan-review cases read-only; exit 0 none held, 1 held, 2 blocked. #106 maps connection-open SQLite errors to `STORE_UNREADABLE`. It does not create dependency markers, inspect source-hash changes or propagate holds.
8. **Backup/restore and tamper drill — NOT YET:** document and test copy/restore, anchor continuity, tamper detection and fail-closed recovery.
9. **Run record and report — PARTIAL:** #88 writes a synthetic-labelled report but does not persist the immutable run-record envelope in `docs/RUN_PROVENANCE_SPEC.md`.
10. **Dress rehearsal — NOT YET:** only after the M2 checklist, tested runbook, exact-head CI and separate owner approval; log the exact command, SHA, fixture hashes, stage results, denials and operator sign-off.

## 5. Mandatory stop conditions

Stop immediately on a missing/invalid Principal, wrong tenant/project, missing required policy, missing/invalid anchor, chain mismatch, non-exact import ID, provenance mismatch, unexpected source read before policy denial, real/personal/sensitive data, credentials, network access, write-back, a simulation/engine call, an unlabelled exploratory output or any attempt to modify a protected study.

Never repair a reconciliation gap by rewriting a decision version or audit event. Preserve ambiguous cases for independent human review. Never treat a simulated preference, agent action, conversion or report metric as an observed outcome.

## 6. Evidence to record when the runbook becomes executable

Record the repository SHA, exact command and CLI version, operator identity reference, synthetic fixture IDs and hashes, schema/binding/ontology fingerprints, import ID, scenario-input hash, decision ID/version/fingerprint, policy version and denial codes, audit chain ID/head, anchor verification result, run-record hash, report ID/mode and backup/restore/tamper drill outcomes. Do not log raw rows, sensitive values, credentials or unrestricted free text.

This skeleton does not declare M1 or M2 reached and does not authorise a rehearsal.
