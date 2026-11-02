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
   for(const [value,expected] of [[0,'none'],[0.2,'possible'],[2,'elevated'],[4,'likely'],[8,'extreme']]){
     const page=await browser.newPage();
     const errors=[];
     page.on('pageerror',e=>errors.push(e.message));
     let hits=0;
     await page.route('**/*lightning*.json*',async route=>{
       hits++;
       const now=new Date(Date.now()+3600000).toISOString();
       await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({
         model:'rrfs',cycle:new Date().toISOString(),status:'available',units_verified:true,
         hours:[{time:now,value,units_verified:true,source_cycle:new Date().toISOString()}]
       })});
     });
     await page.goto(url,{waitUntil:'domcontentloaded',timeout:30000});
     await page.waitForTimeout(5000);
     const report=await page.evaluate(()=>{
       const text=document.body.innerText||'';
       const i=text.toLowerCase().indexOf('lightning');
       return {excerpt:i>=0?text.slice(Math.max(0,i-100),i+350):'',density:window.cuLightningDensityForecasts||[],level:typeof window.cuHRRRLightningLevel==='function'?window.cuHRRRLightningLevel(window.cuLightningDensityForecasts?.[0]?.value):null,updateType:typeof window.cuUpdateThreats};
     });
     console.log('LIGHTNING_BROWSER_CASE',JSON.stringify({value,expected,hits,errors:errors.slice(0,3),report}));
     if(hits===0)throw Error('Lightning JSON was never requested by dashboard');
     if(!report.density.length)throw Error('Lightning data did not enter global forecast state');
     if(report.level?.level!==expected)throw Error('Lightning classifier failed in browser: '+JSON.stringify(report.level));
     await page.close();
   }
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exit(1)});
