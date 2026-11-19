"""Walk-forward experiments on matched segment-month counts (CPU)."""
from itertools import combinations
from pathlib import Path
import argparse,hashlib,json,math
import numpy as np
import pandas as pd
from shapely.geometry import shape
from shapely import transform
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error,mean_squared_error
from xgboost import XGBRegressor
from prepare import OUT
from spatial import intensity,grid_edges,mine_patterns,TO_METERS

MODELS={
 'zero':'Always zero','persistence':'Repeat last month','rolling':'3-month average','kde':'Historical KDE allocation',
 'rf_history':'Random Forest · history','rf_neighbors':'Random Forest · + neighbors','rf_patterns':'Random Forest · + KDE and colocation',
 'xgb_history':'XGBoost · history','xgb_neighbors':'XGBoost · + neighbors','xgb_kde':'XGBoost · + KDE','xgb_patterns':'XGBoost · + KDE and colocation',
}
BASE=['count','lag_1','lag_3','mean_3','mean_6','month_sin','month_cos','year','length_m']
NEAR=BASE+['neighbor_count','neighbor_mean','neighbor_lag_1']
BANDWIDTHS=[100,200,400]

def captured(y,p):
    """Expected capture when equally scored segments straddle the 10% cutoff."""
    if not len(y):return 0.
    k=max(1,math.ceil(.1*len(y)));cut=np.sort(p)[-k];high=p>cut;ties=p==cut
    return float(y[high].sum()+y[ties].sum()*(k-high.sum())/ties.sum())

def score(d,p):
    y=d.target.to_numpy(dtype=float);pos=y>0;capture=0.
    for ix in d.groupby('target_month',sort=False).indices.values():capture+=captured(y[ix],p[ix])
    return {'mae':float(mean_absolute_error(y,p)),'rmse':float(mean_squared_error(y,p)**.5),'nonzero_mae':float(mean_absolute_error(y[pos],p[pos])) if pos.any() else None,'capture_top_10pct':float(capture/y.sum()) if y.sum() else None,'recorded':int(y.sum()),'rows':len(y)}

def estimator(name):
    if name.startswith('rf'):return RandomForestRegressor(n_estimators=90,min_samples_leaf=8,max_features=.8,n_jobs=2,random_state=42)
    return XGBRegressor(n_estimators=160,max_depth=4,learning_rate=.05,subsample=.8,colsample_bytree=.9,objective='count:poisson',n_jobs=2,random_state=42,tree_method='hist')

def build_panel(events,geo,months):
    matched=events[events.match_status.eq('matched')];ids=[f['properties']['segment_id'] for f in geo['features']]
    length=np.array([f['properties']['length_m'] for f in geo['features']]);mid=[]
    for f in geo['features']:
        g=transform(shape(f['geometry']),TO_METERS.transform,interleaved=False);p=g.interpolate(.5,normalized=True);mid.append([p.x,p.y])
    panel=pd.MultiIndex.from_product([ids,months],names=['segment_id','month']).to_frame(index=False)
    counts=matched.groupby(['segment_id','month']).size().rename('count');panel=panel.join(counts,on=['segment_id','month']);panel['count']=panel['count'].fillna(0).astype(int)
    panel['month']=pd.to_datetime(panel.month);panel['target_month']=panel.month+pd.offsets.MonthBegin(1);panel['target']=panel.groupby('segment_id')['count'].shift(-1)
    g=panel.groupby('segment_id')['count'];panel['lag_1']=g.shift(1);panel['lag_3']=g.shift(3)
    for k in [3,6]:panel[f'mean_{k}']=g.transform(lambda s:s.rolling(k).mean())
    panel['year']=panel.month.dt.year;panel['month_sin']=np.sin(2*np.pi*panel.month.dt.month/12);panel['month_cos']=np.cos(2*np.pi*panel.month.dt.month/12);panel['length_m']=panel.segment_id.map(dict(zip(ids,length)))
    edges=pd.read_csv(OUT/'neighbors.csv');d=edges.merge(panel[['segment_id','month','count','lag_1']],left_on='neighbor',right_on='segment_id',suffixes=('','_other'))
    near=d.groupby(['segment_id','month']).agg(neighbor_count=('neighbor','size'),neighbor_mean=('count','mean'),neighbor_lag_1=('lag_1','mean'))
    panel=panel.join(near,on=['segment_id','month']);panel[['neighbor_count','neighbor_mean','neighbor_lag_1']]=panel[['neighbor_count','neighbor_mean','neighbor_lag_1']].fillna(0)
    for bw in BANDWIDTHS:
        values={};allocation={}
        for m in pd.to_datetime(months):
            start=m-pd.DateOffset(months=2);stop=m+pd.offsets.MonthBegin(1);a=events[(events.month>=start.strftime('%Y-%m-01'))&(events.month<=m.strftime('%Y-%m-01'))]
            q=intensity(a[['x','y']].to_numpy(),mid,bw,days=(stop-start).days);weights=q*length
            count_mean=float(a.match_status.eq('matched').sum()/3)
            for i,s in enumerate(ids):values[(s,m)]=q[i];allocation[(s,m)]=weights[i]/weights.sum()*count_mean if weights.sum()>0 else 0.
        keys=list(zip(panel.segment_id,panel.month));panel[f'kde_{bw}']=[values[k] for k in keys];panel[f'kde_alloc_{bw}']=[allocation[k] for k in keys]
    return panel

def choose_patterns(events,train_end):
    subset=events[events.in_study & (events.month<=train_end.strftime('%Y-%m-01'))].copy()
    frequent=subset.crime.value_counts();subset=subset[subset.crime.isin(frequent[frequent>=15].index)]
    r=mine_patterns(subset[['x','y']].to_numpy(),subset.crime.tolist(),subset.month.tolist(),radius=200,threshold=.05,max_size=2)
    return [tuple(row['types']) for row in r['patterns'][:4]]

def pattern_features(panel,events,pairs):
    e=events[events.in_study].reset_index(drop=True);pairs_found=grid_edges(e[['x','y']].to_numpy(),e.month.tolist(),200)
    labels=e.crime.to_numpy();p=panel.copy();cols=[]
    for k,(a,b) in enumerate(pairs):
        i,j=pairs_found.T;mask=((labels[i]==a)&(labels[j]==b))|((labels[i]==b)&(labels[j]==a));ids=np.unique(pairs_found[mask].ravel())
        participating=e.iloc[ids];participating=participating[participating.match_status.eq('matched')];values=participating.groupby(['segment_id','month']).size()
        name=f'pattern_{k+1}';p[name]=[values.get((s,m.strftime('%Y-%m-01')),0) for s,m in zip(p.segment_id,p.month)];cols.append(name)
    return p,cols

def subsets(kde,patterns):
    return {'rf_history':BASE,'rf_neighbors':NEAR,'rf_patterns':NEAR+[kde]+patterns,'xgb_history':BASE,'xgb_neighbors':NEAR,'xgb_kde':NEAR+[kde],'xgb_patterns':NEAR+[kde]+patterns}

def rank(metrics):
    return (-(metrics['capture_top_10pct'] or 0),metrics['mae'])

def add_population(panel, audit):
    manifest=json.loads((OUT/'population.json').read_text())
    if manifest['study_id'] != audit['study_id']:
        raise ValueError('Population features belong to another study')
    for filename, key in [('segments.geojson','segments_sha256'),('population_features.csv','features_sha256')]:
        if hashlib.sha256((OUT/filename).read_bytes()).hexdigest() != manifest[key]:
            raise ValueError('Population features or street geometry changed; rerun population.py')
    population=pd.read_csv(OUT/'population_features.csv')
    if population.duplicated(['segment_id','population_year']).any():
        raise ValueError('Duplicate population rows')
    p=panel.assign(population_year=panel.month.dt.year).merge(population,on=['segment_id','population_year'],how='left',validate='many_to_one')
    required=['population_200m','population_density_200m']
    if p[required].isna().any().any() or not np.isfinite(p[required]).all().all():
        raise ValueError('Population data does not cover every street and origin year')
    p['population_change_defined']=p.population_change_pct.notna().astype(int)
    p['population_change_pct']=p.population_change_pct.fillna(0)
    return p, manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--population',action='store_true',help='Include explicitly retrospective WorldPop comparisons')
    args=parser.parse_args()
    models=dict(MODELS)
    if args.population:
        models.update({'rf_kde':'Random Forest · + KDE',
                       'rf_population':'Random Forest · + KDE and population (retrospective)',
                       'xgb_population':'XGBoost · + KDE and population (retrospective)'})
    audit=json.loads((OUT/'audit.json').read_text());geo=json.loads((OUT/'segments.geojson').read_text());e=pd.read_csv(OUT/'events.csv',keep_default_na=False);months=audit['months']
    if len(months)<34:raise ValueError('Need at least 34 complete months for these three walk-forward folds')
    if set(months)-set(e.month):raise ValueError('Missing source months; do not fill a source outage with zeros')
    p=build_panel(e,geo,months)
    population_manifest=None
    if args.population:p,population_manifest=add_population(p,audit)
    p.to_csv(OUT/'segment_features.csv',index=False);eligible=p[p.mean_6.notna()].copy()
    reports=[];all_preds=[]
    for fold in range(3):
        split=len(months)-18+fold*6;val_start=pd.Timestamp(months[split-4]);test_start=pd.Timestamp(months[split]);test_end=pd.Timestamp(months[split+5]);latest_train_origin=val_start-pd.offsets.MonthBegin(1)
        pairs=choose_patterns(e,latest_train_origin);panel,extra=pattern_features(eligible,e,pairs)
        tr=panel[panel.target_month<val_start];val=panel[(panel.target_month>=val_start)&(panel.target_month<test_start)];test=panel[(panel.target_month>=test_start)&(panel.target_month<=test_end)];fit=panel[panel.target_month<test_start]
        assert tr.target_month.max()<=val.month.min() and fit.target_month.max()<=test.month.min()
        bw=min(BANDWIDTHS,key=lambda b:rank(score(val,val[f'kde_alloc_{b}'].to_numpy())))
        fx=subsets(f'kde_{bw}',extra)
        if args.population:
            population_columns=['population_200m','population_density_200m','population_change_pct','population_change_defined']
            fx['rf_kde']=NEAR+[f'kde_{bw}']
            fx.update({name:NEAR+[f'kde_{bw}']+population_columns for name in ['rf_population','xgb_population']})
        preds={};valid={};fitted={}
        for name,col in [('zero',None),('persistence','count'),('rolling','mean_3'),('kde',f'kde_alloc_{bw}')]:
            f=lambda d: d[col].to_numpy() if col else np.zeros(len(d));preds[name]=f(test);valid[name]=score(val,f(val))
        for name,cols in fx.items():
            model=estimator(name);model.fit(tr[cols],tr.target);valid[name]=score(val,model.predict(val[cols]));model.fit(fit[cols],fit.target);preds[name]=model.predict(test[cols]);fitted[name]=model
        result=test[['segment_id','month','target_month','target']].rename(columns={'target':'actual'}).copy();result['fold']=fold+1;result['kind']='held_out';result=result.assign(**preds);all_preds.append(result)
        density_edges=[]
        if args.population:
            density_edges=sorted(set(float(v) for v in tr.population_density_200m.quantile([.25,.5,.75])))
            result['density_group']=np.searchsorted(density_edges,test.population_density_200m.to_numpy(),side='right')+1
        selected=min(MODELS,key=lambda n:rank(valid[n]));reports.append({'fold':fold+1,'population_density_group_edges':density_edges,'train_target_end':str(tr.target_month.max().date()),'validation_target_start':str(val_start.date()),'validation_target_end':str(val.target_month.max().date()),'test_target_start':str(test_start.date()),'test_target_end':str(test_end.date()),'kde_bandwidth_m':bw,'training_selected_pairs':[list(x) for x in pairs],'selected_on_validation':selected,'validation':valid,'test':{n:score(test,pred) for n,pred in preds.items()}})
        print(f'Fold {fold+1} through {test_end.date()}: {len(test):,} held-out rows; validation selected {selected}, KDE {bw} m',flush=True)
    evaluated=pd.concat(all_preds,ignore_index=True)
    aggregate={name:score(evaluated.rename(columns={'actual':'target'}),evaluated[name].to_numpy()) for name in models}
    # One extra horizon beyond this data snapshot, not a current real-time forecast.
    latest=panel[panel.target.isna()].copy();known=panel[panel.target.notna()]
    f=latest[['segment_id','month','target_month','target']].rename(columns={'target':'actual'}).copy();f['fold']=0;f['kind']='beyond_snapshot';f=f.assign(zero=0.,persistence=latest['count'],rolling=latest.mean_3,kde=latest[f'kde_alloc_{bw}'])
    for name,cols in fx.items():model=estimator(name);model.fit(known[cols],known.target);f[name]=model.predict(latest[cols])
    pd.concat([evaluated,f],ignore_index=True).to_csv(OUT/'predictions.csv',index=False)
    # Auditable baseline-vs-grid reproduction on a single sample month.
    sample=e[e.in_study & (e.month==months[-1])];sample_args=(sample[['x','y']].to_numpy(),sample.crime.tolist(),sample.month.tolist());slow=mine_patterns(*sample_args,threshold=.1,method='baseline');fast=mine_patterns(*sample_args,threshold=.1)
    assert slow['patterns']==fast['patterns'],'Grid filtering changed the exact prevalent patterns'
    summary={'study_id':audit['study_id'],'models':models,'folds':reports,'aggregate':aggregate,'held_out_months':sorted(evaluated.target_month.dt.strftime('%Y-%m-01').unique()),'forecast_month':str(latest.target_month.max().date()),'default_model':reports[-1]['selected_on_validation'],'benchmark':{'month':months[-1],'baseline':slow['stats'],'grid':fast['stats'],'same_patterns':True},'interpretation':'MAE and RMSE are for matched records per segment-month. Top 10% capture uses expected tie handling. Models are evaluated on later months; training pattern selection uses only training-origin information. Current OSM places are not used to predict historical counts.'}
    if args.population:
        summary['population']=population_manifest
        summary['population']['evaluation']='Retrospective association experiment; excluded from historical default-model selection.'
        summary['population']['density_groups']={str(group):{name:score(rows.rename(columns={'actual':'target'}),rows[name].to_numpy()) for name in models} for group,rows in evaluated.groupby('density_group')}
        summary['population']['paired_comparisons']={
            'xgboost':'xgb_population vs xgb_kde (only added population inputs)',
            'random_forest':'rf_population vs rf_kde (only added population inputs)'}
    (OUT/'metrics.json').write_text(json.dumps(summary,indent=2,allow_nan=False));print(json.dumps(aggregate,indent=2),flush=True)
if __name__=='__main__':main()
