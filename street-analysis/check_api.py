"""Verify the running local street API and original citywide endpoints."""
import json,os,urllib.parse,urllib.request
BASE=os.environ.get('DASHBOARD_URL','http://127.0.0.1:8000')
def fetch(path,**q):
    with urllib.request.urlopen(BASE+path+('?' + urllib.parse.urlencode(q) if q else ''),timeout=35) as r:return json.load(r)
s=fetch('/api/street/summary');a=s['audit'];m=s['metrics'];last=a['months'][-1];prior=a['months'][-4]
g=fetch('/api/street/geometry');assert len(g['streets']['features'])==a['segments']
e=fetch('/api/street/events',month=last,window=3);assert e['count']==len(e['points']['features'])>0
crime=e['points']['features'][0]['properties']['crime'];f=fetch('/api/street/events',month=last,window=3,crime=crime)
assert 0<f['count']<=e['count'] and all(p['properties']['crime']==crime for p in f['points']['features'])
for bw in [100,200,400]:
 d=fetch('/api/street/density',month=last,compare=prior,window=3,bandwidth=bw);r=fetch('/api/street/density',month=prior,compare=last,window=3,bandwidth=bw)
 assert d['scale']==r['scale'] and d['threshold']==r['threshold']
 assert d['events']==e['count'] and len(d['cells']['features'])>300
 assert all(abs(p['properties']['value']+q['properties']['value'])<.001 for p,q in zip(d['cells']['features'],r['cells']['features']))
c=fetch('/api/street/counts',month=last,compare=prior,window=3);assert c['total']==sum(c['counts'].values())<=e['count']
p=fetch('/api/street/patterns',month=last,window=3,threshold=.05);q=fetch('/api/street/patterns',month=last,window=3,threshold=.05,method='baseline');assert p['patterns']==q['patterns'] and len(p['patterns'])>0
ctx=fetch('/api/street/patterns',month=last,window=3,scope='places',threshold=.01,test='true');assert ctx['patterns'] and all(v['p_value']<=v['q_value']<=1 for v in ctx['patterns'])
for target,kind in [(last,'held_out'),(m['forecast_month'],'beyond_snapshot')]:
 r=fetch('/api/street/predictions',month=target,model='xgb_kde');assert len(r['rows'])==a['segments'] and r['kind']==kind
 assert all(x['predicted']>=0 and (x['actual'] is None)==(kind=='beyond_snapshot') for x in r['rows'])
h=fetch('/api/street/history/'+r['rows'][0]['segment_id'],model='xgb_kde');assert len(h)==len(a['months'])+1
assert len(fetch('/api/summary')['areas'])==847
assert len(fetch('/api/street/places')['features'])==a['places']
print(f'PASS: point filters, fixed KDE/change scales, counts, exact/grid patterns, contextual random-label test, {a["segments"]} predictions, history, and original dashboard.')

if m.get('population'):
    for year in [m['population']['years'][0],m['population']['years'][-1]]:
        population=fetch('/api/street/population',year=year)
        assert len(population['rows'])==a['segments']
        assert all(r['population_200m']>=0 and r['population_density_200m']>=0 for r in population['rows'])
    for name in ['rf_kde','rf_population','xgb_population']:
        prediction=fetch('/api/street/predictions',month=last,model=name)
        assert len(prediction['rows'])==a['segments'] and all(r['predicted']>=0 for r in prediction['rows'])
    assert sum(g['xgb_kde']['rows'] for g in m['population']['density_groups'].values())==m['aggregate']['xgb_kde']['rows']
    print('PASS: WorldPop population coverage, new model predictions, and density group counts.')
