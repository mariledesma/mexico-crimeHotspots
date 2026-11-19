"""Load a completed pilot into separate PostGIS tables in one transaction."""
import csv,json,sys
from pathlib import Path
from psycopg.types.json import Jsonb
from shapely.geometry import shape
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'data/street/processed'
sys.path.insert(0,str(ROOT/'dashboard/backend'))
from database import connection

SCHEMA='''
CREATE TABLE IF NOT EXISTS street_studies(study_id text PRIMARY KEY, published_at timestamptz NOT NULL DEFAULT now(), audit jsonb NOT NULL, metrics jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS street_population(study_id text REFERENCES street_studies ON DELETE CASCADE,segment_id text,year integer,population_200m double precision NOT NULL,population_density_200m double precision NOT NULL,population_change_pct double precision,buffer_area_km2 double precision NOT NULL,PRIMARY KEY(study_id,segment_id,year));
CREATE TABLE IF NOT EXISTS street_segments(study_id text REFERENCES street_studies ON DELETE CASCADE, segment_id text, name text NOT NULL, highway text NOT NULL,length_m double precision NOT NULL,geometry geometry(LineString,4326) NOT NULL, PRIMARY KEY(study_id,segment_id));
CREATE TABLE IF NOT EXISTS crime_events(study_id text REFERENCES street_studies ON DELETE CASCADE, event_id text, crime text NOT NULL,event_date date NOT NULL,hour text,in_study boolean NOT NULL,segment_id text,match_status text NOT NULL,match_distance_m double precision,geometry geometry(Point,4326) NOT NULL,PRIMARY KEY(study_id,event_id),FOREIGN KEY(study_id,segment_id) REFERENCES street_segments);
CREATE TABLE IF NOT EXISTS street_context_places(study_id text REFERENCES street_studies ON DELETE CASCADE,place_id text,category text,name text,geometry geometry(Point,4326),PRIMARY KEY(study_id,place_id));
CREATE TABLE IF NOT EXISTS street_monthly(study_id text REFERENCES street_studies ON DELETE CASCADE,segment_id text,month date,recorded integer NOT NULL,features jsonb NOT NULL,PRIMARY KEY(study_id,segment_id,month),FOREIGN KEY(study_id,segment_id) REFERENCES street_segments);
CREATE TABLE IF NOT EXISTS street_predictions(study_id text REFERENCES street_studies ON DELETE CASCADE,segment_id text,origin_month date,target_month date,actual integer,fold integer,kind text, predictions jsonb NOT NULL,PRIMARY KEY(study_id,segment_id,target_month),FOREIGN KEY(study_id,segment_id) REFERENCES street_segments);
CREATE INDEX IF NOT EXISTS street_event_geom_idx ON crime_events USING gist(geometry);
CREATE INDEX IF NOT EXISTS street_event_date_idx ON crime_events(study_id,event_date,crime);
CREATE INDEX IF NOT EXISTS street_segment_geom_idx ON street_segments USING gist(geometry);
CREATE INDEX IF NOT EXISTS street_month_idx ON street_monthly(study_id,month);
CREATE INDEX IF NOT EXISTS street_prediction_month_idx ON street_predictions(study_id,target_month);
'''

def rows(name):
    with (OUT/name).open() as f:yield from csv.DictReader(f)
def copy(c,sql,values):
    with c.cursor().copy(sql) as w:
        for row in values:w.write_row(row)
def point(r):return f'SRID=4326;POINT({float(r["lon"])} {float(r["lat"])})'

def main():
    audit=json.loads((OUT/'audit.json').read_text());metrics=json.loads((OUT/'metrics.json').read_text());sid=audit['study_id'];assert metrics['study_id']==sid
    geo=json.loads((OUT/'segments.geojson').read_text());models=list(metrics['models'])
    with connection() as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtext('street_analysis_publish'))");c.execute(SCHEMA)
        # Replace only this derived study snapshot, atomically. Citywide tables are untouched.
        c.execute('DELETE FROM street_studies WHERE study_id=%s',(sid,));c.execute('INSERT INTO street_studies(study_id,audit,metrics) VALUES (%s,%s,%s)',(sid,Jsonb(audit),Jsonb(metrics)))
        copy(c,'COPY street_segments FROM STDIN',((sid,f['properties']['segment_id'],f['properties']['name'],f['properties']['highway'],f['properties']['length_m'],'SRID=4326;'+shape(f['geometry']).wkt) for f in geo['features']))
        copy(c,'COPY crime_events FROM STDIN',((sid,r['event_id'],r['crime'],r['date'],r['hour'],r['in_study']=='True',r['segment_id'] or None,r['match_status'],float(r['match_distance_m']) if r['match_distance_m'] else None,point(r)) for r in rows('events.csv')))
        copy(c,'COPY street_context_places FROM STDIN',((sid,r['place_id'],r['category'],r['name'],point(r)) for r in rows('places.csv')))
        copy(c,'COPY street_monthly FROM STDIN',((sid,r['segment_id'],r['month'],int(r['count']),Jsonb({k:float(v) if v else None for k,v in r.items() if k not in {'segment_id','month','count','target_month','target'}})) for r in rows('segment_features.csv')))
        if metrics.get('population'):
            if metrics['population']['study_id'] != sid:
                raise ValueError('Population snapshot belongs to a different study')
            copy(c,'COPY street_population FROM STDIN',((sid,r['segment_id'],int(r['population_year']),float(r['population_200m']),float(r['population_density_200m']),float(r['population_change_pct']) if r['population_change_pct'] else None,float(r['buffer_area_km2'])) for r in rows('population_features.csv')))
            count=c.execute('SELECT count(*) n FROM street_population WHERE study_id=%s',(sid,)).fetchone()['n']
            assert count==audit['segments']*len(metrics['population']['years'])
        copy(c,'COPY street_predictions FROM STDIN',((sid,r['segment_id'],r['month'],r['target_month'],int(float(r['actual'])) if r['actual'] else None,int(r['fold']),r['kind'],Jsonb({m:float(r[m]) for m in models})) for r in rows('predictions.csv')))
        actual=c.execute('SELECT count(*) n,count(*) FILTER(WHERE in_study) study_count,count(segment_id) matched FROM crime_events WHERE study_id=%s',(sid,)).fetchone();assert actual['n']==audit['valid_records'] and actual['study_count']==audit['study_records'] and actual['matched']==audit['matches']['matched']
        expected=audit['segments']*(len(metrics['held_out_months'])+1)
        assert c.execute('SELECT count(*) n FROM street_predictions WHERE study_id=%s',(sid,)).fetchone()['n']==expected
    print(f'Published {sid}: {actual["study_count"]:,} pilot records; {expected:,} predicted segment-months ({len(models)} methods each).')
if __name__=='__main__':main()
