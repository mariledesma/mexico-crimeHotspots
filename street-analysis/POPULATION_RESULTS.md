# WorldPop street population experiment

Population context was added to the existing 877-segment pilot. These are retrospective comparisons using WorldPop Global2 R2025A. Release inputs can postdate the crime prediction origins. They do not establish the performance of a demographic feature available in real time.

## Source and construction

- Annual count grids for 2018–2026 were retrieved from the WorldPop v3 raster API. The 2018 layer supplies the previous-year comparison for 2019. Output covers 2019–2026, with 7,016 segment-year rows.
- Streets are buffered by 200 m in EPSG:32614. Counts are weighted by the fraction of each projected raster cell intersecting a buffer. Missing population cells cause a build failure. Zero population remains a valid value.
- The three inputs are estimated residents, residents/km², and annual percent change. A separate indicator identifies undefined growth after a zero-population year. Annual values are attached using the crime forecast origin year.
- Buffers overlap. Their populations must not be summed. Study totals are calculated independently within the study boundary.
- Grid spacing is 3 arcseconds, approximately 100 m at the equator. Counts are modeled estimates. Annual change includes births, deaths, migration, and modeling effects. It is not a migration measure.
- Raw GeoTIFFs, request payloads, retrieval dates, country catalog responses and SHA-256 hashes are cached in `data/street/raw/worldpop/`. The manifest pins R2025A and verifies year, units, grid resolution and input hashes.
- Independent small-area INEGI validation remains pending. A coarse comparison using WorldPop’s predefined Distrito Federal unit encountered a boundary-area mismatch, so it was not treated as an accuracy check.

## Controlled model comparisons

Both controls and population variants use identical crime features, neighbors, KDE bandwidth, model settings and chronological splits. The added Random Forest + KDE control isolates the population contribution. Tests cover March 2025–August 2026, 15,786 segment-month rows and 484 matched records. Population variants are excluded from the historical default-model selector.

| Model | MAE | RMSE | Nonzero-month MAE | Top 10% capture |
|---|---:|---:|---:|---:|
| Random Forest · + KDE | 0.0683 | 0.2010 | 1.0217 | 39.3% |
| Random Forest · + KDE and population (retrospective) | 0.0710 | 0.1979 | 1.0058 | 42.4% |
| XGBoost · + KDE | 0.0584 | 0.1931 | 1.0492 | 43.8% |
| XGBoost · + KDE and population (retrospective) | 0.0592 | 0.1923 | 1.0397 | 43.2% |

Random Forest capture improved by 3.1 percentage points, with gains in the first two folds and a loss in the third. XGBoost capture fell by 0.6 percentage points, with a gain in the first fold and losses in the next two. Both population variants reduced RMSE and increased MAE. The current evidence supports a mixed contribution from population features. No significance test or causal interpretation is claimed.

## Capture by test period

| Test period | RF + KDE | RF + population | XGB + KDE | XGB + population |
|---|---:|---:|---:|---:|
| 2025-03–2025-08 | 32.5% | 36.4% | 40.3% | 42.2% |
| 2025-09–2026-02 | 40.2% | 45.8% | 46.4% | 45.3% |
| 2026-03–2026-08 | 45.0% | 44.4% | 44.4% | 41.7% |

## Results across density groups

Groups are defined by training-density quartiles separately in each fold. Cutoffs are saved in the metrics. Their labels describe density relative to each training period. Capture is calculated within each group each month.

| Group (low to high) | Test rows | Matched records | XGB + KDE MAE | XGB + population MAE | KDE capture | Population capture |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 3619 | 137 | 0.0603 | 0.0609 | 67.9% | 70.8% |
| 2 | 3979 | 101 | 0.0517 | 0.0545 | 45.5% | 44.6% |
| 3 | 3643 | 129 | 0.0644 | 0.0662 | 29.5% | 27.1% |
| 4 | 4545 | 117 | 0.0580 | 0.0562 | 30.8% | 29.1% |

## Reproduce and view

```sh
street-analysis/.venv/bin/pip install -r street-analysis/requirements.txt
street-analysis/.venv/bin/python street-analysis/population.py
street-analysis/.venv/bin/python street-analysis/train.py --population
street-analysis/.venv/bin/python street-analysis/publish.py
cd dashboard/frontend
npm run build
cd ../..
sh dashboard/start.sh
```

Open `/streets` and choose **Population density near streets**, then select a year. Click a street for its estimated buffer population and annual change. The page also includes annual study totals, model comparisons, and results by density group.

## Sources

[WorldPop API documentation](https://api.worldpop.org/v3/documentation). Population data, CC BY 4.0, WorldPop, University of Southampton, [DOI 10.5258/SOTON/WP00839](https://doi.org/10.5258/SOTON/WP00839).

[INEGI 2020 Mexico City census reference](https://www.inegi.org.mx/contenidos/saladeprensa/boletines/2021/EstSociodemo/ResultCenso2020_CdMx.pdf).
