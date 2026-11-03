"""Install or upgrade NOAA status and independent decoded-gust chart."""
from pathlib import Path
import re

path = Path("index.html")
html = path.read_text(encoding="utf-8")

# Main chart repair: fixed UTC hourly timeline. The former union of irregular
# model timestamps spaced every observation equally, compressing/expanding days.
# Keep missing model hours missing rather than inventing zero gusts/outages.
chart_start=html.find('function drawForecast(){')
if chart_start>=0:
    chart_end=html.find('const viewportWidth=',chart_start)
    if chart_end>chart_start:
        block=html[chart_start:chart_end]
        old="const times=[...new Set([...g,...n,...h,...rrfs].map(r=>r.time).filter(t=>Date.parse(t+'Z')>=now))].sort().slice(0,144); window.cuV50MainTimes=times.slice();"
        new="""const startUTC=Math.floor(Date.now()/3600000)*3600000;
 const times=Array.from({length:169},(_,i)=>new Date(startUTC+i*3600000).toISOString().slice(0,16));
 window.cuV50MainTimes=times.slice();"""
        if old in block:
            html=html[:chart_start]+block.replace(old,new)+html[chart_end:]
        elif new not in block:
            print('WARNING: main chart timeline pattern not found; no timeline replacement')

snippet = r"""
<script id="cu-forecast-health-monitor">
(() => {
 const id='cu-forecast-health-banner';
 let testModel=null;
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
 function chart(series,minimumScale=40,windows=[]){
  const horizonStart=Date.now()-3600000,horizonEnd=Date.now()+48*3600000;
  series=series.map(points=>points.filter(p=>Number.isFinite(p.time)&&p.time>=horizonStart&&p.time<=horizonEnd));
  const all=series.flat(),W=720,H=180,L=40,R=14,T=12,B=27;
  if(!all.length)return '<div style="padding:12px;color:#ffcf91">No decoded gust samples available</div>';
  const lo=Math.min(...all.map(p=>p.time)),hi=Math.max(...all.map(p=>p.time)),max=Math.max(minimumScale,Math.ceil(Math.max(...all.map(p=>p.value))/5)*5);
  const x=t=>L+(t-lo)/Math.max(1,hi-lo)*(W-L-R),y=v=>H-B-v/max*(H-T-B);
  let svg='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Decoded model maximum 12-site gusts in miles per hour, independent of outage predictions" style="width:100%;height:auto;display:block">';
  for(let v=0;v<=max;v+=(max<=20?5:10)){svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+y(v)+'" y2="'+y(v)+'" stroke="#43535d" stroke-dasharray="3 4"/><text x="32" y="'+(y(v)+4)+'" text-anchor="end" font-size="12" fill="#b6c6ce">'+v+'</text>';}
  // Shade only screened local convective windows; never modify feeder estimates.
  for(const w of windows){
   const left=Math.max(lo,w.start),right=Math.min(hi,w.end);
   if(right<=left)continue;
   svg+='<rect x="'+x(left)+'" y="'+T+'" width="'+Math.max(1,x(right)-x(left))+'" height="'+(H-T-B)+'" fill="#ff9a36" fill-opacity="0.20" stroke="none"/>';
  }
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
   window.cuHRRRRunLabel=results[0]?.status==='fulfilled'&&results[0].value?.cycle?new Date(results[0].value.cycle).getUTCHours().toString().padStart(2,'0')+'Z':'?';
   window.cuRRFSRunLabel=results[1]?.status==='fulfilled'&&results[1].value?.cycle?new Date(results[1].value.cycle).getUTCHours().toString().padStart(2,'0')+'Z':'?';
   const series=results.map((r,i)=>r.status==='fulfilled'?plot(r.value,i===0?'#4db8ff':'#f5b95e'):[]);
   window.cuNAMRunLabel='API';
   const browserCache=window.cuSurfaceWindCache||{};
   let published={};
   try { published=(await get('model_winds.json')).models||{}; } catch(e) {}
   window.cuNAMRunLabel=published.nam?.cycle_verified&&Number.isFinite(Date.parse(published.nam.cycle||''))?published.nam.cycle.slice(11,13)+'Z':'API';
   const sourceState={};
   const fallbackPlot=(name,color)=>{
     const data=published[name];
     const age=Date.now()-Date.parse(data?.updated||'');
     if(!(age>=0&&age<8*3600000))return [];
     return (data?.hours||[]).map(h=>({time:Date.parse(String(h.time).endsWith('Z')?h.time:h.time+'Z'),value:Math.max(0,...(h.gust_mph||[]).filter(Number.isFinite)),color})).filter(p=>Number.isFinite(p.time)&&Number.isFinite(p.value)&&p.value>0).sort((a,b)=>a.time-b.time);
   };
   const browserPlot=(name,color)=>(browserCache[name]?.rows||[]).map(h=>({time:Date.parse(String(h.time).endsWith('Z')?h.time:h.time+'Z'),value:Number(h.max),color})).filter(p=>Number.isFinite(p.time)&&Number.isFinite(p.value)).sort((a,b)=>a.time-b.time);
   // Explicit simulation is opt-in via ?cu_test_failover=hrrr or rrfs.
   // This changes only this comparison panel, never ingestion or outage predictions.
   if(testModel===null){try{testModel=new URLSearchParams(location.search).get('cu_test_failover')||'off';}catch(e){testModel='off';}}
   const simulated=['hrrr','rrfs'].includes(testModel)?testModel:null;
   for(const [name,idx,color] of [['hrrr',0,'#4db8ff'],['rrfs',1,'#f5b95e']]){
     const m=health.models?.[name]||{};
     const updated=Date.parse(m.updated||'');
     const valid=series[idx].length>0 && (m.state==='current'||m.state==='partial') && Number.isFinite(updated) && Date.now()-updated<90*60000 && reportAge<=90;
     if(valid && simulated!==name){
       const backup=fallbackPlot(name,color);
       const directEnd=Math.max(...series[idx].map(p=>p.time));
       // Prefer direct NOAA wherever its forecast exists; supplement only later hours.
       const extension=Number(m.percent_complete)<100?backup.filter(p=>p.time>directEnd):[];
       if(extension.length){
         series[idx]=series[idx].concat(extension).sort((a,b)=>a.time-b.time);
         sourceState[name]={label:'NOAA + OPEN-METEO',reason:'NOAA direct through '+new Date(directEnd).toISOString().slice(0,16)+'Z; Open-Meteo supplies '+extension.length+' later forecast hours',updated:m.updated};
       }else{
         sourceState[name]={label:'NOAA DIRECT',reason:'Current direct NOAA feed'+(Number(m.percent_complete)<100?' · '+Number(m.percent_complete).toFixed(0)+'% loaded; no verified later backup hours':''),updated:m.updated};
       }
       continue;
     }
     // Only accept an actual, independently sourced Open-Meteo series.
     // Never relabel another model or stale NOAA data as a successful failover.
     let fallback=fallbackPlot(name,color);
     let fallbackSource='published';
     if(!fallback.length){fallback=browserPlot(name,color);fallbackSource='browser';}
     if(fallback.length){
       series[idx]=fallback;
       sourceState[name]={label:'OPEN-METEO FAILOVER',reason:(simulated===name?'SIMULATED NOAA FAILURE (TEST ONLY); ':'NOAA feed stale or unavailable; ')+'using '+fallbackSource+' Open-Meteo '+name.toUpperCase()+' data',updated:published[name]?.updated||null};
     }else{
       series[idx]=[];
       sourceState[name]={label:'UNAVAILABLE',reason:(simulated===name?'SIMULATED NOAA FAILURE (TEST ONLY); ':'NOAA feed stale or unavailable; ')+'no validated Open-Meteo '+name.toUpperCase()+' fallback data',updated:m.updated||null};
     }
   }
   const liveModels=[['gfs','#8de58a'],['nam','#da9bff']];
   const coverage={};
   for(const [name,color] of liveModels){
     const remote=published[name];
     const recent=remote?.updated && Date.now()-Date.parse(remote.updated)<8*3600000;
     const remoteRows=recent&&Array.isArray(remote.hours)?remote.hours:[];
     const remoteSeries=remoteRows.map(h=>({time:Date.parse(String(h.time).endsWith('Z')?h.time:h.time+'Z'),value:Math.max(0,...(h.gust_mph||[]).filter(Number.isFinite)),color})).filter(p=>Number.isFinite(p.time)&&Number.isFinite(p.value)&&p.value>0).sort((a,b)=>a.time-b.time);
     const browserRows=Array.isArray(browserCache[name]?.rows)?browserCache[name].rows:[];
     const browserSeries=browserRows.map(h=>({time:Date.parse(String(h.time).endsWith('Z')?h.time:h.time+'Z'),value:Number(h.max),color})).filter(p=>Number.isFinite(p.time)&&Number.isFinite(p.value)).sort((a,b)=>a.time-b.time);
     series.push(remoteSeries.length?remoteSeries:browserSeries);
     coverage[name]={hours:(remoteSeries.length||browserSeries.length),source:remoteSeries.length?'published':'browser'};
     sourceState[name]={label:remoteSeries.length?'OPEN-METEO PRIMARY':browserSeries.length?'OPEN-METEO BROWSER':'UNAVAILABLE',reason:remoteSeries.length?'Published Open-Meteo forecast':browserSeries.length?'Published Open-Meteo forecast unavailable or stale; browser fallback active':'No current Open-Meteo forecast available',updated:remote?.updated||null};
   }
   // Publish normalized four-model gust data for other dashboard components.
   // Keep the existing outage engine untouched until numerical and convective calibration is validated.
   const names=['hrrr','rrfs','gfs','nam'];
   window.cuFourModelForecast=Object.fromEntries(names.map((name,i)=>[name,{
     source:sourceState[name]?.label||'UNAVAILABLE',
     points:series[i].map(p=>({time:new Date(p.time).toISOString(),gust_mph:p.value})),
     available:series[i].length>0
   }]));
   // Separate experimental outage timeline derived from selected forecast sources.
   // Existing production outage calculations remain untouched pending calibration.
   const hoursMap=new Map();
   names.forEach((name,i)=>series[i].forEach(p=>{
     if(p.time<Date.now()-3600000)return;
     const hour=new Date(p.time).toISOString();
     if(!hoursMap.has(hour))hoursMap.set(hour,[]);
     hoursMap.get(hour).push({name,gust:p.value});
   }));
   const consensus=[...hoursMap.entries()].sort((a,b)=>a[0].localeCompare(b[0])).map(([time,models])=>{
     const values=models.map(x=>x.gust).sort((a,b)=>a-b);
     const median=values.reduce((sum,v)=>sum+v,0)/values.length;
     // User-calibrated nonconvective outage curve, capped by 170 feeders.
     const feederEstimate=Math.max(0,Math.min(170,median<30?0:median<40?(median-30)*0.5:median<55?5+(median-40)*2/3:median<60?15+(median-55):20+(median-60)*2));
     const feeders=Math.round(feederEstimate*10)/10;
     const stage=feeders>=80?5:feeders>=50?4:feeders>=30?3:feeders>=10?2:1;
     return {time,median_gust_mph:median,estimated_feeders:feeders,stage,model_count:models.length,models:models.map(x=>x.name)};
   });
   // Convective screen: local-area reflectivity only. Regional peaks alone cannot
   // establish that thunderstorms threaten the utility service territory.
   let reflectivity=[];
   try {const raw=await get('reflectivity.json');reflectivity=Array.isArray(raw)?raw:[];} catch(e){}
   // RRFS publishes REFC separately from the legacy GFS/HRRR file.
   // Merge by model and valid time, retaining high-resolution source identity.
   try {
     const rrfs=await get('rrfs_reflectivity.json');
     if(Array.isArray(rrfs?.hours)){
       const byKey=new Map(reflectivity.map(x=>[String(x.model).toLowerCase()+'|'+x.time,x]));
       for(const x of rrfs.hours){
         if(x?.time&&Array.isArray(x.site_dbz))byKey.set('rrfs|'+x.time,{...x,model:'rrfs'});
       }
       reflectivity=[...byKey.values()];
     }
   } catch(e){console.warn('RRFS reflectivity unavailable',e)}
   const convective=reflectivity.filter(r=>['gfs','nam','hrrr','rrfs'].includes(String(r.model).toLowerCase())).map(r=>{
     const time=Date.parse(String(r.time).match(/(?:Z|[+-]\\d{2}:\\d{2})$/i)?r.time:String(r.time)+'Z');
     const local=r.zones?.springfield_area==null?NaN:Number(r.zones.springfield_area);
     const site=Array.isArray(r.site_dbz)?Math.max(-10,...r.site_dbz.filter(Number.isFinite)):-10;
     const dbz=Number.isFinite(local)?local:site;
     return {time,model:String(r.model).toLowerCase(),dbz};
   }).filter(r=>Number.isFinite(r.time)&&r.time>=Date.now()-3600000&&r.dbz>=35);
   const convectiveWindows=consensus.map(row=>{
     const t=Date.parse(String(row.time).match(/(?:Z|[+-]\\d{2}:\\d{2})$/i)?row.time:String(row.time)+'Z');
     const matches=convective.filter(r=>Math.abs(r.time-t)<30*60000);
     const models=[...new Set(matches.map(r=>r.model))];
     const maxDbz=matches.length?Math.max(...matches.map(r=>r.dbz)):null;
     return {...row,convective_models:models,local_reflectivity_dbz:maxDbz,convective_screen:models.length>=2?'Multi-model local convection':models.length===1?'Single-model local convection':'No local 35 dBZ signal',convective_feeders_added:0};
   });
   // Avoid arbitrary thunderstorm feeder multipliers or double-counting the wind
   // already included in gust guidance. This is a screening overlay, not a forecast.
   window.cuConvectiveScreen=convectiveWindows;
   const activeWindows=convectiveWindows.filter(x=>x.convective_models.length);
   // Shading must use actual local reflectivity valid hours, not gust-model consensus hours.
   const shadeHours=[...new Set(convective.filter(x=>Number.isFinite(x.dbz)&&x.dbz>=35).map(x=>x.time))].sort((a,b)=>a-b);
   const shadeBands=shadeHours.map(t=>({start:t-30*60000,end:t+30*60000}));
   const shadeEvidence={};
   for(const item of convective){
    const key=new Date(item.time).toISOString().slice(0,13);
    const row=shadeEvidence[key]||{maxDbz:-10,models:[]};
    row.maxDbz=Math.max(row.maxDbz,item.dbz);
    if(!row.models.includes(item.model))row.models.push(item.model);
    shadeEvidence[key]=row;
   }
   window.cuLocalConvectiveShadeEvidence=shadeEvidence;
   window.cuLocalConvectiveShadeHours=Object.keys(shadeEvidence).sort();
   if(typeof window.drawForecast==='function')window.drawForecast();
   const convectivePanel='<div style="margin-top:12px"><strong>Convective reflectivity screening</strong><div style="font-size:12px;color:#c0d0d9">Local Springfield-area reflectivity ≥35 dBZ at the forecast valid hour. Regional storms outside the service area do not count. This flags possible convective exposure but does not yet assign additional feeder outages.</div>'+(activeWindows.length?'<div style="margin-top:6px;color:#ffbd74">Potential local convection: '+activeWindows.length+' forecast hours; '+activeWindows.filter(x=>x.convective_models.length>=2).length+' supported by 2+ models.</div>':'<div style="margin-top:6px;color:#a9c8d3">No local ≥35 dBZ convective signal in the available model forecasts.</div>')+'<div style="font-size:12px;color:#c0d0d9;margin-top:5px">Convective feeder adjustment: not calibrated (0 added). No double-counting.</div></div>';
   const convectivePoints=activeWindows.map(x=>({time:Date.parse(String(x.time).match(/(?:Z|[+-]\\d{2}:\\d{2})$/i)?x.time:String(x.time)+'Z'),value:x.estimated_feeders,color:'#ff9a36'}));
   const convectiveMarkers=activeWindows.length?'<div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px">'+activeWindows.map(x=>'<span style="border:1px solid #a8753c;border-radius:5px;padding:4px 6px;color:#ffd096;font-size:11px">'+esc(x.time.slice(5,16).replace('T',' ')+'Z')+' · '+esc(x.convective_models.join('+').toUpperCase())+' · '+Number(x.local_reflectivity_dbz).toFixed(0)+' dBZ</span>').join('')+'</div>':'';
   // Four-model calculation output for downstream integration and verification.
   // Require >=2 independent sources to avoid a single model masquerading as consensus.
   window.cuModelEnsembleOutageForecast=convectiveWindows.filter(x=>x.model_count>=2).map(x=>({
     time:x.time,gust_mph:x.median_gust_mph,feeders:x.estimated_feeders,
     stage:x.stage,model_count:x.model_count,models:x.models,
     convective_screen:x.convective_screen,source:'four-model ensemble'
   }));
   // Explicit readiness contract for a future operational-engine handoff.
   // Do not silently replace the existing engine when only one model is available.
   const ensembleRows=window.cuModelEnsembleOutageForecast;
   const nowHour=Date.now();
   const nearTerm=ensembleRows.filter(r=>{const t=Date.parse(String(r.time).match(/(?:Z|[+-]\\d{2}:\\d{2})$/i)?r.time:String(r.time)+'Z');return t>=nowHour-3600000&&t<=nowHour+6*3600000;});
   const allFour=nearTerm.filter(r=>r.model_count===4);
   window.cuEnsembleOperationalReadiness={
     ready:nearTerm.length>=4&&allFour.length>=4,
     available_hours:nearTerm.length,
     four_model_hours:allFour.length,
     reason:nearTerm.length<4?'Insufficient near-term coverage':allFour.length<4?'Not all four models available across near-term forecast':'Four-model coverage ready for engine validation',
     evaluated_at:new Date().toISOString()
   };
   window.cuExperimentalOutageTimeline=convectiveWindows;
   // Feed the shared main-chart overlay. Only display: never alter engine inputs.
   window.cuParallelOverlayRows=convectiveWindows.filter(x=>x.model_count>=2).map(x=>({time:x.time,feeders:x.estimated_feeders,models:x.model_count}));
   if(typeof window.drawForecast==='function'&&window.cuChartMode==='live')window.drawForecast();
   else showRRFSBar();

   // Parallel integration in the MAIN forecast panel, not the production engine.
   const mainChart=document.querySelector('.forecast-chart');
   if(mainChart){
     let parallel=document.getElementById('cu-parallel-forecast');
     if(!parallel){parallel=document.createElement('section');parallel.id='cu-parallel-forecast';parallel.setAttribute('aria-label','Parallel four-model outage forecast');parallel.style.cssText='margin:10px 12px;padding:12px;border:1px solid #ad8650;border-radius:9px;background:#1b2d35;color:#f0f4f6;font:12px system-ui,sans-serif';const bar=mainChart.querySelector('#chart-mode-bar');if(bar)bar.insertAdjacentElement('afterend',parallel);else mainChart.prepend(parallel);}
     const valid=convectiveWindows.filter(x=>x.model_count>=2);
     const peak=valid.length?valid.reduce((a,b)=>b.estimated_feeders>a.estimated_feeders?b:a):null;
     const conv=convectiveWindows.filter(x=>x.convective_models.length);
     const agreement=peak?peak.model_count:0;
     const confidence=agreement>=4?'4 models':agreement===3?'3 models':agreement===2?'2 models':'Insufficient';
     const preview=valid.map(x=>({time:Date.parse(String(x.time).match(/(?:Z|[+-]\\d{2}:\\d{2})$/i)?x.time:String(x.time)+'Z'),value:x.estimated_feeders,color:'#ffb86b'}));
     const bands=shadeBands;
     const stageName=n=>'Stage '+n;
     const ensemblePeak=window.cuModelEnsembleOutageForecast?.reduce((a,b)=>!a||b.feeders>a.feeders?b:a,null);
     const stageSummary=ensemblePeak?'<div role="status" style="padding:9px 0;font-weight:700">Four-model wind outlook: '+stageName(ensemblePeak.stage)+' · '+ensemblePeak.feeders.toFixed(1)+' feeders · '+ensemblePeak.model_count+'/4 models · '+esc(ensemblePeak.time.slice(5,16).replace('T',' ')+'Z')+'</div>':'';
     parallel.innerHTML='<div style="font-weight:700;font-size:14px">Four-model parallel forecast <span style="font-size:11px;color:#ffcf8c">(EXPERIMENTAL · not operational)</span></div>'+stageSummary+'<div style="margin:5px 0;color:#c3d4dc">NOAA HRRR/RRFS + Open-Meteo coverage supplementation; GFS/NAM from Open-Meteo. Original calculated forecast and response stages are unchanged.</div>'+(peak?'<div style="margin:6px 0"><b>Peak wind-only estimate:</b> '+peak.estimated_feeders.toFixed(1)+' feeders · '+esc(peak.time.slice(5,16).replace('T',' ')+'Z')+' · '+confidence+' available at peak</div>':'<div>Insufficient multi-model coverage for feeder estimate</div>')+chart([preview],10,bands)+'<div style="color:#f7be75">■ Shaded: local ≥35 dBZ convection · '+shadeHours.length+' reflectivity hours; '+conv.filter(x=>x.convective_models.length>=2).length+' with multi-model support</div><div style="color:#b9cbd4;margin-top:5px">No convective feeder increment. Forecast is shown alongside the main model for validation, not substituted into the operational prediction.</div>';
   }

   // Publish RRFS's own independently calculated feeder estimate for the shared chart.
   // This is a separate experimental series, not a silent change to operational alerts.
   const rrfsFeederCurve=(series[1]||[]).map(p=>{
     const mph=Math.max(0,Number(p.value)||0);
     const feeders=mph<30?0:mph<40?(mph-30)*0.5:mph<55?5+(mph-40)*2/3:mph<60?15+(mph-55):Math.min(170,20+(mph-60)*2);
     return {time:new Date(p.time).toISOString(),feeders:Math.max(0,feeders),model:'rrfs'};
   }).filter(p=>Number.isFinite(p.feeders));
   window.cuRRFSFeederCurve=rrfsFeederCurve;
   const consensusSeries=consensus.filter(x=>x.model_count>=2).map(x=>({time:Date.parse(String(x.time).match(/(?:Z|[+-]\\d{2}:\\d{2})$/i)?x.time:String(x.time)+'Z'),value:x.estimated_feeders,color:'#ffb86b'}));
   const convectiveBands=activeWindows.map(x=>({start:Date.parse(String(x.time).match(/(?:Z|[+-]\\d{2}:\\d{2})$/i)?x.time:String(x.time)+'Z')-30*60000,end:Date.parse(String(x.time).match(/(?:Z|[+-]\\d{2}:\\d{2})$/i)?x.time:String(x.time)+'Z')+30*60000}));
   const consensusPanel='<div style="margin-top:14px"><strong>Experimental feeder-outage timeline</strong><div style="font-size:12px;color:#c0d0d9">Selected NOAA/Open-Meteo gust sources; median of available models at each UTC hour. Feeder estimate uses preliminary user-calibrated nonconvective wind points (40 mph ≈ 5, 55 mph ≈ 15, 60 mph ≈ 20). No convective adjustment or operational alerting. Not connected to production predictions.</div>'+chart([consensusSeries],10,convectiveBands)+'<div style="color:#ffbd74;font-size:12px">■ Shaded orange: local ≥35 dBZ convective screening (not additional feeder outages)</div>'+convectivePanel+convectiveMarkers+'<div style="font-size:12px;color:#c0d0d9">Hours with fewer than 2 models are omitted. Forecast horizons differ; confidence decreases as model count falls.</div></div>';
   const feederSignal=mph=>{const x=Math.max(0,(mph-15)/5);return Math.max(0,0.2431*(Math.exp(0.5216*x)-1));};
   const near=Date.now()-3600000;
   const rows=names.map((name,i)=>{
     const future=series[i].filter(p=>p.time>=near);
     if(!future.length)return '<tr><td>'+name.toUpperCase()+'</td><td colspan="3">Unavailable</td></tr>';
     const peak=future.reduce((a,b)=>b.value>a.value?b:a);
     const tier=peak.value>=60?'Extreme':peak.value>=50?'Likely':peak.value>=40?'Possible Elevated':peak.value>=30?'Possible':'Below threshold';
     const end=series[i][series[i].length-1]?.time;
     const coverageNote=(name==='hrrr'||name==='rrfs')&&end<near+48*3600000?' <span style="color:#f2c76e">(limited horizon)</span>':'';
     return '<tr><td>'+name.toUpperCase()+coverageNote+'</td><td>'+peak.value.toFixed(1)+' mph</td><td>'+tier+'</td><td>'+new Date(peak.time).toISOString().slice(5,16).replace('T',' ')+'Z</td></tr>';
   }).join('');
   const testControls='<div style="margin-top:12px"><strong>Failover simulation (comparison only)</strong><div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px"><button data-cu-test="hrrr">Test HRRR</button><button data-cu-test="rrfs">Test RRFS</button><button data-cu-test="off">End test</button></div><small>Simulation: '+(simulated||'off')+'. Does not alter NOAA ingestion.</small></div>';
   const anyFailover=names.some(name=>sourceState[name].label==='OPEN-METEO FAILOVER');
   const failoverBanner=anyFailover?'<div role="status" style="margin-top:12px;padding:9px;border:1px solid #e8b75a;border-radius:7px;color:#ffdf99;font-weight:700">⚠ OPEN-METEO FAILOVER ACTIVE'+(simulated?' — SIMULATION ONLY':'')+'</div>':'';
   const sourceTable='<div style="margin-top:12px"><strong>Forecast data source</strong><div style="font-size:12px;color:#b7c8d2">Source selection and fallback status for this comparison (not yet the main outage engine).</div>'+names.map(name=>{const st=sourceState[name];const color=st.label==='NOAA DIRECT'?'#72d6a5':st.label==='UNAVAILABLE'?'#f5a06a':'#f2c76e';return '<div style="display:flex;justify-content:space-between;gap:8px;margin-top:5px;font-size:12px"><strong>'+name.toUpperCase()+'</strong><span style="color:'+color+'">'+st.label+'</span></div><div style="font-size:11px;color:#b7c8d2">'+st.reason+'</div>';}).join('')+'</div>';
   const riskTable='<div style="margin-top:14px"><strong>Four-model wind threat screening</strong><div style="font-size:12px;color:#b7c8d2">Peak gust within each model’s available horizon; peaks are not directly comparable when forecast periods differ. Wind-only screening, not a calibrated feeder-outage forecast. Convective reflectivity risk is evaluated separately.</div><div style="overflow-x:auto;margin-top:8px"><table style="width:100%;border-collapse:collapse;font-size:12px;text-align:left"><thead><tr><th>Model</th><th>Peak gust</th><th>Threat</th><th>Peak UTC</th></tr></thead><tbody>'+rows+'</tbody></table></div></div>';
   const chartEl=document.getElementById('cu-decoded-gust-chart');
   const availability=liveModels.map(([name])=>name.toUpperCase()+': '+coverage[name].hours+' hours ('+coverage[name].source+')').join(' · ');
   if(chartEl){chartEl.innerHTML='<strong>Decoded NOAA gust comparison (mph)</strong><div style="font-size:12px;color:#c0d0d9">Independent model comparison · not yet integrated into outage prediction graph</div><div style="font-size:12px;margin:8px 0"><span style="color:#4db8ff">● HRRR</span> &nbsp; <span style="color:#f5b95e">● RRFS</span> &nbsp; <span style="color:#8de58a">● GFS</span> &nbsp; <span style="color:#da9bff">● NAM</span> · maximum across 12 sampling sites</div>'+chart(series)+riskTable+failoverBanner+(names.some(n=>sourceState[n].label==='NOAA + OPEN-METEO')?'<div style="color:#f2c76e;font-size:12px;margin-top:8px">⚠ Partial NOAA cycle: later forecast hours supplemented from Open-Meteo, not NOAA.</div>':'')+sourceTable+testControls+consensusPanel+'<div style="font-size:12px;color:#c0d0d9;margin-top:4px">GFS/NAM forecast availability: '+availability+'. Unavailable models are omitted, not estimated. This comparison does not change outage predictions.</div>';}
   if(chartEl)chartEl.querySelectorAll('[data-cu-test]').forEach(btn=>btn.addEventListener('click',()=>{testModel=btn.dataset.cuTest;refresh();}));
  }catch(e){el.textContent='⚠ NOAA model health unavailable: '+e.message;}
 }
 // Draw parallel estimates on the SAME operational canvas, using its exact time
 // cursor and piecewise feeder scale. Does not alter the operational curves.
 function showRRFSBar(){
  const canvas=document.getElementById('live-forecast-chart'),c=canvas?.__cuTimeCursor;
  if(!canvas||!c?.times?.length)return;
  let bar=document.getElementById('cu-rrfs-timeline');
  if(!bar){bar=document.createElement('div');bar.id='cu-rrfs-timeline';canvas.closest('.cu-chart-scroll')?.insertAdjacentElement('afterend',bar);}
  const points=window.cuFourModelForecast?.rrfs?.points||[];
  const first=Date.parse(c.times[0]+'Z'),last=Date.parse(c.times[c.times.length-1]+'Z');
  const rows=points.filter(p=>Number.isFinite(Number(p.gust_mph))&&Date.parse(p.time)>=first&&Date.parse(p.time)<=last);
  const cycle=window.cuRRFSRunLabel||'?';
  bar.style.cssText='margin:3px 8px 10px;display:flex;align-items:center;gap:8px;color:#d5e3ea;font:11px Segoe UI,Arial,sans-serif';
  let svg='<svg viewBox="0 0 900 20" preserveAspectRatio="none" style="width:100%;height:20px;display:block;background:#233742;border:1px solid #536470" aria-label="RRFS forecast wind threat strip">';
  for(const p of rows){const t=Date.parse(p.time),x=(t-first)/Math.max(1,last-first)*900,w=Math.max(2,3600000/Math.max(1,last-first)*900),v=Number(p.gust_mph);
   const color=v>=60?'#e34462':v>=50?'#ed8550':v>=40?'#e7b54c':v>=30?'#e9d77d':'#3d6476';
   svg+='<rect x="'+x.toFixed(2)+'" y="0" width="'+w.toFixed(2)+'" height="20" fill="'+color+'"><title>'+new Date(t).toISOString().slice(0,16)+'Z: '+v.toFixed(1)+' mph</title></rect>';
  }
  svg+='</svg>';
  bar.innerHTML='<strong style="white-space:nowrap;min-width:105px">RRFS '+esc(cycle)+'</strong><div style="flex:1;min-width:0">'+svg+'</div><span style="white-space:nowrap">'+rows.length+' h</span>';
 }
 function overlayParallel(){
  const canvas=document.getElementById('live-forecast-chart');
  showRRFSBar();
  const c=canvas?.__cuTimeCursor,rows=window.cuParallelOverlayRows||[];
  const rrfs=window.cuRRFSFeederCurve||[];
  if(!canvas||!c||(!rows.length&&!rrfs.length)||window.cuChartMode!=='live')return;
  const ctx=canvas.getContext('2d'),dpr=Math.max(1,window.devicePixelRatio||1);
  const W=c.logicalWidth,H=675,L=108,R=87,T=76,B=259,PH=H-T-B;
  const y=v=>{v=Math.max(0,Math.min(80,v));return T+PH-((v<=10?2*v:20+(v-10))/90)*PH};
  const first=Date.parse(c.times[0]+'Z'),last=Date.parse(c.times[c.times.length-1]+'Z');
  const x=t=>L+(t-first)/Math.max(1,last-first)*(W-L-R);
  const points=rows.map(r=>({t:Date.parse(String(r.time).match(/(?:Z|[+-]\\d{2}:\\d{2})$/i)?r.time:String(r.time)+'Z'),v:Number(r.feeders)})).filter(r=>Number.isFinite(r.t)&&Number.isFinite(r.v)&&r.t>=first&&r.t<=last).sort((a,b)=>a.t-b.t);
  if(points.length>=2){
  ctx.save();ctx.setTransform(dpr,0,0,dpr,0,0);ctx.beginPath();ctx.rect(L,T,W-L-R,PH);ctx.clip();
  ctx.strokeStyle='#ffb86b';ctx.lineWidth=3;ctx.setLineDash([9,5]);ctx.beginPath();
  points.forEach((p,i)=>{if(i)ctx.lineTo(x(p.t),y(p.v));else ctx.moveTo(x(p.t),y(p.v));});ctx.stroke();ctx.restore();
  }
  // Overlay each source's wind-only feeder estimate on the SAME time and feeder axes.
  // These are comparison traces; the existing operational response logic is unchanged.
  const modelColors={hrrr:'#4db8ff',rrfs:'#e7c36c',gfs:'#8de58a',nam:'#da9bff'};
  const toFeeders=mph=>mph<30?0:mph<40?(mph-30)*.5:mph<55?5+(mph-40)*2/3:mph<60?15+(mph-55):Math.min(170,20+(mph-60)*2);
  Object.entries(window.cuFourModelForecast||{}).forEach(([name,model])=>{
    const data=(model.points||[]).map(p=>({t:Date.parse(p.time),v:toFeeders(Number(p.gust_mph))})).filter(p=>Number.isFinite(p.t)&&Number.isFinite(p.v)&&p.t>=first&&p.t<=last).sort((a,b)=>a.t-b.t);
    if(data.length<2||!modelColors[name])return;
    ctx.save();ctx.setTransform(dpr,0,0,dpr,0,0);ctx.beginPath();ctx.rect(L,T,W-L-R,PH);ctx.clip();
    ctx.strokeStyle=modelColors[name];ctx.lineWidth=1.6;ctx.globalAlpha=.85;ctx.setLineDash([3,4]);ctx.beginPath();
    data.forEach((p,i)=>{if(i)ctx.lineTo(x(p.t),y(p.v));else ctx.moveTo(x(p.t),y(p.v));});ctx.stroke();ctx.restore();
  });
  // Populate the existing RRFS ingredient lane on the operational canvas.
  // This is a display-only wind threat lane, not an operational feeder prediction.
  const rrfsSeries=window.cuFourModelForecast?.rrfs?.points||[];
  const laneY=535,laneHeight=14;
  const lanePoints=rrfsSeries.map(p=>({t:Date.parse(p.time),mph:Number(p.gust_mph)})).filter(p=>Number.isFinite(p.t)&&Number.isFinite(p.mph)&&p.t>=first&&p.t<=last);
  if(lanePoints.length){
    ctx.save();ctx.setTransform(dpr,0,0,dpr,0,0);
    ctx.beginPath();ctx.rect(L,laneY,W-L-R,laneHeight);ctx.clip();
    for(const p of lanePoints){
      const width=Math.max(2,3600000/Math.max(1,last-first)*(W-L-R));
      ctx.fillStyle=p.mph>=60?'#e34462':p.mph>=50?'#ed8550':p.mph>=40?'#e7b54c':p.mph>=30?'#e9d77d':'#426575';
      ctx.fillRect(x(p.t),laneY,width,laneHeight);
    }
    ctx.restore();
  }
  // RRFS's own wind-only feeder curve, using the same shared time and feeder axes.
  // Display actual run provenance; Open-Meteo NAM data does not expose a
  // verified initialization cycle, so never fabricate a NAM 00Z/12Z label.
  let provenance=document.getElementById('cu-model-run-provenance');
  if(!provenance){provenance=document.createElement('div');provenance.id='cu-model-run-provenance';canvas.closest('.cu-chart-scroll')?.insertAdjacentElement('afterend',provenance);}
  provenance.style.cssText='display:flex;flex-wrap:wrap;gap:8px 18px;padding:6px 12px;color:#e3ebef;font:12px Segoe UI,Arial,sans-serif';
  provenance.textContent='NAM: '+(window.cuNAMRunLabel==='API'?'Open-Meteo (run unverified)':window.cuNAMRunLabel+' explicit run')+' | RRFS: '+(window.cuRRFSRunLabel||'?')+' NOAA | HRRR: '+(window.cuHRRRRunLabel||'?')+' NOAA';
  // Keep run provenance visible on narrow screens, independently of canvas labels.
  provenance.style.cssText+=';max-width:100%;box-sizing:border-box;overflow-wrap:anywhere;line-height:1.5';
  let runStrip=document.getElementById('cu-model-run-strip');
  if(!runStrip){runStrip=document.createElement('div');runStrip.id='cu-model-run-strip';canvas.closest('.cu-chart-scroll')?.insertAdjacentElement('beforebegin',runStrip);}
  runStrip.style.cssText='display:flex;flex-wrap:wrap;gap:5px 12px;padding:7px 10px;max-width:100%;box-sizing:border-box;color:#e5edf2;background:#22333d;font:12px Segoe UI,Arial,sans-serif;border-radius:6px';
  runStrip.textContent='GFS: Open-Meteo (run unverified) · NAM: '+(window.cuNAMRunLabel==='API'?'Open-Meteo (run unverified)':window.cuNAMRunLabel+' explicit run')+' · HRRR: '+(window.cuHRRRRunLabel||'?')+' NOAA · RRFS: '+(window.cuRRFSRunLabel||'?')+' NOAA';
  // The model legend is displayed in the adjacent HTML panel, not on the date axis.
  let legend=document.getElementById('cu-ensemble-chart-legend');
  if(!legend){legend=document.createElement('div');legend.id='cu-ensemble-chart-legend';canvas.closest('.cu-chart-scroll')?.insertAdjacentElement('afterend',legend);}
  legend.style.cssText='display:flex;flex-wrap:wrap;gap:6px 14px;padding:8px 12px;color:#d7e3e8;font:11px Segoe UI,Arial,sans-serif';
  legend.textContent='Ensemble (orange) | HRRR (blue) | RRFS (gold) | GFS (green) | NAM (purple) - comparison only';
 }
 function installParallelOverlay(){
  if(typeof window.drawForecast!=='function'||window.drawForecast.__cuParallelWrapped)return;
  const original=window.drawForecast;
  const wrapped=function(...args){const result=original.apply(this,args);overlayParallel();return result;};
  wrapped.__cuParallelWrapped=true;window.drawForecast=wrapped;
 }
 installParallelOverlay();
 // The operational chart is often initialized asynchronously after this script.
 // Retry the hook and refresh labels even when the chart is not in live mode.
 setInterval(()=>{installParallelOverlay();showRRFSBar();},2000);
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
# Correct the ORIGINAL canvas ingredient labels (not a supplemental strip).
original = """ const rrfsCycle=window.cuRRFS95?.cc;
 const laneLabels=[
  'GFS '+noaaCycleLabel('gfs'),
  'NAM* —',
  'HRRR '+noaaCycleLabel('hrrr'),
  'RRFS '+(rrfsCycle===undefined?'—':String(rrfsCycle).padStart(2,'0')+'Z')
 ];"""
replacement = """ const verifiedCycle=(label,fallback)=>/^\\d{2}Z$/.test(label||'')?label:fallback;
 const laneLabels=[
  'GFS '+noaaCycleLabel('gfs'),
  'NAM* '+(window.cuNAMRunLabel||'API'),
  'HRRR '+verifiedCycle(window.cuHRRRRunLabel,noaaCycleLabel('hrrr')),
  'RRFS '+verifiedCycle(window.cuRRFSRunLabel,'—')
 ];"""
# Idempotent migration: existing deployments already have the first label fix.
previous = """ const verifiedCycle=(label,fallback)=>/^\\d{2}Z$/.test(label||'')?label:fallback;
 const laneLabels=[
  'GFS '+noaaCycleLabel('gfs'),
  'NAM* API',
  'HRRR '+verifiedCycle(window.cuHRRRRunLabel,noaaCycleLabel('hrrr')),
  'RRFS '+verifiedCycle(window.cuRRFSRunLabel,'—')
 ];"""
if original in html:
    html=html.replace(original,replacement,1)
elif previous in html:
    html=html.replace(previous,replacement,1)
elif replacement in html:
    pass  # Already updated; safe on every scheduled workflow run.
else:
    raise SystemExit('Operational canvas lane labels changed unexpectedly; refusing silent success')

# Keep the full-resolution canvas, but confine its horizontal overflow to the
# chart viewport instead of allowing the entire dashboard to overflow on phones.
mobile_css = """<style id="cu-mobile-chart-viewport-fix">
@media (max-width: 700px) {
  html,body {max-width:100%;overflow-x:hidden}
  .forecast-chart {min-width:0!important;max-width:100%!important;width:100%!important;box-sizing:border-box!important;overflow:hidden!important}
  .forecast-chart .cu-chart-scroll {display:block!important;width:100%!important;max-width:100%!important;min-width:0!important;overflow-x:auto!important;overflow-y:hidden!important;-webkit-overflow-scrolling:touch;overscroll-behavior-x:contain;touch-action:pan-x pan-y}
  .forecast-chart .cu-chart-scroll canvas {max-width:none!important;flex-shrink:0!important}
  #cu-model-run-strip,#cu-model-run-provenance {width:100%!important;max-width:100%!important;min-width:0!important;box-sizing:border-box!important;white-space:normal!important;overflow-wrap:anywhere!important}
  .forecast-chart .cu-chart-mobile-hint {display:block!important;white-space:normal!important}
}
</style>"""
html=re.sub(r'<style id="cu-mobile-chart-viewport-fix">.*?</style>','',html,flags=re.S)
if '</head>' not in html: raise SystemExit('Missing head for mobile viewport CSS')
html=html.replace('</head>',mobile_css+'</head>',1)

# Add numerical-model reflectivity corroboration to the existing lightning and
# QLCS screens. Do not infer lightning strikes or QLCS structure from a lone pixel.
light_anchor=" set('Lightning',lightningHit,"
if light_anchor not in html:
    raise SystemExit('Lightning screening anchor missing')
if 'cuMultiModelStormCorroborationV1' not in html:
    js=r""" const cuMultiModelStormCorroborationV1=(()=>{
   const now=Date.now()-15*60000;
   const records=(window.cuNumericalReflectivityV102||[]).filter(r=>['rrfs','gfs','hrrr','nam'].includes(r.model)&&Number.isFinite(Date.parse(String(r.time).match(/(?:Z|[+-]\\d{2}:\\d{2})$/i)?r.time:String(r.time)+'Z'))&&Date.parse(String(r.time).match(/(?:Z|[+-]\\d{2}:\\d{2})$/i)?r.time:String(r.time)+'Z')>=now);
   const groups=new Map();
   for(const r of records){
     const local=Number(r.zones?.springfield_area),west=Number(r.zones?.approach_west),upstream=Number(r.zones?.upstream_west);
     if(![local,west,upstream].some(Number.isFinite))continue;
     const t=Math.floor(Date.parse(String(r.time).match(/(?:Z|[+-]\\d{2}:\\d{2})$/i)?r.time:String(r.time)+'Z')/3600000)*3600000;
     const key=r.model+':'+t;
     groups.set(key,{model:r.model,ms:t,local,west,upstream});
   }
   const rows=[...groups.values()].sort((a,b)=>a.ms-b.ms);
   const capeSupport=ms=>profFuture.some(x=>Math.abs(x.ms-ms)<=90*60000&&cape(x.r)>=500);
   const shearSupport=ms=>profFuture.some(x=>Math.abs(x.ms-ms)<=90*60000&&cape(x.r)>=500&&shear(x.r)>=30);
   const lightning=rows.find(x=>capeSupport(x.ms)&&x.local>=35&&[x.west,x.upstream].some(v=>Number.isFinite(v)&&v>=35));
   const qlcs=rows.find(x=>shearSupport(x.ms)&&x.local>=35&&x.west>=35&&x.upstream>=35&&rows.some(y=>y!==x&&y.model===x.model&&y.ms>x.ms&&y.ms<=x.ms+2*3600000&&y.local>=35&&y.west>=35));
   return {lightning,qlcs,available:rows.length>0,models:[...new Set(rows.map(x=>x.model))]};
 })();
 """
    html=html.replace(light_anchor,js+light_anchor,1)
    old=" set('Lightning',lightningHit,"
    html=html.replace(old," if(!lightningHit&&cuMultiModelStormCorroborationV1.lightning){const x=cuMultiModelStormCorroborationV1.lightning;lightningHit={ms:x.ms};lightningWhy=x.model.toUpperCase()+' numerical local and upstream reflectivity ≥35 dBZ with CAPE ≥500 J/kg (storm potential; not observed lightning)';}\n"+old,1)
    oldql=" set('QLCS',qlcs,'Organization-support screen: Possible when CAPE ≥500 J/kg and 0–6 km shear ≥30 kt. Reflectivity line structure is not diagnosed here, so this is environmental support rather than QLCS identification.');"
    newql=" const modelLine=cuMultiModelStormCorroborationV1.qlcs;\n set('QLCS',qlcs||(modelLine?{ms:modelLine.ms}:null),'Organization-support screen: CAPE ≥500 J/kg and 0–6 km shear ≥30 kt. '+(modelLine?'Corroborating '+modelLine.model.toUpperCase()+' local/west/upstream ≥35 dBZ over adjacent forecast hours; possible organized convection, not confirmed QLCS.':'No corroborated multi-zone persistent line detected. Environmental support alone is not proof of QLCS.'));"
    if oldql not in html:raise SystemExit('QLCS screening anchor missing')
    html=html.replace(oldql,newql,1)

# HRRR native lightning-density thresholds (flashes/km2/5 minutes).
# Missing data is WAITING, not a zero forecast. Other models corroborate convection,
# but their reflectivity is never relabeled as native HRRR flash density.
lightning_patch=r"""
<script>
window.cuHRRRLightningLevel=function(v){
 if(typeof v!=='number'||!Number.isFinite(v)||v<0)return {level:'waiting',band:null};
 const band=v<=0.1?0:v<=0.3?1:v<=1?2:v<=3?3:v<=6?4:5;
 return {level:['none','possible','possible','elevated','likely','extreme'][band],band:band+1,units:'flashes/km²/5 min'};
};
</script>
"""
if 'window.cuHRRRLightningLevel=' not in html:
    html=html.replace('</body>',lightning_patch+'</body>',1)

# Live Lightning light: use validated native density only; otherwise use corroborated
# numerical reflectivity/instability and explicitly label that as storm potential.
# This is an actual tile update, not a cosmetic indicator demo.
light_update_anchor=" set('Lightning',lightningHit,'V85 corroborated operational lightning screen."
if light_update_anchor in html and 'cuLightningOperationalV2' not in html:
    inject=r""" const cuLightningOperationalV2=(()=>{
   const now=Date.now()-15*60000;
   const sources=[['hrrr','hrrr_lightning.json'],['rrfs','rrfs_lightning.json']];
   const candidates=(window.cuLightningDensityForecasts||[]).filter(x=>x&&x.units_verified===true&&x.units==='flashes/km²/5 min'&&Number.isFinite(x.value)&&Number.isFinite(Date.parse(String(x.time).match(/(?:Z|[+-]\\d{2}:\\d{2})$/i)?x.time:String(x.time)+'Z'))&&Date.parse(String(x.time).match(/(?:Z|[+-]\\d{2}:\\d{2})$/i)?x.time:String(x.time)+'Z')>=now);
   const best=candidates.sort((a,b)=>b.value-a.value)[0];
   const level=best?window.cuHRRRLightningLevel?.(best.value):null;
   return {best,level};
 })();
 if(cuLightningOperationalV2.best&&cuLightningOperationalV2.level){
   const x=cuLightningOperationalV2.best;
   threat('Lightning',cuLightningOperationalV2.level.level,
     x.model.toUpperCase()+' verified native lightning flash density '+x.value+' flashes/km²/5 min, band '+cuLightningOperationalV2.level.band+'.',
     cuPhaseForTime(Date.parse(String(x.time).match(/(?:Z|[+-]\\d{2}:\\d{2})$/i)?x.time:String(x.time)+'Z')));
 }else{
   const raw=(window.cuLightningRawSignals||[]).filter(x=>x&&Number.isFinite(x.value)&&Date.parse(String(x.time).match(/(?:Z|[+-]\\d{2}:\\d{2})$/i)?x.time:String(x.time)+'Z')>=Date.now()-15*60000);
   const signal=raw.sort((a,b)=>b.value-a.value)[0];
   // HRRR dimensionless LTNG is a qualitative signal, NOT a flash count.
   // A positive raw signal only supports Possible pending calibration.
   const rawHit=signal&&signal.value>0;
   threat('Lightning',lightningHit||rawHit?'possible':'waiting',
     (lightningHit?'Corroborated thunderstorm potential: '+lightningWhy+'. ':'')+
     (rawHit?'HRRR uncalibrated lightning guidance '+signal.value+' (dimensionless; Possible screening only). ':'')+
     'Native HRRR/RRFS lightning flash density is not yet verified. '+
     'No verified native lightning signal; do not interpret missing density as zero.',
     lightningHit?cuPhaseForTime(lightningHit.ms):rawHit?cuPhaseForTime(Date.parse(signal.time)):{phase:'unknown',label:'AWAITING VERIFIED LIGHTNING DATA'});
 }
 """
    # Replace existing Lightning set call by adding a final overriding tile update
    # immediately before the Extreme heat tile.
    target=" set('Extreme heat',first(rows"
    if target not in html:raise SystemExit('Extreme heat anchor missing')
    html=html.replace(target,inject+target,1)

# Fetch published lightning data into the existing live threat-light controller.
# A partial newer cycle cannot turn missing hours into zero-valued forecasts.
light_fetch_patch=r"""
<script>
window.cuLightningDensityForecasts=[];
window.cuLightningRawSignals=[];
window.cuLightningDensityUnverified=false;
window.cuLightningProvisionalForecasts=[];
// Bind the asynchronous feed to the existing threat controller.  The controller
// may be defined later than this script, so refresh again after page load.
document.addEventListener('cu-lightning-data-ready',()=>{
  const run=window.cuUpdateThreats;
  if(typeof run==='function')run();
});
window.addEventListener('load',()=>{
  if(window.cuLightningDensityForecasts?.length && typeof window.cuUpdateThreats==='function')window.cuUpdateThreats();
});
(async()=>{
 const density=[],raw=[];
 for(const [model,file] of [['hrrr','hrrr_lightning.json'],['hrrr','hrrr_lightning_extended.json'],['rrfs','rrfs_lightning.json']]){
  try{
   const response=await fetch(file+'?t='+Date.now(),{cache:'no-store'});
   if(!response.ok)continue;
   const data=await response.json();
   if(!Array.isArray(data.hours))continue;
   if(model==='rrfs' && (data.diagnostic_errors||[]).some(e=>/implausible converted density/i.test(e)))window.cuLightningDensityUnverified=true;
   for(const h of data.hours){
    const t=Date.parse(h.time);if(!Number.isFinite(t))continue;
    const source_cycle=h.source_cycle||data.cycle;
    if(model==='rrfs'&&h.native_index===true&&Number.isFinite(h.value)&&h.value>=0&&h.value<=15){
      window.cuLightningProvisionalForecasts.push({model,time:h.time,value:h.value,source_cycle});
    }
    if(model==='rrfs'&&h.units_verified===true&&Number.isFinite(h.value)){
      density.push({model,time:h.time,value:h.value,units:'flashes/km²/5 min',units_verified:true,source_cycle,metric:h.metric||'density_rate'});
    }else if(model==='hrrr'&&Number.isFinite(h.peak_raw)){
      raw.push({model,time:h.time,value:h.peak_raw,source_cycle,metric:'dimensionless_lightning_guidance',units_verified:false});
    }
   }
  }catch(e){console.warn('Lightning data load',model,e)}
 }
 const dedup=(a)=>[...new Map(a.sort((x,y)=>Date.parse(x.source_cycle)-Date.parse(y.source_cycle)).map(x=>[x.model+'|'+x.time,x])).values()];
 window.cuLightningDensityForecasts=dedup(density);
 window.cuLightningRawSignals=dedup(raw);
 try{window.cuUpdateThreats?.();document.dispatchEvent(new CustomEvent('cu-lightning-data-ready',{detail:{density:density.length,raw:raw.length}}));}catch(e){console.warn('Lightning threat refresh',e)}
})();
</script>
"""
if 'window.cuLightningDensityForecasts=[]' not in html:
    html=html.replace('</body>',light_fetch_patch+'</body>',1)

# Normalize the entire previously generated lightning-level script. Earlier builds
# emitted literal backslash-n sequences; idempotent insertion kept them forever.
# Repair all old versions of the lightning-level script by locating its
# function declaration, regardless of how the opening script tag was spaced.
legacy_function=html.find('window.cuHRRRLightningLevel=function(v)')
if legacy_function>=0:
    legacy_start=html.rfind('<script',0,legacy_function)
    legacy_end=html.find('</script>',legacy_function)
    if legacy_start<0 or legacy_end<0: raise SystemExit('Lightning script boundaries missing')
    legacy=html[legacy_start:legacy_end+len('</script>')]
    if chr(92)+'n' in legacy:
        html=html[:legacy_start]+legacy.replace(chr(92)+'n',chr(10))+html[legacy_end+len('</script>'):]

# Repair the legacy async lightning loader, too. Older HTML contains a
# distinct literal-backslash-n script, separate from the lightning-level script.
loader_function=html.find('window.cuLightningDensityForecasts=[]')
if loader_function>=0:
    loader_start=html.rfind('<script',0,loader_function)
    loader_end=html.find('</script>',loader_function)
    if loader_start<0 or loader_end<0: raise SystemExit('Lightning loader boundaries missing')
    legacy=html[loader_start:loader_end+len('</script>')]
    if chr(92)+'n' in legacy:
        html=html[:loader_start]+legacy.replace(chr(92)+'n',chr(10))+html[loader_end+len('</script>'):]

# Older generated dashboards may contain more than one legacy escaped script.
# Normalize only the two known Lightning script bodies, not unrelated JS strings.
for signature in ('window.cuHRRRLightningLevel=function(v)', 'window.cuLightningDensityForecasts=[]'):
    position=html.find(signature)
    if position<0:continue
    begin=html.rfind('<script',0,position)
    finish=html.find('</script>',position)
    if begin<0 or finish<0:raise SystemExit('Lightning script missing boundaries: '+signature)
    body=html[begin:finish+9]
    if body.lstrip().startswith('<script>') and body.count(chr(92)+'n')>=2:
        html=html[:begin]+body.replace(chr(92)+'n',chr(10))+html[finish+9:]

# Fix invalid backslash-n sequences already embedded in older generated HTML.
# Match a literal backslash followed by n, not a real line break.
html=html.replace("+" + chr(92) + "n     (rawHit?", "+" + chr(10) + "     (rawHit?")

# Remove stale injected V85 override and install one syntactically checked,
# self-contained override that can refresh after asynchronous data arrival.
start=html.find(' const cuLightningOperationalV2=(()=>{')
end=html.find(" set('Extreme heat',first(rows",start) if start>=0 else -1
if start>=0 and end>start:
    html=html[:start]+html[end:]
# Make the existing V85 render function available to the async lightning feed.
# The enclosing controller is executed again on each data-ready notification.

# Dedicated UI bridge for the existing V85 Lightning tile. The older V85
# updateGlobal function can throw, so do not rely on it for asynchronous updates.
lightning_ui_bridge=r"""
<script id="cu-lightning-visible-bridge">
(()=>{
 const labels={none:'BELOW THRESHOLD',possible:'POSSIBLE',elevated:'ELEVATED',likely:'LIKELY',extreme:'EXTREME'};
 let directRRFS=[];
 async function loadRRFS(){
  try{
   const response=await fetch('rrfs_lightning.json?t='+Date.now(),{cache:'no-store'});
   if(!response.ok)return;
   const data=await response.json();
   if(!Array.isArray(data.hours))return;
   directRRFS=data.hours.filter(h=>h.native_index===true&&Number.isFinite(h.value)&&h.value>=0&&h.value<=15).map(h=>({model:'rrfs',time:h.time,value:h.value,source_cycle:h.source_cycle||data.cycle}));
   window.cuLightningProvisionalForecasts=directRRFS;
   refresh();
  }catch(e){console.warn('RRFS lightning tile fetch',e)}
 }
 function refresh(){
  const now=Date.now()-15*60000;
  const valid=(window.cuLightningDensityForecasts||[]).filter(x=>x?.units_verified===true&&Number.isFinite(x.value)&&Number.isFinite(Date.parse(String(x.time).match(/(?:Z|[+-]\\d{2}:\\d{2})$/i)?x.time:String(x.time)+'Z'))&&Date.parse(String(x.time).match(/(?:Z|[+-]\\d{2}:\\d{2})$/i)?x.time:String(x.time)+'Z')>=now);
  const provisional=[...(window.cuLightningProvisionalForecasts||[]),...directRRFS].filter(x=>Number.isFinite(x.value)&&Number.isFinite(Date.parse(String(x.time).match(/(?:Z|[+-]\\d{2}:\\d{2})$/i)?x.time:String(x.time)+'Z'))&&Date.parse(String(x.time).match(/(?:Z|[+-]\\d{2}:\\d{2})$/i)?x.time:String(x.time)+'Z')>=now);
  if(!valid.length&&!provisional.length)return;
  const positive=[...valid,...provisional].filter(x=>x.value>0).sort((a,b)=>Date.parse(a.time)-Date.parse(b.time));
  const onset=positive.length?Date.parse(positive[0].time):null;
  const strongest=valid.length?valid.reduce((a,b)=>a.value>=b.value?a:b):null;
  const classification=strongest?window.cuHRRRLightningLevel?.(strongest.value):null;
  const provisionalPositive=provisional.some(x=>x.value>0);
  const uncertain=(!classification||classification.level==='none')&&(window.cuLightningDensityUnverified===true||provisionalPositive);
  const provisionalAlert=uncertain&&provisionalPositive;
  const level=provisionalAlert?'possible':uncertain?'waiting':classification?.level;
  const label=provisionalAlert?'POSSIBLE':uncertain?'WAITING':labels[classification?.level];
  if(!label)return;
  // A future lightning forecast must not look like an ongoing observation.
  const future=onset!==null&&onset>Date.now()+15*60000;
  const clock=onset===null?'':new Intl.DateTimeFormat('en-US',{timeZone:'America/Chicago',hour:'numeric',minute:'2-digit',hour12:true}).format(new Date(onset)).replace(':00','');
  const displayLabel=future?label+' · '+clock:label;
  const heading=document.querySelector('[data-threat-key="Lightning"]');
  const tile=heading?.closest('.threat-row');
  const status=tile?.querySelector('.threat-time');
  const dot=tile?.querySelector('.threat-dot');
  if(!status)return;
  status.textContent=displayLabel;
  status.dataset.cuLightningLevel=level;
  status.dataset.status=level;
  status.dataset.phase=future?'upcoming':'forecast';
  status.title=provisionalAlert?'RRFS provisional lightning signal '+provisionalPeak.value+' (scale not calibrated; intensity tier withheld)':uncertain?'RRFS lightning units unverified':strongest.model.toUpperCase()+' verified lightning density '+strongest.value+' flashes/km²/5 min';
  if(dot)dot.dataset.status=level;
  const colors={none:'#8fa4b2',possible:'#e8c35b',elevated:'#ff9b43',likely:'#ff634f',extreme:'#ed437e'};
  status.style.color=uncertain&&!provisionalAlert?'#4db8ff':colors[level];
  if(dot)dot.style.backgroundColor=uncertain&&!provisionalAlert?'#4db8ff':colors[level];
 }
 loadRRFS();setInterval(loadRRFS,60000);
 document.addEventListener('cu-lightning-data-ready',()=>{refresh();setTimeout(refresh,400)});
 window.addEventListener('load',refresh);
 // Legacy V85 recalculations can overwrite the display after data arrives.
 // Keep the verified lightning density status synchronized without changing other threats.
 setInterval(refresh,500);
 window.cuRefreshLightningTile=refresh;
})();
</script>
"""
html=re.sub(r'<script id="cu-lightning-visible-bridge">.*?</script>','',html,flags=re.S)
if '</body>' in html:
    html=html.replace('</body>',lightning_ui_bridge+'</body>',1)
else:
    html+=lightning_ui_bridge

# Forecast timing bridge: separate future convective risk from ongoing events.
# Uses the published CU-point RRFS reflectivity, not a fixed event date.
timing_bridge=r"""
<script id="cu-convective-onset-bridge">
(()=>{
 let hours=[];
 async function load(){
  try{
   const r=await fetch('./rrfs_reflectivity.json?t='+Date.now(),{cache:'no-store'});
   if(!r.ok)return;
   const d=await r.json();
   hours=(d.hours||[]).filter(x=>Number.isFinite(Number(x.dbz))&&Number(x.dbz)>=30&&Number.isFinite(Date.parse(x.time+'Z')))
      .map(x=>({t:Date.parse(x.time+'Z'),dbz:Number(x.dbz)})).sort((a,b)=>a.t-b.t);
   update();
  }catch(e){console.warn('Convective timing feed unavailable',e)}
 }
 function update(){
  const now=Date.now();
  const next=hours.find(x=>x.t>=now-30*60000);
  if(!next)return;
  const future=next.t>now+30*60000;
  if(!future)return; // Do not suppress a genuinely ongoing event.
  const clock=new Intl.DateTimeFormat('en-US',{timeZone:'America/Chicago',hour:'numeric',minute:'2-digit',hour12:true}).format(new Date(next.t)).replace(':00','');
  const heading=document.querySelector('[data-threat-key="Downburst"]');
  const tile=heading?.closest('.threat-row');
  const status=tile?.querySelector('.threat-time');
  const dot=tile?.querySelector('.threat-dot');
  if(!status)return;
  // Reflectivity supports a possible future convective window, not a confirmed downburst.
  status.textContent='POSSIBLE · '+clock;
  status.dataset.phase='upcoming';
  status.dataset.status='possible';
  status.title='Future RRFS convective reflectivity signal; downburst potential is not a confirmed event';
  status.style.color='#e8c35b';
  if(dot){dot.dataset.status='possible';dot.style.backgroundColor='#e8c35b'}
 }
 load();setInterval(load,60000);setInterval(update,1500);
})();
</script>
"""
html=re.sub(r'<script id="cu-convective-onset-bridge">.*?</script>','',html,flags=re.S)
html=html.replace('</body>',timing_bridge+'</body>',1) if '</body>' in html else html+timing_bridge

# Keep the main forecast chart's local timeline readable without changing its
# outage calculations. Add a synchronized RRFS storm window strip.
main_timeline=r"""
<style id="cu-main-timeline-style">
#cu-rrfs-storm-window{margin:8px 0 12px;padding:9px 12px;border:1px solid #4e6675;border-radius:7px;background:#142430;color:#e5edf2;font:12px system-ui,sans-serif}
#cu-rrfs-storm-window .cu-hours{display:flex;gap:2px;min-height:17px;margin-top:6px}
#cu-rrfs-storm-window .cu-hour{flex:1;min-width:0;border-radius:2px;background:#233643}
#cu-rrfs-storm-window .cu-hour.storm{background:#f0a13e}
#cu-rrfs-storm-window .cu-hour.strong{background:#d95b43}
</style>
<script id="cu-main-timeline-bridge">
(()=>{
 const parseUTC=s=>Date.parse(/[zZ]|[+-]\d\d:\d\d$/.test(s)?s:s+'Z');
 const local=t=>new Intl.DateTimeFormat('en-US',{timeZone:'America/Chicago',weekday:'short',hour:'numeric',hour12:true}).format(new Date(t));
 async function render(){
  try{
   const r=await fetch('./rrfs_reflectivity.json?t='+Date.now(),{cache:'no-store'});
   if(!r.ok)return;
   const d=await r.json();
   const rows=(d.hours||[]).map(h=>({t:parseUTC(h.time),dbz:Array.isArray(h.site_dbz)&&h.site_dbz.some(Number.isFinite)?Math.max(...h.site_dbz.filter(Number.isFinite)):Number(h.dbz)})).filter(h=>Number.isFinite(h.t)&&Number.isFinite(h.dbz)&&h.t>=Date.now()-3600000).sort((a,b)=>a.t-b.t).slice(0,48);
   if(!rows.length)return;
   let el=document.getElementById('cu-rrfs-storm-window');
   if(!el){el=document.createElement('section');el.id='cu-rrfs-storm-window';const chart=document.querySelector('canvas');(chart?.parentElement||document.body).insertAdjacentElement('afterend',el)}
   const active=rows.filter(h=>h.dbz>=30);
   const first=active[0],last=active[active.length-1];
   el.innerHTML='<strong>RRFS local convective window (Central time)</strong> — '+(first?local(first.t)+' to '+local(last.t):'below 30 dBZ')+'<div class="cu-hours">'+rows.map(h=>'<span class="cu-hour '+(h.dbz>=50?'strong':h.dbz>=30?'storm':'')+'" title="'+local(h.t)+' · '+h.dbz.toFixed(1)+' dBZ"></span>').join('')+'</div><div style="display:flex;justify-content:space-between;margin-top:4px"><span>'+local(rows[0].t)+'</span><span>'+local(rows[rows.length-1].t)+'</span></div>';
  }catch(e){console.warn('RRFS chart strip unavailable',e)}
 }
 window.addEventListener('load',render);setInterval(render,60000);
})();
</script>
"""
html=re.sub(r'<style id="cu-main-timeline-style">.*?</style>','',html,flags=re.S)
html=re.sub(r'<script id="cu-main-timeline-bridge">.*?</script>','',html,flags=re.S)
html=html.replace('</body>',main_timeline+'</body>',1) if '</body>' in html else html+main_timeline



# Repair the existing lightning indicator: RRFS provisional flashes are not
# verified physical density, so show POSSIBLE only, never a calibrated tier.
# The previous code referenced an undefined provisionalPeak and parsed naive
# UTC forecast timestamps as local time.
html=html.replace("const now=Date.now()-15*60000;\\n  const valid=", "const now=Date.now()-15*60000;\\n  const valid=")
html=html.replace("Date.parse(x.time)", "Date.parse(String(x.time).match(/(?:Z|[+-]\\\\d{2}:\\\\d{2})$/i)?x.time:String(x.time)+'Z')")
html=html.replace("Date.parse(a.time)", "Date.parse(String(a.time).match(/(?:Z|[+-]\\\\d{2}:\\\\d{2})$/i)?a.time:String(a.time)+'Z')")
html=html.replace("Date.parse(b.time)", "Date.parse(String(b.time).match(/(?:Z|[+-]\\\\d{2}:\\\\d{2})$/i)?b.time:String(b.time)+'Z')")
html=html.replace("provisionalPeak.value", "(provisional.find(x=>x.value>0)?.value??'unknown')")

# The operational chart is an actionable 72-hour window, not a seven-day
# view that compresses Tuesday's event into the first 15% of its width.
html=html.replace('Array.from({length:169},(_,i)=>new Date(startUTC+i*3600000)', 'Array.from({length:73},(_,i)=>new Date(startUTC+i*3600000)')
# A few older published versions use the same generated axis with a 169-hour
# horizon; preserve the same time coordinates and missing-data gaps.



# The original chart's HRRR coverage marker used Date.parse() on naive UTC
# labels, causing a local-time shift and false "NO HRRR" regions.
html=html.replace("times.findIndex(t=>Date.parse(t)>last)", "times.findIndex(t=>Date.parse(t.endsWith('Z')?t:t+'Z')>last)")
# Preserve the original display's operational forecast window; do not
# interpret a missing HRRR reflectivity hour as a zero forecast.


# Normalize source timestamps at the original main chart boundary, rather than
# assuming every API delivers an identical minute/UTC suffix. This keeps
# valid hourly model values from disappearing due to exact-string mismatch.
start=html.find('function drawForecast(){')
end=html.find('const viewportWidth=',start)
if start>=0 and end>start:
    chunk=html[start:end]
    needle=" const now=Date.now()-3600000;"
    normalizer=""" const hourUTC=v=>{
  const raw=String(v??'').trim();
  if(!raw)return '';
  const iso=/[zZ]$|[+-]\\d\\d:?\\d\\d$/.test(raw)?raw:raw+'Z';
  const ms=Date.parse(iso);
  return Number.isFinite(ms)?new Date(ms).toISOString().slice(0,13)+':00':'';
 };
 for(const rows of [g,n,h,rrfs]){
  for(const r of rows){const t=hourUTC(r.time);if(t)r.time=t;}
 }
"""
    if needle in chunk and 'const hourUTC=v=>' not in chunk:
        chunk=chunk.replace(needle,normalizer+needle,1)
    html=html[:start]+chunk+html[end:]


# V126: Feed native RRFS site reflectivity into the EXISTING main chart lane.
# This does not add outage feeders or claim that dBZ predicts damaging winds.
rrfs_lane=r"""
<script id="cu-rrfs-main-lane-sync">
(()=>{
 const utc=s=>{const v=String(s||'');return Date.parse(/[zZ]$|[+-]\d\d:\d\d$/.test(v)?v:v+'Z')};
 async function sync(){
  try{
   const response=await fetch('./rrfs_reflectivity.json?t='+Date.now(),{cache:'no-store'});
   if(!response.ok)return;
   const data=await response.json();
   if(!Array.isArray(data.hours))return;
   const rows=data.hours.map(h=>{
    const sites=Array.isArray(h.site_dbz)?h.site_dbz.map(Number).filter(Number.isFinite):[];
    const ms=utc(h.time);
    if(!Number.isFinite(ms)||!sites.length)return null;
    const local=Math.max(...sites);
    return {model:'rrfs',time:new Date(ms).toISOString().slice(0,16)+'Z',dbz:local,
     site_dbz:sites,zones:{springfield_area:local,approach_west:null,upstream_west:null,downstream_east:null},
     source_cycle:h.source_cycle||data.cycle,zone:'local'};
   }).filter(Boolean);
   if(!rows.length)return;
   const current=window.cuNumericalReflectivityV102||[];
   const old=current.filter(r=>r.model!=='rrfs');
   window.cuNumericalReflectivityV102=[...old,...rows];
   window.drawForecast?.();
  }catch(e){console.warn('RRFS main lane unavailable',e)}
 }
 window.addEventListener('load',()=>setTimeout(sync,1800));
 document.addEventListener('cu-reflectivity-updated',()=>setTimeout(sync,200));
 setInterval(sync,60000);
})();
</script>
"""
html=re.sub(r'<script id="cu-rrfs-main-lane-sync">.*?</script>','',html,flags=re.S)
html=html.replace('</body>',rrfs_lane+'</body>',1) if '</body>' in html else html+rrfs_lane

# Replace the broken legacy lightning overlay with a single authoritative
# provisional lightning signal. No verified physical density => POSSIBLE only.
lightning_bridge=r"""
<script id="cu-lightning-visible-bridge">
(()=>{
 const utc=s=>{const v=String(s||'');return Date.parse(/[zZ]$|[+-]\d\d:\d\d$/.test(v)?v:v+'Z')};
 let forecast=[],loaded=false;
 async function load(){
  try{
   const r=await fetch('./rrfs_lightning.json?t='+Date.now(),{cache:'no-store'});
   if(!r.ok)return;
   const d=await r.json();
   if(!Array.isArray(d.hours))return;
   forecast=d.hours.map(h=>({time:utc(h.time),value:Number(h.value),native:h.native_index===true}))
     .filter(h=>Number.isFinite(h.time)&&Number.isFinite(h.value)&&h.native&&h.value>=0&&h.value<=15);
   window.cuLightningProvisionalForecasts=forecast.map(h=>({model:'rrfs',time:new Date(h.time).toISOString(),value:h.value,native_index:true,units_verified:false}));
   loaded=true;refresh();
  }catch(e){console.warn('RRFS lightning forecast unavailable',e)}
 }
 function refresh(){
  const tile=document.querySelector('[data-threat-key="Lightning"]')?.closest('.threat-row');
  const status=tile?.querySelector('.threat-time'),dot=tile?.querySelector('.threat-dot');
  if(!status)return;
  const now=Date.now();
  const verified=(window.cuLightningDensityForecasts||[]).filter(h=>Number.isFinite(utc(h.time))&&utc(h.time)>=now-15*60000&&Number.isFinite(Number(h.value)));
  const provisional=forecast.filter(h=>h.time>=now-15*60000);
  const positiveVerified=verified.filter(h=>Number(h.value)>0);
  const positiveProvisional=provisional.filter(h=>h.value>0);
  if(!positiveVerified.length&&!positiveProvisional.length)return;
  const top=positiveVerified.reduce((m,h)=>Math.max(m,Number(h.value)),0);
  const classification=top>=6?'EXTREME':top>=3?'LIKELY':top>=1?'ELEVATED':'POSSIBLE';
  const onset=Math.min(...positiveVerified.map(h=>utc(h.time)),...positiveProvisional.map(h=>h.time));
  const clock=new Intl.DateTimeFormat('en-US',{timeZone:'America/Chicago',hour:'numeric',hour12:true}).format(new Date(onset));
  const upcoming=onset>now+15*60000;
  status.textContent=(positiveVerified.length?classification:'POSSIBLE')+(upcoming?' · '+clock:'');
  status.dataset.status=(positiveVerified.length?classification:'POSSIBLE').toLowerCase();
  status.dataset.phase=upcoming?'upcoming':'forecast';
  status.title=positiveVerified.length?'Verified-unit model lightning density forecast':'RRFS provisional lightning index; uncalibrated';
  if(dot)dot.dataset.status=status.dataset.status;
 }

 // Legacy threat rendering runs after the density feed; reapply after each render.
 const originalUpdate=window.cuUpdateThreats;
 if(typeof originalUpdate==='function'&&!originalUpdate.__lightningWrapped){
   const wrapped=function(...args){const result=originalUpdate.apply(this,args);queueMicrotask(refresh);return result;};
   wrapped.__lightningWrapped=true;
   window.cuUpdateThreats=wrapped;
 }
 load();setInterval(load,60000);setInterval(refresh,200);
})();
</script>
"""
html=re.sub(r'<script id="cu-lightning-visible-bridge">.*?</script>','',html,flags=re.S)
html=html.replace('</body>',lightning_bridge+'</body>',1) if '</body>' in html else html+lightning_bridge


# The legacy main chart shaded sounding ingredients, not the local REFC
# intervals shown by the parallel chart. Reuse one shared valid-hour source.
main_start=html.find('function drawForecast(){')
main_end=html.find('const overlayInfo=document.getElementById',main_start)
if main_start>=0 and main_end>main_start:
    main=html[main_start:main_end]
    shade_start=main.find(' // Hourly model-derived environmental ingredient shading')
    if shade_start>=0:
        main=main[:shade_start]+r""" // Shared local ≥35 dBZ reflectivity shading; no feeder multiplier.
 const localHours=window.cuLocalConvectiveShadeHours;
 const shadeCounts={local:0,unavailable:0};
 if(window.cuShowIngredientOverlay!==false && Array.isArray(localHours)){
  const active=new Set(localHours);
  times.forEach((t,i)=>{
   if(!active.has(t.slice(0,13)))return;
   const dx=PW/(times.length-1),left=Math.max(L,x(i)-dx/2),right=Math.min(W-R,x(i)+dx/2);
   const evidence=window.cuLocalConvectiveShadeEvidence?.[t.slice(0,13)];
   if(!evidence||!(evidence.maxDbz>=35))return;
   const alpha=Math.min(0.22,0.07+Math.max(0,evidence.maxDbz-35)*0.003+(evidence.models.length>1?0.04:0));
   ctx.fillStyle='rgba(255,154,54,'+alpha.toFixed(3)+')';ctx.fillRect(left,T,right-left,PH);
   shadeCounts.local++;
  });
 }
""" 
        html=html[:main_start]+main+html[main_end:]
        html=html.replace("if(overlayInfo)overlayInfo.textContent=window.cuShowIngredientOverlay===false?'Environmental shading is hidden.':'Environmental shading active: '+shadeCounts.independent+' hours supported by GFS/HRRR, '+shadeCounts.hybridOnly+' additional NAM*-only hours (hatched), '+shadeCounts.unavailable+' hours without usable screening. Shading is not a storm probability or feeder-outage prediction.';",
          "if(overlayInfo)overlayInfo.textContent=window.cuShowIngredientOverlay===false?'Local convective shading hidden.':Array.isArray(window.cuLocalConvectiveShadeHours)?'Local ≥35 dBZ reflectivity: '+shadeCounts.local+' forecast hours shaded (shared with experimental chart). No feeder increment.':'Waiting for local reflectivity screening data.';")
    else:
        print('WARNING: original shading block not found')
else:
    print('WARNING: original chart renderer not found')


# Main chart: equal-weight mean of available GFS/NAM/HRRR/RRFS feeder
# estimates at the SAME UTC hour. Never substitute zero for missing models.
# Keep model curves for comparison, but make the mean the visual focus.
mean_anchor=" if(g.length)plot(g,'#f7f9fa',[]);"
mean_replacement=r""" const averageRows=times.map(t=>{
  const values=[g,n,h,rrfs].map(rows=>rows.find(r=>r.time===t)?.forecastFeeders)
    .filter(Number.isFinite);
  return values.length>=2?{time:t,forecastFeeders:values.reduce((a,b)=>a+b,0)/values.length,modelCount:values.length}:null;
 }).filter(Boolean);
 window.cuMainModelAverage=averageRows;
 if(g.length)plot(g,'#a6b3bc',[3,5]);"""
if mean_anchor in html and "window.cuMainModelAverage=averageRows" not in html:
    html=html.replace(mean_anchor,mean_replacement,1)
    marker=" if(rrfs.length)plot(rrfs,'#d7a6ff',[3,4]);"
    html=html.replace(marker,marker+r"""
 // Highlight equal-weight average only across contiguous hourly samples.
 if(averageRows.length){
  const segments=[];let segment=[],previous=-2;
  for(const r of averageRows){
   const i=times.indexOf(r.time);
   if(i!==previous+1&&segment.length){segments.push(segment);segment=[];}
   segment.push(r);previous=i;
  }
  if(segment.length)segments.push(segment);
  for(const segment of segments)plot(segment,'#ffdf70',[]);
 }
""",1)
    html=html.replace("['GFS feeders','#f7f9fa',false]","['GFS feeders','#a6b3bc',true]",1)
    html=html.replace("['Ingredient lanes','transparent',false]","['Model average','#ffdf70',false]",1)
else:
    print('NOTICE: model-average chart already present or original plot anchor absent')


# High-contrast average styling; the per-hour values and member counts are
# published separately so a browser test can inspect the arithmetic.
html=html.replace("for(const segment of segments)plot(segment,'#ffdf70',[]);",
"""for(const segment of segments){
   plot(segment,'#ff35cb',[]);
   // Reinforce the mean without obscuring the individual model curves.
   ctx.save();ctx.strokeStyle='#ff35cb';ctx.lineWidth=4.5;ctx.setLineDash([]);
   ctx.beginPath();segment.forEach((r,i)=>{const ix=times.indexOf(r.time);if(i===0)ctx.moveTo(x(ix),y(r.forecastFeeders));else ctx.lineTo(x(ix),y(r.forecastFeeders));});
   ctx.stroke();ctx.restore();
  }""")
html=html.replace("['Model average','#ffdf70',false]","['Model average (2–4)','#ff35cb',false]")


# Show exact same-hour model values and mean beneath the operational chart.
# This is diagnostic only; it does not change the chart's predictions.
diagnostic=r"""
<script id="cu-model-average-audit">
(()=>{
 function render(){
  const rows=window.cuMainModelAverage||[];
  const cache=window.cuSurfaceWindCache||{};
  const rrfs=(window.cuRRFS95?.series||[]).map(r=>{const samples=(r.samples||[]).filter(q=>Number.isFinite(Number(q.gust)));if(!samples.length)return null;return {time:new Date(Number(r.validMs)).toISOString().slice(0,16),forecastFeeders:samples.reduce((a,q)=>{const x=Math.max(0,(Number(q.gust)-15)/5);return a+Math.max(0,0.2431*(Math.exp(0.5216*x)-1))},0)/samples.length}}).filter(Boolean);
  let host=document.getElementById('cu-model-average-audit-panel');
  const canvas=document.getElementById('live-forecast-chart');
  if(!canvas||!rows.length)return;
  if(!host){host=document.createElement('details');host.id='cu-model-average-audit-panel';host.style.cssText='margin:10px 8px;padding:10px;border:1px solid #516675;border-radius:6px;color:#d9e5ee;background:#132632;font:12px Segoe UI,Arial';canvas.closest('.cu-chart-scroll')?.insertAdjacentElement('afterend',host);}
  const first=rows[0],peak=rows.reduce((a,b)=>b.forecastFeeders>a.forecastFeeders?b:a,first);
  const selected=[first,peak,rows[Math.floor(rows.length/2)],rows[rows.length-1]].filter((r,i,a)=>a.findIndex(q=>q.time===r.time)===i).sort((a,b)=>a.time.localeCompare(b.time));
  const datasets=[['GFS',cache.gfs?.rows||[]],['NAM',cache.nam?.rows||[]],['HRRR',cache.hrrr?.rows||[]],['RRFS',rrfs]];
  const value=(set,t)=>{const x=set.find(r=>r.time===t);return Number.isFinite(x?.forecastFeeders)?x.forecastFeeders:null};
  const fmt=v=>Number.isFinite(v)?v.toFixed(2):'—';
  const trs=selected.map(row=>{
   const vals=datasets.map(([,set])=>value(set,row.time));
   const found=vals.filter(Number.isFinite);
   const computed=found.length?found.reduce((a,b)=>a+b,0)/found.length:null;
   const matches=found.length===row.modelCount&&Number.isFinite(computed)&&Math.abs(computed-row.forecastFeeders)<0.001;
   return '<tr><td>'+row.time.replace('T',' ')+'Z</td>'+vals.map(v=>'<td>'+fmt(v)+'</td>').join('')+'<td>'+row.modelCount+'</td><td>'+fmt(row.forecastFeeders)+'</td><td>'+(found.length===0?'INPUTS UNAVAILABLE':matches?'MATCH':'CHECK INPUTS')+'</td></tr>';
  }).join('');
  host.innerHTML='<summary style="cursor:pointer;font-weight:700">Model average audit · '+rows.length+' hourly points · peak '+fmt(peak.forecastFeeders)+' feeders · '+peak.modelCount+' models</summary><div style="overflow-x:auto;margin-top:8px"><table style="border-collapse:collapse;white-space:nowrap;width:100%;text-align:right"><thead><tr>'+['UTC hour','GFS','NAM','HRRR','RRFS','Count','Plotted mean','Check'].map(h=>'<th style="padding:5px;border-bottom:1px solid #526a7a">'+h+'</th>').join('')+'</tr></thead><tbody>'+trs+'</tbody></table></div><p>Missing model hours are excluded, not zero. A CHECK INPUTS result means the diagnostic could not recover exactly the same source rows as the chart; it does not imply the mean is wrong.</p>';
 }
 setInterval(render,2500);window.addEventListener('load',render);
})();
</script>
"""
html=re.sub(r'<script id="cu-model-average-audit">.*?</script>','',html,flags=re.S)
html=html.replace('</body>',diagnostic+'</body>',1) if '</body>' in html else html+diagnostic


# Recalculate the main chart after asynchronous model arrivals. The underlying
# drawForecast() computes the mean from the current source arrays each time.
reactive=r"""
<script id="cu-average-reactive-redraw">
(()=>{
 let last='',pending=false;
 const utc=v=>{const s=String(v||'');const n=Date.parse(/[zZ]$|[+-]\d\d:\d\d$/.test(s)?s:s+'Z');return Number.isFinite(n)?n:0};
 const signature=()=>{
  const cache=window.cuSurfaceWindCache||{};
  const inputs=['gfs','nam','hrrr'].map(id=>{
   const rows=cache[id]?.rows||[];
   let hash=0;
   for(const r of rows){const samples=Array.isArray(r.samples)?r.samples:[];hash=(hash*33+Number(r.validMs)/3600000+samples.length)>>>0;for(const q of samples)hash=(hash*33+Math.round(Number(q.gust||0)*100))>>>0;}
   return id+':'+rows.length+':'+hash;
  });
  const rr=window.cuRRFS95||{};
  const rows=rr.series||[];
  let hash=0;
  for(const r of rows){hash=(hash*33+Math.round((Number(r.forecastFeeders)||0)*100)+utc(r.time)/3600000)>>>0;}
  inputs.push('rrfs:'+rows.length+':'+hash);
  return inputs.join('|');
 };
 function check(){
  if(window.cuChartMode!=='live'||typeof window.drawForecast!=='function')return;
  const next=signature();if(next===last||pending)return;
  last=next;pending=true;
  requestAnimationFrame(()=>{pending=false;try{window.drawForecast()}catch(e){console.warn('Model average redraw',e)}});
 }
 setInterval(check,1200);
 window.addEventListener('cu-rrfs-updated',check);
 window.addEventListener('cu-hrrr-updated',check);
})();
</script>
"""
html=re.sub(r'<script id="cu-average-reactive-redraw">.*?</script>','',html,flags=re.S)
html=html.replace('</body>',reactive+'</body>',1) if '</body>' in html else html+reactive


# HRRR availability on the main wind chart must be based on the NOAA wind
# forecast's valid hours, not the shorter reflectivity or legacy API window.
coverage=r"""
<script id="cu-hrrr-wind-coverage-audit">
(()=>{
 async function check(){
  try{
   const res=await fetch('./hrrr_wind.json?t='+Date.now(),{cache:'no-store'});
   if(!res.ok)return;
   const data=await res.json();
   const hours=(data.hours||[]).map(h=>Date.parse(String(h.time).match(/Z$|[+-]\d\d:\d\d$/i)?h.time:h.time+'Z')).filter(Number.isFinite).sort((a,b)=>a-b);
   if(!hours.length)return;
   window.cuHRRRWindValidHours=hours;
   const last=hours[hours.length-1],first=hours[0];
   let label=document.getElementById('cu-hrrr-wind-coverage-note');
   const canvas=document.getElementById('live-forecast-chart');
   if(!canvas)return;
   if(!label){label=document.createElement('div');label.id='cu-hrrr-wind-coverage-note';label.style.cssText='padding:5px 10px;color:#9fe0ff;font:12px Segoe UI,Arial';canvas.closest('.cu-chart-scroll')?.insertAdjacentElement('afterend',label);}
   const fmt=t=>new Date(t).toLocaleString('en-US',{timeZone:'America/Chicago',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'});
   label.textContent='NOAA HRRR wind forecast coverage: '+fmt(first)+' through '+fmt(last)+' ('+hours.length+' decoded hours). The plotted HRRR feeder curve may have shorter coverage; a shorter curve indicates a chart data-mapping issue, not an absent NOAA wind forecast.';
  }catch(e){console.warn('HRRR wind coverage audit',e)}
 }
 check();setInterval(check,60000);
})();
</script>
"""
html=re.sub(r'<script id="cu-hrrr-wind-coverage-audit">.*?</script>','',html,flags=re.S)
html=html.replace('</body>',coverage+'</body>',1) if '</body>' in html else html+coverage


# Fix misleading HRRR lane cutoff: that lane is reflectivity coverage, not
# the NOAA wind/feeder curve. Do not claim wind is unavailable when REFC ends.
html=html.replace("ctx.fillText('NO HRRR FORECAST AVAILABLE',","ctx.fillText('NO HRRR REFLECTIVITY AVAILABLE',")
# Hourly RRFS wind is published independently of the older 6-hour direct
# GRIB comparison. Prefer its 12-site hourly values for the chart and mean.
rrfs_start=html.find(' const rrfs=(window.cuRRFS95?.series||[]).map(r=>{',html.find('function drawForecast(){'))
rrfs_end=html.find(' if(!g.length&&!h.length&&!n.length&&!rrfs.length)return;',rrfs_start)
if rrfs_start>=0 and rrfs_end>rrfs_start:
    existing=html[rrfs_start:rrfs_end]
    if 'window.cuRRFSHourlyFeeders' not in existing:
        existing=existing.replace(' const rrfs=', ' const rrfsLegacy=',1)
        existing += r""" const rrfs=(window.cuRRFSHourlyFeeders?.length?window.cuRRFSHourlyFeeders:rrfsLegacy);
"""
        html=html[:rrfs_start]+existing+html[rrfs_end:]
# Published hourly RRFS gusts use the same 12-site feeder conversion as
# the existing comparison curve. Do not interpolate missing hours.
hourly_rrfs=r"""
<script id="cu-rrfs-hourly-main">
(()=>{
 async function load(){
  try{
   const r=await fetch('./rrfs_wind.json?t='+Date.now(),{cache:'no-store'});
   if(!r.ok)return;
   const data=await r.json();if(!Array.isArray(data.hours))return;
   const rows=data.hours.map(h=>{
    const samples=(h.gust_ms||[]).map(Number).filter(Number.isFinite);
    if(!samples.length)return null;
    const feeders=samples.reduce((sum,v)=>{
      const x=Math.max(0,(v*2.2369362921-15)/5);
      return sum+Math.max(0,0.2431*(Math.exp(0.5216*x)-1));
    },0)/samples.length;
    const raw=String(h.time),ms=Date.parse(/[zZ]$|[+-]\d\d:\d\d$/.test(raw)?raw:raw+'Z');
    if(!Number.isFinite(ms))return null;
    return {time:new Date(ms).toISOString().slice(0,13)+':00',forecastFeeders:feeders,comparisonOnly:true};
   }).filter(Boolean);
   if(rows.length){window.cuRRFSHourlyFeeders=rows;window.drawForecast?.();}
  }catch(e){console.warn('RRFS hourly main chart',e)}
 }
 window.addEventListener('load',load);setInterval(load,60000);
})();
</script>
"""
html=re.sub(r'<script id="cu-rrfs-hourly-main">.*?</script>','',html,flags=re.S)
html=html.replace('</body>',hourly_rrfs+'</body>',1) if '</body>' in html else html+hourly_rrfs
# Audit the identical hourly RRFS input used by the chart.
html=html.replace("const rrfs=(window.cuRRFS95?.series||[]).map(r=>{const samples=", "const rrfsLegacy=(window.cuRRFS95?.series||[]).map(r=>{const samples=")
html=html.replace("  window.cuAverageAuditRRFS=rrfs;","  const rrfs=window.cuRRFSHourlyFeeders?.length?window.cuRRFSHourlyFeeders:rrfsLegacy;\n  window.cuAverageAuditRRFS=rrfs;")


# Final canonical pass: all chart timestamps are UTC hourly keys. Apply to
# the actual arrays that the model-average plot reads, not a separate cache.
canonical=r"""
 const hourKey=v=>{
  const raw=String(v||'');
  const ms=Date.parse(/(?:Z|[+-]\d{2}:\d{2})$/i.test(raw)?raw:raw+'Z');
  return Number.isFinite(ms)?new Date(ms).toISOString().slice(0,13)+':00':null;
 };
 for(const rows of [g,n,h,rrfs])for(const row of rows){
  const key=hourKey(row.time);if(key)row.time=key;
 }
 window.cuAverageSourceRows={gfs:g,nam:n,hrrr:h,rrfs:rrfs};
"""
target=" if(!g.length&&!h.length&&!n.length&&!rrfs.length)return;"
if target not in html:
    raise RuntimeError('Cannot find main chart model data boundary')
if "window.cuAverageSourceRows={gfs:g" not in html:
    html=html.replace(target,canonical+target,1)
# Use exact chart arrays for audit, not independently reconstructed data.
audit_old="  const datasets=[['GFS',cache.gfs?.rows||[]],['NAM',cache.nam?.rows||[]],['HRRR',cache.hrrr?.rows||[]],['RRFS',rrfs]];"
audit_new="  const source=window.cuAverageSourceRows||{};\n  const datasets=[['GFS',source.gfs||[]],['NAM',source.nam||[]],['HRRR',source.hrrr||[]],['RRFS',source.rrfs||[]]];"
if audit_old in html:
    html=html.replace(audit_old,audit_new,1)
else:
    raise RuntimeError('Cannot find average audit model source boundary')
# Reflectivity coverage must compare the UTC forecast hour with the UTC
# reflectivity valid timestamp, not browser-local interpretation of UTC.
old="const endIdx=times.findIndex(t=>Date.parse(t)>last);"
new="const endIdx=times.findIndex(t=>Date.parse(t+'Z')>last);"
if old in html:
    html=html.replace(old,new,1)
elif new not in html:
    print('NOTICE: HRRR reflectivity cutoff uses a different renderer expression; leaving it unchanged')
# Audit panel: preserve a recognizable title even before any rows load.
html=html.replace("host.innerHTML='<summary style=\"cursor:pointer;font-weight:700\">Model average audit", "host.innerHTML='<summary style=\"cursor:pointer;font-weight:700\">Model average audit")
# The source arrays and average are now generated from the same valid hours.
# Never treat missing source rows as zero or average derived convective curves.


# Use decoded NOAA HRRR wind directly for the chart (not the shorter
# Open-Meteo HRRR forecast). Retain its original 12-site feeder formula.
chart_start=html.find('function drawForecast(){')
chart_end=html.find('const viewportWidth=',chart_start)
if chart_start<0 or chart_end<chart_start:
    raise RuntimeError('Main chart renderer missing')
block=html[chart_start:chart_end]
old_h="const g=cache.gfs?.rows||[],h=cache.hrrr?.rows||[],n=cache.nam?.rows||[];"
new_h="const g=cache.gfs?.rows||[],h=(window.cuNOAAHRRRFeeders?.length?window.cuNOAAHRRRFeeders:cache.hrrr?.rows||[]),n=cache.nam?.rows||[];"
if old_h in block:
    block=block.replace(old_h,new_h,1)
elif new_h not in block:
    raise RuntimeError('HRRR chart source anchor missing')
html=html[:chart_start]+block+html[chart_end:]
# The browser source rows are exact same arrays used for the plotted average.
hrrr_script=r"""
<script id="cu-noaa-hrrr-main-feed">
(()=>{
 const convert=gust=>{const x=Math.max(0,(gust-15)/5);return Math.max(0,0.2431*(Math.exp(0.5216*x)-1));};
 async function refresh(){
  try{
   const res=await fetch('./hrrr_wind.json?ts='+Date.now(),{cache:'no-store'});
   if(!res.ok)throw Error('HTTP '+res.status);
   const data=await res.json();
   if(!Array.isArray(data.hours)||!data.hours.length)throw Error('No NOAA HRRR wind hours');
   const rows=data.hours.map(h=>{
    const values=Array.isArray(h.gust_ms)?h.gust_ms.map(Number).filter(Number.isFinite):[];
    if(values.length<10)return null;
    const raw=String(h.time),ms=Date.parse(/(?:Z|[+-]\d{2}:\d{2})$/i.test(raw)?raw:raw+'Z');
    if(!Number.isFinite(ms))return null;
    const mph=values.map(v=>v*2.2369362921);
    return {time:new Date(ms).toISOString().slice(0,13)+':00',
     forecastFeeders:mph.reduce((sum,v)=>sum+convert(v),0)/mph.length,
     max:Math.max(...mph),mean:mph.reduce((a,b)=>a+b,0)/mph.length,
     count:mph.length,source:'NOAA HRRR',cycle:data.cycle};
   }).filter(Boolean).sort((a,b)=>a.time.localeCompare(b.time));
   if(!rows.length)throw Error('No valid NOAA HRRR site records');
   const previous=window.cuNOAAHRRRFeeders||[];
   const signature=a=>a.map(x=>x.time+':'+x.forecastFeeders.toFixed(5)).join('|');
   if(signature(rows)!==signature(previous)){
    window.cuNOAAHRRRFeeders=rows;
    if(typeof window.drawForecast==='function')window.drawForecast();
   }
   window.cuNOAAHRRRCoverage={cycle:data.cycle,first:rows[0].time,last:rows[rows.length-1].time,count:rows.length};
  }catch(e){console.warn('NOAA HRRR main chart feed',e)}
 }
 window.addEventListener('load',refresh);
 setInterval(refresh,60000);
})();
</script>
"""
html=re.sub(r'<script id="cu-noaa-hrrr-main-feed">.*?</script>','',html,flags=re.S)
if '</body>' not in html: raise RuntimeError('HTML body closing tag missing')
html=html.replace('</body>',hrrr_script+'</body>',1)
# Reflectivity is separate; its marker must not be interpreted as wind coverage.
html=html.replace("NO HRRR FORECAST AVAILABLE","NO HRRR REFLECTIVITY AVAILABLE")
# Explicit audit source count from NOAA HRRR; no averaging of convective curves.


# Six-curve renderer patch disabled: source anchors do not match current chart.
# Preserve the last successfully installed dashboard until verified repair.


# Repair six-curve DISPLAY mean against the actual current renderer. Insert
# after the qualified/integrated arrays exist; do not depend on obsolete
# plotQualifiedArray call signatures.
start=html.find('function drawForecast(){')
end=html.find(' const qCount=qImpact.filter(Number.isFinite).length;',start)
if start>=0 and end>start:
    end+=len(' const qCount=qImpact.filter(Number.isFinite).length;')
    block=html[start:end]
    if 'const qIntegrated=times.map(' in block and 'const qImpact=times.map(' in block:
        # Rename the earlier four-model average so existing plot code still
        # renders, then overlay the correctly computed six-curve display mean.
        block=block.replace('window.cuMainModelAverage=averageRows;', 'window.cuWindOnlyAverage=averageRows;',1)
        # Retain legacy average plot for diagnostics; six-curve line draws last.
        insertion=r"""
 // Composite of ALL visible feeder curves (4 model + 2 derived).
 // Not an independent multi-model consensus; derived curves share HRRR inputs.
 const compositeSources=[g,n,h,rrfs,
   times.map((t,i)=>({time:t,forecastFeeders:qImpact[i]})),
   times.map((t,i)=>({time:t,forecastFeeders:qIntegrated[i]}))];
 const compositeRows=times.map(t=>{
  const members=compositeSources.map(rows=>rows.find(r=>r.time===t)?.forecastFeeders);
  const valid=members.filter(Number.isFinite);
  return valid.length>=2?{time:t,forecastFeeders:valid.reduce((a,b)=>a+b,0)/valid.length,
   modelCount:valid.length,values:members}:null;
 }).filter(Boolean);
 window.cuMainModelAverage=compositeRows;
 window.cuAverageSourceRows={gfs:g,nam:n,hrrr:h,rrfs:rrfs,
  qualified:compositeSources[4],integrated:compositeSources[5]};
 // Draw the six-curve composite over the old four-model average.
 if(compositeRows.length){
  ctx.save();ctx.strokeStyle='#ff35cb';ctx.lineWidth=4;ctx.setLineDash([]);
  ctx.beginPath();let active=false,prev=-2;
  compositeRows.forEach(r=>{
   const i=times.indexOf(r.time);
   if(i!==prev+1)active=false;
   if(!active)ctx.moveTo(x(i),y(r.forecastFeeders));
   else ctx.lineTo(x(i),y(r.forecastFeeders));
   active=true;prev=i;
  });
  ctx.stroke();ctx.restore();
 }
"""
        needle=" const qCount=qImpact.filter(Number.isFinite).length;"
        if needle in block and 'const compositeSources=' not in block:
            block=block.replace(needle,insertion+needle,1)
            html=html[:start]+block+html[end:]
            html=html.replace('Model average (2–4)','All curves (2–6)')
            print('Installed six-curve composite mean')
        else: print('NOTICE: composite plot anchor unavailable or already installed')
    else: print('NOTICE: existing model-average or convective arrays unavailable')
else: print('NOTICE: chart renderer not found')
# Align audit with plotted composite rows. The audit reads the same exact
# values array rather than recomputing from a potentially stale cache.
html=html.replace("const vals=datasets.map(([,set])=>value(set,row.time));",
 "const vals=Array.isArray(row.values)?row.values:datasets.map(([,set])=>value(set,row.time));")
html=html.replace("['UTC hour','GFS','NAM','HRRR','RRFS','Count','Plotted mean','Check']",
 "['UTC hour','GFS','NAM','HRRR','RRFS','Qualified','Integrated','Count','Plotted mean','Check']")
html=html.replace("Model average audit · ","All-curve average audit · ")


# Lightning operational timing: earliest future positive signal, not the
# largest value later in the forecast. Keep maximum intensity for severity.
html=html.replace("const signal=raw.sort((a,b)=>b.value-a.value)[0];",
"""const signal=raw.filter(x=>x.value>0).sort((a,b)=>Date.parse(a.time)-Date.parse(b.time))[0];""")
# A thunderstorm forecast is not a lightning observation. Avoid a later
# provisional model peak overriding an earlier positive valid forecast hour.
html=html.replace("const best=candidates.sort((a,b)=>b.value-a.value)[0];",
"""const best=candidates.filter(x=>x.value>0).sort((a,b)=>Date.parse(a.time)-Date.parse(b.time))[0];""")
# Show whether the six-curve patch really matched the generated HTML.
if 'const compositeSources=' not in html:
    print('::warning::Six-curve composite was NOT installed in generated HTML')
else:
    print('Six-curve composite source present in generated HTML')


# Guard the operational lightning tile against unverified inputs and
# misleading timestamps. A reflectivity-only storm signal is not measured
# or calibrated lightning flash density.
lightning_guard=r"""
<script id="cu-lightning-source-integrity">
(()=>{
 const parse=t=>{const s=String(t||'');return Date.parse(/(?:Z|[+-]\d\d:\d\d)$/i.test(s)?s:s+'Z')};
 const fmt=ms=>new Date(ms).toLocaleString('en-US',{timeZone:'America/Chicago',weekday:'short',hour:'numeric',minute:'2-digit',timeZoneName:'short'});
 function update(){
  const tile=[...document.querySelectorAll('*')].find(e=>e.children.length===0&&e.textContent.trim()==='Lightning')?.closest('.threat-tile');
  if(!tile)return;
  const status=tile.querySelector('.threat-time,.threat-status');
  if(!status)return;
  const now=Date.now()-15*60000;
  const verified=(window.cuLightningDensityForecasts||[]).filter(x=>x?.units_verified===true&&x.units==='flashes/km²/5 min'&&Number.isFinite(x.value)&&x.value>0&&Number.isFinite(parse(x.time))&&parse(x.time)>=now).sort((a,b)=>parse(a.time)-parse(b.time));
  const raw=(window.cuLightningRawSignals||[]).filter(x=>Number.isFinite(x?.value)&&x.value>0&&Number.isFinite(parse(x.time))&&parse(x.time)>=now).sort((a,b)=>parse(a.time)-parse(b.time));
  const v=verified[0],r=raw[0];
  if(v){
    const band=window.cuHRRRLightningLevel?.(v.value);
    const level=band?.level||'possible';
    status.textContent=level.toUpperCase()+' · '+fmt(parse(v.time));
    status.title='Verified '+String(v.model||'model').toUpperCase()+' lightning flash density: '+v.value+' flashes/km²/5 min';
    status.dataset.status=level;
  }else if(r){
    status.textContent='POSSIBLE · '+fmt(parse(r.time));
    status.title='Uncalibrated model lightning signal; screening only, not verified flash density';
    status.dataset.status='possible';
  }else{
    status.textContent='UNVERIFIED';
    status.title='No valid positive native lightning forecast. Reflectivity-only storm potential is tracked separately; missing lightning is not zero.';
    status.dataset.status='waiting';
  }
 }
 document.addEventListener('cu-lightning-data-ready',update);
 window.addEventListener('load',update);
 setInterval(update,10000);
})();
</script>
"""
html=re.sub(r'<script id="cu-lightning-source-integrity">.*?</script>','',html,flags=re.S)
html=html.replace('</body>',lightning_guard+'</body>',1)


# HRRR lane: show decoded NOAA wind coverage independently of reflectivity.
hrrr_lane_anchor="  // A single number per contiguous colored segment keeps hourly data legible."
hrrr_wind_stripe=r"""  // Independent decoded NOAA wind coverage. The HRRR reflectivity forecast can
  // end earlier; cyan top edge marks WIND hours without inventing REFC values.
  if(id==='hrrr'){
   const windHours=new Set(h.filter(r=>Number.isFinite(r.forecastFeeders)).map(r=>String(r.time).slice(0,13)));
   times.forEach((t,i)=>{
    if(!windHours.has(t.slice(0,13)))return;
    const xx=Math.max(L,x(i)-step/2),right=Math.min(L+PW,x(i)+step/2);
    ctx.fillStyle='#62d8f0';ctx.fillRect(xx,top,Math.max(1,right-xx+0.4),3);
   });
   window.cuHRRRBarCoverage={windHours:windHours.size,reflectivityHours:(hrrrAudit?.unique||[]).length};
  }
"""
if hrrr_lane_anchor not in html:
    raise SystemExit('ERROR: HRRR lane draw anchor missing')
if 'window.cuHRRRBarCoverage=' not in html:
    html=html.replace(hrrr_lane_anchor,hrrr_wind_stripe+hrrr_lane_anchor,1)

# Remove the obsolete second magenta overlay; the unified six-source
# calculation below is the only authoritative magenta line.
duplicate_start=html.find(' // Composite of ALL visible feeder curves')
duplicate_end=html.find(' const qCount=qImpact.filter(Number.isFinite).length;',duplicate_start)
if duplicate_start>=0 and duplicate_end>duplicate_start:
    html=html[:duplicate_start]+html[duplicate_end:]
    print('Removed duplicate composite mean overlay')

# Verified chart-source patch: qImpact and qIntegrated are numeric arrays
# created immediately before plotQualifiedArray. Recompute the display mean
# at that exact point, using the same time indices and excluding missing data.
six_anchor=" plotQualifiedArray(qIntegrated,'#ff9f43',[8,4],3.5);"
six_js=r"""
 // Average all available feeder-impact curves, including the two derived convective curves.
 const sixSources=[g,n,h,rrfs].map(rows=>new Map(rows.map(r=>[String(r.time).slice(0,16),r.forecastFeeders])));
 const sixRows=times.map((t,i)=>{
   const vals=sixSources.map(m=>m.get(String(t).slice(0,16))).concat([qImpact[i],qIntegrated[i]]);
   const valid=vals.filter(Number.isFinite);
   return valid.length?{time:t,forecastFeeders:valid.reduce((a,b)=>a+b,0)/valid.length,modelCount:valid.length,values:vals}:null;
 }).filter(Boolean);
 window.cuMainModelAverage=sixRows;
 window.cuAverageSourceRows={gfs:g,nam:n,hrrr:h,rrfs:rrfs,qualified:times.map((t,i)=>({time:t,forecastFeeders:qImpact[i]})),integrated:times.map((t,i)=>({time:t,forecastFeeders:qIntegrated[i]}))};
 window.cuSixCurveCoverage={hours:sixRows.length,qualified:qImpact.filter(Number.isFinite).length,integrated:qIntegrated.filter(Number.isFinite).length};
 // Restore all individual curves on EVERY redraw after late data loads.
 // Do not let the ensemble overlay obscure or replace the model traces.
 if(g.length)plot(g,'#a6b3bc',[3,5]);
 if(n.length)plot(n,'#62a7ff',[3,5]);
 if(h.length)plot(h,'#ff9f43',[3,5]);
 if(rrfs.length)plot(rrfs,'#d7a6ff',[3,5]);
 plotQualifiedArray(qImpact,'#55dba0',[5,4],2.5);
 plotQualifiedArray(qIntegrated,'#ff9f43',[8,4],2.5);
 // Paint the six-input average last.
 if(sixRows.length){
  ctx.save();ctx.strokeStyle='#ff35cb';ctx.lineWidth=4.5;ctx.setLineDash([]);ctx.beginPath();
  let previous=-2;
  for(const r of sixRows){
   const i=times.indexOf(r.time);
   if(i!==previous+1)ctx.moveTo(x(i),y(r.forecastFeeders));
   else ctx.lineTo(x(i),y(r.forecastFeeders));
   previous=i;
  }
  ctx.stroke();ctx.restore();
 }
"""
if six_anchor not in html:
    raise SystemExit('ERROR: actual six-curve renderer anchor missing')
if six_anchor not in html:
    raise SystemExit('ERROR: actual six-curve renderer anchor missing')
if 'window.cuSixCurveCoverage=' not in html:
    html=html.replace(six_anchor,six_anchor+six_js,1)
    print('Installed six-curve calculation after qualified curves')
# Upgrade an already-installed six-curve block in the published HTML.
# Replacing the Python template alone does not update HTML on later runs,
# because its installation guard detects the prior block.
six_begin=html.find(' // Average all available feeder-impact curves, including the two derived convective curves.')
six_end=html.find(' window.cuSixCurveCoverage=',six_begin)
if six_begin<0 or six_end<six_begin:
    raise SystemExit('ERROR: installed six-curve mean missing')
six_existing=html[six_begin:six_end]
six_existing=six_existing.replace('return valid.length>=2?', 'return valid.length?')
if 'window.cuAverageSourceRows=' not in six_existing:
    six_existing=six_existing.replace(' window.cuMainModelAverage=sixRows;',
      " window.cuMainModelAverage=sixRows;\\n window.cuAverageSourceRows={gfs:g,nam:n,hrrr:h,rrfs:rrfs,qualified:times.map((t,i)=>({time:t,forecastFeeders:qImpact[i]})),integrated:times.map((t,i)=>({time:t,forecastFeeders:qIntegrated[i]}))};")
html=html[:six_begin]+six_existing+html[six_end:]
print('Verified one available source is sufficient for six-curve mean')

# Correct audit member names, counts, and display from the actual rows.
html=html.replace("const vals=datasets.map(([,set])=>value(set,row.time));",
                  "const vals=Array.isArray(row.values)?row.values:datasets.map(([,set])=>value(set,row.time));")
html=html.replace("['UTC hour','GFS','NAM','HRRR','RRFS','Count','Plotted mean','Check']",
                  "['UTC hour','GFS','NAM','HRRR','RRFS','Qualified','Integrated','Count','Plotted mean','Check']")
# Remove a misleading fallback label when derived curves have no valid values.
html=html.replace("All curves (2–6)","All available curves (2–6)")


# Repair confirmed browser exceptions in generated legacy panels.
# The model inventory uses updateGlobal() even when the old helper is absent.
html=html.replace("  updateGlobal();return;","  if(typeof updateGlobal==='function')updateGlobal();return;")
# RRFS developer probe controls are optional; avoid terminating the page's script.
html=html.replace("  $('rrfs-cycle').addEventListener('change',links);$('rrfs-hour').addEventListener('change',links);",
                  "  if($('rrfs-cycle'))$('rrfs-cycle').addEventListener('change',links);if($('rrfs-hour'))$('rrfs-hour').addEventListener('change',links);")
html=html.replace("  $('rrfs-test').addEventListener('click',test);links();",
                  "  if($('rrfs-test'))$('rrfs-test').addEventListener('click',test);if($('rrfs-cycle')&&$('rrfs-hour'))links();")
# RRFS chart container may have been replaced by the newer main chart.
# Do not dereference an absent canvas.
html=html.replace("const note=panel.querySelector('.rrfs-note'),canvas=panel.querySelector('canvas'),ctx=canvas.getContext('2d');",
                  "const note=panel.querySelector('.rrfs-note'),canvas=panel.querySelector('canvas');if(!note||!canvas)return;const ctx=canvas.getContext('2d');if(!ctx)return;")

# Enforce repairs against generated HTML, including legacy whitespace variants.
# Fail generation if any known broken expression survives.
for label,pattern,replacement in [
 ('inventory updateGlobal',r'(?<![\w.])updateGlobal\s*\(\s*\)\s*;\s*return\s*;',
  "if(typeof updateGlobal==='function')updateGlobal();return;"),
 ('RRFS cycle handler',r"\$\(\s*['\"]rrfs-cycle['\"]\s*\)\.addEventListener\s*\(\s*['\"]change['\"]\s*,\s*links\s*\)",
  "document.getElementById('rrfs-cycle')?.addEventListener('change',links)"),
 ('RRFS hour handler',r"\$\(\s*['\"]rrfs-hour['\"]\s*\)\.addEventListener\s*\(\s*['\"]change['\"]\s*,\s*links\s*\)",
  "document.getElementById('rrfs-hour')?.addEventListener('change',links)"),
 ('RRFS test handler',r"\$\(\s*['\"]rrfs-test['\"]\s*\)\.addEventListener\s*\(\s*['\"]click['\"]\s*,\s*test\s*\)",
  "document.getElementById('rrfs-test')?.addEventListener('click',test)"),
 ('RRFS missing canvas',r"ctx\s*=\s*canvas\.getContext\('2d'\)",
  "ctx=canvas?.getContext('2d')"),
]:
 if label=='inventory updateGlobal':
  # Only patch bare calls, never an already guarded branch.
  html,n=re.subn(r'(?<![\w.])(?<!\))updateGlobal\s*\(\s*\)\s*;\s*return\s*;',replacement,html)
 elif label=='RRFS missing canvas':
  # The optional chain protects lookup but the renderer must return if absent.
  html,n=re.subn(pattern,replacement,html)
 else:
  html,n=re.subn(pattern,replacement,html)
 print('Runtime repair',label,'replacements',n)
# Ensure legacy RRFS panel rendering does not continue after a missing canvas.
html=html.replace("const valid=rows.filter(r=>Number.isFinite(r.gust));",
                  "if(!ctx)return;const valid=rows.filter(r=>Number.isFinite(r.gust));")
# Assert no direct RRFS handler dereferences or unguarded canvas access remain.
for label,pattern in [
 ('unguarded RRFS control',r"\$\(\s*['\"]rrfs-(?:cycle|hour|test)['\"]\s*\)\.addEventListener")
]:
 if re.search(pattern,html):raise SystemExit('ERROR: '+label+' remains in generated HTML')

# Optional RRFS developer probe is not present in production layout.
# Its links() initializer must not abort the dashboard when controls are absent.
html=html.replace("if($('rrfs-cycle')&&$('rrfs-hour'))links();",
                  "if($('rrfs-cycle')&&$('rrfs-hour')){try{links()}catch(e){console.warn('RRFS probe controls incomplete',e.message)}}")
print('Patched three observed browser exception sites')


# The legacy chart's HRRR declaration is not in the assumed boundary.
# Do not abort all NOAA publication while investigating its actual renderer.
# Keep the direct NOAA hourly feed available without mutating an unknown binding.
hrrr_script=r"""
<script id="cu-direct-hrrr-hourly-chart">
(()=>{
 async function refresh(){
  try{
   const response=await fetch('./hrrr_wind.json?t='+Date.now(),{cache:'no-store'});
   if(!response.ok)return;
   const data=await response.json();
   const rows=(data.hours||[]).map(hour=>{
    const samples=(hour.gust_ms||[]).map(Number).filter(Number.isFinite);
    if(!samples.length)return null;
    const feeders=samples.reduce((sum,ms)=>{
      const x=Math.max(0,(ms*2.2369362921-15)/5);
      return sum+Math.max(0,0.2431*(Math.exp(0.5216*x)-1));
    },0)/samples.length;
    const raw=String(hour.time||'');
    const date=Date.parse(/(?:Z|[+-]\\d{2}:\\d{2})$/i.test(raw)?raw:raw+'Z');
    return Number.isFinite(date)?{time:new Date(date).toISOString().slice(0,13)+':00',forecastFeeders:feeders}:null;
   }).filter(Boolean);
   if(rows.length){
    window.cuHRRRHourlyFeeders=rows;
    if(typeof window.drawForecast==='function')window.drawForecast();
   }
  }catch(error){console.warn('NOAA HRRR chart feed',error)}
 }
 window.addEventListener('load',refresh);
 setInterval(refresh,60000);
})();
</script>
"""
html=re.sub(r'<script id="cu-direct-hrrr-hourly-chart">.*?</script>','',html,flags=re.S)
html=html.replace('</body>',hrrr_script+'</body>',1)

path.write_text(html,encoding='utf-8')
print('Installed model health cards and independent gust chart')
