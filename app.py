import os, io, time, json, requests, logging
from datetime import datetime
from flask import Flask, request, session, jsonify, Response, send_file, abort
from functools import wraps
import internetarchive as ia
import boto3
from botocore.client import Config

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET', 'dev-secret-change-me')
PIN = os.getenv('LOGIN_PIN', '2580')
BUCKET = os.getenv('IA_BUCKET', 'junk-manage-caution')
IA_ACCESS = os.getenv('IA_ACCESS_KEY')
IA_SECRET = os.getenv('IA_SECRET_KEY')
WORKER_BASE = os.getenv('WORKER_MEDIA_BASE', 'https://your-worker.workers.dev')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ia-drive')

s3 = boto3.client('s3',
    endpoint_url='https://s3.us.archive.org',
    aws_access_key_id=IA_ACCESS,
    aws_secret_access_key=IA_SECRET,
    config=Config(signature_version='s3v4')
)

VIDEO_EXT = {'mp4','mkv','webm','mov','avi','m4v'}
AUDIO_EXT = {'mp3','wav','flac','m4a','ogg'}
IMAGE_EXT = {'jpg','jpeg','png','gif','webp'}
DOC_EXT = {'pdf','doc','docx','txt','md'}

def login_required(f):
    @wraps(f)
    def d(*a, **kw):
        if not session.get('auth'):
            return jsonify({'error':'unauthorized'}), 401
        return f(*a, **kw)
    return d

def get_item():
    try:
        item = ia.get_item(BUCKET)
        if not item.exists:
            item.upload(files={'_init.txt': io.BytesIO(b'init')},
                       access_key=IA_ACCESS, secret_key=IA_SECRET,
                       metadata={'title':BUCKET,'mediatype':'data','collection':'opensource'})
        return item
    except Exception as e:
        logger.error(f"IA error: {e}")
        raise

def file_type(n):
    e = n.rsplit('.',1)[-1].lower() if '.' in n else ''
    if e in VIDEO_EXT: return 'video'
    if e in AUDIO_EXT: return 'audio'
    if e in IMAGE_EXT: return 'image'
    if e in DOC_EXT: return 'document'
    return 'other'

def is_sys(n):
    n=n.lower()
    return n.endswith('.xml') or '_thumb' in n or n.startswith('ia_') or n.startswith('_')

@app.post('/api/login')
def login():
    if str((request.json or {}).get('pin','')) == str(PIN):
        session['auth']=True
        return jsonify({'ok':True})
    return jsonify({'ok':False}),403

@app.get('/api/list')
@login_required
def list_files():
    try:
        item = get_item()
        files=[]
        for f in item.files:
            name=f.get('name','')
            if is_sys(name): continue
            size=int(f.get('size',0))
            files.append({'key':name,'name':name.split('/')[-1],'size':size,
                         'type':file_type(name),
                         'url':f'{WORKER_BASE}/{name}',
                         'direct':f'https://archive.org/download/{BUCKET}/{name}'})
        return jsonify({'files':files})
    except Exception as e:
        logger.error(f"List error: {e}")
        return jsonify({'error':str(e)}),500

@app.post('/api/upload')
@login_required
def upload():
    f=request.files['file']
    key=(request.form.get('key') or f.filename).replace('..','').lstrip('/')
    tmp=f'/tmp/{int(time.time())}_{key}'
    f.save(tmp)
    try:
        get_item().upload(files={key:tmp}, access_key=IA_ACCESS, secret_key=IA_SECRET)
        return jsonify({'ok':True})
    finally:
        try: os.remove(tmp)
        except: pass

@app.post('/api/multipart/init')
@login_required
def mp_init():
    try:
        key=request.json['key']
        resp=s3.create_multipart_upload(Bucket=BUCKET, Key=key)
        return jsonify({'uploadId':resp['UploadId']})
    except Exception as e:
        logger.error(f"MP init: {e}")
        return jsonify({'error':str(e)}),500

@app.post('/api/multipart/part')
@login_required
def mp_part():
    try:
        d=request.json
        url=s3.generate_presigned_url('upload_part',
            Params={'Bucket':BUCKET,'Key':d['key'],'UploadId':d['uploadId'],'PartNumber':d['part']},
            ExpiresIn=3600)
        return jsonify({'url':url})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.post('/api/multipart/complete')
@login_required
def mp_complete():
    try:
        d=request.json
        s3.complete_multipart_upload(Bucket=BUCKET,Key=d['key'],UploadId=d['uploadId'],
                                    MultipartUpload={'Parts':d['parts']})
        return jsonify({'ok':True})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.post('/api/url-upload')
@login_required
def url_upload():
    try:
        data=request.json or {}
        url=data.get('url'); key=data.get('key') or url.split('/')[-1][:100]
        with requests.get(url,stream=True,timeout=3600) as r:
            r.raise_for_status()
            mp=s3.create_multipart_upload(Bucket=BUCKET,Key=key)
            parts=[]; pn=1; buf=b''
            for chunk in r.iter_content(50*1024*1024):
                buf+=chunk
                if len(buf)>=100*1024*1024:
                    resp=s3.upload_part(Bucket=BUCKET,Key=key,UploadId=mp['UploadId'],PartNumber=pn,Body=buf)
                    parts.append({'ETag':resp['ETag'],'PartNumber':pn}); pn+=1; buf=b''
            if buf:
                resp=s3.upload_part(Bucket=BUCKET,Key=key,UploadId=mp['UploadId'],PartNumber=pn,Body=buf)
                parts.append({'ETag':resp['ETag'],'PartNumber':pn})
            s3.complete_multipart_upload(Bucket=BUCKET,Key=key,UploadId=mp['UploadId'],MultipartUpload={'Parts':parts})
        return jsonify({'ok':True})
    except Exception as e:
        logger.error(f"URL upload: {e}")
        return jsonify({'error':str(e)}),500

@app.get('/health')
def health(): return 'ok'

@app.get('/')
def index(): return send_file('file-manager.html')

if __name__=='__main__':
    app.run(host='0.0.0.0',port=8080)
