from flask import Flask, request, jsonify, render_template_string
import os, sqlite3, requests, threading, time, datetime

app = Flask(__name__)
WORKER = os.environ.get('WORKER_UPLOAD', '')
BUCKET = os.environ.get('IA_BUCKET', 'ia-drive-uploads')
DB = '/data/history.db'
os.makedirs('/data', exist_ok=True)

with sqlite3.connect(DB) as c:
    c.execute('CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, filename TEXT, url TEXT, status TEXT, size INTEGER, started TEXT, finished TEXT)')

tasks = {}

HTML = '''<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IA Drive v4.7</title><style>body{font-family:system-ui;background:#0a0e1a;color:#e2e8f0;margin:0;padding:20px}.card{background:#1e293b;padding:20px;border-radius:12px;margin-bottom:20px} input,button{padding:12px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:#fff;width:100%;margin:5px 0} button{background:#3b82f6;cursor:pointer;font-weight:600}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:15px}.file{background:#1e293b;padding:15px;border-radius:10px}.progress{height:6px;background:#334155;border-radius:3px;overflow:hidden;margin:8px 0}.bar{height:100%;background:#3b82f6;width:0%;transition:.3s}.log{font-family:monospace;font-size:12px;color:#94a3b8;height:60px;overflow:auto;background:#0f172a;padding:8px;border-radius:6px}</style></head>
<body><h1>🚀 IA Drive v4.7 — Cloudflare Powered</h1>
<div class="card"><h3>Upload File (via Cloudflare)</h3><input type="file" id="f"><button onclick="up()">Upload</button><div class="progress"><div class="bar" id="pb"></div></div></div>
<div class="card"><h3>Fast Fetch URL</h3><input id="u" placeholder="https://speed.hetzner.de/100MB.bin"><button onclick="fetchUrl()">Fetch via Worker</button></div>
<div class="card"><h3>Active</h3><div id="active"></div></div>
<div class="card"><h3>Files in IA</h3><div class="grid" id="files"></div></div>
<script>
async function up(){const f=document.getElementById('f').files[0];if(!f)return;const fd=new FormData();fd.append('file',f);fd.append('filename',f.name);const id='u'+Date.now();addTask(id,f.name);const r=await fetch('/upload',{method:'POST',body:fd});document.getElementById('pb').style.width='100%';setTimeout(load,2000);}
async function fetchUrl(){const u=document.getElementById('u').value;if(!u)return;const r=await fetch('/fetch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:u})});load();}
function addTask(id,name){document.getElementById('active').innerHTML+=`<div class="file" id="${id}"><b>${name}</b><div class="log">Sending to Cloudflare...</div></div>`;}
async function load(){const a=await fetch('/tasks').then(r=>r.json());document.getElementById('active').innerHTML=Object.entries(a).map(([k,v])=>`<div class="file"><b>${v.filename}</b><div>${v.status}</div><div class="log">${v.log?.join('<br>')||''}</div></div>`).join('');const f=await fetch('/files').then(r=>r.json());document.getElementById('files').innerHTML=f.map(x=>`<div class="file"><b>${x.name}</b><div>${(x.size/1024/1024).toFixed(1)} MB</div><a href="${x.url}" target="_blank" style="color:#60a5fa">Open</a></div>`).join('');}setInterval(load,3000);load();
</script></body></html>'''

def log_task(tid, msg, status=None):
    if tid not in tasks: tasks[tid] = {'filename':'','status':'','log':[]}
    tasks[tid]['log'].append(msg)
    if status: tasks[tid]['status'] = status

def worker_job(tid, mode, data):
    try:
        tasks[tid] = {'filename': data.get('filename','file'), 'status':'uploading', 'log':['Contacting Cloudflare...']}
        with sqlite3.connect(DB) as c:
            c.execute('INSERT INTO history (filename,url,status,started) VALUES (?,?,?,?)', (tasks[tid]['filename'], data.get('url',''), 'running', datetime.datetime.now().strftime('%Y-%m-%d %H:%M')))

        if mode == 'url':
            r = requests.post(WORKER, json={'url':data['url'],'filename':tasks[tid]['filename']}, timeout=3600)
        else:
            files = {'file': (data['filename'], data['content'], data['type'])}
            r = requests.post(WORKER, files=files, data={'filename':data['filename']}, timeout=3600)

        if r.ok:
            log_task(tid, 'Complete via Cloudflare', 'complete')
            with sqlite3.connect(DB) as c:
                c.execute('UPDATE history SET status=?, finished=? WHERE filename=?', ('complete', datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), tasks[tid]['filename']))
        else:
            log_task(tid, f'Error: {r.text[:100]}', 'error')
    except Exception as e:
        log_task(tid, f'Error: {str(e)}', 'error')

@app.route('/')
def home(): return render_template_string(HTML)

@app.route('/upload', methods=['POST'])
def upload():
    f = request.files['file']
    tid = f'up_{int(time.time())}'
    threading.Thread(target=worker_job, args=(tid,'file',{'filename':f.filename,'content':f.read(),'type':f.content_type}), daemon=True).start()
    return jsonify({'id':tid})

@app.route('/fetch', methods=['POST'])
def fetch():
    url = request.json['url']
    filename = url.split('/')[-1].split('?')[0][:100] or 'file.bin'
    tid = f'ft_{int(time.time())}'
    threading.Thread(target=worker_job, args=(tid,'url',{'url':url,'filename':filename}), daemon=True).start()
    return jsonify({'id':tid})

@app.route('/tasks')
def get_tasks(): return jsonify(tasks)

@app.route('/files')
def files():
    try:
        r = requests.get(f'https://archive.org/advancedsearch.php?q=collection:{BUCKET}&fl=identifier,title,format,size&output=json&rows=50', timeout=10).json()
        docs = r.get('response',{}).get('docs',[])
        out = []
        for d in docs:
            out.append({'name':d.get('title',d['identifier']), 'size': int(d.get('size',0)), 'url':f"https://archive.org/details/{d['identifier']}"})
        return jsonify(out)
    except: return jsonify([])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
