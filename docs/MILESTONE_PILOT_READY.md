# Governed Synthetic Pilot — Milestone Readiness

**Status:** Claude-confirmed M1 code-complete; this is not M2 operator-pilot or production authorisation  
**Assessment date:** 22 November 2026  
**Main base:** `932dfbc4dcb200c53da86bc8580b219eee877076`
**Scope:** Local synthetic-data governance pipeline only

#148 holds the source anchor-writer lock across verify/copy/post-verify, excludes the sidecar lock file and reuses one manifest snapshot for verify/restore (CI `45026655360`, 4/4). #154 strict manifest version/sequence/hash validation is merged (exact-head CI `45037406804`, 4/4). #155 (test-only B10 lock-handshake) is merged at exact head `943d707ac1a67772ca82383c4f00c82c31806fee`; exact-head CI run `45039917180` passed 4/4. Main is now `932dfbc4dcb200c53da86bc8580b219eee877076`. Claude's 21:21 IST entry claims runbook-binding in `tests/test_runbook_commands.py` next. #152's barrier still precedes the pending-row delivery boundary; it does not prove both replay callers fetched the same pending row before delivery. Legacy-marker backfill and outcome/review marker-audit reconciliation remain open. #141 still tests the inventory, not `OPERATOR_RUNBOOK.md`; exact numeric exits, required status tokens and named proof mapping remain open. #142 provenance still needs strict legacy/new discrimination, exact version types, timezone-aware RFC3339, manifest/envelope timestamp equality, complete report/export fields and failure-atomic publication. The pilot intermediate-ancestor `lstat` failure mutation proof is missing. M2 remains incomplete.


This assessment does not authorise simulation, calibration, backtest, forecast, study mutation, real data, credentials, network access, production use or external write-back.

## 2. Evidence basis and merged documentation

## 2.1 Claude's exact M1 confirmation and evidence (22 November 2026)

Claude's 09:05 IST log entry explicitly confirms M1 reached on main `83d0645b983365dddd9da07d4d1352e0b66e3d00`. The entry reports a clean-checkout command:

```bash
python -m agora.cli pilot --workdir <new-empty-dir>
```

Claude's M1 confirmation reports all nine stages completed: `provision_audit`, `import`, `bind`, `decision`, `approval`, `outcome_record`, `outcome_review`, `audit_verify`, and `report`; the audit verifier returned `INTACT`, `anchored_verified`, trust level `local_sidecar`. The report was synthetic-labelled, no simulation engine was run, and `VALIDATED_PREDICTION_ENABLED=False`. Claude reported 747 local tests passed on the M1 confirmation SHA; ChatGPT did not execute the command or tests. Current main is `932dfbc4dcb200c53da86bc8580b219eee877076`, with implementation PRs through #152 and docs PR #150 merged. #141 (`45012531745`), #142 (`45013670475`), #144 (`45015043801`) and #145 (`45021238785`) exact-head CI runs passed all four Ubuntu/Windows × Python 3.11/3.12 jobs.

Assessment base: `932dfbc4dcb200c53da86bc8580b219eee877076`. 

Confirmed merged documentation PRs:
- #59 — principal call-site migration plan.
- #60 — outcome dependency review-marker specification.
- #61 — pilot-readiness checklist.
- #62 — rung-status refresh.
- #64 — audit-anchor wiring and recovery plan.
- #65 — callable-pipeline capability guide.
- #77 — five-document readiness refresh, merged after rebasing on #78; exact-head docs CI run 235 passed all four matrix jobs.
- #83 — M1/M2 readiness refresh, synthetic fixture specification and provisional operator runbook; merged after exact-head docs CI passed all four matrix jobs.

Confirmed merged implementation PRs:
- #53 — append-only observed outcomes and review API.
- #54 — binding purpose/retention propagation into the policy hook.
- #58 — first synthetic principal approval slice; remaining call sites are not migrated.
- #63 — local-sidecar audit-anchor primitive; #71 adds the writer factory and policy-denial/data-boundary wiring (Stages A/D); #74/#75 add lifecycle/outcome append wiring and the structural `AuditAppender` contract. Protected gates remain opt-in.
- #74 — anchored decision lifecycle and outcome/review append wiring, with opt-in anchor gates on three principal entry points.
- #75 — structural `AuditAppender` protocol for decision/outcome audit writers; no change to optional `audit=None` behaviour.
- #66 — Windows audit-log lock fix.
- #78 — `principal_policy(principal, required_role)` and `enforce_policy(..., require_policy=True)`; exact-head CI run 233 (`44930549886`) passed all four matrix jobs.
- #79 — opt-in `require_policy` on `ingest_csv()`, `materialize_instances()` and `build_scenario_input()`; exact-head CI run 236 (`44931670540`) passed all four matrix jobs after one Windows 3.11 database-lock failure was rerun successfully.
- #80 — principal-native `authorize_decision_approval_principal()` and `approve_as()`; exact-head CI run 239 (`44934473818`) passed all four matrix jobs.
- #82 — initially gates legacy role-string `approve()` behind an environment switch; #97 removes that environment variable and moves test-only enablement to `agora.protection.LEGACY_APPROVE_ENABLED`.
- #84 — `approve_as()` ignores the caller-supplied resource and builds PDP inputs from the stored decision scope plus fixed baseline sensitivity `internal`; precise `AnchorRequiredError` tests replace the broad exception assertion. Exact-head CI run `44939812441` passed all four matrix jobs.
- #88 — adds the `agora pilot --workdir <new-empty-directory>` guided synthetic workflow, with per-stage results, first-denial stop, anchored audit verification and synthetic-labelled report; exact-head CI run `44945307064` passed all four jobs.

- #89 — default-on policy/anchor parameters on six protected entry points; merged at `87c7cc95b3e7c231f52dca4924d6fc433c698462`. Exact-head Actions run `44948055801` passed all four matrix jobs.
- #92 — retires public role-string `record_outcome()` / `review_outcome()` exports and routes public writes through Principal wrappers; merged before #94 (mainline merge `1fbde112`). Exact-head Actions run `44950576945` passed all four matrix jobs.
- #94 — lazy-loads `.sim.engine` only in engine-dependent CLI handlers; fresh-process tests cover `import agora.cli` and `agora pilot --help`. Exact-head Actions run `44955653075` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs.
- #96 — removes explicit `require_policy` / `require_anchored` opt-out kwargs from six protected public entry points; exact-head CI run `44956724553` passed 4/4.
- #97 — removes the legacy approval environment switch, defaults direct policy enforcement from `POLICY_REQUIRED=True`, and refuses the unanchored fallback when `audit=None`; exact-head CI run `44958568446` passed 4/4.
- #99 — removes the direct `require_policy` override and requires an anchored writer for protected policy-denial events; exact-head CI run `44960946006` passed 4/4.
- #100 — adds the read-only decision/audit reconciliation detector; exact-head CI run `44963254416` passed 4/4.
- #109 — adds pre-mutation anchored-writer guards to `propose()`, `reject()`, `expire()` and `supersede()`; exact-head CI run `44975437439` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs.
- #113 — adds `BoundPolicy` and protected rejection of non-Principal-bound callables; exact-head Actions run `44979668275` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs.
- #115 — adds the approver-authorised, anchored, exact-head, idempotent missing-event repair API; exact-head Actions run `44980052093` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs.
- #111 — makes the role-string approval authorizer private and restricts PDP imports to the internal allowlist.
- #116/#122/#147/#149/#151/#152 — append-only outcome dependency markers, lifecycle/supersession hardening, marker-open outbox, real-chain replay, anchored-valid transition lookup and a two-caller concurrency proof. #149/#151/#152 exact-head CI runs `45029282251`, `45031782290`, `45034452114` each passed 4/4. #152's barrier precedes pending-row delivery, so add a delivery-boundary handshake. Legacy-marker backfill remains open; Claude's current claimed slice is runbook-binding after #155 merged. `advance_marker_as()` uses stable transition IDs with audit-before-commit; outcome/review marker-audit reconciliation remains separate.
- #119 — adds read-only sidecar-anchor verification before reconciliation classification and requires `--anchor` / `--chain-id`; exact-head run `44981680171` passed 4/4.
- #120/#127/#134 provide the local synthetic backup/verify/restore CLI and direct-root hardening; #135 closes workdir-ancestor/fixture-catalogue symlink gaps; #136 closes backup ancestor/pre-read/lstat-error gaps (CI `45006493190`, 4/4); #138 adds copied-chain sequence/head comparison and manifest binding (CI `45009045175`, 4/4); #148 adds source writer lock, sidecar lock exclusion and single manifest snapshot for verify/restore (CI `45026655360`, 4/4). #154 strict manifest field typing is merged (CI `45037406804`, 4/4); #155 B10 event-based real-writer lock test is merged (CI `45039917180`, 4/4). #139 closes B13 (CI `45011493565`, 4/4); pilot intermediate-ancestor lstat-failure coverage remains.
Exact-head GitHub Actions evidence:
- #63 head `ef1f0ee430598c018a3cccd2ba2627a733f123f5`, run [44917009154](https://github.com/Post2Drive/Agora/actions/runs/44917009154): all four Ubuntu/Windows × Python 3.11/3.12 jobs passed.
- #66 head `6e0b483d628e5b4317e2cd3296a0bf0604d403f6`, run [44912719682](https://github.com/Post2Drive/Agora/actions/runs/44912719682): all four matrix jobs passed.
- #74 head `ca92a206219bb7da6de4b4f50a157b74ac6103c7`, run [44928837108](https://github.com/Post2Drive/Agora/actions/runs/44928837108): all four matrix jobs passed.
- #75 head `ae1b50577047eb7ef1435bcf231037f566eed77d`, run [44929428177](https://github.com/Post2Drive/Agora/actions/runs/44929428177): all four matrix jobs passed.
- #65 head `039beae59e0d3478d5412260d34a1f83618571e8`, run [44910310968](https://github.com/Post2Drive/Agora/actions/runs/44910310968): all four matrix jobs passed.

These are exact-head GitHub Actions results, not local test runs. PR #77's documentation CI run 235 also passed all four matrix jobs. The #79 Windows 3.11 first attempt had a transient SQLite `database is locked` failure; its rerun passed, and the cause remains a hardening item.

## 3. Current capability assessment

| Capability | Status | Evidence and limitation |
|---|---|---|
| Local structured CSV snapshot import | **Available — CLI** | #28 and later provenance/policy work. Local only; no external connectors/write-back. |
| Ontology binding | **Available — Python API, protected boundary** | #96 removes the public `require_policy` opt-out kwarg from `materialize_instances()`; #99 removes the direct helper override and requires an anchored writer for protected denial events. Principal/identity migration remains a separate concern. |
| Shared policy enforcement | **Done — protected Principal-bound callback** | #113 adds `BoundPolicy` and `PRINCIPAL_BOUND_REQUIRED=True`; protected `enforce_policy()` rejects raw callables and re-evaluates the bound Principal on each call. The adapter remains synthetic-fixture-only; no real identity provider or credentials are included. |
| Scenario-input package | **AVAILABLE — used by guided pilot; not connected to engine** | #31/#41 define the package; #142 calls `build_scenario_input()` during pilot bind and stores its envelope in the run record. It is still not consumed by `agora/sim/engine.py`; no simulation wiring is authorised. |
| Decision record/store and lifecycle | **Available — Python API** | #37/#42 and audit events #47. No single end-to-end command. |
| Principal-based approval and outcome wrappers | **Available — Principal public routes; protected shared policy gate** | #92/#96 retire public role-string outcome routes and public anchor opt-outs; #97 confines legacy approval to a test-only flag. #113 adds protected `BoundPolicy` enforcement and rejects raw callables. The identity adapter remains synthetic-fixture-only. |
| Audit hash chain | **Available — local chain only** | #38/#47; verifies its own chain but cannot independently detect a removed tail. |
| Anchored audit chain | **Available — local-sidecar API; protected lifecycle guards merged** | #99 requires an anchored writer for protected policy-denial events; #109 adds pre-mutation `require_anchored()` guards to `propose()`, `reject()`, `expire()` and `supersede()` when `ANCHOR_REQUIRED=True`. Optional signature annotations do not permit `None` or plain writers on the protected path. The anchor remains `local_sidecar`; coordinated rollback and the Linux lock-removal mutation gap remain limitations. |
| Read-only audit timeline and chain/anchor verification | **Available — CLI component (#107)** | `agora audit timeline` verifies the hash chain and lists one decision's stored transitions/related audit events; `agora audit verify` compares the chain with its local sidecar in plain language. It does not make the sidecar independent or detect coordinated rollback of both local files. |
| Observed outcome recording/review | **Available — Principal public routes; private internals remain** | #92 retires public role-string exports and #96 removes public anchor opt-outs. #102 adds a separate read-only held-outcome list; #106 normalizes connection-open SQLite failures to `STORE_UNREADABLE` / exit 2. Neither creates dependency markers or changes outcomes. Private helpers still have optional audit internals. |
| Outcome dependency review markers | **PARTIAL — marker-open replay and stable transition retry (#147/#149/#151); two-caller test merged (#152), backfill pending** | #147 persists marker-open audit intent; #149 adds real-chain same-payload replay; #151 requires anchored-valid lookup and stable transition IDs; #152 adds two independent replay callers (CI `45034452114`, 4/4). Its barrier precedes pending-row delivery; add a delivery-boundary handshake. Legacy-marker backfill remains open; Claude's current claim is runbook-binding (#155 merged). Outcome/review marker-audit reconciliation remains separate. |
| Decision/audit reconciliation | **Done — anchored read-only detector plus API repair** | #100/#104 detect decision lifecycle gaps; #119 verifies the sidecar and #122 holds the same anchor lock across verification/classification. #115 remains API-only, approver-authorised and exact-head-bound for missing decision events. The lock helper opens a sidecar file with `a+b`, which may create a metadata file; the concurrency test uses a fixed sleep rather than a deterministic handshake. Repair excludes outcome/review rows and unanchored-tail recovery remains blocked. |
| Simulated-labelled report | **Available — separate exploratory/mock path** | Existing report CLI path; not connected to the scenario-input/decision/outcome workflow. |
| Single callable end-to-end pipeline | **AVAILABLE — guided synthetic CLI plus M2 fixture/start and partial run record** | #88 provides the nine-stage first-denial-stop workflow; #94 keeps pilot/data dispatch engine-import-free. #125 adds `agora pilot list/start` with the checked-in fixture. #130 adds baseline run-record checks; #132 pins the checked-in manifest and rejects direct fixture/workdir-root symlinks; #135 rejects workdir symlink/reparse-point ancestors and filters linked fixture directories; #139 rejects lexical `..`; #142 stores `input_provenance` during pilot bind. Strict legacy/new, timestamp/version, manifest/report checks, failure-atomic publication and #144/#145 prove clean-checkout install/start and exact run-record/flag/console-script assertions (head 6338c5a5; exact-head CI 45021238785 passed 4/4). |
| Integrated pilot readiness | **M1 Claude-confirmed; M2 incomplete** | Main `932dfbc4dcb200c53da86bc8580b219eee877076` includes #141/#142/#144/#145/#147/#148/#149/#151/#152/#154. #152's two-caller test is merged (CI 4/4), but its start barrier does not guarantee both callers fetched the same pending row before delivery; strengthen with a delivery-boundary handshake. Remaining: legacy backfill, backup manifest typing/B10 synchronization, direct runbook binding, strict/atomic provenance, pilot ancestor-lstat proof, held-outcome/reconcile runbook integration and separately approved logged rehearsal. |

## 4. Pull request status snapshot

| PR | Scope | State at this assessment |
|---|---|---|
| #59 | Principal migration plan | Merged |
| #60 | Outcome dependency review-marker specification | Merged |
| #61 | Pilot-readiness checklist | Merged |
| #62 | Rung-status refresh | Merged |
| #63 | Local audit-anchor implementation | Merged |
| #64 | Audit-anchor wiring plan | Merged |
| #65 | Pipeline capability guide and readiness refresh | Merged |
| #66 | Windows audit-log lock fix | Merged |
| #67–#69 | Readiness and manual-procedure documentation | Merged |
| #70 | Principal-first outcome record/review bridge | Merged |
| #71 | Anchored writer factory and policy-denial wiring (Stages A/D) | Merged |
| #72 | Earlier documentation refresh based on pre-#71 main | Closed; superseded |
| #74 | Anchored lifecycle/outcome append wiring and opt-in principal anchor gates | Merged |
| #75 | Structural `AuditAppender` protocol for lifecycle/outcome writers | Merged |
| #77 | Five-document readiness refresh | Merged |
| #78 | Principal-bound policy helper and missing-policy gate | Merged |
| #79 | Opt-in policy requirement on import/binding/scenario-input | Merged |
| #80 | Principal-native decision approval gate | Merged |
| #83 | M1/M2 readiness refresh, fixture specification and provisional operator runbook | Merged |
| #84 | Approval policy-resource derivation and precise anchor-error regression tests | Merged |
| #85 | Nine-document readiness refresh and operator run-record field map | Merged; exact-head CI run `44945012741` passed four jobs |
| #86 | Outcome `_as` resource derivation and anchored denial tests | Merged (`a0777c1`); four exact-head jobs green, run `44942485500` |
| #88 | Guided synthetic `agora pilot --workdir` entry point | Merged (`6e2d766`); exact-head CI run `44945307064` passed 4/4 |
| #89 | Default-on policy/anchor parameters on six protected entry points | Merged (`87c7cc95`); exact-head CI run `44948055801` passed 4/4 |
| #91 | Documentation refresh after #88/#89 | Merged; exact-head CI run `44949947675` passed 4/4 |
| #92 | Public role-string outcome API retirement | Merged; exact-head CI run `44950576945` passed 4/4 |
| #94 | Lazy-load simulation engine only in engine-dependent CLI handlers | Merged; exact-head CI run `44955653075` passed 4/4 |
| #95 | M1/M2 documentation refresh after #94 | Merged; exact-head docs CI run `44958100514` passed 4/4 |
| #96 | Remove public policy/anchor opt-out kwargs | Merged; exact-head CI run `44956724553` passed 4/4 |
| #97 | Remove legacy approval env switch and unanchored denial fallback | Merged; exact-head CI run `44958568446` passed 4/4 |
| #99 | Remove direct policy-helper override and require anchored denial writer | Merged; exact-head CI run `44960946006` passed 4/4 |
| #100 | Read-only decision/audit reconciliation detector | Merged; exact-head CI run `44963254416` passed 4/4 |
| #101 | M1/M2 documentation refresh after #100 | Merged; exact-head CI run `44965464662` passed 4/4 |
| #102 | Read-only `agora outcomes held` listing | Merged; exact-head CI run `44965953082` passed 4/4 |
| #106 | Held-list connection-open failure hardening | Merged; exact-head CI run `44970435296` passed 4/4 |
| #107 | Read-only audit timeline and chain-vs-anchor verification CLI | Merged; exact-head CI run `44972864246` passed 4/4 |
| #109 | Pre-mutation anchored-writer guards for decision lifecycle transitions | Merged; exact-head CI run `44975437439` passed 4/4 |
| #111 | Role-string approval authorizer made private; PDP imports restricted to internal allowlist | Merged |
| #113 | Principal-bound `BoundPolicy` enforcement | Merged; exact-head CI run `44979668275` passed 4/4 |
| #115 | Approver-authorised, anchored, exact-head missing-decision-event repair API | Merged; exact-head CI run `44980052093` passed 4/4 |
| #116 | First append-only outcome dependency-marker slice | Merged; exact-head CI run `44980453453` passed 4/4 |
| #119 | Read-only sidecar-anchor verification before reconcile classification | Merged; exact-head CI run `44981680171` passed 4/4 |
| #120 | Local synthetic backup/verify/restore CLI and tamper-detection tests | Merged; exact-head CI run `44986367729` passed 4/4 |
| #121 | Documentation refresh after #120/#122 | Merged at head `769de633b6d13c14d60a353da989b716443f0d12`; exact-head Actions run `44990546024` passed 4/4 |
| #122 | Post-M1 marker audit ordering, supersession scope and reconcile lock | Merged at head `73c2d5db61db775602a18ad1d170bc010b39ebbf`; exact-head Actions run `44989188092` passed 4/4 |
| #123 | M2 pilot run-record first slice | Merged at head `1cfc69b3f56b2b98fd8e2eb68e52d69a8d276122`; exact-head run `44990673166` passed 4/4; provenance coverage/loader validation remain incomplete |
| #124 | Documentation refresh after #122/#123 | Merged at head `c937abc412bbae6f3ac2e728a6e6ab4fdd0fb285`; exact-head CI `44991628960` passed 4/4 |
| #125 | Checked-in synthetic fixture and `agora pilot list/start` | Merged; #132 completes manifest/fixture/direct-root hardening and #135 completes workdir-ancestor/fixture-catalogue symlink hardening; #144/#145 prove clean-checkout install/start and exact run-record/flag/console-script assertions (head 6338c5a5; exact-head CI 45021238785 passed 4/4) |
| #126 | Documentation refresh after #125 | Merged; docs-only |
| #127 | M2 backup/restore hardening | Merged at `a4ac0cbdd3efd69da1ace090fa0a4dedc1a6d9a3`; exact-head CI `44994798420` passed 4/4 |
| #128 | M2 runbook inventory and rehearsal plan | Closed as superseded; both docs consolidated into #129 |
| #129 | Consolidated M1/M2 documentation, runbook, command inventory and rehearsal plan | Merged at head `100899e0d93f3d7c7be32996c41853f4461a1ad0`; exact-head CI `44996252476` passed 4/4 |
| #130 | Strict run-record loader and non-empty-workdir guard | Merged at `4e5ff1c8d3d4a6bdeb385b8aed43b7a9c5da65bd`; exact-head CI `44995421141` passed 4/4. #142 later adds the pilot `input_provenance` envelope; strict legacy/new, timestamp/version, manifest/report checks and atomic publication remain open |
| #132 | Fixture/workdir symlink, pinned manifest digest and empty-version hardening | Merged at head `c1fad55c448d0a7e6c49b098824a25e857f7372d`; exact-head CI `44997320523` passed 4/4; #135 subsequently closes workdir-ancestor and linked-fixture catalogue gaps |
| #133 | M3 proposal, validation protocol, red-team and full-potential plans | Documentation-only; merged at head `5248fbde073051078ce2811b06408700c7abd7f2`; exact-head CI `45004073994` passed 4/4 |
| #134 | Direct backup/verify/restore root symlink and reparse-point refusal | Merged at head `47e9a7ec827ed5b5f097605d694263fe660fbb5a`; exact-head CI `44999538699` passed 4/4 |
| #135 | Workdir-ancestor symlink refusal and fixture-catalogue link filtering | Merged at head `2db77c29451c0a9e38c90a148ea635ff143d5cac`; exact-head CI `45001811790` passed 4/4 |
| #136 | Backup ancestor/pre-read/lstat-error refusal | Merged at head `b5d7b045d89a354fdef758feaa49adc23e8fa703`; exact-head CI `45006493190` passed 4/4 |
| #138/#148/#154 | Backup copied-chain sequence/head comparison, source writer lock, single-read manifest snapshot and strict manifest typing | #138 exact-head CI `45009045175` passed 4/4; #148 exact-head CI `45026655360` passed 4/4 and adds real anchored-writer exclusion, sidecar lock-file exclusion, and one manifest snapshot for verify/restore. The writer test still uses bounded join; deterministic event/lock-acquisition synchronization remains open. Strict manifest field typing is merged in #154 (CI `45037406804`, 4/4). |
| #139 | B13 lexical `..` refusal in backup and pilot path walkers | Merged at head `2d3a0e7fa4b2d5821dc8126971a6499b23d012e2`; exact-head CI `45011493565` passed 4/4; pilot intermediate-ancestor lstat test remains |
| #145 | Exact clean-install run-record, explicit false-flag and installed console-script no-engine-import assertions | Merged at head `6338c5a563f0d1dc50b87f0a36826619e3a7ed3e`; exact-head CI `45021238785` passed 4/4 |
| #147/#149/#151/#152 | Marker-open outbox/replay, anchored-valid lookup, stable transition retry and two-caller test | #147/#149/#151/#152 merged; CI `45029282251`, `45031782290`, `45034452114` each passed 4/4. #152's start barrier does not prove overlapping delivery after both callers read the pending row. Legacy-marker backfill remains open; Claude's current claim is runbook-binding (#155 merged). |

Assessment base is main `932dfbc4dcb200c53da86bc8580b219eee877076` after #155 merged. M1 remains Claude-confirmed; M2 remains owner-approved local synthetic scope only and is not reached. #154 strict manifest version/sequence/hash validation is merged (exact-head CI `45037406804`, 4/4). #155 (test-only B10 lock-handshake) is merged at exact head `943d707ac1a67772ca82383c4f00c82c31806fee`; exact-head CI run `45039917180` passed 4/4. Main is now `932dfbc4dcb200c53da86bc8580b219eee877076`. Claude's 21:21 IST entry claims runbook-binding in `tests/test_runbook_commands.py` next. #152's barrier still precedes the pending-row delivery boundary; it does not prove both replay callers fetched the same pending row before delivery. Legacy-marker backfill and outcome/review marker-audit reconciliation remain open. #141 still tests the inventory, not `OPERATOR_RUNBOOK.md`; exact numeric exits, required status tokens and named proof mapping remain open. #142 provenance still needs strict legacy/new discrimination, exact version types, timezone-aware RFC3339, manifest/envelope timestamp equality, complete report/export fields and failure-atomic publication. The pilot intermediate-ancestor `lstat` failure mutation proof is missing. M2 remains incomplete. After the claimed runbook-binding slice, remaining M2 gaps are pilot intermediate-ancestor `lstat` failure mutation coverage; strict legacy/new run-provenance validation, timezone-aware RFC3339, manifest/envelope timestamp equality, complete report/export fields and failure-atomic publication; outcome/review marker-audit reconciliation; held-outcome/reconcile runbook integration; and a separately approved, logged synthetic dress rehearsal. No rehearsal is claimed.

## 5. M1 exit gates — Claude confirmation recorded

- [x] Principal migration plan, outcome-marker specification and pilot-readiness checklist merged (#59–#61).
- [x] Audit-anchor wiring plan merged (#64); it remains a plan, not implementation.
- [x] Synthetic Principal approval foundation merged (#58), then M1 shared-policy migration completed by #111/#113: role-string authorizer private/allowlisted and protected `enforce_policy()` requires `BoundPolicy`. The adapter remains synthetic-only; production identity/OIDC is not claimed.
- [x] Local audit-anchor implementation merged (#63), with all four exact-head CI jobs green. Trust remains local-sidecar; the Linux lock-removal mutation proof did not detect the mutation.
- [x] Windows audit-log lock fix merged (#66), with all four exact-head CI jobs green.
- [x] Anchored writer factory and policy-denial/import/binding/scenario-input wiring merged (#71, Stages A/D), with all four exact-head CI jobs green.
- [x] Lifecycle/outcome append wiring added by #74; subsequent #89/#96/#97/#99/#109/#113 establish default-on protected policy, Principal-bound callback and anchored-writer gates. The synthetic identity adapter and local-sidecar trust remain explicit limitations.
- [x] Principal-native decision approval path merged in #80: `approve_as()` uses the adapter-issued Principal and no caller role/subject parameter.
- [x] Legacy role-string `approve()` is disabled by default; #97 removes the environment-variable switch and confines enablement to the test-only module flag `LEGACY_APPROVE_ENABLED`, reset by test fixtures. Exact-head CI passed 4/4.
- [x] #84 closes the `approve_as()` caller-resource downgrade path by ignoring the supplied resource and using stored decision scope plus fixed baseline sensitivity; its precise anchor-error/no-state-change coverage passed exact-head CI.
- [x] Require policy presence, Principal-bound policy and anchored denial audit on protected public paths. #96/#97/#99/#109 enforce protected defaults and anchored-writer guards; #113 adds the Principal-bound `BoundPolicy` requirement and rejects raw callables. The identity adapter remains synthetic-only. `local_sidecar` trust and the Linux lock-removal mutation gap remain limitations.
- [x] Principal-bound shared policy gate implemented by #113: protected `enforce_policy()` requires `BoundPolicy` and rejects raw callables; `principal_policy()` re-evaluates the adapter-issued Principal on each call. Identity remains synthetic-fixture-only.
- [x] Decision lifecycle reconciliation and missing-event repair are implemented by #100/#104/#115. Repair is API-only, approver-authorised, anchored and exact-head-bound; it handles missing events only, has no CLI, does not reconcile outcomes/reviews and blocks unanchored-tail recovery.
- [x] Outcome dependency markers — #116/#122 append-only markers/lifecycle; #147 marker-open outbox; #149 real-chain same-payload replay; #151 anchored-valid lookup/stable transition retry; #152 two-caller test merged. #152 still needs a delivery-boundary handshake after both callers fetch the pending row. Legacy-marker backfill remains open; Claude's current claim is runbook-binding (#155 merged); outcome/review marker reconciliation remains open.
- [x] A callable CLI/API entry point runs the synthetic example end to end: #88 provides `agora pilot --workdir <new-empty-directory>`; #125 adds the checked-in fixture and `agora pilot list/start`; #132 adds the independent manifest pin, direct fixture symlink checks, empty-version refusal and direct workdir-root symlink refusal; #135 adds workdir-ancestor refusal and linked-fixture catalogue filtering. The guided workflow has nine stages and does not call the engine. #144/#145 prove clean-checkout install/start and exact run-record/flag/console-script assertions (head 6338c5a5; exact-head CI 45021238785 passed 4/4).
- [x] The CLI module no longer imports the simulation engine for pilot/data dispatch; #94 lazy-loads it only in engine-dependent handlers and passes exact-head CI 4/4. Fresh-process coverage is for `--help`, not a complete `--workdir` invocation.
- [x] Exact-head CI is green on the M1 implementation heads: #113 (`44979668275`), #115 (`44980052093`), #116 (`44980453453`), #119 (`44981680171`) and #122 (`44989188092`) each passed all four Ubuntu/Windows × Python 3.11/3.12 jobs; mutation proofs are recorded in the implementation PRs.
- [x] Claude logged the exact M1 confirmation at 09:05 IST on 22 November 2026, naming main `83d0645b983365dddd9da07d4c1352e0b66e3d00`, the clean-checkout pilot command and the nine completed stages.
- [ ] M2 remains owner-approved for local synthetic implementation but is not reached. Main is `932dfbc4dcb200c53da86bc8580b219eee877076`. #155 (test-only B10 lock-handshake) is merged at exact head `943d707ac1a67772ca82383c4f00c82c31806fee`; exact-head CI run `45039917180` passed 4/4. Main is now `932dfbc4dcb200c53da86bc8580b219eee877076`. Claude's 21:21 IST entry claims runbook-binding in `tests/test_runbook_commands.py` next. After the claimed runbook-binding slice, remaining M2 gaps are pilot intermediate-ancestor `lstat` failure mutation coverage; strict legacy/new run-provenance validation, timezone-aware RFC3339, manifest/envelope timestamp equality, complete report/export fields and failure-atomic publication; outcome/review marker-audit reconciliation; held-outcome/reconcile runbook integration; and a separately approved, logged synthetic dress rehearsal. No rehearsal is claimed.

Passing these gates means only that a scoped synthetic rehearsal may be considered. It does not establish predictive validity, real demand, sales performance, production security or permission for external actions.

## 6. Documentation status

M2 planning specifications remain linked from `docs/MILESTONE_OPERATOR_PILOT.md`. M2 is not reached. #155 (test-only B10 lock-handshake) is merged at exact head `943d707ac1a67772ca82383c4f00c82c31806fee`; exact-head CI run `45039917180` passed 4/4. Main is now `932dfbc4dcb200c53da86bc8580b219eee877076`. Claude's 21:21 IST entry claims runbook-binding in `tests/test_runbook_commands.py` next. After the claimed runbook-binding slice, remaining M2 gaps are pilot intermediate-ancestor `lstat` failure mutation coverage; strict legacy/new run-provenance validation, timezone-aware RFC3339, manifest/envelope timestamp equality, complete report/export fields and failure-atomic publication; outcome/review marker-audit reconciliation; held-outcome/reconcile runbook integration; and a separately approved, logged synthetic dress rehearsal. No rehearsal is claimed.

This assessment is refreshed against main `932dfbc4dcb200c53da86bc8580b219eee877076`, including merged #141/#142/#144/#145/#147/#148/#149/#151/#152/#154/#155 and docs #150/#153. Exact-head CI for #154 and #155 passed 4/4. M1 remains Claude-confirmed; M2 remains incomplete.

## 7. Permanent safety boundaries

- Keep `VALIDATED_PREDICTION_ENABLED=False`.
- Do not run simulations, calibration, backtests or forecasts as part of this documentation task.
- Do not mutate existing studies, study folders, NCC Park Square or E0_C0_D0.
- Do not use real data, personal/customer records, credentials, real drivers, network access or external write-back.
- Do not edit `agora/sim/**`; scenario-input-to-engine wiring remains blocked pending Claude's written approval and separate owner approval.
- A green CI run does not authorise a PR merge, ready-for-review transition or external action.
