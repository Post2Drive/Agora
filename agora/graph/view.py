"""Interactive graph viewer: one self-contained HTML file, works offline (no CDN).

Drag nodes, scroll to zoom, drag the background to pan, search by name, click a node
to see its description, aliases and every relation with the source fact."""
from __future__ import annotations

import json
from pathlib import Path

from .store import GraphStore

PALETTE = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f", "#edc948", "#b07aa1",
           "#ff9da7", "#9c755f", "#bab0ac", "#2f4b7c", "#a05195"]

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agora graph: __TITLE__</title>
<style>
:root{--bg:#fafaf8;--fg:#1d1d1b;--muted:#6b6b66;--panel:#ffffff;--line:#d9d9d3;--edge:rgba(60,60,55,.28)}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--fg:#ecebe6;--muted:#9c9b95;--panel:#1f1f1d;--line:#34342f;--edge:rgba(220,220,210,.22)}}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
#app{display:flex;height:100%}#stage{flex:1;position:relative;min-width:0}canvas{display:block;width:100%;height:100%;cursor:grab}
#top{position:absolute;left:12px;right:12px;top:12px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;pointer-events:none}
#top>*{pointer-events:auto}input{font:inherit;padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--panel);color:var(--fg);width:min(260px,60vw)}
.chip{display:inline-flex;align-items:center;gap:6px;padding:4px 9px;border:1px solid var(--line);border-radius:999px;background:var(--panel);cursor:pointer;user-select:none;font-size:12px}
.chip i{width:9px;height:9px;border-radius:50%;display:inline-block}.chip.off{opacity:.35}
#side{width:340px;max-width:42vw;border-left:1px solid var(--line);background:var(--panel);overflow:auto;padding:16px}
#side h2{margin:0 0 4px;font-size:18px}#side .t{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
#side .rel{border-top:1px solid var(--line);padding:8px 0}#side .rel b{font-weight:600}#side .fact{color:var(--muted);font-size:13px}
#side a{color:inherit;cursor:pointer;text-decoration:underline dotted}#stats{color:var(--muted);font-size:12px;margin-top:6px}
@media (max-width:700px){#app{flex-direction:column}#side{width:auto;max-width:none;height:40%;border-left:0;border-top:1px solid var(--line)}}
</style></head><body><div id="app"><div id="stage"><canvas id="c"></canvas>
<div id="top"><input id="q" placeholder="Search entities..."><span id="legend"></span></div></div>
<aside id="side"><div class="t">Knowledge graph</div><h2>__TITLE__</h2>
<div id="stats"></div><p class="fact">Click a node to see what the documents say about it. Drag to move, scroll to zoom.</p></aside></div>
<script>
const G=__DATA__;const COLORS=__COLORS__;
const cv=document.getElementById('c'),cx=cv.getContext('2d'),side=document.getElementById('side');
let W=0,H=0,dpr=window.devicePixelRatio||1,scale=1,ox=0,oy=0,hidden=new Set(),sel=null,hover=null;
const N=G.nodes.map((n,i)=>({...n,i,x:Math.cos(i)*200*Math.random(),y:Math.sin(i)*200*Math.random(),vx:0,vy:0,r:5+Math.min(14,Math.sqrt(n.mentions||1)*2.5)}));
const byId=new Map(N.map(n=>[n.id,n]));const E=G.links.map(e=>({...e,s:byId.get(e.source),t:byId.get(e.target)})).filter(e=>e.s&&e.t);
const deg=new Map();E.forEach(e=>{deg.set(e.s.id,(deg.get(e.s.id)||0)+1);deg.set(e.t.id,(deg.get(e.t.id)||0)+1)});
document.getElementById('stats').textContent=`${N.length} entities · ${E.length} relations · ${G.meta.documents} documents`;
const types=[...new Set(N.map(n=>n.type))];const col=t=>COLORS[types.indexOf(t)%COLORS.length];
const lg=document.getElementById('legend');types.forEach(t=>{const c=document.createElement('span');c.className='chip';c.innerHTML=`<i style="background:${col(t)}"></i>${t}`;c.onclick=()=>{hidden.has(t)?hidden.delete(t):hidden.add(t);c.classList.toggle('off');kick()};lg.appendChild(c)});
function size(){const r=cv.getBoundingClientRect();W=r.width;H=r.height;cv.width=W*dpr;cv.height=H*dpr;draw()}
window.addEventListener('resize',size);
let alpha=1;function kick(){alpha=Math.max(alpha,.5);if(!running)loop()}
let running=false;function loop(){running=true;tick();draw();if(alpha>.01)requestAnimationFrame(loop);else running=false}
function vis(n){return!hidden.has(n.type)}
function tick(){const V=N.filter(vis),k=60;for(let a=0;a<V.length;a++){const p=V[a];for(let b=a+1;b<V.length;b++){const q=V[b];let dx=p.x-q.x,dy=p.y-q.y,d2=dx*dx+dy*dy+.01;if(d2>250000)continue;const f=k*k/d2*alpha;p.vx+=dx*f*.05;p.vy+=dy*f*.05;q.vx-=dx*f*.05;q.vy-=dy*f*.05}}
E.forEach(e=>{if(!vis(e.s)||!vis(e.t))return;const dx=e.t.x-e.s.x,dy=e.t.y-e.s.y,d=Math.sqrt(dx*dx+dy*dy)||1,f=(d-k)/d*.04*alpha;e.s.vx+=dx*f;e.s.vy+=dy*f;e.t.vx-=dx*f;e.t.vy-=dy*f});
V.forEach(n=>{n.vx-=n.x*.002*alpha;n.vy-=n.y*.002*alpha;if(n!==drag){n.x+=n.vx;n.y+=n.vy}n.vx*=.6;n.vy*=.6});alpha*=.985}
function nb(n){const s=new Set([n.id]);E.forEach(e=>{if(e.s===n)s.add(e.t.id);if(e.t===n)s.add(e.s.id)});return s}
function draw(){cx.setTransform(dpr,0,0,dpr,0,0);cx.clearRect(0,0,W,H);cx.translate(ox,oy);cx.scale(scale,scale);
const st=getComputedStyle(document.documentElement),edge=st.getPropertyValue('--edge'),fg=st.getPropertyValue('--fg'),focus=sel?nb(sel):null;
cx.lineWidth=1/scale;E.forEach(e=>{if(!vis(e.s)||!vis(e.t))return;cx.globalAlpha=focus&&!(focus.has(e.s.id)&&focus.has(e.t.id)&&(e.s===sel||e.t===sel))?.12:1;cx.strokeStyle=edge;cx.beginPath();cx.moveTo(e.s.x,e.s.y);cx.lineTo(e.t.x,e.t.y);cx.stroke()});
N.forEach(n=>{if(!vis(n))return;cx.globalAlpha=focus&&!focus.has(n.id)?.2:1;cx.fillStyle=col(n.type);cx.beginPath();cx.arc(n.x,n.y,n.r,0,7);cx.fill();if(n===sel||n===hover){cx.lineWidth=2/scale;cx.strokeStyle=fg;cx.stroke()}
if((scale>.6||n.r>10)&&(n.r>8||n===sel||n===hover||(focus&&focus.has(n.id)))){cx.fillStyle=fg;cx.font=`${12/scale}px system-ui`;cx.fillText(n.name,n.x+n.r+3,n.y+4)}});cx.globalAlpha=1}
function at(mx,my){const x=(mx-ox)/scale,y=(my-oy)/scale;let best=null,bd=1e9;N.forEach(n=>{if(!vis(n))return;const d=(n.x-x)**2+(n.y-y)**2;if(d<(n.r+4)**2&&d<bd){bd=d;best=n}});return best}
let drag=null,pan=null,moved=false;
cv.addEventListener('pointerdown',ev=>{const n=at(ev.offsetX,ev.offsetY);moved=false;if(n){drag=n}else{pan={x:ev.offsetX-ox,y:ev.offsetY-oy}}cv.setPointerCapture(ev.pointerId)});
cv.addEventListener('pointermove',ev=>{if(drag){drag.x=(ev.offsetX-ox)/scale;drag.y=(ev.offsetY-oy)/scale;moved=true;kick()}else if(pan){ox=ev.offsetX-pan.x;oy=ev.offsetY-pan.y;moved=true;draw()}else{const h=at(ev.offsetX,ev.offsetY);if(h!==hover){hover=h;cv.style.cursor=h?'pointer':'grab';draw()}}});
cv.addEventListener('pointerup',ev=>{if(drag&&!moved)show(drag);if(pan&&!moved){sel=null;draw()}drag=null;pan=null});
cv.addEventListener('wheel',ev=>{ev.preventDefault();const f=Math.exp(-ev.deltaY*.0015),mx=ev.offsetX,my=ev.offsetY;ox=mx-(mx-ox)*f;oy=my-(my-oy)*f;scale*=f;draw()},{passive:false});
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function show(n){sel=n;let al=[];try{al=JSON.parse(n.aliases||'[]')}catch(e){}
const rels=E.filter(e=>e.s===n||e.t===n).map(e=>{const o=e.s===n?e.t:e.s,dir=e.s===n?`→ ${e.type} →`:`← ${e.type} ←`;return`<div class="rel">${esc(dir)} <a data-id="${o.id}">${esc(o.name)}</a><div class="fact">${esc(e.fact)}</div></div>`}).join('');
side.innerHTML=`<div class="t">${esc(n.type)} · ${n.mentions} mentions · ${deg.get(n.id)||0} links</div><h2>${esc(n.name)}</h2>${al.length?`<p class="fact">Also called: ${esc(al.join(', '))}</p>`:''}<p>${esc(n.description)}</p>${rels||'<p class="fact">No relations found.</p>'}`;
side.querySelectorAll('a[data-id]').forEach(a=>a.onclick=()=>{const m=byId.get(+a.dataset.id);ox=W/2-m.x*scale;oy=H/2-m.y*scale;show(m)});draw()}
document.getElementById('q').addEventListener('input',ev=>{const q=ev.target.value.trim().toLowerCase();if(!q)return;const m=N.find(n=>n.name.toLowerCase().includes(q)||(n.aliases||'').toLowerCase().includes(q));if(m){ox=W/2-m.x*scale;oy=H/2-m.y*scale;show(m)}});
function fit(){const V=N.filter(vis);if(!V.length)return;let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;V.forEach(n=>{x0=Math.min(x0,n.x-n.r);y0=Math.min(y0,n.y-n.r);x1=Math.max(x1,n.x+n.r+60);y1=Math.max(y1,n.y+n.r)});
const pad=40,top=document.getElementById('top').offsetHeight+24;scale=Math.min(2,Math.max(.1,Math.min((W-2*pad)/(x1-x0||1),(H-top-pad)/(y1-y0||1))));ox=pad+(W-2*pad-(x1-x0)*scale)/2-x0*scale;oy=top+(H-top-pad-(y1-y0)*scale)/2-y0*scale;draw()}
const fb=document.createElement('span');fb.className='chip';fb.textContent='Fit';fb.onclick=fit;document.getElementById('top').insertBefore(fb,lg);
size();for(let i=0;i<400;i++)tick();alpha=.05;fit();loop();
</script></body></html>"""


def render(gs: GraphStore, title: str = "Agora") -> str:
    from .build import stats, to_networkx
    import networkx as nx
    g = to_networkx(gs)
    data = nx.node_link_data(g, edges="links")
    for n in data["nodes"]:
        n["description"] = (n.get("description") or "")[:600]
    data["meta"] = stats(gs)
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return (TEMPLATE.replace("__TITLE__", title.replace("<", "&lt;"))
            .replace("__DATA__", blob).replace("__COLORS__", json.dumps(PALETTE)))


def write(gs: GraphStore, path: str | Path, title: str = "Agora") -> Path:
    path = Path(path)
    path.write_text(render(gs, title), encoding="utf-8")
    return path
