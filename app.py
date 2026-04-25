import os, requests
from flask import Flask, request, session, redirect, jsonify, Response
from werkzeug.utils import secure_filename
from urllib.parse import quote

IA_BUCKET = os.getenv("IA_BUCKET", "junk-manage-caution")
IA_ACCESS = os.getenv("IA_ACCESS_KEY", "")
IA_SECRET = os.getenv("IA_SECRET_KEY", "")
LOGIN_PIN = os.getenv("LOGIN_PIN", "2383")
ENDPOINT = "https://s3.us.archive.org"
WORKER = os.getenv("WORKER_MEDIA_BASE", "").rstrip("/")
AUTH = f"LOW {IA_ACCESS}:{IA_SECRET}"

app = Flask(__name__)
app.secret_key = "secret"

def ia_list():
    try:
        r = requests.get(f"https://archive.org/metadata/{IA_BUCKET}", timeout=10)
        out = []
        for f in r.json().get("files", []):
            n = f.get("name", "")
            if n and not n.startswith("_"):
                url = f"{WORKER}/{IA_BUCKET}/{quote(n)}" if WORKER else f"https://archive.org/download/{IA_BUCKET}/{quote(n)}"
                out.append({"name": n, "size": int(f.get("size",0)), "url": url})
        return sorted(out, key=lambda x: x["name"].lower())
    except: return []

@app.before_request
def gate():
    if request.path in ["/login"] or request.path.startswith(("/api","/file","/health")): 
        if request.path.startswith("/api") and not session.get("ok"): return "",401
        return
    if not session.get("ok"): return redirect("/login")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST" and request.form.get("pin")==LOGIN_PIN:
        session["ok"]=True
        return redirect("/")
    return '<form method=post style="margin:100px auto;width:300px;font-family:sans-serif"><h2>IA Drive</h2><input name=pin type=password placeholder=PIN style="width:100%;padding:10px"><button style="width:100%;padding:10px;margin-top:10px;background:#3b82f6;color:#fff;border:0">Login</button></form>'

@app.route("/")
def home():
    html = """<!doctype html><html><head><meta charset=utf-8><title>IA Drive</title>
<link rel=stylesheet href=https://cdnjs.cloudflare.com/ajax/libs/remixicon/4.2.0/remixicon.min.css>
<style>body{margin:0;background:#020617;color:#fff;font-family:system-ui}.h{padding:14px 20px;border-bottom:1px solid #1e293b;display:flex;gap:12px;align-items:center}.s{flex:1;max-width:500px;position:relative}.s input{width:100%;padding:8px 12px 8px 32px;background:#0b1220;border:1px solid #1e293b;border-radius:8px;color:#fff}.s i{position:absolute;left:8px;top:50%;transform:translateY(-50%);color:#64748b}.g{max-width:1400px;margin:20px auto;padding:0 20px;display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px}.c{background:#0b1220;border:1px solid #1e293b;border-radius:12px;overflow:hidden;text-decoration:none;color:#fff;display:block}.c:hover{transform:translateY(-2px)}.t{aspect-ratio:16/10;background:#000;display:grid;place-items:center}.t img,.t video{width:100%;height:100%;object-fit:cover}.t i{font-size:36px;opacity:.5}.i{padding:10px}.n{font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.m{font-size:11px;color:#64748b;margin-top:3px}</style>
</head><body><div class=h><b>IA Drive</b><div class=s><i class="ri-search-line"></i><input id=q placeholder=Search></div></div><div id=g class=g></div>
<script>
let files=[];
async function load(){files=await (await fetch('/api/list')).json();render()}
function render(){const t=q.value.toLowerCase();g.innerHTML='';files.filter(f=>f.name.toLowerCase().includes(t)).forEach(f=>{const e=f.name.split('.').pop().toLowerCase();const isImg=['png','jpg','jpeg','gif','webp'].includes(e);const isVid=['mp4','webm','mov'].includes(e);let thumb='';if(isImg){thumb='<img src="'+f.url+'" loading=lazy>'}else if(isVid){thumb='<video src="'+f.url+'#t=0.5" muted></video>'}else{thumb='<i class="ri-file-line"></i>'};g.innerHTML+='<a class=c href="/file/'+encodeURIComponent(f.name)+'"><div class=t>'+thumb+'</div><div class=i><div class=n>'+f.name+'</div><div class=m>'+(f.size/1024/1024).toFixed(1)+' MB</div></div></a>'})}
q.oninput=render;load()
</script></body></html>"""
    return html

@app.route("/file/<path:name>")
def view(name):
    f = next((x for x in ia_list() if x["name"]==name), None)
    if not f: return "404",404
    url = f["url"]; ext = name.rsplit(".",1)[-1].lower() if "." in name else ""
    
    if ext in ("mp4","webm","mov","mkv"):
        player = '<video controls style="width:100%;background:#000" src="'+url+'"></video>'
    elif ext in ("mp3","wav","flac"):
        player = '<div style="padding:60px"><audio controls style="width:100%" src="'+url+'"></audio></div>'
    elif ext in ("png","jpg","jpeg","gif","webp"):
        player = '<img src="'+url+'" style="max-width:100%;max-height:85vh;display:block;margin:auto">'
    elif ext=="pdf":
        player = '<iframe src="https://mozilla.github.io/pdf.js/web/viewer.html?file='+quote(url)+'" style="width:100%;height:85vh;border:0"></iframe>'
    else:
        player = '<div style="padding:100px;text-align:center"><a href="'+url+'" download style="padding:12px 20px;background:#3b82f6;color:#fff;border-radius:8px;text-decoration:none">Download</a></div>'
    
    return '<!doctype html><html><head><meta charset=utf-8><title>'+name+'</title><style>body{margin:0;background:#020617;color:#fff;font-family:system-ui}.t{padding:12px 16px;background:#020617;border-bottom:1px solid #1e293b;display:flex;gap:10px;align-items:center;position:sticky;top:0}.b{padding:8px 12px;background:#0b1220;border:1px solid #1e293b;border-radius:8px;color:#ccc;text-decoration:none;font-size:13px}.w{max-width:1200px;margin:20px auto;padding:0 16px}.p{background:#0b1220;border:1px solid #1e293b;border-radius:12px;overflow:hidden}</style></head><body><div class=t><a href="/" class=b>← Back</a><div style="flex:1;font-weight:600;overflow:hidden;text-overflow:ellipsis">'+name+'</div><button class=b onclick="dl()">Download</button></div><div class=w><div class=p>'+player+'</div></div><script>function dl(){const a=document.createElement("a");a.href="'+url+'";a.download="'+name+'";a.click()}</script></body></html>'

@app.route("/api/list")
def api_list(): return jsonify(ia_list())

@app.route("/api/upload", methods=["POST"])
def upload():
    f = request.files["file"]
    h = {"authorization": AUTH, "x-amz-auto-make-bucket":"1", "Content-Type": f.content_type}
    requests.put(f"{ENDPOINT}/{IA_BUCKET}/{secure_filename(f.filename)}", data=f.stream, headers=h)
    return "",200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
