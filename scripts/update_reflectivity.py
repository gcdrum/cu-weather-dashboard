"""Experimental NOAA GFS numerical reflectivity fetcher for GitHub Actions.

Generates dashboard-compatible reflectivity.json from actual GRIB2 values.
Only GFS is supported in this first validation pass; never fabricate other models.
"""
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import requests
from eccodes import codes_get_array, codes_grib_new_from_file, codes_release



def merge_model_records(path, model, fresh, min_count):
    """Preserve other models, reject malformed or regressive same-cycle updates."""
    if len(fresh) < min_count:
        raise RuntimeError(f'{model}: only {len(fresh)} records, minimum {min_count}')
    existing = json.loads(path.read_text()) if path.exists() else []
    if not isinstance(existing, list):
        raise RuntimeError('Existing reflectivity.json is not a list')
    def check(r):
        if not isinstance(r,dict) or not isinstance(r.get('time'),str) or not isinstance(r.get('model'),str):
            raise RuntimeError('Malformed reflectivity record')
        if r['model'] in ('gfs','hrrr'):
            zones=r.get('zones')
            if not isinstance(zones,dict) or not all(k in zones for k in ('upstream_west','approach_west','springfield_area','downstream_east')):
                raise RuntimeError(f'Missing geographic zones in {r["model"]} record {r["time"]}')
            if not isinstance(r.get('peak'),dict) or not all(k in r['peak'] for k in ('lat','lon')):
                raise RuntimeError(f'Missing peak coordinates in {r["model"]} record {r["time"]}')
    for r in fresh: check(r)
    # Older files may contain legacy GFS records. Do not preserve them as if they were validated.
    other=[r for r in existing if isinstance(r,dict) and r.get('model') != model]
    for r in other: check(r)
    old=[r for r in existing if isinstance(r,dict) and r.get('model') == model]
    old_valid=[r for r in old if isinstance(r.get('zones'),dict) and isinstance(r.get('peak'),dict)]
    # Merge by valid forecast hour; do not replace missing hours with zeros.
    # An older cycle may fill only hours not yet present in the incoming cycle.
    merged={}
    for r in old_valid:
        if r.get('time'):
            merged[r['time']]=dict(r,source_cycle=r.get('source_cycle',r.get('cycle',old_valid[0]['time'])))
    incoming_cycle=fresh[0]['time']
    for r in fresh:
        if r.get('time'):
            merged[r['time']]=dict(r,source_cycle=incoming_cycle)
    cutoff=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    retained=[merged[k] for k in sorted(merged) if k>=cutoff]
    combined=sorted(other+retained,key=lambda r:(r['time'],r['model']))
    # Do not write until every model has passed validation.
    for r in combined: check(r)
    tmp=path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(combined,indent=2)+'\n')
    tmp.replace(path)
    print(f'Merged {len(fresh)} {model} + {len(other)} other-model records',flush=True)

OUT = Path('reflectivity.json')
STATUS = Path('reflectivity_status.json')
# West-to-east corridor around southwest Missouri, including upstream storms.
WEST, EAST, SOUTH, NORTH = -95.5, -91.5, 35.5, 39.0
BASE = 'https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl'
# Geographic screening boxes are approximate and are NOT utility service boundaries.
# Each maximum comes from a subset of the same decoded NOAA grid.
ZONES = {
    'upstream_west': (-95.5, -94.0, 35.5, 39.0),
    'approach_west': (-94.0, -93.3, 36.2, 38.3),
    'springfield_area': (-93.6, -92.9, 36.9, 37.6),
    'downstream_east': (-92.9, -91.5, 35.5, 39.0),
}



def download_field(session, cycle, hour):
    filename = f'gfs.t{cycle:%H}z.pgrb2.0p25.f{hour:03d}'
    params = {
        'file': filename, 'lev_entire_atmosphere': 'on', 'var_REFC': 'on',
        'subregion': '', 'leftlon': '264.5', 'rightlon': '268.5',
        'toplat': '39', 'bottomlat': '35.5',
        'dir': f'/gfs.{cycle:%Y%m%d}/{cycle:%H}/atmos',
    }
    r = session.get(BASE, params=params, timeout=75)
    r.raise_for_status()
    if not r.content.startswith(b'GRIB'):
        raise ValueError('NOAA response is not a GRIB2 field: '+r.text[:90])
    with tempfile.NamedTemporaryFile(suffix='.grib2') as tmp:
        tmp.write(r.content)
        tmp.flush()
        with open(tmp.name, 'rb') as f:
            handle = codes_grib_new_from_file(f)
            if handle is None:
                raise ValueError('No GRIB message found')
            try:
                lat = codes_get_array(handle, 'latitudes')
                lon = codes_get_array(handle, 'longitudes')
                values = codes_get_array(handle, 'values')
                lon = np.where(lon > 180, lon - 360, lon)
                mask = ((lat >= SOUTH) & (lat <= NORTH) & (lon >= WEST) & (lon <= EAST)
                        & np.isfinite(values) & (values >= 0) & (values <= 90))
                if not np.any(mask):
                    raise ValueError('No valid dBZ values in requested region')
                # Retain the legacy regional maximum and add geographically resolved evidence.
                regional = round(float(np.max(values[mask])), 1)
                zones = {}
                for name, (west, east, south, north) in ZONES.items():
                    m = mask & (lon >= west) & (lon <= east) & (lat >= south) & (lat <= north)
                    zones[name] = round(float(np.max(values[m])), 1) if np.any(m) else None
                # Grid-cell location of regional peak; this is not a storm-track vector.
                valid_indices = np.flatnonzero(mask)
                peak_index = valid_indices[int(np.argmax(values[mask]))]
                return {
                    'dbz': regional,
                    'zones': zones,
                    'peak': {'lat': round(float(lat[peak_index]), 3),
                             'lon': round(float(lon[peak_index]), 3)},
                }
            finally:
                codes_release(handle)


def main():
    now = datetime.now(timezone.utc)
    # Avoid incomplete cycles; start with the most recent cycle at least 5h old.
    latest = now.replace(hour=(now.hour // 6) * 6, minute=0, second=0, microsecond=0)
    if (now - latest) < timedelta(hours=5):
        latest -= timedelta(hours=6)
    session = requests.Session()
    session.headers.update({'User-Agent': 'CU-Weather-Dashboard-Research/1.0'})
    errors = []
    records = []
    chosen = None
    for back in (0, 6, 12):
        cycle = latest - timedelta(hours=back)
        try:
            # Verify the cycle before attempting the remaining forecast hours.
            first = download_field(session, cycle, 0)
            chosen = cycle
            records.append({'model': 'gfs', 'time': cycle.isoformat(),
                            'dbz': first['dbz'], 'zone': 'regional',
                            'zones': first['zones'], 'peak': first['peak']})
            break
        except Exception as exc:
            errors.append(f'{cycle.isoformat()} f000: {exc}')
    if chosen is None:
        STATUS.write_text(json.dumps({'status':'error','errors':errors,'updated':now.isoformat()}, indent=2))
        raise RuntimeError('No NOAA GFS cycle available: '+'; '.join(errors))
    for hour in range(3, 121, 3):
        try:
            field = download_field(session, chosen, hour)
            valid = chosen + timedelta(hours=hour)
            records.append({'model':'gfs','time':valid.isoformat(),
                            'dbz':field['dbz'],'zone':'regional',
                            'zones':field['zones'],'peak':field['peak']})
            print(f'GFS {valid.isoformat()} regional {field["dbz"]} dBZ '
                  f'Springfield {field["zones"]["springfield_area"]} dBZ '
                  f'west approach {field["zones"]["approach_west"]} dBZ', flush=True)
        except Exception as exc:
            errors.append(f'f{hour:03d}: {exc}')
            print('WARNING', errors[-1], flush=True)
    if len(records) < 4:
        raise RuntimeError(f'Only {len(records)} records decoded; refusing to publish incomplete data')
    merge_model_records(OUT, 'gfs', records, 8)
    STATUS.write_text(json.dumps({'status':'partial' if errors else 'ok', 'model':'gfs',
                                  'cycle':chosen.isoformat(),'updated':now.isoformat(),
                                  'record_count':len(records),'errors':errors},indent=2)+'\n')
    print(f'Wrote {len(records)} geographically resolved GFS records. '
          'Other models not yet supported. Geographic boxes are approximate.')


if __name__ == '__main__':
    main()
