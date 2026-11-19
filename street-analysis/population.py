"""Acquire versioned WorldPop grids and estimate residents around street segments.

Annual modeled context for retrospective analysis. Population change is not a
migration measure. Buffers overlap and their populations must not be summed.
"""
import argparse
import hashlib
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from shapely import transform
from shapely.geometry import box, mapping, shape
from shapely.strtree import STRtree

from prepare import OUT, ROOT
from spatial import TO_METERS, TO_WGS

RAW = ROOT / 'data/street/raw/worldpop'
API = 'https://api.worldpop.org/v3'
FEATURES = ['population_200m', 'population_density_200m', 'population_change_pct']
NOTE = ('WorldPop Global2 R2025A modeled annual population. Retrospective context; '
        'release inputs can postdate crime forecasts. Annual change includes demographic '
        'and modeling effects and does not measure migration. Street buffers overlap.')


def request_bytes(url, payload=None):
    """Use the system TLS trust store and bounded retries; never cache errors."""
    command = ['curl', '--fail-with-body', '--silent', '--show-error', '--location',
               '--retry', '2', '--retry-delay', '2', '--max-time', '90', url]
    if payload is not None:
        command += ['-H', 'Content-Type: application/json', '--data-binary', '@-']
    result = subprocess.run(command, input=json.dumps(payload).encode() if payload else None,
                            capture_output=True, check=True)
    return result.stdout


def weighted_population(dataset, polygon):
    """Sum people per pixel weighted by projected overlap, conserving cell counts."""
    values = dataset.read(1, masked=True)
    cells, counts = [], []
    for row, col in np.ndindex(values.shape):
        left, top = dataset.transform * (col, row)
        right, bottom = dataset.transform * (col + 1, row + 1)
        cell = transform(box(left, bottom, right, top), TO_METERS.transform, interleaved=False)
        if not cell.intersects(polygon):
            continue
        if np.ma.is_masked(values[row, col]):
            raise ValueError('WorldPop has missing cells inside the requested study buffers')
        value = float(values[row, col])
        if not np.isfinite(value) or value < 0:
            raise ValueError('Invalid WorldPop population count')
        cells.append(cell)
        counts.append(value)
    tree = STRtree(cells)
    return cells, np.array(counts), tree


def summarize(polygon, cells, counts, tree):
    indices = tree.query(polygon, predicate='intersects')
    covered = sum(cells[i].intersection(polygon).area for i in indices)
    if abs(covered - polygon.area) / polygon.area > .001:
        raise ValueError('Population raster does not completely cover a study buffer')
    return float(sum(counts[i] * cells[i].intersection(polygon).area / cells[i].area for i in indices))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-year', type=int, default=2019)
    parser.add_argument('--end-year', type=int, default=2026)
    args = parser.parse_args()
    if not 2016 <= args.start_year <= args.end_year <= 2030:
        parser.error('Choose years 2016–2030; one previous year is also fetched for change')
    audit = json.loads((OUT / 'audit.json').read_text())
    segments = json.loads((OUT / 'segments.geojson').read_text())['features']
    lines = [transform(shape(f['geometry']), TO_METERS.transform, interleaved=False) for f in segments]
    buffers = [line.buffer(200, quad_segs=16) for line in lines]
    study = transform(shape(audit['boundary']), TO_METERS.transform, interleaved=False)
    from shapely.ops import unary_union
    coverage = unary_union(buffers + [study])
    extent = coverage.envelope.buffer(150).envelope
    request_area = mapping(transform(extent, TO_WGS.transform, interleaved=False))
    RAW.mkdir(parents=True, exist_ok=True)
    records, totals, sources = [], [], []
    previous = None
    for year in range(args.start_year - 1, args.end_year + 1):
        payload = {'geojson': request_area, 'year': year, 'resolution': '100m', 'layer': 'population'}
        key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
        raster_path = RAW / f'population_{year}_{key}.tif'
        metadata_path = raster_path.with_suffix('.json')
        if not raster_path.exists() or not metadata_path.exists():
            catalog = json.loads(request_bytes(f'{API}/countries/MEX/files?year={year}'))
            data = request_bytes(f'{API}/raster', payload)
            # Validate the response before making it a reusable local snapshot.
            with tempfile.NamedTemporaryFile(suffix='.tif') as temporary:
                temporary.write(data)
                temporary.flush()
                with rasterio.open(temporary.name) as dataset:
                    if dataset.crs.to_epsg() != 4326 or dataset.count != 1:
                        raise ValueError('Unexpected WorldPop raster CRS or bands')
            raster_path.write_bytes(data)
            metadata_path.write_text(json.dumps({'request_url': f'{API}/raster', 'request': payload,
                'retrieved_at': datetime.now(timezone.utc).isoformat(),
                'sha256': hashlib.sha256(data).hexdigest(), 'country_catalog': catalog}, indent=2))
        metadata = json.loads(metadata_path.read_text())
        if hashlib.sha256(raster_path.read_bytes()).hexdigest() != metadata['sha256']:
            raise ValueError(f'Cached raster checksum mismatch: {raster_path}')
        with rasterio.open(raster_path) as dataset:
            tags = dataset.tags()
            if tags.get('RELEASE') != 'R2025A' or tags.get('YEAR') != str(year) or tags.get('UNITS') != 'people per cell':
                raise ValueError('Population response changed release, year or units')
            if dataset.crs.to_epsg() != 4326 or not np.isclose(dataset.res[0], 1/1200):
                raise ValueError('Expected WorldPop 3-arcsecond WGS84 count grid')
            cells, counts, tree = weighted_population(dataset, coverage)
        population = np.array([summarize(buffer, cells, counts, tree) for buffer in buffers])
        sources.append({'year': year, 'metadata': str(metadata_path.relative_to(ROOT)), 'sha256': metadata['sha256']})
        totals.append({'year': year, 'estimated_residents': summarize(study, cells, counts, tree)})
        if previous is not None:
            for feature, buffer, value, old in zip(segments, buffers, population, previous):
                records.append({'segment_id': feature['properties']['segment_id'], 'population_year': year,
                    'population_200m': value, 'population_density_200m': value / (buffer.area / 1e6),
                    'population_change_pct': (value / old - 1) * 100 if old > 0 else None,
                    'buffer_area_km2': buffer.area / 1e6})
        previous = population
        print(f'WorldPop {year}: estimated {totals[-1]["estimated_residents"]:,.1f} residents in study boundary', flush=True)
    frame = pd.DataFrame(records)
    if frame.duplicated(['segment_id', 'population_year']).any():
        raise ValueError('Duplicate population features')
    # Missing growth when the previous population was zero remains explicitly missing.
    frame.to_csv(OUT / 'population_features.csv', index=False)
    manifest = {'study_id': audit['study_id'], 'dataset': 'WorldPop Global2 R2025A',
        'doi': '10.5258/SOTON/WP00839', 'license': 'CC BY 4.0', 'resolution': '3 arcseconds (~100 m)',
        'buffer_m': 200, 'density_scale': float(frame.population_density_200m.max()), 'method': 'Projected cell-overlap fractions of people per pixel; annual values',
        'interpretation': NOTE, 'years': list(range(args.start_year, args.end_year + 1)),
        'study_population': totals[1:], 'sources': sources,
        'segments_sha256': hashlib.sha256((OUT / 'segments.geojson').read_bytes()).hexdigest(),
        'features_sha256': hashlib.sha256((OUT / 'population_features.csv').read_bytes()).hexdigest(),
        'inegi_validation': 'Not performed; independent small-area totals have not been loaded.'}
    (OUT / 'population.json').write_text(json.dumps(manifest, indent=2))
    print(f'Built {len(frame):,} segment-year rows.', flush=True)


if __name__ == '__main__':
    main()
