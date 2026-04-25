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
                out.append({"name": n, "size": int(f.get("size",0)), "url": url, "mtime": f.get("mtime","")[:10]})
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
    return '''<!doctype html><html><head><meta charset=utf-8><title>IA Drive</title><meta name=viewport content="width=device-width,initial-scale=1">
<link rel=stylesheet href=https://cdnjs.cloudflare.com/ajax/libs/remixicon/4.2.0/remixicon.min.css>
<style>:root{--bg:#020617;--s:#0b1220;--b:#1e293b;--m:#64748b;--a:#3b82f6}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#e2e8f0;font-family:ui-sans-serif,system-ui}.app{display:flex;min-height:100vh}
.side{width:260px;background:var(--s);border-right:1px solid var(--b);padding:20px;position:fixed;left:0;top:0;bottom:0;overflow:auto;transition:transform.25s;z-index:40}
.side.hide{transform:translateX(-100%)}.logo{font-weight:700;font-size:18px;display:flex;align-items:center;gap:8px;margin-bottom:24px}.logo i{color:var(--a)}
.nav h4{margin:18px 0 8px;font-size:11px;text-transform:uppercase;color:var(--m);letter-spacing:.5px}
.nav a{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:10px;color:#cbd5e1;text-decoration:none;font-size:14px;margin:2px 0;cursor:pointer}
.nav a:hover,.nav a.on{background:#111a2e;color:#fff}.nav span{margin-left:auto;font-size:12px;color:var(--m)}
.main{flex:1;min-width:0;margin-left:260px;transition:margin.25s}
.top{position:sticky;top:0;background:#020617cc;backdrop-filter:blur(12px);border-bottom:1px solid var(--b);padding:12px 16px;display:flex;gap:10px;align-items:center;z-index:20}
.burger{display:none;background:none;border:0;color:#cbd5e1;font-size:22px;padding:6px;cursor:pointer}
.search{flex:1;max-width:600px;position:relative}.search input{width:100%;padding:10px 14px 10px 38px;background:var(--s);border:1px solid var(--b);border-radius:12px;color:#fff;font-size:14px;outline:none}.search i{position:absolute;left:12px;top:50%;transform:translateY(-50%);color:var(--m)}
.btn{padding:9px 13px;background:var(--s);border:1px solid var(--b);border-radius:10px;color:#cbd5e1;font-size:13px;cursor:pointer;display:flex;align-items:center;gap:6px}
.wrap{padding:20px}.up{background:var(--s);border:1px solid var(--b);border-radius:16px;padding:18px;margin-bottom:18px}
.up-h{display:flex;gap:10px;flex-wrap:wrap}.drop{flex:1;min-width:220px;border:2px dashed #334155;border-radius:12px;padding:16px;text-align:center;cursor:pointer}.drop.drag{border-color:var(--a);background:#0b1220}
.urlbox{display:flex;gap:8px;flex:1;min-width:220px}.urlbox input{flex:1;padding:10px;background:#020617;border:1px solid #334155;border-radius:10px;color:#fff}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px}
.card{background:var(--s);border:1px solid var(--b);border-radius:14px;overflow:hidden;text-decoration:none;color:inherit;display:block}.card:hover{transform:translateY(-2px);border-color:#334155}
.thumb{aspect-ratio:16/10;background:#000;display:grid;place-items:center;overflow:hidden}.thumb img,.thumb video{width:100%;height:100%;object-fit:cover}.thumb i{font-size:34px;opacity:.5}
.info{padding:10px}.name{font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.meta{font-size:11px;color:var(--m);margin-top:3px;display:flex;justify-content:space-between}
.overlay{position:fixed;inset:0;background:#0008;display:none;z-index:30}.overlay.show{display:block}
@media(max-width:900px){.side{transform:translateX(-100%)}.side.show{transform:translateX(0)}.main{margin-left:0}.burger{display:block}.wrap{padding:14px}.grid{grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}}
</style>
</head><body>
<div class=app>
  <aside id=side class=side>
    <div class=logo><i class="ri-hard-drive-3-fill"></i> IA Drive</div>
    <div class=nav>
      <h4>Library</h4>
      <a class=on data-f=all><i class="ri-apps-2-line"></i> All <span id=c-all>0</span></a>
      <a data-f=video><i class="ri-film-line"></i> Videos <span id=c-video>0</span></a>
      <a data-f=audio><i class="ri-music-2-line"></i> Audio <span id=c-audio>0</span></a>
      <a data-f=image><i class="ri-image-line"></i> Images <span id=c-image>0</span></a>
      <a data-f=pdf><i class="ri-file-pdf-line"></i> PDFs <span id=c-pdf>0</span></a>
      <a data-f=doc><i class="ri-file-text-line"></i> Docs <span id=c-doc>0</span></a>
      <a data-f=archive><i class="ri-file-zip-line"></i> Archives <span id=c-archive>0</span></a>
      <a data-f=code><i class="ri-code-line"></i> Code <span id=c-code>0</span></a>
    </div>
  </aside>
  <div id=ov class=overlay onclick="toggleSide()"></div>
  <main class=main>
    <div class=top>
      <button class=burger onclick="toggleSide()"><i class="ri-menu-line"></i></button>
      <div class=search><i class="ri-search-line"></i><input id=q placeholder="Search..."></div>
      <button class=btn onclick="location.reload()"><i class="ri-refresh-line"></i></button>
    </div>
    <div class=wrap>
      <div class=up>
        <div class=up-h>
          <div id=drop class=drop><i class="ri-upload-cloud-2-line"></i><div style="font-size:13px;margin-top:4px">Drop files or click</div></div>
          <div class=urlbox><input id=url placeholder="Paste URL to fetch..."><button class=btn id=urlbtn>Fetch</button></div>
        </div>
        <input id=fi type=file multiple hidden>
        <div id=st style="margin-top:8px;font-size:12px;color:var(--m)"></div>
      </div>
      <div id=grid class=grid></div>
    </div>
  </main>
</div>
<script>
let files=[],filter='all';
const types={video:['mp4','webm','mov','mkv','avi'],audio:['mp3','wav','flac','m4a','ogg'],image:['png','jpg','jpeg','gif','webp','svg'],pdf:['pdf'],doc:['doc','docx','xls','xlsx','ppt','pptx','txt','md','rtf'],archive:['zip','rar','7z','gz','tar'],code:['js','ts','py','html','css','json','php','java']};
function ext(n){return n.split('.').pop().toLowerCase()}
function kind(n){const e=ext(n);for(const k in types)if(types[k].includes(e))return k;return 'other'}
function fmt(b){return b>1e9?(b/1e9).toFixed(1)+'GB':b>1e6?(b/1e6).toFixed(1)+'MB':(b/1e3).toFixed(0)+'KB'}
function toggleSide(){document.getElementById('side').classList.toggle('show');document.getElementById('ov').classList.toggle('show')}
async function load(){files=await(await fetch('/api/list')).json();update();render()}
function update(){const c={all:files.length};for(const k in types)c[k]=0;files.forEach(f=>{const k=kind(f.name);if(c[k]!=null)c[k]++});for(const k in c){const e=document.getElementById('c-'+k);if(e)e.textContent=c[k]}}
function render(){const t=q.value.toLowerCase();const list=files.filter(f=>(filter==='all'||kind(f.name)===filter)&&f.name.toLowerCase().includes(t));grid.innerHTML=list.length?'':'<div style="grid-column:1/-1;text-align:center;padding:60px;color:var(--m)">No files</div>';list.forEach(f=>{const e=ext(f.name);const isI=types.image.includes(e);const isV=types.video.includes(e);const th=isI?'<img src="'+f.url+'" loading=lazy>':isV?'<video src="'+f.url+'#t=0.5" muted></video>':'<i class="ri-file-line"></i>';grid.innerHTML+='<a class=card href="/file/'+encodeURIComponent(f.name)+'"><div class=thumb>'+th+'</div><div class=info><div class=name>'+f.name+'</div><div class=meta><span>'+e.toUpperCase()+'</span><span>'+fmt(f.size)+'</span></div></div></a>'})}
document.querySelectorAll('.nav a').forEach(a=>a.onclick=()=>{document.querySelectorAll('.nav a').forEach(x=>x.classList.remove('on'));a.classList.add('on');filter=a.dataset.f;render();if(window.innerWidth<900)toggleSide()});
async function up(f){const fd=new FormData();fd.append('file',f);await fetch('/api/upload',{method:'POST',body:fd})}
async function handle(l){for(const f of l){st.textContent='Uploading '+f.name;await up(f)}st.textContent='Done';setTimeout(()=>st.textContent='',1500);load()}
drop.onclick=()=>fi.click();drop.ondragover=e=>{e.preventDefault();drop.classList.add('drag')};drop.ondragleave=()=>drop.classList.remove('drag');drop.ondrop=e=>{e.preventDefault();drop.classList.remove('drag');handle([...e.dataTransfer.files])};fi.onchange=()=>handle([...fi.files]);urlbtn.onclick=async()=>{const u=url.value.trim();if(!u)return;st.textContent='Fetching...';await fetch('/api/upload-url',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:u})});url.value='';st.textContent='Fetched';load()};q.oninput=render;load()
</script></body></html>'''

@app.route("/file/<path:name>")
def view(name):
    f = next((x for x in ia_list() if x["name"]==name), None)
    if not f: return "Not found",404
    url = f["url"]; ext = name.rsplit(".",1)[-1].lower() if "." in name else ""; size = f"{f['size']/1024/1024:.1f} MB"

    if ext in ("mp4","webm","mov","mkv","avi","m4v"):
        player = '<video id="v" controls playsinline style="width:100%;max-height:82vh;background:#000" src="'+url+'"></video><link rel=stylesheet href=https://cdn.plyr.io/3.7.8/plyr.css><script src=https://cdn.plyr.io/3.7.8/plyr.js></script><script>new Plyr("#v")</script>'
    elif ext in ("mp3","wav","flac","m4a","ogg","aac"):
        player = '<div style="padding:70px 20px;max-width:900px;margin:auto"><audio id="a" controls style="width:100%" src="'+url+'"></audio></div><link rel=stylesheet href=https://cdn.plyr.io/3.7.8/plyr.css><script src=https://cdn.plyr.io/3.7.8/plyr.js></script><script>new Plyr("#a")</script>'
    elif ext in ("png","jpg","jpeg","gif","webp","svg","avif","bmp"):
        player = '<div style="display:grid;place-items:center;min-height:60vh;background:#000;padding:20px"><img src="'+url+'" style="max-width:100%;max-height:80vh;object-fit:contain"></div>'
    elif ext=="pdf":
        player = '<iframe src="https://mozilla.github.io/pdf.js/web/viewer.html?file='+quote(url)+'" style="width:100%;height:85vh;border:0;background:#fff"></iframe>'
    elif ext in ("txt","md","json","js","py","html","css","log","csv","xml","yml","yaml"):
        try: txt=requests.get(url,timeout=6).text[:300000].replace("&","&amp;").replace("<","&lt;"); player='<pre style="margin:0;padding:20px;background:#000;color:#ddd;max-height:80vh;overflow:auto;font-size:13px;line-height:1.5">'+txt+'</pre>'
        except: player='<div style="padding:60px;text-align:center;color:#64748b">Cannot preview</div>'
    elif ext in ("doc","docx","xls","xlsx","ppt","pptx"):
        player = '<iframe src="https://view.officeapps.live.com/op/embed.aspx?src='+quote(url)+'" style="width:100%;height:85vh;border:0;background:#fff"></iframe>'
    else:
        player = '<div style="text-align:center;padding:100px 20px"><i class="ri-file-3-line" style="font-size:64px;opacity:.3"></i><h3 style="margin:16px 0 8px">'+name+'</h3><p style="color:#64748b">'+ext.upper()+' • '+size+'</p></div>'

    return '''<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>'''+name+'''</title>
<link rel=stylesheet href=https://cdnjs.cloudflare.com/ajax/libs/remixicon/4.2.0/remixicon.min.css>
<style>body{margin:0;background:#020617;color:#e2e8f0;font-family:system-ui}.top{position:sticky;top:0;z-index:30;background:#020617f2;backdrop-filter:blur(14px);border-bottom:1px solid #1e293b}.bar{max-width:1400px;margin:0 auto;padding:12px 20px;display:flex;align-items:center;gap:10px}.back{color:#94a3b8;text-decoration:none;display:flex;align-items:center;gap:6px;padding:8px 12px;border-radius:10px}.back:hover{background:#0b1220;color:#fff}.title{flex:1;min-width:0;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:15px}.menu{display:flex;gap:8px}.btn{padding:9px 13px;background:#0b1220;border:1px solid #1e293b;border-radius:10px;color:#cbd5e1;font-size:13px;cursor:pointer;display:flex;align-items:center;gap:6px;text-decoration:none;white-space:nowrap}.btn:hover{background:#111a2e}.btn.p{background:#3b82f6;border-color:#3b82f6;color:#fff}.wrap{max-width:1400px;margin:0 auto;padding:20px}.player{background:#0b1220;border:1px solid #1e293b;border-radius:18px;overflow:hidden}.info{margin-top:14px;background:#0b1220;border:1px solid #1e293b;border-radius:14px;padding:16px 18px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}.meta h1{margin:0 0 4px;font-size:16px;font-weight:600;word-break:break-all}.meta div{color:#64748b;font-size:13px}.dd{position:relative}.ddm{position:absolute;top:100%;right:0;margin-top:6px;background:#0b1220;border:1px solid #1e293b;border-radius:12px;min-width:180px;padding:6px;display:none;z-index:50}.ddm.show{display:block}.ddm a{display:flex;gap:8px;padding:8px 10px;border-radius:8px;color:#cbd5e1;text-decoration:none;font-size:13px}.ddm a:hover{background:#1e293b}.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);background:#0b1220;border:1px solid #1e293b;padding:10px 14px;border-radius:10px;display:none;font-size:13px}@media(max-width:700px){.menu.btn span{display:none}.bar{padding:10px 14px}}</style>
</head><body>
<div class=top><div class=bar>
  <a href="/" class=back><i class="ri-arrow-left-line"></i> Back</a>
  <div class=title>'''+name+'''</div>
  <div class=menu>
    <button class=btn onclick="copy()"><i class="ri-clipboard-line"></i><span>Copy</span></button>
    <a class=btn href="'''+url+'''" target=_blank><i class="ri-external-link-line"></i><span>Open</span></a>
    <div class=dd><button class=btn onclick="tog()"><i class="ri-share-line"></i><span>Share</span></button><div id=dd class=ddm><a href="#" onclick="share();return false"><i class="ri-share-forward-line"></i> Share</a><a href="https://t.me/share/url?url='''+quote(url)+'''" target=_blank><i class="ri-telegram-line"></i> Telegram</a><a href="https://wa.me/?text='''+quote(url)+'''" target=_blank><i class="ri-whatsapp-line"></i> WhatsApp</a></div>
    <button class="btn p" onclick="dl()"><i class="ri-download-2-line"></i><span>Download</span></button>
  </div>
</div></div>
<div class=wrap><div class=player>'''+player+'''</div><div class=info><div class=meta><h1>'''+name+'''</h1><div>'''+size+''' • '''+ext.upper()+'''</div></div><div style="display:flex;gap:8px"><button class=btn onclick="dl()"><i class="ri-download-line"></i> Download</button></div></div></div>
<div id=t class=toast></div>
<script>
const url="'''+url+'''"; const name="'''+name.replace('"','')+'''";
function toast(m){const e=document.getElementById('t');e.textContent=m;e.style.display='block';setTimeout(()=>e.style.display='none',1800)}
function copy(){navigator.clipboard.writeText(url).then(()=>toast('Link copied'))}
function tog(){document.getElementById('dd').classList.toggle('show')}
function dl(){const a=document.createElement('a');a.href=url;a.download=name;a.click();toast('Downloading...')}
async function share(){if(navigator.share){try{await navigator.share({title:name,url:url})}catch(e){}}else{copy()}}
document.addEventListener('click',e=>{if(!e.target.closest('.dd'))document.getElementById('dd').classList.remove('show')})
</script></body></html>'''

@app.route("/api/list")
def api_list(): return jsonify(ia_list())

@app.route("/api/upload", methods=["POST"])
def api_up():
    f = request.files["file"]
    ia_put(secure_filename(f.filename), f.stream, f.content_type)
    return "",200

@app.route("/api/upload-url", methods=["POST"])
def api_url():
    data = request.get_json()
    u = data.get("url","")
    try:
        r = requests.get(u, stream=True, timeout=60)
        name = secure_filename(urlparse(u).path.split("/")[-1] or f"file-{int(time.time())}")
        ia_put(name, r.raw, r.headers.get("Content-Type"))
        return "",200
    except: return "",500

@app.route("/health")
def health(): return "ok"

if __name__=="__main__": app.run(host="0.0.0.0",port=8080)
