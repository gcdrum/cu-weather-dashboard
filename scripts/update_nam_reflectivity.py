"""NOAA NAM CONUS-nest composite reflectivity; optional, non-destructive."""
import json, tempfile
from pathlib import Path
from datetime import datetime,timezone,timedelta
import requests,numpy as np
from eccodes import codes_grib_new_from_file,codes_get_array,codes_release

OUT=Path("reflectivity.json")
ZONES={'upstream_west':(-95.5,-94.,35.5,39.),'approach_west':(-94.,-93.3,36.2,38.3),'springfield_area':(-93.6,-92.9,36.9,37.6),'downstream_east':(-92.9,-91.5,35.5,39.)}
BASE="https://nomads.ncep.noaa.gov/cgi-bin/filter_nam_conusnest.pl"
S=requests.Session();S.headers.update({'User-Agent':'CU-Weather-Dashboard/1.0'})
def field(cycle,lead):
    filename=f"nam.t{cycle:%H}z.conusnest.hiresf{lead:02d}.tm00.grib2"
    params={'file':filename,'var_REFC':'on','lev_entire_atmosphere':'on','subregion':'','leftlon':'264.5','rightlon':'268.5','toplat':'39','bottomlat':'35.5','dir':f"/nam.{cycle:%Y%m%d}"}
    response=S.get(BASE,params=params,timeout=45);response.raise_for_status()
    if not response.content.startswith(b'GRIB'):raise ValueError('NAM response is not GRIB')
    with tempfile.NamedTemporaryFile(suffix='.grib2') as f:
        f.write(response.content);f.flush()
        with open(f.name,'rb') as src:
            handle=codes_grib_new_from_file(src)
            if handle is None:raise ValueError('No NAM GRIB field')
            try:
                lat=codes_get_array(handle,'latitudes')
                lon=codes_get_array(handle,'longitudes')
                val=codes_get_array(handle,'values')
            finally:codes_release(handle)
    lon=np.where(lon>180,lon-360,lon)
    mask=(lat>=35.5)&(lat<=39)&(lon>=-95.5)&(lon<=-91.5)&np.isfinite(val)&(val>=0)&(val<=90)
    if not np.any(mask):raise ValueError('No valid NAM regional grid')
    zones={}
    for name,(w,e,s,n) in ZONES.items():
        m=mask&(lat>=s)&(lat<=n)&(lon>=w)&(lon<=e)
        zones[name]=round(float(np.max(val[m])),1) if np.any(m) else None
    ids=np.flatnonzero(mask);idx=ids[int(np.argmax(val[mask]))]
    return {'model':'nam','time':(cycle+timedelta(hours=lead)).isoformat(),'dbz':round(float(np.max(val[mask])),1),'zone':'regional','zones':zones,'peak':{'lat':round(float(lat[idx]),3),'lon':round(float(lon[idx]),3)},'source_cycle':cycle.isoformat(),'source':'NOAA NAM CONUS nest REFC'}
def main():
    now=datetime.now(timezone.utc)
    cycle=now.replace(hour=(now.hour//6)*6,minute=0,second=0,microsecond=0)
    cycles=[cycle-timedelta(hours=6*i) for i in range(4)]
    selected=None
    for c in cycles:
        try:
            first=field(c,1);selected=c;break
        except Exception as e:print('NAM cycle unavailable',c,e,flush=True)
    if selected is None:raise RuntimeError('No NAM cycle available')
    rows=[first]
    # NAM nest output is hourly through f60; prioritize upcoming 24h.
    for lead in range(2,25):
        try:rows.append(field(selected,lead))
        except Exception as e:print('NAM f%02d unavailable: %s'%(lead,e),flush=True)
    if len(rows)<4:raise RuntimeError('Too few NAM reflectivity records; retaining previous')
    existing=json.loads(OUT.read_text()) if OUT.exists() else []
    merged={r['time']:r for r in existing if isinstance(r,dict) and r.get('model')=='nam' and r.get('time')}
    for r in rows:merged[r['time']]=r
    cutoff=(now-timedelta(hours=1)).isoformat()
    retained=[merged[k] for k in sorted(merged) if k>=cutoff]
    others=[r for r in existing if isinstance(r,dict) and r.get('model')!='nam']
    OUT.write_text(json.dumps(sorted(others+retained,key=lambda r:(r['time'],r['model'])),indent=2)+'\n')
    print('NAM published',len(retained),'hours, current cycle',selected.isoformat(),flush=True)
if __name__=='__main__':main()
