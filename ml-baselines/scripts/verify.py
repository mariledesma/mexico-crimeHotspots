"""Independent checks against the exported panel and adjacency graph."""
from pathlib import Path
import numpy as np
import pandas as pd
root=Path(__file__).resolve().parents[1]
d=pd.read_csv(root/'data/monthly_features.csv',parse_dates=['date','target_date']).sort_values(['cuadrante','date'])
assert not d.duplicated(['cuadrante','date']).any()
g=d.groupby('cuadrante').total_crime
for col,expected in [('lag_1',g.shift(1)),('lag_3',g.shift(3)),('target_next_month',g.shift(-1))]:
    np.testing.assert_allclose(d[col],expected,equal_nan=True)
for w,col in [(3,'rolling_3_month'),(6,'rolling_6_month')]:
    np.testing.assert_allclose(d[col],g.transform(lambda s:s.rolling(w).mean()),equal_nan=True)
assert (d.target_date==d.date+pd.offsets.MonthBegin(1)).all()
e=pd.read_csv(root/'data/neighbors.csv')
assert not e.duplicated().any()
edges=set(map(tuple,e.to_numpy()))
assert all(a!=b and (b,a) in edges for a,b in edges)
joined=e.merge(d[['cuadrante','date','total_crime','lag_1']],left_on='neighbor',right_on='cuadrante',suffixes=('','_neighbor'))
agg=joined.groupby(['cuadrante','date']).agg(neighbor_count=('neighbor','count'),neighbor_sum=('total_crime','sum'),neighbor_mean=('total_crime','mean'),neighbor_lag_1=('lag_1','mean'))
actual=d.set_index(['cuadrante','date']).loc[agg.index]
for col in agg:
    np.testing.assert_allclose(actual[col],agg[col],equal_nan=True)
print(f'PASS: {len(d):,} feature rows and {len(e):,} directed edges; temporal and spatial values independently verified.')
