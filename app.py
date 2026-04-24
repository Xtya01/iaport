import os, io, time, json, requests, logging
from datetime import datetime
from flask import Flask, request, session, jsonify, Response, send_file, abort, redirect
from functools import wraps
import internetarchive as ia

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET', 'dev-secret-change-me')
PIN = os.getenv('LOGIN_PIN', '2580')
BUCKET = os.getenv('IA_BUCKET', 'junk-manage-caution')
IA_ACCESS = os.getenv('IA_ACCESS_KEY')
IA_SECRET = os.getenv('IA_SECRET_KEY')
WORKER_BASE = os.getenv('WORKER_MEDIA_BASE', 'https://your-worker.workers.dev')

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('ia-drive')

VIDEO_EXT = {'mp4','mkv','webm','mov','avi','m4v','mpg'}
AUDIO_EXT = {'mp3','wav','flac','m4a','ogg','aac','opus'}
IMAGE_EXT = {'jpg','jpeg','png','gif','webp','bmp','svg','ico'}
DOC_EXT = {'pdf','doc','docx','txt','md','epub','ppt','pptx','xls','xlsx','csv'}

@app.before_request
def block_scanners():
    path = request.path
    ip = request.remote_addr

    # Block common exploits
    blocked = ['setup.cgi', 'netgear', 'Mozi.m', '.env', 'wp-login', 'phpmyadmin', 'shell', 'cmd=', 'boaform']
    if any(b in path.lower() for b in blocked):
        logger.warning(f"Blocked exploit probe from {ip}: {path}")
        abort(404)

    # Block AI/scanner endpoints unless authenticated
    scanner_paths = ['/v1/', '/api/tags', '/api/generate', '/api/version', '/api/models',
                     '/.well-known/', '/metrics', '/docs', '/openapi', '/predict', '/embed']
    if any(path.startswith(p) for p in scanner_paths) and path not in ['/health', '/favicon.ico']:
        if not session.get('auth'):
            abort(404)

    # Detect TLS handshake on HTTP port
    if request.method == 'PRI' or (request.content_length and request.content_length > 0):
        try:
            if request.data and len(request.data) > 0 and request.data[0] == 0x16:
                logger.warning(f"TLS probe from {ip}")
                abort(400)
        except:
            pass

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
        logger.info(f"Creating new IA item: {BUCKET}")
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

@app.get('/health')
def health():
    return jsonify({'status':'ok', 'bucket': BUCKET, 'time': datetime.utcnow().isoformat()}), 200

@app.get('/favicon.ico')
def favicon():
    return redirect('https://archive.org/images/glogo.png', code=301)

@app.post('/api/login')
def login():
    pin = (request.json or {}).get('pin','')
    if str(pin) == str(PIN):
        session['auth'] = True
        session.permanent = True
        logger.info(f"Login success from {request.remote_addr}")
        return jsonify({'ok': True})
    logger.warning(f"Login failed from {request.remote_addr}")
    return jsonify({'ok': False}), 403

@app.get('/api/list')
@login_required
def list_files():
    try:
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
    except Exception as e:
        logger.error(f"List error: {e}", exc_info=True)
        return jsonify({'error':'list failed', 'files':[]}), 500

@app.post('/api/upload')
@login_required
def upload():
    if 'file' not in request.files:
        return jsonify({'error':'no file'}), 400

    f = request.files['file']
    key = request.form.get('key') or f.filename
    key = key.replace('..','').lstrip('/')

    if not IA_ACCESS or not IA_SECRET:
        return jsonify({'error':'IA credentials not configured'}), 500

    tmp = f'/tmp/{int(time.time())}_{os.path.basename(key)}'
    try:
        f.save(tmp)
        item = get_item()
        item.upload(tmp, key=key, access_key=IA_ACCESS, secret_key=IA_SECRET,
                    verbose=False, retries=3,
                    metadata={'x-archive-keep-old-version':'0'})
        logger.info(f"Upload success: {key} ({os.path.getsize(tmp)} bytes)")
        return jsonify({'ok': True, 'key': key})
    except Exception as e:
        logger.error(f"Upload failed {key}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

@app.post('/api/url-upload')
@login_required
def url_upload():
    data = request.json or {}
    url = data.get('url','').strip()
    key = data.get('key') or url.split('/')[-1].split('?')[0][:100]
    key = key.replace('..','').lstrip('/')

    if not url or not url.startswith(('http://','https://')):
        return jsonify({'error':'invalid url'}), 400

    if not IA_ACCESS or not IA_SECRET:
        logger.error("URL upload attempted without IA credentials")
        return jsonify({'error':'IA credentials not configured - set IA_ACCESS_KEY and IA_SECRET_KEY'}), 500

    try:
        import tempfile
        logger.info(f"URL upload start: {url} -> {key}")

        with requests.get(url, stream=True, timeout=600,
                         headers={'User-Agent':'IA-Drive/1.0'},
                         allow_redirects=True) as r:
            r.raise_for_status()

            total = int(r.headers.get('content-length', 0))
            if total > 100 * 1024**3:
                return jsonify({'error':'file too large (>100GB)'}), 413

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.download')
            try:
                downloaded = 0
                for chunk in r.iter_content(1024*1024):
                    if chunk:
                        tmp.write(chunk)
                        downloaded += len(chunk)
                tmp.close()

                logger.info(f"Downloaded {downloaded} bytes, uploading to IA...")
                item = get_item()
                item.upload(tmp.name, key=key, access_key=IA_ACCESS,
                           secret_key=IA_SECRET, verbose=False, retries=2)

                logger.info(f"URL upload success: {key}")
                return jsonify({'ok': True, 'key': key, 'size': downloaded})
            finally:
                if os.path.exists(tmp.name):
                    os.unlink(tmp.name)

    except requests.exceptions.RequestException as e:
        logger.error(f"URL fetch failed: {e}")
        return jsonify({'error': f'download failed: {str(e)}'}), 502
    except Exception as e:
        logger.error(f"URL upload error: {e}", exc_info=True)
        return jsonify({'error': f'upload failed: {str(e)}'}), 500

@app.post('/api/delete')
@login_required
def delete():
    key = (request.json or {}).get('key')
    if not key: return jsonify({'error':'no key'}),400
    try:
        ia.delete(BUCKET, files=[key], access_key=IA_ACCESS, secret_key=IA_SECRET, cascade_delete=True)
        logger.info(f"Deleted: {key}")
        return jsonify({'ok': True})
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        return jsonify({'error': str(e)}), 500

@app.post('/api/bulk')
@login_required
def bulk():
    data = request.json or {}
    if data.get('action')!= 'delete':
        return jsonify({'error':'unsupported'}),400
    keys = data.get('keys',[])
    try:
        if keys:
            ia.delete(BUCKET, files=keys, access_key=IA_ACCESS, secret_key=IA_SECRET, cascade_delete=True)
        logger.info(f"Bulk deleted {len(keys)} files")
        return jsonify({'ok': True, 'deleted': len(keys)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.post('/api/share')
@login_required
def share():
    file = (request.json or {}).get('file')
    try:
        r = requests.post(f'{WORKER_BASE}/api/share', json={'file':file}, timeout=10)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 502

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
    # Try to serve file-manager.html, fallback to error page
    html_path = 'file-manager.html'
    if os.path.exists(html_path):
        return send_file(html_path)
    else:
        logger.warning("file-manager.html not found, serving fallback")
        return """<!DOCTYPE html><html><head><title>IA Drive</title>
        <style>body{background:#000;color:#fff;font-family:system-ui;padding:40px;text-align:center}
        h1{font-size:48px;margin:40px 0}code{background:#111;padding:4px 8px;border-radius:4px}</style>
        </head><body><h1>📁 IA Drive</h1>
        <p>Backend is running, but <code>file-manager.html</code> is missing.</p>
        <p>Copy the HTML file to <code>/app/file-manager.html</code> and refresh.</p>
        <p>API is available at <code>/api/list</code></p></body></html>""", 200

@app.errorhandler(404)
def not_found(e):
    # Don't log scanner 404s
    if not any(x in request.path for x in ['.env','wp-','setup','php']):
        logger.info(f"404: {request.path}")
    return jsonify({'error':'not found'}), 404

@app.errorhandler(500)
def server_error(e):
    logger.error(f"500 error: {e}", exc_info=True)
    return jsonify({'error':'internal error'}), 500

if __name__ == '__main__':
    logger.info(f"Starting IA Drive on port 8080, bucket={BUCKET}")
    if not IA_ACCESS or not IA_SECRET:
        logger.warning("WARNING: IA_ACCESS_KEY and IA_SECRET_KEY not set - uploads will fail!")
    app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)
