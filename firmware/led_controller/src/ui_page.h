// The one web page: LED controls, live preview, device status and the console.
// Served from flash at "/". Talks to /api/led, /api/frame, /api/status,
// /api/log and /api/cmd.
#pragma once
#include <Arduino.h>

static const char UI_PAGE[] PROGMEM = R"HTML(<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>LED controller</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--fg:#1d2330;--mut:#667085;--acc:#2e6fba;--log:#0f1720;--logfg:#d6e2f0;--bd:#d9dee7;--chip:#eef1f6}
@media(prefers-color-scheme:dark){:root{--bg:#0f1218;--card:#181c24;--fg:#e6e9ef;--mut:#98a2b3;--acc:#6aa5ee;--log:#090c11;--logfg:#cfe0f5;--bd:#2a303c;--chip:#222833}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,sans-serif}
main{max-width:52rem;margin:0 auto;padding:16px}
header{display:flex;align-items:center;gap:12px;margin:.25rem 0 1rem}h1{font-size:1.25rem;margin:0;flex:1}
h2{font-size:.8rem;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);margin:0 0 .6rem;font-weight:600}
section{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:14px;margin-bottom:12px}
.row{display:flex;align-items:center;gap:10px;margin:.5rem 0}.row label{min-width:5.5rem;color:var(--mut)}
input[type=range]{flex:1;accent-color:var(--acc)}.val{min-width:2.5rem;text-align:right;font-variant-numeric:tabular-nums}
input[type=color]{width:3rem;height:2.2rem;border:1px solid var(--bd);border-radius:6px;background:none;padding:2px}
input[type=number],input[type=text],input:not([type]){font:inherit;padding:.45rem;border:1px solid var(--bd);border-radius:6px;background:var(--card);color:var(--fg)}
input[type=number]{width:5.5rem}
button{font:inherit;padding:.5rem 1rem;border:0;border-radius:6px;background:var(--acc);color:#fff;cursor:pointer}
.chips{display:flex;flex-wrap:wrap;gap:6px}.chips button{background:var(--chip);color:var(--fg);border:1px solid var(--bd);padding:.4rem .8rem;text-transform:capitalize}
.chips button.on{background:var(--acc);color:#fff;border-color:var(--acc)}
.chips label{display:flex;align-items:center;gap:4px;background:var(--chip);border:1px solid var(--bd);border-radius:6px;padding:.3rem .6rem;text-transform:capitalize;cursor:pointer}.chips label input{accent-color:var(--acc)}
.sw{display:flex;gap:4px;flex-wrap:wrap}.sw i{width:1.6rem;height:1.6rem;border-radius:50%;border:1px solid var(--bd);cursor:pointer;display:inline-block}
.tog{position:relative;width:3.2rem;height:1.8rem;flex:none}.tog input{opacity:0;width:0;height:0}
.tog span{position:absolute;inset:0;background:var(--bd);border-radius:1rem;transition:.2s;cursor:pointer}
.tog span:before{content:"";position:absolute;width:1.4rem;height:1.4rem;left:.2rem;top:.2rem;background:#fff;border-radius:50%;transition:.2s}
.tog input:checked+span{background:var(--acc)}.tog input:checked+span:before{transform:translateX(1.4rem)}
.seg{display:flex;border:1px solid var(--bd);border-radius:8px;overflow:hidden}.seg button{flex:1;border-radius:0;background:var(--chip);color:var(--fg);padding:.6rem}
.seg button+button{border-left:1px solid var(--bd)}.seg button.on{background:var(--acc);color:#fff}
.badge{font-size:.8rem;color:var(--mut);font-variant-numeric:tabular-nums}.warn{color:#d97706}
.strip{display:flex;align-items:center;gap:8px;margin:4px 0}.strip b{font-size:.75rem;color:var(--mut);width:2.6rem;font-weight:500}
.strip canvas{flex:1;height:14px;border-radius:3px;background:#000;min-width:0}
.presets{display:grid;grid-template-columns:repeat(auto-fill,minmax(10.5rem,1fr));gap:6px}
.pre{display:flex;align-items:center;gap:6px;border:1px solid var(--bd);border-radius:8px;padding:6px 8px;background:var(--chip)}
.pre .dot{width:1rem;height:1rem;border-radius:50%;flex:none}.pre span{flex:1;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pre.empty span{color:var(--mut);cursor:default}.pre.cur{outline:2px solid var(--acc)}
.pre button{background:none;color:var(--mut);padding:0 .2rem}.pre input{accent-color:var(--acc)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(8.5rem,1fr));gap:8px;margin-bottom:12px}
.k{background:var(--chip);border-radius:8px;padding:8px 10px}
.k b{display:block;font-size:.75rem;color:var(--mut);font-weight:500}.k span{font-variant-numeric:tabular-nums;word-break:break-all}
#log{background:var(--log);color:var(--logfg);font:13px/1.35 ui-monospace,monospace;height:16rem;overflow:auto;white-space:pre-wrap;border-radius:8px;padding:10px;margin:0}
form{display:flex;gap:8px;margin-top:8px}form input{flex:1}
details summary{cursor:pointer;color:var(--mut);font-weight:600;font-size:.8rem;text-transform:uppercase;letter-spacing:.06em}
a{color:var(--acc)}.off{color:#c0392b}.mut{color:var(--mut);font-size:.85rem}
</style></head><body><main>
<header><h1>LED controller</h1><span id=pw class=badge></span>
<label class=tog title="LEDs on/off"><input type=checkbox id=on><span></span></label></header>

<section><h2>Live preview</h2>
<div id=strips></div>
<div class=row><label class=mut style="min-width:0"><input type=checkbox id=pv checked> live</label>
<span class=mut>Colours before brightness and power limit.</span></div></section>

<section><h2>Mode</h2>
<div class=seg id=run><button data-r=manual>User</button><button data-r=auto>Auto</button><button data-r=seq>Sequence</button></div>
<p class=mut id=runhint></p>
<div id=autoopts><div class=row><span>New effect and colours every</span><input type=number id=autosec min=2 max=3600> s</div>
<details><summary>Effects included</summary><div class=chips id=automask style="margin-top:8px"></div></details></div>
<div id=seqopts><div class=row><span>Next preset every</span><input type=number id=seqsec min=2 max=3600> s</div></div>
</section>

<section><h2>Effect</h2><div class=chips id=modes></div>

<div class=row><label>Brightness</label><input type=range id=bri min=1 max=255><span class=val id=briv></span></div>
<div class=row><label>Speed</label><input type=range id=speed min=0 max=255><span class=val id=speedv></span></div>
<div class=row><label>Colour 1</label><input type=color id=c1><div class=sw data-for=c1></div></div>
<div class=row><label>Colour 2</label><input type=color id=c2><div class=sw data-for=c2></div></div></section>

<section><h2>Presets &amp; sequence</h2>
<div class=presets id=presets></div>
<div class=row style="flex-wrap:wrap"><input id=pname placeholder="preset name" maxlength=15 style="flex:1;min-width:8rem">
<button id=psave>Save current to slot</button></div>
<p class=mut>Tick presets to include them in Sequence mode.</p></section>

<section><details><summary>Strips &amp; power</summary>
<div class=row style="flex-wrap:wrap" id=counts></div>
<div class=row><label>Power limit</label><input type=number id=maxma min=100 step=100> mA
<span class=mut id=maxmah></span></div>
<button id=apply>Apply</button>
<p class=mut>LEDs need 5 V on J1/J2; USB alone powers only the ESP32. Count 0 disables an output.</p>
</details></section>

<section><h2>Device</h2>
<div class=grid>
<div class=k><b>Wi-Fi</b><span id=st>&hellip;</span></div><div class=k><b>Network</b><span id=ss>-</span></div>
<div class=k><b>IP</b><span id=ip>-</span></div><div class=k><b>Signal</b><span id=rs>-</span></div>
<div class=k><b>Uptime</b><span id=up>-</span></div><div class=k><b>Free heap</b><span id=hp>-</span></div>
<div class=k><b>Chip temp</b><span id=tp>-</span></div><div class=k><b>MAC</b><span id=mc>-</span></div>
</div>
<pre id=log></pre>
<form id=f><input id=c placeholder="command - try 'help' or 'led'" autocomplete=off><button>Send</button></form>
<div class=chips style="margin-top:8px"><button data-c=status>status</button><button data-c=led>led</button><button data-c=info>info</button><button data-c=help>help</button></div>
<p><a href=/wifi>Change Wi-Fi network</a></p></section>
</main><script>
const $=id=>document.getElementById(id);let S=null,busy=0,slot=0;
const SW=['#ff0000','#ff6000','#ffc000','#00ff00','#00ffff','#0000ff','#8000ff','#ff2080','#ff9a40','#ffffff'];
async function api(body){busy++;try{const r=await fetch('/api/led',body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});
 const j=await r.json();if(!r.ok){add('\n[led] '+(j.error||r.status)+'\n');return}S=j;render()}catch(e){}finally{busy--}}
let tm={};function later(k,body,ms){clearTimeout(tm[k]);tm[k]=setTimeout(()=>api(body),ms||120)}
function render(){if(!S)return;const a=document.activeElement;
 if(S.presets[slot]){const fe=S.presets.findIndex(p=>!p);if(fe>=0)slot=fe}
 $('on').checked=S.on;$('pw').innerHTML='~'+S.est_ma+' mA'+(S.limited?' <span class=warn>limited</span>':'');
 for(const k of['bri','speed'])if(a!==$(k)){$(k).value=S[k];$(k+'v').textContent=S[k]}
 for(const k of['c1','c2'])if(a!==$(k))$(k).value=S[k].toLowerCase();
 $('modes').innerHTML=S.modes.map((m,i)=>`<button data-m=${i} class="${i==S.mode?'on':''}">${m}</button>`).join('');
 $('presets').innerHTML=S.presets.map((p,i)=>p?`<div class="pre${S.seq.current==i?' cur':''}"><input type=checkbox data-q=${i} ${S.seq.mask>>i&1?'checked':''} title="include in sequence">
 <i class=dot style="background:linear-gradient(90deg,${p.c1},${p.c2})"></i><span data-l=${i} title="load">${esc(p.name)}</span><button data-d=${i} title="delete">&times;</button></div>`
 :`<div class="pre empty${slot==i?' cur':''}" data-e=${i}><input type=radio name=sl ${slot==i?'checked':''} data-s=${i}><span>slot ${i+1} - empty</span></div>`).join('');
 if(a!==$('seqsec'))$('seqsec').value=S.seq.sec;
 if(a!==$('autosec'))$('autosec').value=S.auto.sec;
 const run=S.auto.on?'auto':S.seq.on?'seq':'manual';
 document.querySelectorAll('#run button').forEach(b=>b.classList.toggle('on',b.dataset.r==run));
 $('autoopts').style.display=run=='auto'?'':'none';$('seqopts').style.display=run=='seq'?'':'none';
 $('runhint').textContent={manual:'You pick the effect and colours below.',
  auto:'Automatic effect and colour combinations. Now: '+S.modes[S.mode]+'. Picking an effect or colour switches to User mode.',
  seq:'Cycling through your ticked presets'+(S.seq.current>=0&&S.presets[S.seq.current]?'. Now: '+S.presets[S.seq.current].name:'')+'. Loading a preset or picking an effect switches to User mode.'}[run];
 $('automask').innerHTML=S.modes.map((m,i)=>`<label><input type=checkbox data-a=${i} ${S.auto.mask>>i&1?'checked':''}>${m}</label>`).join('');
 if(!$('counts').contains(a))$('counts').innerHTML=S.count.map((n,i)=>`<label>OUT${i+1} <input type=number min=0 max=${S.max_per_output} value=${n} data-n=${i}></label>`).join('');
 if(a!==$('maxma')){$('maxma').value=S.maxma;$('maxma').max=S.maxma_limit}$('maxmah').textContent='max '+S.maxma_limit+' (fuse F1 7.5 A)';
 strips()}
function esc(s){return s.replace(/[&<>"']/g,c=>'&#'+c.charCodeAt(0)+';')}
function strips(){const h=$('strips');if(h.childElementCount!=4)h.innerHTML=[0,1,2,3].map(i=>`<div class=strip><b>OUT${i+1}</b><canvas id=cv${i}></canvas></div>`).join('')}
document.querySelectorAll('.sw').forEach(d=>{d.innerHTML=SW.map(c=>`<i style="background:${c}" data-c="${c}"></i>`).join('');
 d.onclick=e=>{const c=e.target.dataset.c;if(c){$(d.dataset.for).value=c;api({[d.dataset.for]:c})}}});
$('on').onchange=e=>api({on:e.target.checked});
for(const k of['bri','speed'])$(k).oninput=e=>{$(k+'v').textContent=e.target.value;later(k,{[k]:+e.target.value})};
for(const k of['c1','c2'])$(k).oninput=e=>later(k,{[k]:e.target.value},150);
$('modes').onclick=e=>{const m=e.target.dataset.m;if(m!=null)api({mode:+m})};
$('presets').onclick=e=>{const t=e.target.dataset;
 if(t.l!=null)api({preset:{action:'load',slot:+t.l}});
 else if(t.d!=null){if(confirm('Delete preset '+S.presets[+t.d].name+'?'))api({preset:{action:'delete',slot:+t.d}})}
 else if(t.s!=null||t.e!=null){slot=+(t.s??t.e);render()}};
$('presets').onchange=e=>{const q=e.target.dataset.q;if(q!=null)api({seq:{mask:S.seq.mask^(1<<q)}})};
$('psave').onclick=()=>{let s=slot;if(S.presets[s]&&!confirm('Overwrite '+S.presets[s].name+'?'))return;
 api({preset:{action:'save',slot:s,name:$('pname').value}});$('pname').value='';const nx=S.presets.findIndex((p,i)=>!p&&i!=s);if(nx>=0)slot=nx};

$('seqsec').onchange=e=>api({seq:{sec:+e.target.value}});
$('run').onclick=e=>{const r=e.target.dataset.r;if(!r)return;
 if(r=='manual')api({auto:{on:false},seq:{on:false}});
 else if(r=='auto')api({auto:{on:true,sec:+$('autosec').value}});
 else{const used=S.presets.reduce((m,p,i)=>p?m|1<<i:m,0);
  if(!used){alert('Save at least one preset first (Presets section), then pick Sequence.');return}
  const mask=(S.seq.mask&used)||used;api({seq:{on:true,sec:+$('seqsec').value,mask}})}};
$('autosec').onchange=e=>api({auto:{sec:+e.target.value}});
$('automask').onchange=e=>{const i=e.target.dataset.a;if(i!=null)api({auto:{mask:S.auto.mask^(1<<i)}})};
$('apply').onclick=()=>api({count:[...document.querySelectorAll('[data-n]')].map(x=>+x.value),maxma:+$('maxma').value});
async function frame(){if(!$('pv').checked||document.hidden||!S)return;try{const f=await(await fetch('/api/frame')).json();
 f.px.forEach((hx,i)=>{const c=$('cv'+i);if(!c)return;const n=hx.length/6,w=c.clientWidth||300;c.width=w;c.height=14;const g=c.getContext('2d');
 g.fillStyle='#000';g.fillRect(0,0,w,14);if(!n)return;const cw=w/n;
 for(let j=0;j<n;j++){g.fillStyle='#'+hx.substr(j*6,6);g.fillRect(j*cw,0,Math.max(1,cw-(cw>3?1:0)),14)}})}catch(e){}}
const log=$('log');let seq=0,hist=[],hi=0;
function add(t){const atEnd=log.scrollTop+log.clientHeight>=log.scrollHeight-4;log.textContent+=t;
 if(log.textContent.length>60000)log.textContent=log.textContent.slice(-40000);if(atEnd)log.scrollTop=log.scrollHeight}
async function poll(){try{const r=await fetch('/api/log?since='+seq);const t=await r.text();seq=+r.headers.get('X-Seq')||seq;if(t)add(t)}catch(e){}}
function fmt(s){const d=Math.floor(s/86400),h=Math.floor(s/3600)%24,m=Math.floor(s/60)%60;return(d?d+'d ':'')+(d||h?h+'h ':'')+m+'m '+s%60+'s'}
async function stat(){try{const s=await(await fetch('/api/status')).json();
 $('st').textContent=s.status;$('st').className=s.connected?'':'off';$('ss').textContent=s.ssid||'-';$('ip').textContent=s.ip||'-';
 $('rs').textContent=s.connected?s.rssi+' dBm':'-';$('up').textContent=fmt(s.uptime_s);$('hp').textContent=(s.heap/1024).toFixed(0)+' KB';
 $('tp').textContent=s.temp_c.toFixed(1)+' °C';$('mc').textContent=s.mac}catch(e){$('st').textContent='device unreachable';$('st').className='off'}}
async function cmd(c){if(!c)return;hist.push(c);hi=hist.length;
 try{await fetch('/api/cmd',{method:'POST',headers:{'Content-Type':'text/plain'},body:c})}catch(e){add('\n[send failed]\n')}poll();if(/^led/.test(c))api()}
$('f').onsubmit=e=>{e.preventDefault();cmd($('c').value.trim());$('c').value=''};
$('c').onkeydown=e=>{if(e.key=='ArrowUp'&&hi>0){$('c').value=hist[--hi];e.preventDefault()}
 if(e.key=='ArrowDown'){hi=Math.min(hist.length,hi+1);$('c').value=hist[hi]||''}};
document.querySelectorAll('[data-c]').forEach(b=>{if(b.tagName=='BUTTON')b.onclick=()=>cmd(b.dataset.c)});
strips();api();poll();stat();
setInterval(frame,250);setInterval(poll,1000);setInterval(stat,3000);setInterval(()=>{if(!busy&&!document.hidden)api()},4000);
</script></body></html>)HTML";
