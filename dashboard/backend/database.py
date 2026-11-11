import os
from contextlib import contextmanager
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

DASHBOARD_ROOT=Path(__file__).resolve().parents[1]
PROJECT_ROOT=DASHBOARD_ROOT.parent
load_dotenv(PROJECT_ROOT/'.env')
RESULTS=Path(os.getenv('CRIME_RESULTS_DIR',PROJECT_ROOT/'ml-baselines/results'))
if not RESULTS.exists() and (PROJECT_ROOT/'mexico-crime-ml/results').exists():
    RESULTS=PROJECT_ROOT/'mexico-crime-ml/results'

@contextmanager
def connection():
    url=os.getenv('DATABASE_URL','dbname=cdmx_crime')
    url=url.replace('postgresql+psycopg://','postgresql://').replace('postgresql+psycopg2://','postgresql://')
    with psycopg.connect(url,connect_timeout=10,row_factory=dict_row) as conn:
        yield conn

def current_run(conn):
    row=conn.execute('SELECT run_id,metrics,created_at FROM dashboard_prediction_runs ORDER BY created_at DESC,run_id LIMIT 1').fetchone()
    if not row:
        raise RuntimeError('Import the saved predictions before opening the dashboard.')
    return row

MODELS={
 'persistence':'Persistence', 'rolling_mean':'3-month average',
 'random_forest_temporal':'Random Forest · temporal', 'random_forest_spatial':'Random Forest · spatial',
 'xgboost_temporal':'XGBoost · temporal', 'xgboost_spatial':'XGBoost · spatial'
}
