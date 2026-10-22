-- Run in one transaction via build_monthly_features.py.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.crime_monthly) THEN
        RAISE EXCEPTION 'crime_monthly is empty';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.crime_monthly
        WHERE cuadrante IS NULL OR btrim(cuadrante) = '' OR crime IS NULL
           OR btrim(crime) = '' OR date IS NULL OR count IS NULL
           OR count < 0 OR count <> trunc(count::numeric)
           OR date::date <> date_trunc('month', date)::date
    ) THEN
        RAISE EXCEPTION 'Invalid source keys, dates, or counts; repair crime_monthly first';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.crime_monthly
        GROUP BY cuadrante, crime, date_trunc('month', date)
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Duplicate cuadrante/crime/month rows; repair loader duplicates first';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.crime_monthly_features (
    cuadrante text NOT NULL,
    date date NOT NULL,
    year integer NOT NULL,
    month integer NOT NULL,
    total_crime bigint,
    observed_categories integer NOT NULL,
    expected_categories integer NOT NULL,
    is_complete boolean NOT NULL,
    lag_1 bigint,
    lag_3 bigint,
    rolling_3_month double precision,
    target_date date NOT NULL,
    target_next_month bigint,
    PRIMARY KEY (cuadrante, date)
);
-- Transactional refresh; preserve the table and its grants.
DELETE FROM public.crime_monthly_features;
INSERT INTO public.crime_monthly_features
WITH expected AS (
    SELECT cuadrante, count(DISTINCT crime)::integer AS n
    FROM public.crime_monthly GROUP BY cuadrante
), monthly AS (
    SELECT cuadrante, date_trunc('month', date)::date AS date,
           sum(count)::bigint AS total, count(*)::integer AS n
    FROM public.crime_monthly GROUP BY cuadrante, date_trunc('month', date)
), calendar AS (
    SELECT b.cuadrante, g::date AS date
    FROM (SELECT cuadrante, min(date) AS first_date, max(date) AS last_date
          FROM monthly GROUP BY cuadrante) b
    CROSS JOIN LATERAL generate_series(b.first_date, b.last_date, interval '1 month') g
), panel AS (
    SELECT c.cuadrante, c.date,
           CASE WHEN m.n = e.n THEN m.total END AS total_crime,
           coalesce(m.n, 0) AS observed_categories, e.n AS expected_categories,
           coalesce(m.n = e.n, false) AS is_complete
    FROM calendar c JOIN expected e USING (cuadrante)
    LEFT JOIN monthly m USING (cuadrante, date)
), features AS (
    SELECT *, lag(total_crime, 1) OVER w AS lag_1,
           lag(total_crime, 3) OVER w AS lag_3,
           CASE WHEN count(total_crime) OVER r = 3
                THEN avg(total_crime) OVER r END AS rolling_3_month,
           lead(total_crime, 1) OVER w AS target_next_month
    FROM panel
    WINDOW w AS (PARTITION BY cuadrante ORDER BY date),
           r AS (PARTITION BY cuadrante ORDER BY date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
)
SELECT cuadrante, date, extract(year FROM date)::integer,
       extract(month FROM date)::integer, total_crime, observed_categories,
       expected_categories, is_complete, lag_1, lag_3, rolling_3_month,
       (date + interval '1 month')::date, target_next_month
FROM features;
