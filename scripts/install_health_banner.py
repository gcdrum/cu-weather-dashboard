"""Install or upgrade NOAA status and independent decoded-gust chart."""
from pathlib import Path
import re

path = Path("index.html")
html = path.read_text(encoding="utf-8")
snippet = r"""
<script id="cu-forecast-health-monitor">
(() => {
 const id='cu-forecast-health-banner';
 const esc=s=>String(s??'?').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
 function host(){
  let el=document.getElementById(id);
  if(!el){el=document.createElement('section');el.id=id;el.setAttribute('aria-label','NOAA model health and gust comparison');document.body.prepend(el);}
  el.style.cssText='position:relative;z-index:5;margin:0 0 16px;padding:14px;border:1px solid #536b78;border-radius:12px;background:#17252d;color:#edf4f8;font:14px system-ui,sans-serif';
  return el;
 }
 async function get(name){
  const r=await fetch('./'+name+'?t='+Date.now(),{cache:'no-store'});
  if(!r.ok)throw Error(name+' HTTP '+r.status);
  return r.json();
 }
 function plot(data, color){
  const hours=(data?.hours||[]).filter(h=>h.time&&Array.isArray(h.gust_ms));
  return hours.map(h=>({time:Date.parse(h.time.endsWith('Z')?h.time:h.time+'Z'),value:Math.max(0,...h.gust_ms.filter(Number.isFinite))*2.236936})).filter(p=>Number.isFinite(p.time)&&Number.isFinite(p.value)).sort((a,b)=>a.time-b.time).map(p=>({...p,color}));
 }
 function chart(series){
  const all=series.flat(),W=720,H=180,L=40,R=14,T=12,B=27;
  if(!all.length)return '<div style="padding:12px;color:#ffcf91">No decoded gust samples available</div>';
  const lo=Math.min(...all.map(p=>p.time)),hi=Math.max(...all.map(p=>p.time)),max=Math.max(40,Math.ceil(Math.max(...all.map(p=>p.value))/10)*10);
  const x=t=>L+(t-lo)/Math.max(1,hi-lo)*(W-L-R),y=v=>H-B-v/max*(H-T-B);
  let svg='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Decoded model maximum 12-site gusts in miles per hour, independent of outage predictions" style="width:100%;height:auto;display:block">';
  for(let v=0;v<=max;v+=10){svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+y(v)+'" y2="'+y(v)+'" stroke="#43535d" stroke-dasharray="3 4"/><text x="32" y="'+(y(v)+4)+'" text-anchor="end" font-size="12" fill="#b6c6ce">'+v+'</text>';}
  for(const points of series){if(!points.length)continue;svg+='<polyline fill="none" stroke="'+points[0].color+'" stroke-width="2.5" points="'+points.map(p=>x(p.time)+','+y(p.value)).join(' ')+'"/>';}
  for(let i=0;i<=4;i++){const t=lo+(hi-lo)*i/4;svg+='<text x="'+x(t)+'" y="'+(H-5)+'" text-anchor="middle" font-size="11" fill="#b6c6ce">'+new Date(t).toISOString().slice(5,16).replace('T',' ')+'Z</text>';}
  return svg+'</svg>';
 }
 async function refresh(){
  const el=host();
  try{
   const health=await get('forecast_health.json');
   const reportAge=Math.round((Date.now()-Date.parse(health.checked_at))/60000);
   const modelEntries=['hrrr','rrfs'].map(name=>({name,m:health.models?.[name]||{}}));
   const cards=modelEntries.map(({name,m})=>{
    const age=Math.round((Date.now()-Date.parse(m.updated))/60000);
    const stale=m.state!=='current'||!Number.isFinite(age)||age>90||reportAge>90;
    const pct=Math.max(0,Math.min(100,Number(m.percent_complete)||0));
    const cycle=m.cycle?new Date(m.cycle).getUTCHours().toString().padStart(2,'0')+'Z':'?';
    return '<div style="flex:1;min-width:220px;background:#22343e;padding:12px;border-radius:9px;border:1px solid '+(stale?'#e4a064':'#526f76')+'"><div style="display:flex;justify-content:space-between;gap:8px;align-items:center"><strong style="font-size:16px">'+name.toUpperCase()+' · '+cycle+'</strong><strong style="color:'+(stale?'#ffb08a':'#85dfb5')+'">'+(stale?'STALE':'CURRENT')+'</strong></div><div style="font-size:24px;font-weight:700;margin:8px 0 5px">'+pct.toFixed(1)+'% <span style="font-size:13px;font-weight:400;color:#c0d0d9">'+esc(m.hours)+' / '+esc(m.expected_hours)+' hours</span></div><div style="height:10px;background:#455762;border-radius:10px;overflow:hidden"><div style="height:100%;width:'+pct+'%;background:'+(stale?'#d78d4a':'#3cb58a')+'"></div></div><div style="font-size:12px;margin-top:7px;color:#c0d0d9">'+(Number.isFinite(age)?age+' min old':'Update unknown')+'</div></div>';
   }).join('');
   const bad=reportAge>90||modelEntries.some(({m})=>m.state!=='current'||Date.now()-Date.parse(m.updated)>5400000);
   el.innerHTML='<div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:12px"><strong style="font-size:17px">NOAA model status</strong><strong style="color:'+(bad?'#ffb08a':'#85dfb5')+'">'+(bad?'⚠ DATA FRESHNESS WARNING':'✓ Data recently updated')+'</strong></div><div style="display:flex;gap:10px;flex-wrap:wrap">'+cards+'</div><div id="cu-decoded-gust-chart" style="margin-top:14px"><strong>Decoded NOAA gust comparison (mph)</strong><div style="font-size:12px;color:#c0d0d9">Independent model comparison · not yet integrated into outage prediction graph</div><div style="padding:10px">Loading gust data…</div></div><div style="font-size:12px;color:#b7c8d2;margin-top:7px">Health report '+reportAge+' min old · Freshness and forecast completeness are different measures</div>';
   const results=await Promise.allSettled([get('hrrr_wind.json'),get('rrfs_wind.json')]);
   const series=results.map((r,i)=>r.status==='fulfilled'?plot(r.value,i===0?'#4db8ff':'#f5b95e'):[]);
   const browserCache=window.cuSurfaceWindCache||{};
   const liveModels=[['gfs','#8de58a'],['nam','#da9bff']];
   for(const [name,color] of liveModels){
     const record=browserCache[name];
     const rows=Array.isArray(record?.rows)?record.rows:[];
     series.push(rows.map(h=>({time:Date.parse(String(h.time).endsWith('Z')?h.time:h.time+'Z'),value:Number(h.max),color})).filter(p=>Number.isFinite(p.time)&&Number.isFinite(p.value)).sort((a,b)=>a.time-b.time));
   }
   // Publish normalized four-model gust data for other dashboard components.
   // Keep the existing outage engine untouched until numerical and convective calibration is validated.
   const names=['hrrr','rrfs','gfs','nam'];
   window.cuFourModelForecast=Object.fromEntries(names.map((name,i)=>[name,{
     source:i<2?'NOAA decoded GRIB':'Open-Meteo browser sample',
     points:series[i].map(p=>({time:new Date(p.time).toISOString(),gust_mph:p.value})),
     available:series[i].length>0
   }]));
   const feederSignal=mph=>{const x=Math.max(0,(mph-15)/5);return Math.max(0,0.2431*(Math.exp(0.5216*x)-1));};
   const near=Date.now()-3600000;
   const rows=names.map((name,i)=>{
     const future=series[i].filter(p=>p.time>=near);
     if(!future.length)return '<tr><td>'+name.toUpperCase()+'</td><td colspan="3">Unavailable</td></tr>';
     const peak=future.reduce((a,b)=>b.value>a.value?b:a);
     const tier=peak.value>=60?'Extreme':peak.value>=50?'Likely':peak.value>=40?'Possible Elevated':peak.value>=30?'Possible':'Below threshold';
     return '<tr><td>'+name.toUpperCase()+'</td><td>'+peak.value.toFixed(1)+' mph</td><td>'+tier+'</td><td>'+new Date(peak.time).toISOString().slice(5,16).replace('T',' ')+'Z</td></tr>';
   }).join('');
   const riskTable='<div style="margin-top:14px"><strong>Four-model wind threat screening</strong><div style="font-size:12px;color:#b7c8d2">Peak 12-site gust by model. Wind-only threshold screening; not a calibrated feeder-outage forecast. Convective reflectivity risk is evaluated separately.</div><div style="overflow-x:auto;margin-top:8px"><table style="width:100%;border-collapse:collapse;font-size:12px;text-align:left"><thead><tr><th>Model</th><th>Peak gust</th><th>Threat</th><th>Peak UTC</th></tr></thead><tbody>'+rows+'</tbody></table></div></div>';
   const chartEl=document.getElementById('cu-decoded-gust-chart');
   const availability=liveModels.map(([name])=>name.toUpperCase()+': '+(browserCache[name]?.rows?.length||0)+' hours').join(' · ');
   if(chartEl){chartEl.innerHTML='<strong>Decoded NOAA gust comparison (mph)</strong><div style="font-size:12px;color:#c0d0d9">Independent model comparison · not yet integrated into outage prediction graph</div><div style="font-size:12px;margin:8px 0"><span style="color:#4db8ff">● HRRR</span> &nbsp; <span style="color:#f5b95e">● RRFS</span> &nbsp; <span style="color:#8de58a">● GFS</span> &nbsp; <span style="color:#da9bff">● NAM</span> · maximum across 12 sampling sites</div>'+chart(series)+riskTable+'<div style="font-size:12px;color:#c0d0d9;margin-top:4px">GFS/NAM via existing Open-Meteo browser sampling: '+availability+'. Unavailable models are omitted, not estimated. This comparison does not change outage predictions.</div>';}
  }catch(e){el.textContent='⚠ NOAA model health unavailable: '+e.message;}
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',refresh);else refresh();
 setInterval(refresh,60000);
 // The Open-Meteo GFS/NAM requests finish asynchronously after page load.
 // Redraw when their shared cache gains new forecast rows, without fetching NOAA again.
 let lastLiveSignature='';
 setInterval(()=>{
   const cache=window.cuSurfaceWindCache||{};
   const signature=['gfs','nam'].map(name=>{
     const rows=cache[name]?.rows||[];
     return name+':'+rows.length+':'+(rows[0]?.time||'')+':'+(rows.at(-1)?.time||'');
   }).join('|');
   if(signature===lastLiveSignature)return;
   lastLiveSignature=signature;
   if(!['gfs','nam'].some(name=>(cache[name]?.rows||[]).length))return;
   refresh();
 },10000);
})();
</script>
"""
pattern=r'<script id="cu-forecast-health-monitor">.*?</script>'
if re.search(pattern,html,flags=re.S):
    html=re.sub(pattern,lambda _:snippet,html,count=1,flags=re.S)
else:
    if '</body>' not in html: raise SystemExit('Missing closing body')
    html=html.replace('</body>',snippet+'</body>',1)
path.write_text(html,encoding='utf-8')
print('Installed model health cards and independent gust chart')
