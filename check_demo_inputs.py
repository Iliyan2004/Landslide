#!/usr/bin/env python3
"""Check Gilgit pilot input references without downloading or changing any data."""
import argparse
from pathlib import Path
import yaml


def walk(prefix, mapping):
    for key, value in mapping.items():
        name = f'{prefix}.{key}' if prefix else key
        if isinstance(value, dict):
            yield from walk(name, value)
        else:
            yield name, value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='configs/gilgit_demo.yaml')
    parser.add_argument('--project-root', default='.', help='landslide-platform root folder')
    args = parser.parse_args()
    root = Path(args.project_root).expanduser().resolve()
    cfg_path = Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = root / cfg_path
    with cfg_path.open('r', encoding='utf-8') as fh:
        config = yaml.safe_load(fh)
    keys = {'terrain','inventory','forcing','soil','datasets','study_area'}
    extensions = ('.tif','.tiff','.gpkg','.shp','.geojson','.nc','.csv','.zarr','.parquet')
    checked = missing = unset = 0
    data_root = Path(config.get('project',{}).get('data_root',''))
    for section in keys:
        values = config.get(section)
        if not isinstance(values, dict):
            values = {'path': values}
        for name, value in walk(section,values):
            if name in ('study_area.canonical_crs','study_area.analysis_crs','study_area.target_resolution_m', 'study_area.buffer_m', 'study_area.strict_aoi_statistics','soil.parameter_mode'):
                continue
            if value is None:
                print(f'UNSET    {name}')
                unset += 1
            elif isinstance(value,str) and value.lower().endswith(extensions):
                # Relative paths use project root; prefix with data_root yourself if desired.
                p = Path(value)
                if not p.is_absolute():
                    p = root / p
                good = p.exists() and (p.is_dir() if p.suffix == '.zarr' else p.is_file())
                print(f'{"OK" if good else "MISSING" :<8} {name}: {p}')
                checked += 1
                if not good:
                    missing += 1
            elif isinstance(value,dict):
                continue
            elif section == 'soil':
                print(f'SCENARIO {name}: {value}')
    print(f'\nData paths checked: {checked}; missing: {missing}; unset: {unset}.')
    print('This only checks existence; it does not verify CRS, data content, units, or model readiness.')
    raise SystemExit(1 if missing else 0)

if __name__ == '__main__':
    main()
