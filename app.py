
import os, requests
from flask import Flask, request, session, redirect, jsonify, Response, make_response
from werkzeug.utils import secure_filename
from xml.etree.ElementTree import Element, SubElement, tostring
from urllib.parse import unquote, quote

IA_BUCKET = os.getenv("IA_BUCKET", "")
IA_ACCESS = os.getenv("IA_ACCESS_KEY", "")
IA_SECRET = os.getenv("IA_SECRET_KEY", "")
LOGIN_PIN = os.getenv("LOGIN_PIN", "2383")
DAV_USER = os.getenv("DAV_USER", "admin")
DAV_PASS = os.getenv("DAV_PASS", "2383")
ENDPOINT = "https://s3.us.archive.org"
WORKER = os.getenv("WORKER_MEDIA_BASE", "").rstrip("/")
AUTH = f"LOW {IA_ACCESS}:{IA_SECRET}" if IA_ACCESS and IA_SECRET else ""

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "ia-drive-secret")

def ia_put(key, data, ctype):
    h = {"authorization": AUTH,"x-amz-auto-make-bucket":"1","x-archive-auto-make-bucket":"1","x-archive-meta01-collection":"opensource","x-archive-meta-mediatype":"data","x-archive-queue-derive":"0","x-archive-interactive-priority":"1","Content-Type": ctype or "application/octet-stream"}
    r = requests.put(f"{ENDPOINT}/{IA_BUCKET}/{key}", data=data, headers=h, timeout=900)
    r.raise_for_status()

def ia_get(key):
    r = requests.get(f"{ENDPOINT}/{IA_BUCKET}/{key}", headers={"authorization": AUTH}, stream=True, timeout=600)
    if r.status_code==404: return None
    r.raise_for_status()
    return r

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
            out.append({"name":n,"size":int(f.get("size",0)),"mtime":f.get("mtime",""),"format":f.get("format",""),"url": f"{WORKER}/{IA_BUCKET}/{quote(n)}" if WORKER else f"https://archive.org/download/{IA_BUCKET}/{quote(n)}","ia_url": f"https://archive.org/download/{IA_BUCKET}/{quote(n)}"})
        return sorted(out,key=lambda x:x["name"].lower())
    except:
        return []

@app.before_request
def gate():
    if request.path.startswith("/dav") or request.path in ("/login","/health"): return
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
        resp=make_response("",200); resp.headers["DAV"]="1,2"; resp.headers["Allow"]="OPTIONS,GET,HEAD,PUT,DELETE,PROPFIND,MKCOL"; return resp
    if request.method in ("PROPFIND","HEAD"):
        files=ia_list(); ms=Element("{DAV:}multistatus")
        for f in ([{"name":path,"size":0}]+files if not path else [x for x in files if x["name"].startswith(path)]):
            re=SubElement(ms,"{DAV:}response"); href=SubElement(re,"{DAV:}href"); href.text="/dav/"+f["name"]
            ps=SubElement(re,"{DAV:}propstat"); pr=SubElement(ps,"{DAV:}prop")
            SubElement(pr,"{DAV:}displayname").text=f["name"].split("/")[-1] or IA_BUCKET
            SubElement(pr,"{DAV:}getcontentlength").text=str(f.get("size",0)); SubElement(pr,"{DAV:}resourcetype")
            SubElement(ps,"{DAV:}status").text="HTTP/1.1 200 OK"
        xml=tostring(ms,encoding="utf-8",xml_declaration=True); resp=make_response(xml,207); resp.headers["Content-Type"]="application/xml"; return resp
    if request.method=="GET":
        r=ia_get(path); return Response(r.iter_content(32768), headers={"Content-Type":r.headers.get("Content-Type")}) if r else ("",404)
    if request.method=="PUT": ia_put(path, request.stream, request.content_type); return "",201
    if request.method=="DELETE": ia_delete(path); return "",204
    if request.method=="MKCOL": ia_put(path.rstrip("/")+"/.keep",b"","text/plain"); return "",201
    return "",200

@app.route("/health")
def health(): return "ok"

@app.route("/login", methods=["GET","POST"])
def login():
    err=""
    if request.method=="POST" and request.form.get("pin")==LOGIN_PIN:
        session["ok"]=True; return redirect("/")
    if request.method=="POST": err="Wrong PIN"
    return f"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Login</title>
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b1220;color:#e5e7eb;font-family:system-ui}} .card{{width:360px;background:#111827;padding:40px;border-radius:20px;border:1px solid #1f2937;box-shadow:0 25px 80px #0008}} h1{{margin:0 0 8px}} p{{margin:0 0 24px;color:#9ca3af}} input{{width:100%;padding:14px;background:#0b1220;border:1px solid #374151;border-radius:12px;color:#fff;font-size:16px}} input:focus{{outline:none;border-color:#3b82f6;box-shadow:0 0 0 3px #3b82f633}} button{{width:100%;margin-top:16px;padding:14px;background:#3b82f6;border:0;border-radius:12px;color:#fff;font-weight:600;cursor:pointer}} .err{{background:#450a0a;border:1px solid #7f1d1d;color:#fca5a5;padding:10px;border-radius:10px;margin-bottom:16px;font-size:14px}}</style>
</head><body><div class=card><h1>IA Drive</h1><p>Enter PIN to continue</p>{f'<div class=err>{err}</div>' if err else ''}<form method=post><input name=pin type=password placeholder="PIN" autofocus><button>Unlock</button></form></div></body></html>"""

@app.route("/")
def home():
    return """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>IA Drive</title>
<style>:root{--bg:#0b1220;--card:#111827;--muted:#9ca3af;--acc:#3b82f6;--b:#1f2937}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#e5e7eb;font-family:system-ui}.wrap{max-width:1200px;margin:0 auto;padding:24px}.h{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}.card{background:var(--card);padding:20px;border-radius:16px;margin-bottom:16px;border:1px solid var(--b)}.drop{border:2px dashed #334155;border-radius:14px;padding:36px;text-align:center;cursor:pointer}.drop.drag{border-color:var(--acc);background:#0b1220}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px}.it{background:#0b1220;border:1px solid var(--b);border-radius:14px;padding:12px;transition:.15s}.it:hover{transform:translateY(-2px);border-color:#334155}.th{height:140px;display:grid;place-items:center;background:#000;border-radius:10px;overflow:hidden}.th img,.th video{width:100%;height:100%;object-fit:cover}.nm{font-size:14px;margin:8px 0 2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.mt{font-size:12px;color:var(--muted)}.sr{padding:10px 12px;width:260px;background:#0b1220;border:1px solid #334155;border-radius:10px;color:#fff}.pr{height:8px;background:#0b1220;border-radius:8px;overflow:hidden;margin-top:12px;display:none;border:1px solid var(--b)}.br{height:100%;width:0;background:var(--acc);transition:width .1s}a{color:inherit;text-decoration:none}</style>
</head><body><div class=wrap><div class=h><h1 style="margin:0">IA Drive</h1><input id=q class=sr placeholder="Search…"></div>
<div class=card><div id=drop class=drop><b>Drop files here</b><div style="color:var(--muted);margin-top:6px">or click to browse</div></div><input id=f type=file multiple style="display:none"><div class=pr id=pr><div class=br id=br></div></div><div id=st style="margin-top:8px;color:var(--muted);font-size:13px"></div></div>
<div class=card><div id=g class=grid></div></div></div>
<script>
const drop=document.getElementById('drop'),fi=document.getElementById('f'),pr=document.getElementById('pr'),br=document.getElementById('br'),st=document.getElementById('st'),g=document.getElementById('g'),q=document.getElementById('q');let files=[];
async function load(){const r=await fetch('/api/list');files=await r.json();render()}
function icon(n){const e=n.split('.').pop().toLowerCase();if(['mp4','webm','mov','mkv','avi'].includes(e))return '🎬';if(['mp3','wav','flac','m4a','ogg'].includes(e))return '🎵';if(['pdf'].includes(e))return '📕';if(['zip','rar','7z'].includes(e))return '📦';return '📄'}
function render(){const t=q.value.toLowerCase();const list=files.filter(x=>x.name.toLowerCase().includes(t));g.innerHTML='';list.forEach(f=>{const n=f.name;const e=n.split('.').pop().toLowerCase();const isMedia=['png','jpg','jpeg','gif','webp','mp4','webm','mov'].includes(e);const th=isMedia?`<div class=th>${e.match(/mp4|webm|mov/)?`<video src="${f.url}" muted></video>`:`<img src="${f.url}" loading=lazy>`}</div>`:`<div class=th style="font-size:48px">${icon(n)}</div>`;g.innerHTML+=`<a class=it href="/file/${encodeURIComponent(n)}">${th}<div class=nm title="${n}">${n}</div><div class=mt>${(f.size/1024/1024).toFixed(2)} MB</div></a>`})}
async function up(file){const fd=new FormData();fd.append('file',file);return new Promise((res,rej)=>{const x=new XMLHttpRequest();x.open('POST','/api/upload');x.upload.onprogress=e=>{if(e.lengthComputable)br.style.width=(e.loaded/e.total*100)+'%'};x.onload=()=>x.status==200?res():rej();x.onerror=rej;x.send(fd)})}
async function handle(list){pr.style.display='block';for(let i=0;i<list.length;i++){st.textContent=`${i+1}/${list.length} ${list[i].name}`;br.style.width='0%';await up(list[i])}st.textContent='Done';setTimeout(()=>{pr.style.display='none';st.textContent=''},800);load()}
drop.onclick=()=>fi.click();drop.ondragover=e=>{e.preventDefault();drop.classList.add('drag')};drop.ondragleave=()=>drop.classList.remove('drag');drop.ondrop=e=>{e.preventDefault();drop.classList.remove('drag');handle([...e.dataTransfer.files])};fi.onchange=()=>handle([...fi.files]);q.oninput=render;load()
</script></body></html>"""

@app.route("/file/<path:name>")
def file_view(name):
    files=ia_list(); f=next((x for x in files if x["name"]==name),None)
    if not f: return "Not found",404
    ext = name.rsplit(".",1)[-1].lower() if "." in name else ""
    url = f["url"]
    
    VIDEO = ('mp4','webm','mov','mkv','avi','m4v','flv','wmv','3gp','ogv','webm')
    AUDIO = ('mp3','wav','ogg','m4a','flac','aac','opus','wma','aiff','alac')
    IMAGE = ('png','jpg','jpeg','gif','webp','svg','avif','bmp','tiff','ico','heic','heif','psd')
    PDF = ('pdf',)
    TEXT = ('txt','md','log','csv','json','xml','yml','yaml','ini','conf','toml')
    CODE = ('js','ts','py','html','htm','css','php','java','c','cpp','cs','go','rs','rb','sh','bash','sql','kt','swift','dart','lua','r')
    OFFICE = ('doc','docx','xls','xlsx','ppt','pptx','odt','ods','odp')
    ARCHIVE = ('zip','rar','7z','tar','gz','bz2','xz')
    
    preview = ""
    if ext in VIDEO:
        preview = '<video id="p" playsinline controls crossorigin style="width:100%;max-height:78vh;background:#000"><source src="'+url+'"></video><link rel="stylesheet" href="https://cdn.plyr.io/3.7.8/plyr.css"><script src="https://cdn.plyr.io/3.7.8/plyr.polyfilled.js"></script><script>new Plyr("#p",{settings:["quality","speed","loop"]})</script>'
    elif ext in AUDIO:
        preview = '<div style="padding:60px 20px;text-align:center"><div style="font-size:80px;margin-bottom:20px">🎵</div><audio id="p" controls style="width:100%;max-width:720px"><source src="'+url+'"></audio><div style="margin-top:16px;color:#9ca3af">'+name+'</div></div><link rel="stylesheet" href="https://cdn.plyr.io/3.7.8/plyr.css"><script src="https://cdn.plyr.io/3.7.8/plyr.polyfilled.js"></script><script>new Plyr("#p")</script>'
    elif ext in IMAGE:
        preview = '<div style="text-align:center"><img src="'+url+'" style="max-width:100%;max-height:78vh;border-radius:12px;cursor:zoom-in" onclick="window.open(\''+url+'\',\'_blank\')"></div>'
    elif ext in PDF:
        preview = '<iframe src="https://mozilla.github.io/pdf.js/web/viewer.html?file='+quote(url)+'" style="width:100%;height:78vh;border:0;border-radius:12px;background:#fff"></iframe>'
    elif ext in TEXT or ext in CODE:
        try:
            txt = requests.get(url, timeout=10).text[:200000]
            esc = txt.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            preview = '<pre style="margin:0;background:#0b1220;padding:20px;border-radius:12px;max-height:78vh;overflow:auto;font-size:13px;line-height:1.5"><code class="language-'+ext+'">'+esc+'</code></pre><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css"><script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script><script>hljs.highlightAll()</script>'
        except:
            preview = '<div style="padding:60px;text-align:center">Cannot preview</div>'
    elif ext in OFFICE:
        preview = '<iframe src="https://view.officeapps.live.com/op/embed.aspx?src='+quote(url)+'" style="width:100%;height:78vh;border:0;border-radius:12px;background:#fff"></iframe>'
    elif ext in ARCHIVE:
        preview = '<div style="text-align:center;padding:80px"><div style="font-size:80px">📦</div><div style="margin-top:16px">Archive file</div><a href="'+url+'" download style="display:inline-block;margin-top:20px;padding:12px 20px;background:#3b82f6;color:#fff;border-radius:10px;text-decoration:none">Download</a></div>'
    else:
        preview = '<div style="text-align:center;padding:80px"><div style="font-size:80px;opacity:.4">📄</div><div style="margin-top:12px">'+ext.upper()+' file</div><a href="'+url+'" download style="display:inline-block;margin-top:20px;padding:12px 20px;background:#3b82f6;color:#fff;border-radius:10px;text-decoration:none">Download</a></div>'
    
    size = f["size"]; size_str = f"{size/1024/1024:.2f} MB" if size>1024*1024 else f"{size/1024:.1f} KB"
    
    html = """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>"""+name+"""</title>
<style>body{margin:0;background:#0b1220;color:#e5e7eb;font-family:system-ui} .w{max-width:1200px;margin:0 auto;padding:20px} .c{background:#111827;border:1px solid #1f2937;border-radius:16px;padding:20px;margin-bottom:16px} .t{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px} a{color:#9ca3af;text-decoration:none} a:hover{color:#fff} .b{padding:9px 14px;background:#1f2937;border:1px solid #334155;border-radius:10px;color:#fff;text-decoration:none;font-size:14px;display:inline-block;margin-right:8px} .b.p{background:#3b82f6;border-color:#3b82f6} h1{margin:0;font-size:20px;word-break:break-all} .m{color:#9ca3af;font-size:13px;margin-top:4px} .g{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px} @media(max-width:700px){.g{grid-template-columns:1fr}} input{width:100%;background:#0b1220;border:1px solid #1f2937;border-radius:8px;padding:8px;color:#e5e7eb;font-family:monospace;font-size:12px}</style>
</head><body><div class=w><div class=t><a href="/">← Back</a><div style="color:#6b7280;font-size:13px">IA Drive</div></div>
<div class=c style="padding:0;overflow:hidden;background:#000">"""+preview+"""</div>
<div class=c><h1>"""+name+"""</h1><div class=m>"""+size_str+""" • """+ext.upper()+""" • """+f.get('mtime','')+"""</div>
<div style="margin-top:14px"><a class="b p" href="""+url+""" target="_blank">Open</a><a class=b href="""+url+""" download>Download</a><button class=b onclick="navigator.clipboard.writeText('"""+url+"""')">Copy Link</button><a class=b href="/dav/"""+quote(name)+"""">WebDAV</a></div>
<div class=g><div><div style="font-size:12px;color:#9ca3af;margin-bottom:4px">Direct URL</div><input value=""""+url+"""" readonly onclick="this.select()"></div><div><div style="font-size:12px;color:#9ca3af;margin-bottom:4px">Archive.org</div><input value=""""+f['ia_url']+"""" readonly onclick="this.select()"></div></div></div></div></body></html>"""
    return html

@app.route("/api/list")
def api_list(): return jsonify(ia_list()) if session.get("ok") else (jsonify([]),401)

@app.route("/api/upload", methods=["POST"])
def api_upload():
    if not session.get("ok"): return "",401
    f=request.files.get("file"); ia_put(secure_filename(f.filename), f.stream, f.content_type); return "",200

@app.route("/api/delete", methods=["DELETE"])
def api_del():
    if not session.get("ok"): return "",401
    ia_delete(request.args.get("name","")); return "",200

if __name__=="__main__": app.run(host="0.0.0.0",port=8080)
