# First real holdout: US presidential 2024, state level

Test: predict each state's two-party Democratic share in 2024 using only 2008–2020 data.
Truth: 2024 county results, summed to state (DC excluded, 50 states scored).

Data: https://github.com/tonmcg/US_County_Level_Presidential_Results_08-24 at commit 8cccc82f9235dced94a76d143c59a43f4a6bf979 (MIT).
The repo says it is not authoritative. Check state totals against certified results before publishing.
National check: 2024 file totals give Dem 75,006,739 and GOP 77,294,799 (two-party Dem 49.25%).

Run: `python validation/us_presidential_2024/baselines.py` after cloning the data repo to `/tmp/claude-0/elec`.

## Baseline results (2024 state two-party Dem share, 50 states)

| Method | MAE (pts) | RMSE (pts) | Bias (pts) |
|---|---|---|---|
| Last value (2020) | 2.19 | 2.52 | +2.19 |
| Mean 2008–2020 | 2.89 | 3.45 | +2.46 |
| Linear trend 2008–2020 | 2.11 | 2.72 | -0.07 |

Agora has not been scored on this holdout yet. It must beat the best baseline (linear trend, MAE 2.11) to add value.
