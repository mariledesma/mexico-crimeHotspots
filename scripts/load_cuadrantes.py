import os
import requests
import geopandas as gpd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://api.hoyodecrimen.com/api/v1/cuadrantes/geojson"
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is missing. Copy .env.example to .env and set your PostgreSQL password."
    )

def main():
    print("Downloading Mexico City cuadrantes...")
    response = requests.get(API_URL, timeout=60)
    response.raise_for_status()
    geojson = response.json()

    gdf = gpd.GeoDataFrame.from_features(geojson["features"], crs="EPSG:4326")
    gdf.columns = [str(c).strip().lower().replace(" ", "_") for c in gdf.columns]
    gdf = gdf.to_crs("EPSG:4326")

    print(f"Downloaded {len(gdf)} cuadrantes.")
    print("Columns:", list(gdf.columns))

    engine = create_engine(DATABASE_URL)

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))

    gdf.to_postgis(
        name="cuadrantes",
        con=engine,
        if_exists="replace",
        index=False
    )

    with engine.begin() as conn:
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_cuadrantes_geom "
            "ON cuadrantes USING GIST (geometry);"
        ))

    print("Loaded cuadrantes into PostgreSQL/PostGIS.")
    print("Created spatial GIST index.")

if __name__ == "__main__":
    main()
