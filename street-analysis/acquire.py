"""Acquire ONE bounded snapshot; never merge overlapping API queries without IDs."""
import argparse,json,hashlib,subprocess,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode
ROOT=Path(__file__).resolve().parents[1];RAW=ROOT/'data/street/raw'
def download(url,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    pending=path.with_suffix(path.suffix+'.partial')
    subprocess.run(['curl','--fail','--silent','--show-error','--max-time','90','--user-agent','MexicoCrimeResearch/1.0',url,'-o',str(pending)],check=True)
    if path.suffix=='.xml':
        if ET.parse(pending).getroot().tag!='osm':raise ValueError('OSM extract did not contain an osm document')
    else:
        data=json.loads(pending.read_text())
        if not isinstance(data.get('rows',data.get('latlong')),list):raise ValueError('Unexpected crime coordinate response')
    pending.replace(path)
def main():
    p=argparse.ArgumentParser();p.add_argument('--start',default='2023-01');p.add_argument('--end',default='2026-08');p.add_argument('--lon',type=float,default=-99.13333);p.add_argument('--lat',type=float,default=19.43);p.add_argument('--radius',type=int,default=2000);p.add_argument('--name',default='centro');p.add_argument('--with-streets',action='store_true');p.add_argument('--bbox',default='-99.146,19.419,-99.122,19.441',help='OSM west,south,east,north');a=p.parse_args()
    url=f'https://api.hoyodecrimen.com/api/v1/latlong/crimes/all/coords/{a.lon}/{a.lat}/distance/{a.radius}?'+urlencode({'start_date':a.start,'end_date':a.end})
    if not a.name.replace('-','').isalnum():p.error('Snapshot name must contain only letters, digits, and hyphens')
    path=RAW/f'{a.name}-{a.start[:4]}-{a.end[:4]}.json';download(url,path)
    payload=json.loads(path.read_text());rows=payload.get('rows',payload.get('latlong'))
    if not isinstance(rows,list):raise ValueError('Coordinate API returned an unexpected response')
    meta={**vars(a),'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'raw_file':str(path.relative_to(ROOT)),'rows':len(rows),'identity_policy':'Snapshot hash plus source row ordinal; identical-looking records are retained. No overlap merging.'}
    path.with_suffix('.metadata.json').write_text(json.dumps(meta,indent=2));print(json.dumps(meta,indent=2))
    if a.with_streets:
        osm=RAW/f'{a.name}-osm-small.xml';osm_url='https://api.openstreetmap.org/api/0.6/map?'+urlencode({'bbox':a.bbox});download(osm_url,osm)
        osm.with_suffix('.metadata.json').write_text(json.dumps({'url':osm_url,'sha256':hashlib.sha256(osm.read_bytes()).hexdigest(),'retrieved_at':datetime.now(timezone.utc).isoformat()},indent=2))
if __name__=='__main__':main()
