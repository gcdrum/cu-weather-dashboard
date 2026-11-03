// Browser-level Lightning integration test. Synthetic responses are intercepted in
// the test browser only; no forecast files or deployed HTML are modified.
const {chromium}=require('playwright');
const http=require('http');
const fs=require('fs');
const path=require('path');
(async()=>{
 const server=http.createServer((req,res)=>{
   const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
   const file=path.join(process.cwd(),pathname.replace(/^\/+/,''))||'index.html';
   const target=pathname==='/'?'index.html':pathname.slice(1);
   if(target.includes('..')){res.writeHead(403);return res.end();}
   fs.readFile(target,(err,data)=>{
     if(err){res.writeHead(404);return res.end();}
     res.writeHead(200,{'Content-Type':target.endsWith('.json')?'application/json':target.endsWith('.js')?'text/javascript':'text/html'});
     res.end(data);
   });
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const url='http://127.0.0.1:'+server.address().port+'/';
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
   for(const [value,expected,provisional] of [[0,'none',false],[0.2,'possible',false],[2,'elevated',false],[4,'likely',false],[8,'extreme',false],[2.06,'possible',true]]){
     const page=await browser.newPage();
     const errors=[];
     page.on('pageerror',e=>errors.push(e.stack||e.message));
     let hits=0;
     await page.route('**/*lightning*.json*',async route=>{
       hits++;
       const now=new Date(Date.now()+3600000).toISOString();
       await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({
         model:'rrfs',cycle:new Date().toISOString(),status:'available',units_verified:!provisional,
         hours:[{time:now,value,units_verified:!provisional,native_index:provisional,source_cycle:new Date().toISOString()}]
       })});
     });
     await page.goto(url,{waitUntil:'domcontentloaded',timeout:30000});
     await page.waitForTimeout(5000);
     if(value===0){
       const chartReport=await page.evaluate(()=>{
         const avg=window.cuMainModelAverage||[],src=window.cuAverageSourceRows||{};
         const names=['gfs','nam','hrrr','rrfs','qualified','integrated'];
         const results=avg.slice(0,60).map(row=>{
           const values=names.map((name,i)=>{
             const r=(src[name]||[]).find(x=>String(x.time).slice(0,16)===String(row.time).slice(0,16));
             const v=Array.isArray(row.values)?row.values[i]:r?.forecastFeeders;
             return Number.isFinite(v)?v:null;
           });
           const present=values.filter(Number.isFinite);
           const calculated=present.length?present.reduce((a,b)=>a+b,0)/present.length:null;
           return {t:row.time,v:values,mean:row.forecastFeeders,n:row.modelCount,calculated,delta:calculated===null?null:row.forecastFeeders-calculated};
         });
         const evidence=window.cuLocalConvectiveShadeEvidence||{};
         return {canvas:document.getElementById('live-forecast-chart')?.width,averageCount:avg.length,sourceLengths:Object.fromEntries(names.map(n=>[n,(src[n]||[]).length])),coverage:window.cuSixCurveCoverage||null,shadeHours:Object.entries(evidence).map(([t,v])=>({t,dbz:v.maxDbz,models:v.models})).slice(0,36),sample:results.slice(0,18),mismatches:results.filter(x=>x.delta!==null&&Math.abs(x.delta)>0.001).slice(0,8),counts:results.reduce((o,x)=>(o[x.n]=(o[x.n]||0)+1,o),{})};
       });
       console.log('CU_CHART_AUDIT',JSON.stringify(chartReport));
     }
     const report=await page.evaluate(()=>{
       const text=document.body.innerText||'';
       const i=text.toLowerCase().indexOf('lightning');
       return {excerpt:i>=0?text.slice(Math.max(0,i-100),i+350):'',density:window.cuLightningDensityForecasts||[],provisional:window.cuLightningProvisionalForecasts||[],level:typeof window.cuHRRRLightningLevel==='function'?window.cuHRRRLightningLevel(window.cuLightningDensityForecasts?.[0]?.value):null,bridgeType:typeof window.cuRefreshLightningTile,lightningNodes:[...document.querySelectorAll('*')].filter(e=>e.children.length===0&&e.textContent.trim()==='Lightning').slice(0,3).map(e=>e.parentElement?.outerHTML.slice(0,1100)),updateType:typeof window.cuUpdateThreats};
     });
     console.log('LIGHTNING_BROWSER_CASE',JSON.stringify({value,expected,hits,errors:errors.slice(0,3),report}));
     if(errors.length)throw Error('Dashboard JavaScript runtime errors (first 3): '+errors.slice(0,3).join(' | '));
     if(hits===0)throw Error('Lightning JSON was never requested by dashboard');
     if(!report.density.length&&!report.provisional.length)throw Error('Lightning data did not enter global forecast state');
     if(!provisional&&report.level?.level!==expected)throw Error('Lightning classifier failed in browser: '+JSON.stringify(report.level));
     const visible=report.excerpt.match(/Lightning\s+([^\n]+)/i)?.[1]?.trim()||'';
     const expectedVisible={none:'BELOW THRESHOLD',possible:'POSSIBLE',elevated:'ELEVATED',likely:'LIKELY',extreme:'EXTREME'}[expected];
     if(!visible.toUpperCase().includes(expectedVisible))throw Error('Visible Lightning tile mismatch: expected '+expectedVisible+', got '+visible+'; browser errors: '+errors.join(' | '));
     await page.close();
   }
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exit(1)});
