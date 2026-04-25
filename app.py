import os, requests, time, json
from flask import Flask, request, session, redirect, jsonify, Response, make_response, g
from werkzeug.utils import secure_filename
from xml.etree.ElementTree import Element, SubElement, tostring
from urllib.parse import unquote, quote
from collections import defaultdict, deque

IA_BUCKET = os.getenv("IA_BUCKET", "")
IA_ACCESS = os.getenv("IA_ACCESS_KEY", "")
IA_SECRET = os.getenv("IA_SECRET_KEY", "")
LOGIN_PIN = os.getenv("LOGIN_PIN", "2383")
DAV_USER = os.getenv("DAV_USER", "admin")
DAV_PASS = os.getenv("DAV_PASS", "2383")
ENDPOINT = "https://s3.us.archive.org"
WORKER = os.getenv("WORKER_MEDIA_BASE", "").rstrip("/")
AUTH = f"LOW {IA_ACCESS}:{IA_SECRET}" if IA_ACCESS and IA_SECRET else ""
MAX_FAILS = 5
BAN_TIME = 3600  # 1 hour

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "change-this-please")

# Simple in-memory rate limiting
fails = defaultdict(deque)
bans = {}

BLOCKED = ('/admin','/php','/wp-','/wp/','/wordpress','/rustfs','/uof','/scripts','/backend','/idexpert','/boaform','/cgi-bin','/pma','/phpmyadmin','/shell','/actuator','/api/v','/.env','/.git','/config','/solr','/jenkins','/hudson')

def get_ip():
    return request.headers.get('CF-Connecting-IP') or request.headers.get('X-Forwarded-For','').split(',')[0].strip() or request.remote_addr

def is_banned(ip):
    t = bans.get(ip,0)
    if t > time.time(): return True
    if t: del bans[ip]
    return False

def record_fail(ip):
    now = time.time()
    dq = fails[ip]
    dq.append(now)
    while dq and dq[0] < now-900: dq.popleft()
    if len(dq) >= MAX_FAILS:
        bans[ip] = now + BAN_TIME
        fails[ip].clear()
        print(f"[SECURITY] Banned {ip} for {BAN_TIME}s after {MAX_FAILS} fails")

@app.before_request
def security():
    ip = get_ip()
    g.ip = ip
    
    # Block scanners instantly with 404
    path = request.path.lower()
    if any(path.startswith(p) for p in BLOCKED):
        print(f"[BLOCK] {ip} -> {request.path}")
        return "", 404
    
    # Block banned IPs
    if is_banned(ip):
        return "Too many attempts. Try later.", 429
    
    # Log real requests
    if not path.startswith('/static'):
        print(f"[{time.strftime('%H:%M:%S')}] {ip} {request.method} {request.path}")

def ia_put(key, data, ctype):
    h = {"authorization": AUTH,"x-amz-auto-make-bucket":"1","x-archive-auto-make-bucket":"1","x-archive-meta01-collection":"opensource","x-archive-meta-mediatype":"data","x-archive-queue-derive":"0","x-archive-interactive-priority":"1","Content-Type": ctype or "application/octet-stream"}
    r = requests.put(f"{ENDPOINT}/{IA_BUCKET}/{key}", data=data, headers=h, timeout=900); r.raise_for_status()

def ia_get(key):
    r = requests.get(f"{ENDPOINT}/{IA_BUCKET}/{key}", headers={"authorization": AUTH}, stream=True, timeout=600)
    if r.status_code==404: return None
    r.raise_for_status(); return r

def ia_delete(key):
    r = requests.delete(f"{ENDPOINT}/{IA_BUCKET}/{key}", headers={"authorization": AUTH}, timeout=30)
    if r.status_code not in (200,204,404): r.raise_for_status()

def ia_list():
    try:
        r = requests.get(f"https://archive.org/metadata/{IA_BUCKET}", timeout=15)
        if not r.ok: return []
        out=[]
        for f in r.json().get("files",[]):
            n=f.get("name","")
            if n.startswith("_") or n in ("","history"): continue
            out.append({"name":n,"size":int(f.get("size",0)),"mtime":f.get("mtime",""),"url": f"{WORKER}/{IA_BUCKET}/{quote(n)}" if WORKER else f"https://archive.org/download/{IA_BUCKET}/{quote(n)}","ia_url": f"https://archive.org/download/{IA_BUCKET}/{quote(n)}"})
        return sorted(out,key=lambda x:x["name"].lower())
    except: return []

@app.before_request
def gate():
    if request.path.startswith("/dav") or request.path in ("/login","/health","/robots.txt"): return
    if request.path.startswith("/api/") or request.path.startswith("/file/"):
        if not session.get("ok") and request.path.startswith("/api/"): return jsonify({"error":"auth"}),401
        return
    if not session.get("ok"): return redirect("/login")

def dav_auth():
    a=request.authorization
    if not a or a.username!=DAV_USER or a.password!=DAV_PASS:
        return Response("Unauthorized",401,{"WWW-Authenticate":'Basic realm="IA Drive"'})

@app.route("/dav/", defaults={"path":""}, methods=["OPTIONS","PROPFIND","GET","PUT","DELETE","MKCOL","HEAD"])
@app.route("/dav/<path:path>", methods=["OPTIONS","PROPFIND","GET","PUT","DELETE","MKCOL","HEAD"])
def dav(path):
    if (r:=dav_auth()): return r
    path=unquote(path)
    if request.method=="OPTIONS":
        resp=make_response("",200); resp.headers["DAV"]="1,2"; return resp
    if request.method in ("PROPFIND","HEAD"):
        files=ia_list(); ms=Element("{DAV:}multistatus")
        for f in ([{"name":"","size":0}]+files if not path else [x for x in files if x["name"].startswith(path)]):
            re=SubElement(ms,"{DAV:}response"); SubElement(re,"{DAV:}href").text="/dav/"+f["name"]
            ps=SubElement(re,"{DAV:}propstat"); pr=SubElement(ps,"{DAV:}prop"); SubElement(pr,"{DAV:}displayname").text=f["name"].split("/")[-1] or IA_BUCKET; SubElement(pr,"{DAV:}getcontentlength").text=str(f.get("size",0)); SubElement(pr,"{DAV:}resourcetype"); SubElement(ps,"{DAV:}status").text="HTTP/1.1 200 OK"
        xml=tostring(ms,encoding="utf-8",xml_declaration=True); resp=make_response(xml,207); resp.headers["Content-Type"]="application/xml"; return resp
    if request.method=="GET":
        r=ia_get(path); return Response(r.iter_content(32768), headers={"Content-Type":r.headers.get("Content-Type")}) if r else ("",404)
    if request.method=="PUT": ia_put(path, request.stream, request.content_type); return "",201
    if request.method=="DELETE": ia_delete(path); return "",204
    if request.method=="MKCOL": ia_put(path.rstrip("/")+"/.keep",b"","text/plain"); return "",201
    return "",200

@app.route("/robots.txt")
def robots(): return "User-agent: *\nDisallow: /\n",200,{"Content-Type":"text/plain"}

@app.route("/health")
def health(): return "ok"

@app.route("/login", methods=["GET","POST"])
def login():
    ip = get_ip()
    if is_banned(ip):
        return f"<h1>Too many attempts</h1><p>Try again in {int((bans[ip]-time.time())/60)} minutes</p>",429
    err=""
    if request.method=="POST":
        if request.form.get("pin")==LOGIN_PIN:
            fails[ip].clear()
            session["ok"]=True; session.permanent=True
            print(f"[LOGIN OK] {ip}")
            return redirect("/")
        record_fail(ip)
        err=f"Wrong PIN ({len(fails[ip])}/{MAX_FAILS})"
        print(f"[LOGIN FAIL] {ip}")
    return f"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Login</title>
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b1220;color:#e5e7eb;font-family:system-ui}} .c{{width:360px;background:#111827;padding:40px;border-radius:20px;border:1px solid #1f2937}} input{{width:100%;padding:14px;background:#0b1220;border:1px solid #374151;border-radius:12px;color:#fff;font-size:16px}} button{{width:100%;margin-top:16px;padding:14px;background:#3b82f6;border:0;border-radius:12px;color:#fff;font-weight:600;cursor:pointer}} .e{{background:#450a0a;border:1px solid #7f1d1d;color:#fca5a5;padding:10px;border-radius:10px;margin-bottom:16px;font-size:14px}} .ip{{color:#6b7280;font-size:12px;margin-top:16px;text-align:center}}</style>
</head><body><div class=c><h1>IA Drive</h1><p style="color:#9ca3af">Enter PIN</p>{f'<div class=e>{err}</div>' if err else ''}<form method=post><input name=pin type=password placeholder="••••" autofocus autocomplete=off><button>Unlock</button></form><div class=ip>IP: {ip}</div></div></body></html>"""

@app.route("/logout", methods=["POST"])
def logout(): session.clear(); return "",200

@app.route("/")
def home():
    # (same UI as before, shortened)
    return """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>IA Drive</title>
<style>:root{--bg:#0b1220;--c:#111827;--m:#9ca3af;--a:#3b82f6;--b:#1f2937}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#e5e7eb;font-family:system-ui}.w{max-width:1200px;margin:0 auto;padding:24px}.h{display:flex;justify-content:space-between;margin-bottom:20px}.cd{background:var(--c);padding:20px;border-radius:16px;margin-bottom:16px;border:1px solid var(--b)}.dp{border:2px dashed #334155;border-radius:14px;padding:36px;text-align:center;cursor:pointer}.gd{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}.it{background:#0b1220;border:1px solid var(--b);border-radius:12px;padding:10px}.th{height:130px;display:grid;place-items:center;background:#000;border-radius:8px;overflow:hidden}.th img,.th video{width:100%;height:100%;object-fit:cover}.nm{font-size:13px;margin:6px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.mt{font-size:11px;color:var(--m)}a{color:inherit;text-decoration:none}</style>
</head><body><div class=w><div class=h><h1 style="margin:0">IA Drive 🔒</h1><div><input id=q placeholder="Search" style="padding:8px 12px;background:#0b1220;border:1px solid #334155;border-radius:8px;color:#fff"><button onclick="fetch('/logout',{method:'POST'}).then(()=>location='/login')" style="margin-left:8px;padding:8px 12px;background:#1f2937;border:1px solid #334155;border-radius:8px;color:#fff;cursor:pointer">Logout</button></div></div>
<div class=cd><div id=dp class=dp><b>Drop files</b></div><input id=fi type=file multiple style="display:none"><div id=st style="margin-top:8px;color:var(--m);font-size:12px"></div></div>
<div class=cd><div id=gd class=gd></div></div></div>
<script>const dp=document.getElementById('dp'),fi=document.getElementById('fi'),gd=document.getElementById('gd'),q=document.getElementById('q'),st=document.getElementById('st');let fs=[];async function ld(){fs=await (await fetch('/api/list')).json();rn()}function rn(){const t=q.value.toLowerCase();gd.innerHTML='';fs.filter(f=>f.name.toLowerCase().includes(t)).forEach(f=>{const e=f.name.split('.').pop().toLowerCase();const m=['png','jpg','jpeg','gif','webp','mp4','webm'].includes(e);const th=m?`<div class=th>${e.includes('mp4')||e.includes('webm')?`<video src="${f.url}" muted></video>`:`<img src="${f.url}" loading=lazy>`}</div>`:`<div class=th style="font-size:40px">${e=='pdf'?'📕':e.match(/mp3|wav|flac/)?'🎵':'📄'}</div>`;gd.innerHTML+=`<a class=it href="/file/${encodeURIComponent(f.name)}">${th}<div class=nm>${f.name}</div><div class=mt>${(f.size/1024/1024).toFixed(1)} MB</div></a>`})}
async function up(f){const d=new FormData();d.append('file',f);await fetch('/api/upload',{method:'POST',body:d})}async function hd(ls){for(let i=0;i<ls.length;i++){st.textContent=`${i+1}/${ls.length} ${ls[i].name}`;await up(ls[i])}st.textContent='Done';ld()}dp.onclick=()=>fi.click();dp.ondragover=e=>{e.preventDefault()};dp.ondrop=e=>{e.preventDefault();hd([...e.dataTransfer.files])};fi.onchange=()=>hd([...fi.files]);q.oninput=rn;ld()</script></body></html>"""

@app.route("/file/<path:name>")
def file_view(name):
    if not session.get("ok"): return redirect("/login")
    files=ia_list(); f=next((x for x in files if x["name"]==name),None)
    if not f: return "Not found",404
    ext = name.rsplit(".",1)[-1].lower() if "." in name else ""
    url = f["url"]
    # Simplified player (same as before)
    if ext in ('mp4','webm','mov','mkv','avi'): prev = f'<video controls style="width:100%;max-height:80vh;background:#000" src="{url}"></video>'
    elif ext in ('mp3','wav','flac','m4a','ogg'): prev = f'<audio controls style="width:100%" src="{url}"></audio>'
    elif ext in ('png','jpg','jpeg','gif','webp','svg'): prev = f'<img src="{url}" style="max-width:100%;max-height:80vh">'
    elif ext=='pdf': prev = f'<iframe src="https://mozilla.github.io/pdf.js/web/viewer.html?file={quote(url)}" style="width:100%;height:80vh;border:0"></iframe>'
    else: prev = f'<div style="padding:60px;text-align:center"><a href="{url}" download style="padding:12px 20px;background:#3b82f6;color:#fff;border-radius:8px;text-decoration:none">Download {ext.upper()}</a></div>'
    return f"""<!doctype html><html><head><meta charset=utf-8><title>{name}</title><style>body{{margin:0;background:#0b1220;color:#fff;font-family:system-ui}}.w{{max-width:1100px;margin:20px auto;padding:0 20px}}.c{{background:#111827;padding:20px;border-radius:12px}}</style></head><body><div class=w><a href="/" style="color:#9ca3af">← Back</a><div class=c style="margin-top:12px">{prev}</div><div class=c><h2 style="margin:0 0 8px;word-break:break-all">{name}</h2><p style="color:#9ca3af;margin:0">{f['size']/1024/1024:.2f} MB</p><p><a href="{url}" download style="color:#60a5fa">Download</a> • <a href="/dav/{quote(name)}" style="color:#60a5fa">WebDAV</a></p></div></div></body></html>"""

@app.route("/api/list")
def api_list(): return jsonify(ia_list()) if session.get("ok") else (jsonify([]),401)

@app.route("/api/upload", methods=["POST"])
def api_upload():
    if not session.get("ok"): return "",401
    f=request.files.get("file"); ia_put(secure_filename(f.filename), f.stream, f.content_type); print(f"[UPLOAD] {g.ip} -> {f.filename}"); return "",200

if __name__=="__main__": app.run(host="0.0.0.0",port=8080)
