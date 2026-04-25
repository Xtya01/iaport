import os, requests, time
from flask import Flask, request, session, redirect, jsonify, Response, make_response
from werkzeug.utils import secure_filename
from urllib.parse import quote
from collections import defaultdict, deque

IA_BUCKET = os.getenv("IA_BUCKET", "")
IA_ACCESS = os.getenv("IA_ACCESS_KEY", "")
IA_SECRET = os.getenv("IA_SECRET_KEY", "")
LOGIN_PIN = os.getenv("LOGIN_PIN", "2383")
DAV_USER = os.getenv("DAV_USER", "admin")
DAV_PASS = os.getenv("DAV_PASS", "2383")
ENDPOINT = "https://s3.us.archive.org"
WORKER = os.getenv("WORKER_MEDIA_BASE", "").rstrip("/")
AUTH = f"LOW {IA_ACCESS}:{IA_SECRET}"

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "secret123")

fails = defaultdict(deque)
bans = {}

def get_ip():
    return request.headers.get('CF-Connecting-IP') or request.remote_addr

@app.before_request
def block():
    if any(request.path.lower().startswith(p) for p in ['/admin','/wp','/php','/.env']):
        return "", 404
    if get_ip() in bans and bans[get_ip()] > time.time():
        return "Banned", 429

def ia_list():
    r = requests.get(f"https://archive.org/metadata/{IA_BUCKET}", timeout=10)
    out = []
    for f in r.json().get("files", []):
        n = f.get("name", "")
        if n and not n.startswith("_"):
            url = f"{WORKER}/{IA_BUCKET}/{quote(n)}" if WORKER else f"https://archive.org/download/{IA_BUCKET}/{quote(n)}"
            out.append({"name": n, "size": int(f.get("size",0)), "url": url})
    return sorted(out, key=lambda x: x["name"].lower())

@app.route("/login", methods=["GET","POST"])
def login():
    err = ""
    if request.method == "POST":
        if request.form.get("pin") == LOGIN_PIN:
            session["ok"] = True
            return redirect("/")
        err = "Wrong PIN"
    return f"""<!doctype html><html><head><meta charset=utf-8><title>Login</title><style>body{{margin:0;height:100vh;display:grid;place-items:center;background:#020617;color:#fff;font-family:system-ui}}.box{{background:#0b1220;padding:40px;border-radius:20px;width:340px;border:1px solid #1e293b}}input{{width:100%;padding:14px;background:#000;border:1px solid #334155;border-radius:12px;color:#fff;margin:16px 0}}button{{width:100%;padding:14px;background:#3b82f6;border:0;border-radius:12px;color:#fff;font-weight:600;cursor:pointer}}</style></head><body><div class=box><h2>IA Drive</h2><p style="color:#64748b">Enter PIN</p>{'<div style="color:#f87171;margin-bottom:10px">'+err+'</div>' if err else ''}<form method=post><input name=pin type=password autofocus><button>Unlock</button></form></div></body></html>"""

@app.before_request
def gate():
    if request.path in ["/login","/health"] or request.path.startswith("/dav"): return
    if not session.get("ok") and not request.path.startswith("/file"):
        if request.path.startswith("/api"): return "", 401
        return redirect("/login")

@app.route("/")
def home():
    return """<!doctype html><html><head><meta charset=utf-8><title>IA Drive</title><meta name=viewport content="width=device-width,initial-scale=1"><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/remixicon/4.2.0/remixicon.min.css"><style>:root{--bg:#020617;--c:#0b1220;--b:#1e293b;--m:#64748b}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#e2e8f0;font-family:system-ui}.top{position:sticky;top:0;background:#020617cc;backdrop-filter:blur(12px);border-bottom:1px solid var(--b);padding:14px 20px;display:flex;gap:12px;align-items:center}.srch{flex:1;max-width:500px;position:relative}.srch input{width:100%;padding:10px 12px 10px 36px;background:var(--c);border:1px solid var(--b);border-radius:10px;color:#fff}.srch i{position:absolute;left:10px;top:50%;transform:translateY(-50%);color:var(--m)}.grid{max-width:1400px;margin:20px auto;padding:0 20px;display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px}.card{background:var(--c);border:1px solid var(--b);border-radius:14px;overflow:hidden;text-decoration:none;color:inherit;transition:.15s}.card:hover{transform:translateY(-2px);border-color:#334155}.th{aspect-ratio:16/10;background:#000;display:grid;place-items:center;overflow:hidden}.th img,.th video{width:100%;height:100%;object-fit:cover}.th i{font-size:40px;opacity:.6}.info{padding:10px}.nm{font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.mt{font-size:11px;color:var(--m);margin-top:2px}</style></head><body><div class=top><div style="font-weight:700;display:flex;align-items:center;gap:6px"><i class="ri-hard-drive-3-fill" style="color:#3b82f6"></i>IA Drive</div><div class=srch><i class="ri-search-line"></i><input id=q placeholder="Search..."></div><a href="/logout" style="color:var(--m);text-decoration:none">Logout</a></div><div id=g class=grid></div><script>let fs=[];async function ld(){fs=await(await fetch('/api/list')).json();rn()}function ic(n){const e=n.split('.').pop().toLowerCase();return{mp4:'ri-film-line',mov:'ri-film-line',mkv:'ri-film-line',mp3:'ri-music-2-line',wav:'ri-music-2-line',pdf:'ri-file-pdf-line',zip:'ri-file-zip-line'}[e]||'ri-file-line'}function rn(){const t=document.getElementById('q').value.toLowerCase();const g=document.getElementById('g');g.innerHTML='';fs.filter(f=>f.name.toLowerCase().includes(t)).forEach(f=>{const e=f.name.split('.').pop().toLowerCase();const isMedia=['png','jpg','jpeg','gif','webp','mp4','webm'].includes(e);const th=isMedia?`<div class=th>${e.match(/mp4|webm/)?`<video src="${f.url}#t=0.5" muted></video>`:`<img src="${f.url}" loading=lazy>`}</div>`:`<div class=th><i class="${ic(f.name)}"></i></div>`;g.innerHTML+=`<a class=card href="/file/${encodeURIComponent(f.name)}">${th}<div class=info><div class=nm>${f.name}</div><div class=mt>${(f.size/1024/1024).toFixed(1)} MB</div></div></a>`})}document.getElementById('q').oninput=rn;ld()</script></body></html>"""

@app.route("/file/<path:name>")
def view(name):
    files = ia_list()
    f = next((x for x in files if x["name"] == name), None)
    if not f: return "Not found", 404
    url = f["url"]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""

    if ext in ("mp4","webm","mov","mkv","avi"):
        player = f'<video id="p" playsinline controls><source src="{url}"></video><link rel="stylesheet" href="https://cdn.plyr.io/3.7.8/plyr.css"><script src="https://cdn.plyr.io/3.7.8/plyr.js"></script><script>new Plyr("#p")</script>'
    elif ext in ("mp3","wav","flac","m4a","ogg"):
        player = f'<div style="padding:60px"><audio id="p" controls><source src="{url}"></audio></div><link rel="stylesheet" href="https://cdn.plyr.io/3.7.8/plyr.css"><script src="https://cdn.plyr.io/3.7.8/plyr.js"></script><script>new Plyr("#p")</script>'
    elif ext in ("png","jpg","jpeg","gif","webp","svg"):
        player = f'<img src="{url}" style="max-width:100%;max-height:85vh;display:block;margin:auto">'
    elif ext == "pdf":
        player = f'<iframe src="https://mozilla.github.io/pdf.js/web/viewer.html?file={url}" style="width:100%;height:85vh;border:0"></iframe>'
    elif ext in ("txt","md","json","js","py","html","css","log"):
        txt = requests.get(url, timeout=5).text[:200000].replace("&","&amp;").replace("<","&lt;")
        player = f'<pre style="background:#000;color:#cbd5e1;padding:20px;margin:0;max-height:80vh;overflow:auto;font-size:13px"><code>{txt}</code></pre>'
    elif ext in ("doc","docx","xls","xlsx","ppt","pptx"):
        player = f'<iframe src="https://view.officeapps.live.com/op/embed.aspx?src={url}" style="width:100%;height:85vh;border:0;background:#fff"></iframe>'
    else:
        player = f'<div style="text-align:center;padding:100px"><a href="{url}" download style="padding:14px 24px;background:#3b82f6;color:#fff;border-radius:12px;text-decoration:none;display:inline-block">Download {name}</a></div>'

    return f"""<!doctype html><html><head><meta charset=utf-8><title>{name}</title><meta name=viewport content="width=device-width,initial-scale=1"><style>body{{margin:0;background:#020617;color:#fff;font-family:system-ui}}.top{{position:sticky;top:0;background:#020617ee;padding:12px 16px;border-bottom:1px solid #1e293b;display:flex;align-items:center;gap:12px;backdrop-filter:blur(8px)}}.top a{{color:#94a3b8;text-decoration:none}}.wrap{{max-width:1200px;margin:16px auto;padding:0 16px}}.box{{background:#0b1220;border:1px solid #1e293b;border-radius:16px;overflow:hidden}}video,audio{{width:100%;display:block}}</style></head><body><div class=top><a href="/">← Back</a><div style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500">{name}</div><a href="{url}" download>Download</a></div><div class=wrap><div class=box>{player}</div></div></body></html>"""

@app.route("/api/list")
def api_list():
    return jsonify(ia_list())

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/health")
def health():
    return "ok"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
