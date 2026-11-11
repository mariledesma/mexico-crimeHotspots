"""Validate saved model evidence and import it atomically; safe to rerun."""
import csv, hashlib, json, math
from datetime import date
from psycopg.types.json import Jsonb
from database import connection,RESULTS,MODELS

def main():
    source=RESULTS/'test_predictions.csv'
    report=json.loads((RESULTS/'metrics.json').read_text())
    digest=hashlib.sha256(source.read_bytes()+(RESULTS/'metrics.json').read_bytes()).hexdigest()
    run='baseline-'+digest[:12]
    records=[];seen=set(); errors={m:[] for m in MODELS}; covered={}
    with source.open() as f:
        for row in csv.DictReader(f):
            q=row['cuadrante'];target=date.fromisoformat(row['target_date'][:10]); origin=date.fromisoformat(row['date'][:10])
            assert target.day==origin.day==1 and (target.year*12+target.month)-(origin.year*12+origin.month)==1
            actual=float(row['target_next_month']); assert math.isfinite(actual) and actual>=0 and actual.is_integer()
            key=(q,target); assert key not in seen,'Duplicate prediction key';seen.add(key)
            covered.setdefault(target,set()).add(q)
            for model in MODELS:
                prediction=float(row[model]);assert math.isfinite(prediction) and prediction>=0
                records.append((run,q,origin,target,model,actual,prediction))
                errors[model].append((actual-prediction)**2)
    assert len(seen)==report['split']['test']['rows']
    for model in MODELS:
        mae=sum(math.sqrt(e) for e in errors[model])/len(seen)
        rmse=math.sqrt(sum(errors[model])/len(seen))
        assert abs(mae-report['test'][model]['MAE'])<1e-5
        assert abs(rmse-report['test'][model]['RMSE'])<1e-5
    with connection() as conn:
        ids={r['cuadrante'] for r in conn.execute('SELECT cuadrante FROM public.cuadrantes')}
        assert all(q==ids for q in covered.values()),'Predictions do not cover every polygon'
        conn.execute('''CREATE TABLE IF NOT EXISTS dashboard_prediction_runs (
          run_id text PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now(),
          source_sha256 text NOT NULL, metrics jsonb NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS dashboard_predictions (
          run_id text NOT NULL REFERENCES dashboard_prediction_runs(run_id),cuadrante text NOT NULL,
          origin_date date NOT NULL,target_date date NOT NULL,model text NOT NULL,
          actual double precision NOT NULL CHECK(actual>=0),predicted double precision NOT NULL CHECK(predicted>=0),
          PRIMARY KEY(run_id,cuadrante,target_date,model))''')
        conn.execute('INSERT INTO dashboard_prediction_runs(run_id,source_sha256,metrics) VALUES (%s,%s,%s) ON CONFLICT(run_id) DO NOTHING',(run,digest,Jsonb(report)))
        with conn.cursor() as cur:
            cur.executemany('INSERT INTO dashboard_predictions VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',records)
        n=conn.execute('SELECT count(*) n FROM dashboard_predictions WHERE run_id=%s',(run,)).fetchone()['n']
        assert n==len(records)
    print(f'Imported and verified {n:,} model predictions across {len(seen):,} observations; run {run}.')
if __name__=='__main__':main()
