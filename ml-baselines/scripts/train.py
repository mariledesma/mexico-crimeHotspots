"""One-month-ahead count regression, chronological validation and test."""
from pathlib import Path
import argparse, json, platform
import numpy as np
import pandas as pd
import sklearn, joblib
from importlib.metadata import version
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

ROOT=Path(__file__).resolve().parents[1]
def metrics(y,p):
    return dict(MAE=float(mean_absolute_error(y,p)),RMSE=float(mean_squared_error(y,p)**.5),R2=float(r2_score(y,p)))
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cutoff',default='2026-08-01')
    parser.add_argument('--resume',action='store_true',help='Resume unchanged data/configuration from partial outputs')
    args=parser.parse_args()
    out=ROOT/'results'; out.mkdir(exist_ok=True)
    d=pd.read_csv(ROOT/'data/monthly_features.csv',parse_dates=['date','target_date'])
    cutoff=pd.Timestamp(args.cutoff)
    d=d[d.date<=cutoff].copy()
    d.loc[d.target_date>cutoff,'target_next_month']=np.nan
    d['month_sin']=np.sin(2*np.pi*d.month/12)
    d['month_cos']=np.cos(2*np.pi*d.month/12)
    temporal=['total_crime','lag_1','lag_3','rolling_3_month','rolling_6_month','month_sin','month_cos','year']
    spatial=temporal+['neighbor_count','neighbor_mean','neighbor_sum','neighbor_lag_1']
    eligible=d.dropna(subset=spatial+['target_next_month']).copy()
    months=sorted(eligible.target_date.unique())
    assert len(months)>=24
    test_start=pd.Timestamp(months[-6]); val_start=pd.Timestamp(months[-12])
    train=eligible[eligible.target_date<val_start]
    val=eligible[(eligible.target_date>=val_start)&(eligible.target_date<test_start)]
    test=eligible[eligible.target_date>=test_start]
    fit=eligible[eligible.target_date<test_start]
    assert train.target_date.max()<=val.date.min()
    assert fit.target_date.max()<=test.date.min()
    report={'cutoff':str(cutoff.date()),'source_rows':1558480,'feature_rows':len(d),'eligible_rows':len(eligible),
      'split':{},'validation':{},'test':{},'versions':{'python':platform.python_version(),'sklearn':sklearn.__version__,'xgboost':version('xgboost')}}
    for name,part in [('train',train),('validation',val),('test',test)]:
        report['split'][name]={'rows':len(part),'first_target':str(part.target_date.min().date()),'last_target':str(part.target_date.max().date())}
    predictions=test[['cuadrante','date','target_date','target_next_month']].copy()
    for name,column in [('persistence','total_crime'),('rolling_mean','rolling_3_month')]:
        report['validation'][name]=metrics(val.target_next_month,val[column])
        report['test'][name]=metrics(test.target_next_month,test[column])
        predictions[name]=test[column]
    completed=set()
    if args.resume:
        previous=json.loads((out/'metrics.partial.json').read_text())
        for key in ['cutoff','source_rows','feature_rows','eligible_rows','split','versions']:
            assert previous[key]==report[key], f'Checkpoint differs: {key}'
        report=previous
        predictions=pd.read_csv(out/'test_predictions.partial.csv')
        predictions.index=test.index
        completed=set(report['test'])
    for kind in ['random_forest','xgboost']:
        if kind=='xgboost':
            from xgboost import XGBRegressor
        for group,features in [('temporal',temporal),('spatial',spatial)]:
            name=f'{kind}_{group}'
            if name in completed:
                continue
            model=(RandomForestRegressor(n_estimators=200,min_samples_leaf=5,max_features=.8,n_jobs=2,random_state=42)
              if kind=='random_forest' else XGBRegressor(n_estimators=300,max_depth=4,learning_rate=.05,subsample=.8,colsample_bytree=.9,objective='count:poisson',n_jobs=2,random_state=42))
            model.fit(train[features],train.target_next_month)
            report['validation'][name]=metrics(val.target_next_month,model.predict(val[features]))
            model.fit(fit[features],fit.target_next_month)
            p=model.predict(test[features]); predictions[name]=p
            report['test'][name]=metrics(test.target_next_month,p)
            joblib.dump({'model':model,'features':features,'fit_last_target':str(fit.target_date.max().date())},out/f'{name}.joblib')
            pd.DataFrame({'feature':features,'importance':model.feature_importances_}).sort_values('importance',ascending=False).to_csv(out/f'{name}_importance.csv',index=False)
            (out/'metrics.partial.json').write_text(json.dumps(report,indent=2))
            predictions.to_csv(out/'test_predictions.partial.csv',index=False)
            print(name,report['test'][name],flush=True)
    report['selected_by_validation_mae']=min(report['validation'],key=lambda n:report['validation'][n]['MAE'])
    predictions.to_csv(out/'test_predictions.csv',index=False)
    (out/'metrics.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
if __name__=='__main__': main()
