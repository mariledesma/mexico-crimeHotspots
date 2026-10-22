-- Read-only source and derived-table checks.
SELECT count(*) AS source_rows,count(DISTINCT cuadrante) AS cuadrantes,
 count(DISTINCT crime) AS categories,min(date) AS first_month,max(date) AS last_month
FROM public.crime_monthly;
SELECT count(*) AS duplicate_keys FROM (
 SELECT cuadrante,crime,date FROM public.crime_monthly GROUP BY 1,2,3 HAVING count(*)>1
) s;
SELECT min(n) AS minimum_categories,max(n) AS maximum_categories,count(*) AS monthly_rows
FROM (SELECT cuadrante,date,count(*) AS n FROM public.crime_monthly GROUP BY 1,2) s;
SELECT count(*) FILTER(WHERE NOT ST_IsValid(geometry)) AS invalid_polygons,
 min(ST_SRID(geometry)) AS srid FROM public.cuadrantes;
SELECT count(*) AS label_mismatches FROM public.crime_monthly_features f
JOIN public.crime_monthly_features n ON f.cuadrante=n.cuadrante
AND n.date=(f.date+interval '1 month')::date
WHERE f.target_next_month IS DISTINCT FROM n.total_crime;
SELECT count(*) AS asymmetric_edges FROM public.cuadrante_neighbors a
LEFT JOIN public.cuadrante_neighbors b ON a.cuadrante=b.neighbor AND a.neighbor=b.cuadrante
WHERE b.cuadrante IS NULL;
