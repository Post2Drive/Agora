# M3 Exit Evidence — Claude Milestone Declaration Checklist

**Status:** Working checklist, not a milestone declaration. As of 23 November 2026, M3 has not been declared reached. The owner's 23 November run approval is recorded below as received, dormant; no freeze approval has been given, no run has occurred, and only Claude's explicit collaboration-log entry may declare M3 reached.

**Post-#192/#195 status:** #189 (RT05c) merged at exact head `21b540ee91cbfb47335156c8f2c2510b1b4d7d45`, merge `757da519f7af2c75a515ca42c6d23015d9e47123`, run `45141079904`, 4/4; it closes verification/restore record findings. #192 (RT05d) merged at exact head `bdf13a0663e5498c9d2e857817769985a8419e94`, merge commit `3e55e5505cda38a2ccfdc93a3e9996120ebb659e`, run `45150068645`, 4/4; it closes source-side strict-record preflight before destination creation/copy and re-checks copied bytes. #195 is the latest docs-only merge at exact head `fedab29c7d1e5b3d67e252d73bb97c9ae37acf93`, current main `e29ee4b1428fbc27458b547cc8c68bd4833c6ff2`, exact-head CI `45160887328`, 4/4 (six paths all under `docs/**`). Path-based SQLite reopen (TOCTOU) remains owner-gated.

**Assessment base:** main `e29ee4b1428fbc27458b547cc8c68bd4833c6ff2` (23 November 2026; latest docs-only merge #195 at exact head `fedab29c7d1e5b3d67e252d73bb97c9ae37acf93`, exact-head CI `45160887328` passed 4/4; latest code merge #192 at exact head `bdf13a0663e5498c9d2e857817769985a8419e94`, exact-head CI `45150068645` passed 4/4).

## 1. Merged implementation slices

| Slice | Merged PR | Mainline evidence | Exact-head CI |
|---|---:|---|---|
| 4.1 deterministic projection | #163 | `agora/scenario_projection.py`, tests; pure projection, explicit mapping/allow-list/bounds | Confirm exact run/job evidence in Claude's log before final declaration |
| 4.1b fail-closed projection hardening | #164 | `agora/scenario_projection.py`, tests; sensitivity and mapping/hash validation tightened | Confirm exact run/job evidence in Claude's log before final declaration |
| 4.2 governed engine integration | #171 | `agora/sim/engine.py` plus tests only; optional governed input, verification, append-once provenance guard, changed-input/legacy/force refusal | Run `45089066900`, 4/4 |
| 4.3 governed CLI | #172 | `agora/cli.py` plus tests; exact import ID, binding/pack/mapping args, `--force` refusal, exit 3 on engine refusal | Run `45093439437`, 4/4 |
| 4.4 instance-row integrity | #173 | `agora/scenario_projection.py` plus tests; order-independent `instances_hash` included in `projection_hash` | Run `45096233966`, 4/4 |
| 4.6 base/projected scenario hashes | #178 | `agora/sim/engine.py` plus tests only, within the owner's named scope; original `scenario.yaml` hash is `base_scenario_hash`, separate `projected_scenario_hash` binds it to `projection_hash` | Run `45113858688`, 4/4 |

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

Resolved by #178: `base_scenario_hash` is captured from the original `scenario.yaml` before projection; `projected_scenario_hash` is separate and bound to `projection_hash`. The exact-head CI passed 4/4 and merged tests cover row/mapping changes plus unchanged-envelope resume refusal. Claude reports local mutation proofs; ChatGPT did not reproduce them.
1. **Policy authorization boundary:** the CLI currently calls `_governed_policy()`, which returns `None`; the policy-required builder therefore denies before opening snapshot bytes. Do not weaken this. The owner must decide whether a bounded synthetic Principal is acceptable for local public-data validation or a production identity adapter is required. Any accepted adapter must be Principal-bound, scoped, expiring, fail-closed, and prove denial precedes source reads.
2. **Direct engine constructor:** a self-consistent package/hash is not proof of a successful policy decision. Prove direct `Simulation(..., governed_input=...)` cannot bypass the policy-built input boundary, or require a trusted capability that arbitrary callers cannot forge. Include a mutation proof.
3. **Provenance/report completeness:** verify manifest, projection, mapping, instances, original/projected scenario hashes and report/export fields agree. Keep append-once semantics and ensure `--force` cannot alter the envelope.

Claude must explicitly resolve each item or record a justified, owner-approved deferral before declaring the implementation milestone. A deferral cannot be used to claim an operator-usable governed workflow while the CLI still denies.

## 4. Documentation and validation gates

- [ ] `RUN_PROVENANCE_SPEC.md` accurately describes the implementation and all unresolved semantics.
- [ ] `M3_DESIGN.md` records the exact owner-approved engine path and current implementation, with no broader implied authorization.
- [ ] `OPERATOR_RUNBOOK.md` documents the CLI syntax and explicitly says it is blocked until policy identity is available; legacy `agora run` is not a substitute.
- [ ] `RUNG_STATUS.md`, `MILESTONE_OPERATOR_PILOT.md` and `MILESTONE_PILOT_READY.md` distinguish M2 reached from M3 unreached.
- [ ] `VALIDATION_PROTOCOL.md` remains clearly draft until owner approval. Freeze blockers include exact files/headers/licences, per-file privacy review, seeds/run counts, bootstrap parameters, independent evaluator/label custody, M5 reserve-file alignment and target-output compatibility.
- [ ] Dataset acquisition checklist records canonical sources, expected semantic fields, exact file/version/hash capture, licence terms and personal-data stop rules.
- [ ] A merged docs commit updates the assessment base and links this checklist; exact-head docs CI is green.

## 5. Owner decisions and external inputs

- [ ] Owner confirms whether a synthetic Principal is acceptable for local public-data validation or requires production identity.
- [ ] Owner supplies/approves the exact three benchmark packages and source terms; each file has a dataset-register row with source/version, licence/citation, access date, filename, bytes and SHA-256.
- [ ] Owner explicitly approves freezing a specific version/SHA of the validation protocol.
- [ ] Any simulation/validation run has separate explicit owner authorization naming scope, data, project and run purpose. M3 code merge is not run authorization.

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

The owner reports a partial FiveThirtyEight import in private `Post2Drive/Post2Drive` PR #5, import commit `15c9a053291925813ef568466a92fc5460f6b554`, from FiveThirtyEight/data source commit `4c1ff5e3aef1816ae04af63218015066e186c147`. The PR's changed-file list shows the upstream polls README/licence and eight `old_model/*.csv` files. Four larger CSVs remain outstanding: the uncorrected 2024 general averages, 2024 primary averages, 1968–2016 presidential poll averages and 1980–2016 presidential primary averages. Their reported byte counts and per-file manifest rows are in `DATASET_MANIFEST_TEMPLATE.md`. No per-file SHA-256 values are recorded; the handoff metadata does not establish raw-byte verification, complete 2020/2024 coverage, licence approval or permission to run.

The MEDSL V20 county presidential returns source is Harvard Dataverse DOI 10.7910/DVN/VOQCHQ, Version 20.0, CC0 1.0; the exact source file and bytes still need to be pinned and hashed. M5 Walmart remains conditional on the owner's review of Kaggle Competition Rules; do not acquire or use it before that review. The Ember monthly EV file remains a candidate public-adoption source whose exact official release and licence must be verified; a third-party 16-Nov snapshot is not presumed current. Any Rossmann replacement requires explicit selection and its own per-file licence review.

No raw dataset bytes were downloaded or inspected by ChatGPT in this documentation task. No complete manifest is present, no protocol freeze has occurred, and no dataset, simulation or validation run has occurred.

## 8. Owner approvals received — 23 November 2026 (status, not milestone completion)

### A–D design acceptance

The owner explicitly accepted Claude's written 23 November A–D design approval in the owner's chat message. This is acceptance of the design decisions, not an expansion of repository-path authorization. Within `agora/sim/**`, the only authorized path remains `agora/sim/engine.py`; no additional `agora/sim/**` path is authorized.

### Run approval — received, dormant

**Owner's run approval received 23 November 2026; status: RECEIVED, DORMANT.** The owner's approved scope is exactly one run per frozen configuration on the election, retail and adoption public datasets named in the frozen protocol, no tuning and no reruns for better numbers, all results reported including losses to the naive baseline, and no NCC, Nutrivance or P2D data.

This approval remains dormant until all preconditions are met: the protocol is separately frozen by the owner's freeze approval below; the complete selected datasets and per-file SHA-256 manifest are committed in the owner-controlled private repository; required implementation slices are merged and Claude records M3 reached; and the independent evaluator and custody are in place. The four outstanding FiveThirtyEight CSVs remain an acquisition blocker. This record does not authorize a run now, a second run, prediction enablement or any data outside the named public sets. No run has been made.

### Owner freeze sentence — template only; not approved or executed

Once the protocol PR is merged and the complete manifest and evaluator are ready, the owner may paste the following sentence with only the three values supplied:

“I approve freezing `docs/VALIDATION_PROTOCOL.md` as merged at commit [protocol commit sha], with dataset manifest [manifest sha] and evaluator [evaluator name]. This approves no run and no flag change.”

The blanks are intentionally limited to the protocol commit SHA, manifest SHA and evaluator name. This is a template, not a freeze decision. The protocol remains draft/unfrozen; M3 has not been declared reached; no dataset or simulation run has occurred; `VALIDATED_PREDICTION_ENABLED=False` remains unchanged.
