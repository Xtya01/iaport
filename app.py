import os, requests
from flask import Flask, request, session, redirect, jsonify, Response, make_response
from werkzeug.utils import secure_filename
from xml.etree.ElementTree import Element, SubElement, tostring
from urllib.parse import unquote

IA_BUCKET = os.getenv("IA_BUCKET")
IA_ACCESS = os.getenv("IA_ACCESS_KEY")
IA_SECRET = os.getenv("IA_SECRET_KEY")
LOGIN_PIN = os.getenv("LOGIN_PIN", "2383")
DAV_USER = os.getenv("DAV_USER", "admin")
DAV_PASS = os.getenv("DAV_PASS", "2383")
ENDPOINT = "https://s3.us.archive.org"
WORKER = os.getenv("WORKER_MEDIA_BASE", "").rstrip("/")
AUTH = f"LOW {IA_ACCESS}:{IA_SECRET}" if IA_ACCESS and IA_SECRET else ""

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "change-me-123")

def ia_put(key, data, ctype):
    h = {
        "authorization": AUTH,
        "x-amz-auto-make-bucket": "1",
        "x-archive-auto-make-bucket": "1",
        "x-archive-meta01-collection": "opensource",
        "x-archive-meta-mediatype": "data",
        "x-archive-queue-derive": "0",
        "x-archive-interactive-priority": "1",
        "Content-Type": ctype or "application/octet-stream",
    }
    r = requests.put(f"{ENDPOINT}/{IA_BUCKET}/{key}", data=data, headers=h, timeout=900)
    r.raise_for_status()

def ia_get(key):
    r = requests.get(f"{ENDPOINT}/{IA_BUCKET}/{key}", headers={"authorization": AUTH}, stream=True, timeout=600)
    if r.status_code == 404: return None
    r.raise_for_status()
    return r

def ia_delete(key):
    r = requests.delete(f"{ENDPOINT}/{IA_BUCKET}/{key}", headers={"authorization": AUTH}, timeout=30)
    if r.status_code not in (200,204,404): r.raise_for_status()

def ia_list():
    try:
        r = requests.get(f"https://archive.org/metadata/{IA_BUCKET}", timeout=15)
        if not r.ok: return []
        files=[]
        for f in r.json().get("files",[]):
            name=f.get("name","")
            if name.startswith("_") or name=="history": continue
            files.append({"name":name,"size":int(f.get("size",0)),"mtime":f.get("mtime"),
                          "url": f"{WORKER}/{IA_BUCKET}/{name}" if WORKER else f"https://archive.org/download/{IA_BUCKET}/{name}"})
        return sorted(files,key=lambda x:x["name"].lower())
    except: return []

@app.before_request
def gate():
    if request.path.startswith("/dav") or request.path in ("/login","/health","/api/list","/api/upload"): return
    if request.path.startswith("/api/"): return
    if not session.get("ok") and request.path != "/login": return redirect("/login")

def dav_auth():
    a=request.authorization
    if not a or a.username!=DAV_USER or a.password!=DAV_PASS:
        return Response("Unauthorized",401,{"WWW-Authenticate":'Basic realm="IA DAV"'})

@app.route("/dav/", defaults={"path":""}, methods=["OPTIONS","PROPFIND","GET","PUT","DELETE","MKCOL","HEAD"])
@app.route("/dav/<path:path>", methods=["OPTIONS","PROPFIND","GET","PUT","DELETE","MKCOL","HEAD"])
def dav(path):
    if (r:=dav_auth()): return r
    path=unquote(path)
    if request.method=="OPTIONS":
        resp=make_response("",200); resp.headers["DAV"]="1,2"; resp.headers["Allow"]="OPTIONS,GET,HEAD,PUT,DELETE,PROPFIND,MKCOL"; return resp
    if request.method in ("PROPFIND","HEAD"):
        depth=request.headers.get("Depth","1")
        files=ia_list()
        target=[f for f in files if f["name"]==path or (path=="" or f["name"].startswith(path))]
        ms=Element("{DAV:}multistatus")
        items=[{"name":path,"size":0}] + target if path=="" and depth!="0" else (target if target else [{"name":path,"size":0}])
        for f in items:
            re=SubElement(ms,"{DAV:}response"); href=SubElement(re,"{DAV:}href"); href.text="/dav/"+f["name"]
            ps=SubElement(re,"{DAV:}propstat"); pr=SubElement(ps,"{DAV:}prop")
            SubElement(pr,"{DAV:}displayname").text=f["name"].split("/")[-1] or IA_BUCKET
            SubElement(pr,"{DAV:}getcontentlength").text=str(f.get("size",0))
            rt=SubElement(pr,"{DAV:}resourcetype"); 
            SubElement(ps,"{DAV:}status").text="HTTP/1.1 200 OK"
        xml=tostring(ms,encoding="utf-8",xml_declaration=True)
        resp=make_response(xml,207); resp.headers["Content-Type"]="application/xml"; return resp
    if request.method=="GET":
        r=ia_get(path); 
        if not r: return "Not found",404
        return Response(r.iter_content(8192),headers={"Content-Type":r.headers.get("Content-Type","application/octet-stream")})
    if request.method=="PUT":
        ia_put(path, request.stream, request.content_type); return "",201
    if request.method=="DELETE":
        ia_delete(path); return "",204
    if request.method=="MKCOL":
        ia_put(path.rstrip("/")+"/.keep",b"","text/plain"); return "",201
    return "",200

@app.route("/health")
def health(): return "ok"

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST" and request.form.get("pin")==LOGIN_PIN:
        session["ok"]=True; return redirect("/")
    return """<!doctype html><html><head><meta name=viewport content="width=device-width,initial-scale=1"><title>IA Drive</title>
<style>body{margin:0;height:100vh;display:grid;place-items:center;background:#0b1220;color:#fff;font-family:system-ui}
.card{background:#111827;padding:36px;border-radius:16px;width:320px;box-shadow:0 20px 60px #0008}
input{width:100%;padding:12px;background:#0b1220;border:1px solid #334155;border-radius:10px;color:#fff}
button{width:100%;margin-top:14px;padding:12px;background:#3b82f6;border:0;border-radius:10px;color:#fff;font-weight:600;cursor:pointer}
</style></head><body><div class=card><h2>IA Drive</h2><form method=post>
<input name=pin type=password placeholder="PIN" autofocus><button>Unlock</button></form></div></body></html>"""

@app.route("/")
def home():
    return """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>IA Drive + WebDAV</title><style>
:root{--bg:#0b1220;--card:#111827;--muted:#9ca3af;--acc:#3b82f6}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#e5e7eb;font-family:system-ui}
.wrap{max-width:1100px;margin:32px auto;padding:0 16px}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.card{background:var(--card);padding:18px;border-radius:14px;margin-bottom:16px}
.drop{border:2px dashed #334155;border-radius:12px;padding:28px;text-align:center;cursor:pointer}
.drop.drag{border-color:var(--acc);background:#0b1220}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.item{background:#0b1220;border:1px solid #1f2937;border-radius:12px;padding:12px}
.item img,.item video{width:100%;height:140px;object-fit:cover;border-radius:8px;background:#000}
.name{font-size:14px;margin:8px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.meta{font-size:12px;color:var(--muted)}
.actions{display:flex;gap:8px;margin-top:8px}
.btn{padding:6px 10px;border-radius:8px;border:1px solid #334155;background:#1f2937;color:#fff;font-size:12px;cursor:pointer;text-decoration:none}
.btn.danger{border-color:#7f1d1d;background:#450a0a}
.progress{height:6px;background:#1f2937;border-radius:6px;overflow:hidden;margin-top:10px;display:none}
.bar{height:100%;width:0;background:var(--acc);transition:width .1s}
.search{padding:10px 12px;width:260px;background:#0b1220;border:1px solid #334155;border-radius:10px;color:#fff}
code{background:#0b1220;padding:2px 6px;border-radius:6px}
</style></head><body><div class=wrap>
<div class=header><h1 style="margin:0">IA Drive</h1><input id=q class=search placeholder="Search…"></div>
<div class=card><div style="color:var(--muted);font-size:13px;margin-bottom:8px">WebDAV: <code>/dav/</code> — user: <b>admin</b> pass: <b>2383</b> (change via env)</div>
<div id=drop class=drop><b>Drop files here</b> or click to select</div><input id=file type=file multiple style="display:none">
<div class=progress id=prog><div class=bar id=bar></div></div><div id=status style="margin-top:8px;color:var(--muted);font-size:13px"></div></div>
<div class=card><h3 style="margin:0 0 10px">Files <span id=count style="color:var(--muted)"></span></h3><div id=grid class=grid></div></div></div>
<script>
const drop=document.getElementById('drop'),fileIn=document.getElementById('file'),prog=document.getElementById('prog'),bar=document.getElementById('bar'),status=document.getElementById('status'),grid=document.getElementById('grid'),q=document.getElementById('q');let files=[];
async function load(){const r=await fetch('/api/list');files=await r.json();render();}
function render(){const t=q.value.toLowerCase();const list=files.filter(f=>f.name.toLowerCase().includes(t));document.getElementById('count').textContent='('+list.length+')';grid.innerHTML='';list.forEach(f=>{const img=/\.(png|jpe?g|gif|webp|svg)$/i.test(f.name);const vid=/\.(mp4|webm|mov)$/i.test(f.name);const thumb=img?`<img src="${f.url}" loading=lazy>`:vid?`<video src="${f.url}" muted></video>`:`<div style="height:140px;display:grid;place-items:center;background:#000;border-radius:8px">📄</div>`;grid.innerHTML+=`<div class=item>${thumb}<div class=name title="${f.name}">${f.name}</div><div class=meta>${(f.size/1024/1024).toFixed(2)} MB</div><div class=actions><a class=btn href="${f.url}" target=_blank>Open</a><button class=btn onclick="navigator.clipboard.writeText('${f.url}')">Copy</button><button class="btn danger" onclick="del('${f.name}')">Delete</button></div></div>`;});}
async function upload(file){const fd=new FormData();fd.append('file',file);return new Promise((res,rej)=>{const x=new XMLHttpRequest();x.open('POST','/api/upload');x.upload.onprogress=e=>{if(e.lengthComputable)bar.style.width=(e.loaded/e.total*100)+'%';};x.onload=()=>x.status===200?res():rej();x.onerror=()=>rej();x.send(fd);});}
async function handle(list){prog.style.display='block';for(let i=0;i<list.length;i++){status.textContent=`Uploading ${i+1}/${list.length}: ${list[i].name}`;bar.style.width='0%';await upload(list[i]);}status.textContent='Done';setTimeout(()=>prog.style.display='none',700);load();}
drop.onclick=()=>fileIn.click();drop.ondragover=e=>{e.preventDefault();drop.classList.add('drag')};drop.ondragleave=()=>drop.classList.remove('drag');drop.ondrop=e=>{e.preventDefault();drop.classList.remove('drag');handle(e.dataTransfer.files)};fileIn.onchange=()=>handle(fileIn.files);q.oninput=render;
async function del(n){if(!confirm('Delete '+n+'?'))return;await fetch('/api/delete?name='+encodeURIComponent(n),{method:'DELETE'});load();}
load();
</script></body></html>"""

@app.route("/api/list")
def api_list(): return jsonify(ia_list())

@app.route("/api/upload", methods=["POST"])
def api_upload():
    f=request.files["file"]; ia_put(secure_filename(f.filename), f.stream, f.content_type); return "",200

@app.route("/api/delete", methods=["DELETE"])
def api_delete(): ia_delete(request.args.get("name","")); return "",200

if __name__=="__main__": app.run(host="0.0.0.0",port=8080)
