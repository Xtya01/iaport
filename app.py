import os, requests, time, threading, sqlite3, json
from flask import Flask, request, session, redirect, jsonify
from werkzeug.utils import secure_filename
from urllib.parse import quote, urlparse
from collections import defaultdict

# Config
IA_BUCKET = os.getenv("IA_BUCKET", "junk-manage-caution")
IA_ACCESS = os.getenv("IA_ACCESS_KEY", "")
IA_SECRET = os.getenv("IA_SECRET_KEY", "")
LOGIN_PIN = os.getenv("LOGIN_PIN", "2383")
ENDPOINT = "https://s3.us.archive.org"
WORKER = os.getenv("WORKER_MEDIA_BASE", "").rstrip("/")
AUTH = f"LOW {IA_ACCESS}:{IA_SECRET}"
DB_PATH = "/data/history.db"

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "ia-drive-2026")

# Progress tracking
PROGRESS = {}
HISTORY_MEM = {}

# Init DB
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS history (
        id TEXT PRIMARY KEY,
        url TEXT,
        filename TEXT,
        size INTEGER,
        started TEXT,
        finished TEXT,
        status TEXT,
        speed REAL,
        error TEXT
    )""")
    conn.commit()
    conn.close()

init_db()

def ia_list():
    try:
        r = requests.get(f"https://archive.org/metadata/{IA_BUCKET}", timeout=15)
        out = []
        for f in r.json().get("files", []):
            n = f.get("name", "")
            if n and not n.startswith("_") and "/" not in n and n!= "history":
                url = f"{WORKER}/{IA_BUCKET}/{quote(n)}" if WORKER else f"https://archive.org/download/{IA_BUCKET}/{quote(n)}"
                out.append({"name": n, "size": int(f.get("size", 0)), "url": url})
        return sorted(out, key=lambda x: x["name"].lower())
    except Exception as e:
        print("List error:", e)
        return []

def ia_put(key, data, ctype):
    headers = {
        "authorization": AUTH,
        "x-amz-auto-make-bucket": "1",
        "x-archive-auto-make-bucket": "1",
        "x-archive-meta01-collection": "opensource",
        "Content-Type": ctype or "application/octet-stream"
    }
    r = requests.put(f"{ENDPOINT}/{IA_BUCKET}/{key}", data=data, headers=headers, timeout=900)
    r.raise_for_status()
    return r

def save_history(entry):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""INSERT OR REPLACE INTO history
        (id,url,filename,size,started,finished,status,speed,error)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (entry["id"], entry["url"], entry["filename"], entry["size"],
         entry["started"], entry.get("finished"), entry["status"],
         entry.get("speed", 0), entry.get("error")))
    conn.commit()
    conn.close()

def fetch_with_progress(task_id, url):
    try:
        started = time.strftime("%Y-%m-%d %H:%M:%S")
        PROGRESS[task_id] = {
            "status": "starting", "downloaded": 0, "total": 0, "uploaded": 0,
            "speed": 0, "eta": 0, "log": [f"{time.strftime('%H:%M:%S')} - Starting"],
            "speedHistory": []
        }

        entry = {
            "id": task_id, "url": url, "filename": "", "size": 0,
            "started": started, "status": "starting", "speed": 0
        }
        HISTORY_MEM[task_id] = entry
        save_history(entry)

        # Get info
        head = requests.head(url, allow_redirects=True, timeout=15)
        total = int(head.headers.get('content-length', 0))
        filename = secure_filename(urlparse(url).path.split("/")[-1] or f"file-{int(time.time())}")
        if not filename or '.' not in filename:
            ctype = head.headers.get('content-type', '')
            ext = '.bin'
            if 'video' in ctype: ext = '.mp4'
            elif 'image' in ctype: ext = '.jpg'
            elif 'audio' in ctype: ext = '.mp3'
            elif 'pdf' in ctype: ext = '.pdf'
            filename += ext

        PROGRESS[task_id].update({"total": total, "filename": filename, "status": "downloading"})
        PROGRESS[task_id]["log"].append(f"{time.strftime('%H:%M:%S')} - File: {filename} ({total/1024/1024:.1f} MB)" if total else f"{time.strftime('%H:%M:%S')} - File: {filename}")
        entry.update({"filename": filename, "size": total, "status": "downloading"})
        save_history(entry)

        # Download
        r = requests.get(url, stream=True, timeout=600)
        r.raise_for_status()

        chunks = []
        downloaded = 0
        start = time.time()
        last_update = start

        for chunk in r.iter_content(chunk_size=256*1024):
            if chunk:
                chunks.append(chunk)
                downloaded += len(chunk)
                now = time.time()

                if now - last_update > 0.3:
                    elapsed = now - start
                    speed = downloaded / elapsed if elapsed > 0 else 0
                    eta = (total - downloaded) / speed if speed > 0 and total > 0 else 0

                    PROGRESS[task_id].update({
                        "downloaded": downloaded,
                        "speed": speed,
                        "eta": int(eta)
                    })
                    PROGRESS[task_id]["speedHistory"].append(speed)
                    if len(PROGRESS[task_id]["speedHistory"]) > 60:
                        PROGRESS[task_id]["speedHistory"].pop(0)
                    last_update = now

        data = b''.join(chunks)
        PROGRESS[task_id]["log"].append(f"{time.strftime('%H:%M:%S')} - Downloaded {downloaded/1024/1024:.2f} MB")

        # Upload
        PROGRESS[task_id].update({"status": "uploading", "uploaded": 0})
        PROGRESS[task_id]["log"].append(f"{time.strftime('%H:%M:%S')} - Uploading to IA...")
        entry["status"] = "uploading"
        save_history(entry)

        upload_start = time.time()
        ia_put(filename, data, r.headers.get("Content-Type"))

        duration = time.time() - start
        avg_speed = len(data) / duration if duration > 0 else 0

        PROGRESS[task_id].update({
            "uploaded": len(data),
            "status": "complete",
            "speed": avg_speed
        })
        PROGRESS[task_id]["log"].append(f"{time.strftime('%H:%M:%S')} - ✓ Complete in {duration:.1f}s")

        entry.update({
            "status": "complete",
            "finished": time.strftime("%Y-%m-%d %H:%M:%S"),
            "speed": avg_speed
        })
        save_history(entry)

    except Exception as e:
        err = str(e)[:200]
        PROGRESS[task_id].update({"status": "error", "error": err})
        PROGRESS[task_id]["log"].append(f"{time.strftime('%H:%M:%S')} - ✗ Error: {err}")
        if task_id in HISTORY_MEM:
            HISTORY_MEM[task_id].update({"status": "error", "error": err, "finished": time.strftime("%Y-%m-%d %H:%M:%S")})
            save_history(HISTORY_MEM[task_id])

@app.before_request
def gate():
    if request.path.startswith(("/login","/health","/api","/file")):
        if request.path.startswith("/api") and not session.get("ok"):
            return jsonify(error="auth"), 401
        return
    if not session.get("ok"):
        return redirect("/login")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST" and request.form.get("pin") == LOGIN_PIN:
        session["ok"] = True
        return redirect("/")
    return """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Login</title>
<style>body{margin:0;height:100vh;display:grid;place-items:center;background:#020617;color:#e2e8f0;font-family:system-ui}
.box{width:320px;background:#0f172a;padding:32px;border-radius:16px;border:1px solid #1e293b}
input{width:100%;padding:12px;background:#000;border:1px solid #334155;border-radius:8px;color:#fff;margin:12px 0;box-sizing:border-box}
button{width:100%;padding:12px;background:#3b82f6;border:0;border-radius:8px;color:#fff;font-weight:600;cursor:pointer}
</style></head><body><div class=box><h2 style="margin:0 0 20px">IA Drive</h2>
<form method=post><input name=pin type=password placeholder="Enter PIN" autofocus required><button>Unlock</button></form></div></body></html>"""

@app.route("/")
def home():
    return """<!doctype html><html><head><meta charset=utf-8><title>IA Drive</title><meta name=viewport content="width=device-width,initial-scale=1">
<link rel=stylesheet href=https://cdnjs.cloudflare.com/ajax/libs/remixicon/4.2.0/remixicon.min.css>
<style>
:root{--bg:#020617;--s:#0f172a;--b:#1e293b;--m:#64748b;--a:#3b82f6;--g:#22c55e;--r:#ef4444}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#e2e8f0;font-family:system-ui,-apple-system,sans-serif}
.layout{display:flex;min-height:100vh}
.sidebar{width:240px;background:var(--s);border-right:1px solid var(--b);padding:16px;position:fixed;top:0;left:0;bottom:0;overflow-y:auto;z-index:40;transition:transform.25s}
.logo{font-weight:700;margin-bottom:20px;display:flex;align-items:center;gap:8px;font-size:17px}.logo i{color:var(--a)}
.menu a{display:flex;align-items:center;gap:10px;padding:10px 12px;margin:3px 0;border-radius:8px;color:#cbd5e1;text-decoration:none;cursor:pointer;font-size:14px}
.menu a.active,.menu a:hover{background:#1e293b;color:#fff}.menu a span{margin-left:auto;font-size:12px;opacity:.7}
.content{margin-left:240px;flex:1;min-width:0}
.header{padding:14px 20px;border-bottom:1px solid var(--b);background:rgba(2,6,23,.85);backdrop-filter:blur(8px);position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:12px}
.burger{display:none;background:none;border:none;color:#fff;font-size:22px;cursor:pointer;padding:4px}
.page{padding:20px}
.page-view{display:none}.page-view.active{display:block}
.upload-box{max-width:700px;margin:40px auto;background:var(--s);border:1px solid var(--b);border-radius:16px;padding:40px;text-align:center}
.drop{border:2px dashed #334155;border-radius:12px;padding:50px 20px;margin:24px 0;cursor:pointer;transition:.2s}
.drop:hover,.drop.drag{border-color:var(--a);background:#1e293b40}
.drop i{font-size:48px;color:var(--a);margin-bottom:12px}
.url-input{display:flex;gap:8px;max-width:500px;margin:0 auto}
.url-input input{flex:1;padding:12px;background:#000;border:1px solid #334155;border-radius:8px;color:#fff;font-size:14px}
.btn{padding:12px 20px;background:var(--a);border:none;border-radius:8px;color:#fff;font-weight:600;cursor:pointer;font-size:14px;white-space:nowrap}
.btn:hover{background:#2563eb}
.toolbar{display:flex;gap:10px;margin-bottom:16px;align-items:center}
.toolbar input{flex:1;max-width:400px;padding:10px 12px;background:var(--s);border:1px solid var(--b);border-radius:8px;color:#fff;font-size:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:14px}
.card{background:var(--s);border:1px solid var(--b);border-radius:10px;overflow:hidden;text-decoration:none;color:inherit;transition:.15s;display:block}
.card:hover{transform:translateY(-2px);border-color:#334155}
.thumb{height:110px;background:#000;display:flex;align-items:center;justify-content:center;overflow:hidden}
.thumb img,.thumb video{width:100%;height:100%;object-fit:cover}
.thumb i{font-size:32px;opacity:.5}
.info{padding:8px 10px}
.name{font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.meta{font-size:11px;color:var(--m);display:flex;justify-content:space-between;margin-top:3px}
.empty{text-align:center;padding:60px;color:var(--m);grid-column:1/-1}
.table{width:100%;border-collapse:collapse;background:var(--s);border:1px solid var(--b);border-radius:10px;overflow:hidden}
.table th{padding:12px;text-align:left;font-size:12px;color:var(--m);background:#0b1220;border-bottom:1px solid var(--b);font-weight:600}
.table td{padding:12px;border-bottom:1px solid #1e293b33;font-size:13px}
.table tr:hover{background:#1e293b40}
.badge{padding:3px 8px;border-radius:6px;font-size:11px;font-weight:500}
.badge.ok{background:#052e16;color:#4ade80}.badge.err{background:#450a0a;color:#f87171}.badge.run{background:#1e3a8a;color:#93c5fd}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.85);backdrop-filter:blur(4px);display:none;align-items:center;justify-content:center;z-index:100;padding:20px}
.modal.show{display:flex}
.modal-box{background:var(--s);border:1px solid var(--b);border-radius:14px;padding:24px;width:100%;max-width:440px;box-shadow:0 20px 60px #000}
.progress{height:6px;background:#000;border-radius:3px;overflow:hidden;margin:12px 0}
.progress-bar{height:100%;background:var(--a);width:0%;transition:width.3s}
.toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--s);border:1px solid var(--b);padding:12px 18px;border-radius:10px;display:none;z-index:200;font-size:14px;box-shadow:0 10px 40px rgba(0,0,0,.5);align-items:center;gap:8px;min-width:220px;justify-content:center}
.overlay{position:fixed;inset:0;background:#0006;display:none;z-index:30}
.overlay.show{display:block}
@media(max-width:768px){.sidebar{transform:translateX(-100%)}.sidebar.open{transform:translateX(0)}.content{margin-left:0}.burger{display:block}.grid{grid-template-columns:repeat(auto-fill,minmax(140px,1fr))}}
</style></head><body>
<div class=layout>
 <aside class=sidebar id=sidebar>
  <div class=logo><i class="ri-hard-drive-3-fill"></i> IA Drive</div>
  <nav class=menu>
   <a class=active data-page=upload><i class="ri-upload-2-line"></i> Upload</a>
   <a data-page=files data-filter=all><i class="ri-folder-line"></i> All Files <span id=c-all>0</span></a>
   <a data-page=files data-filter=video><i class="ri-film-line"></i> Videos <span id=c-video>0</span></a>
   <a data-page=files data-filter=image><i class="ri-image-line"></i> Images <span id=c-image>0</span></a>
   <a data-page=files data-filter=audio><i class="ri-music-2-line"></i> Audio <span id=c-audio>0</span></a>
   <a data-page=files data-filter=doc><i class="ri-file-text-line"></i> Docs <span id=c-doc>0</span></a>
   <a data-page=history><i class="ri-history-line"></i> History</a>
  </nav>
 </aside>
 <div class=overlay id=overlay onclick="toggleSidebar()"></div>
 <main class=content>
  <header class=header>
   <button class=burger onclick="toggleSidebar()"><i class="ri-menu-line"></i></button>
   <h1 id=page-title style="margin:0;font-size:18px;font-weight:600">Upload</h1>
  </header>
  <div class=page>
   <div id=view-upload class="page-view active">
    <div class=upload-box>
     <h2 style="margin:0 0 8px">Upload Files</h2>
     <p style="margin:0 0 24px;color:var(--m);font-size:14px">Permanent storage on Internet Archive</p>
     <div class=drop id=dropzone><i class="ri-upload-cloud-2-fill"></i><div style="font-weight:500">Drop files here or click to browse</div><div style="font-size:13px;color:var(--m);margin-top:4px">All file types supported</div></div>
     <div class=url-input><input id=url-input placeholder="Paste direct download URL..."><button class=btn onclick="uploadFromUrl()">Fetch</button></div>
     <input type=file id=file-input multiple hidden>
    </div>
   <div id=view-files class="page-view">
    <div class=toolbar><input id=search placeholder="Search files..." oninput="renderFiles()"><button class=btn onclick="loadFiles()" style="background:var(--s);border:1px solid var(--b);padding:10px 14px"><i class="ri-refresh-line"></i></button></div>
    <div class=grid id=file-grid><div class=empty>Loading...</div></div>
   </div>
   <div id=view-history class="page-view">
    <div class=toolbar><input id=hist-search placeholder="Search history..." oninput="renderHistory()"><button class=btn onclick="loadHistory()" style="background:var(--s);border:1px solid var(--b);padding:10px 14px"><i class="ri-refresh-line"></i></button></div>
    <div style="overflow:auto"><table class=table><thead><tr><th>File</th><th>Size</th><th>Source</th><th>Started</th><th>Status</th><th>Speed</th></tr></thead><tbody id=hist-body><tr><td colspan=6 style="text-align:center;padding:40px;color:var(--m)">Loading...</td></tr></tbody></table></div>
   </div>
  </div>
 </main>
</div>
<div class=modal id=modal><div class=modal-box>
 <h3 id=modal-title style="margin:0 0 8px">Uploading</h3>
 <div id=modal-status style="font-size:13px;color:#94a3b8">Preparing...</div>
 <div class=progress><div class=progress-bar id=progress-bar></div></div>
 <canvas id=speedChart width=392 height=60 style="margin-top:10px;display:none"></canvas>
 <div id=modal-list style="font-size:12px;color:var(--m);max-height:140px;overflow:auto;margin-top:10px;font-family:ui-monospace,monospace"></div>
</div></div>
<div class=toast id=toast></div>
<script>
let allFiles=[], historyData=[], currentFilter='all', currentPage='upload';
const types={video:['mp4','webm','mov','mkv','avi','m4v'],image:['png','jpg','jpeg','gif','webp','svg','bmp','avif'],audio:['mp3','wav','flac','m4a','ogg','aac'],doc:['pdf','doc','docx','txt','md','xls','xlsx','ppt','pptx','csv','rtf']};

function toggleSidebar(){sidebar.classList.toggle('open');overlay.classList.toggle('show')}
function showToast(msg,type='info'){const t=toast;const icons={info:'ri-information-line',success:'ri-check-line',error:'ri-error-warning-line'};const colors={info:'#1e293b',success:'#052e16',error:'#450a0a'};t.style.borderColor=colors[type];t.innerHTML=`<i class="${icons[type]}"></i><span>${msg}</span>`;t.style.display='flex';setTimeout(()=>t.style.display='none',3000)}
function showConfirm(msg,title='Confirm'){return new Promise(res=>{const m=document.createElement('div');m.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.85);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;z-index:1000';m.innerHTML=`<div style="background:#0f172a;border:1px solid #1e293b;border-radius:14px;padding:24px;max-width:400px;width:90%"><h3 style="margin:0 0 8px;font-size:16px">${title}</h3><p style="margin:0 0 20px;color:#94a3b8;font-size:14px;line-height:1.5">${msg}</p><div style="display:flex;gap:10px;justify-content:flex-end"><button id=c style="padding:8px 16px;background:#334155;border:0;border-radius:8px;color:#cbd5e1;cursor:pointer">Cancel</button><button id=o style="padding:8px 16px;background:#3b82f6;border:0;border-radius:8px;color:#fff;cursor:pointer">OK</button></div></div>`;document.body.appendChild(m);m.querySelector('#o').onclick=()=>{m.remove();res(true)};m.querySelector('#c').onclick=()=>{m.remove();res(false)};m.onclick=e=>{if(e.target===m){m.remove();res(false)}}})}
function switchPage(page,filter){currentPage=page;currentFilter=filter||'all';document.querySelectorAll('.menu a').forEach(a=>a.classList.remove('active'));document.querySelector(`[data-page="${page}"]${filter?`[data-filter="${filter}"]`:''}`)?.classList.add('active');document.querySelectorAll('.page-view').forEach(v=>v.classList.remove('active'));document.getElementById('view-'+page).classList.add('active');document.getElementById('page-title').textContent=page==='upload'?'Upload':page==='files'?(filter?filter.charAt(0).toUpperCase()+filter.slice(1):'Files'):'History';if(page==='files')loadFiles();if(page==='history')loadHistory();if(window.innerWidth<768)toggleSidebar()}
document.querySelectorAll('.menu a').forEach(a=>a.onclick=()=>switchPage(a.dataset.page,a.dataset.filter));
function getExt(n){return n.split('.').pop().toLowerCase()}
function getType(n){const e=getExt(n);for(const[k,v]of Object.entries(types))if(v.includes(e))return k;return'other'}
function fmt(b){if(b===0)return'0 B';if(b<1024)return b+' B';if(b<1048576)return(b/1024).toFixed(1)+' KB';if(b<1073741824)return(b/1048576).toFixed(1)+' MB';return(b/1073741824).toFixed(2)+' GB'}
async function loadFiles(){try{const r=await fetch('/api/list');allFiles=await r.json();const c={all:allFiles.length,video:0,image:0,audio:0,doc:0};allFiles.forEach(f=>{const t=getType(f.name);if(c[t]!=null)c[t]++});Object.entries(c).forEach(([k,v])=>{const e=document.getElementById('c-'+k);if(e)e.textContent=v});renderFiles()}catch(e){showToast('Failed to load','error')}}
function renderFiles(){const q=search.value.toLowerCase();const list=allFiles.filter(f=>(currentFilter==='all'||getType(f.name)===currentFilter)&&f.name.toLowerCase().includes(q));const g=fileGrid;g.innerHTML='';if(!list.length){g.innerHTML='<div class=empty>No files</div>';return}list.forEach(f=>{const e=getExt(f.name);const isI=types.image.includes(e);const isV=types.video.includes(e);const thumb=isI?`<img src="${f.url}" loading=lazy>`:isV?`<video src="${f.url}#t=0.5" muted></video>`:`<i class="ri-file-line"></i>`;const a=document.createElement('a');a.className='card';a.href='/file/'+encodeURIComponent(f.name);a.innerHTML=`<div class=thumb>${thumb}</div><div class=info><div class=name title="${f.name}">${f.name}</div><div class=meta><span>${e.toUpperCase()}</span><span>${fmt(f.size)}</span></div></div>`;g.appendChild(a)})}
async function loadHistory(){try{const r=await fetch('/api/history');historyData=await r.json();renderHistory()}catch(e){showToast('Failed to load history','error')}}
function renderHistory(){const q=(document.getElementById('hist-search')?.value||'').toLowerCase();const body=document.getElementById('hist-body');const list=historyData.filter(h=>(h.filename+h.url).toLowerCase().includes(q));if(!list.length){body.innerHTML='<tr><td colspan=6 style="text-align:center;padding:40px;color:var(--m)">No history</td></tr>';return}body.innerHTML=list.map(h=>{const badge=h.status==='complete'?'ok':h.status==='error'?'err':'run';const icon=h.status==='complete'?'✓':h.status==='error'?'✗':'⟳';return`<tr><td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${h.filename}">${h.filename||'-'}</td><td>${fmt(h.size||0)}</td><td style="max-width:200px;overflow:hidden;text-overflow:ellipsis" title="${h.url}">${(h.url||'').slice(0,40)}</td><td>${h.started||''}</td><td><span class="badge ${badge}">${icon} ${h.status}</span></td><td>${h.speed?fmt(h.speed)+'/s':'-'}</td></tr>`}).join('')}
async function uploadFile(f){const d=new FormData();d.append('file',f);const r=await fetch('/api/upload',{method:'POST',body:d});if(!r.ok)throw new Error()}
async function handleFiles(list){if(!list.length)return;modal.classList.add('show');modalTitle.textContent='Uploading';modalStatus.textContent='';progressBar.style.width='0%';modalList.innerHTML='';speedChart.style.display='none';let ok=0;for(let i=0;i<list.length;i++){const f=list[i];modalStatus.textContent=`${i+1}/${list.length}: ${f.name}`;progressBar.style.width=Math.round(i/list.length*100)+'%';modalList.innerHTML+=`<div>• ${f.name}</div>`;try{await uploadFile(f);ok++;modalList.lastChild.innerHTML+=' <span style="color:var(--g)">✓</span>'}catch{modalList.lastChild.innerHTML+=' <span style="color:var(--r)">✗</span>'}}progressBar.style.width='100%';modalStatus.textContent=`Done ${ok}/${list.length}`;setTimeout(()=>{modal.classList.remove('show');showToast(`${ok} uploaded`,'success');loadFiles()},1000)}
async function uploadFromUrl(){const url=document.getElementById('url-input').value.trim();if(!url)return showToast('Enter URL','error');const ok=await showConfirm(`Fetch file from this URL?<br><span style="opacity:.7;font-size:12px;word-break:break-all">${url.slice(0,80)}</span>`,'Fetch URL');if(!ok)return;const r=await fetch('/api/upload-url',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});const{task_id}=await r.json();modal.classList.add('show');modalTitle.textContent='Fetching URL';speedChart.style.display='block';const ctx=speedChart.getContext('2d');let speeds=[];const poll=setInterval(async()=>{const p=await(await fetch(`/api/progress/${task_id}`)).json();if(p.status==='notfound')return;const dl=fmt(p.downloaded),tot=p.total?fmt(p.total):'?',up=fmt(p.uploaded),spd=p.speed?fmt(p.speed)+'/s':'-',eta=p.eta?`${Math.floor(p.eta/60)}m${p.eta%60}s`:'-';modalStatus.innerHTML=`<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:12px"><div>Down: <b>${dl} / ${tot}</b></div><div>Speed: <b>${spd}</b></div><div>Up: <b>${up}</b></div><div>ETA: <b>${eta}</b></div></div>`;const pct=p.total?(p.downloaded/p.total*70):30;const upct=p.status==='uploading'?70+(p.uploaded/Math.max(p.downloaded,1)*30):pct;progressBar.style.width=Math.min(upct,100)+'%';if(p.speedHistory){speeds=p.speedHistory.slice(-60);ctx.clearRect(0,0,392,60);ctx.beginPath();ctx.strokeStyle='#3b82f6';ctx.lineWidth=2;speeds.forEach((s,i)=>{const x=i*392/speeds.length;const y=60-(s/Math.max(...speeds,1))*50;if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y)});ctx.stroke()}if(p.log)modalList.innerHTML=p.log.map(l=>`<div>${l}</div>`).join('');if(p.status==='complete'||p.status==='error'){clearInterval(poll);setTimeout(()=>{modal.classList.remove('show');showToast(p.status==='complete'?'Fetch complete':'Fetch failed',p.status==='complete'?'success':'error');if(p.status==='complete'){document.getElementById('url-input').value='';loadFiles();loadHistory()}},800)}},500)}
const dz=dropzone,fi=fileInput;dz.onclick=()=>fi.click();dz.ondragover=e=>{e.preventDefault();dz.classList.add('drag')};dz.ondragleave=()=>dz.classList.remove('drag');dz.ondrop=e=>{e.preventDefault();dz.classList.remove('drag');handleFiles([...e.dataTransfer.files])};fi.onchange=()=>handleFiles([...fi.files]);switchPage('upload');loadFiles();
</script></body></html>"""

@app.route("/file/<path:name>")
def view_file(name):
    f = next((x for x in ia_list() if x["name"] == name), None)
    if not f: return "Not found", 404
    url, ext = f["url"], name.rsplit(".",1)[-1].lower() if "." in name else ""
    if ext in ("mp4","webm","mov","mkv","avi"): player = f'<video controls style="width:100%;max-height:85vh;background:#000" src="{url}"></video>'
    elif ext in ("mp3","wav","flac","m4a","ogg"): player = f'<audio controls style="width:100%;max-width:600px" src="{url}"></audio>'
    elif ext in ("png","jpg","jpeg","gif","webp","svg"): player = f'<img src="{url}" style="max-width:100%;max-height:85vh;display:block;margin:auto">'
    elif ext == "pdf": player = f'<iframe src="https://mozilla.github.io/pdf.js/web/viewer.html?file={quote(url)}" style="width:100%;height:85vh;border:0"></iframe>'
    else: player = f'<div style="text-align:center;padding:80px"><a href="{url}" download style="padding:12px 24px;background:#3b82f6;color:#fff;text-decoration:none;border-radius:8px">Download</a></div>'
    return f'<!doctype html><html><head><meta charset=utf-8><title>{name}</title><meta name=viewport content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#020617;color:#e2e8f0;font-family:system-ui"><div style="padding:12px 16px;border-bottom:1px solid #1e293b;display:flex;gap:12px;align-items:center;position:sticky;top:0;background:#020617"><a href="/" style="color:#94a3b8;text-decoration:none">← Back</a><div style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{name}</div><a href="{url}" download style="padding:8px 14px;background:#1e293b;color:#fff;text-decoration:none;border-radius:6px;font-size:14px">Download</a></div><div style="max-width:1400px;margin:20px auto;padding:0 16px">{player}</div></body></html>'

@app.route("/api/list")
def api_list(): return jsonify(ia_list())

@app.route("/api/upload", methods=["POST"])
def api_upload():
    try:
        f = request.files["file"]
        ia_put(secure_filename(f.filename), f.stream, f.content_type)
        return "", 200
    except Exception as e:
        return str(e), 500

@app.route("/api/upload-url", methods=["POST"])
def api_upload_url():
    url = request.get_json().get("url", "")
    task_id = f"t{int(time.time()*1000)}"
    threading.Thread(target=fetch_with_progress, args=(task_id, url), daemon=True).start()
    return jsonify({"task_id": task_id})

@app.route("/api/progress/<task_id>")
def api_progress(task_id): return jsonify(PROGRESS.get(task_id, {"status": "notfound"}))

@app.route("/api/history")
def api_history():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM history ORDER BY started DESC LIMIT 100").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/health")
def health(): return "ok"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
