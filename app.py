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
        r = requests.get(f"https://archive.org/metadata/{IA_BUCKET}", timeout=15)
        data = r.json()
        out = []
        for f in data.get("files", []):
            n = f.get("name", "")
            if n and not n.startswith("_") and n!= "history":
                url = f"{WORKER}/{IA_BUCKET}/{quote(n)}" if WORKER else f"https://archive.org/download/{IA_BUCKET}/{quote(n)}"
                out.append({"name": n, "size": int(f.get("size",0)), "url": url})
        return sorted(out, key=lambda x: x["name"].lower())
    except Exception as e:
        print("List error:", e)
        return []

def ia_put(key, data, ctype):
    h = {"authorization": AUTH, "x-amz-auto-make-bucket":"1", "x-archive-auto-make-bucket":"1", "x-archive-meta01-collection":"opensource", "x-archive-meta-mediatype":"data", "Content-Type": ctype or "application/octet-stream"}
    r = requests.put(f"{ENDPOINT}/{IA_BUCKET}/{key}", data=data, headers=h, timeout=900)
    r.raise_for_status()

@app.before_request
def gate():
    if request.path.startswith(("/login","/health")): return
    if request.path.startswith(("/api","/file")):
        if request.path.startswith("/api") and not session.get("ok"): return jsonify({"error":"auth"}),401
        return
    if not session.get("ok"): return redirect("/login")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST" and request.form.get("pin")==LOGIN_PIN:
        session["ok"]=True
        return redirect("/")
    return '''<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Login</title>
<style>body{margin:0;height:100vh;display:grid;place-items:center;background:#020617;color:#fff;font-family:system-ui}.b{width:320px;background:#0b1220;padding:32px;border-radius:16px;border:1px solid #1e293b}input{width:100%;padding:12px;background:#000;border:1px solid #334155;border-radius:8px;color:#fff;margin:12px 0}button{width:100%;padding:12px;background:#3b82f6;border:0;border-radius:8px;color:#fff;font-weight:600;cursor:pointer}</style>
</head><body><div class=b><h2>IA Drive</h2><form method=post><input name=pin type=password placeholder="PIN" autofocus><button>Unlock</button></form></div></body></html>'''

@app.route("/")
def home():
    html = """<!doctype html><html><head><meta charset=utf-8><title>IA Drive</title><meta name=viewport content="width=device-width,initial-scale=1">
<link rel=stylesheet href=https://cdnjs.cloudflare.com/ajax/libs/remixicon/4.2.0/remixicon.min.css>
<style>:root{--bg:#020617;--s:#0b1220;--b:#1e293b;--m:#64748b;--a:#3b82f6}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#e2e8f0;font-family:system-ui}.app{display:flex;min-height:100vh}
.side{width:250px;background:var(--s);border-right:1px solid var(--b);padding:18px;position:fixed;left:0;top:0;bottom:0;overflow:auto;z-index:40;transition:transform.25s}
.logo{font-weight:700;font-size:17px;display:flex;gap:8px;align-items:center;margin-bottom:20px}.logo i{color:var(--a)}
.nav a{display:flex;align-items:center;gap:10px;padding:10px 12px;margin:2px 0;border-radius:9px;color:#cbd5e1;text-decoration:none;cursor:pointer;font-size:14px}
.nav a:hover,.nav a.on{background:#111a2e;color:#fff}.nav a span{margin-left:auto;font-size:11px;color:var(--m)}
.main{flex:1;margin-left:250px;min-height:100vh}
.top{padding:14px 20px;border-bottom:1px solid var(--b);display:flex;align-items:center;gap:12px;position:sticky;top:0;background:#020617cc;backdrop-filter:blur(10px);z-index:20}
.burger{display:none;background:none;border:0;color:#fff;font-size:22px;cursor:pointer;padding:4px}
.content{padding:24px}
.upload-wrap{display:grid;place-items:center;min-height:calc(100vh - 70px)}
.upload-box{width:100%;max-width:680px;background:var(--s);border:1px solid var(--b);border-radius:20px;padding:40px;text-align:center}
.upload-box h1{margin:0 0 8px;font-size:26px}.upload-box p{margin:0 0 28px;color:var(--m);font-size:14px}
.drop{border:2px dashed #334155;border-radius:14px;padding:50px 20px;cursor:pointer;margin-bottom:20px;transition:.2s}
.drop:hover,.drop.drag{border-color:var(--a);background:#0b1220}
.drop i{font-size:44px;color:var(--a)}
.url-row{display:flex;gap:8px;max-width:480px;margin:0 auto}.url-row input{flex:1;padding:12px;background:#000;border:1px solid #334155;border-radius:10px;color:#fff}.btn{padding:12px 18px;background:var(--a);border:0;border-radius:10px;color:#fff;font-weight:600;cursor:pointer}
.files-wrap{display:none}.search-bar{display:flex;gap:10px;margin-bottom:18px}.search-bar input{flex:1;max-width:420px;padding:10px 14px;background:var(--s);border:1px solid var(--b);border-radius:10px;color:#fff}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px}
.card{background:var(--s);border:1px solid var(--b);border-radius:12px;overflow:hidden;text-decoration:none;color:inherit;display:block}
.card:hover{transform:translateY(-2px);border-color:#334155}
.thumb{aspect-ratio:16/10;background:#000;display:grid;place-items:center}.thumb img,.thumb video{width:100%;height:100%;object-fit:cover}.thumb i{font-size:32px;opacity:.5}
.info{padding:9px}.name{font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.meta{font-size:11px;color:var(--m);display:flex;justify-content:space-between;margin-top:2px}
.modal{position:fixed;inset:0;background:#000a;backdrop-filter:blur(3px);display:none;place-items:center;z-index:100}
.modal.show{display:grid}.modal-box{background:var(--s);border:1px solid var(--b);border-radius:14px;padding:22px;width:90%;max-width:400px}
.progress{height:5px;background:#000;border-radius:5px;overflow:hidden;margin:12px 0}.progress div{height:100%;background:var(--a);width:0%;transition:width.2s}
.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:var(--s);border:1px solid var(--b);padding:10px 16px;border-radius:10px;font-size:13px;display:none;z-index:200}
.overlay{position:fixed;inset:0;background:#0006;display:none;z-index:30}.overlay.show{display:block}
@media(max-width:900px){.side{transform:translateX(-100%)}.side.show{transform:translateX(0)}.main{margin-left:0}.burger{display:block}.upload-box{padding:28px 18px}}
</style></head><body>
<div class=app>
 <aside id=side class=side>
  <div class=logo><i class="ri-hard-drive-3-fill"></i> IA Drive</div>
  <div class=nav>
   <a class=on data-v=upload><i class="ri-upload-cloud-2-line"></i> Upload</a>
   <a data-v=files data-f=all><i class="ri-folder-line"></i> All Files <span id=c-all>0</span></a>
   <a data-v=files data-f=video><i class="ri-film-line"></i> Videos <span id=c-video>0</span></a>
   <a data-v=files data-f=image><i class="ri-image-line"></i> Images <span id=c-image>0</span></a>
   <a data-v=files data-f=audio><i class="ri-music-2-line"></i> Audio <span id=c-audio>0</span></a>
   <a data-v=files data-f=doc><i class="ri-file-text-line"></i> Docs <span id=c-doc>0</span></a>
  </div>
 </aside>
 <div id=ov class=overlay onclick="toggleNav()"></div>
 <main class=main>
  <div class=top><button class=burger onclick="toggleNav()"><i class="ri-menu-line"></i></button><div id=title style="font-weight:600">Upload</div></div>
  <div class=content>
   <div id=uploadView class=upload-wrap>
    <div class=upload-box>
     <h1>Upload Files</h1><p>Permanent storage on Internet Archive</p>
     <div id=drop class=drop><i class="ri-upload-cloud-2-fill"></i><div style="margin-top:10px;font-weight:500">Drop files here</div><div style="font-size:13px;color:var(--m);margin-top:4px">or click to browse</div></div>
     <div class=url-row><input id=urlInp placeholder="Paste direct URL..."><button class=btn onclick="doUrl()">Fetch</button></div>
     <input id=fileInp type=file multiple hidden>
    </div>
   <div id=filesView class=files-wrap>
    <div class=search-bar><input id=search placeholder="Search..."><button class=btn onclick="loadFiles()" style="padding:10px 14px;background:var(--s);border:1px solid var(--b)">Refresh</button></div>
    <div id=grid class=grid></div>
   </div>
  </div>
 </main>
</div>
<div id=modal class=modal><div class=modal-box><h3 id=mTitle style="margin:0 0 6px">Uploading</h3><div id=mStatus style="font-size:13px;color:var(--m)">Starting...</div><div class=progress><div id=mBar></div></div><div id=mList style="font-size:12px;color:var(--m);max-height:150px;overflow:auto;margin-top:8px"></div></div></div>
<div id=toast class=toast></div>
<script>
let allFiles=[], view='upload', filter='all';
const types={video:['mp4','webm','mov','mkv','avi'],audio:['mp3','wav','flac','m4a','ogg'],image:['png','jpg','jpeg','gif','webp','svg'],doc:['pdf','txt','md','doc','docx','xls','xlsx','ppt','pptx']};
function $(id){return document.getElementById(id)}
function toggleNav(){side.classList.toggle('show');ov.classList.toggle('show')}
function showToast(t){toast.textContent=t;toast.style.display='block';setTimeout(()=>toast.style.display='none',2500)}
function setView(v,f){view=v;filter=f||'all';document.querySelectorAll('.nav a').forEach(a=>a.classList.remove('on'));document.querySelector(`[data-v="${v}"]${f?`[data-f="${f}"]`:''}`).classList.add('on');uploadView.style.display=v==='upload'?'grid':'none';filesView.style.display=v==='files'?'block':'none';title.textContent=v==='upload'?'Upload':(f?f.charAt(0).toUpperCase()+f.slice(1):'Files');if(v==='files')loadFiles();if(window.innerWidth<900)toggleNav()}
document.querySelectorAll('.nav a').forEach(a=>a.onclick=()=>setView(a.dataset.v,a.dataset.f));
function ext(n){return n.split('.').pop().toLowerCase()}
function kind(n){const e=ext(n);for(const k in types)if(types[k].includes(e))return k;return 'other'}
function fmt(b){return b>1e9?(b/1e9).toFixed(1)+' GB':b>1e6?(b/1e6).toFixed(1)+' MB':(b/1e3).toFixed(0)+' KB'}
async function loadFiles(){try{const r=await fetch('/api/list');allFiles=await r.json();const counts={all:allFiles.length,video:0,image:0,audio:0,doc:0};allFiles.forEach(f=>{const k=kind(f.name);if(counts[k]!=null)counts[k]++});Object.keys(counts).forEach(k=>{const el=$('c-'+k);if(el)el.textContent=counts[k]});renderFiles()}catch(e){showToast('Failed to load files')}}
function renderFiles(){const q=search.value.toLowerCase();const list=allFiles.filter(f=>(filter==='all'||kind(f.name)===filter)&&f.name.toLowerCase().includes(q));grid.innerHTML='';if(!list.length){grid.innerHTML='<div style="grid-column:1/-1;text-align:center;padding:50px;color:var(--m)">No files found</div>';return}list.forEach(f=>{const e=ext(f.name);const isImg=types.image.includes(e);const isVid=types.video.includes(e);const thumb=isImg?`<img src="${f.url}" loading="lazy">`:isVid?`<video src="${f.url}#t=0.5" muted></video>`:`<i class="ri-file-line"></i>`;grid.innerHTML+=`<a class=card href="/file/${encodeURIComponent(f.name)}"><div class=thumb>${thumb}</div><div class=info><div class=name title="${f.name}">${f.name}</div><div class=meta><span>${e.toUpperCase()}</span><span>${fmt(f.size)}</span></div></div></a>`})}
async function uploadFile(file){const fd=new FormData();fd.append('file',file);const r=await fetch('/api/upload',{method:'POST',body:fd});if(!r.ok)throw new Error('Upload failed')}
async function handleFiles(list){if(!list.length)return;modal.classList.add('show');mList.innerHTML='';let done=0;for(let i=0;i<list.length;i++){const f=list[i];mStatus.textContent=`Uploading ${i+1}/${list.length}: ${f.name}`;mBar.style.width=Math.round((i/list.length)*100)+'%';mList.innerHTML+=`<div>• ${f.name}</div>`;try{await uploadFile(f);done++;mList.lastElementChild.innerHTML+=` <span style="color:#22c55e">✓</span>`}catch(e){mList.lastElementChild.innerHTML+=` <span style="color:#ef4444">✗</span>`}}mBar.style.width='100%';mStatus.textContent=`Complete: ${done}/${list.length}`;setTimeout(()=>{modal.classList.remove('show');showToast(`${done} uploaded`);loadFiles()},1000)}
async function doUrl(){const u=urlInp.value.trim();if(!u)return showToast('Enter URL');if(!confirm('Fetch this URL?'))return;modal.classList.add('show');mTitle.textContent='Fetching URL';mStatus.textContent=u.substring(0,50);mBar.style.width='30%';try{const r=await fetch('/api/upload-url',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:u})});mBar.style.width='100%';mStatus.textContent=r.ok?'Done':'Failed';setTimeout(()=>{modal.classList.remove('show');mTitle.textContent='Uploading';if(r.ok){showToast('URL fetched');urlInp.value='';loadFiles()}else showToast('Fetch failed')},800)}catch(e){modal.classList.remove('show');showToast('Error')}}
drop.onclick=()=>fileInp.click();drop.ondragover=e=>{e.preventDefault();drop.classList.add('drag')};drop.ondragleave=()=>drop.classList.remove('drag');drop.ondrop=e=>{e.preventDefault();drop.classList.remove('drag');handleFiles([...e.dataTransfer.files])};fileInp.onchange=()=>handleFiles([...fileInp.files]);search.oninput=renderFiles;setView('upload');loadFiles()
</script></body></html>"""
    return html

@app.route("/file/<path:name>")
def view(name):
    f = next((x for x in ia_list() if x["name"]==name), None)
    if not f: return "Not found",404
    url = f["url"]; ext = name.rsplit(".",1)[-1].lower() if "." in name else ""
    if ext in ("mp4","webm","mov","mkv"): player = f'<video controls style="width:100%;max-height:85vh;background:#000" src="{url}"></video>'
    elif ext in ("mp3","wav","flac","m4a"): player = f'<audio controls style="width:100%" src="{url}"></audio>'
    elif ext in ("png","jpg","jpeg","gif","webp"): player = f'<img src="{url}" style="max-width:100%;max-height:85vh;display:block;margin:auto">'
    elif ext=="pdf": player = f'<iframe src="https://mozilla.github.io/pdf.js/web/viewer.html?file={quote(url)}" style="width:100%;height:85vh;border:0"></iframe>'
    else: player = f'<div style="padding:100px;text-align:center"><a href="{url}" download style="padding:12px 20px;background:#3b82f6;color:#fff;border-radius:8px;text-decoration:none">Download File</a></div>'
    return f'<!doctype html><html><head><meta charset=utf-8><title>{name}</title><style>body{{margin:0;background:#020617;color:#fff;font-family:system-ui}}.t{{padding:12px 16px;border-bottom:1px solid #1e293b;display:flex;gap:10px;align-items:center}}a{{color:#94a3b8;text-decoration:none;padding:8px 12px;background:#0b1220;border-radius:8px}}.w{{max-width:1200px;margin:20px auto;padding:0 16px}}</style></head><body><div class=t><a href="/">← Back</a><div style="flex:1;font-weight:600;overflow:hidden;text-overflow:ellipsis">{name}</div><a href="{url}" download>Download</a></div><div class=w>{player}</div></body></html>'

@app.route("/api/list")
def api_list():
    return jsonify(ia_list())

@app.route("/api/upload", methods=["POST"])
def api_up():
    try:
        f = request.files["file"]
        ia_put(secure_filename(f.filename), f.stream, f.content_type)
        return "",200
    except Exception as e:
        print("Upload error:", e)
        return "",500

@app.route("/api/upload-url", methods=["POST"])
def api_url():
    try:
        u = request.get_json().get("url","")
        r = requests.get(u, stream=True, timeout=120)
        r.raise_for_status()
        name = secure_filename(urlparse(u).path.split("/")[-1] or f"file-{int(time.time())}")
        ia_put(name, r.raw, r.headers.get("Content-Type"))
        return "",200
    except Exception as e:
        print("URL error:", e)
        return "",500

@app.route("/health")
def health(): return "ok"

if __name__=="__main__":
    app.run(host="0.0.0.0", port=8080)
