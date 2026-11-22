# Full-Potential Test Plan — Governed Pipeline, Operator Workflow and M3

**Status:** Plan only. This is the requested end-to-end test outline; no full-potential test has been run. M2 remains in progress and M3 is proposal-only. The plan does not declare either milestone reached.

**Baseline:** main `c01098d8f815b1e76b12296f41e887d5f6dd87d0` (22 November 2026). The implementation facts below were checked against current main after #135 merged. The M2 documentation consolidated in #133 is on main; #132 fixture/workdir hardening, #134 direct backup/restore root symlink/reparse-point refusal and #135 workdir-ancestor/fixture-catalogue hardening are merged. PR #136 backup ancestor/pre-read/lstat-error checks remain open and not mainline (exact-head CI `45006493190`, 1/4 complete); a `..`-through-symlink normalization regression, backup snapshot-lock/head equality and clean-install proof remain open.

## 1. Objective and limits

After M2 and M3 are confirmed by Claude, demonstrate the whole governed workflow from clean checkout and synthetic pilot through denial, audit, backup/restore, reconciliation, owner-entered P2D rate-card decision, governed public-data inputs reaching the engine, labelled simulation output and end-to-end provenance.

The test proves that governance and data plumbing work together under the tested scope. It does not prove forecast accuracy, pricing quality, demand, sales, adoption, election outcomes, causal effects, production fitness or commercial value.

P2D is pre-launch with no real operational data. The P2D section uses only a hand-entered owner rate card; test accounts are not evidence of market volume. No P2D customer/driver data, live database, replica, Railway API, connector, credential, network access or write-back is permitted. Keep `VALIDATED_PREDICTION_ENABLED=False`.

## 2. Entry gates

All must pass before the full-potential test begins:

- [ ] Claude has explicitly confirmed M2 reached in the collaboration log.
- [ ] Claude has explicitly confirmed M3 reached in the collaboration log.
- [ ] M3 simulation-tree implementation was approved by owner by exact file path before code changes; exact-head CI is green on all four Ubuntu/Windows × Python 3.11/3.12 jobs.
- [ ] Validation protocol is committed before any validation run; protocol SHA and dataset register SHA are frozen.
- [ ] All three public benchmark packages pass source, licence, schema, field and hash checks. M5 competition terms are explicitly reviewed and recorded.
- [ ] Exact dataset/run scope matches owner's 12:52 named approval; no substitute dataset or expanded run scope is assumed.
- [ ] Any P2D rate-card test uses only owner-entered synthetic/illustrative values and has a separately approved decision scope. It is not an engine simulation or outcome validation.
- [ ] Exact run commands, CLI version, M3 adapter version, repository SHA, model/backend, seeds and environment are pinned.
- [ ] Synthetic red-team plan's critical denial cases have been executed by Claude and reviewed; unresolved root-symlink, snapshot consistency or provenance gaps block the corresponding test.
- [ ] A disposable local workspace exists. No existing project, study or run is reused.
- [ ] Separate owner approval is recorded for any specific rehearsal window or action not already covered by named approvals.

## 3. Six test areas

### Area 1 — Clean-checkout install and guided run

**Purpose:** prove that a new operator can install the exact release and complete the synthetic governed pilot without relying on a developer worktree or hidden local state.

**Procedure**

1. Start from a clean checkout of exact merged main SHA in a new temporary directory.
2. Install from documented package instructions in an isolated environment; record OS, Python, package manager and dependency lock.
3. Run documented fixture catalogue command and verify expected checked-in fixture/version/hash.
4. Start guided pilot in a truly empty, non-symlink workdir.
5. Capture all named stage results, denial stops, run record, report, audit chain and anchor verification.
6. Repeat from a second clean environment to check deterministic metadata and documented nondeterministic fields.

**Pass criteria**

- Installation succeeds using only documented steps.
- No undeclared global package, user configuration or prior project is required.
- Fixture version and hashes match pinned manifest.
- Every guided stage returns a stable status; first denial stops subsequent protected stages.
- Run record is valid and failure-atomic; `data_class=synthetic`, `engine_invoked=false`, `validated_prediction_enabled=false`.
- Pilot dispatch does not import `agora.sim.engine`.
- Report is clearly synthetic/exploratory and includes available provenance.

**Fail criteria:** missing fixture, hash drift, symlink escape, non-empty workdir acceptance, missing run record, partial run-record write, hidden environment dependency, simulation-engine import or any real data access.

### Area 2 — Every denial path

**Purpose:** prove deny-by-default behavior across identity, policy, approval, data import, binding, anchor and provenance boundaries.

**Procedure**

Run the complete denial matrix using isolated synthetic fixtures: forged/expired Principal; raw callable or unbound policy; missing/invalid policy; personal/sensitive column without approved purpose/retention; unknown import ID; wrong data role; invalid schema/binding; stale decision version; self-approval; wrong reviewer/approver; missing/plain audit writer; missing/corrupt/wrong-chain anchor; unanchored tail; changed manifest/input hash; resume with altered source or mapping.

**Pass criteria**

- Each denial returns exact typed failure or stable public code documented for that path.
- Protected source bytes are not read before policy denial.
- Decision, outcome, marker and run records are unchanged on pre-mutation denial.
- Required denial events are anchored and redacted.
- No fallback, implicit latest import, role-string bypass, raw callable or test-only legacy switch is available in protected path.
- Test records no secrets or raw rejected values.

**Fail criteria:** protected read before denial, unanchored denial event, silent allow, partial state, raw data in diagnostics or traceback instead of stable denial.

### Area 3 — Audit, backup, restore, tamper, reconciliation and held outcomes

**Purpose:** demonstrate that governance evidence can be inspected, verified, backed up, restored and fail-closed under tampering.

**Procedure**

1. Read one selected decision's audit timeline and verify chain/anchor.
2. Create and verify backup from marked synthetic pilot only.
3. Restore to a new empty directory; verify every restored file hash and audit/anchor pair.
4. Tamper disposable copies: event byte, truncation, anchor mismatch/rollback, manifest field, file hash, extra/missing file, symlink in tree, symlinked root/parent and restore-time file change.
5. Run reconciliation against clean and deliberately blocked copies.
6. List held outcomes against clean, held and unreadable stores.
7. Preserve all attacked copies; do not repair or overwrite them.

**Pass criteria**

- Timeline is redacted and read-only.
- Anchor verification and reconciliation report exact stable status; blocked anchor states stop classification.
- Backup refuses non-synthetic sources and unsafe paths; manifest faults and changed snapshots return documented codes.
- Restore verifies post-copy file hashes and publishes no partial target on failure.
- Reconciliation distinguishes missing, conflict, source-invalid and orphan cases without mutation.
- Held-outcome listing never treats unreadable state as no holds.
- Local-sidecar coordinated-rollback limitation is disclosed.
- All source and original backup hashes remain unchanged.

**Fail criteria:** silent repair, unsafe path read, backup of unmarked project, inconsistent pair, partial restore, mutation of source, false clean reconciliation or held outcome silently omitted.

### Area 4 — Governed owner-entered P2D rate-card decision

**Purpose:** prove that P2D's pre-launch pricing rules can be captured as a governed decision, without treating the project as a real-data or outcome pilot.

**Input boundary**

- Use a hand-entered rate card supplied/confirmed by owner, clearly labelled illustrative/owner-entered.
- No import from P2D database, no test-account records, no customer/driver/job data, no personal fields and no external file unless separately named and approved.
- Rate card contains only minimum fields required for decision: service/route class, distance or zone band, base charge, included allowance, per-unit increment, surcharge/discount, currency, effective date, owner and version. Freeze exact schema before test.
- No live quote, job, carrier or customer write-back.

**Procedure**

1. Record owner-entered rate card and its hash/version as a local synthetic/owner-entered input.
2. Register schema, purpose, policy, decision scope and evidence references.
3. Propose a bounded pricing-rule decision with explicit assumptions and alternatives.
4. Review and approve using distinct authorized principals and exact version/fingerprint checks.
5. Record a governed decision outcome only if owner explicitly supplies a synthetic test outcome; otherwise stop at approved decision.
6. Inspect decision timeline, approval evidence, anchor and report.

**Pass criteria**

- All values are labelled owner-entered/illustrative; no actual market outcome is inferred.
- Proposal, reviewer and approver are distinct and properly authorized.
- Decision scope, evidence and fingerprint match approved version.
- No P2D database or external service is accessed or changed.
- No claim of price optimality, conversion, demand or profitability is made.

**Fail criteria:** any live P2D data read, personal field, external write, role bypass, self-approval, stale version or unqualified pricing/performance claim.

### Area 5 — Governed public inputs reach the engine and produce labelled output

**Purpose:** prove the M3 governed-input path end to end on the three protocol-approved public benchmark packages.

**Procedure**

1. Use only frozen validation protocol and its named election/polls, M5 Walmart and Ember EV datasets. M5 use remains blocked until competition terms are recorded as permitting intended evaluation.
2. Manually supply permitted source files; AGORA has no network or connector.
3. Import exact files under approved schemas and explicit `validation` or `scenario_input` roles as specified by committed protocol. Record immutable import IDs and hashes.
4. Bind snapshots to approved ontology and policy fingerprints.
5. Create exact governed input envelope and deterministic projection defined by M3.
6. Run engine only after M3 is confirmed and only within committed validation protocol, split, seed, model and run count.
7. Verify engine consumed exact input manifest and resume rejects any changed input.
8. Generate reports with exploratory/simulated labels and complete provenance.
9. Compare with predeclared baseline and metrics only after outputs are frozen and held-out labels are released to evaluator.

**Pass criteria**

- Exact source files, import IDs, field allow-lists, schema/binding/ontology/policy fingerprints and manifest hashes are traceable into run record.
- No unapproved field, import, data role, row, source or later-period label is consumed.
- Simulation engine is reached only through approved M3 adapter.
- Run and report provenance are complete and immutable; resume fails on any changed input.
- Output is labelled exploratory simulation; no validated-prediction mode or observed-outcome claim is enabled.
- Evaluation uses protocol's exact time split, baseline, metric and uncertainty procedure; all failures remain logged.

**Fail criteria:** engine receives raw/unapproved data, latest snapshot, missing manifest or mismatched hash; held-out labels leak; output cannot be mapped to declared target; report omits provenance; or a result is presented as validated prediction.

**Separate authorization note:** owner's 12:52 approval covers validation simulation runs only on the three named public benchmark packages, after M2, M3 and protocol commitment. It does not approve P2D/NCC/Nutrivance runs, arbitrary extra datasets, other real/personal data, connectors, credentials, write-back or changing `VALIDATED_PREDICTION_ENABLED`. Exact `agora/sim/**` edits still require owner's separate written approval naming the files after Claude's design.

### Area 6 — End-to-end provenance trace

**Purpose:** prove every final report/output can be traced back through exact run, input, approval and audit evidence.

**Procedure**

For each run, reconstruct trace from report ID/hash to run ID, repository SHA, scenario hash, exact import ID, source file hashes, canonical input manifest/hash, schema, binding, ontology, transformation policy, data role, decision ID/version/fingerprint, principal references, approval events, audit chain ID/head, anchor sequence/head, adapter version, seed and model/backend configuration.

**Pass criteria**

- Every link resolves to one exact immutable record; no `latest` references.
- All hashes recompute correctly.
- Decision and approval evidence match exact input/run scope and version.
- Audit timeline and anchor verify; reconciliation reports no unexplained gap.
- Report label, provenance and metric calculation match frozen protocol.
- Independent reviewer can reproduce trace without access to raw personal data or secrets.

**Fail criteria:** missing/mismatched link, overwritten record, unanchored event, stale approval, raw data in provenance, unexplained report number or inability to reproduce trace.

## 4. Global test controls

- Use isolated temporary projects and local stores. Preserve a fresh project for every dataset/split/seed.
- Capture stdout, stderr, exit codes, timestamps, hashes and environment for every command.
- Do not delete failed or denied run records.
- No real P2D data exists or is assumed; P2D remains pre-launch.
- No NCC or Nutrivance data, projects or historical runs are used.
- No network, connector, credential, cloud service or external write-back.
- No test changes `VALIDATED_PREDICTION_ENABLED`; it remains `False`.
- No M3 engine file is edited without separate written owner approval naming exact `agora/sim/**` paths.
- No simulation run begins before M2/M3 confirmation and protocol commitment.

## 5. Evidence bundle

| Evidence | Required contents |
|---|---|
| Build | Exact main SHA, merged PRs, CI run IDs, clean-checkout/install log, OS/Python/dependency lock |
| Scope | M2/M3 confirmation log references, owner approvals, exact simulation-tree file list |
| Dataset | Source/version/licence, source citation, field allow-list, exclusions, file hashes, date coverage |
| Input | Import IDs, schema/binding/ontology/policy fingerprints, canonical manifest and hash |
| Run | Run ID, scenario hash, adapter version, model/backend, seed, configuration, engine-invoked flag |
| Governance | Decision IDs/versions, principals, approval references, audit chain/head, anchor verdict, reconciliation findings |
| Security | Red-team attack IDs, expected/observed codes, before/after hashes, outside-root sentinel checks |
| Output | Report ID/hash, exploratory label, provenance trace, baseline and predeclared metrics |
| Evaluation | Evaluator SHA, test-label release reference, coverage, metrics, 95% intervals, exclusions and failed attempts |
| Sign-off | Independent reviewer, Claude's milestone/result log entry, owner approval references for any separately gated action |

## 6. Final stop rules

Stop the whole test if any run uses a non-approved dataset, personal/sensitive field, P2D/NCC/Nutrivance data, credential, connector, network access, external write-back, unapproved simulation-tree file, uncommitted protocol, missing provenance envelope, changed held-out label, failed anchor or unexpected partial write.

Do not resume by changing a split, seed, model, dataset, target, field allow-list or metric after seeing results. Freeze a new protocol version first and treat it as a new evaluation.

A completed test plan is not a completed test. A passing integration test is not evidence of forecast accuracy or production readiness. Only Claude's explicit collaboration-log entry may declare M2/M3 reached or report validation results.

**No test, simulation, calibration, backtest, forecast, data import or rehearsal was executed to prepare this plan.**
