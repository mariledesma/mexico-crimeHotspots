# Initial baseline results

Run: October 22, 2026. Target: next-month total recorded incidents across the 20 loaded categories per cuadrante.

Training target months: July 2019–August 2025 (62,678 rows). Validation: September 2025–February 2026 (5,082 rows). Test: March–August 2026 (5,082 rows). Models are refitted on training plus validation before test evaluation.

| Model | Test MAE | Test RMSE | Test R² |
|---|---:|---:|---:|
| persistence | 1.4111 | 2.0226 | -0.2052 |
| rolling_mean | 1.2210 | 1.6737 | 0.1748 |
| random_forest_temporal | 1.1665 | 1.5663 | 0.2773 |
| random_forest_spatial | 1.1487 | 1.5488 | 0.2933 |
| xgboost_temporal | 1.1458 | 1.5391 | 0.3022 |
| xgboost_spatial | 1.1401 | 1.5347 | 0.3061 |

XGBoost with spatial features was selected by validation MAE (1.1383). Its test MAE was 19.2% lower than persistence and 6.6% lower than the three-month average. Spatial features reduced Random Forest MAE by 1.5% and XGBoost MAE by 0.5% relative to temporal-only versions. These are modest improvements from one chronological holdout; statistical significance and generalization to other periods have not been established.

All 77,924 feature rows passed independent lag, rolling-window, label, and neighbor-aggregation checks. All six saved test metric sets matched recomputation from CSV predictions within 0.000001 (CSV float precision).

This implements Part 2 Approach 2 and explicit neighborhood features. No policy variables, deep learning, or hotspot classification were implemented. Counts may be revised, and August reporting finality was not independently established. Forecasts assume the origin month is available before predicting the following month.
