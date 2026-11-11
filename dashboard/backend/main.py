import csv,io,json,logging
from datetime import date
from pathlib import Path
from fastapi import FastAPI,HTTPException,Query
from fastapi.responses import Response,FileResponse
from fastapi.staticfiles import StaticFiles
from database import connection,current_run,MODELS,DASHBOARD_ROOT

from street_api import router as street_router

app=FastAPI(title='Mexico City Crime Prediction Explorer',version='1.1.0')
app.include_router(street_router)

def model_valid(model):
    if model not in MODELS:raise HTTPException(422,'Unknown prediction model')

@app.get('/api/health')
def health():
    try:
        with connection() as c:
            run=current_run(c)
        return {'status':'ok','run_id':run['run_id']}
    except Exception:
        logging.exception('Dashboard database check failed')
        raise HTTPException(503,'Database unavailable or predictions not imported. See dashboard setup instructions.')

@app.get('/api/summary')
def summary():
    with connection() as c:
        run=current_run(c)
        months=[r['target_date'].isoformat() for r in c.execute('SELECT DISTINCT target_date FROM dashboard_predictions WHERE run_id=%s ORDER BY target_date',(run['run_id'],))]
        areas=c.execute('SELECT cuadrante,alcaldia,sector FROM public.cuadrantes ORDER BY cuadrante').fetchall()
    return {'run_id':run['run_id'],'models':MODELS,'months':months,'areas':areas,'metrics':run['metrics']}

@app.get('/api/cuadrantes')
def boundaries():
    with connection() as c:
        rows=c.execute('''SELECT cuadrante,alcaldia,sector,ST_AsGeoJSON(ST_SimplifyPreserveTopology(geometry,0.00003))::json AS geometry FROM public.cuadrantes ORDER BY cuadrante''').fetchall()
    return {'type':'FeatureCollection','features':[{'type':'Feature','properties':{k:r[k] for k in ('cuadrante','alcaldia','sector')},'geometry':r['geometry']} for r in rows]}

@app.get('/api/predictions')
def predictions(month:date,model:str='xgboost_spatial'):
    model_valid(model)
    with connection() as c:
        run=current_run(c)
        rows=c.execute('SELECT cuadrante,actual,predicted,abs(actual-predicted) absolute_error FROM dashboard_predictions WHERE run_id=%s AND target_date=%s AND model=%s ORDER BY cuadrante',(run['run_id'],month,model)).fetchall()
    if not rows:raise HTTPException(404,'No saved test predictions for that month')
    return {'month':month,'model':model,'rows':rows}

@app.get('/api/history/{cuadrante}')
def history(cuadrante:str,model:str='xgboost_spatial'):
    model_valid(model)
    with connection() as c:
        run=current_run(c)
        rows=c.execute('SELECT target_date,actual,predicted,abs(actual-predicted) absolute_error FROM dashboard_predictions WHERE run_id=%s AND cuadrante=%s AND model=%s ORDER BY target_date',(run['run_id'],cuadrante,model)).fetchall()
    if not rows:raise HTTPException(404,'Cuadrante not found')
    return rows

@app.get('/api/download')
def download(month:date,model:str='xgboost_spatial'):
    payload=predictions(month,model)
    stream=io.StringIO();w=csv.writer(stream);w.writerow(['cuadrante','target_month','model','actual','predicted','absolute_error'])
    for r in payload['rows']:w.writerow([r['cuadrante'],month,model,r['actual'],r['predicted'],r['absolute_error']])
    return Response(stream.getvalue(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="cdmx-{month}-{model}.csv"'})

# A built frontend can run from this same server, without Node.js at runtime.
dist=DASHBOARD_ROOT/'frontend/dist'
if dist.exists():
    app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
    @app.get('/')
    @app.get('/streets')
    def index():return FileResponse(dist/'index.html')
