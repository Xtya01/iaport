import os, requests
from flask import Flask, request, session, redirect
from werkzeug.utils import secure_filename

IA_BUCKET = os.getenv("IA_BUCKET")
IA_ACCESS = os.getenv("IA_ACCESS_KEY")
IA_SECRET = os.getenv("IA_SECRET_KEY")
LOGIN_PIN = os.getenv("LOGIN_PIN", "2383")
ENDPOINT = "https://s3.us.archive.org"
AUTH = f"LOW {IA_ACCESS}:{IA_SECRET}"

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "change-me")

def ia_put(key, data, ctype):
    headers = {
        "authorization": AUTH,
        "x-amz-auto-make-bucket": "1",
        "x-archive-auto-make-bucket": "1",
        "x-archive-meta01-collection": "opensource",
        "x-archive-meta-mediatype": "data",
        "x-archive-queue-derive": "0",
        "x-archive-interactive-priority": "1",
        "Content-Type": ctype or "application/octet-stream",
    }
    r = requests.put(f"{ENDPOINT}/{IA_BUCKET}/{key}", data=data, headers=headers, timeout=600)
    r.raise_for_status()

def ia_list():
    try:
        r = requests.get(f"https://archive.org/metadata/{IA_BUCKET}", timeout=10)
        if r.ok:
            return [{"name": f["name"], "size": int(f.get("size",0))} for f in r.json().get("files",[]) if not f["name"].startswith("_")]
    except: pass
    return []

@app.before_request
def chk():
    if request.path != "/login" and not session.get("ok"):
        return redirect("/login")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST" and request.form.get("pin") == LOGIN_PIN:
        session["ok"] = True
        return redirect("/")
    return '<form method=post style="margin:100px auto;width:300px"><h2>IA Drive</h2><input name=pin type=password placeholder=PIN style="width:100%;padding:10px"><button style="width:100%;margin-top:10px">Enter</button></form>'

@app.route("/")
def home():
    files = ia_list()
    rows = "".join([f"<li>{f['name']} - {f['size']//1024}KB</li>" for f in files])
    return f'<div style="font-family:sans-serif;max-width:800px;margin:40px auto"><h1>{IA_BUCKET}</h1><form action=/upload method=post enctype=multipart/form-data><input type=file name=file required> <button>Upload</button></form><ul>{rows}</ul></div>'

@app.route("/upload", methods=["POST"])
def up():
    f = request.files["file"]
    ia_put(secure_filename(f.filename), f.stream, f.content_type)
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
