# Centro street analysis pilot

The existing 847-cuadrante dashboard is still at `/`. The new **Street analysis** page is at `/streets` and uses a separate PostGIS study. It does not depend on a live map-tile service.

```sh
sh dashboard/start.sh
```

Open http://127.0.0.1:8000/streets. If the dashboard was already running, stop it in its terminal and restart it to load the new API routes. `PORT=8010 sh dashboard/start.sh` is an alternative when port 8000 is occupied.

## What to try

- **Recorded locations:** filter historical point records by category and period, with optional current mapped places.
- **KDE hotspot density:** choose 100, 200, or 400 m smoothing. Outlines mark cells above the 90th percentile of the historical reference distribution.
- **KDE density change:** compare two equal-length windows; blue indicates a decrease and orange an increase. The grid and units stay fixed. Colors saturate at the historical reference scale; tooltips/legend describe the units.
- **Street counts and changes:** view matched records or differences between two periods on the road network.
- **Street predictions:** choose a held-out month and one of 11 methods, then select a street to see its history. September 2026 is one month beyond this source snapshot and has no observed outcome here.
- **Find patterns:** compare crime categories or crime and mapped places using a distance and minimum participation index. The optional random-label test preserves incident positions and monthly category totals; it reports adjusted q values for pairs. It is exploratory and does not establish causation.

## Data and limits

A single HoyoDeCrimen request covered a 2 km radius, January 2023–August 2026. The smaller 1 km Centro circle is the analysis area. The surrounding records support KDE near the boundary. The study uses 877 street segments and 457 mapped context places from a bounded OpenStreetMap extract.

Of 1,760 records inside the study area, 1,364 matched a segment, 385 had competing matches within 3 m of the nearest distance, and 11 were farther than 50 m from the usable network. Unmatched points stay available for KDE and colocation but are excluded from street count labels. Source coordinate accuracy was not independently verified. The matching rules are approximations and can bias which records enter the street model.

The crime API lacks a stable event identifier, so this pilot retains source rows by snapshot hash and row ordinal. It does not merge overlapping crime API requests. A normalized CSV with unique `source_id`, `crime`, `date`, `lat`, `long`, and optional `hour` can be supplied via `prepare.py --events PATH` for a verified bulk source. The unit is the source record, not a claim that all incidents were reported. Current OSM places are exploratory; they are excluded from historical forecasting. The OSM network also represents its extract date, so historical matching assumes that the relevant street geometry did not change.

## Methods and results

- Gaussian KDE uses projected meters, a fixed 100 m grid, and intensity in records per km² per 30 days. For each category, bandwidth, and window length, the fixed map scale and hotspot threshold come from periods before the first test fold.
- Colocation uses distinct-instance participation, exact pairwise distances, and complete cliques for triples. A coarse grid removes impossible candidates before refinement. In the August 2026 benchmark the grid and exhaustive implementations produced identical prevalent patterns; the grid reduced exact distance checks from 946 to 56. This is a small workload example, not a general speed benchmark.
- Three chronological folds cover March 2025–August 2026. KDE bandwidth and pattern inputs were selected using training/validation information before each test. Results include zero, persistence, rolling average, historical KDE, Random Forest and XGBoost variants, plus a separate XGBoost + KDE comparison to isolate the contribution from colocation.
- XGBoost + KDE captured 43.8% of later matched records in the highest-ranked tenth of street segments, compared with 41.5% for XGBoost with neighbors alone and 10.0% for the always-zero baseline. Adding colocation reduced this XGBoost result to 43.2%. The always-zero baseline had the lowest MAE (0.0307), reflecting the many zero-count segment-months; ranking and average count error answer different questions.

`data/street/processed/metrics.json` contains all fold dates, selected patterns, model results, and the exact/grid comparison. `predictions.csv` contains 15,786 held-out segment-month rows plus 877 beyond-snapshot rows. The pilot is not a citywide street model or a real-time service.

## Reproduce or refresh

Use Python 3.12+ and an existing local `cdmx_crime` PostgreSQL/PostGIS database. XGBoost requires OpenMP on macOS. The separate environment keeps the original ML and dashboard environments independent.

```sh
python3.12 -m venv street-analysis/.venv
street-analysis/.venv/bin/pip install -r street-analysis/requirements.txt
# Optional: fetch a new snapshot. Skip this to reproduce the saved source files.
street-analysis/.venv/bin/python street-analysis/acquire.py --with-streets
street-analysis/.venv/bin/python street-analysis/prepare.py
street-analysis/.venv/bin/python street-analysis/train.py
street-analysis/.venv/bin/python street-analysis/publish.py
```

`publish.py` writes the pilot tables in one transaction and uses the existing project database settings. `crime_events`, `street_segments`, `street_context_places`, `street_monthly`, `street_predictions`, and `street_studies` are separate from the citywide tables. Source snapshots and generated data are kept locally and ignored by Git. The recorded source request and hashes are in the snapshot metadata. On a fresh clone, run the dashboard setup once to install its additional spatial libraries.

```sh
PYTHONPATH=street-analysis street-analysis/.venv/bin/python -m unittest discover -s street-analysis/tests
# With the dashboard running on port 8000:
dashboard/.venv/bin/python street-analysis/check_api.py
```

Crime source: [HoyoDeCrimen](https://api.hoyodecrimen.com/) (CC BY 4.0). Streets and context: [© OpenStreetMap contributors](https://www.openstreetmap.org/copyright) (ODbL).
