"""Publish GFS/NAM 12-point wind-gust forecasts independently of browser loading.

Uses Open-Meteo's NOAA model API (same endpoint/models as existing dashboard).
These are not direct NOAA GRIB decodes. Never synthesize missing points.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

POINTS = [
    ("NW / Willard side",37.258,-93.405),("North",37.290,-93.310),
    ("NE / Strafford side",37.258,-93.190),("West",37.221,-93.395),
    ("Central Springfield",37.209,-93.292),("East",37.215,-93.210),
    ("SW / Republic side",37.170,-93.392),("South / Battlefield",37.150,-93.292),
    ("SE",37.155,-93.220),("Far South / West",37.095,-93.405),
    ("Far South / Central",37.088,-93.300),("Far South / East",37.095,-93.220)
]
MODELS = {"gfs":("gfs_global",7), "nam":("ncep_nam_conus",3)}
URL = "https://api.open-meteo.com/v1/gfs"
OUT = Path("model_winds.json")

def fetch(model, point):
    _, lat, lon = point
    params = {"latitude":lat,"longitude":lon,"hourly":"wind_gusts_10m,wind_speed_10m",
              "models":model,"wind_speed_unit":"mph","timezone":"UTC",
              "forecast_days":MODELS_BY_API[model],"cell_selection":"nearest"}
    last = None
    for attempt in range(3):
        try:
            r=requests.get(URL,params=params,timeout=28,headers={"User-Agent":"CU-Weather-Dashboard/1.0"})
            r.raise_for_status()
            data=r.json()
            if data.get("error"): raise ValueError(data.get("reason","API error"))
            h=data.get("hourly") or {}
            times=h.get("time") or []
            gust=h.get("wind_gusts_10m") or []
            wind=h.get("wind_speed_10m") or []
            if not times or len(times)!=len(gust) or len(times)!=len(wind):
                raise ValueError("Missing/misaligned hourly wind fields")
            return {"time":times,"gust":gust,"wind":wind}
        except (requests.RequestException,ValueError) as exc:
            last=str(exc)
            time.sleep(1+attempt)
    raise RuntimeError(last)

MODELS_BY_API={api:days for api,days in MODELS.values()}

def build(name, api):
    rows={}
    errors=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(fetch,api,p):i for i,p in enumerate(POINTS)}
        for fut in as_completed(futures):
            idx=futures[fut]
            try:
                result=fut.result()
                for j,t in enumerate(result["time"]):
                    row=rows.setdefault(t,{"time":t,"gust_mph":[None]*len(POINTS),"wind_mph":[None]*len(POINTS)})
                    for field,key in (("gust","gust_mph"),("wind","wind_mph")):
                        value=result[field][j]
                        row[key][idx]=float(value) if isinstance(value,(float,int)) else None
            except Exception as exc:
                errors.append(f"{POINTS[idx][0]}: {exc}")
    hours=[r for r in sorted(rows.values(),key=lambda r:r["time"]) if any(v is not None for v in r["gust_mph"])]
    return {"source":"Open-Meteo NOAA model API","model":name,"updated":datetime.now(timezone.utc).isoformat(),
            "points":[{"name":p[0],"lat":p[1],"lon":p[2]} for p in POINTS],
            "hours":hours,"successful_points":len(POINTS)-len(errors),"errors":errors[:12]}

def main():
    existing={}
    if OUT.exists():
        try: existing=json.loads(OUT.read_text())
        except (ValueError,OSError): pass
    existing.setdefault("models",{})
    for name,(api,days) in MODELS.items():
        try:
            result=build(name,api)
            if result["successful_points"]<6 or len(result["hours"])<12:
                raise ValueError(f"Insufficient coverage: {result['successful_points']} sites, {len(result['hours'])} hours")
            existing["models"][name]=result
            print(f"{name.upper()}: {len(result['hours'])} hours / {result['successful_points']} sites")
        except Exception as exc:
            print(f"WARNING {name}: {exc}; retaining last published data")
    existing["checked_at"]=datetime.now(timezone.utc).isoformat()
    OUT.write_text(json.dumps(existing,separators=(",",":"))+"\n")

if __name__=="__main__":
    main()
