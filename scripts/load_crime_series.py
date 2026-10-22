import os
import time
import requests
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

BASE_URL = "https://api.hoyodecrimen.com/api/v1"
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing from .env")

engine = create_engine(DATABASE_URL)

session = requests.Session()

retry = Retry(
    total=5,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)

session.mount("https://", HTTPAdapter(max_retries=retry))


def get_cuadrantes():
    query = """
        SELECT DISTINCT cuadrante
        FROM cuadrantes
        WHERE cuadrante IS NOT NULL
        ORDER BY cuadrante;
    """

    df = pd.read_sql(query, engine)

    return df["cuadrante"].tolist()


def crime_table_exists():
    with engine.connect() as conn:
        exists = conn.execute(text("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_name = 'crime_monthly'
            );
        """)).scalar()

    return exists


def get_already_loaded():
    if not crime_table_exists():
        return set()

    df = pd.read_sql(
        """
        SELECT DISTINCT cuadrante
        FROM crime_monthly;
        """,
        engine
    )

    return set(df["cuadrante"].tolist())


def download_cuadrante(cuadrante):
    url = (
        f"{BASE_URL}/cuadrantes/"
        f"{cuadrante}/crimes/all/series"
    )

    response = session.get(
        url,
        timeout=60
    )

    response.raise_for_status()

    data = response.json()

    return data.get("rows", [])


def clean_rows(rows):
    df = pd.DataFrame(rows)

    if df.empty:
        return df

    required_columns = [
        "count",
        "crime",
        "cuadrante",
        "date",
        "population",
        "sector"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing columns from API response: {missing_columns}"
        )

    df["count"] = (
        pd.to_numeric(
            df["count"],
            errors="coerce"
        )
        .fillna(0)
        .astype(int)
    )

    df["population"] = (
        pd.to_numeric(
            df["population"],
            errors="coerce"
        )
    )

    # API returns date values like "2019-01"
    df["date"] = pd.to_datetime(
        df["date"],
        format="%Y-%m",
        errors="coerce"
    )

    df = df.dropna(
        subset=["date"]
    )

    # Create separate year/month fields for ML
    df["year"] = df["date"].dt.year.astype(int)
    df["month"] = df["date"].dt.month.astype(int)

    df["crime"] = (
        df["crime"]
        .astype(str)
        .str.strip()
    )

    df["cuadrante"] = (
        df["cuadrante"]
        .astype(str)
        .str.strip()
    )

    df["sector"] = (
        df["sector"]
        .astype(str)
        .str.strip()
    )

    # Put columns in a clean order
    df = df[
        [
            "cuadrante",
            "sector",
            "crime",
            "date",
            "year",
            "month",
            "count",
            "population"
        ]
    ]

    return df


def create_indexes():
    with engine.begin() as conn:

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS
            idx_crime_monthly_cuadrante
            ON crime_monthly (cuadrante);
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS
            idx_crime_monthly_year_month
            ON crime_monthly (year, month);
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS
            idx_crime_monthly_crime
            ON crime_monthly (crime);
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS
            idx_crime_monthly_date
            ON crime_monthly (date);
        """))


def main():

    cuadrantes = get_cuadrantes()
    already_loaded = get_already_loaded()

    total = len(cuadrantes)

    print(f"Cuadrantes in PostGIS: {total}")
    print(f"Already loaded: {len(already_loaded)}")
    print()

    completed = 0
    skipped = 0
    failed = []

    for i, cuadrante in enumerate(
        cuadrantes,
        start=1
    ):

        if cuadrante in already_loaded:
            print(
                f"[{i}/{total}] "
                f"{cuadrante} already loaded - skipping"
            )

            skipped += 1
            continue

        print(
            f"[{i}/{total}] "
            f"Downloading {cuadrante}..."
        )

        try:

            rows = download_cuadrante(
                cuadrante
            )

            if not rows:
                print("  No rows returned.")
                continue

            df = clean_rows(
                rows
            )

            if df.empty:
                print(
                    "  No valid rows after cleaning."
                )
                continue

            df.to_sql(
                "crime_monthly",
                con=engine,
                if_exists="append",
                index=False
            )

            min_date = df["date"].min()
            max_date = df["date"].max()

            print(
                f"  Added {len(df):,} rows "
                f"({min_date.strftime('%Y-%m')} "
                f"to {max_date.strftime('%Y-%m')})"
            )

            completed += 1

            # Small delay to avoid overwhelming API
            time.sleep(0.25)

        except KeyboardInterrupt:
            print()
            print("Stopped by user.")
            print(
                "You can run the script again "
                "and it will skip completed cuadrantes."
            )
            return

        except Exception as e:
            print(
                f"  FAILED: {type(e).__name__}: {e}"
            )

            failed.append(
                cuadrante
            )

    if crime_table_exists():
        create_indexes()

    print()
    print("----------------------------")
    print("Finished loading crime data.")
    print("----------------------------")

    print(
        f"New cuadrantes loaded: {completed}"
    )

    print(
        f"Already loaded/skipped: {skipped}"
    )

    print(
        f"Failed cuadrantes: {len(failed)}"
    )

    if failed:
        print()
        print("Failed list:")

        for cuadrante in failed:
            print(
                f"  {cuadrante}"
            )

    if crime_table_exists():

        with engine.connect() as conn:

            row_count = conn.execute(
                text("""
                    SELECT COUNT(*)
                    FROM crime_monthly;
                """)
            ).scalar()

            cuadrante_count = conn.execute(
                text("""
                    SELECT COUNT(
                        DISTINCT cuadrante
                    )
                    FROM crime_monthly;
                """)
            ).scalar()

            first_date = conn.execute(
                text("""
                    SELECT MIN(date)
                    FROM crime_monthly;
                """)
            ).scalar()

            last_date = conn.execute(
                text("""
                    SELECT MAX(date)
                    FROM crime_monthly;
                """)
            ).scalar()

        print()
        print("Database summary:")
        print(
            f"Total rows: {row_count:,}"
        )
        print(
            f"Cuadrantes loaded: {cuadrante_count}"
        )
        print(
            f"First date: {first_date}"
        )
        print(
            f"Last date: {last_date}"
        )


if __name__ == "__main__":
    main()