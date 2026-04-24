import os, requests
from flask import Flask, request, session, redirect
from werkzeug.utils import secure_filename

IA_BUCKET = os.getenv("IA_BUCKET", "junk-manage-caution")
IA_ACCESS = os.getenv("IA_ACCESS_KEY")
IA_SECRET = os.getenv("IA_SECRET_KEY")
LOGIN_PIN = os.getenv("LOGIN_PIN", "2383")
ENDPOINT = "https://s3.us.archive.org"
WORKER_BASE = os.getenv("WORKER_MEDIA_BASE", "")
AUTH = f"LOW {IA_ACCESS}:{IA_SECRET}" if IA_ACCESS and IA_SECRET else ""

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "change-me-secret")

def ia_put(key, data, ctype):
    url = f"{ENDPOINT}/{IA_BUCKET}/{key}"
    headers = {
        "authorization": AUTH,
        "x-amz-auto-make-bucket": "1",
        "x-archive-auto-make-bucket": "1",
        "x-archive-queue-derive": "0",
        "x-archive-interactive-priority": "1",
        "Content-Type": ctype or "application/octet-stream",
    }
    r = requests.put(url, data=data, headers=headers, timeout=600)
    r.raise_for_status()

def ia_list():
    try:
        r = requests.get(f"https://archive.org/metadata/{IA_BUCKET}", timeout=15)
        if r.status_code == 200:
            files = r.json().get("files", [])
            return [{"name": f["name"], "size": int(f.get("size",0))} for f in files if not f["name"].startswith("_")]
    except: pass
    return []

@app.before_request
def check():
    if request.path in ["/login","/health"] or request.path.startswith("/static"):
        return
    if not session.get("ok"):
        return redirect("/login")

@app.route("/health")
def health(): return "ok"

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        if request.form.get("pin")==LOGIN_PIN:
            session["ok"]=True
            return redirect("/")
        return "Wrong PIN",403
    return '<form method=post style="margin:100px auto;width:300px;font-family:sans-serif"><h2>IA Drive</h2><input name=pin type=password placeholder=PIN style="width:100%;padding:10px"><button style="width:100%;margin-top:10px;padding:10px">Enter</button></form>'

@app.route("/")
def home():
    files = ia_list()
    rows = "".join([f"<tr><td>{f['name']}</td><td>{f['size']//1024}KB</td><td><a href='{(WORKER_BASE or 'https://archive.org/download')}/{IA_BUCKET}/{f['name']}' target=_blank>open</a></td></tr>" for f in files])
    return f"<html><body style='font-family:sans-serif;max-width:900px;margin:40px auto'><h1>IA Drive - {IA_BUCKET}</h1><form action=/upload method=post enctype=multipart/form-data><input type=file name=file required> <button>Upload</button></form><h3>Files ({len(files)})</h3><table border=1 cellpadding=6 style='border-collapse:collapse;width:100%'><tr><th>Name</th><th>Size</th><th>Link</th></tr>{rows}</table></body></html>"

@app.route("/upload", methods=["POST"])
def upload():
    f = request.files["file"]
    ia_put(secure_filename(f.filename), f.stream, f.content_type)
    return redirect("/")

if __name__=="__main__":
    app.run(host="0.0.0.0", port=8080)
