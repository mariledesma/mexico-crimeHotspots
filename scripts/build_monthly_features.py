"""Build features, chronological exports, and two count forecasting baselines."""
import argparse
import json
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ['total_crime', 'lag_1', 'lag_3', 'rolling_3_month']


def split_by_target(frame, test_months):
    labeled = frame.dropna(subset=FEATURES + ['target_next_month']).copy()
    months = sorted(labeled['target_date'].unique())
    if test_months < 1 or len(months) <= test_months:
        raise ValueError('Need more eligible target months than --test-months.')
    cutoff = months[-test_months]
    train = labeled[labeled.target_date < cutoff].copy()
    test = labeled[labeled.target_date >= cutoff].copy()
    assert train.target_date.max() < test.target_date.min()
    return train, test


def evaluate(test):
    predictions = test[['cuadrante', 'date', 'target_date', 'target_next_month']].copy()
    metrics = {}
    for name, column in [('persistence', 'total_crime'), ('rolling_average', 'rolling_3_month')]:
        pred = test[column].astype(float)
        error = pred - test.target_next_month
        predictions[name] = pred
        metrics[name] = {'mae': float(error.abs().mean()),
                         'rmse': float((error.pow(2).mean()) ** 0.5)}
    return predictions, metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-months', type=int, default=6)
    parser.add_argument('--last-complete-month', required=True,
                        help='Last fully reported source month, YYYY-MM; do not guess from MAX(date).')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'data' / 'ml')
    args = parser.parse_args()
    last = pd.to_datetime(args.last_complete_month, format='%Y-%m', errors='raise')
    load_dotenv(ROOT / '.env')
    url = os.getenv('DATABASE_URL')
    if not url:
        raise SystemExit('Set DATABASE_URL in the project .env file.')
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            # Serialize concurrent rebuilds for this pipeline.
            conn.execute(text('SELECT pg_advisory_xact_lock(73420261014)'))
            conn.exec_driver_sql((ROOT / 'sql' / 'build_monthly_features.sql').read_text())
            frame = pd.read_sql_query(text('SELECT * FROM public.crime_monthly_features ORDER BY cuadrante, date'), conn)
    finally:
        engine.dispose()
    for column in ['date', 'target_date']:
        frame[column] = pd.to_datetime(frame[column])
    if last > frame.date.max():
        raise ValueError('--last-complete-month is later than the available source data.')
    frame = frame[frame.date <= last].copy()
    # Hide labels beyond the declared reporting cutoff, even if the database has them.
    frame.loc[frame.target_date > last, 'target_next_month'] = float('nan')
    train, test = split_by_target(frame, args.test_months)
    predictions, metrics = evaluate(test)
    latest = frame[(frame.date == last)].dropna(subset=FEATURES).copy()
    latest['prediction_next_month'] = latest.total_crime
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in [('monthly_features', frame), ('train', train), ('test', test),
                       ('test_predictions', predictions), ('latest_predictions', latest)]:
        data.to_csv(args.output_dir / f'{name}.csv', index=False)
    report = {'last_complete_month': args.last_complete_month,
              'train_rows': len(train), 'test_rows': len(test),
              'first_test_target_month': test.target_date.min().strftime('%Y-%m'),
              'incomplete_panel_rows': int((~frame.is_complete).sum()),
              'latest_prediction_rows': len(latest), 'metrics': metrics}
    (args.output_dir / 'metrics.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    print(f'Exports saved to {args.output_dir.resolve()}')


if __name__ == '__main__':
    main()
