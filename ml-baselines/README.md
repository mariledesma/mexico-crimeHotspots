# Mexico City crime prediction: implemented baseline

This package continues Part 2, Approach 2: Random Forest and gradient boosting on structured spatial and temporal features. Data source: [HoyoDeCrimen](https://api.hoyodecrimen.com/), [API documentation](https://hoyodecrimen.com/api/), CC BY 4.0. Counts describe the 20 loaded recorded-crime categories, rather than all crime or individual risk.

## Verified database state, October 22, 2026

- PostgreSQL database: `cdmx_crime`; 847 valid EPSG:4326 cuadrante polygons.
- `public.crime_monthly`: 1,558,480 rows, January 2019–August 2026; 847 × 92 × 20.
- Every cuadrante-month contains the same 20 category labels. No duplicate cuadrante/category/month keys or negative/null counts. Existing data was sufficient; no new API download was necessary.
- `public.crime_monthly_features`: 77,924 rows; all category panels complete.
- `public.cuadrante_neighbors`: 5,144 directed edges. Neighbors share a boundary or corner (`ST_Touches`); no self edges, asymmetric edges, or isolated cuadrantes. Degrees range from 1 to 18.
- Independently checked all next-month labels against the following calendar month's count: zero mismatches.

## Feature definitions

A row dated month t represents a forecast issued after that month's counts are available. `total_crime` sums the 20 source categories at t; `lag_1` and `lag_3` refer to t−1 and t−3. `rolling_3_month` averages t−2 through t; `rolling_6_month` averages t−5 through t. `target_next_month` is the count at t+1, never a predictor. Missing calendar months remain unknown rather than becoming zero.

Spatial inputs are the number of touching neighbors, sum and mean of neighbors' counts at t, and mean neighbors' counts at t−1. All neighbors must have the relevant count, otherwise the aggregate is NULL. Annual sine/cosine and year provide calendar predictors. No target, target date, future count, or cuadrante identifier is fed to the model.

## Evaluation

Fixed initial hyperparameters, seed 42. Both model families are evaluated with temporal features alone and with spatial features added, on identical eligible rows. Random Forest uses 200 trees and minimum leaf size 5; XGBoost uses 300 trees, depth 4, learning rate 0.05, and a Poisson count objective. Persistence and the three-month average provide simple comparison forecasts.

The latest six eligible target months are the test period; the six preceding target months are validation. Models first fit on training data for validation, then refit on training plus validation for test. Model selection uses validation MAE. Serialized fitted models retain the pre-test training cutoff. MAE, RMSE and R², exact split dates, versions, predictions, and feature importance are in `results/`.

This is sequential one-month-ahead evaluation: later test origins can use earlier test months' observed counts. It assumes counts at t are available when predicting t+1. It does not reconstruct publication delays or historical data revisions. August 2026 is the latest fully populated database month, but source reporting finality was not independently established; results are preliminary. The cutoff can be moved earlier with `--cutoff YYYY-MM-01`.

## Reproduce

From this package directory, use Python 3.12 or newer (on macOS, install the XGBoost runtime with `brew install libomp` first):

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
sh scripts/build.sh
.venv/bin/python scripts/verify.py
.venv/bin/python scripts/train.py --cutoff 2026-08-01
```

The build uses standard PostgreSQL connection settings (`PGDATABASE`, `PGHOST`, `PGUSER`, `.pgpass`); the database defaults to `cdmx_crime`. It transactionally refreshes derived tables and exports data without modifying `crime_monthly` or polygons. Existing loader data is validated before refresh. Database credentials are not included. Python dependencies used in this run are recorded in `requirements-lock.txt`.

## Scope for the later Part 3 writeup

Implemented: source validation, monthly calendar panel, temporal features, PostGIS adjacency and neighboring-crime features, fitted Random Forest and XGBoost, chronological validation/test, spatial ablation, saved models and predictions.

Not implemented: policy/law features, PyTorch/GNN, KDE/DBSCAN, hotspot classification, frontend/API, or causal policy evaluation. These may be described as future work only. Explicit spatial features are an experiment addressing Part 2's limitation; they are not evidence by themselves of a new algorithm or improvement over the research state of the art.
