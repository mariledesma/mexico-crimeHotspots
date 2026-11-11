"""Integration check against a running dashboard server; does not change data."""
import csv,io,json,math,os
from urllib.request import urlopen
from urllib.error import HTTPError
BASE=os.getenv('DASHBOARD_URL','http://127.0.0.1:8000')
def get(path):
    with urlopen(BASE+path,timeout=30) as response:return json.load(response)
s=get('/api/summary');g=get('/api/cuadrantes')
assert len(s['areas'])==len(g['features'])==847
assert len(s['months'])==6 and len(s['models'])==6
ids={a['cuadrante'] for a in s['areas']};assert {f['properties']['cuadrante'] for f in g['features']}==ids
for model in s['models']:
    errors=[]
    for month in s['months']:
        rows=get(f'/api/predictions?month={month}&model={model}')['rows']
        assert len(rows)==847 and {r['cuadrante'] for r in rows}==ids
        errors.extend(abs(r['actual']-r['predicted']) for r in rows)
    assert abs(sum(errors)/len(errors)-s['metrics']['test'][model]['MAE'])<1e-5
h=get('/api/history/C-1.2.18?model=xgboost_spatial');assert len(h)==6
with urlopen(BASE+'/api/download?month=2026-08-01&model=xgboost_spatial') as response:
    records=list(csv.DictReader(io.StringIO(response.read().decode())));assert len(records)==847
for path,code in [('/api/predictions?month=2000-01-01',404),('/api/predictions?month=2026-08-01&model=invalid',422),('/api/history/unknown',404)]:
    try:get(path);raise AssertionError('Expected error response')
    except HTTPError as e:assert e.code==code
print('PASS: all 36 month/model combinations, 847 geometries, saved MAE values, history, CSV, and invalid inputs.')
