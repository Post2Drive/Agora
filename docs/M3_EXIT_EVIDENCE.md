# M3 Exit Evidence — Claude Milestone Declaration Checklist

**Status:** Working checklist, not a milestone declaration. Current main is `5ec1bdd62d562cb8ef2ef58d54b61d717232e4ec` after #208/#209 and #213. v0.2 remains frozen at `3fc4bc4f9b06e90b4602169de4cc13534a403ca0`; run-spec SHA-256 `ca87e4f47f39b1112e4ef808e949a49b1c87720f5e6576032acbba8723b5987b`; v0.1 protocol SHA-256 `b776948e14d6dc5c72262b3572365ebc0288fd632bc0bb13743d96fe7d8fea66`; manifest SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`. PR #213 merged at `5ec1bdd62d562cb8ef2ef58d54b61d717232e4ec`, exact head `699ab1739aad4a654ae98e339de23e8b8321d6b7`, CI `45312734872` 4/4. ChatGPT independently verified all nine output/log files against SHA256SUMS; inventory-file SHA-256 `7ac2ffece93b4c923e26d35f8b59fc24c38373d8ad515b7f7d8165ca1c9a8c7d`. 2016 output hash matches the pre-label seal. PR #214 merged at `b111a4f918710f41650c659c40cad593419b02af` from exact head `e6f48ed9a6305d9f325c99099bc1c653f274c9a5`, CI `45313425335` 4/4; two assertion-strengthening findings remain. PR #212 is a separate open Decision Cell docs draft, not an M3 implementation. Package A is NOT EVALUABLE; Package R/M5 and retail are dropped. No exact Claude M3 declaration is present; `VALIDATED_PREDICTION_ENABLED=False`.

**Package E interpretation:** The reported benchmark used the mock backend and crowd-agent simulation only; no LLM agents were used. The harness built governed packages with the synthetic-fixture Principal, not production authentication. The readout is a monotone transform of the published FiveThirtyEight average and adds no independent predictive signal. ChatGPT independently verified the nine PR #213 output/log file bytes against SHA256SUMS, but did not access outcome labels or independently recompute label-based metrics; scores remain Claude-reported. The 2012 MAE interval includes zero and RMSE is worse; 2016 MAE/RMSE lose to the published average, and MAE also loses to persistence. This is a negative result for the frozen mapping, not evidence of validated prediction, causal efficacy, observed demand or deployment fitness.

**Post-#197/#198/#199 status:** #197 RT06 read-side held-descriptor SQLite snapshot merged at exact head `5d67cb4ceed8200a9a952b05ae1db9a58c3b0ba6`, merge `5cbe4cfbb82039543d408ab5c67e045e17e10a99`, exact-head CI `45167913607` passed 4/4. #198 Principal-bound authorization receipt merged at exact head `d3a8435bbabc28a1e488d87b752b1350b99c687d`, merge `4a55f2efd44da7aea54adda6ca7787471dd97cba`, CI `45170449040` passed 4/4. #199 adapter-origin check merged at exact head `851bbf1a217f018695133ee9c42f1c538fa088f0`, merge/current main `4a0607f8946e32ef828b47183099ead4f8ae2bd7`, CI `45173316190` passed 4/4. ChatGPT docs #196 merged at exact head `f9d34afa5914ee1cd2ccfd39a722fbb791ac4591`, merge `34e5cc39b2bb9f53ca6be0dc057de53e5aa5532c`, CI `45170530846` passed 4/4 (seven docs-only paths). #197 is read-side only; AuditChainStore writer opens remain path-based and Python <3.11 fails closed. #198/#199 leave an in-process trust limitation: `_ISSUED`/`_MINT` are accessible, receipt construction accepts the sentinel, `object.__setattr__` bypasses immutability, and the fixture adapter is caller-configurable/test-only. Production CLI remains default-deny.

**Assessment base:** main `b111a4f918710f41650c659c40cad593419b02af`. #208 exact head `94d74c943591da99d9473490149cbd829809c405`, merge `f7dc73cd002d98f2e97cf609ba44b48fac26cd3d`, CI `45227646106` 4/4; #209 exact head `fa0c213eed4b5197fe7eee7635d1391fcf70b4ae`, merge `ce1c6f0e0ad74e1fe62753ec7c64631d7b5fe196`, CI `45312159080` 4/4; #213 exact head `699ab1739aad4a654ae98e339de23e8b8321d6b7`, merge `5ec1bdd62d562cb8ef2ef58d54b61d717232e4ec`, CI `45312734872` 4/4; #214 exact head `e6f48ed9a6305d9f325c99099bc1c653f274c9a5`, merge/current main `b111a4f918710f41650c659c40cad593419b02af`, CI `45313425335` 4/4. #205/#207/#211 exact-head CI remains 4/4: `45222866705`, `45225751700`, `45229437458`. #212 Decision Cell docs draft exact head `5a248f750606ac1a2db5afd9f825353fc53a3cea`, CI `45311657870` 4/4. #215 synthetic freight demo is open, three paths, no `agora/sim/**` changes; CI status pending.

## 1. Merged implementation slices

| Slice | Merged PR | Mainline evidence | Exact-head CI |
|---|---:|---|---|
| 4.1 deterministic projection | #163 | `agora/scenario_projection.py`, tests; pure projection, explicit mapping/allow-list/bounds | Confirm exact run/job evidence in Claude's log before final declaration |
| 4.1b fail-closed projection hardening | #164 | `agora/scenario_projection.py`, tests; sensitivity and mapping/hash validation tightened | Confirm exact run/job evidence in Claude's log before final declaration |
| 4.2 governed engine integration | #171 | `agora/sim/engine.py` plus tests only; optional governed input, verification, append-once provenance guard, changed-input/legacy/force refusal | Run `45089066900`, 4/4 |
| 4.3 governed CLI | #172 | `agora/cli.py` plus tests; exact import ID, binding/pack/mapping args, `--force` refusal, exit 3 on engine refusal | Run `45093439437`, 4/4 |
| 4.4 instance-row integrity | #173 | `agora/scenario_projection.py` plus tests; order-independent `instances_hash` included in `projection_hash` | Run `45096233966`, 4/4 |
| 4.6 base/projected scenario hashes | #178 | `agora/sim/engine.py` plus tests only, within the owner's named scope; original `scenario.yaml` hash is `base_scenario_hash`, separate `projected_scenario_hash` binds it to `projection_hash` | Run `45113858688`, 4/4 |
| Package E leaning + harness/driver | #205 | Optional per-option `leaning` mapping in `project_segments`; staged election harness and driver; adds `docs/VALIDATION_RUN_SPEC.md` as a draft v0.2 candidate. No `agora/sim/**` path changed. | Exact head `9d5c466ec886b27e7c83c5c13695810cb44ed08d`, merge/current main `3fc4bc4f9b06e90b4602169de4cc13534a403ca0`, run `45222866705`, 4/4 |
| RT06 read-side SQLite snapshot | #197 | Held-descriptor read-side snapshots for audit chain, anchor and run-record/seal checks; writer opens remain path-based; Python <3.11 fails closed | Run `45167913607`, 4/4 |
| 4.7 Principal-bound authorization receipt | #198 | Receipt minted after Principal-bound allow and revalidated in the engine; in-process sentinel and `object.__setattr__` limitations remain | Run `45170449040`, 4/4 |
| 4.7a adapter-origin provenance | #199 | Hand-built Principals without adapter-origin marker denied; same-process sentinel access remains possible | Run `45173316190`, 4/4 |

For #171–#173 and #178, 4/4 means Ubuntu/Windows × Python 3.11/3.12 jobs all completed successfully. Claude's log reports 15 new engine tests, 7 CLI tests, 2 row-hash tests and four hash-split regression cases, plus local full-suite/mutation results; ChatGPT did not run or independently reproduce those local tests. For #178, exact head `a620feb98d342250e29ded132781630fcb31f395` passed run `45113858688` 4/4. Its diff changes only `agora/sim/engine.py` and `tests/test_engine_governed_input.py`; the sole `agora/sim/**` path remains the owner-approved `engine.py`. Confirm exact merge-head and workflow evidence for every implementation PR; do not rely on a branch-head result if the merged SHA differs.

**Supporting validation utility (not an M3 engine slice):** #175 adds pure benchmark metrics/baselines in `agora/validation/benchmark_metrics.py`; exact PR-head CI `45105990141` passed 4/4. Follow-up #176 hardens boolean, date and window validation and pins the official M5 RMSSE scale convention; exact-head CI `45110601617` passed 4/4. #179 and #180 add strict metric/seed guards. #205 adds the Package E harness/driver and optional `leaning` projection; exact-head CI `45222866705` passed 4/4. #211 corrects test-evaluate ordering so the output seal is checked before MEDSL hashing/loading; exact head `1d90528de82d2a08f24ad38cf6c7c5c7bdd15eb0`, merge `2730903234196e9b38914ccb0fcab2de4e6c16ca`, exact-head CI `45229437458` passed 4/4. The merged #211 test covers wrong-seal no-read only; missing-seal negative and valid-seal positive-control tests remain required before held-out label release. These supporting utilities do not declare M3 reached.

**Documentation evidence:** ChatGPT docs PR #181 merged at exact head `73a4947efc1beb94b55718568a1d453d579bae1b` (merge commit/main `9dad1c8f9ab9ccc3c73aee76403cecab222d25e6`); exact-head CI run `45122674011` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. Its five changed paths were exclusively `docs/**`. This is documentation evidence only; it does not close the policy-authorization, validation-protocol approval or dataset-register gates.

**Subsequent mainline security and documentation evidence — 23 November 2026:**
- Track A PR #183 merged at exact head `0f870e22aad3d2496a5da872c21c5871106e262d`; exact-head CI `45126668732` passed 4/4. It adds static symlink/reparse-point refusal for audit chain, anchor and lock paths. This does not prove resistance to concurrent path replacement; that TOCTOU boundary remains conditional on the owner's threat-model decision.
- Backup RT05b PR #186 introduced the run-record/seal checks (exact head `b50e1e3f6386e6762de83c08023721d7882a720e`, run `45137276771`, 4/4). Follow-up RT05c PR #189 merged at exact head `21b540ee91cbfb47335156c8f2c2510b1b4d7d45`, merge `757da519f7af2c75a515ca42c6d23015d9e47123`, exact-head CI `45141079904` passed 4/4; it closes missing-record, status-plus-run-ID downgrade and malformed-ID cases for backup verification/restore. RT05d PR #192 merged at exact head `bdf13a0663e5498c9d2e857817769985a8419e94`, merge/current main `3e55e5505cda38a2ccfdc93a3e9996120ebb659e`, exact-head CI `45150068645` passed 4/4; it adds strict source-record/seal preflight before destination creation/copy and re-checks copied bytes before publication. The source-side backup preflight gap is closed on main. The owner-gated path-based SQLite reopen TOCTOU boundary remains; see `RUNG_STATUS.md`.
- Dataset download guide and M3 documentation/exit checklist were included in ChatGPT docs PR #174, merged at exact head `e231961494a849d092c45a9a9377855fe30f188b` (merge commit `aeb9ab08046268674ef7c848f78ad17fb2002738`); exact-head CI `45107961493` passed 4/4. Ten changed paths were all under `docs/**`.
- Follow-up ChatGPT docs PR #188 merged at exact head `3704728a9623365c7c7e2dd7b736cd2d53fcd175` (merge `a2473cf1bd196e84fdc6301152c30b7ac94f1bd1`); exact-head CI `45138934878` passed 4/4. Five changed paths were all under `docs/**`.
- Latest ChatGPT docs PR #191 merged at exact head `02a88463529559009adec76c052be94621aa557e` (merge `705fe5cfa157b36fd75c93a141afe39255c08b65`); exact-head CI `45148838308` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. Six changed paths were exclusively under `docs/**`; it refreshed the M3 evidence and the owner-controlled private-repository handoff.

These supporting security, metrics and documentation merges do not resolve the production identity/policy boundary, do not freeze the validation protocol, and do not authorize dataset acquisition/use or a simulation/validation run.



## 2. Scope and safety evidence

- [ ] Review changed-file lists for #163/#164/#171/#172/#173/#178 and confirm no unauthorized path under `agora/sim/**` was edited. #171 and #178 touch only the owner-approved `agora/sim/engine.py`; #172/#173 and projection slices remain outside `agora/sim/**`.
- [ ] Confirm the default `governed_input=None` path remains compatible and the legacy run path is not silently treated as governed.
- [x] Claude reports that the single Package E calibration/2012 validation/2016 test-evaluate run occurred under the owner's conditional go after v0.2 freeze; no additional package, seed, configuration or rerun was authorized. This is operator-reported authorization/status, not independent raw-output verification.
- [ ] Confirm `VALIDATED_PREDICTION_ENABLED=False` remains unchanged.
- [ ] Confirm no real/personal/customer data, credentials, connectors, network fetches or write-back were introduced.

## 3. Blocking correctness and trust-boundary findings

These are not waived by merged PRs or green CI:

Resolved by #178: `base_scenario_hash` is captured from the original `scenario.yaml` before projection; `projected_scenario_hash` is separate and bound to `projection_hash`. Exact-head CI passed 4/4.

1. **Production policy source remains absent.** `agora/cli.py::_governed_policy()` returns `None`; the policy-required scenario-input builder denies before snapshot bytes are opened. Preserve this default-deny behaviour. Do not inject a permissive callback or bypass it.
2. **Receipt/Principal provenance has a same-process limitation.** #198 requires an exact-type Principal-bound receipt and #199 rejects hand-built Principals without the adapter-origin marker. However `_ISSUED` and `_MINT` are reachable module objects in the same Python process; the public receipt constructor accepts `_MINT`, and `object.__setattr__` bypasses the setter. The synthetic fixture adapter accepts caller-supplied fixture definitions and is test-only. No production identity adapter or process-isolated trust boundary exists. Do not describe this as production authentication.
3. **Read/write path-race coverage is incomplete.** #197 adds held-descriptor, identity-checked read-side snapshots for audit-chain, anchor and run-record/seal verification. `AuditChainStore` writer opens remain path-based. Python <3.11 fails closed because `Connection.deserialize` is unavailable; no path-reopen fallback is permitted.
4. **Dataset scope and custody:** only Packages E and A remain selected. Package R/M5 was dropped by the owner and retail is untested. The 15-row Agora manifest is hash-only (SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`) and active rows remain PLANNED - NOT EXECUTED. P2D PR #5 is open/draft/unmerged with the 12 FiveThirtyEight CSVs only. Claude reports the MEDSL and Ember files were hash-verified against their pinned public sources; the 24 Nov owner/Claude direction explicitly stops their private import, so their absence from P2D is not an M3 blocker. ChatGPT did not fetch raw bytes. Package A is predeclared NOT EVALUABLE under v0.2; no raw source CSVs were committed to Agora. Claude reports the Package E harness read the approved poll/MEDSL inputs from its workspace for the authorized run.
PR #211 merged and exact-head CI passed 4/4. PR #214 exact head `e6f48ed9a6305d9f325c99099bc1c653f274c9a5` passed exact-head CI run `45313425335` 4/4. Static review of its missing-seal negative shows it instruments `load_outcomes` but not `h.sha256_file` for the MEDSL path, so it proves no label loading but not no MEDSL hash. The valid-seal positive proves one `load_outcomes` call and result creation but does not assert that `test_outputs.json` is read before MEDSL hashing/loading. These are review findings, not test results; ChatGPT did not run code or tests. This is follow-up coverage, not evidence that the already-reported test-evaluate was unsealed.

Claude must state these residuals accurately and must not declare M3 reached while required milestone gates remain incomplete.


## 4. Documentation and validation gates

- [ ] `RUN_PROVENANCE_SPEC.md` accurately describes the implementation and all unresolved semantics.
- [ ] `M3_DESIGN.md` records the exact owner-approved engine path and current implementation, with no broader implied authorization.
- [ ] `OPERATOR_RUNBOOK.md` documents the CLI syntax and explicitly says it is blocked until policy identity is available; legacy `agora run` is not a substitute.
- [ ] `RUNG_STATUS.md`, `MILESTONE_OPERATOR_PILOT.md` and `MILESTONE_PILOT_READY.md` distinguish M2 reached from M3 unreached.
- [x] VALIDATION_PROTOCOL.md v0.1 is frozen at 6d06088cf7954bd41f003544f5ec61675389bcc1. Its historic in-file “Draft preregistration only” header is preserved byte-for-byte; the explicit owner/Claude freeze attestation governs its status, and any header amendment requires a separately approved versioned freeze. The 15-row manifest was finalized separately by PR #203 (merge 3872f2401a8c6c6de097ad82a701414e8b1a26c9, SHA-256 59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf) and is included in the v0.2 freeze at 3fc4bc4f9b06e90b4602169de4cc13534a403ca0. VALIDATION_RUN_SPEC.md v0.2 is frozen at 3fc4bc4f9b06e90b4602169de4cc13534a403ca0 with SHA-256 ca87e4f47f39b1112e4ef808e949a49b1c87720f5e6576032acbba8723b5987b. Claude reports Package E stages were run once under the owner's conditional go after v0.2 freeze; calibration/2012/2016 results and hashes are recorded in the 24 Nov log. ChatGPT has not independently inspected raw outputs. The 24 Nov owner/Claude direction stops private MEDSL/Ember import; their absence from P2D is not an M3 blocker. PR #213 is merged and its artifact package is on main, but it lacks a complete byte-counted inventory and inventory hash; a separate owner-designated verifier must handle raw bytes and labels. M5 is dropped.
- [ ] Dataset acquisition checklist records canonical sources, expected semantic fields, exact file/version/hash capture, licence terms and personal-data stop rules.
- [ ] A merged docs commit updates the assessment base and links this checklist; exact-head docs CI is green.

## 5. Owner decisions and external inputs

- [x] Owner accepted Claude's A–D design decisions on 23 November 2026. This is design acceptance, not expanded path authorization; only `agora/sim/engine.py` is approved under `agora/sim/**`.
- [x] Owner confirmed that the synthetic-fixture Principal is acceptable for strictly local validation on approved public datasets only. Production CLI remains blocked/default-deny.
- [x] Owner approved the five protocol design values: bootstrap B=2000; bootstrap RNG seed 20261123; percentile interval; one preregistered seed per configuration; LLM temperature 0 with cache on. These values are effective under the frozen v0.1/v0.2 package. The v0.1 protocol and v0.2 run-spec files are byte-identical to their frozen commits; their in-file draft-status wording is preserved as part of the frozen bytes and must not be edited without a new owner-approved versioned freeze.
- [x] Claude's STEP 5 report states that all 12 FiveThirtyEight CSVs and Windows checked-out files match pinned source and committed-destination byte counts/SHA-256 values; manifest-file SHA-256 is `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb`. ChatGPT did not independently fetch raw CSV bytes.
- [x] Owner explicitly approved the exact MEDSL and Ember mirrors in Claude's latest entry; Claude reports the MEDSL and Ember file hashes above verified in its workspace. ChatGPT inspected public repository trees and metadata only, not raw bytes.
- [x] MEDSL/Ember private import is not required for frozen v0.2: the exact public source commits, file hashes and licences are pinned in the frozen 15-row manifest. Claude reports workspace hash verification; ChatGPT did not fetch raw bytes. No further import/download is authorized.
- [x] Owner explicitly dropped Package R/M5 on 23 November 2026; retail is untested and no Rossmann substitute is selected.
- [x] P2D PR #5 is not an M3 gate for MEDSL/Ember import. It remains a separate FiveThirtyEight import PR; no raw MEDSL/Ember private copy is required for v0.2. The 2000–2016 window excludes 2020/2024; the uncorrected 2024 general-average asset remains excluded.
- [x] ChatGPT compared the test_outputs.json and validation_outputs.json digest strings in SHA256SUMS with the two Notion-recorded hashes. This is a metadata string comparison only; ChatGPT did not fetch/hash raw output bytes, byte counts, prediction rows or labels.
- [x] Owner supplied the complete v0.1 freeze sentence naming protocol commit `6d06088cf7954bd41f003544f5ec61675389bcc1` and manifest SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`; Claude recorded v0.1 frozen. This approves no run and no flag change.
Claude reports 2016 labels were opened for its one test-evaluate after the output seal matched. ChatGPT did not receive or access those labels. The PR #213 output-integrity review is complete; a separately inventoried label bundle is needed only for any future independent metric recalculation. PR #214 seal-control tests pass exact-head CI 4/4; the missing-seal test does not instrument MEDSL hashing and the positive test does not explicitly assert output-read-before-MEDSL-hash order.


## 6. Claude's final declaration requirements

Before declaring M3 reached, Claude's collaboration-log entry must:

1. State the exact main SHA assessed and link each merged PR/head SHA.
2. List exact-head CI run IDs and all four job conclusions for each required slice.
3. State test counts and mutation proofs with clear distinction between CI evidence and local-only claims.
4. Confirm only the owner-approved `agora/sim/engine.py` path was touched under `agora/sim/**`.
5. Confirm the policy identity/capability trust boundary is resolved or explicitly state why M3 is limited to implementation-only and not operator-usable; cite #178 for the now-implemented base/projected hash semantics.
6. Link merged docs and the validation-protocol status; no false claim that draft preregistration equals approved validation.
7. Confirm no dataset/simulation/validation run occurred without authorization and `VALIDATED_PREDICTION_ENABLED=False`.
8. Use the exact phrase **"M3 reached"** only if all required acceptance gates are satisfied; otherwise state **"M3 not yet reached"** and name the remaining blockers.

**Claude reports** Package E calibration, 2012 validation and 2016 test-evaluate were run under the owner's conditional v0.2 go. ChatGPT independently verified the non-sensitive generated output/log bytes in PR #213 against SHA256SUMS and the logged stage hashes; it did not access labels or independently recalculate metrics. No prediction-validity claim is made; `VALIDATED_PREDICTION_ENABLED=False`.


## 7. Dataset handoff status — 23 November 2026

P2D PR #5 remains a separate open/draft/unmerged 12-FiveThirtyEight-file import proposal. For M3, the frozen manifest already pins the public FiveThirtyEight and MEDSL source commits, paths, bytes, SHA-256 values and licences; Claude's 24 Nov ~08:35 entry says MEDSL/Ember private copies are unnecessary and no new data/import is authorized. ChatGPT has not independently re-hashed MEDSL/Ember input CSVs. Package A is NOT EVALUABLE; Ember is not to be acquired or run.

| Relative path under `validation-data/elections/fivethirtyeight-polls/` | Bytes | Per-file SHA-256 |
|---|---:|---|
| `old_model/2024_presidential_primary_averages_old_model.csv` | 23,289 | `fb6d3f09936126651d60f30bc1559703611dc6b3cf28ef6185116d3e952a4c26` |
| `old_model/donald_trump_favorability_old_model.csv` | 82,705 | `4c39fe81a0d753551395c5436aa920546e1c4caf4611fed481b6ac98955c973a` |
| `old_model/generic_ballot_averages_old_model.csv` | 229,659 | `caae521c49a1ec9387a84a1a40f8f5a4555215513334cb667474d4f2ff130840` |
| `old_model/joe_biden_approval_old_model.csv` | 105,827 | `a65f9320d7202809289a4de50032892a282c8e73970057b87bf58899ed5f4849` |
| `old_model/kamala_harris_approval_old_model.csv` | 84,376 | `7cb826b1b247fdcb7fcbb941586c1b0c042f39a45f5828c40d3c6e3dfd8431b8` |
| `old_model/mike_pence_favorability_old_model.csv` | 46,274 | `4e174e4affc7dfedb847d75cc1fbb162eba61ffb77961085e45c224a71613f03` |
| `old_model/nikki_haley_favorability_old_model.csv` | 23,681 | `edbba323c9c857adffe991cb4ce4720a33944828a0e4349b5a75a8b019bbddc3` |
| `old_model/ron_desantis_favorability_old_model.csv` | 48,231 | `60a6d875a0b201f29280facd6fe59d26fe147005445790676ec281fbc6ab6e20` |
| `polls/2024-averages/presidential_general_averages_2024-09-12_uncorrected.csv` | 1,604,311 | `c66cf38aa566c3dfa0b50823e8259d9631bfb5ab830c18af13dd54204a8d8b35` |
| `polls/2024-averages/presidential_primary_averages_2024.csv` | 11,407,331 | `0d22110875abddbed1b0709553ba9e2c20e459f0ca8254961e321c9ac18791cc` |
| `polls/pres_pollaverages_1968-2016.csv` | 50,438,309 | `b897a8bc5f17ad0a2e959422cb8ec480dab5fcf25555b8eaaed60472ce68efcd` |
| `polls/pres_primary_avgs_1980-2016.csv` | 30,087,513 | `d30dd11829cd8748cbe3bfbb326d7708f03f3c3abe323edf43d29c0f7501944d` |

The selected v0.2 election window is 2000–2016; 2020/2024 are out of scope. The 2024 general-average file is explicitly uncorrected and excluded. The 12 FiveThirtyEight files remain on unmerged P2D PR #5; no raw input dataset was added to Agora. PR #213 adds only predictions, aggregate results and logs under docs/**, not source CSVs or outcome labels.

**Other packages:** MEDSL V20.0 and Ember 16-Nov public mirror sources and licences are pinned in the frozen manifest; Claude reports their hashes matched in its workspace, but ChatGPT did not inspect raw bytes. The 24 Nov owner/Claude direction stops private MEDSL/Ember import; their absence from P2D is not an M3 blocker. MEDSL dataset licence is CC0 1.0; Ember data is CC BY 4.0 (the mirror repos' MIT licences apply to code only). Package R/M5 was dropped; retail is untested and Rossmann is not selected.

ChatGPT did not download raw benchmark inputs or run project code/tests. It did fetch and independently hash the non-sensitive generated output/log artifacts in PR #213 as requested; it did not access held-out labels or independently recalculate label-based metrics.

## 8. Owner approvals received — 23 November 2026 (status, not milestone completion)

### A–D design acceptance and path boundary

The owner accepted Claude's A–D design decisions. This did not expand path-level authorization: within `agora/sim/**`, the only approved path remains `agora/sim/engine.py`. #205 did not touch `agora/sim/**`.

### Protocol v0.1 freeze

The owner supplied the complete freeze sentence at 22:14 IST on 23 November 2026. It names protocol commit `6d06088cf7954bd41f003544f5ec61675389bcc1`, the 15-row hash-only manifest SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf` (the manifest file was finalized separately by #203 merge `3872f2401a8c6c6de097ad82a701414e8b1a26c9`), and ChatGPT as a separate-process evaluator. Claude recorded v0.1 frozen at that exact commit. The freeze authorizes no run, no dataset import into AGORA and no flag change.

### Conditional v0.2 freeze pre-approval

At 22:25 IST the owner pre-approved freezing v0.2 at its exact merged commit only if its diff to v0.1 is limited to the five specified items: published-average-to-input mapping, output-to-state-margin mapping, counted-action mapping, run command and backend. Splits, metrics, baselines, data and manifest must remain unchanged, and exact-head CI must pass 4/4. Claude's 23:05 IST entry records v0.2 frozen at `3fc4bc4f9b06e90b4602169de4cc13534a403ca0` under the owner's conditional pre-approval; the run-spec SHA-256 is `ca87e4f47f39b1112e4ef808e949a49b1c87720f5e6576032acbba8723b5987b`. GitHub blob checks confirm `VALIDATION_PROTOCOL.md`, `VALIDATION_RUN_SPEC.md` and the 15-row manifest are unchanged between the frozen v0.2 commit and current main. Preserve the frozen files as-is; the external freeze attestation governs their status.

### Conditional run go — active for frozen Package E stages

The owner said “Go, once v0.2 is frozen,” limited to Packages E and A, one run per frozen configuration, outputs hashed before labels opened, no flag change and no other data. Claude's 24 Nov entries report Package E completed once. PR #213's nine output/log files and SHA256SUMS are merged to main; ChatGPT independently verified all nine hashes/byte counts and the 2016 pre-label seal. The first calibration process's silent exit and partial-output disposition remain undocumented. Package A is NOT EVALUABLE, Package R/M5 is dropped, and `VALIDATED_PREDICTION_ENABLED=False` remains unchanged. M3 is not declared reached.


### Exploratory v1.0 direction — 24 November 2026 (not a freeze or M3 evidence)

Claude's latest 24 Nov entry reports the owner's direction to perform exploratory analysis now and consider a 2020 confirmatory holdout later, with only minimal fundamentals (incumbent party and previous-election state result). The reported leave-one-cycle-out comparison used 2004/2008/2012/2016, and 2016 labels had already been opened. It is therefore exploratory only, not a validation result, not independent evidence of generalisation, and not an M3 acceptance gate. The reported blend did not beat poll alone on mean MAE (4.45 pp versus 4.15 pp); its 2008 error was materially worse. The shared signed poll bias changed sign across cycles, so no post-hoc bias correction is justified.

A separate `VALIDATION_PROTOCOL_V1_DRAFT.md` proposes 2020 as a future held-out election. The 2020 polling-average file has not been downloaded; a new manifest, exact source/licence/hash, model definitions, interval method, bootstrap seed, evaluator custody, owner freeze sentence and separate run authorization remain outstanding. Frozen v0.1/v0.2 files and the 15-row manifest are not amended. This direction does not declare M3 reached or change `VALIDATED_PREDICTION_ENABLED=False`.
