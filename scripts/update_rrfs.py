"""RRFS observational forecast ingestion (independent of outage predictions).
Uses NOAA operational RRFS S3 index byte ranges. No synthetic values.
"""
import json, re, tempfile, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
import requests
import numpy as np
from eccodes import codes_grib_new_from_file, codes_get_array, codes_release, codes_get

BUCKET="https://noaa-rrfs-ops-pds.s3.amazonaws.com"
POINTS=[("NW / Willard side",37.258,-93.405),("North",37.290,-93.310),("NE / Strafford side",37.258,-93.190),("West",37.221,-93.395),("Central Springfield",37.209,-93.292),("East",37.215,-93.210),("SW / Republic side",37.170,-93.392),("South / Battlefield",37.150,-93.292),("SE",37.155,-93.220),("Far South / West",37.095,-93.405),("Far South / Central",37.088,-93.300),("Far South / East",37.095,-93.220)]
S=requests.Session()
S.headers["User-Agent"]="CU-Weather-Dashboard/1.0"
def fetch(url,**kw):
    for n in range(3):
        try:
            r=S.get(url,timeout=45,**kw);r.raise_for_status();return r
        except requests.RequestException:
            if n==2:raise
            time.sleep(2+n*2)
def candidates(cycle,lead):
    d=cycle.strftime("%Y%m%d");h=cycle.strftime("%H")
    f=f"{lead:03d}"
    # Operational layout: product inventory may change; verify index before decoding.
    names=[f"rrfs.t{h}z.2dfld.3km.f{f}.conus.grib2",f"rrfs.t{h}z.2dfld.3km.f{f}.na.grib2"]
    prefixes=[f"rrfs.{d}/{h}/",f"rrfs.{d}/{h}/conus/",f"rrfs.{d}/{h}/2dfld/"]
    return [BUCKET+"/"+p+n for p in prefixes for n in names]
def fields(url):
    rows=[]
    for line in fetch(url+".idx").text.splitlines():
        p=line.split(":",2)
        if len(p)>2 and p[1].isdigit():rows.append((int(p[1]),line))
    if not rows:raise ValueError("Empty GRIB index")
    return rows
def span(rows,variable,level=None):
    for i,(start,line) in enumerate(rows):
        if f":{variable}:" in line and (level is None or f":{level}:" in line):
            if i+1<len(rows):return start,rows[i+1][0]-1
    return None
def decode(url,byte_span):
    if byte_span is None:return None
    a,b=byte_span
    r=fetch(url,headers={"Range":f"bytes={a}-{b}"})
    if r.status_code!=206 or not r.content.startswith(b"GRIB"):raise ValueError("Invalid GRIB range response")
    with tempfile.NamedTemporaryFile(suffix=".grib2") as tmp:
        tmp.write(r.content);tmp.flush()
        with open(tmp.name,"rb") as f:
            g=codes_grib_new_from_file(f)
            if g is None:raise ValueError("Cannot decode GRIB")
            try:
                lat=codes_get_array(g,"latitudes");lon=codes_get_array(g,"longitudes")
                val=codes_get_array(g,"values")
                return lat,np.where(lon>180,lon-360,lon),val
            finally:codes_release(g)
def sample(field):
    if field is None:return None
    lat,lon,val=field;out=[]
    for _,y,x in POINTS:
        distance=(lat-y)**2+((lon-x)*np.cos(np.deg2rad(y)))**2
        j=int(np.argmin(distance));v=float(val[j])
        out.append(round(v,2) if np.isfinite(v) and abs(v)<1e6 else None)
    return out
def atomic(path,obj):
    p=Path(path);tmp=p.with_suffix(p.suffix+".tmp")
    tmp.write_text(json.dumps(obj, indent=2) + chr(10));tmp.replace(p)
def rrfs_lightning_diagnostic(cycle, indexed_urls):
    """Inspect and decode available RRFS LTNGSD leads; never guess units."""
    result={'model':'rrfs','cycle':cycle.isoformat(),'status':'field_unavailable',
            'units':'flashes/km²/5 min','units_verified':False,'hours':[],
            'note':'LTNG (dimensionless) is not flash density; only LTNGSD is eligible.'}
    # Probe both documented height variants; unknown ecCodes parameter names
    # are diagnostic only, never grounds for assuming a density conversion.
    matches=[(lead,url,rows,i,line) for lead,(url,rows) in sorted(indexed_urls.items())
             for i,(_,line) in enumerate(rows) if ':LTNGSD:' in line]
    result['index_matches']=[{'lead':lead,'line':line[:280]} for lead,_,_,_,line in matches[:60]]
    result['field_variants']=[]
    for lead,url,rows,i,line in matches:
        if line.find(':1 m above ground:')<0:continue
        if i+1>=len(rows):continue
        field=(rows[i][0],rows[i+1][0]-1)
        try:
            a,b=field
            response=fetch(url,headers={'Range':f'bytes={a}-{b}'})
            if response.status_code!=206 or not response.content.startswith(b'GRIB'):
                raise ValueError('Invalid GRIB range response')
            with tempfile.NamedTemporaryFile(suffix='.grib2') as tmp:
                tmp.write(response.content);tmp.flush()
                with open(tmp.name,'rb') as fh:
                    g=codes_grib_new_from_file(fh)
                    if g is None:raise ValueError('No GRIB lightning message')
                    try:
                        meta={}
                        for key in ('shortName','name','units','stepType','stepRange',
                                    'typeOfLevel','level','discipline','parameterCategory',
                                    'parameterNumber','tablesVersion','localTablesVersion'):
                            try:meta[key]=str(codes_get(g,key))
                            except Exception:pass
                    finally:codes_release(g)
            if not any(v.get('index')==line[:280] for v in result['field_variants']):
                result['field_variants'].append({'index':line[:280],'metadata':meta})
            unit=meta.get('units','').replace(' ','').lower()
            factor={'m-2s-1':300000000.0,'m**-2s**-1':300000000.0,
                    '1/m2/s':300000000.0,'m^-2s^-1':300000000.0,
                    'flashes/km2/5min':1.0,'flasheskm-2(5min)-1':1.0}.get(unit)
            # ecCodes may not know the RRFS parameter name/units, but the
            # internationally defined GRIB2 discipline/category/number is
            # sufficient when all three match 0/17/0 and level is 1 m AGL.
            # This is a 1-hour MAXIMUM rate, expressed as a 5-min equivalent,
            # not a measured or accumulated five-minute flash count.
            known_parameter=(meta.get('discipline')=='0' and
                             meta.get('parameterCategory')=='17' and
                             meta.get('parameterNumber')=='0' and
                             meta.get('typeOfLevel')=='heightAboveGround' and
                             meta.get('level')=='1')
            if factor is None and known_parameter:
                factor=300000000.0
                result['units_basis']='GRIB2 0-17-0: m^-2 s^-1 (1-hour maximum); 5-min equivalent rate'
            if factor is None:
                result['status']='units_unverified'
                continue
            lat,lon,values=decode(url,field)
            mask=(lat>=36.85)&(lat<=37.65)&(lon>=-94.2)&(lon<=-92.8)&np.isfinite(values)&(values>=0)
            if not np.any(mask):
                result.setdefault('sample_diagnostics',[]).append({'lead':lead,'level':meta.get('level'),'grid_points':int(len(values)),'finite':int(np.count_nonzero(np.isfinite(values))),'latitude_range':[float(np.nanmin(lat)),float(np.nanmax(lat))],'longitude_range':[float(np.nanmin(lon)),float(np.nanmax(lon))],'nonnegative_in_area':0})
                continue
            result.setdefault('sample_diagnostics',[]).append({'lead':lead,'level':meta.get('level'),'nonnegative_in_area':int(np.count_nonzero(mask)),'native_peak':float(np.max(values[mask]))})
            peak=float(np.max(values[mask]))*factor
            if not (0 <= peak <= 15):
                result.setdefault('diagnostic_errors',[]).append(f'LTNGSD lead {lead}: implausible converted density {peak:g}; rejecting, not treating as zero')
                continue
            result.update(status='available',units_verified=True,
                grib_metadata=meta,source='RRFS LTNGSD; native units '+meta.get('units',''),
                hours=result['hours']+[{'time':(cycle+timedelta(hours=lead)).isoformat(),
                        'value':round(peak,5),'units_verified':True,
                        'metric':'five_minute_equivalent_of_one_hour_maximum_rate'}])
        except Exception as exc:
            result.setdefault('diagnostic_errors',[]).append(str(exc)[:250])
    # Merge valid forecast hours from previous cycles, never synthesizing zeros.
    dest=Path('rrfs_lightning.json')
    prior=json.loads(dest.read_text()) if dest.exists() else {}
    merged={}
    for row in prior.get('hours',[]):
        if isinstance(row,dict) and row.get('time') and row.get('units_verified') is True and isinstance(row.get('value'),(int,float)) and 0 <= row['value'] <= 15:
            merged[row['time']]=dict(row,source_cycle=row.get('source_cycle',prior.get('cycle','')))
    for row in result['hours']:
        merged[row['time']]=dict(row,source_cycle=cycle.isoformat())
    cutoff=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    result['hours']=[merged[k] for k in sorted(merged) if k>=cutoff]
    # Lightning density bands, derived only from decoded, verified LTNGSD.
    # A zero is valid only for a decoded hour; absent hours stay absent.
    edges=(0.1,0.3,1.0,3.0,6.0)
    for row in result['hours']:
        if row.get('units_verified') is True and isinstance(row.get('value'),(int,float)):
            v=row['value']
            row['lightning_band']=sum(v>=edge for edge in edges) if v>=0 else None
            row['lightning_detected']=v>0 if v>=0 else None
    result['bands_flashes_per_km2_per_5min']=[0,0.1,0.3,1,3,6,15]
    result['band_policy']='band 0: 0 to <0.1; 1: 0.1 to <0.3; 2: 0.3 to <1; 3: 1 to <3; 4: 3 to <6; 5: >=6'
    result['conversion_source']='NCEP GRIB2 table 4.2-0-17, parameter 0: m^-2 s^-1'
    result['time_statistic']='one-hour maximum rate expressed as five-minute equivalent; not accumulated flashes'
    result['coverage_policy']='per-valid-hour replacement; older cycle retained until replaced'
    result['units_verified']=bool(result['hours']) and all(r.get('units_verified') is True for r in result['hours'])
    if result['hours'] and result['status']!='available':result['status']='retained_previous_cycle'
    if result['hours'] and result['units_verified'] and result['status']=='units_unverified':result['status']='available'
    if not result['hours'] and result['status']=='field_unavailable' and matches:
        result['status']='no_valid_geographic_samples'
    result['matched_fields']=len(matches)
    result['valid_hours']=len(result['hours'])
    atomic('rrfs_lightning.json',result)
    print('RRFS LTNGSD: '+result['status'],flush=True)

def main():
    now=datetime.now(timezone.utc);hour=now.replace(minute=0,second=0,microsecond=0)
    errors=[];chosen=None;first_url=None
    for back in range(0,13):
        cycle=hour-timedelta(hours=back)
        if cycle.hour % 3: continue
        for url in candidates(cycle,1):
            try:
                rows=fields(url)
                if span(rows,"GUST") or span(rows,"REFC"):
                    chosen=cycle;first_url=url;break
            except Exception:pass
        if chosen:break
    if not chosen:
        atomic("rrfs_status.json",{"status":"unavailable","updated":now.isoformat(),"errors":["No supported RRFS operational 2dfld index found; check bucket layout"]})
        print("RRFS unavailable; no fabricated data",flush=True);return
    previous=Path("rrfs_wind.json")
    old=json.loads(previous.read_text()) if previous.exists() else {}
    # Persist an incoming cycle separately, so each scheduled run can finish it
    # without replacing the active forecast prematurely.
    pending_path=Path("rrfs_pending.json")
    pending=json.loads(pending_path.read_text()) if pending_path.exists() else {}
    source=old if old.get("cycle")==chosen.isoformat() else pending if pending.get("cycle")==chosen.isoformat() else {}
    hours={r["time"]:r for r in source.get("hours",[]) if isinstance(r,dict) and "time" in r}
    # RRFS 3-km 2dfld intermediate 3-hour cycles commonly expose an
    # 18-hour forecast; do not claim 60 missing hours for those cycles.
    maxlead=60 if chosen.hour%6==0 else 18
    newly_decoded = 0
    missing_streak = 0
    # Probe indexes in parallel so unpublished hours do not consume minutes.
    # Prioritize the near-term 24h forecast before the extended horizon.
    missing_leads=[lead for lead in range(1,maxlead+1)
                   if (chosen+timedelta(hours=lead)).strftime("%Y-%m-%dT%H:%M") not in hours]
    def probe(lead):
        for candidate in candidates(chosen,lead):
            try:
                response=requests.get(candidate+'.idx',timeout=7,headers={'User-Agent':'CU-Weather-Dashboard/1.0'})
                if response.status_code!=200:continue
                rows=[]
                for line in response.text.splitlines():
                    parts=line.split(':',2)
                    if len(parts)>2 and parts[1].isdigit():rows.append((int(parts[1]),line))
                if rows and (span(rows,'GUST') or span(rows,'REFC')):return lead,candidate,rows
            except requests.RequestException:continue
        return lead,None,None
    indexed={}
    # Limit concurrent requests and check near-term first.
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(probe,lead) for lead in missing_leads[:36]]
        for future in as_completed(futures):
            lead,url,rows=future.result()
            if url:indexed[lead]=(url,rows)
    # Lightning must probe all available leads, including wind hours already decoded.
    lightning_indexed={1:(first_url,fields(first_url)),**indexed}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(probe,lead) for lead in range(2,maxlead+1) if lead not in lightning_indexed]
        for future in as_completed(futures):
            lead,url,rows=future.result()
            if url:lightning_indexed[lead]=(url,rows)
    rrfs_lightning_diagnostic(chosen,lightning_indexed)
    print(f'RRFS index probe: {len(indexed)}/{min(36,len(missing_leads))} missing leads available',flush=True)
    if missing_leads and not indexed:errors.append('No newly published RRFS hours in current probe window')
    # Keep manual runs bounded, but allow useful catch-up without waiting for
    # several additional dispatches when the NOAA cycle is already published.
    max_new_per_run = 36
    for lead in sorted(indexed):
        stamp=(chosen+timedelta(hours=lead)).strftime("%Y-%m-%dT%H:%M")
        if stamp in hours:continue
        try:
            url,rows=indexed.get(lead,(None,None))
            if not url:
                errors.append(f'f{lead:03d}: no published RRFS index at any supported path')
                print('RRFS waiting:', errors[-1], flush=True)
                # A missing lead may be a publication gap; try subsequent hours
                # before concluding the entire forecast cycle is exhausted.
                missing_streak += 1
                if missing_streak < 2:
                    continue
                print('RRFS stopping after two consecutive unpublished forecast hours', flush=True)
                break
            gust=sample(decode(url,span(rows,"GUST")))
            ref=sample(decode(url,span(rows,"REFC")))
            u=sample(decode(url,span(rows,"UGRD","10 m above ground")))
            v=sample(decode(url,span(rows,"VGRD","10 m above ground")))
            wind=[round((a*a+b*b)**.5,2) if a is not None and b is not None else None for a,b in zip(u,v)] if u and v else None
            if gust is None and ref is None and wind is None:raise ValueError("Required fields absent")
            hours[stamp]={"time":stamp,"lead":lead,"gust_ms":gust,"wind_ms":wind,"site_dbz":ref}
            missing_streak = 0
            newly_decoded += 1
            print(f"RRFS {chosen:%HZ} f{lead:03d} decoded",flush=True)
        except Exception as exc:
            errors.append(f"f{lead:03d}: {exc}")
            print('RRFS decode warning:', errors[-1], flush=True)
            break
        # Bound each run's new decoding work while allowing incremental catch-up.
        if newly_decoded >= max_new_per_run:break
    print(f"RRFS {chosen:%HZ}: {len(hours)}/{maxlead} hours available; {newly_decoded} newly decoded; errors={errors[:2]}", flush=True)
    if hours:
        atomic("rrfs_pending.json",{"model":"rrfs","cycle":chosen.isoformat(),"updated":now.isoformat(),
             "hours":[hours[k] for k in sorted(hours)]})
        payload={"model":"rrfs","cycle":chosen.isoformat(),"updated":now.isoformat(),
                 "source":"NOAA operational RRFS 3km 2dfld GRIB2",
                 "points":[{"name":n,"lat":y,"lon":x} for n,y,x in POINTS],
                 "hours":[hours[k] for k in sorted(hours)]}
        # Per-valid-hour replacement, retaining older extended-horizon forecasts.
        merged={}
        for row in old.get('hours',[]):
            if isinstance(row,dict) and row.get('time'):
                merged[row['time']]=dict(row,source_cycle=row.get('source_cycle',old.get('cycle','')))
        for row in payload['hours']:
            if isinstance(row,dict) and row.get('time'):
                merged[row['time']]=dict(row,source_cycle=chosen.isoformat())
        cutoff=(now-timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M')
        payload['hours']=[merged[k] for k in sorted(merged) if k>=cutoff]
        payload['coverage_policy']='latest available value per valid hour; source_cycle per hour'
        atomic("rrfs_wind.json",payload)
    atomic("rrfs_status.json",{"status":"partial" if hours else "unavailable","cycle":chosen.isoformat(),"updated":now.isoformat(),"hours":sum(1 for k in hours if chosen.strftime("%Y-%m-%d") and 1 <= round((datetime.fromisoformat(k)-chosen.replace(tzinfo=None)).total_seconds()/3600) <= maxlead),"expected_hours":maxlead,"percent_complete":round(100*min(maxlead,sum(1 for k in hours if 1 <= round((datetime.fromisoformat(k)-chosen.replace(tzinfo=None)).total_seconds()/3600) <= maxlead))/maxlead,1),"complete":sum(1 for k in hours if 1 <= round((datetime.fromisoformat(k)-chosen.replace(tzinfo=None)).total_seconds()/3600) <= maxlead)>=maxlead,"errors":errors})
if __name__=="__main__":main()
