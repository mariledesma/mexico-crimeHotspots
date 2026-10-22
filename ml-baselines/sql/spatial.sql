CREATE TABLE IF NOT EXISTS public.cuadrante_neighbors (
 cuadrante text NOT NULL, neighbor text NOT NULL,
 PRIMARY KEY(cuadrante,neighbor), CHECK(cuadrante<>neighbor));
DELETE FROM public.cuadrante_neighbors;
INSERT INTO public.cuadrante_neighbors
SELECT a.cuadrante,b.cuadrante FROM public.cuadrantes a
JOIN public.cuadrantes b ON a.cuadrante<>b.cuadrante
AND a.geometry && b.geometry AND ST_Touches(a.geometry,b.geometry);
ALTER TABLE public.crime_monthly_features ADD COLUMN IF NOT EXISTS rolling_6_month double precision;
ALTER TABLE public.crime_monthly_features ADD COLUMN IF NOT EXISTS neighbor_count integer;
ALTER TABLE public.crime_monthly_features ADD COLUMN IF NOT EXISTS neighbor_mean double precision;
ALTER TABLE public.crime_monthly_features ADD COLUMN IF NOT EXISTS neighbor_sum double precision;
ALTER TABLE public.crime_monthly_features ADD COLUMN IF NOT EXISTS neighbor_lag_1 double precision;
WITH r AS (
 SELECT cuadrante,date,CASE WHEN count(total_crime) OVER w=6 THEN avg(total_crime) OVER w END v
 FROM public.crime_monthly_features
 WINDOW w AS(PARTITION BY cuadrante ORDER BY date ROWS BETWEEN 5 PRECEDING AND CURRENT ROW)
) UPDATE public.crime_monthly_features f SET rolling_6_month=r.v FROM r
WHERE f.cuadrante=r.cuadrante AND f.date=r.date;
WITH n AS (
 SELECT f.cuadrante,f.date,count(e.neighbor)::integer n,
 CASE WHEN count(e.neighbor)=count(g.total_crime) THEN coalesce(avg(g.total_crime),0) END mean,
 CASE WHEN count(e.neighbor)=count(g.total_crime) THEN coalesce(sum(g.total_crime),0) END total,
 CASE WHEN count(e.neighbor)=count(g.lag_1) THEN coalesce(avg(g.lag_1),0) END lagged
 FROM public.crime_monthly_features f
 LEFT JOIN public.cuadrante_neighbors e ON e.cuadrante=f.cuadrante
 LEFT JOIN public.crime_monthly_features g ON g.cuadrante=e.neighbor AND g.date=f.date
 GROUP BY f.cuadrante,f.date
) UPDATE public.crime_monthly_features f
SET neighbor_count=n.n,neighbor_mean=n.mean,neighbor_sum=n.total,neighbor_lag_1=n.lagged
FROM n WHERE f.cuadrante=n.cuadrante AND f.date=n.date;
