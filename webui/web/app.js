let mode = 'gen', files = [], maskFile = null;
let genAbort = null, genJobId = '', genBgNow = false, genBusy = false;
const $ = id => document.getElementById(id);
const MODEL_NOTES = {
  'gpt-image-2': '旗舰单模型，画质 low/medium/high',
  'gpt-image-2-2k': '固定 2K 分辨率输出',
  'gpt-image-2-4k': '固定 4K 分辨率输出',
  'gpt-image-2.5': 'Images 2.5 基础版',
  'gpt-image-2.5-flare': '速度优先（比 gpt-image-2 快 2~4 倍），日常首选',
  'gpt-image-2.5-flare-ad': 'Flare 广告变体，适合营销素材',
  'gpt-image-2.5-sunburst': '质量/改图精度优先，多轮编辑更稳，耗时更长',
  'gpt-image-2.5-sunburst-ad': 'Sunburst 广告变体',
  'gpt-image-2.5-ext-2k': '2.5 ext 变体，2K 输出',
  'gpt-image-2.5-ext-4k': '2.5 ext 变体，4K 输出',
  'gpt-image-2.5-flare-2k': 'Flare 高分辨率档（2K）',
  'gpt-image-2.5-flare-4k': 'Flare 高分辨率档（4K）',
  'gpt-image-2.5-sunburst-2k': 'Sunburst 高分辨率档（2K）',
  'gpt-image-2.5-sunburst-4k': 'Sunburst 高分辨率档（4K）',
  'gpt-image-2.6': '最新一代',
  'nano-banana-2.1-1k': 'Google Nano Banana 2.1，1K',
  'nano-banana-2.1-2k': 'Google Nano Banana 2.1，2K',
  'nano-banana-2.1-4k': 'Google Nano Banana 2.1，4K',
  'banana-pro-1k': 'Banana Pro，1K',
  'banana-pro-2k': 'Banana Pro，2K',
  'banana-pro-4k': 'Banana Pro，4K',
  'banana2-1k': 'Banana 2，1K',
  'banana2-2k': 'Banana 2，2K',
  'banana2-4k': 'Banana 2，4K',
  'gemini-3-pro-image-preview': 'Gemini 3 Pro 图像预览版',
  'gemini-3.1-flash-image-preview': 'Gemini 3.1 Flash 图像预览版（快）',
  'grok-imagine-image': 'Grok 图像生成',
  'grok-imagine-image-2.0': 'Grok Imagine 2.0',
  'grok-imagine-image-quality': 'Grok Imagine 高质量版',
  'grok-4.7-build-fast': 'Grok 4.7 快速构建版'
};
const MODEL_QUALITY_MAX = m => /2\.5|2\.6|2-4k/.test(m) ? 'max' : 'high';

(async function init(){
  const cfg = await (await fetch('/api/config')).json();
  $('groupSel').innerHTML = (cfg.groups||[]).map(g => `<option value="${g}">${g}</option>`).join('');
  $('groupSel').value = cfg.group || '';
  let m0 = savedOrDefault('model', cfg.model);
  if (!(cfg.models||[]).includes(m0)) m0 = cfg.model;
  if (!(cfg.models||[]).includes(m0)) m0 = (cfg.models||[])[0] || '';
  $('model').innerHTML = (cfg.models||[]).map(m => `<option value="${m}">${m}</option>`).join('');
  $('model').value = m0;
  const ratioMap = {};
  $('sizeRatio').innerHTML = `<option value="auto">auto（自动）</option>`
    + (cfg.size_groups || []).filter(g => g[0] !== '自动').map(g => {
      ratioMap[g[0]] = g[1].map(it => it[0]);
      return `<option value="${g[0]}">${g[0]}</option>`; }).join('')
    + `<option value="custom">自定义…</option>`;
  window.RATIO_MAP = ratioMap;
  $('sizeTier').innerHTML = ['1K','2K','4K'].map((t,i)=>`<option value="${i}">${t}</option>`).join('');
  $('n').innerHTML = Array.from({length:10},(_,i)=>`<option>${i+1}</option>`).join('');
  $('quality').innerHTML = cfg.qualities.map(q => `<option value="${q}">${q==='auto'?'auto（默认）':q}</option>`).join('');
  $('background').innerHTML = cfg.backgrounds.map(b => `<option value="${b}">${b==='auto'?'auto（默认）':b==='transparent'?'transparent（透明底）':'opaque（不透明）'}</option>`).join('');
  $('format').innerHTML = cfg.formats.map(f => `<option value="${f}">${f==='png'?'png（默认）':f}</option>`).join('');
  $('moderation').innerHTML = cfg.moderations.map(m => `<option value="${m}">${m==='auto'?'auto（默认）':m}</option>`).join('');

  // 恢复上次参数（浏览器本地记忆）
  try{
    const saved = JSON.parse(localStorage.getItem('gptImageParams') || '{}');
    if (saved.size && saved.sizeRatio === undefined){
      if (saved.size === 'auto'){ saved.sizeRatio = 'auto'; }
      else {
        for (const [r, vals] of Object.entries(window.RATIO_MAP || {})){
          const i = vals.indexOf(saved.size);
          if (i >= 0){ saved.sizeRatio = r; saved.sizeTier = String(i); break; }
        }
      }
    }
    ['model','sizeRatio','sizeTier','customSize','n','quality','background','format','moderation','prompt'].forEach(k=>{
      if (saved[k] !== undefined && $(k)) $(k).value = saved[k];
    });
    if (saved.comp !== undefined){ $('comp').value = saved.comp; }
  }catch(e){}

  $('model').value = savedOrDefault('model', cfg.model);
  onModelChange(); onSizeChange(); onFormatChange();
  loadHistory();
  refreshHistColl();
})();

function savedOrDefault(k, d){ try{ return JSON.parse(localStorage.getItem('gptImageParams')||'{}')[k] ?? d; }catch(e){ return d; } }

function setMode(m){
  mode = m;
  $('tabGen').classList.toggle('active', m==='gen');
  $('tabEdit').classList.toggle('active', m==='edit');
  $('editBox').style.display = m==='edit' ? '' : 'none';
  $('background').disabled = (m==='edit');
  $('background').parentElement && ($('background').title = m==='edit' ? '背景参数仅文生图支持' : '');
}

function modelSeries(m){
  m = (m || '').toLowerCase();
  if (m.startsWith('gpt-image')) return 'gpt';
  if (m.includes('banana') || m.includes('gemini')) return 'banana';
  return 'other';
}
function onModelChange(){
  const m = $('model').value;
  const s = modelSeries(m);
  const lite = s !== 'gpt';   // 非 gpt-image 系列：仅支持 尺寸/张数 等基础参数
  $('quality').disabled = lite;
  if (lite) $('quality').value = 'auto';
  $('outSect').style.display = lite ? 'none' : '';
  if (lite){ $('background').value = 'auto'; $('format').value = 'png'; $('moderation').value = 'auto'; }
  let note = MODEL_NOTES[m] || '';
  if (lite) note += (note ? '　' : '') + (s === 'banana'
    ? 'nano-banana / gemini 系列：仅支持尺寸、张数等基础参数（画质/背景/格式/审核不适用，已自动隐藏）'
    : '该系列：仅支持尺寸、张数等基础参数（画质/背景/格式/审核不适用，已自动隐藏）');
  $('modelHint').textContent = note;
}
function onSizeChange(){
  const r = $('sizeRatio').value;
  const custom = r === 'custom';
  $('customSizeBox').style.display = custom ? '' : 'none';
  $('sizeTier').style.display = (custom || r === 'auto') ? 'none' : '';
  $('sizeHint').textContent = custom
    ? '自定义尺寸需满足：宽高均为 16 的倍数、宽高比 1:3~3:1；最长边与总像素不限制，能否生效由上游模型决定'
    : '';
}
function onFormatChange(){
  const f = $('format').value;
  $('compBox').style.display = (f==='jpeg'||f==='webp') ? '' : 'none';
  if (f==='jpeg' && $('background').value==='transparent'){
    $('background').value = 'auto';
  }
}
$('comp').oninput = () => $('compVal').textContent = $('comp').value;
$('prompt').addEventListener('input', persistParams);
$('model').onchange = onModelChange;
$('sizeRatio').onchange = onSizeChange; $('sizeTier').onchange = onSizeChange;
$('format').onchange = onFormatChange;

function persistParams(){
  const p = { mode, model:$('model').value, sizeRatio:$('sizeRatio').value, sizeTier:$('sizeTier').value,
    customSize:$('customSize').value, n:$('n').value, quality:$('quality').value,
    background:$('background').value, format:$('format').value,
    moderation:$('moderation').value, comp:$('comp').value, prompt:$('prompt').value };
  localStorage.setItem('gptImageParams', JSON.stringify(p));
}

function renderThumbs(){
  $('thumbs').innerHTML = files.map((f,i)=>`<div class="thumb"><img src="${f.url}" onclick="lbShow(this.src)"><b onclick="files.splice(${i},1);renderThumbs()">×</b></div>`).join('');
}
function renderMask(){
  $('thumbMask').innerHTML = maskFile ? `<div class="thumb"><img src="${maskFile.url}" onclick="lbShow(this.src)"><b onclick="maskFile=null;renderMask()">×</b></div>` : '';
}
function lbShow(u){ $('lbImg').src = u; $('lb').style.display='flex'; }

/* ---------- 隐私遮罩 ---------- */
let maskOn = localStorage.getItem('gptImageMask') === '1';
function syncMaskBtn(){
  [$('maskToggle'), $('maskToggleMg')].filter(Boolean).forEach(b => {
    b.textContent = '遮罩：' + (maskOn ? '开' : '关');
    b.classList.toggle('on', maskOn);
  });
}
function toggleMask(){
  maskOn = !maskOn;
  localStorage.setItem('gptImageMask', maskOn ? '1' : '0');
  document.body.classList.toggle('masked', maskOn);
  document.querySelectorAll('img[data-full]')
    .forEach(i => i.classList.toggle('masked', maskOn));
  syncMaskBtn();
}
syncMaskBtn();
if (maskOn) document.body.classList.add('masked');
const drop = $('drop'), fileInput = $('file');
drop.onclick = () => fileInput.click();
drop.ondragover = e => { e.preventDefault(); drop.classList.add('on'); };
drop.ondragleave = () => drop.classList.remove('on');
drop.ondrop = e => { e.preventDefault(); drop.classList.remove('on'); addFiles(e.dataTransfer.files); };
fileInput.onchange = () => { addFiles(fileInput.files); fileInput.value=''; };
function addFiles(list){
  for (const f of list){
    if (files.length >= 16) break;
    files.push({ name:f.name, mime:f.type||'image/png', url:URL.createObjectURL(f), file:f });
  }
  renderThumbs();
}
async function addAsInput(url, name){
  if (files.length >= 16){ alert('输入图片已达上限（16 张）'); return; }
  try{
    const blob = await (await fetch(url)).blob();
    const ext = (blob.type.split('/')[1] || 'png').replace('jpeg', 'jpg');
    const f = new File([blob], name || ('input.' + ext), { type: blob.type || 'image/png' });
    files.push({ name:f.name, mime:f.type, url:URL.createObjectURL(f), file:f });
    if (mode !== 'edit') setMode('edit');
    persistParams(); renderThumbs();
  }catch(e){ alert('引用失败：' + e); }
}
function revealImage(name){
  fetch('/api/reveal?name=' + encodeURIComponent(name)).then(r => r.json()).then(j => {
    if (j.error) alert('本地查看失败：' + j.error);
  }).catch(e => alert('本地查看失败：' + e));
}
const dropMask = $('dropMask'), fileMask = $('fileMask');
dropMask.onclick = () => fileMask.click();
fileMask.onchange = () => {
  const f = fileMask.files[0];
  if (f){ maskFile = { name:f.name, mime:f.type||'image/png', url:URL.createObjectURL(f), file:f }; }
  fileMask.value = '';
  renderMask();
};

// ---------------- 蒙版绘制（点击“绘制蒙版”按钮） ----------------
let mBase = null, mStroke = null, mCtx = null, sCtx = null, mPainting = false;
function openMaskEditor(){
  if (!files.length){ alert('请先上传至少一张原图，再绘制蒙版'); return; }
  const img = new Image();
  img.onload = () => {
    const cv = $('maskCv'), w = img.naturalWidth, h = img.naturalHeight;
    cv.width = w; cv.height = h;
    mBase = document.createElement('canvas'); mBase.width = w; mBase.height = h;
    mBase.getContext('2d').drawImage(img, 0, 0);
    mStroke = document.createElement('canvas'); mStroke.width = w; mStroke.height = h;
    sCtx = mStroke.getContext('2d');
    sCtx.strokeStyle = '#ff4040'; sCtx.lineCap = 'round'; sCtx.lineJoin = 'round';
    mCtx = cv.getContext('2d');
    redrawMask();
    $('maskModal').style.display = 'flex';
  };
  img.src = files[0].url;
}
function redrawMask(){
  if (!mCtx) return;
  const cv = $('maskCv');
  mCtx.clearRect(0, 0, cv.width, cv.height);
  mCtx.drawImage(mBase, 0, 0);
  mCtx.globalAlpha = 0.55; mCtx.drawImage(mStroke, 0, 0); mCtx.globalAlpha = 1;
}
function maskPos(e){
  const cv = $('maskCv'), r = cv.getBoundingClientRect();
  return { x:(e.clientX - r.left) * cv.width / r.width,
           y:(e.clientY - r.top) * cv.height / r.height };
}
$('maskCv').addEventListener('pointerdown', e => {
  if (!sCtx) return;
  mPainting = true;
  const p = maskPos(e);
  sCtx.lineWidth = +$('brushSize').value;
  sCtx.beginPath(); sCtx.moveTo(p.x, p.y); sCtx.lineTo(p.x + 0.01, p.y); sCtx.stroke();
  redrawMask();
});
$('maskCv').addEventListener('pointermove', e => {
  if (!mPainting || !sCtx) return;
  const p = maskPos(e);
  sCtx.lineWidth = +$('brushSize').value;
  sCtx.lineTo(p.x, p.y); sCtx.stroke();
  redrawMask();
});
window.addEventListener('pointerup', () => mPainting = false);
$('brushSize').oninput = () => $('brushVal').textContent = $('brushSize').value;
function clearMaskCanvas(){
  if (!sCtx) return;
  sCtx.clearRect(0, 0, mStroke.width, mStroke.height);
  redrawMask();
}
function closeMaskEditor(){ $('maskModal').style.display = 'none'; }
function saveMaskEditor(){
  if (!mStroke){ closeMaskEditor(); return; }
  const out = document.createElement('canvas');
  out.width = mStroke.width; out.height = mStroke.height;
  const octx = out.getContext('2d');
  octx.fillStyle = '#000'; octx.fillRect(0, 0, out.width, out.height);
  octx.globalCompositeOperation = 'destination-out';
  octx.drawImage(mStroke, 0, 0);
  out.toBlob(b => {
    const f = new File([b], 'mask-drawn.png', { type:'image/png' });
    if (maskFile && maskFile.url && maskFile.url.startsWith('blob:')) URL.revokeObjectURL(maskFile.url);
    maskFile = { name:'mask-drawn.png', mime:'image/png', url:URL.createObjectURL(f), file:f };
    renderMask();
    closeMaskEditor();
  }, 'image/png');
}

async function fileToB64(f){
  return new Promise((res, rej) => { const r = new FileReader();
    r.onload = () => res(r.result.split(',')[1]); r.onerror = rej; r.readAsDataURL(f); });
}

function currentSize(){
  const r = $('sizeRatio').value;
  if (r === 'auto') return 'auto';
  if (r === 'custom'){
    const v = ($('customSize').value || '').trim().toLowerCase();
    return v || 'auto';
  }
  const vals = (window.RATIO_MAP || {})[r] || [];
  return vals[+($('sizeTier').value || 0)] || 'auto';
}

let bgPollTimer = null;
function toBackground(){
  // 通知服务端进入后台面板，再断开前端 fetch（AbortController 只影响浏览器等待，服务端任务继续）
  genBgNow = true;
  if (genJobId) fetch('/api/jobs/background', { method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({job_id: genJobId}) }).catch(()=>{});
  if (genAbort) genAbort.abort();
  $('go').disabled = false; $('go').textContent = '生成（约 60~90 秒 / 张）';
  $('toBgBtn').style.display = 'none';
  $('status').className = 'status';
  $('status').textContent = '任务已转入后台：' + (genJobId||'');
  toggleJobsPanel(true); refreshJobs();
}
function toggleJobsPanel(show){
  $('jobsPanel').style.display = show ? '' : 'none';
  if (show) refreshJobs();
  if (bgPollTimer){ clearInterval(bgPollTimer); bgPollTimer = null; }
  if (show) bgPollTimer = setInterval(refreshJobs, 3000);
}
async function refreshJobs(force){
  try{
    const j = await (await fetch('/api/jobs', {cache:'no-store'})).json();
    const jobs = j.jobs || [];
    let running = 0;
    $('jobsList').innerHTML = jobs.map(t => {
      const stMap = {running:['run','进行中'], done:['ok','已完成'], failed:['fail','失败'], cancelled:['can','已中止']};
      const isDl = t.status === 'running' && t.phase === 'downloading';
      const [cls, label] = isDl ? ['dl', '下载中…'] : (stMap[t.status] || ['can', t.status]);
      if (t.status === 'running') running++;
      const tstr = t.status === 'running'
        ? '已等 ' + Math.round((Date.now()/1000 - t.t0)) + ' 秒'
        : (t.elapsed || 0) + ' 秒';
      const imgs = (t.images||[]).length ? `，${t.images.length} 张已入库` : '';
      const err = t.error ? `，${t.error.slice(0,60)}` : '';
      return `<div class="jobItem">
        <div class="jTop">
          <span class="${cls}">● ${label}</span>
          <span class="jid">${t.id}</span>
          ${t.status==='failed' ? `<a class="retry" href="javascript:void(0)" onclick="retryJob('${t.id}')" title="用原参数重新生成">重试</a>` : ''}
          <a class="del" href="javascript:void(0)" onclick="jobX('${t.id}','${t.status}')" title="${t.status==='running'?'中止任务':'从列表移除'}">✕</a>
        </div>
        <div class="jMid">${t.mode==='edit'?'改图':'文生图'} · ${t.model} · ${t.size} · ${tstr}${imgs}</div>
        ${t.error ? `<div class="jErr">${t.error.slice(0,80)}</div>` : ''}
        <div class="jSub">${t.pshow||''}</div>
      </div>`;
    }).join('') || '<div class="jobItem" style="color:var(--muted)">暂无任务</div>';
    $('jobsRun').textContent = running;
    // 有新完成任务时刷一次历史（修复：原条件写反，恰在新完成时跳过；seenDone 未声明抛错被吞）
    window.seenDone = window.seenDone || {};
    const hasNew = jobs.some(t => t.status==='done' && !window.seenDone[t.id]);
    if (running === 0 && hasNew) loadHistory();
    jobs.forEach(t => { if (t.status==='done') window.seenDone[t.id] = 1; });
    if (running === 0 && bgPollTimer){ clearInterval(bgPollTimer); bgPollTimer = null; }
  }catch(e){ /* 面板静默 */ }
}
function refreshJobsNow(){ refreshJobs(true); loadHistory(); }  // 面板「刷新」：任务列表 + 历史一起刷新
async function clearJobs(){
  await fetch('/api/jobs/clear', { method:'POST' });
  refreshJobs();
}
async function cancelJob(jid){
  await fetch('/api/cancel', { method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({job_id: jid}) });
  refreshJobs();
  setTimeout(refreshJobs, 800);  // 服务端感知断开需要片刻，补刷一次
  setTimeout(refreshJobs, 2500);
}
async function retryJob(jid){
  const r = await (await fetch('/api/jobs/retry', { method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({job_id: jid}) })).json();
  if (r.error){ alert('重试失败：' + r.error); return; }
  refreshJobs();
}
function jobX(jid, status){
  if (status === 'running'){ cancelJob(jid); return; }
  // 已结束的任务：从列表移除
  fetch('/api/jobs/delete', { method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({job_id: jid}) })
    .then(() => refreshJobs()).catch(() => {});
}
function stopGenerate(){
  if (genJobId){
    fetch('/api/cancel', { method:'POST',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify({job_id: genJobId}) }).catch(()=>{});
  }
  if (genAbort) genAbort.abort();
}

async function generate(){
  if (genAbort){ stopGenerate(); return; }
  if (genBusy) return;   // 参数准备中（改图需编码大图），防快速连点重复提交
  genBusy = true;
  try {   // 包住全流程：任何路径结束（校验早退/中止/完成）都解除互斥
  const prompt = $('prompt').value.trim();
  const st = $('status');
  st.className = 'status'; st.textContent = '';
  if (!prompt){ st.className='status err'; st.textContent='请先填写提示词'; return; }
  if (mode==='edit' && !files.length){ st.className='status err'; st.textContent='改图模式请先上传至少一张图片'; return; }
  const size = currentSize();
  if (size !== 'auto' && !/^\d{1,5}x\d{1,5}$/.test(size) && !['1024x1024','1024x1536','1536x1024','2048x1152','3840x2160'].includes(size)){
    st.className='status err'; st.textContent='自定义尺寸格式应为 WxH，例如 2048x1152'; return; }

  persistParams();
  const payload = {
    mode, prompt,
    model: $('model').value,
    size,
    n: +$('n').value,
    quality: $('quality').value,
    background: (mode==='gen' && $('background').value) || '',
    output_format: $('format').value,
    output_compression: +$('comp').value,
    moderation: $('moderation').value,
    images: [], mask: null
  };
  if (mode==='edit'){
    for (const f of files) payload.images.push({ name:f.name, mime:f.mime, data:await fileToB64(f.file) });
    if (maskFile) payload.mask = { name:maskFile.name, mime:maskFile.mime, data:await fileToB64(maskFile.file) };
  }

  genAbort = new AbortController();
  genJobId = 'job-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
  payload.job_id = genJobId;
  $('go').textContent = '中止生成';
  $('toBgBtn').style.display = '';
  st.textContent = '正在请求中，再次点击按钮可中止本次请求……';
  const t0 = Date.now();
  const timer = setInterval(() => { st.textContent = `正在请求中，已等待 ${((Date.now()-t0)/1000).toFixed(0)} 秒……`; }, 1000);
  try{
    const r = await fetch('/api/generate', { method:'POST',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload), signal: genAbort.signal });
    const j = await r.json();
    clearInterval(timer);
    if (j.error){ st.className='status err';
      st.textContent = '生成失败：' + j.error + (j.detail ? '\n' + j.detail : ''); return; }
    st.textContent = `完成 · ${j.model} · ${j.size} · 耗时 ${j.elapsed}s` + (j.usage ? ` · 用量 ${JSON.stringify(j.usage)}` : '');
    $('results').innerHTML = j.images.map(im => card(im)).join('');
    bindCard(); loadHistory();
  }catch(e){
    clearInterval(timer);
    if (e && e.name === 'AbortError'){ st.className='status';
      st.textContent = genBgNow ? '任务已转入后台，进度见右侧面板' : '已中止本次请求'; }
    else { st.className='status err'; st.textContent = '请求异常：' + e + '（服务是否还在运行？）'; }
  }finally{ $('go').disabled = false; $('go').textContent = '生成（约 60~90 秒 / 张）'; genAbort = null;
    $('toBgBtn').style.display = 'none';
    if (genBgNow){ toggleJobsPanel(true); } else { refreshJobs(); }
    genBgNow = false; }
  } finally { genBusy = false; }
}

function card(im){
  const kb = im.size ? (im.size/1024).toFixed(0)+' KB' : '';
  return `<div class="card${im.fav?' fav':''}" data-name="${im.name||''}">
    <img src="${im.url}" data-full="${im.url}" loading="lazy">
    <div class="meta"><span>${im.name||''}</span><span><span class="dims">…</span>${kb?' · '+kb:''}</span></div>
    <div class="ops"><a href="javascript:void(0)" onclick="toggleFav('${im.name||''}')">${im.fav?'取消收藏':'收藏'}</a>
    <a href="javascript:void(0)" onclick="renameImage('${im.name||''}')">重命名</a>
    <a href="javascript:void(0)" onclick="addAsInput('${im.url}','${im.name||''}')">引用</a>
    <a href="${im.url}" download="${im.name||'image'}">下载</a>
    <a href="javascript:void(0)" onclick="revealImage('${im.name||''}')">本地查看</a></div></div>`;
}
function bindCard(){
  document.querySelectorAll('img[data-full]').forEach(img=>{
    if (maskOn) img.classList.add('masked');
    if (img.classList.contains('mgThumb')){
      img.onclick = () => { if (maskOn) img.classList.toggle('masked'); };
      img.ondblclick = () => { $('lbImg').src = img.dataset.full; $('lb').style.display='flex'; };
    } else {
      img.onclick = () => {
        if (maskOn){ img.classList.toggle('masked'); return; }
        $('lbImg').src = img.dataset.full; $('lb').style.display='flex';
      };
      img.ondblclick = () => { $('lbImg').src = img.dataset.full; $('lb').style.display='flex'; };
    }
    const dims = img.parentElement.querySelector('.dims');
    if (dims){
      const set = () => { if (img.naturalWidth) dims.textContent = img.naturalWidth + '×' + img.naturalHeight; };
      if (img.complete && img.naturalWidth) set(); else img.addEventListener('load', set);
    }
  });
}

let favOnly = false;
async function loadHistory(){
  try{
    const params = [];
    if (favOnly) params.push('fav=1');
    const cid = $('histColl') ? $('histColl').value : '';
    if (cid) params.push('cid=' + encodeURIComponent(cid));
    const items = await (await fetch('/api/history' + (params.length ? '?' + params.join('&') : ''))).json();
    if (items.error){ $('history').innerHTML = '<div class="empty">' + items.error + '</div>'; return; }
    $('history').innerHTML = items.length
      ? items.map(im => card(im)).join('')
      : `<div class="empty">${favOnly ? '收藏夹为空' : '暂无历史记录'}</div>`;
    bindCard();
  }catch(e){ $('history').innerHTML = '<div class="empty">历史加载失败</div>'; }
}
function toggleFavOnly(){
  favOnly = !favOnly;
  $('favOnlyBtn').classList.toggle('on', favOnly);
  loadHistory();
}

function post(url, body){
  return fetch(url, { method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body) }).then(r => r.json());
}
function toggleFav(name){
  const first = document.querySelector('.card[data-name="' + CSS.escape(name) + '"]');
  post('/api/fav', { name, fav: !(first && first.classList.contains('fav')) }).then(j => {
    if (j.error) return alert('收藏失败：' + j.error);
    document.querySelectorAll('.card[data-name="' + CSS.escape(name) + '"]').forEach(el => {
      el.classList.toggle('fav', j.fav);
      const a = [...el.querySelectorAll('a')].find(x => x.textContent === '收藏' || x.textContent === '取消收藏');
      if (a) a.textContent = j.fav ? '取消收藏' : '收藏';
    });
    if (mgViewVisible()) mgRender();
  }).catch(e => alert('收藏失败：' + e));
}
function renameImage(name){
  const to = prompt('重命名为（需带图片扩展名，如 my-asset.png）：', name);
  if (!to || to === name) return;
  post('/api/rename', { name, to }).then(j => {
    if (j.error) return alert('重命名失败：' + j.error);
    document.querySelectorAll('.card[data-name="' + CSS.escape(name) + '"]').forEach(el => {
      el.dataset.name = j.name;
      el.querySelector('.meta span').textContent = j.name;
      const img = el.querySelector('img');
      img.src = j.url; img.dataset.full = j.url;
      const dl = el.querySelector('a[download]');
      dl.href = j.url; dl.setAttribute('download', j.name);
      el.querySelectorAll('a[onclick]').forEach(a => {
        a.setAttribute('onclick', (a.getAttribute('onclick')||'').split(name).join(j.name));
      });
    });
    loadHistory();
  }).catch(e => alert('重命名失败：' + e));
}


/* ---------- 中转站分组管理 ---------- */
let editGroups = [], editActive = '', gi = 0;
function closeSettings(){ $('settingsModal').style.display = 'none'; }
async function openSettings(){
  try{
    const s = await (await fetch('/api/groups')).json();
    editGroups = (s.groups||[]).map(g => ({ name:g.name, base_url:g.base_url, api_key:'',
      has_key:g.has_key, key_masked:g.key_masked, models:(g.models||[]).slice(), proxy:g.proxy||'' }));
    editActive = s.active || '';
    gi = Math.max(0, editGroups.findIndex(g => g.name === editActive));
    renderGroupEditor();
  }catch(e){ alert('读取分组失败：' + e); }
  $('settingsModal').style.display = 'flex';
}
function renderGroupEditor(){
  $('setGroup').innerHTML = editGroups.map((g,i) =>
    `<option value="${i}">${g.name}${g.name===editActive?'（当前）':''}</option>`).join('');
  $('setGroup').value = gi;
  const g = editGroups[gi] || {};
  $('grpName').value = g.name || '';
  $('grpUrl').value = g.base_url || '';
  $('grpKey').value = '';
  $('keyMasked').textContent = g.has_key ? `（已存 ${g.key_masked}，留空不改）` : '（未设置密钥）';
  $('grpProxy').value = g.proxy || '';
  $('grpModels').value = (g.models || []).join('\n');
  $('setStatus').textContent = '';
}
function collectEditor(){
  const g = editGroups[gi];
  if (!g) return;
  g.name = $('grpName').value.trim();
  g.base_url = $('grpUrl').value.trim();
  const k = $('grpKey').value.trim();
  if (k){ g.api_key = k; g.has_key = true; g.key_masked = k.slice(0,6) + '****' + k.slice(-4); }
  g.proxy = $('grpProxy').value.trim();
  g.models = $('grpModels').value.split('\n').map(s => s.trim()).filter(Boolean);
}
function onSetGroupChange(){
  collectEditor();   // 先把当前组输入框里未保存的编辑收进 editGroups
  gi = parseInt($('setGroup').value, 10) || 0;
  renderGroupEditor();
}
function newGroup(){
  collectEditor();
  editGroups.push({ name:'新分组' + (editGroups.length+1), base_url:'', api_key:'',
    has_key:false, key_masked:'', models:[], proxy:'' });
  gi = editGroups.length - 1;
  renderGroupEditor();
}
function delGroup(){
  if (editGroups.length <= 1){ setErr('至少保留一个分组'); return; }
  if (!confirm(`删除分组「${editGroups[gi].name}」？（不会删除任何图片）`)) return;
  editGroups.splice(gi, 1);
  gi = Math.min(gi, editGroups.length - 1);
  renderGroupEditor();
}
function setErr(msg){ $('setStatus').className='status err'; $('setStatus').textContent = msg; }
async function fetchModels(){
  collectEditor();
  const g = editGroups[gi];
  if (!g.base_url){ setErr('请先填写中转站地址'); return; }
  $('setStatus').className='status'; $('setStatus').textContent = '正在拉取模型列表……';
  const j = await post('/api/models', { name: g.name, base_url: g.base_url,
    api_key: g.api_key, proxy: g.proxy });
  if (j.error){ setErr('拉取失败：' + j.error); return; }
  g.models = j.models;
  $('grpModels').value = j.models.join('\n');
  $('setStatus').textContent = `已拉取 ${j.models.length} 个模型（尚未保存，请点「保存全部分组」）`;
}
async function saveAllGroups(silent){
  collectEditor();
  for (const g of editGroups){
    if (!g.name){ if(!silent) setErr('分组名称不能为空'); return null; }
    if (!g.base_url.startsWith('http')){ if(!silent) setErr(`分组「${g.name}」地址需以 http(s):// 开头`); return null; }
    if (!g.has_key && !g.api_key){ if(!silent) setErr(`分组「${g.name}」未填写密钥`); return null; }
  }
  const j = await post('/api/groups', { groups: editGroups });
  if (j.error){ if(!silent) setErr('保存失败：' + j.error); return null; }
  editActive = j.active;
  await refreshHeader();
  if (!silent){
    $('setStatus').className='status'; $('setStatus').textContent = '已保存 ✓';
    renderGroupEditor();
  }
  return j;
}
async function useGroup(){
  const saved = await saveAllGroups(true);
  if (!saved) return;
  const j = await post('/api/group/switch', { name: editGroups[gi].name });
  if (j.error){ setErr('切换失败：' + j.error); return; }
  editActive = j.group;
  await refreshHeader();
  applyModels(j.models, j.model);
  $('setStatus').className='status'; $('setStatus').textContent = `已切换到「${j.group}」✓`;
  setTimeout(closeSettings, 700);
}
async function switchGroupHeader(){
  const name = $('groupSel').value;
  const j = await post('/api/group/switch', { name });
  if (j.error){ alert('切换失败：' + j.error); await refreshHeader(); return; }
  applyModels(j.models, j.model);
}
async function refreshHeader(){
  try{
    const s = await (await fetch('/api/groups')).json();
    $('groupSel').innerHTML = (s.groups||[]).map(g => `<option value="${g.name}">${g.name}</option>`).join('');
    $('groupSel').value = s.active || '';
  }catch(e){}
}
function applyModels(models, model){
  const list = models || [];
  $('model').innerHTML = list.map(m => `<option value="${m}">${m}</option>`).join('');
  $('model').value = list.includes(model) ? model : (list[0] || '');
  onModelChange();
}


/* ==================== 作品管理（收藏夹） ==================== */
let mgOpenId = null;
let mgLayout = localStorage.getItem('mgLayout') || 'list';
let mgPicking = false;
let mgSel = new Set();
let mgDataCache = null;       // 当前打开的收藏夹 id；null = 列表视图
function mgViewVisible(){ return $('mgView') && $('mgView').style.display !== 'none'; }

function showView(v){
  document.body.classList.toggle('mgmode', v === 'mg');
  $('wsView').style.display = v === 'ws' ? '' : 'none';
  $('mgView').style.display = v === 'mg' ? '' : 'none';
  if (v === 'mg') mgRender();
}

async function mgData(){
  return (await (await fetch('/api/collections')).json());
}
async function refreshHistColl(){
  try{
    const s = await mgData();
    const sel = $('histColl');
    const cur = sel.value;
    sel.innerHTML = '<option value="">全部（不筛选）</option>'
      + (s.collections || []).map(c => `<option value="${c.id}">${c.name}${c.is_default ? '（默认）' : ''}</option>`).join('');
    sel.value = (s.collections || []).some(c => c.id === cur) ? cur : '';
  }catch(e){ /* 静默 */ }
}

async function mgRender(){
  const s = await mgData();
  mgDataCache = s;
  if (s.error){ $('mgSide').innerHTML = '<div class="empty">' + s.error + '</div>';
                $('mgMain').innerHTML = ''; return; }
  if (mgOpenId && !(s.collections || []).some(c => c.id === mgOpenId)) mgOpenId = null;
  mgRenderSide(s);
  await mgRenderMain(s);
}

function mgEsc(s){
  return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;')
                  .replace(/'/g, "\\'").replace(/</g, '&lt;');
}

function mgRenderSide(s){
  const cols = s.collections || [];
  const def = cols.find(c => c.is_default);
  const rest = cols.filter(c => !c.is_default);
  const item = c => `
    <div class="mgSideItem${c.id === mgOpenId ? ' sel' : ''}" onclick="mgOpen('${c.id}')">
      <div class="mgSideTop">
        <span class="mgSideName">${c.is_default ? '⭐' : '📁'} ${c.name}${c.is_default ? '<em>默认</em>' : ''}</span>
        <span class="mgSideCount">${c.count}</span>
      </div>
      <div class="mgSideOps">
        <a title="重命名" href="javascript:void(0)" onclick="event.stopPropagation();mgRename('${c.id}','${mgEsc(c.name)}')">✎ 重命名</a>
        <a title="导出" href="javascript:void(0)" onclick="event.stopPropagation();mgExport('${c.id}')">⬇ 导出</a>
        ${c.is_default ? '' : `<a title="删除" href="javascript:void(0)" class="mgDel" onclick="event.stopPropagation();mgDelete('${c.id}','${mgEsc(c.name)}')">✕ 删除</a>`}
      </div>
    </div>`;
  $('mgSide').innerHTML = `
    <div class="mgSideBtns">
      <button onclick="mgCreate()">＋ 新建合集</button>
      <button onclick="mgImportZip()">导入包</button>
      <button onclick="mgExport('all')">导出全部</button>
    </div>
    <div class="mgSideList">
      ${def ? item(def) + '<div class="mgSideLabel">合集</div>' + (rest.map(item).join('') || '<div class="empty mgSideEmpty">还没有合集</div>') : '<div class="empty">还没有收藏夹</div>'}
    </div>`;
}

async function mgRenderMain(s){
  const c = (s.collections || []).find(x => x.id === mgOpenId);
  if (!c){
    $('mgMain').innerHTML = '<div class="empty">← 从左侧选择一个收藏夹，或点「＋ 新建合集」创建</div>';
    return;
  }
  if (mgPicking) return mgRenderPicker(s, c);
  const items = await (await fetch('/api/history?cid=' + encodeURIComponent(c.id))).json();
  const imgs = items.error ? [] : items;
  $('mgMain').innerHTML = `
    <div class="mgDetailHead">
      <span class="mgName">${c.is_default ? '⭐' : '📁'} ${c.name}${c.is_default ? ' <em>默认</em>' : ''} · ${imgs.length} 张</span>
      <div class="mgBtns">
        ${mgLayBtnHtml()}
        <button onclick="mgImportImages('${c.id}')">导入图片</button>
        <button onclick="mgStartPicker('${c.id}')">从历史添加</button>
      </div>
    </div>
    ${mgRenderImgs(imgs, c.id, false)}`;
  bindCard();
}

function mgLayBtnHtml(){
  return `<button title="${mgLayout === 'list' ? '切换为平铺' : '切换为列表'}" onclick="mgToggleLayout()">${mgLayout === 'list' ? '⊞ 平铺' : '☰ 列表'}</button>`;
}

function mgRenderImgs(imgs, cid, pick){
  const emptyTxt = pick ? '没有可添加的图片' : '收藏夹是空的：用「导入图片」或「从历史添加」加入素材';
  const kb = im => im.size ? ' · ' + (im.size/1024).toFixed(0) + ' KB' : '';
  if (mgLayout === 'grid'){
    const body = imgs.map(im => {
      const sel = mgSel.has(im.name);
      return `
      <div class="card${pick ? ' pick' : ''}${pick && sel ? ' picksel' : ''}" data-name="${im.name}">
        <img class="mgThumb" src="${im.url}" data-full="${im.url}" loading="lazy" title="双击放大预览">
        <div class="meta"><span>${im.name}</span><span><span class="dims">…</span>${kb(im)}</span></div>
        ${pick ? `<div class="ops">
          <a href="javascript:void(0)" class="mgPickAct${sel ? ' on' : ''}" onclick="mgToggleSel('${im.name}')">${sel ? '✓ 已选' : '选择'}</a>
        </div>` : `<div class="ops">
          <a href="${im.url}" download="${im.name}">下载</a>
          <a href="javascript:void(0)" class="mgDel" onclick="mgRemoveItem('${cid}','${im.name}')">移出</a>
        </div>`}
      </div>`;}).join('');
    return `<div class="grid mgGrid">${body || '<div class="empty">' + emptyTxt + '</div>'}</div>`;
  }
  const body = imgs.map(im => {
    const sel = mgSel.has(im.name);
    return `
    <div class="mgRow${pick ? ' pick' : ''}${pick && sel ? ' picksel' : ''}" data-name="${im.name}">
      <img class="mgThumb" src="${im.url}" data-full="${im.url}" loading="lazy" title="双击放大预览">
      <span class="mgRowName">${im.name}</span>
      ${pick ? `<span class="mgPickZone${sel ? ' on' : ''}" onclick="mgToggleSel('${im.name}')">${sel ? '✓ 已选' : '选择'}</span>`
        : `<span class="mgRowInfo"><span class="dims">…</span>${kb(im)}</span>
      <span class="mgRowOps">
        <a href="${im.url}" download="${im.name}">下载</a>
        <a href="javascript:void(0)" class="mgDel" onclick="mgRemoveItem('${cid}','${im.name}')">移出</a>
      </span>`}
    </div>`;}).join('');
  return `<div class="mgList">${body || '<div class="empty">' + emptyTxt + '</div>'}</div>`;
}

function mgToggleLayout(){
  mgLayout = mgLayout === 'list' ? 'grid' : 'list';
  localStorage.setItem('mgLayout', mgLayout);
  mgRenderMain(mgDataCache);
}

async function mgStartPicker(cid){
  mgPicking = true;
  mgSel = new Set();
  const s = await mgData();
  mgDataCache = s;
  mgRenderMain(s);
}

async function mgRenderPicker(s, c){
  const all = await (await fetch('/api/history')).json();
  const inCol = await (await fetch('/api/history?cid=' + encodeURIComponent(c.id))).json();
  const inSet = new Set((inCol.error ? [] : inCol).map(x => x.name));
  const imgs = (all.error ? [] : all).filter(im => !inSet.has(im.name));
  $('mgMain').innerHTML = `
    <div class="mgDetailHead">
      <span class="mgName">从历史添加到「${c.name}」· 已选 ${mgSel.size} 张</span>
      <div class="mgBtns">
        ${mgLayBtnHtml()}
        <button onclick="mgPickCancel()">返回</button>
        <button id="mgPickAdd" onclick="mgPickAdd('${c.id}')">添加所选（${mgSel.size}）</button>
      </div>
    </div>
    ${imgs.length ? mgRenderImgs(imgs, c.id, true) : '<div class="empty">没有可添加的图片（其余已在合集中）</div>'}`;
  bindCard();
}

function mgToggleSel(name){
  if (mgSel.has(name)) mgSel.delete(name); else mgSel.add(name);
  const on = mgSel.has(name);
  const row = [...document.querySelectorAll('#mgMain .mgRow[data-name],#mgMain .card[data-name]')]
    .find(r => r.dataset.name === name);
  if (row){
    row.classList.toggle('picksel', on);
    const act = row.querySelector('.mgPickAct, .mgPickZone');
    if (act){ act.textContent = on ? '✓ 已选' : '选择'; act.classList.toggle('on', on); }
  }
  const btn = $('mgPickAdd');
  if (btn) btn.textContent = `添加所选（${mgSel.size}）`;
  const head = document.querySelector('#mgMain .mgDetailHead .mgName');
  if (head) head.textContent = head.textContent.replace(/已选 \d+ 张/, `已选 ${mgSel.size} 张`);
}

async function mgPickAdd(cid){
  if (!mgSel.size) return alert('先勾选要添加的图片');
  let ok = 0;
  const fail = [];
  for (const name of mgSel){
    const j = await post('/api/collections/item', { id: cid, name, add: true });
    if (j.error) fail.push(name); else ok++;
  }
  mgPicking = false;
  mgSel.clear();
  refreshHistColl();
  mgRender();
  if (fail.length) alert('添加失败：\n' + fail.join('\n'));
  else logMsg?.('已添加 ' + ok + ' 张');
}

function mgPickCancel(){
  mgPicking = false;
  mgSel.clear();
  mgRender();
}

function mgOpen(cid){ mgOpenId = cid; mgRender(); }

async function mgCreate(){
  const name = prompt('新合集名称：');
  if (!name || !name.trim()) return;
  const j = await post('/api/collections/create', { name: name.trim() });
  if (j.error) return alert('创建失败：' + j.error);
  refreshHistColl(); mgRender();
}
async function mgRename(cid, cur){
  const name = prompt('重命名：', cur);
  if (!name || !name.trim() || name === cur) return;
  const j = await post('/api/collections/rename', { id: cid, name: name.trim() });
  if (j.error) return alert('重命名失败：' + j.error);
  refreshHistColl(); mgRender();
}
async function mgDelete(cid, name){
  if (!confirm(`删除合集「${name}」？\n（只解除关联，不会删除 outputs/ 里的图片）`)) return;
  const j = await post('/api/collections/delete', { id: cid });
  if (j.error) return alert('删除失败：' + j.error);
  if (mgOpenId === cid) mgOpenId = null;
  refreshHistColl(); mgRender();
}
async function mgRemoveItem(cid, name){
  const j = await post('/api/collections/item', { id: cid, name, add: false });
  if (j.error) return alert('移出失败：' + j.error);
  mgRender();
}

async function mgExport(cid){
  const r = await fetch('/api/collections/export?id=' + encodeURIComponent(cid));
  const ct = r.headers.get('Content-Type') || '';
  if (!ct.includes('application/zip')){
    const j = await r.json().catch(() => ({}));
    return alert('导出失败：' + (j.error || '未知错误'));
  }
  const blob = await r.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = cid === 'all' ? 'snoakari-favorites-all.zip' : 'snoakari-favorites.zip';
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}

function mgImportZip(){
  const inp = $('mgZipFile');
  inp.onchange = async () => {
    const f = inp.files[0];
    inp.value = '';
    if (!f) return;
    const r = await fetch('/api/collections/import', { method: 'POST', body: f });
    const j = await r.json();
    if (j.error) return alert('导入失败：' + j.error);
    alert(`导入完成：\n新建收藏夹 ${j.created} 个、合并 ${j.merged} 个\n新增图片 ${j.added} 张、内容重复跳过 ${j.skipped} 张`);
    refreshHistColl(); mgRender();
  };
  inp.click();
}

function mgImportImages(cid){
  const inp = $('mgImgFiles');
  inp.onchange = async () => {
    const fs = [...inp.files];
    inp.value = '';
    if (!fs.length) return;
    let ok = 0;
    const fail = [];
    for (const f of fs){
      try{
        const r = await fetch('/api/collections/import_image?name=' + encodeURIComponent(f.name),
                               { method: 'POST', body: f });
        const j = await r.json();
        if (j.error){ fail.push(f.name + '：' + j.error); continue; }
        await post('/api/collections/item', { id: cid, name: j.name, add: true });
        ok++;
      }catch(e){ fail.push(f.name + '：' + e); }
    }
    alert('导入 ' + ok + ' 张' + (fail.length ? '；失败：\n' + fail.join('\n') : ''));
    refreshHistColl(); mgRender();
  };
  inp.click();
}

document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  if ($('lb').style.display === 'flex') { $('lb').style.display = 'none'; return; }
  if (mgPicking) mgPickCancel();
});
