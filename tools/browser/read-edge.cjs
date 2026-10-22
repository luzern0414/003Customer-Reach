/** 固定的公开网页读取器：专用Edge实例；OpenCLI web/read经CDP，失败可回退Playwright。 */
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const dns=require('node:dns/promises');
const net=require('node:net');
const {spawn}=require('node:child_process');
const [requestedUrl,folder,preference='auto',rawLimit='40000']=process.argv.slice(2);
const limit=Math.min(100000,Math.max(2000,Number(rawLimit)||40000));
const hostCache=new Map();
let context;
/** 仅授权公网站点；主页面与重定向/子资源均拒绝回环、私网或凭据URL。 */
async function publicAddress(value){
  let u;try{u=new URL(value)}catch{return false}
  if(!['https:','http:'].includes(u.protocol)||u.username||u.password)return false;
  if(hostCache.has(u.hostname))return hostCache.get(u.hostname);
  let addresses;try{addresses=await dns.lookup(u.hostname,{all:true})}catch{return false}
  const safe=addresses.length>0&&addresses.every(({address})=>{
    if(net.isIP(address)===6)return !/^(::|fe[89ab]|f[cd]|2001:db8)/i.test(address)&&!address.startsWith('::ffff:');
    const p=address.split('.').map(Number);
    return p[0]!==0&&p[0]!==10&&p[0]!==127&&p[0]<224&&!(p[0]===169&&p[1]===254)&&!(p[0]===172&&p[1]>=16&&p[1]<=31)&&!(p[0]===192&&p[1]===168)&&!(p[0]===100&&p[1]>=64&&p[1]<=127);
  });hostCache.set(u.hostname,safe);return safe;
}
/** 子进程参数固定；正文从stdout读取，真实stderr仅用于本地诊断，不作为资料。 */
async function opencliRead(endpoint){
  const cli=path.join(__dirname,'../../vendor/opencli/dist/src/main.js');
  return await new Promise((resolve,reject)=>{
    const child=spawn(process.execPath,[cli,'web','read','--url',requestedUrl,'--stdout','--download-images','false','--frames','none','--wait','2','--output',path.join(folder,'article')],
      {windowsHide:true,env:{...process.env,OPENCLI_CDP_ENDPOINT:endpoint,OPENCLI_BROWSER_CONNECT_TIMEOUT:'15',OPENCLI_BROWSER_COMMAND_TIMEOUT:'30'}});
    let body='',error='',count=0;
    const timeout=setTimeout(()=>{child.kill();reject(new Error('opencli_timeout'))},65000);
    child.stdout.on('data',chunk=>{const s=chunk.toString();count+=s.length;if(body.length<limit)body+=s.slice(0,limit-body.length)});
    child.stderr.on('data',chunk=>{if(error.length<4000)error+=chunk.toString().slice(0,4000-error.length)});
    child.on('error',e=>{clearTimeout(timeout);reject(e)});
    child.on('close',code=>{clearTimeout(timeout);if(code!==0)reject(new Error('opencli_exit_'+code));else resolve({body,count})});
  });
}
(async()=>{
  if(!requestedUrl||!folder||!await publicAddress(requestedUrl))throw new Error('url_not_public');
  fs.mkdirSync(folder,{recursive:true});const started=Date.now();
  context=await chromium.launchPersistentContext(path.join(folder,'edge-profile'),{channel:'msedge',headless:true,
    args:['--remote-debugging-port=0','--no-first-run','--no-default-browser-check'],viewport:{width:1440,height:960}});
  await context.route('**/*',async route=>{if(await publicAddress(route.request().url()))await route.continue();else await route.abort('blockedbyclient')});
  let mainStatus=0;
  context.on('response',response=>{if(response.request().isNavigationRequest()&&response.request().resourceType()==='document')mainStatus=response.status()});
  const portFile=path.join(folder,'edge-profile','DevToolsActivePort');
  for(let i=0;i<30&&!fs.existsSync(portFile);i++)await new Promise(resolve=>setTimeout(resolve,100));
  let result,backend='opencli',fallbackReason='';
  if(preference!=='playwright'){
    try{
      if(!fs.existsSync(portFile))throw new Error('edge_cdp_unavailable');
      const port=fs.readFileSync(portFile,'utf8').split(/\r?\n/)[0];
      result=await opencliRead('http://127.0.0.1:'+port);
      if(result.body.length<150)throw new Error('empty_body');
    }catch(error){
      fallbackReason=error.message;
      if(preference==='opencli'||[401,403,429].includes(mainStatus))throw error;
    }
  }
  if(!result){
    backend='playwright';const page=await context.newPage();
    await page.goto(requestedUrl,{waitUntil:'domcontentloaded',timeout:30000});
    if([401,403,429].includes(mainStatus))throw new Error('site_access_restricted');
    await page.waitForTimeout(1200);
    const text=await page.locator('body').innerText({timeout:10000});
    result={body:text.slice(0,limit),count:text.length};
  }
  const pages=context.pages();const page=pages.find(p=>p.url().startsWith('http'))||pages[0];
  const url=page?.url()||requestedUrl;
  if(!await publicAddress(url))throw new Error('redirect_not_public');
  const title=page?await page.title():'';
  const screenshot=path.join(folder,'page.png');if(page)await page.screenshot({path:screenshot,fullPage:true,timeout:15000});
  fs.writeFileSync(path.join(folder,'body.txt'),result.body,'utf8');
  const payload={url,requested_url:requestedUrl,title,body:result.body,body_chars:result.body.length,total_chars:result.count,
    truncated:result.count>result.body.length,backend,opencli_version:require('../../vendor/opencli/package.json').version,
    screenshot,elapsed_ms:Date.now()-started,fallback_reason:fallbackReason,http_status:mainStatus};
  await context.close();context=null;process.stdout.write(JSON.stringify(payload));
})().catch(async error=>{if(context)await context.close().catch(()=>{});process.stderr.write(JSON.stringify({error:error.message}));process.exitCode=1});
