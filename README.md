# Mexico City Crime Prediction — Starter

This starter imports Mexico City crime cuadrante boundaries from the HoyoDeCrimen REST API into PostgreSQL/PostGIS.

## Setup

Create the database:

```sql
CREATE DATABASE cdmx_crime;
```

Then connect to it and enable PostGIS:

```sql
CREATE EXTENSION postgis;
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install packages:

```bash
pip install -r requirements.txt
```

Create your environment file:

```bash
cp .env.example .env
```

Edit `.env` and replace `YOUR_PASSWORD`.

Test the API:

```bash
python scripts/test_hoyodecrimen.py
```

Load cuadrante GeoJSON into PostGIS:

```bash
python scripts/load_cuadrantes.py
```

Verify:

```bash
python scripts/check_postgis.py
```

Useful SQL:

```sql
SELECT * FROM cuadrantes LIMIT 5;
```

```sql
SELECT
    ST_GeometryType(geometry),
    ST_SRID(geometry),
    COUNT(*)
FROM cuadrantes
GROUP BY 1, 2;
```
