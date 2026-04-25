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
app.secret_key = os.getenv("FLASK_SECRET", "ia-drive-secret-2026")

fails = defaultdict(deque)
bans = {}

def get_ip():
    return request.headers.get('CF-Connecting-IP') or request.remote_addr

def ia_list():
    try:
        r = requests.get(f"https://archive.org/metadata/{IA_BUCKET}", timeout=12)
        out = []
        for f in r.json().get("files", []):
            n = f.get("name", "")
            if n and not n.startswith("_"):
                url = f"{WORKER}/{IA_BUCKET}/{quote(n)}" if WORKER else f"https://archive.org/download/{IA_BUCKET}/{quote(n)}"
                out.append({"name": n, "size": int(f.get("size",0)), "mtime": f.get("mtime","")[:10], "url": url})
        return sorted(out, key=lambda x: x["name"].lower())
    except:
        return []

@app.before_request
def sec():
    if any(request.path.lower().startswith(p) for p in ['/admin','/wp','/php','/.env','.git']):
        return "", 404

@app.before_request
def gate():
    if request.path in ['/login','/health'] or request.path.startswith('/dav'): return
    if request.path.startswith(('/api','/file')):
        if request.path.startswith('/api') and not session.get('ok'): return jsonify(error='auth'),401
        return
    if not session.get('ok'): return redirect('/login')

@app.route('/login', methods=['GET','POST'])
def login():
    err=''
    if request.method=='POST':
        if request.form.get('pin')==LOGIN_PIN:
            session['ok']=True
            return redirect('/')
        err='Wrong PIN'
    return '''<!doctype html><html><head><meta charset=utf-8><title>Login</title><style>body{margin:0;height:100vh;display:grid;place-items:center;background:#020617;color:#fff;font-family:system-ui}.c{background:#0b1220;padding:40px;border-radius:20px;width:340px;border:1px solid #1e293b}input{width:100%;padding:14px;background:#000;border:1px solid #334155;border-radius:12px;color:#fff;margin:16px 0}button{width:100%;padding:14px;background:#3b82f6;border:0;border-radius:12px;color:#fff;font-weight:600}</style></head><body><div class=c><h2>IA Drive</h2>'''+(f'<div style="color:#f88;margin-bottom:10px">{err}</div>' if err else '')+'''<form method=post><input name=pin type=password autofocus><button>Unlock</button></form></div></body></html>'''

@app.route('/')
def home():
    return open(__file__).read().split("##HOME##")[1]

@app.route('/file/<path:name>')
def view(name):
    files = ia_list()
    f = next((x for x in files if x["name"]==name), None)
    if not f: return "404",404
    url = f['url']; ext = name.rsplit('.',1)[-1].lower() if '.' in name else ''; size = f"{f['size']/1024/1024:.1f} MB"
    
    if ext in ('mp4','webm','mov','mkv'):
        player = '<video id=p controls playsinline><source src="'+url+'"></video><link rel=stylesheet href=https://cdn.plyr.io/3.7.8/plyr.css><script src=https://cdn.plyr.io/3.7.8/plyr.js></script><script>new Plyr("#p")</script>'
    elif ext in ('mp3','wav','flac','m4a'):
        player = '<div style="padding:60px"><audio id=p controls><source src="'+url+'"></audio></div><link rel=stylesheet href=https://cdn.plyr.io/3.7.8/plyr.css><script src=https://cdn.plyr.io/3.7.8/plyr.js></script><script>new Plyr("#p")</script>'
    elif ext in ('png','jpg','jpeg','gif','webp'):
        player = '<img src="'+url+'" style="max-width:100%;max-height:85vh;display:block;margin:auto">'
    elif ext=='pdf':
        player = '<iframe src="https://mozilla.github.io/pdf.js/web/viewer.html?file='+quote(url)+'" style="width:100%;height:85vh;border:0"></iframe>'
    else:
        try: txt=requests.get(url,timeout=5).text[:200000].replace('&','&amp;').replace('<','&lt;'); player='<pre style="background:#000;color:#ddd;padding:20px;max-height:80vh;overflow:auto">'+txt+'</pre>'
        except: player='<div style="padding:100px;text-align:center"><a href="'+url+'" download style="padding:14px 24px;background:#3b82f6;color:#fff;border-radius:12px;text-decoration:none">Download</a></div>'

    html = '''<!doctype html><html><head><meta charset=utf-8><title>'''+name+'''</title><meta name=viewport content="width=device-width,initial-scale=1"><link rel=stylesheet href=https://cdnjs.cloudflare.com/ajax/libs/remixicon/4.2.0/remixicon.min.css><style>body{margin:0;background:#020617;color:#e2e8f0;font-family:system-ui}.top{position:sticky;top:0;background:#020617f2;backdrop-filter:blur(12px);border-bottom:1px solid #1e293b;padding:12px 16px;display:flex;gap:10px;align-items:center}.btn{padding:8px 12px;background:#0b1220;border:1px solid #1e293b;border-radius:9px;color:#cbd5e1;text-decoration:none;font-size:13px;display:flex;gap:6px;align-items:center}.btn.p{background:#3b82f6;border-color:#3b82f6;color:#fff}.wrap{max-width:1200px;margin:16px auto;padding:0 16px}.box{background:#0b1220;border:1px solid #1e293b;border-radius:16px;overflow:hidden}video,audio{width:100%}</style></head><body>
<div class=top><a href="/" class=btn><i class="ri-arrow-left-line"></i>Back</a><div style="flex:1;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'''+name+'''</div>
<button class=btn onclick="navigator.clipboard.writeText('''+"'"+url+"'"+''')"><i class="ri-clipboard-line"></i>Copy</button>
<a class=btn href="'''+url+'''" target=_blank><i class="ri-external-link-line"></i>Open</a>
<button class=btn p onclick="dl()"><i class="ri-download-line"></i>Download</button>
</div>
<div class=wrap><div class=box>'''+player+'''</div><div style="margin-top:12px;padding:14px;background:#0b1220;border:1px solid #1e293b;border-radius:12px;display:flex;justify-content:space-between"><div><div style="font-weight:600">'''+name+'''</div><div style="color:#64748b;font-size:13px;margin-top:4px">'''+size+''' • '''+ext.upper()+'''</div></div></div></div>
<script>function dl(){const a=document.createElement('a');a.href="'''+url+'''";a.download="'''+name+'''";a.click()}</script>
</body></html>'''
    return html

@app.route('/api/list')
def api_list():
    return jsonify(ia_list())

@app.route('/api/upload', methods=['POST'])
def api_upload():
    f=request.files['file']
    h={"authorization":AUTH,"x-amz-auto-make-bucket":"1","x-archive-auto-make-bucket":"1","x-archive-meta01-collection":"opensource","x-archive-meta-mediatype":"data","Content-Type":f.content_type or 'application/octet-stream'}
    requests.put(f"{ENDPOINT}/{IA_BUCKET}/{secure_filename(f.filename)}", data=f.stream, headers=h, timeout=900)
    return '',200

@app.route('/health')
def health(): return 'ok'

if __name__=='__main__': app.run(host='0.0.0.0',port=8080)

##HOME##
<!doctype html><html><head><meta charset=utf-8><title>IA Drive</title><meta name=viewport content="width=device-width,initial-scale=1"><link rel=stylesheet href=https://cdnjs.cloudflare.com/ajax/libs/remixicon/4.2.0/remixicon.min.css><style>:root{--bg:#020617;--c:#0b1220;--b:#1e293b;--m:#64748b}body{margin:0;background:var(--bg);color:#e2e8f0;font-family:system-ui}.top{position:sticky;top:0;background:#020617cc;backdrop-filter:blur(10px);border-bottom:1px solid var(--b);padding:12px 20px;display:flex;gap:12px}.sr{flex:1;max-width:500px;position:relative}.sr input{width:100%;padding:9px 12px 9px 32px;background:var(--c);border:1px solid var(--b);border-radius:10px;color:#fff}.sr i{position:absolute;left:9px;top:50%;transform:translateY(-50%);color:var(--m)}.g{max-width:1400px;margin:20px auto;padding:0 20px;display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px}.cd{background:var(--c);border:1px solid var(--b);border-radius:14px;overflow:hidden;text-decoration:none;color:inherit}.cd:hover{transform:translateY(-2px);border-color:#334155}.th{aspect-ratio:16/10;background:#000;display:grid;place-items:center}.th img,.th video{width:100%;height:100%;object-fit:cover}.th i{font-size:36px;opacity:.6}.in{padding:10px}.nm{font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.mt{font-size:11px;color:var(--m);margin-top:2px}</style></head><body><div class=top><div style="font-weight:700"><i class="ri-hard-drive-3-fill" style="color:#3b82f6"></i> IA Drive</div><div class=sr><i class="ri-search-line"></i><input id=q placeholder=Search></div></div><div id=g class=g></div><script>let f=[];async function ld(){f=await(await fetch('/api/list')).json();rn()}function ic(n){const e=n.split('.').pop().toLowerCase();return{mp4:'ri-film-line',mp3:'ri-music-2-line',pdf:'ri-file-pdf-line'}[e]||'ri-file-line'}function rn(){const t=q.value.toLowerCase();g.innerHTML='';f.filter(x=>x.name.toLowerCase().includes(t)).forEach(x=>{const e=x.name.split('.').pop().toLowerCase();const m=['png','jpg','jpeg','gif','webp','mp4','webm'].includes(e);const th=m?`<div class=th>${e.match(/mp4|webm/)?`<video src="${x.url}#t=0.5" muted></video>`:`<img src="${x.url}" loading=lazy>`}</div>`:`<div class=th><i class="${ic(x.name)}"></i></div>`;g.innerHTML+=`<a class=cd href="/file/${encodeURIComponent(x.name)}">${th}<div class=in><div class=nm>${x.name}</div><div class=mt>${(x.size/1024/1024).toFixed(1)} MB</div></div></a>`})};q.oninput=rn;ld()</script></body></html>
