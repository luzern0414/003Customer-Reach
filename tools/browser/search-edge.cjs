/** 中文网页检索兜底：一次启动临时无头Edge，经CDP让内置OpenCLI依次执行“websearch run”。
 * 用法：node search-edge.cjs <工作目录> <每条结果数> <检索词1> [检索词2 …]
 * 百度为主、被验证/无结果时改用搜狗；搜狗跳转链接解析为真实地址。输出JSON：{results:[{query,engine,rows,error}]}。
 */
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const ROOT=path.resolve(__dirname,'../..');
const CLI=path.join(ROOT,'vendor/opencli/dist/src/main.js');
const PLUGIN=path.join(ROOT,'src/opencli-plugin');
const [folder,rawLimit='8',...queries]=process.argv.slice(2);
const limit=Math.min(30,Math.max(1,Number(rawLimit)||8));
const UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0';
/** 子进程参数固定，只接受检索词；stdout为OpenCLI JSON，失败时返回错误码而不抛出。 */
function run(endpoint,engine,query){
  return new Promise(resolve=>{
    const child=spawn(process.execPath,[CLI,'websearch','run',engine,query,'--limit',String(limit),'-f','json'],
      {windowsHide:true,env:{...process.env,OPENCLI_CDP_ENDPOINT:endpoint,OPENCLI_PLUGIN_DIRS:PLUGIN,OPENCLI_BROWSER_CONNECT_TIMEOUT:'15',OPENCLI_BROWSER_COMMAND_TIMEOUT:'30',NO_COLOR:'1'}});
    let out='',err='';const timer=setTimeout(()=>child.kill(),60000);
    child.stdout.on('data',c=>{if(out.length<400000)out+=c});child.stderr.on('data',c=>{if(err.length<4000)err+=c});
    child.on('close',code=>{clearTimeout(timer);
      if(code!==0)return resolve({rows:[],error:/VERIFICATION_REQUIRED/.test(out+err)?'verification_required':/EMPTY_RESULT/.test(out+err)?'empty_results':'search_failed'});
      try{const text=out.trim();resolve({rows:text?JSON.parse(text.slice(text.search(/[\[{]/))):[],error:''})}catch{resolve({rows:[],error:'bad_output'})}});
  });
}
/** 搜狗跳转页含 URL='…' 或 location.replace("…")；只解析跳转目标，不访问目标页。 */
async function resolveRedirect(url){
  try{const res=await fetch(url,{redirect:'manual',signal:AbortSignal.timeout(8000),headers:{'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edg/130.0.0.0'}});
    if(res.headers.get('location'))return res.headers.get('location');
    const html=await res.text();const m=html.match(/URL='([^']+)'/)||html.match(/location\.replace\("([^"]+)"\)/);return m?m[1]:''}catch{return ''}
}
(async()=>{
  if(!folder||!queries.length)throw new Error('usage');
  fs.mkdirSync(folder,{recursive:true});
  const context=await chromium.launchPersistentContext(path.join(folder,'edge-profile'),{channel:'msedge',headless:true,locale:'zh-CN',
    // 无头Edge默认UA含HeadlessEdg，搜索引擎会直接给验证页；使用常规桌面UA，不做其他指纹伪装。
    userAgent:UA,args:['--remote-debugging-port=0','--no-first-run','--no-default-browser-check','--user-agent='+UA]});
  try{
    const portFile=path.join(folder,'edge-profile','DevToolsActivePort');
    for(let i=0;i<50&&!fs.existsSync(portFile);i++)await new Promise(r=>setTimeout(r,100));
    if(!fs.existsSync(portFile))throw new Error('edge_cdp_unavailable');
    const endpoint='http://127.0.0.1:'+fs.readFileSync(portFile,'utf8').split(/\r?\n/)[0];
    const results=[];
    for(const query of queries){
      let engine='baidu',res=await run(endpoint,engine,query);
      if(!res.rows.length){engine='sogou';const second=await run(endpoint,engine,query);if(second.rows.length||!res.error)res=second;else res={rows:[],error:res.error}}
      for(const row of res.rows)if(row.redirect){const real=await resolveRedirect(row.redirect);if(real&&/^https?:/.test(real))row.url=real}
      results.push({query,engine,rows:res.rows.filter(r=>!/sogou\.com\/link|baidu\.com\/link/.test(r.url)),error:res.error});
      await new Promise(r=>setTimeout(r,800));
    }
    process.stdout.write(JSON.stringify({results}));
  }finally{await context.close().catch(()=>{})}
})().catch(error=>{process.stderr.write(JSON.stringify({error:error.message}));process.exitCode=1});
