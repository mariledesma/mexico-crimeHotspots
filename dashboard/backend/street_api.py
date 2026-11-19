"""Local, read-only analytics for the separately versioned street pilot."""
import calendar,math,sys
from collections import Counter
from datetime import date
from functools import lru_cache
from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from database import connection,PROJECT_ROOT

router=APIRouter(prefix='/api/street')
sys.path.insert(0,str(PROJECT_ROOT/'street-analysis'))

def current(c):
    if not c.execute("SELECT to_regclass('street_studies') present").fetchone()['present']:
        raise HTTPException(404,'Street data has not been prepared. See street-analysis/README.md.')
    row=c.execute('SELECT study_id,published_at,audit,metrics FROM street_studies ORDER BY published_at DESC LIMIT 1').fetchone()
    if not row:raise HTTPException(404,'No street study has been published locally yet')
    return row

def month_shift(m,n):
    i=m.year*12+m.month-1+n;return date(i//12,i%12+1,1)
def period(m,n,audit):
    start=month_shift(m,1-n);stop=month_shift(m,1)
    if m.day!=1 or m.isoformat() not in audit['months'] or start.isoformat() not in audit['months']:
        raise HTTPException(422,'Select a complete period within the saved study dates')
    return start,stop

def event_rows(c,sid,start,stop,crime,core=True):
    return c.execute('''SELECT crime,event_date,match_status,segment_id,ST_X(geometry) lon,ST_Y(geometry) lat FROM crime_events
      WHERE study_id=%s AND event_date >=%s AND event_date <%s AND (%s='' OR crime=%s) AND (%s=false OR in_study)''',(sid,start,stop,crime,crime,core)).fetchall()

def fc(features):return {'type':'FeatureCollection','features':features}
def point(r,props):return {'type':'Feature','geometry':{'type':'Point','coordinates':[r['lon'],r['lat']]},'properties':props}

@router.get('/summary')
def summary():
    with connection() as c:return current(c)

@router.get('/geometry')
def geometry():
    with connection() as c:
        s=current(c);rows=c.execute('SELECT segment_id,name,highway,length_m,ST_AsGeoJSON(geometry)::json geometry FROM street_segments WHERE study_id=%s ORDER BY segment_id',(s['study_id'],)).fetchall()
    return {'boundary':s['audit']['boundary'],'streets':fc([{'type':'Feature','properties':{k:v for k,v in r.items() if k!='geometry'},'geometry':r['geometry']} for r in rows])}

@router.get('/events')
def events(month:date,window:int=Query(1,ge=1,le=12),crime:str=''):
    with connection() as c:
        s=current(c);start,stop=period(month,window,s['audit']);rows=event_rows(c,s['study_id'],start,stop,crime)
    return {'points':fc([point(r,{'crime':r['crime'],'month':r['event_date'].strftime('%Y-%m'),'match_status':r['match_status']}) for r in rows]),'count':len(rows),'from':start,'to_exclusive':stop}

@lru_cache(maxsize=4)
def grid(lon,lat,radius):
    import numpy as np
    from shapely.geometry import Point,box,mapping
    from shapely import transform
    from spatial import project,TO_WGS
    center=project([[lon,lat]])[0];circle=Point(center).buffer(radius,quad_segs=64);features=[];xy=[]
    # Shared fixed metric grid for all periods and bandwidths.
    for x in np.arange(center[0]-radius,center[0]+radius,100):
        for y in np.arange(center[1]-radius,center[1]+radius,100):
            cell=box(x,y,x+100,y+100).intersection(circle)
            if cell.is_empty or cell.area<100:continue
            p=cell.centroid;xy.append([p.x,p.y]);features.append(mapping(transform(cell,TO_WGS.transform,interleaved=False)))
    return np.array(xy),features

def density(rows,xy,bw,days):
    from spatial import project,intensity
    return intensity(project([[r['lon'],r['lat']] for r in rows]),xy,bw,days)

@lru_cache(maxsize=96)
def reference(sid,version,crime,bw,window,lon,lat,radius,start,end):
    import numpy as np
    xy,_=grid(lon,lat,radius);values=[]
    with connection() as c:
        m=month_shift(start,window-1)
        while m<=end:
            a,b=month_shift(m,1-window),month_shift(m,1)
            values.append(density(event_rows(c,sid,a,b,crime,core=False),xy,bw,(b-a).days));m=month_shift(m,1)
    z=np.concatenate(values) if values else np.array([0.]);return float(np.quantile(z,.90)),max(1.,float(np.quantile(z,.99)))

@router.get('/density')
def kde(month:date,compare:date|None=None,window:int=Query(1,ge=1,le=12),crime:str='',bandwidth:int=200):
    if bandwidth not in (100,200,400):raise HTTPException(422,'Bandwidth must be 100, 200, or 400 meters')
    with connection() as c:
        s=current(c);a=s['audit'];sid=s['study_id'];start,stop=period(month,window,a);cfg=a['config'];lon,lat=cfg['center'];radius=cfg['radius_m'];xy,shapes=grid(lon,lat,radius)
        raw=event_rows(c,sid,start,stop,crime,core=False);v=density(raw,xy,bandwidth,(stop-start).days);core=len(event_rows(c,sid,start,stop,crime));b=None;count_other=None
        if compare:
            lo,hi=period(compare,window,a);b=density(event_rows(c,sid,lo,hi,crime,core=False),xy,bandwidth,(hi-lo).days);count_other=len(event_rows(c,sid,lo,hi,crime))
    end=date.fromisoformat(s['metrics']['folds'][0]['train_target_end']);threshold,scale=reference(sid,s['published_at'],crime,bandwidth,window,lon,lat,radius,date.fromisoformat(a['months'][0]),end)
    cells=fc([{'type':'Feature','geometry':g,'properties':{'value':round(float(v[i]-(b[i] if b is not None else 0)),3),'density':round(float(v[i]),3),'comparison':round(float(b[i]),3) if b is not None else None,'hotspot':bool(threshold>0 and v[i]>=threshold)}} for i,g in enumerate(shapes)])
    return {'cells':cells,'events':core,'comparison_events':count_other,'threshold':threshold,'scale':scale,'unit':'records / km² / 30 days','bandwidth_m':bandwidth,'grid_m':100,'comparison':compare is not None,'reference_end':end}

@router.get('/counts')
def counts(month:date,compare:date|None=None,window:int=Query(1,ge=1,le=12),crime:str=''):
    with connection() as c:
        s=current(c);start,stop=period(month,window,s['audit']);a=Counter(r['segment_id'] for r in event_rows(c,s['study_id'],start,stop,crime) if r['segment_id']);b={}
        if compare:
            lo,hi=period(compare,window,s['audit']);b=Counter(r['segment_id'] for r in event_rows(c,s['study_id'],lo,hi,crime) if r['segment_id'])
    return {'counts':dict(a),'comparison':dict(b),'total':sum(a.values()),'comparison_total':sum(b.values()) if compare else None}

@router.get('/patterns')
def patterns(month:date,window:int=Query(1,ge=1,le=12),scope:Literal['crime','places']='crime',radius:int=Query(200,ge=50,le=500),threshold:float=Query(.1,ge=0,le=1),test:bool=False,method:Literal['grid','baseline']='grid'):
    from spatial import project,mine_patterns,mine_context
    with connection() as c:
        s=current(c);start,stop=period(month,window,s['audit']);rows=event_rows(c,s['study_id'],start,stop,'');places=[]
        if scope=='places':places=c.execute('SELECT category,ST_X(geometry) lon,ST_Y(geometry) lat FROM street_context_places WHERE study_id=%s',(s['study_id'],)).fetchall()
    labels=[r['crime'] for r in rows];counts=Counter(labels);rows=[r for r in rows if counts[r['crime']]>=5];xy=project([[r['lon'],r['lat']] for r in rows]);types=[r['crime'] for r in rows];groups=[r['event_date'].strftime('%Y-%m') for r in rows]
    if scope=='places':return mine_context(xy,types,groups,project([[p['lon'],p['lat']] for p in places]),[p['category'] for p in places],radius,threshold,99 if test else 0)
    return mine_patterns(xy,types,groups,radius,threshold,permutations=99 if test else 0,method=method)

@router.get('/predictions')
def predictions(month:date,model:str):
    with connection() as c:
        s=current(c)
        if model not in s['metrics']['models']:raise HTTPException(422,'Unknown street model')
        rows=c.execute('SELECT segment_id,actual,kind,origin_month,(predictions->>%s)::double precision predicted FROM street_predictions WHERE study_id=%s AND target_month=%s',(model,s['study_id'],month)).fetchall()
    if not rows:raise HTTPException(404,'No street predictions for that month')
    return {'rows':rows,'kind':rows[0]['kind'],'origin_month':rows[0]['origin_month']}

@router.get('/history/{segment_id}')
def history(segment_id:str,model:str):
    with connection() as c:
        s=current(c)
        if model not in s['metrics']['models']:raise HTTPException(422,'Unknown street model')
        rows=c.execute('''SELECT m.month,m.recorded AS actual,(p.predictions->>%s)::double precision predicted
          FROM street_monthly m LEFT JOIN street_predictions p ON p.study_id=m.study_id AND p.segment_id=m.segment_id AND p.target_month=m.month
          WHERE m.study_id=%s AND m.segment_id=%s ORDER BY m.month''',(model,s['study_id'],segment_id)).fetchall()
        extra=c.execute("SELECT target_month AS month,actual,(predictions->>%s)::double precision predicted FROM street_predictions WHERE study_id=%s AND segment_id=%s AND kind='beyond_snapshot'",(model,s['study_id'],segment_id)).fetchall()
    if not rows:raise HTTPException(404,'Unknown segment')
    return rows+extra

@router.get('/places')
def places():
    with connection() as c:
        s=current(c);r=c.execute('SELECT category,name,ST_X(geometry) lon,ST_Y(geometry) lat FROM street_context_places WHERE study_id=%s',(s['study_id'],)).fetchall()
    return fc([point(x,{'category':x['category'],'name':x['name']}) for x in r])


@router.get('/population')
def population(year:int=Query(...,ge=2015,le=2030)):
    with connection() as c:
        study=current(c)
        metadata=study['metrics'].get('population')
        if not metadata:
            raise HTTPException(404,'Population context has not been prepared and published')
        if year not in metadata['years']:
            raise HTTPException(422,'Select a year in the saved population snapshot')
        rows=c.execute('SELECT segment_id,population_200m,population_density_200m,population_change_pct FROM street_population WHERE study_id=%s AND year=%s ORDER BY segment_id',(study['study_id'],year)).fetchall()
    return {'year':year,'rows':rows,'unit':'estimated residents per km² within 200 m',
            'scale':metadata['density_scale'],
            'interpretation':metadata['interpretation']}
