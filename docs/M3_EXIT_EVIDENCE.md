# M3 Exit Evidence — Claude Milestone Declaration Checklist

**Status:** Working checklist, not a milestone declaration. Agora main is `7400ec462fa6182a262b6a15571d2441d1490543` (23 November 2026). No exact Claude log entry declaring “M3 reached” is present. Protocol v0.1 is frozen at `6d06088cf7954bd41f003544f5ec61675389bcc1`; the 15-row hash-only manifest SHA-256 is `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`. #205 merged at exact head `9d5c466ec886b27e7c83c5c13695810cb44ed08d`, merge commit `3fc4bc4f9b06e90b4602169de4cc13534a403ca0`, exact-head CI run `45222866705` passed 4/4. It adds optional per-option leaning, the Package E harness/driver and `docs/VALIDATION_RUN_SPEC.md` v0.2. v0.2 remains DRAFT pending the owner's conditional freeze. Static review found that `test-evaluate` reads/verifies and loads MEDSL before checking `--sealed-sha`; held-out labels must remain closed until this is corrected and regression-proved. Package A is predeclared NOT EVALUABLE; Package R/M5 is dropped. P2D PR #5 remains open/draft/unmerged with only 12 FiveThirtyEight files; MEDSL and Ember raw files remain workspace-only. No dataset has been run, no run is authorized, and `VALIDATED_PREDICTION_ENABLED=False`.

**Current implementation/security evidence:** #197 RT06 read-side SQLite snapshots, #198 Principal-bound receipt, and #199 adapter-origin check remain merged with exact-head CI 4/4 each. Their documented limits remain: writer-side path opens are not held-descriptor hardened; receipt sentinels remain reachable in-process; no production identity adapter exists and the CLI remains default-deny. #205 exact-head CI is 4/4. #207 security hardening merged at exact head `687822c5870b66aba9c00890088b5efb95785267`, merge/current main `7400ec462fa6182a262b6a15571d2441d1490543`; run `45225751700` passed 4/4. ChatGPT documentation and evaluator-custody work is consolidated in draft PR #204; the former separate custody PR #206 is to be closed after consolidation.

## 1. Merged implementation slices## 1. Merged implementation slices

| Slice | Merged PR | Mainline evidence | Exact-head CI |
|---|---:|---|---|
| 4.1 deterministic projection | #163 | `agora/scenario_projection.py`, tests; pure projection, explicit mapping/allow-list/bounds | Confirm exact run/job evidence in Claude's log before final declaration |
| 4.1b fail-closed projection hardening | #164 | `agora/scenario_projection.py`, tests; sensitivity and mapping/hash validation tightened | Confirm exact run/job evidence in Claude's log before final declaration |
| 4.2 governed engine integration | #171 | `agora/sim/engine.py` plus tests only; optional governed input, verification, append-once provenance guard, changed-input/legacy/force refusal | Run `45089066900`, 4/4 |
| 4.3 governed CLI | #172 | `agora/cli.py` plus tests; exact import ID, binding/pack/mapping args, `--force` refusal, exit 3 on engine refusal | Run `45093439437`, 4/4 |
| 4.4 instance-row integrity | #173 | `agora/scenario_projection.py` plus tests; order-independent `instances_hash` included in `projection_hash` | Run `45096233966`, 4/4 |
| 4.6 base/projected scenario hashes | #178 | `agora/sim/engine.py` plus tests only, within the owner's named scope; original `scenario.yaml` hash is `base_scenario_hash`, separate `projected_scenario_hash` binds it to `projection_hash` | Run `45113858688`, 4/4 |
| RT06 read-side SQLite snapshot | #197 | Held-descriptor read-side snapshots for audit chain, anchor and run-record/seal checks; writer opens remain path-based; Python <3.11 fails closed | Run `45167913607`, 4/4 |
| 4.7 Principal-bound authorization receipt | #198 | Receipt minted after Principal-bound allow and revalidated in the engine; in-process sentinel and `object.__setattr__` limitations remain | Run `45170449040`, 4/4 |
| 4.7a adapter-origin provenance | #199 | Hand-built Principals without adapter-origin marker denied; same-process sentinel access remains possible | Run `45173316190`, 4/4 |
| 4.8 Package E leaning and staged harness | #205 | Optional per-option leaning in `agora/scenario_projection.py`; Package E harness/driver and v0.2 run-spec draft; no dataset execution | Head `9d5c466ec886b27e7c83c5c13695810cb44ed08d`, run `45222866705`, 4/4 |

For #171–#173 and #178, 4/4 means Ubuntu/Windows × Python 3.11/3.12 jobs all completed successfully. Claude's log reports 15 new engine tests, 7 CLI tests, 2 row-hash tests and four hash-split regression cases, plus local full-suite/mutation results; ChatGPT did not run or independently reproduce those local tests. For #178, exact head `a620feb98d342250e29ded132781630fcb31f395` passed run `45113858688` 4/4. Its diff changes only `agora/sim/engine.py` and `tests/test_engine_governed_input.py`; the sole `agora/sim/**` path remains the owner-approved `engine.py`. Confirm exact merge-head and workflow evidence for every implementation PR; do not rely on a branch-head result if the merged SHA differs.

**Supporting validation utility (not an M3 engine slice):** #175 adds pure benchmark metrics/baselines in `agora/validation/benchmark_metrics.py`; exact PR-head CI `45105990141` passed 4/4. Follow-up #176 hardens boolean, date and window validation and pins the official M5 RMSSE scale convention (differences start at the first non-zero training observation; pre-sale leading zeros are excluded); exact-head CI `45110601617` passed 4/4. #179 adds strict `samples`, `min_clusters` and `alpha` guards; exact-head CI `45116463242` passed 4/4. #180 adds a non-negative seed guard (merged at `82c830fd`, merge commit `76ee7625`; exact-head CI run `45119572140` passed 4/4). These supporting utilities do not complete the governed engine slices or authorize data use; no dataset run is authorized.

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
- [ ] Confirm no simulation, calibration, backtest, forecast, validation or real/public dataset run occurred without separate owner approval. Unit tests with synthetic fixtures/mock backend are not dataset runs.
- [ ] Confirm `VALIDATED_PREDICTION_ENABLED=False` remains unchanged.
- [ ] Confirm no real/personal/customer data, credentials, connectors, network fetches or write-back were introduced.

## 3. Blocking correctness and trust-boundary findings

These are not waived by merged PRs or green CI:

Resolved by #178: `base_scenario_hash` is captured from the original `scenario.yaml` before projection; `projected_scenario_hash` is separate and bound to `projection_hash`. Exact-head CI passed 4/4.

1. **Production policy source remains absent.** `agora/cli.py::_governed_policy()` returns `None`; the policy-required scenario-input builder denies before snapshot bytes are opened. Preserve this default-deny behaviour. Do not inject a permissive callback or bypass it.
2. **Receipt/Principal provenance has a same-process limitation.** #198 requires an exact-type Principal-bound receipt and #199 rejects hand-built Principals without the adapter-origin marker. However `_ISSUED` and `_MINT` are reachable module objects in the same Python process; the public receipt constructor accepts `_MINT`, and `object.__setattr__` bypasses the setter. The synthetic fixture adapter accepts caller-supplied fixture definitions and is test-only. No production identity adapter or process-isolated trust boundary exists. Do not describe this as production authentication.
3. **Read/write path-race coverage is incomplete.** #197 adds held-descriptor, identity-checked read-side snapshots for audit-chain, anchor and run-record/seal verification. `AuditChainStore` writer opens remain path-based. Python <3.11 fails closed because `Connection.deserialize` is unavailable; no path-reopen fallback is permitted.
4. **Two-package handoff is not complete in the owner-controlled private repository.** P2D PR #5 at `b06b29cb2071f048f0c234f65c1014ea4677d33d` remains open/draft/unmerged with 12 FiveThirtyEight CSVs (94,181,506 bytes), pinned to `4c1ff5e3aef1816ae04af63218015066e186c147`, CC BY 4.0; Claude reports source/destination and Windows checkout hashes match. Its 4,679-byte sub-manifest SHA-256 is `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb`. Owner-approved MEDSL V20.0 and Ember 16-Nov mirror hashes are reported by Claude as verified in its workspace, but neither raw file is committed to P2D/Agora; ChatGPT inspected metadata only. Agora #203 commits the 15-row hash-only register at `docs/VALIDATION_DATASET_MANIFEST.csv` with SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`; E/A rows are `PLANNED - NOT EXECUTED`. Package R/M5 was dropped by the owner; retail is untested and no substitute is selected. The complete private raw-file handoff/manifest ; evaluator custody procedure is drafted in `docs/EVALUATOR_CUSTODY.md` and awaits owner review/merge. Protocol v0.1 is frozen; v0.2 target mappings and run specification remain outstanding.
5. **Run approval is dormant.** The owner's one-run approval is received but applies only after an effective protocol freeze, complete data manifest, implementation gates and Claude's M3-reached confirmation. No dataset, simulation or validation run is authorized now.

Claude must state these residuals accurately and must not declare M3 reached while required milestone gates remain incomplete.


## 4. Documentation and validation gates

- [ ] `RUN_PROVENANCE_SPEC.md` accurately describes the implementation and all unresolved semantics.
- [ ] `M3_DESIGN.md` records the exact owner-approved engine path and current implementation, with no broader implied authorization.
- [ ] `OPERATOR_RUNBOOK.md` documents the CLI syntax and explicitly says it is blocked until policy identity is available; legacy `agora run` is not a substitute.
- [ ] `RUNG_STATUS.md`, `MILESTONE_OPERATOR_PILOT.md` and `MILESTONE_PILOT_READY.md` distinguish M2 reached from M3 unreached.
- [ ] Review the merged `docs/VALIDATION_RUN_SPEC.md` v0.2 against the owner's five-item pre-approval; verify splits, metrics, baselines, data and manifest are unchanged. It remains DRAFT until the conditional freeze is explicitly invoked. Before any run or label release, fix `test-evaluate` so the output seal is verified before MEDSL is hashed or loaded, and add a regression/mutation proof that a missing or wrong seal does not touch label bytes.
- [ ] Dataset acquisition checklist records canonical sources, expected semantic fields, exact file/version/hash capture, licence terms and personal-data stop rules.
- [ ] A merged docs commit updates the assessment base and links this checklist; exact-head docs CI is green.

## 5. Owner decisions and external inputs

- [x] Owner accepted Claude's A–D design decisions on 23 November 2026. This is design acceptance, not expanded path authorization; only `agora/sim/engine.py` is approved under `agora/sim/**`.
- [x] Owner confirmed that the synthetic-fixture Principal is acceptable for strictly local validation on approved public datasets only. Production CLI remains blocked/default-deny.
- [x] Owner approved the five protocol design values: bootstrap B=2000; bootstrap RNG seed 20261123; percentile interval; one preregistered seed per configuration; LLM temperature 0 with cache on. These values are merged in protocol #202 and effective under the owner's 22:14 IST freeze approval, recorded by Claude at 22:16 IST.
- [x] Claude's STEP 5 report states that all 12 FiveThirtyEight CSVs and Windows checked-out files match pinned source and committed-destination byte counts/SHA-256 values; manifest-file SHA-256 is `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb`. ChatGPT did not independently fetch raw CSV bytes.
- [x] Owner explicitly approved the exact MEDSL and Ember mirrors in Claude's latest entry; Claude reports the MEDSL and Ember file hashes above verified in its workspace. ChatGPT inspected public repository trees and metadata only, not raw bytes.
- [ ] Commit the owner-approved MEDSL and Ember raw files, codebook/attribution and per-file manifest rows to the owner-controlled private repository; verify the transferred bytes and recompute the complete private-manifest SHA-256.
- [x] Owner dropped Package R/M5 on 23 November 2026 21:08 IST; no Kaggle acquisition, Rossmann substitute or retail claim is in scope. Retail is untested.
- [ ] Owner accepts/merges P2D PR #5 and transfers the approved MEDSL/Ember mirror files into the owner-controlled private repository, with exact per-file hashes, licence and source metadata. P2D PR #5 currently stages only FiveThirtyEight; the two mirror files remain in Claude's workspace. The 15-row Agora manifest is hash-only and is not the private data handoff.
- [ ] Owner establishes the named ChatGPT separate-process evaluator's restricted access to only the frozen protocol, manifest and raw outputs, plus output custody and label-release procedure.
- [x] Owner posted the complete v0.1 freeze sentence at 22:14 IST; Claude recorded the freeze at 22:16 IST. It authorizes no run and no flag change.
- [ ] Any simulation/validation run remains dormant until all freeze and data gates are satisfied and Claude has declared M3 reached; the owner's one-run approval does not authorize a run now.


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

**No dataset was acquired, no simulation or validation was run, and no prediction-validity claim is made by this document.**


## 7. Dataset handoff status — 23 November 2026

The private Post2Drive data repository main remains `5c8787a410a1aacaa9be9933b1c725a0b12e9689`. FiveThirtyEight import PR #5 remains open/draft/unmerged at branch head `b06b29cb2071f048f0c234f65c1014ea4677d33d`; it stages 12 CSVs (94,181,506 bytes) with a 12-row manifest SHA-256 `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb`. Claude reports source/destination and Windows checkout hashes match. The owner-approved MEDSL mirror is `mathis-group/cas-201-data-project@1358bc6047f0c22989d37fa64ac03ee755bd17e7` (10,222,208 bytes; Claude-reported SHA-256 `9299583148f5f8264baf50b5d929c260699c46d915909b13ea3c3850918946f8`, CC0 1.0); the owner-approved Ember mirror is `Awes0mer/fuel-cars-pollution@2c21f1edced7aae884314ebc28c89ab212f30563` (7,695,642 bytes; Claude-reported SHA-256 `76e241d07d2086477ef0279d4ce20cd6a02c7869b5152ecc016bf132d2734fb2`, CC BY 4.0, 16-Nov snapshot). Claude reports both raw mirror files remain in its workspace only; ChatGPT inspected metadata, not raw bytes. Agora #203's 15-row hash-only documentation manifest has current SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`; statuses are PLANNED - NOT EXECUTED / inventoried only, not used. No raw data was added to Agora.

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

The selected election window is 2000–2016; 2020/2024 are out of scope. The 2024 general-average file is explicitly uncorrected and excluded. The 12 FiveThirtyEight files remain on unmerged P2D PR #5 and are not in P2D main or Agora main; no raw data was added to Agora.

**Other active package:** Package A is the owner-approved Ember 16-Nov mirror; Claude reports its hash verified in its workspace, but the raw file is not committed to P2D/Agora. MEDSL V20.0 (Package E) is likewise owner-approved but remains in Claude's workspace only. Package R/M5 is dropped; retail is untested. Agora's combined manifest is hash-only and does not mean the private raw files are staged.

No raw benchmark files were downloaded by ChatGPT, no dataset was imported into Agora, and no simulation or validation was run.

## 8. Owner approvals received — 23 November 2026 (status, not milestone completion)

### A–D design acceptance

The owner explicitly accepted Claude's written 23 November A–D design approval in the owner's chat message. This is acceptance of the design decisions, not an expansion of repository-path authorization. Within `agora/sim/**`, the only authorized path remains `agora/sim/engine.py`; no additional `agora/sim/**` path is authorized.

### Run approval — received, dormant

**Owner's run approval received 23 November 2026; status: RECEIVED, DORMANT.** The active run scope is Packages E (polls + election returns) and A (Ember monthly EV) only; Package R/M5 was subsequently dropped by the owner. The approval remains limited to one run per frozen configuration, no tuning or outcome-led reruns, and no NCC, Nutrivance or P2D data.

This conditional run approval remains dormant until v0.2 is specified and frozen within the owner's pre-approved change boundary; the selected E/A raw files and complete per-file SHA-256 manifest are committed in the owner-controlled private repository; required implementation and evaluator-custody gates pass; and Claude confirms M3 reached. Protocol v0.1 is already frozen, but its freeze authorizes no run. P2D PR #5 remains unmerged with only FiveThirtyEight files; MEDSL and Ember raw files remain in Claude's workspace only. Agora's 15-row documentation manifest is hash-only and does not satisfy the private data handoff. Package R/M5 is dropped. This record authorizes no run now, no second run, no prediction enablement and no data outside Packages E/A. No run has been made.

### Owner freeze sentence — v0.1 frozen; v0.2 run specification still required

The owner supplied the following historical sentence on 23 November 2026. It cites the earlier protocol commit and is superseded by merged protocol amendment #202:

“I approve freezing `docs/VALIDATION_PROTOCOL.md` as merged at commit 34e5cc39b2bb9f53ca6be0dc057de53e5aa5532c, with dataset manifest `<sha>` and evaluator ChatGPT (separate process, sees only the frozen protocol, manifest and raw outputs). This approves no run and no flag change.”

The owner posted the exact sentence at 22:14 IST: “I approve freezing `docs/VALIDATION_PROTOCOL.md` as merged at commit `6d06088cf7954bd41f003544f5ec61675389bcc1`, with dataset manifest `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf` and evaluator ChatGPT (separate process, sees only the frozen protocol, manifest and raw outputs). This approves no run and no flag change.” Claude recorded protocol v0.1 frozen at 22:16 IST.

Protocol v0.1 is frozen. Before any run, the v0.2 mapping/run-spec gap must be resolved, the evaluator custody procedure must be approved, all data and implementation gates must pass, and the conditional run go must be satisfied. The v0.1 freeze itself authorizes no run or flag change. `VALIDATED_PREDICTION_ENABLED=False` remains unchanged.