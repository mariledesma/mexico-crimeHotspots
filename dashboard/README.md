# Crime Prediction Explorer

An interactive React dashboard for the Mexico City crime prediction project, using FastAPI and PostgreSQL/PostGIS. It displays the saved March–August 2026 test predictions; it does not generate live forecasts.

## Open the dashboard

With PostgreSQL running, open a terminal in the `mexico-crime` project:

```sh
sh dashboard/start.sh
```

Then visit **http://127.0.0.1:8000**. Keep the terminal running; Ctrl+C stops the dashboard. If port 8000 is already in use, run `PORT=8010 sh dashboard/start.sh` and visit port 8010.

The first run prepares a separate Python environment, installs the React dependencies, builds the frontend, and imports the saved predictions. Python 3.11+, Node.js 20.19+ or 22.12+, npm, and PostgreSQL with PostGIS are required. The Node and Python environments are separate from the earlier ML environment. Later runs use the existing frontend build without requiring Node.js at runtime.

## What you can explore

- Select a target month and any of the six prediction models.
- Color all 847 cuadrantes by predicted count, actual count, or absolute prediction error.
- Click a polygon or choose a cuadrante to compare actual counts and predictions over six test months.
- Compare test MAE across all models and inspect the highest predicted counts in the selected month.
- Download the selected month/model as CSV.
- Use **Presentation view** to simplify the display for a live demonstration, or **Print / PDF** to capture it for slides. On macOS, Shift+Command+4 can capture a selected chart for PowerPoint.

The top error metrics cover the entire six-month test period. The city totals and selected-area values follow the selected target month. The color bins are fixed, allowing comparisons between months. Map geometries are lightly simplified for display; training adjacency used the original polygons.

## Database connection and imports

The backend reads `DATABASE_URL` from the project's existing `.env`, or the process environment. If absent, it uses `dbname=cdmx_crime` with normal PostgreSQL connection settings. No credentials are sent to React.

Saved predictions and metrics are read from `ml-baselines/results/`. Set `CRIME_RESULTS_DIR` if they live elsewhere. The import validates duplicate keys, coverage, nonnegative finite counts, calendar dates, and agreement with saved MAE/RMSE values before committing.

Two new tables hold the data:

- `dashboard_prediction_runs`: source hashes and evaluation metadata.
- `dashboard_predictions`: 30,492 model predictions across 5,082 observations.

The source files' combined hash identifies each run. Importing the same files again does not duplicate rows. New source evidence creates a new run; the dashboard uses the latest imported run. Original crime tables, polygons, feature tables, and fitted models are not modified.

Re-import after updating the source results:

```sh
dashboard/.venv/bin/python dashboard/backend/import_predictions.py
```

## Frontend development

Run the backend in one terminal:

```sh
dashboard/.venv/bin/python -m uvicorn main:app --app-dir dashboard/backend --host 127.0.0.1 --port 8000 --reload
```

Run React in another terminal:

```sh
cd dashboard/frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173. Vite forwards `/api` requests to the backend. To update the built frontend used by `start.sh`, run `npm run build` in `dashboard/frontend`, then restart the server.

## Checks

With the backend running:

```sh
dashboard/.venv/bin/python dashboard/backend/check_api.py
```

This checks all 36 month/model combinations, boundary coverage, agreement with saved MAE values, history, CSV downloads, and invalid inputs. The frontend build checks the React application; browser checks cover filters, charts, presentation view, and responsive layout.

## Scope and sharing

This is a local dashboard. Its URL works on the computer running it; it is not a public share link. Public hosting would require deploying the FastAPI app and providing a reachable PostgreSQL database. The built React frontend is served by FastAPI, so no separate frontend host is required. Do not publish the project's `.env` or database credentials.

Predictions describe recorded incidents in the 20 loaded categories, not individual risk or all crime. This first evaluation uses one chronological holdout and assumes origin-month counts are available. Source counts may be revised, publication delays were not reconstructed, and August 2026 reporting finality was not independently established. Policy variables and PyTorch are not implemented.

Data and boundaries: [HoyoDeCrimen](https://api.hoyodecrimen.com/), CC BY 4.0.
