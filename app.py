import os, json, time, threading, sqlite3, mimetypes, requests, hashlib, subprocess
from datetime import datetime
from flask import Flask, request, jsonify, Response, redirect, session, make_response

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'ia-drive-stable-key-v4')

IA_BUCKET = os.environ.get('IA_BUCKET', 'junk-manage-caution')
IA_ACCESS = os.environ.get('IA_ACCESS_KEY', '')
IA_SECRET = os.environ.get('IA_SECRET_KEY', '')
PIN = os.environ.get('LOGIN_PIN', '2383')

DB = '/data/history.db'
os.makedirs('/data', exist_ok=True)
os.makedirs('/tmp/downloads', exist_ok=True)

def db_init():
    with sqlite3.connect(DB) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS history
            (id INTEGER PRIMARY KEY, filename TEXT, url TEXT, size INTEGER,
             status TEXT, speed INTEGER, started TEXT, finished TEXT)''')
db_init()

tasks = {}

def ia_upload(key, data, content_type):
    url = f'https://s3.us.archive.org/{IA_BUCKET}/{key}'
    h = {'authorization': f'LOW {IA_ACCESS}:{IA_SECRET}', 'x-amz-auto-make-bucket': '1',
         'x-archive-keep-old-version': '0', 'Content-Type': content_type}
    r = requests.put(url, data=data, headers=h, timeout=7200)
    r.raise_for_status()
    return f'https://archive.org/download/{IA_BUCKET}/{key}'

def ia_list():
    try:
        r = requests.get(f'https://s3.us.archive.org/{IA_BUCKET}?list-type=2',
                         auth=(IA_ACCESS, IA_SECRET), timeout=30)
        if r.status_code!= 200: return []
        import xml.etree.ElementTree as ET
        root = ET.fromstring(r.content)
        files = []
        for elem in root.iter():
            if elem.tag.endswith('Contents'):
                key = next((c.text for c in elem if c.tag.endswith('Key')), None)
                size = next((c.text for c in elem if c.tag.endswith('Size')), '0')
                if key and not key.endswith('/'):
                    files.append({'name': key, 'size': int(size),
                                 'url': f'https://archive.org/download/{IA_BUCKET}/{key}'})
        return files
    except: return []

def fetch_url_task(tid, url):
    tasks[tid] = {'status':'starting','downloaded':0,'total':0,'uploaded':0,'speed':0,'eta':0,'log':[],'speedHistory':[]}
    filepath = None
    try:
        filename = url.split('/')[-1].split('?')[0] or f'file_{int(time.time())}'
        filename = "".join(c for c in filename if c.isalnum() or c in '._- ')[:100].strip()
        tasks[tid]['filename'] = filename
        filepath = f'/tmp/downloads/{tid}_{filename}'

        tasks[tid]['log'].append(f'Starting {filename}')
                with sqlite3.connect(DB) as c:
            cur = c.execute('INSERT INTO history (filename,url,status,started) VALUES (?,?,?,?)',
                     (filename, url, 'running', datetime.now().strftime('%Y-%m-%d %H:%M')))
            hid = cur.lastrowid

        # FAST: aria2c with 16 connections
        cmd = ['aria2c', '-x16', '-s16', '-k1M', '--file-allocation=none',
               '--allow-overwrite=true', '--console-log-level=warn',
               '--summary-interval=1', '-d', '/tmp/downloads', '-o', f'{tid}_{filename}', url]

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        last_update = time.time()

        for line in proc.stdout:
            if time.time() - last_update > 0.5:
                if os.path.exists(filepath):
                    size = os.path.getsize(filepath)
                    tasks[tid]['downloaded'] = size
                    elapsed = time.time() - last_update
                    if elapsed > 0:
                        tasks[tid]['speed'] = int(size / (time.time() - (last_update - 0.5)))
                        tasks[tid]['speedHistory'].append(tasks[tid]['speed'])
                        if len(tasks[tid]['speedHistory']) > 60:
                            tasks[tid]['speedHistory'].pop(0)
                last_update = time.time()
            if '[#' in line:
                tasks[tid]['log'] = [line.strip()][-1:]

        proc.wait()
        if proc.returncode!= 0 or not os.path.exists(filepath):
            raise Exception("aria2c download failed")

        filesize = os.path.getsize(filepath)
        tasks[tid]['total'] = filesize
        tasks[tid]['downloaded'] = filesize
        tasks[tid]['status'] = 'uploading'
        tasks[tid]['log'].append(f'Downloaded {filesize//1024//1024}MB, uploading...')

        ct = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        with open(filepath, 'rb') as f:
            ia_upload(filename, f, ct)

        tasks[tid]['uploaded'] = filesize
        tasks[tid]['status'] = 'complete'
        tasks[tid]['log'].append('Complete')
        os.remove(filepath)

        with sqlite3.connect(DB) as c:
            c.execute('UPDATE history SET status=?,size=?,speed=?,finished=? WHERE id=?',
                     ('complete', filesize, tasks[tid]['speed'],
                      datetime.now().strftime('%Y-%m-%d %H:%M'), hid))
    except Exception as e:
        tasks[tid]['status'] = 'error'
        tasks[tid]['log'].append(f'Error: {str(e)}')
        if filepath and os.path.exists(filepath):
            try: os.remove(filepath)
            except: pass

@app.before_request
def auth():
    if request.path in ['/login', '/auth', '/health'] or request.path.startswith('/static'):
        return
    if request.path.startswith('/api') or request.path.startswith('/file'):
        if not session.get('auth') and request.cookies.get('pin')!= PIN:
            return jsonify({'error':'auth'}), 401
    if not session.get('auth') and request.cookies.get('pin')!= PIN:
        return redirect('/login')

@app.route('/login')
def login_page():
    return '''<!doctype html><html><head><meta name=viewport content="width=device-width,initial-scale=1">
<title>Login</title><style>body{margin:0;background:#020617;color:#e2e8f0;font-family:system-ui;display:grid;place-items:center;height:100vh}
.b{background:#0f172a;border:1px solid #1e293b;padding:32px;border-radius:16px;width:300px;text-align:center}
input{width:100%;padding:12px;background:#020617;border:1px solid #334155;border-radius:8px;color:#fff;font-size:18px;text-align:center;margin:16px 0;box-sizing:border-box}
button{width:100%;padding:12px;background:#3b82f6;border:0;border-radius:8px;color:#fff;font-weight:600;cursor:pointer}</style></head>
<body><div class=b><h2>IA Drive</h2><input id=p type=password placeholder="PIN" autofocus>
<button id=b>Unlock</button></div>
<script>
document.getElementById('b').onclick=()=>{fetch('/auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:document.getElementById('p').value})}).then(r=>r.ok?location='/':alert('Wrong PIN'))};
document.getElementById('p').onkeydown=e=>{if(e.key==='Enter')document.getElementById('b').click()};
</script></body></html>'''

@app.route('/auth', methods=['POST'])
def do_auth():
    if request.json.get('pin') == PIN:
        session['auth'] = True
        resp = make_response({'ok': True})
        resp.set_cookie('pin', PIN, max_age=86400*30, httponly=True, samesite='Lax')
        return resp
    return {'error': 'bad pin'}, 403

@app.route('/health')
def health(): return 'ok'

@app.route('/')
def index():
    # (same UI as v4.2 - omitted for brevity, use previous full HTML)
    return open(__file__).read().split("'''<!doctype")[1].split("'''")[0].insert(0,"<!doctype") if False else '''<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>IA Drive</title><link href="https://cdn.jsdelivr.net/npm/remixicon@4.2.0/fonts/remixicon.css" rel=stylesheet>
<style>:root{--b:#020617;--s:#0f172a;--m:#1e293b;--t:#334155;--a:#3b82f6;--g:#22c55e;--r:#ef4444;--w:#e2e8f0;--d:#94a3b8}
*{box-sizing:border-box}body{margin:0;background:var(--b);color:var(--w);font-family:system-ui,-apple-system,Segoe UI,Roboto;overflow-x:hidden}
.app{display:grid;grid-template-columns:260px 1fr;min-height:100vh}
.sidebar{background:var(--s);border-right:1px solid var(--m);padding:20px;display:flex;flex-direction:column;position:sticky;top:0;height:100vh;overflow-y:auto}
.logo{display:flex;align-items:center;gap:10px;font-weight:700;font-size:18px;margin-bottom:28px}
.logo i{color:var(--a);font-size:24px}
.menu{display:flex;flex-direction:column;gap:4px}
.menu a{display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:8px;color:var(--d);text-decoration:none;transition:.15s;cursor:pointer}
.menu a:hover{background:var(--m);color:var(--w)}.menu a.active{background:var(--a);color:#fff}
.menu a i{font-size:18px;width:20px}.count{margin-left:auto;font-size:12px;background:var(--t);padding:2px 6px;border-radius:10px}
.main{display:flex;flex-direction:column;min-width:0}
.topbar{height:56px;background:var(--s);border-bottom:1px solid var(--m);display:flex;align-items:center;padding:0 20px;gap:16px;position:sticky;top:0;z-index:10}
.hamburger{display:none;background:0;border:0;color:var(--w);font-size:22px;cursor:pointer}
.search{flex:1;max-width:480px;position:relative}.search input{width:100%;background:var(--b);border:1px solid var(--m);border-radius:8px;padding:8px 12px 8px 36px;color:var(--w)}
.search i{position:absolute;left:12px;top:50%;transform:translateY(-50%);color:var(--d)}
.content{padding:24px;flex:1}
.page-view{display:none}.page-view.active{display:block}
.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px;margin-top:16px}
.card{background:var(--s);border:1px solid var(--m);border-radius:12px;overflow:hidden;transition:.2s;cursor:pointer;text-decoration:none;color:inherit;display:block}
.card:hover{transform:translateY(-2px);border-color:var(--t)}.thumb{aspect-ratio:16/10;background:var(--b);display:grid;place-items:center;overflow:hidden}
.thumb img,.thumb video{width:100%;height:100%;object-fit:cover}.thumb i{font-size:32px;color:var(--d)}
.info{padding:12px}.name{font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.meta{display:flex;justify-content:space-between;margin-top:6px;font-size:11px;color:var(--d)}
.drop{border:2px dashed var(--m);border-radius:12px;padding:48px;text-align:center;background:var(--s);cursor:pointer;transition:.2s}
.drop:hover,.drop.drag{border-color:var(--a);background:rgba(59,130,246,.05)}
.url-box{display:flex;gap:8px;margin-top:16px}.url-box input{flex:1;background:var(--s);border:1px solid var(--m);border-radius:8px;padding:10px 12px;color:var(--w)}
.btn{background:var(--a);color:#fff;border:0;padding:10px 18px;border-radius:8px;font-weight:500;cursor:pointer;transition:.15s}
.btn:hover{opacity:.9}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.8);backdrop-filter:blur(4px);display:none;align-items:center;justify-content:center;z-index:100;padding:20px}
.modal.show{display:flex}.modal-box{background:var(--s);border:1px solid var(--m);border-radius:16px;width:100%;max-width:480px;padding:24px}
.progress{height:6px;background:var(--b);border-radius:3px;overflow:hidden;margin:12px 0}.progress-bar{height:100%;background:var(--a);width:0%;transition:.3s}
.log{max-height:160px;overflow-y:auto;background:var(--b);border-radius:8px;padding:8px;font-family:ui-monospace,monospace;font-size:12px;margin-top:12px}
.log div{padding:2px 0;color:var(--d)}
table{width:100%;border-collapse:collapse;margin-top:16px}th{text-align:left;padding:10px 12px;font-size:12px;color:var(--d);border-bottom:1px solid var(--m);font-weight:500}
td{padding:12px;border-bottom:1px solid rgba(30,41,59,.5);font-size:13px}.badge{display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:12px;font-size:11px;font-weight:500}
.badge.ok{background:rgba(34,197,94,.15);color:var(--g);border:1px solid rgba(34,197,94,.3)}
.badge.err{background:rgba(239,68,68,.15);color:var(--r);border:1px solid rgba(239,68,68,.3)}
.badge.run{background:rgba(59,130,246,.15);color:var(--a);border:1px solid rgba(59,130,246,.3)}
.empty{padding:60px 20px;text-align:center;color:var(--d)}.empty i{font-size:48px;margin-bottom:12px;opacity:.5}
.toast{position:fixed;bottom:24px;right:24px;background:var(--s);border:1px solid var(--m);padding:12px 16px;border-radius:8px;display:none;align-items:center;gap:10px;z-index:200;box-shadow:0 10px 30px rgba(0,0,0,.5)}
.overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:90}
@media(max-width:768px){.app{grid-template-columns:1fr}.sidebar{position:fixed;left:-260px;z-index:100;transition:.3s}.sidebar.open{left:0}.hamburger{display:block}.overlay.show{display:block}.card-grid{grid-template-columns:repeat(auto-fill,minmax(140px,1fr))}}
</style></head><body>
<div class=app>
<aside class=sidebar id=sidebar>
<div class=logo><i class="ri-hard-drive-3-fill"></i><span>IA Drive v4.4</span></div>
<nav class=menu>
<a data-page=upload class=active><i class="ri-upload-cloud-2-line"></i><span>Upload</span></a>
<a data-page=files data-filter=all><i class="ri-folder-2-line"></i><span>All Files</span><span class=count id=c-all>0</span></a>
<a data-page=files data-filter=video><i class="ri-movie-line"></i><span>Videos</span><span class=count id=c-video>0</span></a>
<a data-page=files data-filter=image><i class="ri-image-line"></i><span>Images</span><span class=count id=c-image>0</span></a>
<a data-page=files data-filter=audio><i class="ri-music-2-line"></i><span>Audio</span><span class=count id=c-audio>0</span></a>
<a data-page=files data-filter=doc><i class="ri-file-text-line"></i><span>Documents</span><span class=count id=c-doc>0</span></a>
<a data-page=history><i class="ri-history-line"></i><span>History</span></a>
</nav>
</aside>
<div class=overlay id=overlay onclick="toggleSidebar()"></div>
<main class=main>
<div class=topbar>
<button class=hamburger onclick="toggleSidebar()"><i class="ri-menu-line"></i></button>
<h2 id=page-title style="margin:0;font-size:18px;font-weight:600">Upload</h2>
<div class=search style="margin-left:auto"><i class="ri-search-line"></i><input id=search placeholder="Search files..." oninput="renderFiles()"></div>
</div>
<div class=content>
<div id=view-upload class="page-view active">
<div class=drop id=dropzone><i class="ri-upload-cloud-2-line" style="font-size:48px;color:var(--d);margin-bottom:12px"></i><div style="font-weight:500;margin-bottom:4px">Drop files here or click to browse</div><div style="font-size:13px;color:var(--d)">16x parallel fetch enabled</div><input type=file id=file-input multiple hidden></div>
<div class=url-box><input id=url-input placeholder="Paste direct download URL" onkeydown="if(event.key==='Enter')uploadFromUrl()"><button class=btn onclick="uploadFromUrl()"><i class="ri-download-line"></i> Fast Fetch</button></div>
</div>
<div id=view-files class="page-view"><div class=card-grid id=file-grid></div></div>
<div id=view-history class="page-view">
<div style="display:flex;gap:8px;margin-bottom:12px"><input id=hist-search placeholder="Search history..." style="flex:1;background:var(--s);border:1px solid var(--m);border-radius:8px;padding:8px 12px;color:var(--w)" oninput="renderHistory()"></div>
<table><thead><tr><th>File</th><th>Size</th><th>Source</th><th>Started</th><th>Status</th><th>Speed</th></tr></thead><tbody id=hist-body></tbody></table>
</div>
</div>
</main>
</div>
<div class=modal id=modal><div class=modal-box><h3 id=modal-title style="margin:0 0 4px">Uploading</h3><div id=modal-status style="color:var(--d);font-size:13px;margin-bottom:12px"></div><div class=progress><div class=progress-bar id=progress-bar></div></div><canvas id=speed-chart width=392 height=60 style="width:100%;height:60px;margin:8px 0;display:none"></canvas><div class=log id=modal-log></div></div></div>
<div class=toast id=toast></div>
<script>
let allFiles=[], historyData=[], currentFilter='all', currentPage='upload';
const types={video:['mp4','webm','mov','mkv','avi','m4v'],image:['png','jpg','jpeg','gif','webp','svg','bmp','avif'],audio:['mp3','wav','flac','m4a','ogg','aac'],doc:['pdf','doc','docx','txt','md','xls','xlsx','ppt','pptx','csv','rtf']};
function toggleSidebar(){document.getElementById('sidebar').classList.toggle('open');document.getElementById('overlay').classList.toggle('show')}
function showToast(msg,type='info'){const t=document.getElementById('toast');t.innerHTML=`<i class="ri-${type==='success'?'check':type==='error'?'error-warning':'information'}-line"></i><span>${msg}</span>`;t.style.display='flex';setTimeout(()=>t.style.display='none',3000)}
function switchPage(page,filter){currentPage=page;currentFilter=filter||'all';document.querySelectorAll('.menu a').forEach(a=>a.classList.remove('active'));document.querySelector(`[data-page="${page}"]${filter?`[data-filter="${filter}"]`:''}`)?.classList.add('active');document.querySelectorAll('.page-view').forEach(v=>v.classList.remove('active'));document.getElementById('view-'+page).classList.add('active');document.getElementById('page-title').textContent=page==='upload'?'Upload':page==='files'?(filter?filter.charAt(0).toUpperCase()+filter.slice(1):'Files'):'History';if(page==='files')loadFiles();if(page==='history')loadHistory();if(window.innerWidth<768)toggleSidebar()}
document.querySelectorAll('.menu a').forEach(a=>a.onclick=()=>switchPage(a.dataset.page,a.dataset.filter));
function getExt(n){return n.split('.').pop().toLowerCase()}
function getType(n){const e=getExt(n);for(const[k,v]of Object.entries(types))if(v.includes(e))return k;return'other'}
function fmt(b){if(!b)return'0 B';if(b<1024)return b+' B';if(b<1048576)return(b/1024).toFixed(1)+' KB';if(b<1073741824)return(b/1048576).toFixed(1)+' MB';return(b/1073741824).toFixed(2)+' GB'}
async function loadFiles(){try{const r=await fetch('/api/list');allFiles=await r.json();const c={all:allFiles.length,video:0,image:0,audio:0,doc:0};allFiles.forEach(f=>{const t=getType(f.name);if(c[t]!=null)c[t]++});Object.entries(c).forEach(([k,v])=>document.getElementById('c-'+k).textContent=v);renderFiles()}catch{}}
function renderFiles(){const q=document.getElementById('search').value.toLowerCase();const g=document.getElementById('file-grid');const list=allFiles.filter(f=>(currentFilter==='all'||getType(f.name)===currentFilter)&&f.name.toLowerCase().includes(q));g.innerHTML='';if(!list.length){g.innerHTML='<div class=empty><i class="ri-folder-open-line"></i><div>No files</div></div>';return}list.forEach(f=>{const e=getExt(f.name);const isI=types.image.includes(e);const isV=types.video.includes(e);const thumb=isI?`<img src="${f.url}" loading=lazy>`:isV?`<video src="${f.url}#t=0.5" muted></video>`:`<i class="ri-file-line"></i>`;g.innerHTML+=`<a class=card href="/file/${encodeURIComponent(f.name)}"><div class=thumb>${thumb}</div><div class=info><div class=name title="${f.name}">${f.name}</div><div class=meta><span>${e.toUpperCase()}</span><span>${fmt(f.size)}</span></div></div></a>`})}
async function loadHistory(){try{const r=await fetch('/api/history');historyData=await r.json();renderHistory()}catch{}}
function renderHistory(){const q=(document.getElementById('hist-search')?.value||'').toLowerCase();const body=document.getElementById('hist-body');const list=historyData.filter(h=>(h.filename+h.url).toLowerCase().includes(q));body.innerHTML=list.map(h=>`<tr><td>${h.filename}</td><td>${fmt(h.size)}</td><td>${h.url.slice(0,40)}</td><td>${h.started}</td><td><span class="badge ${h.status==='complete'?'ok':h.status==='error'?'err':'run'}">${h.status}</span></td><td>${h.speed?fmt(h.speed)+'/s':'-'}</td></tr>`).join('')||'<tr><td colspan=6 style="text-align:center;padding:40px;color:var(--d)">No history</td></tr>'}
async function uploadFile(f){const d=new FormData();d.append('file',f);await fetch('/api/upload',{method:'POST',body:d})}
async function handleFiles(list){if(!list.length)return;const m=document.getElementById('modal');m.classList.add('show');document.getElementById('modal-title').textContent='Uploading';let ok=0;for(let i=0;i<list.length;i++){document.getElementById('modal-status').textContent=`${i+1}/${list.length}: ${list[i].name}`;document.getElementById('progress-bar').style.width=Math.round(i/list.length*100)+'%';try{await uploadFile(list[i]);ok++}catch{}}document.getElementById('progress-bar').style.width='100%';setTimeout(()=>{m.classList.remove('show');showToast(`${ok} uploaded`,'success');loadFiles()},800)}
async function uploadFromUrl(){const url=document.getElementById('url-input').value.trim();if(!url)return;const r=await fetch('/api/upload-url',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});const{task_id}=await r.json();const m=document.getElementById('modal');m.classList.add('show');document.getElementById('modal-title').textContent='Fast Fetch (16x)';document.getElementById('speed-chart').style.display='block';const ctx=document.getElementById('speed-chart').getContext('2d');const poll=setInterval(async()=>{const p=await(await fetch(`/api/progress/${task_id}`)).json();document.getElementById('modal-status').innerHTML=`Down: <b>${fmt(p.downloaded)}</b> • Speed: <b>${fmt(p.speed)}/s</b>`;document.getElementById('progress-bar').style.width=(p.total?Math.min(100,p.downloaded/p.total*100):30)+'%';if(p.speedHistory){ctx.clearRect(0,0,392,60);ctx.beginPath();ctx.strokeStyle='#3b82f6';ctx.lineWidth=2;p.speedHistory.slice(-60).forEach((s,i)=>{const x=i*6.5;const y=60-(s/Math.max(...p.speedHistory,1))*50;if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y)});ctx.stroke()}document.getElementById('modal-log').innerHTML=(p.log||[]).map(l=>`<div>${l}</div>`).join('');if(p.status==='complete'||p.status==='error'){clearInterval(poll);setTimeout(()=>{m.classList.remove('show');showToast(p.status==='complete'?'Complete':'Failed',p.status);loadFiles();loadHistory()},1000)}},500)}
const dz=document.getElementById('dropzone'),fi=document.getElementById('file-input');dz.onclick=()=>fi.click();dz.ondragover=e=>{e.preventDefault();dz.classList.add('drag')};dz.ondragleave=()=>dz.classList.remove('drag');dz.ondrop=e=>{e.preventDefault();dz.classList.remove('drag');handleFiles([...e.dataTransfer.files])};fi.onchange=()=>handleFiles([...fi.files]);switchPage('upload');loadFiles();
</script></body></html>'''

@app.route('/api/list')
def api_list(): return jsonify(ia_list())

@app.route('/api/upload', methods=['POST'])
def api_upload():
    f = request.files['file']
    ct = f.content_type or mimetypes.guess_type(f.filename)[0] or 'application/octet-stream'
    # stream directly
    url = ia_upload(f.filename, f.stream, ct)
    return jsonify({'url': url})

@app.route('/api/upload-url', methods=['POST'])
def api_upload_url():
    url = request.json.get('url')
    tid = hashlib.md5(f"{url}{time.time()}".encode()).hexdigest()[:12]
    threading.Thread(target=fetch_url_task, args=(tid, url), daemon=True).start()
    return jsonify({'task_id': tid})

@app.route('/api/progress/<tid>')
def api_progress(tid): return jsonify(tasks.get(tid, {'status': 'notfound'}))

@app.route('/api/history')
def api_history():
    with sqlite3.connect(DB) as c:
        rows = c.execute('SELECT filename,url,size,status,speed,started FROM history ORDER BY id DESC LIMIT 100').fetchall()
    return jsonify([{'filename':r[0],'url':r[1],'size':r[2],'status':r[3],'speed':r[4],'started':r[5]} for r in rows])

@app.route('/file/<path:name>')
def file_page(name):
    f = next((x for x in ia_list() if x['name'] == name), None)
    if not f: return 'Not found', 404
    return f'''<meta http-equiv="refresh" content="0; url={f['url']}">'''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
