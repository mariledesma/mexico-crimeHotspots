"""Metric spatial operations shared by the offline pipeline and dashboard.
KDE = Gaussian event intensity per km² per 30 days, not a population risk rate.
Colocation row instances are cliques, with distinct instances counted once/type.
"""
from itertools import combinations
from collections import defaultdict
import math,time
import numpy as np
from scipy.spatial.distance import cdist
from pyproj import Transformer

TO_METERS=Transformer.from_crs(4326,32614,always_xy=True)
TO_WGS=Transformer.from_crs(32614,4326,always_xy=True)

def project(coords):
    a=np.asarray(coords,dtype=float).reshape(-1,2)
    if not len(a):return a
    x,y=TO_METERS.transform(a[:,0],a[:,1]);return np.column_stack([x,y])

def intensity(points,locations,bandwidth,days=30):
    if bandwidth<=0 or days<=0:raise ValueError('Positive bandwidth and duration required')
    p=np.asarray(points,dtype=float).reshape(-1,2);q=np.asarray(locations,dtype=float).reshape(-1,2)
    result=np.zeros(len(q))
    if len(p):
        for lo in range(0,len(q),256):
            d2=cdist(q[lo:lo+256],p,'sqeuclidean')
            result[lo:lo+256]=np.exp(-d2/(2*bandwidth**2)).sum(axis=1)
    return result/(2*math.pi*bandwidth**2)*1e6*(30/days)

def grid_edges(xy,groups,radius,refine=True):
    """h=r, same/8 neighboring cells: a conservative Euclidean candidate filter."""
    xy=np.asarray(xy);buckets=defaultdict(list);pairs=[]
    for i,(point,g) in enumerate(zip(xy,groups)):
        cell=np.floor(point/radius).astype(int);buckets[(g,*cell)].append(i)
    for i,(point,g) in enumerate(zip(xy,groups)):
        x,y=np.floor(point/radius).astype(int)
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for j in buckets.get((g,x+dx,y+dy),[]):
                    if j>i:pairs.append((i,j))
    edges=np.asarray(pairs,dtype=int).reshape(-1,2)
    if refine and len(edges):
        edges=edges[np.sum((xy[edges[:,0]]-xy[edges[:,1]])**2,axis=1)<=radius**2+1e-8]
    return edges

def ratios(edges,codes,k):
    part=np.zeros((len(codes),k),dtype=bool)
    if len(edges):
        part[edges[:,0],codes[edges[:,1]]]=True
        part[edges[:,1],codes[edges[:,0]]]=True
    output=np.zeros((k,k))
    for a in range(k):
        if np.any(codes==a):output[a]=part[codes==a].mean(axis=0)
    return output

def mine_patterns(xy,types,groups,radius=200,threshold=.1,max_size=3,permutations=0,seed=42,method='grid'):
    start=time.perf_counter();xy=np.asarray(xy,dtype=float).reshape(-1,2)
    if radius<=0 or not 0<=threshold<=1:raise ValueError('Invalid neighborhood settings')
    names=sorted(set(types));codes=np.asarray([names.index(t) for t in types]);k=len(names)
    if len(xy)==0:return {'patterns':[],'stats':{'instances':0,'candidate_patterns':0,'pruned_patterns':0}}
    if method=='baseline':
        es=[]
        for g in sorted(set(groups)):
            ids=np.where(np.asarray(groups)==g)[0]
            for a,b in combinations(ids,2):
                if np.sum((xy[a]-xy[b])**2)<=radius**2+1e-8:es.append((a,b))
        exact=np.asarray(es,dtype=int).reshape(-1,2);coarse=exact;coarse_ratio=ratios(exact,codes,k)
        candidates=list(combinations(range(k),2));checks=sum(sum(np.asarray(groups)==g)*(sum(np.asarray(groups)==g)-1)//2 for g in set(groups))
    else:
        coarse=grid_edges(xy,groups,radius,refine=False);coarse_ratio=ratios(coarse,codes,k)
        candidates=[(a,b) for a,b in combinations(range(k),2) if min(coarse_ratio[a,b],coarse_ratio[b,a])+1e-12>=threshold]
        allowed=set(candidates)
        relevant=np.asarray([tuple(sorted((codes[i],codes[j]))) in allowed for i,j in coarse],dtype=bool)
        es=coarse[relevant];checks=len(es)
        exact=es[np.sum((xy[es[:,0]]-xy[es[:,1]])**2,axis=1)<=radius**2+1e-8] if len(es) else es
    rr=ratios(exact,codes,k);patterns=[];prevalent=set()
    for a,b in candidates:
        pi=float(min(rr[a,b],rr[b,a]))
        if pi+1e-12>=threshold and pi>0:
            prevalent.add((a,b));patterns.append({'types':[names[a],names[b]],'size':2,'pi':pi,'participation':{names[a]:float(rr[a,b]),names[b]:float(rr[b,a])},'p_value':None,'q_value':None})
    triple_candidates=0
    if max_size>=3:
        adj=[set() for _ in xy]
        for i,j in exact:adj[i].add(int(j));adj[j].add(int(i))
        for a,b,c in combinations(range(k),3):
            if not all(p in prevalent for p in [(a,b),(a,c),(b,c)]):continue
            triple_candidates+=1;participants=[set(),set(),set()]
            for i in np.where(codes==a)[0]:
                for j in adj[i]:
                    if codes[j]!=b:continue
                    cs=[z for z in adj[i].intersection(adj[j]) if codes[z]==c]
                    if cs:
                        participants[0].add(int(i));participants[1].add(int(j));participants[2].update(cs)
            pr=[len(v)/sum(codes==t) for v,t in zip(participants,(a,b,c))];pi=min(pr)
            if pi+1e-12>=threshold and pi>0:patterns.append({'types':[names[a],names[b],names[c]],'size':3,'pi':float(pi),'participation':{names[t]:float(v) for t,v in zip((a,b,c),pr)},'p_value':None,'q_value':None})
    # Random-label test: preserve locations and per-month type totals. All pairs
    # enter Benjamini-Hochberg correction, including pairs below the PI cutoff.
    if permutations:
        all_edges=grid_edges(xy,groups,radius);observed=ratios(all_edges,codes,k)
        pairs=list(combinations(range(k),2));obs=np.array([min(observed[a,b],observed[b,a]) for a,b in pairs]);exceed=np.zeros(len(pairs));rng=np.random.default_rng(seed)
        group_indices=[np.where(np.asarray(groups)==g)[0] for g in sorted(set(groups))]
        for _ in range(permutations):
            shuffled=codes.copy()
            for ids in group_indices:shuffled[ids]=rng.permutation(shuffled[ids])
            r=ratios(all_edges,shuffled,k);null=np.array([min(r[a,b],r[b,a]) for a,b in pairs]);exceed+=null>=obs-1e-12
        p=(exceed+1)/(permutations+1);order=np.argsort(p);q=np.empty(len(p));q[order]=np.minimum.accumulate((p[order]*len(p)/np.arange(1,len(p)+1))[::-1])[::-1].clip(0,1)
        tests={(names[a],names[b]):(float(p[i]),float(q[i])) for i,(a,b) in enumerate(pairs)}
        for item in patterns:
            if item['size']==2:item['p_value'],item['q_value']=tests[tuple(item['types'])]
    patterns.sort(key=lambda p:(-p['pi'],p['types']))
    return {'patterns':patterns,'stats':{'instances':len(xy),'candidate_patterns':k*(k-1)//2,'pruned_patterns':k*(k-1)//2-len(candidates),'triple_candidates':triple_candidates,'coarse_edges':len(coarse),'exact_edges':len(exact),'distance_checks':int(checks),'seconds':round(time.perf_counter()-start,4),'method':method,'permutations':permutations},'radius_m':radius,'threshold':threshold,'note':'Spatial association, not causation. Events are neighbors only within the same selected calendar month.'}

def mine_context(xy,types,groups,places,place_types,radius,threshold,permutations=0):
    from scipy.spatial import cKDTree
    start=time.perf_counter();a=sorted(set(types));b=sorted(set(place_types));n=len(xy);names=a+['Place: '+t for t in b]
    if not n or not len(places):return {'patterns':[],'stats':{'instances':n+len(places)},'note':'No comparable crime records or mapped places for this period.'}
    codes=np.array([a.index(t) for t in types]+[len(a)+b.index(t) for t in place_types]);pairs=list((i,j) for i in range(len(a)) for j in range(len(a),len(names)))
    nb=cKDTree(xy).query_ball_tree(cKDTree(places),radius);edges=np.array([(i,n+j) for i,js in enumerate(nb) for j in js],dtype=int).reshape(-1,2)
    observed=ratios(edges,codes,len(names));pi=np.array([min(observed[i,j],observed[j,i]) for i,j in pairs]);p=[None]*len(pairs);q=p.copy()
    if permutations:
        rng=np.random.default_rng(42);ge=np.zeros(len(pairs));groups=np.asarray(groups);indices=[np.where(groups==g)[0] for g in sorted(set(groups))]
        for _ in range(permutations):
            sh=codes.copy()
            for ix in indices:sh[ix]=rng.permutation(sh[ix])
            r=ratios(edges,sh,len(names));ge+=np.array([min(r[i,j],r[j,i]) for i,j in pairs])>=pi-1e-12
        p=(ge+1)/(permutations+1);o=np.argsort(p);q=np.empty(len(p));q[o]=np.minimum.accumulate((p[o]*len(p)/np.arange(1,len(p)+1))[::-1])[::-1].clip(0,1)
    out=[{'types':[names[i],names[j]],'size':2,'pi':float(pi[k]),'participation':{names[i]:float(observed[i,j]),names[j]:float(observed[j,i])},'p_value':None if p[k] is None else float(p[k]),'q_value':None if q[k] is None else float(q[k])} for k,(i,j) in enumerate(pairs) if pi[k]>0 and pi[k]+1e-12>=threshold]
    out.sort(key=lambda p:(-p['pi'],p['types']))
    return {'patterns':out,'stats':{'instances':n+len(places),'candidate_patterns':len(pairs),'exact_edges':len(edges),'seconds':round(time.perf_counter()-start,4),'permutations':permutations,'method':'indexed proximity'},'radius_m':radius,'threshold':threshold,'note':'Exploratory association with the current OSM snapshot. The optional test shuffles crime types among observed locations within months, keeping places fixed; it does not establish that a place caused crime.'}
