import os, io, time, logging
from flask import Flask, request, session, jsonify, send_file
from functools import wraps
import requests
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

try:
    import internetarchive as ia
except ImportError:
    ia = None

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET', 'dev-secret-change-me-please')
PIN = str(os.getenv('LOGIN_PIN', '2580'))
BUCKET = os.getenv('IA_BUCKET', 'junk-manage-caution')
IA_ACCESS = os.getenv('IA_ACCESS_KEY')
IA_SECRET = os.getenv('IA_SECRET_KEY')
WORKER_BASE = os.getenv('WORKER_MEDIA_BASE', '').rstrip('/')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('ia-drive')

# S3 client
s3 = None
if IA_ACCESS and IA_SECRET:
    try:
        s3 = boto3.client('s3',
            endpoint_url='https://s3.us.archive.org',
            aws_access_key_id=IA_ACCESS,
            aws_secret_access_key=IA_SECRET,
            config=Config(signature_version='s3v4', s3={'addressing_style':'path'}),
            region_name='us-east-1'
        )
        log.info("S3 client initialized")
    except Exception as e:
        log.error(f"S3 init failed: {e}")

VIDEO = {'mp4','mkv','webm','mov','avi','m4v','mpg','flv'}
AUDIO = {'mp3','wav','flac','m4a','ogg','aac','opus','wma'}
IMAGE = {'jpg','jpeg','png','gif','webp','bmp','svg','ico'}
DOC = {'pdf','doc','docx','txt','md','epub','ppt','pptx','xls','xlsx','csv','rtf'}

def login_required(f):
    @wraps(f)
    def d(*a, **kw):
        if not session.get('auth'):
            return jsonify({'error':'unauthorized'}), 401
        return f(*a, **kw)
    return d

def file_type(name):
    ext = name.rsplit('.',1)[-1].lower() if '.' in name else ''
    if ext in VIDEO: return 'video'
    if ext in AUDIO: return 'audio'
    if ext in IMAGE: return 'image'
    if ext in DOC: return 'document'
    return 'other'

def is_system(name):
    n = name.lower()
    return (n.endswith('.xml') or '_thumb' in n or n.startswith('ia_') 
            or n.startswith('_') or n.endswith('.sqlite'))

@app.post('/api/login')
def login():
    try:
        pin = str((request.get_json() or {}).get('pin', ''))
        if pin == PIN:
            session['auth'] = True
            session.permanent = True
            return jsonify({'ok': True})
        return jsonify({'ok': False, 'error': 'Invalid PIN'}), 403
    except Exception as e:
        log.error(f"Login error: {e}")
        return jsonify({'error': str(e)}), 500

@app.get('/api/list')
@login_required
def list_files():
    try:
        if not s3 or not IA_ACCESS:
            return jsonify({'files': [], 'warning': 'IA not configured'})
        
        files = []
        try:
            # List via S3 (faster than internetarchive)
            paginator = s3.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=BUCKET):
                for obj in page.get('Contents', []):
                    name = obj['Key']
                    if is_system(name):
                        continue
                    size = obj['Size']
                    files.append({
                        'key': name,
                        'name': name.split('/')[-1],
                        'size': size,
                        'type': file_type(name),
                        'url': f"{WORKER_BASE}/{name}" if WORKER_BASE else f"https://archive.org/download/{BUCKET}/{name}",
                        'direct': f"https://archive.org/download/{BUCKET}/{name}"
                    })
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchBucket':
                log.warning(f"Bucket {BUCKET} does not exist, will be created on first upload")
                return jsonify({'files': []})
            raise
        
        return jsonify({'files': files})
    except Exception as e:
        log.error(f"List error: {e}", exc_info=True)
        return jsonify({'files': [], 'error': str(e)}), 200  # Return 200 with empty to avoid frontend crash

@app.post('/api/upload')
@login_required
def upload():
    try:
        if not s3:
            return jsonify({'error': 'S3 not configured'}), 500
        
        f = request.files.get('file')
        if not f:
            return jsonify({'error': 'No file'}), 400
        
        key = (request.form.get('key') or f.filename).replace('..', '').lstrip('/')
        log.info(f"Uploading {key} ({f.content_length} bytes)")
        
        # Stream directly to S3
        s3.upload_fileobj(f, BUCKET, key, ExtraArgs={'ACL': 'private'})
        return jsonify({'ok': True, 'key': key})
    except Exception as e:
        log.error(f"Upload error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.post('/api/multipart/init')
@login_required
def mp_init():
    try:
        if not s3:
            return jsonify({'error': 'S3 not configured'}), 500
        key = request.get_json().get('key')
        resp = s3.create_multipart_upload(Bucket=BUCKET, Key=key)
        log.info(f"Multipart init: {key} -> {resp['UploadId']}")
        return jsonify({'uploadId': resp['UploadId']})
    except Exception as e:
        log.error(f"MP init error: {e}")
        return jsonify({'error': str(e)}), 500

@app.post('/api/multipart/part')
@login_required
def mp_part():
    try:
        d = request.get_json()
        url = s3.generate_presigned_url(
            'upload_part',
            Params={'Bucket': BUCKET, 'Key': d['key'], 'UploadId': d['uploadId'], 'PartNumber': int(d['part'])},
            ExpiresIn=3600
        )
        return jsonify({'url': url})
    except Exception as e:
        log.error(f"MP part error: {e}")
        return jsonify({'error': str(e)}), 500

@app.post('/api/multipart/complete')
@login_required
def mp_complete():
    try:
        d = request.get_json()
        s3.complete_multipart_upload(
            Bucket=BUCKET,
            Key=d['key'],
            UploadId=d['uploadId'],
            MultipartUpload={'Parts': sorted(d['parts'], key=lambda x: x['PartNumber'])}
        )
        log.info(f"Multipart complete: {d['key']}")
        return jsonify({'ok': True})
    except Exception as e:
        log.error(f"MP complete error: {e}")
        return jsonify({'error': str(e)}), 500

@app.post('/api/url-upload')
@login_required
def url_upload():
    try:
        if not s3:
            return jsonify({'error': 'S3 not configured'}), 500
        
        data = request.get_json() or {}
        url = data.get('url')
        key = data.get('key') or url.split('/')[-1].split('?')[0][:100]
        
        log.info(f"URL upload: {url} -> {key}")
        
        with requests.get(url, stream=True, timeout=3600) as r:
            r.raise_for_status()
            # Use multipart for streaming
            mp = s3.create_multipart_upload(Bucket=BUCKET, Key=key)
            parts = []
            part_num = 1
            buffer = b''
            
            for chunk in r.iter_content(chunk_size=50*1024*1024):
                if not chunk:
                    continue
                buffer += chunk
                if len(buffer) >= 100*1024*1024:
                    resp = s3.upload_part(Bucket=BUCKET, Key=key, UploadId=mp['UploadId'],
                                        PartNumber=part_num, Body=buffer)
                    parts.append({'ETag': resp['ETag'], 'PartNumber': part_num})
                    part_num += 1
                    buffer = b''
                    log.info(f"URL upload part {part_num-1} done")
            
            if buffer:
                resp = s3.upload_part(Bucket=BUCKET, Key=key, UploadId=mp['UploadId'],
                                    PartNumber=part_num, Body=buffer)
                parts.append({'ETag': resp['ETag'], 'PartNumber': part_num})
            
            s3.complete_multipart_upload(
                Bucket=BUCKET, Key=key, UploadId=mp['UploadId'],
                MultipartUpload={'Parts': parts}
            )
        
        return jsonify({'ok': True})
    except Exception as e:
        log.error(f"URL upload error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.get('/health')
def health():
    return jsonify({'status': 'ok', 's3': bool(s3), 'bucket': BUCKET})

@app.get('/')
def index():
    return send_file('file-manager.html')

if __name__ == '__main__':
    log.info(f"Starting IA Drive - Bucket: {BUCKET}, Worker: {WORKER_BASE or 'none'}")
    app.run(host='0.0.0.0', port=8080, debug=False)
