"""NOAA HRRR numerical reflectivity and 10-m gust/velocity for CU dashboard.
Uses NOAA's public HRRR S3 GRIB2 byte ranges; no rendered map imagery.
Requires: requests, numpy, eccodes, system libeccodes.
"""
import json, re, tempfile, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import requests
from eccodes import codes_grib_new_from_file, codes_get_array, codes_release

ROOT='https://noaa-hrrr-bdp-pds.s3.amazonaws.com'
ZONES={'upstream_west':(-95.5,-94.0,35.5,39.0),'approach_west':(-94.0,-93.3,36.2,38.3),'springfield_area':(-93.6,-92.9,36.9,37.6),'downstream_east':(-92.9,-91.5,35.5,39.0)}
POINTS=[('NW / Willard side',37.258,-93.405),('North',37.290,-93.310),('NE / Strafford side',37.258,-93.190),('West',37.221,-93.395),('Central Springfield',37.209,-93.292),('East',37.215,-93.210),('SW / Republic side',37.170,-93.392),('South / Battlefield',37.150,-93.292),('SE',37.155,-93.220),('Far South / West',37.095,-93.405),('Far South / Central',37.088,-93.300),('Far South / East',37.095,-93.220)]
S=requests.Session(); S.headers['User-Agent']='CU-Weather-Dashboard/1.0 (public NOAA research)'
def get(url,**kw):
    for attempt in range(3):
        try:
            r=S.get(url,timeout=50,**kw);r.raise_for_status();return r
        except (requests.RequestException,ValueError):
            if attempt==2:raise
            time.sleep(2*(attempt+1))
def index_fields(root):
    lines=get(root+'.idx').text.splitlines();out=[]
    for i,line in enumerate(lines):
        parts=line.split(':',3)
        if len(parts)<4:continue
        try: start=int(parts[1])
        except ValueError:continue
        out.append((start,line))
    return out

def choose(fields,token):
    for i,(start,line) in enumerate(fields):
        # idx entries use :REFC:entire atmosphere: and :GUST:surface: etc.
        if re.search(r':'+re.escape(token)+r':',line):
            end=fields[i+1][0]-1 if i+1<len(fields) else None
            return start,end
    return None

def read_field(root,span):
    start,end=span
    if end is None:raise ValueError('Cannot range-fetch final GRIB field without an end offset')
    r=get(root,headers={'Range':f'bytes={start}-{end}'})
    if r.status_code!=206 or not r.content.startswith(b'GRIB'):raise ValueError('No GRIB byte-range response')
    with tempfile.NamedTemporaryFile(suffix='.grib2') as tmp:
        tmp.write(r.content);tmp.flush()
        with open(tmp.name,'rb') as fh:
            handle=codes_grib_new_from_file(fh)
            if handle is None:raise ValueError('GRIB decoder returned no field')
            try:
                lat=codes_get_array(handle,'latitudes');lon=codes_get_array(handle,'longitudes');val=codes_get_array(handle,'values')
                lon=np.where(lon>180,lon-360,lon)
                return lat,lon,val
            finally:codes_release(handle)

def reflectivity(lat,lon,v):
    valid=(lat>=35.5)&(lat<=39)&(lon>=-95.5)&(lon<=-91.5)&np.isfinite(v)&(v>=0)&(v<=90)
    if not np.any(valid):raise ValueError('No valid regional REFC grid cells')
    ids=np.flatnonzero(valid);peak=ids[int(np.argmax(v[valid]))]
    zones={}
    for name,(w,e,s,n) in ZONES.items():
        m=valid&(lon>=w)&(lon<=e)&(lat>=s)&(lat<=n)
        zones[name]=round(float(np.max(v[m])),1) if np.any(m) else None
    return {'dbz':round(float(np.max(v[valid])),1),'zones':zones,'peak':{'lat':round(float(lat[peak]),3),'lon':round(float(lon[peak]),3)}}

def sample(lat,lon,v):
    out=[]
    for name,y,x in POINTS:
        distance=(lat-y)**2+((lon-x)*np.cos(np.deg2rad(y)))**2
        j=int(np.argmin(distance))
        z=float(v[j]);out.append(round(z,2) if np.isfinite(z) and abs(z)<1e6 else None)
    return out

def cycle_root(cycle,lead):
    return f'{ROOT}/hrrr.{cycle:%Y%m%d}/conus/hrrr.t{cycle:%H}z.wrfsfcf{lead:02d}.grib2'

def process(cycle,lead):
    root=cycle_root(cycle,lead);fields=index_fields(root)
    ref=choose(fields,'REFC');gust=choose(fields,'GUST');u=next((choose(fields,'UGRD') for _ in [0]),None);v=choose(fields,'VGRD')
    # Disambiguate 10-m winds from other levels.
    def wind_span(var):
        for i,(start,line) in enumerate(fields):
            if f':{var}:10 m above ground:' in line:
                return start,fields[i+1][0]-1 if i+1<len(fields) else None
        return None
    u=wind_span('UGRD');v=wind_span('VGRD')
    if not ref or not gust or not u or not v:raise ValueError('Missing REFC/GUST/10-m UGRD/VGRD in HRRR index')
    a,b,c=read_field(root,ref);rf=reflectivity(a,b,c)
    a,b,g=read_field(root,gust);gusts=sample(a,b,g)
    a,b,uu=read_field(root,u);upts=sample(a,b,uu)
    a,b,vv=read_field(root,v);vpts=sample(a,b,vv)
    winds=[round((x*x+y*y)**.5,2) if x is not None and y is not None else None for x,y in zip(upts,vpts)]
    valid=cycle+timedelta(hours=lead)
    return ({'model':'hrrr','time':valid.isoformat(),'dbz':rf['dbz'],'zone':'regional','zones':rf['zones'],'peak':rf['peak']},
            {'time':valid.strftime('%Y-%m-%dT%H:%M'),'gust_ms':gusts,'wind_ms':winds})

def main():
    now=datetime.now(timezone.utc);hour=now.replace(minute=0,second=0,microsecond=0)
    chosen=None;first=None;errors=[]
    # NOAA HRRR generally available ~1-2 hours after cycle; verify by fetching.
    for back in range(2,9):
        cycle=hour-timedelta(hours=back)
        try:
            first=process(cycle,0);chosen=cycle;break
        except Exception as e:errors.append(f'{cycle:%Y-%m-%d %HZ} f00: {e}')
    if chosen is None:raise RuntimeError('No available HRRR cycle: '+'; '.join(errors))
    # Standard hourly cycles extend to 18h; 00/06/12/18Z cycles may extend to 48h.
    maxlead=48 if chosen.hour%6==0 else 18
    pairs=[first]
    for lead in range(1,maxlead+1):
        try:
            pairs.append(process(chosen,lead))
            print(f'HRRR {chosen:%HZ} f{lead:02d}: REFC and 12-site wind decoded',flush=True)
        except Exception as e:
            errors.append(f'f{lead:02d}: {e}');print('WARNING',errors[-1],flush=True)
    if len(pairs)<8:raise RuntimeError('Only '+str(len(pairs))+' HRRR forecast hours; existing published data retained')
    # Never erase the GFS records; retain only fresh HRRR records for the chosen cycle.
    dest=Path('reflectivity.json')
    existing=json.loads(dest.read_text()) if dest.exists() else []
    gfs=[r for r in existing if r.get('model')!='hrrr']
    dest.write_text(json.dumps(sorted(gfs+[a for a,b in pairs],key=lambda r:(r['time'],r['model'])),indent=2)+'\n')
    payload={'model':'hrrr','cycle':chosen.isoformat(),'updated':now.isoformat(),
             'source':'NOAA HRRR wrfsfc GRIB2, 10-m U/V and surface gust (m/s)',
             'points':[{'name':n,'lat':y,'lon':x} for n,y,x in POINTS],
             'hours':[b for a,b in pairs],'errors':errors}
    Path('hrrr_wind.json').write_text(json.dumps(payload,indent=2)+'\n')
    Path('hrrr_status.json').write_text(json.dumps({'cycle':chosen.isoformat(),'updated':now.isoformat(),'hours':len(pairs),'expected_hours':maxlead+1,'errors':errors},indent=2)+'\n')
    print(f'Published {len(pairs)} HRRR forecast hours and {len(gfs)} preserved non-HRRR reflectivity records')
if __name__=='__main__':main()
