"""Install or upgrade NOAA status and independent decoded-gust chart."""
from pathlib import Path
import re

path = Path("index.html")
html = path.read_text(encoding="utf-8")
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
   window.cuNAMRunLabel=published.nam?.cycle_verified&&/^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}Z$/.test(published.nam.cycle||'')?published.nam.cycle.slice(11,13)+'Z':'API';
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
     const median=values.length%2?values[(values.length-1)/2]:(values[values.length/2-1]+values[values.length/2])/2;
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
   const convective=reflectivity.filter(r=>['gfs','hrrr','rrfs'].includes(String(r.model).toLowerCase())).map(r=>{
     const time=Date.parse(r.time);
     const local=Number(r.zones?.springfield_area);
     const site=Array.isArray(r.site_dbz)?Math.max(-10,...r.site_dbz.filter(Number.isFinite)):-10;
     const dbz=Math.max(Number.isFinite(local)?local:-10,site);
     return {time,model:String(r.model).toLowerCase(),dbz};
   }).filter(r=>Number.isFinite(r.time)&&r.time>=Date.now()-3600000&&r.dbz>=35);
   const convectiveWindows=consensus.map(row=>{
     const t=Date.parse(row.time);
     const matches=convective.filter(r=>Math.abs(r.time-t)<=90*60000);
     const models=[...new Set(matches.map(r=>r.model))];
     const maxDbz=matches.length?Math.max(...matches.map(r=>r.dbz)):null;
     return {...row,convective_models:models,local_reflectivity_dbz:maxDbz,convective_screen:models.length>=2?'Multi-model local convection':models.length===1?'Single-model local convection':'No local 35 dBZ signal',convective_feeders_added:0};
   });
   // Avoid arbitrary thunderstorm feeder multipliers or double-counting the wind
   // already included in gust guidance. This is a screening overlay, not a forecast.
   window.cuConvectiveScreen=convectiveWindows;
   const activeWindows=convectiveWindows.filter(x=>x.convective_models.length);
   const convectivePanel='<div style="margin-top:12px"><strong>Convective reflectivity screening</strong><div style="font-size:12px;color:#c0d0d9">Local Springfield-area reflectivity ≥35 dBZ within ±90 minutes of a forecast hour. Regional storms outside the service area do not count. This flags possible convective exposure but does not yet assign additional feeder outages.</div>'+(activeWindows.length?'<div style="margin-top:6px;color:#ffbd74">Potential local convection: '+activeWindows.length+' forecast hours; '+activeWindows.filter(x=>x.convective_models.length>=2).length+' supported by 2+ models.</div>':'<div style="margin-top:6px;color:#a9c8d3">No local ≥35 dBZ convective signal in the available model forecasts.</div>')+'<div style="font-size:12px;color:#c0d0d9;margin-top:5px">Convective feeder adjustment: not calibrated (0 added). No double-counting.</div></div>';
   const convectivePoints=activeWindows.map(x=>({time:Date.parse(x.time),value:x.estimated_feeders,color:'#ff9a36'}));
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
   const nearTerm=ensembleRows.filter(r=>{const t=Date.parse(r.time);return t>=nowHour-3600000&&t<=nowHour+6*3600000;});
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
     const preview=valid.map(x=>({time:Date.parse(x.time),value:x.estimated_feeders,color:'#ffb86b'}));
     const bands=conv.map(x=>({start:Date.parse(x.time)-30*60000,end:Date.parse(x.time)+30*60000}));
     const stageName=n=>'Stage '+n;
     const ensemblePeak=window.cuModelEnsembleOutageForecast?.reduce((a,b)=>!a||b.feeders>a.feeders?b:a,null);
     const stageSummary=ensemblePeak?'<div role="status" style="padding:9px 0;font-weight:700">Four-model wind outlook: '+stageName(ensemblePeak.stage)+' · '+ensemblePeak.feeders.toFixed(1)+' feeders · '+ensemblePeak.model_count+'/4 models · '+esc(ensemblePeak.time.slice(5,16).replace('T',' ')+'Z')+'</div>':'';
     parallel.innerHTML='<div style="font-weight:700;font-size:14px">Four-model parallel forecast <span style="font-size:11px;color:#ffcf8c">(EXPERIMENTAL · not operational)</span></div>'+stageSummary+'<div style="margin:5px 0;color:#c3d4dc">NOAA HRRR/RRFS + Open-Meteo coverage supplementation; GFS/NAM from Open-Meteo. Original calculated forecast and response stages are unchanged.</div>'+(peak?'<div style="margin:6px 0"><b>Peak wind-only estimate:</b> '+peak.estimated_feeders.toFixed(1)+' feeders · '+esc(peak.time.slice(5,16).replace('T',' ')+'Z')+' · '+confidence+' available at peak</div>':'<div>Insufficient multi-model coverage for feeder estimate</div>')+chart([preview],10,bands)+'<div style="color:#f7be75">■ Shaded: local ≥35 dBZ convection · '+conv.length+' screened hours; '+conv.filter(x=>x.convective_models.length>=2).length+' with multi-model support</div><div style="color:#b9cbd4;margin-top:5px">No convective feeder increment. Forecast is shown alongside the main model for validation, not substituted into the operational prediction.</div>';
   }

   // Publish RRFS's own independently calculated feeder estimate for the shared chart.
   // This is a separate experimental series, not a silent change to operational alerts.
   const rrfsFeederCurve=(series[1]||[]).map(p=>{
     const mph=Math.max(0,Number(p.value)||0);
     const feeders=mph<30?0:mph<40?(mph-30)*0.5:mph<55?5+(mph-40)*2/3:mph<60?15+(mph-55):Math.min(170,20+(mph-60)*2);
     return {time:new Date(p.time).toISOString(),feeders:Math.max(0,feeders),model:'rrfs'};
   }).filter(p=>Number.isFinite(p.feeders));
   window.cuRRFSFeederCurve=rrfsFeederCurve;
   const consensusSeries=consensus.filter(x=>x.model_count>=2).map(x=>({time:Date.parse(x.time),value:x.estimated_feeders,color:'#ffb86b'}));
   const convectiveBands=activeWindows.map(x=>({start:Date.parse(x.time)-30*60000,end:Date.parse(x.time)+30*60000}));
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
  const points=rows.map(r=>({t:Date.parse(r.time),v:Number(r.feeders)})).filter(r=>Number.isFinite(r.t)&&Number.isFinite(r.v)&&r.t>=first&&r.t<=last).sort((a,b)=>a.t-b.t);
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
if original in html:
    html=html.replace(original,replacement,1)
elif replacement not in html:
    raise SystemExit('Original operational canvas lane labels not found; refusing silent success')

path.write_text(html,encoding='utf-8')
print('Installed model health cards and independent gust chart')
