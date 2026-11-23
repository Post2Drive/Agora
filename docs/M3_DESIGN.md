# M3 Design — Governed Scenario Input to the Simulation Engine

**Status:** Design and implementation record assessed against main `4a0607f8946e32ef828b47183099ead4f8ae2bd7` (23 November 2026). The owner approved only `agora/sim/engine.py` under `agora/sim/**`; #171/#178 implement that engine scope, while #172/#173 and #163/#164 provide the CLI/projection slices. RT06 read-side SQLite snapshot hardening #197 merged at exact head `5d67cb4ceed8200a9a952b05ae1db9a58c3b0ba6` (merge `5cbe4cfbb82039543d408ab5c67e045e17e10a99`, CI `45167913607`, 4/4). Principal-bound receipt #198 merged at exact head `d3a8435bbabc28a1e488d87b752b1350b99c687d` (merge `4a55f2efd44da7aea54adda6ca7787471dd97cba`, CI `45170449040`, 4/4). Adapter-origin check #199 merged at exact head `851bbf1a217f018695133ee9c42f1c538fa088f0` (merge/current main `4a0607f8946e32ef828b47183099ead4f8ae2bd7`, CI `45173316190`, 4/4). Docs PR #196 merged at exact head `f9d34afa5914ee1cd2ccfd39a722fbb791ac4591` (merge `34e5cc39b2bb9f53ca6be0dc057de53e5aa5532c`, CI `45170530846`, 4/4; seven docs-only paths). The owner explicitly accepted Claude's A–D design decisions, but that acceptance does not widen path-level authorization: `agora/sim/engine.py` remains the only approved `agora/sim/**` path. The receipt and adapter-origin slices are merged, but their in-process sentinels remain reachable and `object.__setattr__` can bypass receipt immutability; the fixture adapter accepts caller-supplied definitions and is test-only. There is no production identity adapter, and `_governed_policy()` remains `None`, so the production CLI denies before snapshot bytes are opened. #197 hardens read-side SQLite snapshots; AuditChainStore writer opens remain path-based and Python <3.11 fails closed. The owner-named evaluator is ChatGPT in a separate process, but the evaluator's restricted scope, output custody and label-release boundary are not established. The owner approved five protocol design values on 23 November (B=2000, bootstrap seed 20261123, percentile interval, one preregistered seed per configuration, temperature 0 with cache on); they take effect only after merge and a complete freeze sentence. P2D PR #5 remains open/draft/unmerged at `b06b29cb2071f048f0c234f65c1014ea4677d33d`; its 12 FiveThirtyEight CSVs and 4,679-byte manifest SHA-256 `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb` are reported source/destination verified by Claude. The owner approved MEDSL mirror `mathis-group/cas-201-data-project@1358bc6047f0c22989d37fa64ac03ee755bd17e7` (10,222,208 bytes; Claude-reported SHA-256 `9299583148f5f8264baf50b5d929c260699c46d915909b13ea3c3850918946f8`; dataset CC0 1.0) and Ember mirror `Awes0mer/fuel-cars-pollution@2c21f1edced7aae884314ebc28c89ab212f30563` (7,695,642 bytes; Claude-reported SHA-256 `76e241d07d2086477ef0279d4ce20cd6a02c7869b5152ecc016bf132d2734fb2`; 16-Nov snapshot, data CC BY 4.0). Claude reports both raw files fetched and verified in its workspace only; ChatGPT inspected public repo trees/metadata, not raw bytes. Neither file is committed to P2D or Agora. The selected polls window is 2000–2016 with 538 published averages and the MEDSL `TOTAL`-mode rule; 2020/2024 are out of scope and the uncorrected 2024 file is excluded. Ember uses monthly rows only; quarterly rows are excluded. M5 is the only remaining owner download/terms decision (acquire under Kaggle rules or drop retail). The complete all-package manifest is not committed. The freeze sentence still contains literal `<sha>`; the protocol remains draft and no dataset run is authorized. The run approval is dormant. No dataset has been run; M3 remains unreached and only Claude's exact collaboration-log confirmation can declare it reached. `VALIDATED_PREDICTION_ENABLED=False` remains mandatory.

**Post-#197 / #198 / #199 review note:** #197 adds `read_stable_bytes()` and `open_ro_snapshot()` for held-descriptor, identity-checked read-side snapshots used by audit-chain, anchor and run-record/seal verification; exact-head CI `45167913607` passed 4/4. This does not harden `AuditChainStore` writer opens, which remain path-based. Python <3.11 fails closed because SQLite `Connection.deserialize` is unavailable. #198 adds a Principal-bound authorization receipt and verifies it in the engine; exact-head CI `45170449040` passed 4/4. #199 adds adapter-origin provenance and rejects a hand-built Principal with no origin marker; exact-head CI `45173316190` passed 4/4. Residual: the module sentinels `_ISSUED` and `_MINT` are accessible to Python code in the same process, `AuthorizationReceipt.__init__` accepts the sentinel, and `object.__setattr__` bypasses its immutability guard. The caller-supplied fixture table is test-only; no production identity adapter exists. The CLI remains default-deny because `_governed_policy()` returns `None`. The owner's freeze sentence is incomplete (literal `<sha>` placeholder); the protocol remains draft and the run approval dormant. The only explicit owner-approved `agora/sim/**` path remains `agora/sim/engine.py`.

## 1. M3 target contract (not yet an operational proof)

**Target contract:** a governed run must start from one exact, approved, immutable tabular import, with a policy check before source bytes are read; deterministic projection; a failure-atomic provenance envelope written before round 0; resume refusal on any input change; and reports that carry the trace and the EXPLORATORY label.

**Current mainline boundary:** #198/#199 now carry and verify a Principal-bound receipt and reject hand-built Principals that lack adapter-origin provenance. This closes the earlier missing-receipt and trusted-issuer-only checks, but not the in-process trust boundary: `_ISSUED`/`_MINT` are importable module objects, a caller can pass the sentinel to the public receipt constructor, and `object.__setattr__` can mutate receipt fields. The fixture adapter accepts a caller-supplied fixture table and is not production authentication. The production CLI's `_governed_policy()` still returns `None`, so it denies before snapshot bytes are opened. #197 hardens read-side SQLite snapshots only; writer opens remain path-based and Python <3.11 fails closed. The end-to-end governed-run contract is therefore not demonstrated on main. Not proved: that outputs match reality (Track B, under `VALIDATION_PROTOCOL.md`).

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

As ChatGPT's list (12 gates) with this narrowed scope: exact-head CI 4/4, full suite green, only `engine.py` touched under `agora/sim/**`, `VALIDATED_PREDICTION_ENABLED=False`, no run of the engine on any real dataset (tests use the fake backend and synthetic fixture only).

## 8. Owner decision and remaining gates

**Owner decisions and scope:** at 05:54 IST on 23 November 2026, the owner approved the initial `agora/sim/engine.py` slice implemented in #171. Later, the owner delegated design choices for validation quality to Claude; Claude then recorded the A–D design proposal. The owner explicitly accepted Claude's written 23 November A–D design approval in the owner's chat message. This records acceptance of the A–D design decisions, not a grant of additional code-path authority. The only explicit owner approval for an `agora/sim/**` path remains `agora/sim/engine.py`; no additional `agora/sim/**` path is authorized.

**Still blocked:** no validation run until the direct-engine policy trust boundary is closed, an approved identity/policy source is available and fail-closed, the validation protocol is explicitly approved and frozen in a merged documentation commit, and the owner accepts the selected benchmark files with licence/version/hash records in the owner-controlled private repository. Claude reports the 12-file FiveThirtyEight package verified and reports the owner-approved MEDSL and Ember mirror files fetched/hash-verified in its workspace, but the two mirror files are not committed to P2D; P2D PR #5 remains unmerged, M5 acquire-or-drop remains undecided, and the complete all-package manifest is incomplete. The selected poll window is 2000–2016; MEDSL mode and Ember snapshot rules are recorded in the draft protocol. The CLI remains default-deny because `_governed_policy()` returns `None`; do not weaken that denial. No dataset or simulation run is authorized by this design. `VALIDATED_PREDICTION_ENABLED` remains `False`.


## 9. Post-merge review findings and current operator boundary

The merged slices improve the implementation boundary but do not yet establish an operator-usable approved workflow:

- #198 adds an exact-type Principal-bound authorization receipt, verified by the engine before governed execution. #199 adds an adapter-origin marker and rejects hand-built Principals that do not carry it. Both have exact-head CI 4/4.
- **Residual in-process trust limitation:** Python code in the same process can import the module-private `_ISSUED` and `_MINT` sentinels. A caller can pass `_MINT` to the public `AuthorizationReceipt` constructor, and `object.__setattr__` bypasses the receipt's `__setattr__` guard. The synthetic adapter also accepts a caller-supplied fixture table. Treat this adapter as test-only, not production authentication; a real process/adapter trust boundary is absent.
- The CLI's `_governed_policy()` still returns `None`; the policy-required scenario-input builder therefore denies before opening snapshot bytes. Do not inject a permissive callback or bypass this gate.
- #197 replaces several read-side path reopen operations with held-descriptor snapshots and file-identity checks. `AuditChainStore` writer opens remain path-based, so write-side path replacement is not covered. Python before 3.11 fails closed rather than reopening by path because SQLite `Connection.deserialize` is unavailable.
- Hash semantics are resolved in #178: `base_scenario_hash` is captured from `scenario.yaml` before projection; `projected_scenario_hash` is separate and bound to `projection_hash`.
- The CLI form remains `agora run PROJECT --governed-input IMPORT_ID --binding FILE --pack FILE --mapping FILE`, but it is not currently an executable operator workflow because the production policy source denies. Do not run the legacy `agora run PROJECT` path as a substitute.
- The owner has not authorized a dataset simulation or validation run. The owner's one-run approval is dormant; the protocol remains draft because the freeze sentence contains literal `<sha>` and required parameter values are design-approved but not frozen. Claude reports the FiveThirtyEight 12-file sub-manifest and the owner-approved MEDSL/Ember mirror files hash-verified, but the mirror files remain in Claude's workspace only, P2D PR #5 is unmerged, M5 acquire-or-drop is undecided, and the complete all-package manifest is incomplete. Keep `VALIDATED_PREDICTION_ENABLED=False`.

These are completion gates, not permission for ChatGPT to edit source. The owner-approved `agora/sim/engine.py` path remains the only approved `agora/sim/**` path; no source changes are included here.

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

The selected election window is training 2000/2004/2008, validation 2012, held-out test 2016; use the latest FiveThirtyEight daily state average on or before each cutoff and report previous-election state-margin persistence separately. MEDSL uses the `TOTAL` row where present, otherwise sums modes; never double-count both. Ember is the owner-approved 16-Nov-2026 snapshot, monthly rows only, with quarterly rows excluded. M5 remains the only pending owner download/terms decision. The rest of the fixed splits, seasonal-naive retail baseline, loss comparisons, 95% uncertainty ranges for every metric, no-test-tuning rule, one-run-per-frozen-config rule and package stop rules remain in `VALIDATION_PROTOCOL.md` as draft controls. The owner approved B=2000, bootstrap RNG seed 20261123, percentile interval, one preregistered seed per configuration, and LLM temperature 0 with cache on. These values become effective only after they are merged into the protocol and covered by a complete freeze sentence. The owner-named evaluator is ChatGPT as a separate process limited to the frozen protocol, manifest and raw outputs; the evaluator's restricted scope, output custody and label-release boundary are not yet established. The freeze sentence's manifest field is literal `<sha>`. No dataset run is authorized. M3 remains unreached pending Claude's exact log confirmation. `VALIDATED_PREDICTION_ENABLED=False` remains mandatory.
