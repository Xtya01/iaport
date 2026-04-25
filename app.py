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
app.secret_key = "ia-final"

def ia_list():
    try:
        r = requests.get(f"https://archive.org/metadata/{IA_BUCKET}", timeout=20)
        files = []
        for f in r.json().get("files", []):
            n = f.get("name", "")
            if n and not n.startswith("_") and "/" not in n:
                url = f"{WORKER}/{IA_BUCKET}/{quote(n)}" if WORKER else f"https://archive.org/download/{IA_BUCKET}/{quote(n)}"
                files.append({"name": n, "size": int(f.get("size", 0)), "url": url})
        return sorted(files, key=lambda x: x["name"].lower())
    except Exception as e:
        print("LIST ERROR:", e)
        return []

def ia_put(key, data, ctype):
    headers = {
        "authorization": AUTH,
        "x-amz-auto-make-bucket": "1",
        "x-archive-auto-make-bucket": "1",
        "Content-Type": ctype or "application/octet-stream"
    }
    requests.put(f"{ENDPOINT}/{IA_BUCKET}/{key}", data=data, headers=headers, timeout=900)

@app.before_request
def auth():
    if request.path.startswith(("/login", "/health", "/api", "/file")):
        if request.path.startswith("/api") and not session.get("ok"):
            return jsonify({"error": "unauthorized"}), 401
        return
    if not session.get("ok"):
        return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST" and request.form.get("pin") == LOGIN_PIN:
        session["ok"] = True
        return redirect("/")
    return """<html><body style="background:#000;color:#fff;font-family:sans-serif;display:grid;place-items:center;height:100vh;margin:0"><form method=post style="background:#111;padding:30px;border-radius:12px;width:280px"><h2>IA Drive</h2><input name=pin type=password placeholder=PIN style="width:100%;padding:10px;margin:10px 0;background:#000;color:#fff;border:1px solid #333"><button style="width:100%;padding:10px;background:#2563eb;border:0;color:#fff">Login</button></form></body></html>"""

@app.route("/")
def index():
    return """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IA Drive</title>
<link href="https://cdnjs.cloudflare.com/ajax/libs/remixicon/4.2.0/remixicon.min.css" rel="stylesheet">
<style>
*{box-sizing:border-box}body{margin:0;background:#020617;color:#e2e8f0;font-family:system-ui,-apple-system,sans-serif}
.layout{display:flex;min-height:100vh}
.sidebar{width:240px;background:#0f172a;border-right:1px solid #1e293b;padding:16px;position:fixed;top:0;left:0;bottom:0;overflow-y:auto}
.logo{font-weight:700;margin-bottom:20px;display:flex;align-items:center;gap:8px}
.logo i{color:#3b82f6}
.menu a{display:flex;align-items:center;gap:10px;padding:10px 12px;margin:3px 0;border-radius:8px;color:#cbd5e1;text-decoration:none;cursor:pointer;font-size:14px}
.menu a.active,.menu a:hover{background:#1e293b;color:#fff}
.menu a span{margin-left:auto;font-size:12px;opacity:.7}
.content{margin-left:240px;flex:1;min-width:0}
.header{padding:14px 20px;border-bottom:1px solid #1e293b;background:rgba(2,6,23,.8);backdrop-filter:blur(8px);position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:12px}
.burger{display:none;background:none;border:none;color:#fff;font-size:22px;cursor:pointer}
.page{padding:20px}
#page-upload{display:block}
#page-files{display:none}
.upload-box{max-width:700px;margin:60px auto;background:#0f172a;border:1px solid #1e293b;border-radius:16px;padding:40px;text-align:center}
.drop{border:2px dashed #334155;border-radius:12px;padding:50px 20px;margin:24px 0;cursor:pointer;transition:.2s}
.drop:hover{border-color:#3b82f6;background:#1e293b40}
.drop i{font-size:48px;color:#3b82f6;margin-bottom:12px}
.url-input{display:flex;gap:8px;max-width:500px;margin:0 auto}
.url-input input{flex:1;padding:12px;background:#000;border:1px solid #334155;border-radius:8px;color:#fff}
.url-input button{padding:12px 20px;background:#3b82f6;border:none;border-radius:8px;color:#fff;font-weight:600;cursor:pointer}
.toolbar{display:flex;gap:10px;margin-bottom:16px;align-items:center}
.toolbar input{flex:1;max-width:400px;padding:10px 12px;background:#0f172a;border:1px solid #1e293b;border-radius:8px;color:#fff}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:14px}
.card{background:#0f172a;border:1px solid #1e293b;border-radius:10px;overflow:hidden;text-decoration:none;color:inherit;transition:.15s;display:block}
.card:hover{transform:translateY(-2px);border-color:#334155}
.thumb{height:110px;background:#000;display:flex;align-items:center;justify-content:center;overflow:hidden}
.thumb img,.thumb video{width:100%;height:100%;object-fit:cover}
.thumb i{font-size:32px;opacity:.5}
.info{padding:8px 10px}
.name{font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.meta{font-size:11px;color:#64748b;display:flex;justify-content:space-between;margin-top:3px}
.empty{text-align:center;padding:60px;color:#64748b;grid-column:1/-1}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.8);display:none;align-items:center;justify-content:center;z-index:100}
.modal.show{display:flex}
.modal-content{background:#0f172a;border:1px solid #1e293b;border-radius:12px;padding:24px;width:90%;max-width:400px}
.progress{height:4px;background:#000;border-radius:2px;overflow:hidden;margin:12px 0}
.progress-bar{height:100%;background:#3b82f6;width:0%;transition:width.3s}
.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#0f172a;border:1px solid #1e293b;padding:10px 16px;border-radius:8px;display:none;z-index:200}
@media(max-width:768px){.sidebar{transform:translateX(-100%);transition:.3s;z-index:50}.sidebar.open{transform:translateX(0)}.content{margin-left:0}.burger{display:block}.grid{grid-template-columns:repeat(auto-fill,minmax(140px,1fr))}}
</style>
</head>
<body>
<div class="layout">
  <aside class="sidebar" id="sidebar">
    <div class="logo"><i class="ri-hard-drive-3-fill"></i> IA Drive</div>
    <nav class="menu">
      <a class="active" data-page="upload"><i class="ri-upload-2-line"></i> Upload</a>
      <a data-page="files" data-filter="all"><i class="ri-folder-line"></i> All Files <span id="count-all">0</span></a>
      <a data-page="files" data-filter="video"><i class="ri-film-line"></i> Videos <span id="count-video">0</span></a>
      <a data-page="files" data-filter="image"><i class="ri-image-line"></i> Images <span id="count-image">0</span></a>
      <a data-page="files" data-filter="audio"><i class="ri-music-2-line"></i> Audio <span id="count-audio">0</span></a>
      <a data-page="files" data-filter="doc"><i class="ri-file-text-line"></i> Docs <span id="count-doc">0</span></a>
    </nav>
  </aside>

  <main class="content">
    <header class="header">
      <button class="burger" onclick="toggleSidebar()"><i class="ri-menu-line"></i></button>
      <h1 id="page-title" style="margin:0;font-size:18px;font-weight:600">Upload</h1>
    </header>

    <div class="page">
      <!-- UPLOAD PAGE -->
      <div id="page-upload">
        <div class="upload-box">
          <h2 style="margin:0 0 8px">Upload Files</h2>
          <p style="margin:0 0 24px;color:#64748b;font-size:14px">Stored permanently on Internet Archive</p>

          <div class="drop" id="dropzone">
            <i class="ri-upload-cloud-2-fill"></i>
            <div style="font-weight:500">Drop files here or click to browse</div>
            <div style="font-size:13px;color:#64748b;margin-top:4px">Supports all file types</div>
          </div>

          <div class="url-input">
            <input type="text" id="url-input" placeholder="Paste direct download URL...">
            <button onclick="uploadFromUrl()">Fetch</button>
          </div>
          <input type="file" id="file-input" multiple hidden>
        </div>
      </div>

      <!-- FILES PAGE -->
      <div id="page-files">
        <div class="toolbar">
          <input type="text" id="search" placeholder="Search files..." oninput="renderFiles()">
          <button onclick="loadFiles()" style="padding:10px 14px;background:#0f172a;border:1px solid #1e293b;border-radius:8px;color:#cbd5e1;cursor:pointer"><i class="ri-refresh-line"></i></button>
        </div>
        <div class="grid" id="file-grid">
          <div class="empty">Loading files...</div>
        </div>
      </div>
    </div>
  </main>
</div>

<!-- Modal -->
<div class="modal" id="modal">
  <div class="modal-content">
    <h3 id="modal-title" style="margin:0 0 8px">Uploading</h3>
    <div id="modal-status" style="font-size:13px;color:#94a3b8">Preparing...</div>
    <div class="progress"><div class="progress-bar" id="progress-bar"></div></div>
    <div id="modal-list" style="font-size:12px;color:#64748b;max-height:150px;overflow:auto;margin-top:10px"></div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
let allFiles = [];
let currentFilter = 'all';
const fileTypes = {
  video: ['mp4','webm','mov','mkv','avi','m4v'],
  image: ['png','jpg','jpeg','gif','webp','svg','bmp','avif'],
  audio: ['mp3','wav','flac','m4a','ogg','aac'],
  doc: ['pdf','doc','docx','txt','md','xls','xlsx','ppt','pptx','rtf','csv']
};

function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.display = 'block';
  setTimeout(() => t.style.display = 'none', 2500);
}

function switchPage(page, filter) {
  document.querySelectorAll('.menu a').forEach(a => a.classList.remove('active'));
  const link = document.querySelector(`[data-page="${page}"]${filter? `[data-filter="${filter}"]` : ''}`);
  if (link) link.classList.add('active');

  document.getElementById('page-upload').style.display = page === 'upload'? 'block' : 'none';
  document.getElementById('page-files').style.display = page === 'files'? 'block' : 'none';
  document.getElementById('page-title').textContent = page === 'upload'? 'Upload' : (filter? filter.charAt(0).toUpperCase() + filter.slice(1) : 'Files');

  if (page === 'files') {
    currentFilter = filter || 'all';
    loadFiles();
  }

  if (window.innerWidth < 768) toggleSidebar();
}

document.querySelectorAll('.menu a').forEach(a => {
  a.onclick = () => switchPage(a.dataset.page, a.dataset.filter);
});

function getExt(name) {
  return name.split('.').pop().toLowerCase();
}

function getType(name) {
  const ext = getExt(name);
  for (const [type, exts] of Object.entries(fileTypes)) {
    if (exts.includes(ext)) return type;
  }
  return 'other';
}

function formatSize(bytes) {
  if (bytes > 1e9) return (bytes/1e9).toFixed(1) + ' GB';
  if (bytes > 1e6) return (bytes/1e6).toFixed(1) + ' MB';
  if (bytes > 1e3) return Math.round(bytes/1024) + ' KB';
  return bytes + ' B';
}

async function loadFiles() {
  try {
    console.log('Loading files...');
    const res = await fetch('/api/list');
    allFiles = await res.json();
    console.log('Loaded', allFiles.length, 'files');

    // Update counts
    const counts = {all: allFiles.length, video:0, image:0, audio:0, doc:0};
    allFiles.forEach(f => {
      const t = getType(f.name);
      if (counts[t]!== undefined) counts[t]++;
    });
    Object.entries(counts).forEach(([k,v]) => {
      const el = document.getElementById('count-'+k);
      if (el) el.textContent = v;
    });

    renderFiles();
  } catch (e) {
    console.error('Load error:', e);
    showToast('Failed to load files');
  }
}

function renderFiles() {
  const grid = document.getElementById('file-grid');
  const query = document.getElementById('search').value.toLowerCase();

  const filtered = allFiles.filter(f => {
    const matchesFilter = currentFilter === 'all' || getType(f.name) === currentFilter;
    const matchesSearch = f.name.toLowerCase().includes(query);
    return matchesFilter && matchesSearch;
  });

  console.log('Rendering', filtered.length, 'files (filter:', currentFilter, ')');

  if (filtered.length === 0) {
    grid.innerHTML = '<div class="empty">No files found</div>';
    return;
  }

  grid.innerHTML = '';
  filtered.forEach(file => {
    const ext = getExt(file.name);
    const isImage = fileTypes.image.includes(ext);
    const isVideo = fileTypes.video.includes(ext);

    const card = document.createElement('a');
    card.className = 'card';
    card.href = '/file/' + encodeURIComponent(file.name);

    let thumb = '<i class="ri-file-line"></i>';
    if (isImage) thumb = `<img src="${file.url}" loading="lazy" alt="">`;
    else if (isVideo) thumb = `<video src="${file.url}#t=0.5" muted preload="metadata"></video>`;

    card.innerHTML = `
      <div class="thumb">${thumb}</div>
      <div class="info">
        <div class="name" title="${file.name}">${file.name}</div>
        <div class="meta">
          <span>${ext.toUpperCase()}</span>
          <span>${formatSize(file.size)}</span>
        </div>
      </div>
    `;
    grid.appendChild(card);
  });
}

async function uploadFile(file) {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/api/upload', {method: 'POST', body: fd});
  if (!res.ok) throw new Error('Upload failed');
}

async function handleFiles(fileList) {
  if (!fileList.length) return;

  const modal = document.getElementById('modal');
  const status = document.getElementById('modal-status');
  const bar = document.getElementById('progress-bar');
  const list = document.getElementById('modal-list');

  modal.classList.add('show');
  list.innerHTML = '';
  let success = 0;

  for (let i = 0; i < fileList.length; i++) {
    const file = fileList[i];
    status.textContent = `Uploading ${i+1} of ${fileList.length}: ${file.name}`;
    bar.style.width = ((i / fileList.length) * 100) + '%';
    list.innerHTML += `<div>• ${file.name}</div>`;

    try {
      await uploadFile(file);
      success++;
      list.lastChild.innerHTML += ' <span style="color:#22c55e">✓</span>';
    } catch (e) {
      list.lastChild.innerHTML += ' <span style="color:#ef4444">✗</span>';
    }
  }

  bar.style.width = '100%';
  status.textContent = `Complete: ${success}/${fileList.length} uploaded`;

  setTimeout(() => {
    modal.classList.remove('show');
    showToast(`${success} file${success!==1?'s':''} uploaded`);
    loadFiles();
  }, 1200);
}

async function uploadFromUrl() {
  const url = document.getElementById('url-input').value.trim();
  if (!url) return showToast('Enter a URL');
  if (!confirm('Fetch file from URL?')) return;

  const modal = document.getElementById('modal');
  modal.classList.add('show');
  document.getElementById('modal-title').textContent = 'Fetching URL';
  document.getElementById('modal-status').textContent = url.substring(0, 50);

  try {
    const res = await fetch('/api/upload-url', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url})
    });
    modal.classList.remove('show');
    if (res.ok) {
      showToast('URL fetched successfully');
      document.getElementById('url-input').value = '';
      loadFiles();
    } else {
      showToast('Failed to fetch URL');
    }
  } catch (e) {
    modal.classList.remove('show');
    showToast('Error fetching URL');
  }
}

// Setup drag and drop
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('file-input');

dropzone.onclick = () => fileInput.click();
dropzone.ondragover = e => { e.preventDefault(); dropzone.style.borderColor = '#3b82f6'; };
dropzone.ondragleave = () => dropzone.style.borderColor = '';
dropzone.ondrop = e => { e.preventDefault(); dropzone.style.borderColor = ''; handleFiles([...e.dataTransfer.files]); };
fileInput.onchange = () => handleFiles([...fileInput.files]);

// Initial load
switchPage('upload');
loadFiles();
</script>
</body>
</html>"""

@app.route("/file/<path:name>")
def view_file(name):
    f = next((x for x in ia_list() if x["name"] == name), None)
    if not f:
        return "File not found", 404
    url = f["url"]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""

    if ext in ("mp4", "webm", "mov", "mkv", "avi"):
        player = f'<video controls style="width:100%;max-height:85vh;background:#000" src="{url}"></video>'
    elif ext in ("mp3", "wav", "flac", "m4a", "ogg"):
        player = f'<audio controls style="width:100%;max-width:600px" src="{url}"></audio><div style="padding:40px"></div>'
    elif ext in ("png", "jpg", "jpeg", "gif", "webp", "svg", "avif"):
        player = f'<img src="{url}" style="max-width:100%;max-height:85vh;display:block;margin:0 auto">'
    elif ext == "pdf":
        player = f'<iframe src="https://mozilla.github.io/pdf.js/web/viewer.html?file={quote(url)}" style="width:100%;height:85vh;border:none"></iframe>'
    else:
        player = f'<div style="text-align:center;padding:80px"><p style="color:#64748b;margin-bottom:20px">Preview not available</p><a href="{url}" download style="display:inline-block;padding:12px 24px;background:#3b82f6;color:#fff;text-decoration:none;border-radius:8px">Download File</a></div>'

    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{name}</title></head>
<body style="margin:0;background:#020617;color:#e2e8f0;font-family:system-ui">
<div style="padding:12px 16px;border-bottom:1px solid #1e293b;display:flex;align-items:center;gap:12px;position:sticky;top:0;background:#020617">
<a href="/" style="color:#94a3b8;text-decoration:none">← Back</a>
<div style="flex:1;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{name}</div>
<a href="{url}" download style="padding:8px 14px;background:#1e293b;color:#fff;text-decoration:none;border-radius:6px;font-size:14px">Download</a>
</div>
<div style="max-width:1400px;margin:20px auto;padding:0 16px">{player}</div>
</body></html>"""

@app.route("/api/list")
def api_list():
    return jsonify(ia_list())

@app.route("/api/upload", methods=["POST"])
def api_upload():
    try:
        f = request.files["file"]
        ia_put(secure_filename(f.filename), f.stream, f.content_type)
        return "", 200
    except Exception as e:
        print("Upload error:", e)
        return "", 500

@app.route("/api/upload-url", methods=["POST"])
def api_upload_url():
    try:
        url = request.get_json().get("url", "")
        r = requests.get(url, stream=True, timeout=120)
        r.raise_for_status()
        filename = secure_filename(urlparse(url).path.split("/")[-1] or f"file-{int(time.time())}")
        ia_put(filename, r.raw, r.headers.get("Content-Type"))
        return "", 200
    except Exception as e:
        print("URL upload error:", e)
        return "", 500

@app.route("/health")
def health():
    return "ok"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
