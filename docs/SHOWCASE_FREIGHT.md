# Freight-pricing showcase — scope and evidence

**Status:** Local demonstration only. PR [#215](https://github.com/Post2Drive/Agora/pull/215) merged on 24 November 2026 at `d2302c1d6d04bffa23cdee861ce75de2fc3861bd`, from exact head `d493645f9c7bc687bf20f583f0a35c87a1f08981`. Exact-head CI run `45318338538` completed successfully: Ubuntu/Windows × Python 3.11/3.12, 4/4. The PR changed three paths under `agora/showcase/**` and `tests/**`; it did not change `agora/sim/**`.

## What the demonstration does

The showcase compares six monthly plan-price changes (-10%, -5%, 0%, +5%, +10%, +15%) through the governed scenario-input/projection/engine path. It uses a mock backend and crowd agents, creates a synthetic fixture Principal and a Principal-bound receipt, and writes `report.html` plus `result.json`. It is a local what-if demonstration, not a production workflow.

## Inputs: distinguish stated prices from assumptions

- **Price schedule:** the code uses the owner's stated Post2Drive pricing page (November 2026). Weekly driver/fleet prices are annualised to monthly using 52/12. Launch free periods and one-off verification fees are not modelled. Therefore, not every input is invented; the rate card is owner-stated business information.
- **Synthetic assumptions:** account counts by segment, price sensitivities, loyalty, the response scale, fixed segment characteristics and the simulated population are assumptions, not measured customer behaviour.
- **Data boundary:** the PR states that no P2D user/customer/account data, personal data or real accounts are used. The owner-stated rate card is not a customer dataset. No external feed or network access is part of the merged showcase.
- **Execution defaults in the merged source:** 70 seeds by CLI default (seed candidates 1–100), 1,200 crowd agents and 16 rounds. The PR body says 20 seeds, which does not match the current CLI default. A separate Claude report describes a 72-seed / 3,600-crowd / 32-round competitor-aware run; that is not the merged #215 configuration and is not independently verified here.

## Interpretation limits

The report's revenue index compares each scenario's mean simulated revenue with the no-change scenario's mean. Its displayed 5th–95th percentile ranges are seed-to-seed simulation spread, not real-world uncertainty. The code does not calculate paired per-seed revenue deltas, even though the same seed list is supplied to each price scenario. The result is sensitive to the assumed account mix and response parameters; it cannot establish real price elasticity, retention, revenue, demand or a recommended price.

The test suite includes a broad `pytest.raises(Exception)` assertion for the missing-receipt case rather than asserting the documented `GovernedInputError`. The CLI slices the seed list with `SEEDS[:a.seeds]` and does not validate the requested seed count; zero/negative values can yield an empty or shortened run, and values above 100 are silently capped by the available list. Output files are written directly to their destination names, so an existing `result.json` or `report.html` is overwritten. These are follow-up hardening items, not evidence that the merged CI failed.

## Identity and prediction boundary

The showcase uses `SyntheticFixtureAdapter`, which is a test/demo fixture and not production authentication. The production CLI policy hook still returns `None` and denies governed input by default. The report and package keep `VALIDATED_PREDICTION_ENABLED=False`. The showcase does not demonstrate a production identity adapter, a production trust boundary, validated prediction, or an operational customer deployment.

## Conditions for any real-world follow-on

A real-world pricing study is a separate task. Before any run, the owner must give written approval naming the exact rate card, inputs, run configuration (seeds, crowd size, rounds and backend), output location and permitted data. Assumed mix and response strengths must be replaced or calibrated using an explicitly approved, privacy-reviewed pilot with observed booking/retention outcomes. No personal, private customer or account data, external feeds, network access, write-back, or prediction-flag change is authorized by PR #215 or this document.
