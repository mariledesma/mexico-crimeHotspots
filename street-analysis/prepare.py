"""Validate a single crime snapshot, build real OSM street sections, audit matches."""
import argparse,csv,hashlib,json,math,xml.etree.ElementTree as ET
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
from shapely.geometry import Point,LineString,mapping
from shapely.ops import substring
from shapely import transform as shapely_transform

def transform(fn,geometry):
    return shapely_transform(geometry,fn,interleaved=False)
from shapely.strtree import STRtree
from spatial import TO_METERS,TO_WGS,project
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'data/street/processed'
ROAD_TYPES={'primary','secondary','tertiary','residential','unclassified','living_street','pedestrian','service','trunk','primary_link','secondary_link','tertiary_link'}

def load_events(path,start,end):
    if path.suffix.lower()=='.csv':
        with path.open() as f:rows=list(csv.DictReader(f))
        required={'source_id','crime','date','lat','long'}
        if not rows or not required.issubset(rows[0]):raise ValueError('CSV needs source_id,crime,date,lat,long (hour optional)')
        ids=[str(r['source_id']).strip() for r in rows]
        if any(not x for x in ids) or len(ids)!=len(set(ids)):raise ValueError('CSV source IDs must be present and unique')
    else:
        data=json.loads(path.read_text());rows=data.get('rows',data.get('latlong'))
        if not isinstance(rows,list):raise ValueError('API response must contain an array of rows')
    digest=hashlib.sha256(path.read_bytes()).hexdigest();events=[];bad=Counter()
    for i,r in enumerate(rows):
        try:
            lon=float(r['long']);lat=float(r['lat']);when=pd.Timestamp(r['date']);crime=str(r['crime']).strip()
            if not math.isfinite(lon+lat) or not -100.5<lon<-98 or not 18<lat<21:raise ValueError()
            if pd.isna(when) or not crime or crime=='None':raise ValueError()
            if not start<=when<=end:bad['outside_requested_dates']+=1;continue
        except (ValueError,KeyError,TypeError):bad['invalid_record']+=1;continue
        events.append({'event_id':str(r.get('source_id',f'{digest[:16]}:{i}')),'source_row':i,'crime':crime,'date':when.date().isoformat(),'month':when.strftime('%Y-%m-01'),'hour':str(r.get('hour','')),'lon':lon,'lat':lat})
    return events,digest,dict(bad),len(rows)

def read_osm(path,clip):
    tree=ET.parse(path);root=tree.getroot();nodes={};node_tags={};ways=[]
    for el in root.findall('node'):
        i=el.attrib['id'];nodes[i]=(float(el.attrib['lon']),float(el.attrib['lat']));node_tags[i]={t.attrib['k']:t.attrib['v'] for t in el.findall('tag')}
    for el in root.findall('way'):
        tags={t.attrib['k']:t.attrib['v'] for t in el.findall('tag')};refs=[n.attrib['ref'] for n in el.findall('nd')]
        if len(refs)>=2 and all(n in nodes for n in refs):ways.append({'id':el.attrib['id'],'tags':tags,'refs':refs})
    roads=[w for w in ways if w['tags'].get('highway') in ROAD_TYPES and w['tags'].get('area')!='yes' and w['tags'].get('access') not in {'no','private'}]
    uses=Counter(n for w in roads for n in set(w['refs']));segments=[]
    for w in roads:
        refs=w['refs'];cuts=[0]+[i for i in range(1,len(refs)-1) if uses[refs[i]]>1]+[len(refs)-1]
        for ci,(a,b) in enumerate(zip(cuts,cuts[1:])):
            line=transform(TO_METERS.transform,LineString([nodes[n] for n in refs[a:b+1]]))
            if line.length<2 or not line.intersects(clip):continue
            clipped=line.intersection(clip);parts=[clipped] if clipped.geom_type=='LineString' else [g for g in getattr(clipped,'geoms',[]) if g.geom_type=='LineString']
            for pi,part in enumerate(parts):
                if part.length<10:continue
                count=math.ceil(part.length/200)
                keys=[f'osm-node:{refs[a]}' if Point(part.coords[0]).distance(Point(line.coords[0]))<.1 else f'clip:{w["id"]}:{ci}:{pi}:0']
                keys += [f'part:{w["id"]}:{ci}:{pi}:{k}' for k in range(1,count)]
                keys += [f'osm-node:{refs[b]}' if Point(part.coords[-1]).distance(Point(line.coords[-1]))<.1 else f'clip:{w["id"]}:{ci}:{pi}:end']
                for k in range(count):
                    geom=substring(part,k*part.length/count,(k+1)*part.length/count)
                    sid=f'osm-{w["id"]}-{ci}-{pi}-{k}'
                    segments.append({'segment_id':sid,'name':w['tags'].get('name',w['tags'].get('ref','Unnamed street')),'highway':w['tags']['highway'],'length_m':geom.length,'start_key':keys[k],'end_key':keys[k+1],'geometry':geom})
    pois=[]
    def category(tags):
        if tags.get('amenity') in {'bar','pub','nightclub'}:return 'Nightlife'
        if tags.get('amenity') in {'restaurant','cafe','fast_food'}:return 'Food and drink'
        if tags.get('amenity') in {'bank','atm'}:return 'Bank / ATM'
        if tags.get('amenity')=='marketplace' or tags.get('shop') in {'supermarket','convenience','mall'}:return 'Retail / market'
        if tags.get('railway')=='station' or tags.get('public_transport') in {'station','platform'}:return 'Transit'
    for i,tags in node_tags.items():
        c=category(tags)
        if c:
            p=transform(TO_METERS.transform,Point(nodes[i]))
            if clip.covers(p):pois.append({'place_id':'node:'+i,'category':c,'name':tags.get('name',c),'point':p})
    for w in ways:
        c=category(w['tags'])
        if c:
            p=transform(TO_METERS.transform,LineString([nodes[n] for n in w['refs']])).centroid
            if clip.covers(p):pois.append({'place_id':'way:'+w['id'],'category':c,'name':w['tags'].get('name',c),'point':p})
    return segments,pois

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--events',type=Path,default=ROOT/'data/street/raw/centro-2023-2026.json');parser.add_argument('--osm',type=Path,default=ROOT/'data/street/raw/centro-osm-small.xml');parser.add_argument('--radius',type=float,default=1000);parser.add_argument('--lon',type=float,default=-99.13333);parser.add_argument('--lat',type=float,default=19.43);parser.add_argument('--start',default='2023-01-01');parser.add_argument('--end',default='2026-08-31');parser.add_argument('--match-distance',type=float,default=50);a=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True);center=project([[a.lon,a.lat]])[0];clip=Point(center).buffer(a.radius,quad_segs=64)
    events,sha,bad,raw_count=load_events(a.events,pd.Timestamp(a.start),pd.Timestamp(a.end));coords=project([[r['lon'],r['lat']] for r in events]);retained=[]
    for r,xy in zip(events,coords):
        r.update(x=float(xy[0]),y=float(xy[1]),in_study=bool(np.linalg.norm(xy-center)<=a.radius))
        # Buffer records are retained for KDE; they are not assigned pilot street counts.
        retained.append(r)
    segments,pois=read_osm(a.osm,clip)
    if not segments:raise ValueError('No real road geometries in this study area')
    geoms=[s['geometry'] for s in segments];tree=STRtree(geoms);matches=Counter()
    for r in retained:
        r.update(segment_id='',match_status='buffer',match_distance_m=None)
        if not r['in_study']:continue
        p=Point(r['x'],r['y']);indices=tree.query(p.buffer(a.match_distance))
        candidates=sorted([(p.distance(geoms[i]),int(i)) for i in indices])
        if not candidates or candidates[0][0]>a.match_distance:r['match_status']='too_far'
        elif len(candidates)>1 and candidates[1][0]-candidates[0][0]<=3:r['match_status']='ambiguous'
        else:r['match_status']='matched';r['segment_id']=segments[candidates[0][1]]['segment_id']
        r['match_distance_m']=candidates[0][0] if candidates else None;matches[r['match_status']]+=1
    pd.DataFrame(retained).to_csv(OUT/'events.csv',index=False)
    topology=defaultdict(set)
    for s in segments:
        topology[s['start_key']].add(s['segment_id']);topology[s['end_key']].add(s['segment_id'])
    edges=set()
    for ids in topology.values():
        for x in ids:
            for y in ids:
                if x!=y:edges.add((x,y))
    pd.DataFrame(sorted(edges),columns=['segment_id','neighbor']).to_csv(OUT/'neighbors.csv',index=False)
    geo={'type':'FeatureCollection','features':[]}
    for s in segments:
        geo['features'].append({'type':'Feature','properties':{k:v for k,v in s.items() if k!='geometry'},'geometry':mapping(transform(TO_WGS.transform,s['geometry']))})
    (OUT/'segments.geojson').write_text(json.dumps(geo,separators=(',',':')))
    poirows=[]
    for p in pois:
        lon,lat=TO_WGS.transform(p['point'].x,p['point'].y);poirows.append({k:v for k,v in p.items() if k!='point'}|{'lon':lon,'lat':lat,'x':p['point'].x,'y':p['point'].y})
    pd.DataFrame(poirows,columns=['place_id','category','name','lon','lat','x','y']).to_csv(OUT/'places.csv',index=False)
    config={'center':[a.lon,a.lat],'radius_m':a.radius,'start':a.start,'end':a.end,'match_distance_m':a.match_distance,'ambiguity_margin_m':3,'max_segment_length_m':200}
    osm_sha=hashlib.sha256(a.osm.read_bytes()).hexdigest();dataset='centro-'+hashlib.sha256((sha+osm_sha+json.dumps(config,sort_keys=True)).encode()).hexdigest()[:12]
    months=pd.date_range(pd.Timestamp(a.start).replace(day=1),pd.Timestamp(a.end).replace(day=1),freq='MS').strftime('%Y-%m-01').tolist()
    audit={'study_id':dataset,'title':'Centro street-level pilot','prepared_at':datetime.now(timezone.utc).isoformat(),'config':config,'source_sha256':sha,'osm_sha256':osm_sha,'source_rows':raw_count,'validation_rejections':bad,'valid_records':len(retained),'study_records':sum(r['in_study'] for r in retained),'buffer_records':sum(not r['in_study'] for r in retained),'matches':dict(matches),'segments':len(segments),'places':len(pois),'months':months,'crime_types':sorted({r['crime'] for r in retained if r['in_study']}),'source':('Normalized geocoded CSV with source IDs' if a.events.suffix.lower()=='.csv' else 'HoyoDeCrimen coordinate API; single nonoverlapping snapshot'),'source_url':'https://api.hoyodecrimen.com/','osm_source':'OpenStreetMap API 0.6 bounded extract','coordinate_accuracy':'Not independently verified; nearest-street association is an approximation, not an observed street address.','coverage':'Bounded pilot; source completeness and historical publication delays are not independently verified. Zero counts mean no records in this snapshot.','identity':'Source IDs when supplied; otherwise snapshot hash + source row ordinal. Identical-looking records are preserved; overlapping crime-query snapshots are not merged.','context':'Business/transit and road locations are a current OSM snapshot, not historical openings/closures. POIs are exploratory only and excluded from historical predictive features.','crs':'EPSG:32614 (meters)','boundary':mapping(transform(TO_WGS.transform,clip))}
    (OUT/'audit.json').write_text(json.dumps(audit,indent=2));print(json.dumps({k:audit[k] for k in ['study_id','source_rows','study_records','matches','segments','places']},indent=2))
if __name__=='__main__':main()
