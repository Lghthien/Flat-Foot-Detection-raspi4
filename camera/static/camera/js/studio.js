const $=s=>document.querySelector(s);
const RESTART=['index','width','height','fps','format'];
const I=p=>`<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
const ICON={
 cam:I('<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>'),
 rec:I('<circle cx="12" cy="12" r="6" fill="currentColor"/>'),
 stop:I('<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/>'),
 full:I('<path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>'),
 trash:I('<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m5 0V4a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v2"/>'),
 dl:I('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>'),
 reset:I('<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>')
};
const SW=[
 {k:'brightness',t:'Độ sáng',min:-100,max:100,step:1},
 {k:'gamma',t:'Gamma (làm sáng vùng tối)',min:0.5,max:3,step:0.05},
 {k:'contrast',t:'Tương phản',min:0.5,max:2,step:0.05},
 {k:'saturation',t:'Độ bão hòa màu',min:0,max:2,step:0.05},
 {k:'sharpen',t:'Làm nét',min:0,max:2,step:0.05}
];
const PRESETS={
 natural:{gamma:1,brightness:0,contrast:1,saturation:1,sharpen:0,clahe:false},
 bright:{gamma:1.6,brightness:10,contrast:1.1,saturation:1.1,sharpen:0.3,clahe:false},
 lowlight:{gamma:2.0,brightness:20,contrast:1.15,saturation:1.1,sharpen:0.5,clahe:true}
};
let st=null, tab='photos', media={photos:[],videos:[]}, prevRec=false;

function csrfToken(){
  const cookie=document.cookie.split('; ').find(item=>item.startsWith('csrftoken='));
  return cookie?decodeURIComponent(cookie.slice('csrftoken='.length)):
    document.querySelector('[name=csrfmiddlewaretoken]')?.value;
}

async function api(path,body){
  const headers={'Content-Type':'application/json'};
  const csrf=csrfToken();
  if(csrf)headers['X-CSRFToken']=csrf;
  const opt=body===undefined?{}:{method:'POST',headers,body:JSON.stringify(body)};
  const r=await fetch(path,opt); let j={}; try{j=await r.json()}catch(e){}
  if(!r.ok) throw new Error(j.error||('Lỗi '+r.status));
  return j;
}
let tt;
function toast(msg,type){const t=$('#toast');t.textContent=msg;t.className='show '+(type||'');clearTimeout(tt);tt=setTimeout(()=>{t.className=''},3400);}
const fmtSize=b=>b>1048576?(b/1048576).toFixed(1)+' MB':Math.max(1,Math.round(b/1024))+' KB';
const mmss=s=>{s=Math.floor(s);return String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0')};

function addOpt(sel,val,label){if(![...sel.options].some(o=>o.value===String(val)))sel.add(new Option(label||val,val));sel.value=String(val);}

function buildSW(){
  const box=$('#swControls');box.innerHTML='';
  SW.forEach(c=>{
    const d=document.createElement('div');d.className='row';
    d.innerHTML=`<label for="sw_${c.k}">${c.t}</label><output id="o_${c.k}"></output><input type="range" id="sw_${c.k}" min="${c.min}" max="${c.max}" step="${c.step}">`;
    box.appendChild(d);
    const inp=d.querySelector('input');
    inp.addEventListener('input',()=>{$('#o_'+c.k).textContent=(+inp.value).toFixed(c.step<1?2:0);setSetting({[c.k]:+inp.value});});
  });
}

function syncUI(s){
  SW.forEach(c=>{const i=$('#sw_'+c.k);if(i){i.value=s[c.k];$('#o_'+c.k).textContent=(+s[c.k]).toFixed(c.step<1?2:0);}});
  ['clahe','flip_h','flip_v'].forEach(k=>{$('#t_'+k).checked=!!s[k];});
  $('#selRot').value=String(s.rotate);
  addOpt($('#selRes'),s.width+'x'+s.height,s.width+'×'+s.height);
  addOpt($('#selFps'),s.fps);
  $('#selFmt').value=s.format;
  $('#jq').value=s.jpeg_quality;$('#o_jq').textContent=s.jpeg_quality;
  const dv=$('#selDev');if([...dv.options].some(o=>o.value===String(s.index)))dv.value=String(s.index);
}

let pend={},tm;
function setSetting(p){
  Object.assign(pend,p);clearTimeout(tm);
  tm=setTimeout(async()=>{
    const b=pend;pend={};
    try{
      st=await api('/api/settings',b);renderStatus();
      if(Object.keys(b).some(k=>RESTART.includes(k))){setTimeout(startStream,900);if('index' in b)setTimeout(loadControls,1500);}
    }catch(e){
      toast(e.message,'err');
      try{st=await api('/api/status');syncUI(st.settings);}catch(_){}
    }
  },150);
}

function renderStatus(){
  if(!st)return;
  const ok=st.ok;
  $('#pillCam').className='pill '+(ok?'ok':'bad');
  $('#pillCamT').textContent=ok?'Camera hoạt động':'Mất tín hiệu';
  $('#pillFps').textContent=(st.fps||0)+' FPS';
  $('#nosignal').classList.toggle('hidden',ok);
  $('#errText').textContent=st.error||'Đang chờ camera…';
  $('#chipRes').textContent=ok&&st.width?`${st.width}×${st.height} · ${st.fourcc||'?'}`:'–';
  const rec=st.recording;
  $('#pillRec').classList.toggle('hidden',!rec);$('#chipRec').classList.toggle('hidden',!rec);
  if(rec){$('#pillRecT').textContent='REC '+mmss(st.rec_seconds);$('#chipRecT').textContent=mmss(st.rec_seconds);}
  const b=$('#btnRec');b.classList.toggle('on',rec);
  b.innerHTML=(rec?ICON.stop:ICON.rec)+(rec?' Dừng quay':' Quay video')+' <kbd>R</kbd>';
  if(prevRec&&!rec){loadMedia();}
  prevRec=rec;
  $('#ffNote').classList.toggle('hidden',st.ffmpeg);
  $('#pathHint').textContent='Lưu tại: '+(tab==='photos'?st.paths.photos:st.paths.videos);
}

async function pollStatus(){
  try{st=await api('/api/status');renderStatus();}
  catch(e){$('#pillCam').className='pill bad';$('#pillCamT').textContent='Mất kết nối Pi';}
  setTimeout(pollStatus,1000);
}

function startStream(){$('#live').src='/stream.mjpg?t='+Date.now();}
$('#live').addEventListener('error',()=>setTimeout(startStream,2000));

async function snap(){
  try{
    const r=await api('/api/snapshot',{});
    const v=$('#viewer');v.classList.remove('flash');void v.offsetWidth;v.classList.add('flash');
    toast('Đã lưu ảnh: '+r.name,'good');loadMedia();
  }catch(e){toast(e.message,'err');}
}
async function toggleRec(){
  try{
    if(st&&st.recording){const r=await api('/api/record/stop',{});toast('Đã lưu video: '+r.name,'good');}
    else{const r=await api('/api/record/start',{});toast('Bắt đầu quay: '+r.name,'good');}
    st=await api('/api/status');renderStatus();loadMedia();
  }catch(e){toast(e.message,'err');}
}

async function loadDevices(){
  try{
    const r=await api('/api/devices');const sel=$('#selDev');sel.innerHTML='';
    r.devices.forEach(d=>sel.add(new Option(`/dev/video${d.index} · ${d.name}`,d.index)));
    if(st)syncUI(st.settings);
  }catch(e){}
}

function pretty(n){n=n.replace(/_/g,' ');return n.charAt(0).toUpperCase()+n.slice(1);}
async function loadControls(){
  const box=$('#hwControls'),note=$('#hwNote');
  try{
    const r=await api('/api/controls');box.innerHTML='';note.textContent='';
    if(!r.available){note.textContent='Cần cài v4l-utils: sudo apt install v4l-utils';return;}
    if(!r.controls.length){note.textContent='Thiết bị này không có điều khiển phần cứng nào qua V4L2.';return;}
    r.controls.forEach(c=>{
      const d=document.createElement('div');
      if(c.type==='int'){
        d.className='row'+(c.inactive?' dim':'');
        d.innerHTML=`<label>${pretty(c.name)}</label><output>${c.value}</output><input type="range" min="${c.min}" max="${c.max}" step="${c.step}" value="${c.value}" ${c.inactive?'disabled':''}>`;
        const inp=d.querySelector('input'),out=d.querySelector('output');
        inp.addEventListener('input',()=>{out.textContent=inp.value;});
        inp.addEventListener('change',()=>sendHW(c.name,inp.value));
      }else if(c.type==='bool'){
        d.className='toggle'+(c.inactive?' dim':'');
        d.innerHTML=`<span>${pretty(c.name)}</span><input type="checkbox" ${c.value?'checked':''} ${c.inactive?'disabled':''}>`;
        d.querySelector('input').addEventListener('change',e=>sendHW(c.name,e.target.checked?1:0));
      }else{
        d.className='f'+(c.inactive?' dim':'');d.style.margin='10px 0';
        d.innerHTML=`<label class="f">${pretty(c.name)}<select ${c.inactive?'disabled':''}>${c.menu.map(m=>`<option value="${m.value}" ${m.value===c.value?'selected':''}>${m.label}</option>`).join('')}</select></label>`;
        d.querySelector('select').addEventListener('change',e=>sendHW(c.name,e.target.value));
      }
      box.appendChild(d);
    });
  }catch(e){note.textContent='Không đọc được điều khiển phần cứng.';}
}
async function sendHW(name,value){
  try{await api('/api/control',{name,value:+value});setTimeout(loadControls,250);}
  catch(e){toast(e.message,'err');loadControls();}
}

async function loadMedia(){try{media=await api('/api/media');renderGallery();}catch(e){}}
function renderGallery(){
  const list=media[tab]||[],g=$('#grid');
  $('#cntP').textContent=(media.photos||[]).length;$('#cntV').textContent=(media.videos||[]).length;
  if(st)$('#pathHint').textContent='Lưu tại: '+(tab==='photos'?st.paths.photos:st.paths.videos);
  if(!list.length){g.innerHTML='<div class="empty">Chưa có '+(tab==='photos'?'ảnh':'video')+' nào.</div>';return;}
  g.innerHTML=list.map(m=>{
    const th=tab==='photos'?`<img loading="lazy" src="${m.url}" alt="">`:(m.name.endsWith('.mp4')?`<video preload="metadata" muted playsinline src="${m.url}#t=0.1"></video>`:'<div class="avi">AVI</div>');
    return `<div class="item"><div class="thumb" data-open="${m.url}" data-name="${m.name}">${th}</div>
      <div class="meta"><div><b>${m.name}</b><small>${fmtSize(m.size)} · ${new Date(m.mtime*1000).toLocaleString('vi-VN')}</small></div>
      <div class="acts"><a class="ib" href="${m.url}?dl=1" title="Tải xuống">${ICON.dl}</a><button class="ib del" data-del="${m.name}" title="Xóa">${ICON.trash}</button></div></div></div>`;
  }).join('');
}
$('#grid').addEventListener('click',async e=>{
  const o=e.target.closest('[data-open]');
  if(o){openModal(o.dataset.open,o.dataset.name);return;}
  const d=e.target.closest('[data-del]');
  if(d&&confirm('Xóa tệp '+d.dataset.del+'?')){
    try{await api('/api/media/delete',{kind:tab,name:d.dataset.del});loadMedia();}catch(err){toast(err.message,'err');}
  }
});
function openModal(url,name){
  const box=$('#modalBox');
  if(tab==='photos')box.innerHTML=`<img src="${url}" alt="">`;
  else if(name.endsWith('.mp4'))box.innerHTML=`<video src="${url}" controls autoplay></video>`;
  else box.innerHTML=`<div class="card">Định dạng .avi không phát được trong trình duyệt.<br><a class="btn" style="margin-top:10px" href="${url}?dl=1">Tải xuống</a></div>`;
  $('#modal').classList.add('show');
}
function closeModal(){$('#modal').classList.remove('show');$('#modalBox').innerHTML='';}
$('#modal').addEventListener('click',e=>{if(e.target.id==='modal')closeModal();});

document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>{
  tab=b.dataset.tab;document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===b));renderGallery();
}));
document.querySelectorAll('[data-i]').forEach(e=>e.insertAdjacentHTML('afterbegin',ICON[e.dataset.i]+(e.classList.contains('logo')?'':' ')));
document.querySelectorAll('[data-preset]').forEach(b=>b.addEventListener('click',()=>{
  const p=PRESETS[b.dataset.preset];setSetting(p);syncUI(Object.assign({},st.settings,p));
}));
$('#btnSwReset').addEventListener('click',()=>{const p=PRESETS.natural;setSetting(Object.assign({flip_h:false,flip_v:false,rotate:0},p));syncUI(Object.assign({},st.settings,p,{flip_h:false,flip_v:false,rotate:0}));});
$('#btnHwReset').addEventListener('click',async()=>{try{await api('/api/controls/reset',{});toast('Đã đặt lại thông số phần cứng','good');loadControls();}catch(e){toast(e.message,'err');}});
$('#btnSnap').addEventListener('click',snap);
$('#btnRec').addEventListener('click',toggleRec);
$('#btnFull').addEventListener('click',()=>{const v=$('#viewer');if(document.fullscreenElement)document.exitFullscreen();else v.requestFullscreen&&v.requestFullscreen();});
$('#selDev').addEventListener('change',e=>setSetting({index:+e.target.value}));
$('#selRes').addEventListener('change',e=>{const[w,h]=e.target.value.split('x');setSetting({width:+w,height:+h});});
$('#selFps').addEventListener('change',e=>setSetting({fps:+e.target.value}));
$('#selFmt').addEventListener('change',e=>setSetting({format:e.target.value}));
$('#selRot').addEventListener('change',e=>setSetting({rotate:+e.target.value}));
$('#jq').addEventListener('input',e=>{$('#o_jq').textContent=e.target.value;setSetting({jpeg_quality:+e.target.value});});
['clahe','flip_h','flip_v'].forEach(k=>$('#t_'+k).addEventListener('change',e=>setSetting({[k]:e.target.checked})));
document.addEventListener('keydown',e=>{
  if(['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName))return;
  if(e.key==='Escape')closeModal();
  else if(e.key==='s'||e.key==='S')snap();
  else if(e.key==='r'||e.key==='R')toggleRec();
});

(async function init(){
  buildSW();
  try{st=await api('/api/status');syncUI(st.settings);renderStatus();}catch(e){}
  await loadDevices();
  startStream();loadControls();loadMedia();pollStatus();
})();
