import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.environ["DATABASE_URL"])

with engine.connect() as conn:
    version = conn.execute(text("SELECT PostGIS_Version();")).scalar()
    count = conn.execute(text("SELECT COUNT(*) FROM cuadrantes;")).scalar()

print("PostGIS version:", version)
print("Cuadrantes loaded:", count)
