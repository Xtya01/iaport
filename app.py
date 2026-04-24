import os, io, time, mimetypes, json, requests
from datetime import datetime
from flask import Flask, request, session, jsonify, Response, send_file
from functools import wraps
import internetarchive as ia

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET', 'dev-secret-change-me')
PIN = os.getenv('LOGIN_PIN', '2580')
BUCKET = os.getenv('IA_BUCKET', 'junk-manage-caution')
IA_ACCESS = os.getenv('IA_ACCESS_KEY')
IA_SECRET = os.getenv('IA_SECRET_KEY')
WORKER_BASE = os.getenv('WORKER_MEDIA_BASE', 'https://your-worker.workers.dev')

VIDEO_EXT = {'mp4','mkv','webm','mov','avi','m4v'}
AUDIO_EXT = {'mp3','wav','flac','m4a','ogg','aac'}
IMAGE_EXT = {'jpg','jpeg','png','gif','webp','bmp','svg'}
DOC_EXT = {'pdf','doc','docx','txt','md','epub','ppt','pptx','xls','xlsx'}

def login_required(f):
    @wraps(f)
    def d(*a, **kw):
        if not session.get('auth'):
            return jsonify({'error':'unauthorized'}), 401
        return f(*a, **kw)
    return d

def get_item():
    item = ia.get_item(BUCKET)
    if not item.exists:
        item.upload(files={'_ia_init.txt': io.BytesIO(b'init')},
                    access_key=IA_ACCESS, secret_key=IA_SECRET,
                    metadata={'title': BUCKET, 'mediatype':'data', 'collection':'opensource'})
    return item

def file_type(name):
    ext = name.rsplit('.',1)[-1].lower() if '.' in name else ''
    if ext in VIDEO_EXT: return 'video'
    if ext in AUDIO_EXT: return 'audio'
    if ext in IMAGE_EXT: return 'image'
    if ext in DOC_EXT: return 'document'
    return 'other'

def is_system_file(name):
    n = name.lower()
    return n.endswith('.xml') or '_thumb.jpg' in n or n.startswith('ia_') or n.startswith('_')

@app.post('/api/login')
def login():
    pin = (request.json or {}).get('pin','')
    if str(pin) == str(PIN):
        session['auth'] = True
        return jsonify({'ok': True})
    return jsonify({'ok': False}), 403

@app.get('/api/list')
@login_required
def list_files():
    ftype = request.args.get('type','all')
    prefix = request.args.get('prefix','').strip('/')
    q = request.args.get('q','').lower()

    item = get_item()
    files = []
    for f in item.files:
        name = f.get('name','')
        if is_system_file(name): continue
        if prefix and not name.startswith(prefix + '/'): continue
        if q and q not in name.lower(): continue

        t = file_type(name)
        if ftype!= 'all':
            mapping = {'videos':'video','audio':'audio','images':'image','documents':'document'}
            if mapping.get(ftype)!= t: continue

        size = int(f.get('size',0))
        mtime = f.get('mtime') or f.get('last-modified','')
        try:
            modified = datetime.utcfromtimestamp(int(mtime)).isoformat()+'Z' if mtime else ''
        except: modified = ''

        files.append({
            'key': name,
            'name': name.split('/')[-1],
            'size': size,
            'modified': modified,
            'type': t,
            'url': f'{WORKER_BASE}/{name}',
            'thumb': f'{WORKER_BASE}/thumb/{name}',
            'direct': f'https://archive.org/download/{BUCKET}/{name}'
        })

    files.sort(key=lambda x: x['modified'], reverse=True)
    return jsonify({'files': files})

@app.post('/api/upload')
@login_required
def upload():
    if 'file' not in request.files:
        return jsonify({'error':'no file'}), 400
    f = request.files['file']
    key = request.form.get('key') or f.filename
    tmp = f'/tmp/{int(time.time())}_{key.replace("/","_")}'
    f.save(tmp)

    item = get_item()
    r = item.upload(tmp, key=key, access_key=IA_ACCESS, secret_key=IA_SECRET,
                    verbose=False, retries=3)
    os.remove(tmp)
    return jsonify({'ok': True, 'key': key})

@app.post('/api/url-upload')
@login_required
def url_upload():
    data = request.json or {}
    url = data.get('url','')
    key = data.get('key') or url.split('/')[-1].split('?')[0][:100]
    if not url: return jsonify({'error':'no url'}),400
    import tempfile
    try:
        with requests.get(url, stream=True, timeout=600) as r:
            r.raise_for_status()
            tmp = tempfile.NamedTemporaryFile(delete=False)
            for chunk in r.iter_content(1024*1024):
                if chunk: tmp.write(chunk)
            tmp.close()
            item = get_item()
            item.upload(tmp.name, key=key, access_key=IA_ACCESS, secret_key=IA_SECRET,
                        verbose=False, retries=2)
            os.unlink(tmp.name)
        return jsonify({'ok': True, 'key': key})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.post('/api/delete')
@login_required
def delete():
    key = (request.json or {}).get('key')
    if not key: return jsonify({'error':'no key'}),400
    ia.delete(BUCKET, files=[key], access_key=IA_ACCESS, secret_key=IA_SECRET, cascade_delete=True)
    return jsonify({'ok': True})

@app.post('/api/bulk')
@login_required
def bulk():
    data = request.json or {}
    if data.get('action')!= 'delete': return jsonify({'error':'unsupported'}),400
    keys = data.get('keys',[])
    if keys:
        ia.delete(BUCKET, files=keys, access_key=IA_ACCESS, secret_key=IA_SECRET, cascade_delete=True)
    return jsonify({'ok': True, 'deleted': len(keys)})

@app.post('/api/share')
@login_required
def share():
    file = (request.json or {}).get('file')
    r = requests.post(f'{WORKER_BASE}/api/share', json={'file':file}, timeout=10)
    return jsonify(r.json()), r.status_code

@app.get('/manifest.json')
def manifest():
    return jsonify({
      "name": "IA Drive",
      "short_name": "IA Drive",
      "display": "standalone",
      "background_color": "#000000",
      "theme_color": "#000000",
      "icons": [{"src":"https://archive.org/images/glogo.png","sizes":"512x512","type":"image/png"}]
    })

@app.get('/sw.js')
def sw():
    js = "self.addEventListener('install',e=>self.skipWaiting());self.addEventListener('fetch',e=>{});"
    return Response(js, mimetype='application/javascript')

@app.get('/')
def index():
    return send_file('file-manager.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
