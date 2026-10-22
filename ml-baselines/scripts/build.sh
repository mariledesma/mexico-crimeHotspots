#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p data
# PGDATABASE/PGHOST/PGUSER or standard libpq credentials may override defaults.
export PGDATABASE="${PGDATABASE:-cdmx_crime}"
{ echo 'BEGIN;'; cat sql/temporal.sql sql/spatial.sql; echo 'COMMIT;'; } | psql -X -w -v ON_ERROR_STOP=1
psql -X -w -c '\copy (SELECT * FROM public.crime_monthly_features ORDER BY cuadrante,date) TO data/monthly_features.csv CSV HEADER'
psql -X -w -c '\copy (SELECT * FROM public.cuadrante_neighbors ORDER BY cuadrante,neighbor) TO data/neighbors.csv CSV HEADER'
