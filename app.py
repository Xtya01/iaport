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
app.secret_key = "ia-drive-2026"

def ia_list():
    try:
        r = requests.get(f"https://archive.org/metadata/{IA_BUCKET}", timeout=12)
        out = []
        for f in r.json().get("files", []):
            n = f.get("name", "")
            if n and not n.startswith("_"):
                url = f"{WORKER}/{IA_BUCKET}/{quote(n)}" if WORKER else f"https://archive.org/download/{IA_BUCKET}/{quote(n)}"
                out.append({"name": n, "size": int(f.get("size",0)), "url": url})
        return sorted(out, key=lambda x: x["name"].lower())
    except: return []

def ia_put(key, data, ctype):
    h = {"authorization": AUTH, "x-amz-auto-make-bucket":"1", "x-archive-auto-make-bucket":"1", "x-archive-meta01-collection":"opensource", "x-archive-meta-mediatype":"data", "Content-Type": ctype or "application/octet-stream"}
    requests.put(f"{ENDPOINT}/{IA_BUCKET}/{key}", data=data, headers=h, timeout=900)

@app.before_request
def gate():
    if request.path.startswith(("/login","/health")): return
    if request.path.startswith(("/api","/file")):
        if request.path.startswith("/api") and not session.get("ok"): return jsonify(error="auth"),401
        return
    if not session.get("ok"): return redirect("/login")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST" and request.form.get("pin")==LOGIN_PIN:
        session["ok"]=True; return redirect("/")
    return '''<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>IA Drive</title>
<style>body{margin:0;height:100vh;display:grid;place-items:center;background:#020617;color:#e2e8f0;font-family:system-ui}.b{width:340px;background:#0b1220;border:1px solid #1e293b;padding:36px;border-radius:18px}input{width:100%;padding:13px;background:#000;border:1px solid #334155;border-radius:10px;color:#fff;margin:14px 0}button{width:100%;padding:13px;background:#3b82f6;border:0;border-radius:10px;color:#fff;font-weight:600}</style>
</head><body><div class=b><h2 style="margin:0 0 6px">IA Drive</h2><p style="margin:0 0 18px;color:#64748b;font-size:14px">Enter PIN</p><form method=post><input name=pin type=password autofocus placeholder="PIN"><button>Unlock</button></form></div></body></html>'''

@app.route("/")
def home():
    return '''<!doctype html><html><head><meta charset=utf-8><title>IA Drive - Upload</title><meta name=viewport content="width=device-width,initial-scale=1">
<link rel=stylesheet href=https://cdnjs.cloudflare.com/ajax/libs/remixicon/4.2.0/remixicon.min.css>
<style>:root{--bg:#020617;--s:#0b1220;--b:#1e293b;--m:#64748b;--a:#3b82f6}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#e2e8f0;font-family:ui-sans-serif,system-ui}.app{display:flex;min-height:100vh}
.side{width:260px;background:var(--s);border-right:1px solid var(--b);padding:20px;position:fixed;left:0;top:0;bottom:0;overflow:auto;transition:transform.25s;z-index:40}
.logo{font-weight:700;font-size:18px;display:flex;align-items:center;gap:8px;margin-bottom:24px}.logo i{color:var(--a)}
.nav a{display:flex;align-items:center;gap:10px;padding:11px 12px;border-radius:10px;color:#cbd5e1;text-decoration:none;font-size:14px;margin:3px 0;cursor:pointer}
.nav a:hover,.nav a.on{background:#111a2e;color:#fff}.nav a i{font-size:19px}.nav span{margin-left:auto;font-size:12px;color:var(--m)}
.main{flex:1;margin-left:260px;min-height:100vh;display:flex;flex-direction:column}
.top{padding:16px 24px;border-bottom:1px solid var(--b);display:flex;align-items:center;gap:12px}
.burger{display:none;background:none;border:0;color:#cbd5e1;font-size:22px;padding:6px;cursor:pointer}
.content{flex:1;display:grid;place-items:center;padding:24px}
.upload-box{width:100%;max-width:720px;background:var(--s);border:1px solid var(--b);border-radius:24px;padding:48px;text-align:center}
.upload-box h1{margin:0 0 8px;font-size:28px;font-weight:700}.upload-box p{margin:0 0 32px;color:var(--m)}
.drop{border:2px dashed #334155;border-radius:16px;padding:60px 20px;cursor:pointer;transition:.2s;margin-bottom:24px}
.drop:hover,.drop.drag{border-color:var(--a);background:#0b1220cc;transform:scale(1.01)}
.drop i{font-size:48px;color:var(--a);opacity:.8}.drop h3{margin:16px 0 6px;font-size:18px}.drop p{margin:0;color:var(--m);font-size:14px}
.url-row{display:flex;gap:10px;max-width:520px;margin:0 auto}.url-row input{flex:1;padding:13px 16px;background:#020617;border:1px solid #334155;border-radius:12px;color:#fff;font-size:14px;outline:none}.url-row input:focus{border-color:var(--a)}.btn{padding:13px 20px;background:var(--a);border:0;border-radius:12px;color:#fff;font-weight:600;cursor:pointer;font-size:14px;white-space:nowrap}.btn:hover{background:#2563eb}
.files-view{padding:24px;display:none}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px;margin-top:20px}
.card{background:var(--s);border:1px solid var(--b);border-radius:14px;overflow:hidden;text-decoration:none;color:inherit;display:block}.card:hover{transform:translateY(-2px);border-color:#334155}
.thumb{aspect-ratio:16/10;background:#000;display:grid;place-items:center;overflow:hidden}.thumb img,.thumb video{width:100%;height:100%;object-fit:cover}.thumb i{font-size:34px;opacity:.5}
.info{padding:10px}.name{font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.meta{font-size:11px;color:var(--m);margin-top:3px;display:flex;justify-content:space-between}
.overlay{position:fixed;inset:0;background:#0008;display:none;z-index:30}.overlay.show{display:block}
.modal{position:fixed;inset:0;display:none;place-items:center;z-index:100;background:#0008;backdrop-filter:blur(4px)}.modal.show{display:grid}
.modal-box{background:var(--s);border:1px solid var(--b);border-radius:18px;width:90%;max-width:440px;padding:26px}
.progress{height:6px;background:#020617;border-radius:6px;overflow:hidden;margin:14px 0}.progress>div{height:100%;background:var(--a);width:0%;transition:width .2s}
.toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--s);border:1px solid var(--b);padding:12px 18px;border-radius:12px;z-index:200;font-size:13px;box-shadow:0 10px 30px #0008;display:none}
@media(max-width:900px){.side{transform:translateX(-100%)}.side.show{transform:translateX(0)}.main{margin-left:0}.burger{display:block}.upload-box{padding:32px 20px}.content{padding:16px}}
</style>
</head><body>
<div class=app>
  <aside id=side class=side>
    <div class=logo><i class="ri-hard-drive-3-fill"></i> IA Drive</div>
    <div class=nav>
      <a class=on data-view=upload><i class="ri-upload-cloud-2-line"></i> Upload</a>
      <a data-view=files data-filter=all><i class="ri-folder-2-line"></i> All Files <span id=c-all>0</span></a>
      <a data-view=files data-filter=video><i class="ri-film-line"></i> Videos <span id=c-video>0</span></a>
      <a data-view=files data-filter=image><i class="ri-image-line"></i> Images <span id=c-image>0</span></a>
      <a data-view=files data-filter=audio><i class="ri-music-2-line"></i> Audio <span id=c-audio>0</span></a>
      <a data-view=files data-filter=pdf><i class="ri-file-pdf-line"></i> Documents <span id=c-pdf>0</span></a>
    </div>
  </aside>
  <div id=ov class=overlay onclick="toggleSide()"></div>
  <main class=main>
    <div class=top>
      <button class=burger onclick="toggleSide()"><i class="ri-menu-line"></i></button>
      <div style="font-weight:600" id=page-title>Upload Files</div>
    </div>
    
    <!-- UPLOAD VIEW -->
    <div id=upload-view class=content>
      <div class=upload-box>
        <h1>Upload to Internet Archive</h1>
        <p>Files are stored permanently and free</p>
        <div id=drop class=drop>
          <i class="ri-upload-cloud-2-fill"></i>
          <h3>Drop files here</h3>
          <p>or click to browse</p>
        </div>
        <div class=url-row>
          <input id=url placeholder="Or paste a direct URL...">
          <button class=btn onclick="fetchUrl()">Fetch URL</button>
        </div>
        <input id=fi type=file multiple hidden>
      </div>
    </div>
    
    <!-- FILES VIEW -->
    <div id=files-view class=files-view>
      <div style="display:flex;gap:10px;align-items:center;margin-bottom:16px">
        <input id=q placeholder="Search files..." style="flex:1;max-width:400px;padding:10px 14px;background:var(--s);border:1px solid var(--b);border-radius:10px;color:#fff;outline:none">
        <button class=btn onclick="loadFiles()" style="padding:10px 14px;background:var(--s);border:1px solid var(--b)"><i class="ri-refresh-line"></i></button>
      </div>
      <div id=grid class=grid></div>
    </div>
  </main>
</div>

<div id=modal class=modal><div class=modal-box>
  <h3 style="margin:0 0 8px" id=m-title>Uploading</h3>
  <div id=m-status style="color:var(--m);font-size:13px">Preparing...</div>
  <div class=progress><div id=m-bar></div></div>
  <div id=m-list style="max-height:180px;overflow:auto;font-size:12px;color:var(--m);margin-top:10px"></div>
</div></div>
<div id=toast class=toast></div>

<script>
let files=[], currentView='upload', currentFilter='all';
const types={video:['mp4','webm','mov','mkv'],audio:['mp3','wav','flac','m4a'],image:['png','jpg','jpeg','gif','webp','svg'],pdf:['pdf','doc','docx','xls','xlsx','ppt','pptx','txt','md']};
function toggleSide(){side.classList.toggle('show');ov.classList.toggle('show')}
function showView(v,f){currentView=v;currentFilter=f||'all';document.querySelectorAll('.nav a').forEach(a=>a.classList.remove('on'));document.querySelector(`[data-view="${v}"]${f?`[data-filter="${f}"]`:''}`)?.classList.add('on');uploadView.style.display=v==='upload'?'grid':'none';filesView.style.display=v==='files'?'block':'none';pageTitle.textContent=v==='upload'?'Upload Files':f?f.charAt(0).toUpperCase()+f.slice(1):'Files';if(v==='files')loadFiles();if(window.innerWidth<900)toggleSide()}
document.querySelectorAll('.nav a').forEach(a=>a.onclick=()=>showView(a.dataset.view,a.dataset.filter));
function toast(m){toastEl.textContent=m;toastEl.style.display='block';setTimeout(()=>toastEl.style.display='none',2500)}
function ext(n){return n.split('.').pop().toLowerCase()}
function kind(n){const e=ext(n);for(const k in types)if(types[k].includes(e))return k;return 'other'}
function fmt(b){return b>1e9?(b/1e9).toFixed(1)+'GB':b>1e6?(b/1e6).toFixed(1)+'MB':(b/1e3).toFixed(0)+'KB'}
async function loadFiles(){files=await(await fetch('/api/list')).json();const c={all:files.length};for(const k in types)c[k]=0;files.forEach(f=>{const k=kind(f.name);if(c[k]!=null)c[k]++});for(const k in c){const e=document.getElementById('c-'+k);if(e)e.textContent=c[k]};renderFiles()}
function renderFiles(){const t=q.value.toLowerCase();const list=files.filter(f=>(currentFilter==='all'||kind(f.name)===currentFilter)&&f.name.toLowerCase().includes(t));grid.innerHTML=list.length?'':'<div style="grid-column:1/-1;text-align:center;padding:60px;color:var(--m)">No files</div>';list.forEach(f=>{const e=ext(f.name);const isI=types.image.includes(e);const isV=types.video.includes(e);const th=isI?'<img src="'+f.url+'" loading=lazy>':isV?'<video src="'+f.url+'#t=0.5" muted></video>':'<i class="ri-file-line"></i>';grid.innerHTML+='<a class=card href="/file/'+encodeURIComponent(f.name)+'"><div class=thumb>'+th+'</div><div class=info><div class=name>'+f.name+'</div><div class=meta><span>'+e.toUpperCase()+'</span><span>'+fmt(f.size)+'</span></div></div></a>'})}
async function up(file){const fd=new FormData();fd.append('file',file);const r=await fetch('/api/upload',{method:'POST',body:fd});if(!r.ok)throw new Error()}
async function handle(list){if(!list.length)return;modal.classList.add('show');mList.innerHTML='';let ok=0;for(let i=0;i<list.length;i++){const f=list[i];mStatus.textContent=`${i+1}/${list.length}: ${f.name}`;mBar.style.width=((i/list.length)*100)+'%';mList.innerHTML+=`<div>• ${f.name}</div>`;try{await up(f);ok++;mList.lastChild.innerHTML+=` <span style="color:#22c55e">✓</span>`}catch{mList.lastChild.innerHTML+=` <span style="color:#ef4444">✗</span>`}}mBar.style.width='100%';mStatus.textContent=`Done: ${ok}/${list.length}`;setTimeout(()=>{modal.classList.remove('show');toast(`${ok} file${ok!=1?'s':''} uploaded`);loadFiles()},1200)}
async function fetchUrl(){const u=url.value.trim();if(!u)return toast('Enter URL');if(!confirm('Fetch this URL?'))return;modal.classList.add('show');mStatus.textContent='Fetching...';mBar.style.width='30%';try{const r=await fetch('/api/upload-url',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:u})});mBar.style.width='100%';mStatus.textContent=r.ok?'Complete':'Failed';setTimeout(()=>{modal.classList.remove('show');if(r.ok){toast('URL fetched');url.value='';loadFiles()}else toast('Fetch failed')},800)}catch{modal.classList.remove('show');toast('Error')}}
drop.onclick=()=>fi.click();drop.ondragover=e=>{e.preventDefault();drop.classList.add('drag')};drop.ondragleave=()=>drop.classList.remove('drag');drop.ondrop=e=>{e.preventDefault();drop.classList.remove('drag');handle([...e.dataTransfer.files])};fi.onchange=()=>handle([...fi.files]);q.oninput=renderFiles;showView('upload')
</script></body></html>'''

@app.route("/file/<path:name>")
def view(name):
    f = next((x for x in ia_list() if x["name"]==name), None)
    if not f: return "Not found",404
    url = f["url"]; ext = name.rsplit(".",1)[-1].lower() if "." in name else ""; size = f"{f['size']/1024/1024:.1f} MB"
    if ext in ("mp4","webm","mov","mkv"): player = '<video controls style="width:100%;max-height:80vh;background:#000" src="'+url+'"></video>'
    elif ext in ("mp3","wav","flac","m4a"): player = '<audio controls style="width:100%" src="'+url+'"></audio>'
    elif ext in ("png","jpg","jpeg","gif","webp"): player = '<img src="'+url+'" style="max-width:100%;max-height:80vh;display:block;margin:auto">'
    elif ext=="pdf": player = '<iframe src="https://mozilla.github.io/pdf.js/web/viewer.html?file='+quote(url)+'" style="width:100%;height:85vh;border:0"></iframe>'
    else: player = '<div style="padding:80px;text-align:center"><a href="'+url+'" download style="padding:12px 20px;background:#3b82f6;color:#fff;border-radius:10px;text-decoration:none">Download</a></div>'
    return '<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>'+name+'</title><style>body{margin:0;background:#020617;color:#fff;font-family:system-ui}.t{padding:12px 16px;border-bottom:1px solid #1e293b;display:flex;gap:10px;align-items:center;position:sticky;top:0;background:#020617}.b{padding:8px 12px;background:#0b1220;border:1px solid #1e293b;border-radius:8px;color:#ccc;text-decoration:none}.w{max-width:1200px;margin:20px auto;padding:0 16px}.p{background:#0b1220;border:1px solid #1e293b;border-radius:14px;overflow:hidden}</style></head><body><div class=t><a href="/" class=b>← Back</a><div style="flex:1;font-weight:600;overflow:hidden;text-overflow:ellipsis">'+name+'</div><button class=b onclick="dl()">Download</button></div><div class=w><div class=p>'+player+'</div></div><script>function dl(){const a=document.createElement("a");a.href="'+url+'";a.download="'+name+'";a.click()}</script></body></html>'''

@app.route("/api/list")
def api_list(): return jsonify(ia_list())

@app.route("/api/upload", methods=["POST"])
def api_up():
    f = request.files["file"]
    ia_put(secure_filename(f.filename), f.stream, f.content_type)
    return "",200

@app.route("/api/upload-url", methods=["POST"])
def api_url():
    u = request.get_json().get("url","")
    try:
        r = requests.get(u, stream=True, timeout=60)
        name = secure_filename(urlparse(u).path.split("/")[-1] or f"file-{int(time.time())}")
        ia_put(name, r.raw, r.headers.get("Content-Type"))
        return "",200
    except: return "",500

@app.route("/health")
def health(): return "ok"

if __name__=="__main__": app.run(host="0.0.0.0",port=8080)
