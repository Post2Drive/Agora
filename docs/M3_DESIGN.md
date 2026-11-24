# M3 Design — Governed Scenario Input to the Simulation Engine

**Status:** Design/implementation record assessed against current main `ace85f6483ef0d20a1a3c916311232a81d7d05f9` after PR #216 merged from exact head `7ab7adab0753207b51580ceced0ba155202128be`; merge commit `ace85f6483ef0d20a1a3c916311232a81d7d05f9`, exact-head workflow `45391932296` passed 4/4. #216 changed four paths: `agora/sim/engine.py`, `agora/validation/election_harness.py`, `agora/showcase/freight_pricing.py`, and `tests/test_engine_governed_input.py`; only `agora/sim/engine.py` is under `agora/sim/**`, the only currently owner-approved sim path. It adds `input_origin` and `synthetic_demo` labels, but the merge commit explicitly says they are not a security boundary and same-process callers can imitate both. #219 is an open/draft design-only PR at head `cc1466e03512b700231220343297d9a52174d40d`, one path `docs/PRODUCT_BOUNDARY_AND_INTEGRITY_DESIGN.md`, with no CI run; it proposes signed receipts, signed releases and hosted-first delivery, but no code or key-management decision is implemented. Its owner-direction statement is Claude-authored and is not separately present in the latest six Notion entries; treat it as pending owner confirmation. #212 remains open/draft, one docs path, 1 ahead/7 behind main; exact-head CI `45311657870` passed 4/4. #210 merged docs-only at `58695236b79b55233d46c096c27cf7e479097beb` from head `2058e9b798d0b2633fff49db41a7e850fac6ae3f`, CI `45387958484` passed 4/4. Frozen v0.1/v0.2 protocol artifacts and the 15-row manifest remain unchanged. Full run configuration, the separate seven state-year exclusions and first-calibration-failure disposition remain outstanding. Package A is NOT EVALUABLE; Package R/M5 is dropped; M3 remains unreached.

**Post-#197 / #198 / #199 / #205 / #207 / #211 review note:** #197 adds `read_stable_bytes()` and `open_ro_snapshot()` for held-descriptor, identity-checked read-side snapshots used by audit-chain, anchor and run-record/seal verification; exact-head CI `45167913607` passed 4/4. This does not harden `AuditChainStore` writer opens, which remain path-based. Python <3.11 fails closed because SQLite `Connection.deserialize` is unavailable. #198 adds a Principal-bound authorization receipt and verifies it in the engine; exact-head CI `45170449040` passed 4/4. #199 adds adapter-origin provenance and rejects a hand-built Principal with no origin marker; exact-head CI `45173316190` passed 4/4. Residual: the module sentinels `_ISSUED` and `_MINT` are accessible to Python code in the same process, `AuthorizationReceipt.__init__` accepts the sentinel, and `object.__setattr__` bypasses its immutability guard. The caller-supplied fixture table is test-only; no production identity adapter exists. The CLI remains default-deny because `_governed_policy()` returns `None`. The v0.1 protocol file remains byte-identical at `6d06088cf7954bd41f003544f5ec61675389bcc1`. Its in-file “Draft preregistration only” header is historical and preserved byte-for-byte; the owner supplied the complete freeze sentence at 22:14 IST on 23 November 2026 naming protocol commit `6d06088cf7954bd41f003544f5ec61675389bcc1`, manifest SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`, and evaluator ChatGPT (separate process), and Claude recorded v0.1 frozen at that exact commit at 22:16 IST. Treat the external owner/Claude attestation as governing status; do not edit the frozen protocol or its historical header without a separately approved versioned freeze. The freeze authorizes no run, dataset import or flag change. The 15-row manifest was finalized separately by #203 (merge `3872f2401a8c6c6de097ad82a701414e8b1a26c9`, SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`) before v0.2 freeze. The freeze authorized no run. The additive v0.2 run specification was merged and is now FROZEN at `3fc4bc4f9b06e90b4602169de4cc13534a403ca0` under the owner's pre-approval; Claude reports the frozen Package E calibration, validation and test-evaluate stages complete; the 2016 held-out result is a loss to both baselines. The only explicit owner-approved `agora/sim/**` path remains `agora/sim/engine.py`.

## 1. M3 target contract (not yet an operational proof)

**Target contract:** a governed run must start from one exact, approved, immutable tabular import, with a policy check before source bytes are read; deterministic projection; a failure-atomic provenance envelope written before round 0; resume refusal on any input change; and reports that carry the trace and the EXPLORATORY label.

**Current mainline boundary:** PR #216 is now in main. `Simulation._input_origin()` classifies a package as `builder` when caller-supplied manifest fields match the builder shape, or `synthetic_demo` when the package includes `synthetic_demo is True`; the value is persisted in the provenance manifest. This is a provenance label only. PR #216's own test explicitly constructs a builder-shaped manifest in-process and observes it labelled `builder`; the top-level demo marker is caller-controlled and outside the manifest hash. `_MINT` remains importable, `AuthorizationReceipt` accepts it, and `object.__setattr__` can bypass the normal immutability guard. `_verify_governed()` still checks the receipt but does not re-run `build_scenario_input()`/`enforce_policy()`. Direct same-process construction remains forgeable; the CLI remains default-deny because `_governed_policy()` returns `None`. PR #219 proposes signed receipts and signed releases, but is design-only; key custody, rotation/revocation, nonce replay, clock, trust-list, independent release verification and hosted tenant-isolation decisions remain open. No production issuer or release verifier exists. Treat `input_origin` as diagnostic, never as authenticated origin or a fresh policy allow.

`VALIDATED_PREDICTION_ENABLED` stays `False`; no connectors, credentials, network, write-back, real or personal data.

## 2. Findings from live code that shape the design

- `Simulation.prepare()` (`engine.py`) builds the world from `population.build(self.sc)`. The population is driven by
  `Scenario.segments` (`share`, `stance_mean`, `stance_sd`, `stubbornness`, `activity`, `influence`, `openness`) plus counts.
  So the natural projection target is a **derived Scenario** (segments), not a change to `population.py` or `world.py`.
- Resume compares only a 16-hex `scenario_hash` and `--force` bypasses it. A governed run must not be forceable past its envelope.
- Run metadata lives in `Store.set_meta/get_meta`; it is the natural place for the append-once envelope.
- `cli.py` imports the engine lazily; pilot/data paths are engine-free. Must stay so.
- `agora/pilot.py` already builds the envelope shape (`RUN_PROVENANCE_SPEC.md`); reuse its canonical-manifest/hash code.

## 3. Owner-approved `agora/sim/**` edit scope (implemented in #171)

| Path | Edit | Reason |
|---|---|---|
| `agora/sim/engine.py` | Add optional `governed_input` argument to `Simulation`; in `prepare()` (a) verify envelope, (b) persist it in `Store` meta before `write_population`, atomically with it, (c) on resume re-verify stored envelope == requested and ignore `--force` for governed runs; legacy runs unchanged. | Only place the lifecycle boundary exists. |

**Explicitly NOT in scope:** `agora/sim/population.py`, `world.py`, `llm_agent.py`, `memory.py`, `opinion.py`,
`timing.py`, `platforms/**`. The projection is a pure function outside the tree that returns a derived `Scenario`;
`population.build` consumes it unchanged. If implementation proves another sim file is needed, I stop, revise this
design, and ask for a new named go. (This is narrower than ChatGPT's proposal, which listed population.py and a conditional world.py.)

## 4. Non-sim scope (Claude code PRs, no owner sim-go needed but same review/CI rules)

1. New `agora/scenario_input.py`: `build_envelope(project, import_id, binding, policy, scenario)` and
   `project_segments(envelope, snapshot) -> Scenario` (pure, deterministic, allow-listed columns, bounds, stable ordering,
   explicit assumption register; no inference of weights/behaviour without a declared mapping). Policy and anchor checks run
   before the snapshot is opened (reuse `ontology/binding.py` protected path).
2. `agora/cli.py`: `run --governed-input <import_id> ...` (exact id; `latest` rejected); lazy engine import kept.
3. `agora/report/*`: carry envelope fields, EXPLORATORY SIMULATION label; block export if envelope missing/inconsistent.
4. Docs: update `RUN_PROVENANCE_SPEC.md`.
Order: (4.1) adapter + tests with no engine edit; (4.2 after named go) engine.py; (4.3) CLI/report.

## 5. Tests and mutation proofs (each must fail when the guard is removed)

1. Policy denied -> snapshot file never opened (spy on open).
2. `latest`/path/unknown import id rejected; changed source bytes rejected.
3. Projection deterministic: same input -> same projection hash; reordered rows -> same hash; unknown/unmapped column, out-of-bound value, null violation, prohibited sensitivity class -> reject.
4. Envelope written before round 0; simulate crash after envelope/before population -> no run that looks valid; crash after -> run complete or absent (single transaction).
5. Resume identical -> ok; changed import/bytes/manifest/schema/binding/ontology/policy/scenario -> refuse, original envelope byte-identical; `--force` does not bypass.
6. Legacy run (no envelope) cannot resume through governed path; not silently upgraded.
7. Report/export without or with altered envelope -> blocked; label present; `VALIDATED_PREDICTION_ENABLED` is False and unchanged (AST/value check).
8. No network/connector import, no writes outside project root, fake LLM backend only in tests (no model call).
Mutations: remove policy pre-check, remove hash compare, make envelope write non-atomic, let `--force` skip, drop label — each flips a test red.

## 6. Rollback

Governed path is opt-in (`governed_input` default `None`); legacy path is byte-for-byte the old code path.
Rollback = revert the single engine.py PR; adapter, CLI flag and report fields become inert. No data migration; envelopes are append-only metadata in per-run stores.

## 7. Acceptance gates

As ChatGPT's list (12 gates) for the initial governed-engine implementation: exact-head CI 4/4, full suite green, only `engine.py` touched under `agora/sim/**`, and `VALIDATED_PREDICTION_ENABLED=False`. The earlier no-benchmark-run boundary was subsequently superseded by the owner's conditional approval for one offline Package E benchmark on approved public datasets after v0.2 freeze; Claude reports that run completed with the mock backend and crowd agents only. This does not establish production/operator readiness, validated prediction, or permission for any additional run. No customer/personal data, production identity, LLM-agent run, network access or write-back is authorized.

## 8. Owner decision and remaining gates

**Owner decisions and scope:** at 05:54 IST on 23 November 2026, the owner approved the initial `agora/sim/engine.py` slice implemented in #171. Later, the owner delegated design choices for validation quality to Claude; Claude then recorded the A–D design proposal. The owner explicitly accepted Claude's written 23 November A–D design approval in the owner's chat message. This records acceptance of the A–D design decisions, not a grant of additional code-path authority. The only explicit owner approval for an `agora/sim/**` path remains `agora/sim/engine.py`; no additional `agora/sim/**` path is authorized.

**Still blocked:** M3 is not declared reached; Claude's exact canonical declaration is absent. PR #216 merged at `ace85f6483ef0d20a1a3c916311232a81d7d05f9`, but its origin labels are not authorization and the direct-constructor receipt bypass remains. PR #219 is a design-only proposal for signed receipts/releases and hosted delivery; owner confirmation, key-custody decisions and exact-path approvals are outstanding. Production identity/policy adapter remains absent and CLI remains default-deny; `VALIDATED_PREDICTION_ENABLED=False`. The separate seven state-cycle exclusions and first calibration silent-exit/partial-output disposition remain undocumented; full run-level provenance remains incomplete. Package A is NOT EVALUABLE and Package R/M5 is dropped.




## 9. Post-merge review findings and current operator boundary

The merged slices improve the implementation boundary but do not yet establish an operator-usable approved workflow:

- #198 adds an exact-type Principal-bound authorization receipt, verified by the engine before governed execution. #199 adds an adapter-origin marker and rejects hand-built Principals that do not carry it. Both have exact-head CI 4/4.
- **Residual in-process trust limitation:** Python code in the same process can import the module-private `_ISSUED` and `_MINT` sentinels. A caller can pass `_MINT` to the public `AuthorizationReceipt` constructor, and `object.__setattr__` bypasses the receipt's `__setattr__` guard. The synthetic adapter also accepts a caller-supplied fixture table. Treat this adapter as test-only, not production authentication; a real process/adapter trust boundary is absent.
- The CLI's `_governed_policy()` still returns `None`; the policy-required scenario-input builder therefore denies before opening snapshot bytes. Do not inject a permissive callback or bypass this gate.
- #197 replaces several read-side path reopen operations with held-descriptor snapshots and file-identity checks. `AuditChainStore` writer opens remain path-based, so write-side path replacement is not covered. Python before 3.11 fails closed rather than reopening by path because SQLite `Connection.deserialize` is unavailable.
- Hash semantics are resolved in #178: `base_scenario_hash` is captured from `scenario.yaml` before projection; `projected_scenario_hash` is separate and bound to `projection_hash`.
- The CLI form remains `agora run PROJECT --governed-input IMPORT_ID --binding FILE --pack FILE --mapping FILE`, but it is not currently an executable operator workflow because the production policy source denies. Do not run the legacy `agora run PROJECT` path as a substitute.
- The owner's conditional run go (“Go, once v0.2 is frozen”) was limited to the frozen Package E stages. Claude reports calibration/validation/test-evaluate completed once; no extra package, data, seed, configuration or rerun is authorized. The 15-row hash-only manifest remains unchanged. PR #213 merged the output/log bundle and SHA256SUMS into main. ChatGPT independently verified the SHA-256 and byte count of all nine PR #213 repository artifacts against SHA256SUMS; all matched.  The nine non-sensitive PR #213 output/log artifacts and SHA256SUMS are merged to main; ChatGPT independently verified all nine byte counts and SHA-256 values against SHA256SUMS, so the byte-counted output inventory is complete. Full run-level configuration/provenance and the first calibration failure's exit status, logs, partial-output inventory/hash/disposition and restart rationale remain outstanding. The separate seven state-cycle exclusions remain unenumerated. Claude reports the 2016 labels were opened once only after the output seal matched; ChatGPT did not receive or access held-out labels and did not recalculate metrics. `VALIDATED_PREDICTION_ENABLED=False`.

These are completion gates, not permission for ChatGPT to edit source. The owner-approved `agora/sim/engine.py` path remains the only approved `agora/sim/**` path; no source changes are included here.

**#205 Package E addition, #211 label-gate correction and #214 test follow-up:** #205 exact-head CI `45222866705` passed 4/4. #211 moved the `test_outputs.json` SHA-256 check before MEDSL verification/loading; exact head `1d90528de82d2a08f24ad38cf6c7c5c7bdd15eb0`, merge `2730903234196e9b38914ccb0fcab2de4e6c16ca`, CI `45229437458` passed 4/4. #214 merged missing-seal negative and matching-seal positive controls at `b111a4f918710f41650c659c40cad593419b02af`; exact head `e6f48ed9a6305d9f325c99099bc1c653f274c9a5`, exact-head CI `45313425335` passed 4/4. Review finding: missing-seal test instruments `load_outcomes` but not MEDSL `sha256_file`; positive test proves one load and result creation but not explicit test-output-read-before-MEDSL-hash ordering. Recommend those assertions as follow-up. ChatGPT did not run code or tests.


## 10. Owner-delegated design choices — implementation status and remaining gates (23 November 2026)

The owner delegated the identity and TOCTOU design choices for the stated objective of unbiased, genuine validation. These choices are recorded here as design decisions only; they do not establish implementation completion, protocol freeze, M3 reached or permission to run data.

### 10.1 Identity and authorization receipt

- **Validation identity:** use the existing synthetic-fixture Principal only for strictly local validation runs against owner-approved public datasets. No real people, personal data, private operational data or production identities are in scope.
- **Authorization proof:** the direct engine path must require an opaque, Principal-bound authorization receipt minted only after a successful allow decision by the trusted synthetic-fixture adapter. Bind it to issuer, subject, role, expiry and the exact project, import ID, binding ID, dataset/schema and scenario/manifest hashes. Revalidate allow, scope and expiry before Store construction, provenance writes or population creation.
- **Untrusted inputs:** reject missing, forged, wrong-type, denied, expired, cross-project, wrong-import/binding and tampered-package receipts. A caller-supplied mapping, plain dictionary or self-asserted allow flag is not proof.
- **Production boundary:** keep production CLI fail-closed. _governed_policy() continues to return None; do not add a permissive production fallback or weaken the denial. A production identity adapter requires a separate approval and design.
- **Implementation status:** #198 implements the Principal-bound receipt across `agora/principal.py`, `agora/scenario_inputs.py`, `agora/cli.py` and the already-approved `agora/sim/engine.py`; #199 adds the adapter-origin marker in `agora/principal.py`. Exact-head CI passed 4/4 for both. The owner confirmed that the synthetic-fixture Principal is acceptable for strictly local validation on approved public datasets only; production CLI remains blocked/default-deny. These merges do not authorize any additional `agora/sim/**` path; `agora/sim/engine.py` remains the only owner-approved path. Residual: the in-process `_ISSUED`/`_MINT` sentinels are reachable, receipt construction accepts `_MINT`, and `object.__setattr__` bypasses the setter. The caller-supplied fixture adapter is test-only; production identity is absent and CLI policy remains `None`.

### 10.2 TOCTOU threat-model decision

Concurrent local path replacement is **in scope** for the synthetic and validation path. #197 merged a read-side implementation that reads audit-chain, anchor and run-record/seal SQLite snapshots through a held descriptor, checks file identity before and after reading, and does not reopen the verified database by pathname. Exact-head CI `45167913607` passed 4/4. This is not full writer-side race resistance: `AuditChainStore` still opens its SQLite database by path. Python <3.11 fails closed because `sqlite3.Connection.deserialize` is unavailable; it must not fall back to a path reopen. Any additional race-hardening slice must name its exact files and preserve the existing owner path approvals.

### 10.3 Validation controls and remaining gates

The selected election window remains training 2000/2004/2008, validation 2012 and held-out test 2016; use the latest FiveThirtyEight daily state average on or before each cutoff and report previous-election state-margin persistence separately. MEDSL uses TOTAL where present, otherwise sums modes; never double-count both. Ember is not required because Package A is NOT EVALUABLE; Package R/M5 is dropped. The frozen v0.1/v0.2 splits, baselines, metrics, uncertainty, no-test-tuning, one-run and stop rules remain unchanged. v0.2 remains frozen at `3fc4bc4f9b06e90b4602169de4cc13534a403ca0`; run-spec SHA-256 `ca87e4f47f39b1112e4ef808e949a49b1c87720f5e6576032acbba8723b5987b`. Claude reports calibration k=0.24, a 2012 MAE tie with worse RMSE and a 2016 loss to published average and persistence. ChatGPT independently fetched and verified the exact bytes and byte counts of all nine non-sensitive PR #213 output/log artifacts against SHA256SUMS; all matched. ChatGPT did not access raw source CSVs or held-out labels and did not recalculate metrics. The 2016 output has one no-poll cutoff exclusion (District of Columbia, 2016-10-11); the 2012 output has two (District of Columbia and Idaho, 2012-10-09). The separate seven state-cycle exclusions, full run configuration and first calibration failure disposition remain outstanding. No additional run/data is authorized. M3 remains unreached; `VALIDATED_PREDICTION_ENABLED=False`.
