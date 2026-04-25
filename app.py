import os, requests, time
from flask import Flask, request, session, redirect, jsonify
from werkzeug.utils import secure_filename
from urllib.parse import quote, urlparse

IA_BUCKET = os.getenv("IA_BUCKET", "junk-manage-caution")
IA_ACCESS = os.getenv("IA_ACCESS_KEY", "")
IA_SECRET = os.getenv("IA_SECRET_KEY", "")
LOGIN_PIN = os.getenv("LOGIN_PIN", "2383")
ENDPOINT = "https://s3.us.archive.org"
WORKER = os.getenv("WORKER_MEDIA_BASE", "").rstrip("/")
AUTH = f"LOW {IA_ACCESS}:{IA_SECRET}"

app = Flask(__name__)
app.secret_key = "ia-2026"

def ia_list():
    try:
        r = requests.get(f"https://archive.org/metadata/{IA_BUCKET}", timeout=15)
        out=[]
        for f in r.json().get("files",[]):
            n=f.get("name","")
            if n and not n.startswith("_") and n!="history":
                url=f"{WORKER}/{IA_BUCKET}/{quote(n)}" if WORKER else f"https://archive.org/download/{IA_BUCKET}/{quote(n)}"
                out.append({"name":n,"size":int(f.get("size",0)),"url":url})
        return sorted(out,key=lambda x:x["name"].lower())
    except: return []

def ia_put(key,data,ctype):
    h={"authorization":AUTH,"x-amz-auto-make-bucket":"1","x-archive-auto-make-bucket":"1","x-archive-meta01-collection":"opensource","Content-Type":ctype or "application/octet-stream"}
    requests.put(f"{ENDPOINT}/{IA_BUCKET}/{key}",data=data,headers=h,timeout=900)

@app.before_request
def gate():
    if request.path.startswith(("/login","/health")): return
    if request.path.startswith("/api") and not session.get("ok"): return jsonify(error="auth"),401
    if not session.get("ok") and not request.path.startswith("/file"): return redirect("/login")

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST" and request.form.get("pin")==LOGIN_PIN:
        session["ok"]=True;return redirect("/")
    return '<form method=post style="margin:100px auto;width:300px;font-family:sans-serif"><h2>IA Drive</h2><input name=pin type=password placeholder=PIN style="width:100%;padding:10px"><button style="width:100%;padding:10px;margin-top:10px">Login</button></form>'

@app.route("/")
def home():
    return """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>IA Drive</title>
<link rel=stylesheet href=https://cdnjs.cloudflare.com/ajax/libs/remixicon/4.2.0/remixicon.min.css>
<style>:root{--bg:#020617;--s:#0f172a;--b:#1e293b;--m:#64748b;--a:#3b82f6}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#e2e8f0;font-family:system-ui}
.app{display:flex}.side{width:240px;background:var(--s);height:100vh;position:fixed;left:0;top:0;padding:16px;border-right:1px solid var(--b);overflow:auto}
.logo{display:flex;align-items:center;gap:8px;font-weight:700;margin-bottom:20px}.logo i{color:var(--a)}
.nav a{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:8px;color:#cbd5e1;text-decoration:none;margin:2px 0;cursor:pointer;font-size:14px}
.nav a.on,.nav a:hover{background:#1e293b;color:#fff}.nav a span{margin-left:auto;font-size:12px;color:var(--m)}
.main{margin-left:240px;flex:1;min-height:100vh}
.top{padding:14px 20px;border-bottom:1px solid var(--b);background:#020617cc;position:sticky;top:0;backdrop-filter:blur(8px);display:flex;align-items:center;gap:12px}
.burger{display:none;background:none;border:0;color:#fff;font-size:22px;cursor:pointer}
.view{padding:20px}
.upload{display:grid;place-items:center;min-height:calc(100vh - 80px)}
.box{background:var(--s);border:1px solid var(--b);border-radius:16px;padding:40px;max-width:640px;width:100%;text-align:center}
.drop{border:2px dashed #334155;border-radius:12px;padding:48px 20px;cursor:pointer;margin:20px 0}
.drop.drag{border-color:var(--a);background:#1e293b50}
.url{display:flex;gap:8px;max-width:460px;margin:0 auto}.url input{flex:1;padding:11px;background:#000;border:1px solid #334155;border-radius:8px;color:#fff}
.btn{padding:11px 16px;background:var(--a);border:0;border-radius:8px;color:#fff;font-weight:600;cursor:pointer}
.files{display:none}.search{display:flex;gap:8px;margin-bottom:16px}.search input{flex:1;max-width:400px;padding:10px;background:var(--s);border:1px solid var(--b);border-radius:8px;color:#fff}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px}
.card{background:var(--s);border:1px solid var(--b);border-radius:10px;overflow:hidden;text-decoration:none;color:inherit}
.thumb{aspect-ratio:16/10;background:#000;display:grid;place-items:center}.thumb img,.thumb video{width:100%;height:100%;object-fit:cover}.thumb i{font-size:30px;opacity:.6}
.info{padding:8px}.name{font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.meta{font-size:11px;color:var(--m);display:flex;justify-content:space-between;margin-top:2px}
.modal{position:fixed;inset:0;background:#000a;display:none;place-items:center;z-index:50}.modal.show{display:grid}.modal>div{background:var(--s);border:1px solid var(--b);padding:20px;border-radius:12px;width:90%;max-width:380px}
.progress{height:4px;background:#000;border-radius:4px;overflow:hidden;margin:10px 0}.progress div{height:100%;background:var(--a);width:0%}
.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:var(--s);border:1px solid var(--b);padding:10px 16px;border-radius:8px;display:none}
@media(max-width:900px){.side{transform:translateX(-100%);transition:.25s;z-index:40}.side.show{transform:translateX(0)}.main{margin-left:0}.burger{display:block}}
</style></head><body>
<div class=app>
 <div id=side class=side>
  <div class=logo><i class="ri-hard-drive-3-fill"></i> IA Drive</div>
  <div class=nav>
   <a class=on data-v=upload><i class="ri-upload-line"></i> Upload</a>
   <a data-v=files data-f=all><i class="ri-folder-line"></i> All Files <span id=c-all>0</span></a>
   <a data-v=files data-f=video><i class="ri-vidicon-line"></i> Videos <span id=c-video>0</span></a>
   <a data-v=files data-f=image><i class="ri-image-line"></i> Images <span id=c-image>0</span></a>
   <a data-v=files data-f=audio><i class="ri-music-line"></i> Audio <span id=c-audio>0</span></a>
   <a data-v=files data-f=doc><i class="ri-file-line"></i> Docs <span id=c-doc>0</span></a>
  </div>
 </div>
 <div class=main>
  <div class=top><button class=burger onclick="side.classList.toggle('show')"><i class="ri-menu-line"></i></button><div id=ttl style="font-weight:600">Upload</div></div>
  <div class=view>
   <div id=v-upload class=upload>
    <div class=box>
     <h2 style="margin:0 0 6px">Upload to IA Drive</h2>
     <p style="color:var(--m);margin:0 0 20px;font-size:14px">Permanent free storage</p>
     <div id=drop class=drop><i class="ri-upload-cloud-2-line" style="font-size:40px;color:var(--a)"></i><div style="margin-top:8px">Drop files here or click</div></div>
     <div class=url><input id=url placeholder="Paste URL..."><button class=btn onclick="fetchUrl()">Fetch</button></div>
     <input id=fi type=file multiple hidden>
    </div>
   <div id=v-files class=files>
    <div class=search><input id=q placeholder="Search files"><button class=btn onclick="load()" style="background:var(--s);border:1px solid var(--b)">Refresh</button></div>
    <div id=grid class=grid></div>
   </div>
  </div>
 </div>
</div>
<div id=modal class=modal><div><div id=mt style="font-weight:600;margin-bottom:6px">Uploading</div><div id=ms style="font-size:13px;color:var(--m)">...</div><div class=progress><div id=mb></div></div><div id=ml style="font-size:12px;color:var(--m);max-height:120px;overflow:auto;margin-top:8px"></div></div></div>
<div id=toast class=toast></div>
<script>
let files=[],view='upload',filter='all';
const types={video:['mp4','webm','mov','mkv'],image:['png','jpg','jpeg','gif','webp','svg'],audio:['mp3','wav','flac','m4a','ogg'],doc:['pdf','doc','docx','txt','md','xls','xlsx','ppt','pptx']};
function toast(t){const e=document.getElementById('toast');e.textContent=t;e.style.display='block';setTimeout(()=>e.style.display='none',2000)}
function setView(v,f){view=v;filter=f||'all';document.querySelectorAll('.nav a').forEach(a=>a.classList.remove('on'));document.querySelector(`[data-v="${v}"]${f?`[data-f="${f}"]`:''}`).classList.add('on');document.getElementById('v-upload').style.display=v==='upload'?'grid':'none';document.getElementById('v-files').style.display=v==='files'?'block':'none';document.getElementById('ttl').textContent=v==='upload'?'Upload':(f?f.charAt(0).toUpperCase()+f.slice(1):'Files');if(v==='files')load();if(window.innerWidth<900)side.classList.remove('show')}
document.querySelectorAll('.nav a').forEach(a=>a.onclick=()=>setView(a.dataset.v,a.dataset.f));
function ext(n){return n.split('.').pop().toLowerCase()}
function kind(n){const e=ext(n);for(const k in types)if(types[k].includes(e))return k;return'other'}
function fmt(b){return b>1e9?(b/1e9).toFixed(1)+'GB':b>1e6?(b/1e6).toFixed(1)+'MB':Math.round(b/1024)+'KB'}
async function load(){try{const r=await fetch('/api/list');files=await r.json();const c={all:files.length,video:0,image:0,audio:0,doc:0};files.forEach(f=>{const k=kind(f.name);if(c[k]!=null)c[k]++});Object.keys(c).forEach(k=>document.getElementById('c-'+k).textContent=c[k]);render()}catch(e){toast('Load failed')}}
function render(){const q=document.getElementById('q').value.toLowerCase();const list=files.filter(f=>(filter==='all'||kind(f.name)===filter)&&f.name.toLowerCase().includes(q));const g=document.getElementById('grid');g.innerHTML='';if(!list.length){g.innerHTML='<div style="grid-column:1/-1;padding:40px;text-align:center;color:var(--m)">No files</div>';return}list.forEach(f=>{const e=ext(f.name);const isI=types.image.includes(e);const isV=types.video.includes(e);const th=isI?`<img src="${f.url}" loading="lazy">`:isV?`<video src="${f.url}#t=0.5" muted></video>`:`<i class="ri-file-line"></i>`;g.innerHTML+=`<a class=card href="/file/${encodeURIComponent(f.name)}"><div class=thumb>${th}</div><div class=info><div class=name>${f.name}</div><div class=meta><span>${e.toUpperCase()}</span><span>${fmt(f.size)}</span></div></div></a>`})}
async function up(f){const d=new FormData();d.append('file',f);const r=await fetch('/api/upload',{method:'POST',body:d});if(!r.ok)throw''}
async function handle(list){if(!list.length)return;modal.classList.add('show');ml.innerHTML='';let ok=0;for(let i=0;i<list.length;i++){const f=list[i];ms.textContent=`${i+1}/${list.length} ${f.name}`;mb.style.width=(i/list.length*100)+'%';ml.innerHTML+=`<div>• ${f.name}</div>`;try{await up(f);ok++;ml.lastChild.innerHTML+=' ✓'}catch{ml.lastChild.innerHTML+=' ✗'}}mb.style.width='100%';ms.textContent=`Done ${ok}/${list.length}`;setTimeout(()=>{modal.classList.remove('show');toast(ok+' uploaded');load()},900)}
async function fetchUrl(){const u=url.value.trim();if(!u)return;modal.classList.add('show');mt.textContent='Fetching';ms.textContent=u;mb.style.width='30%';try{await fetch('/api/upload-url',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:u})});mb.style.width='100%';ms.textContent='Done';setTimeout(()=>{modal.classList.remove('show');url.value='';toast('Fetched');load()},700)}catch{modal.classList.remove('show');toast('Failed')}}
const drop=document.getElementById('drop'),fi=document.getElementById('fi');drop.onclick=()=>fi.click();drop.ondragover=e=>{e.preventDefault();drop.classList.add('drag')};drop.ondragleave=()=>drop.classList.remove('drag');drop.ondrop=e=>{e.preventDefault();drop.classList.remove('drag');handle([...e.dataTransfer.files])};fi.onchange=()=>handle([...fi.files]);document.getElementById('q').oninput=render;setView('upload');load();
</script></body></html>"""

@app.route("/file/<path:name>")
def view(name):
    f=next((x for x in ia_list() if x["name"]==name),None)
    if not f: return "404",404
    u=f["url"];e=name.rsplit(".",1)[-1].lower() if "." in name else ""
    p=f'<video controls src="{u}" style="width:100%;max-height:85vh;background:#000"></video>' if e in ("mp4","webm","mov") else f'<img src="{u}" style="max-width:100%;max-height:85vh">' if e in ("png","jpg","jpeg","gif","webp") else f'<iframe src="https://mozilla.github.io/pdf.js/web/viewer.html?file={quote(u)}" style="width:100%;height:85vh;border:0"></iframe>' if e=="pdf" else f'<a href="{u}" download style="padding:12px 20px;background:#3b82f6;color:#fff;border-radius:8px;text-decoration:none;display:inline-block;margin:50px">Download</a>'
    return f'<div style="background:#020617;color:#fff;min-height:100vh;font-family:system-ui"><div style="padding:12px 16px;border-bottom:1px solid #1e293b;display:flex;gap:10px;align-items:center"><a href="/" style="color:#94a3b8;text-decoration:none">← Back</a><div style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{name}</div><a href="{u}" download style="padding:8px 12px;background:#0f172a;border:1px solid #1e293b;border-radius:8px;color:#fff;text-decoration:none">Download</a></div><div style="max-width:1200px;margin:20px auto;padding:0 16px">{p}</div></div>'

@app.route("/api/list")
def api_list(): return jsonify(ia_list())

@app.route("/api/upload",methods=["POST"])
def api_up():
    f=request.files["file"]; ia_put(secure_filename(f.filename),f.stream,f.content_type); return "",200

@app.route("/api/upload-url",methods=["POST"])
def api_url():
    u=request.get_json().get("url",""); r=requests.get(u,stream=True,timeout=120); n=secure_filename(urlparse(u).path.split("/")[-1] or f"file-{int(time.time())}"); ia_put(n,r.raw,r.headers.get("Content-Type")); return "",200

@app.route("/health")
def health(): return "ok"

if __name__=="__main__": app.run(host="0.0.0.0",port=8080)
