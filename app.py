import os, requests, mimetypes
from flask import Flask, request, session, redirect, jsonify, Response, make_response
from werkzeug.utils import secure_filename
from xml.etree.ElementTree import Element, SubElement, tostring
from datetime import datetime
from urllib.parse import unquote

IA_BUCKET = os.getenv("IA_BUCKET")
IA_ACCESS = os.getenv("IA_ACCESS_KEY")
IA_SECRET = os.getenv("IA_SECRET_KEY")
LOGIN_PIN = os.getenv("LOGIN_PIN", "2383")
DAV_USER = os.getenv("DAV_USER", "admin")
DAV_PASS = os.getenv("DAV_PASS", "2383")
ENDPOINT = "https://s3.us.archive.org"
WORKER = os.getenv("WORKER_MEDIA_BASE", "").rstrip("/")
AUTH = f"LOW {IA_ACCESS}:{IA_SECRET}"

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "secret")

# --- IA helpers ---
def ia_put(key, data, ctype):
    h = {
        "authorization": AUTH,
        "x-amz-auto-make-bucket": "1",
        "x-archive-auto-make-bucket": "1",
        "x-archive-meta01-collection": "opensource",
        "x-archive-meta-mediatype": "data",
        "x-archive-queue-derive": "0",
        "x-archive-interactive-priority": "1",
        "Content-Type": ctype or "application/octet-stream",
    }
    r = requests.put(f"{ENDPOINT}/{IA_BUCKET}/{key}", data=data, headers=h, timeout=900)
    r.raise_for_status()

def ia_get(key):
    r = requests.get(f"{ENDPOINT}/{IA_BUCKET}/{key}", headers={"authorization": AUTH}, timeout=600, stream=True)
    if r.status_code == 404: return None
    r.raise_for_status()
    return r

def ia_delete(key):
    r = requests.delete(f"{ENDPOINT}/{IA_BUCKET}/{key}", headers={"authorization": AUTH}, timeout=30)
    if r.status_code not in (200,204,404): r.raise_for_status()

def ia_list():
    try:
        r = requests.get(f"https://archive.org/metadata/{IA_BUCKET}", timeout=15)
        if not r.ok: return []
        files = []
        for f in r.json().get("files", []):
            name = f.get("name","")
            if name.startswith("_") or name == "history": continue
            files.append({
                "name": name,
                "size": int(f.get("size",0)),
                "mtime": f.get("mtime"),
                "is_dir": name.endswith("/"),
                "url": f"{WORKER}/{IA_BUCKET}/{name}" if WORKER else f"https://archive.org/download/{IA_BUCKET}/{name}"
            })
        return files
    except: return []

# --- Web UI auth ---
@app.before_request
def check_web():
    if request.path.startswith("/dav") or request.path in ("/login","/health"): return
    if not session.get("ok"): return redirect("/login")

# --- WebDAV auth ---
def dav_auth():
    auth = request.authorization
    if not auth or auth.username!= DAV_USER or auth.password!= DAV_PASS:
        return Response("Unauthorized", 401, {"WWW-Authenticate": 'Basic realm="IA DAV"'})
    return None

# --- WebDAV endpoints ---
@app.route("/dav/", defaults={"path": ""}, methods=["OPTIONS","PROPFIND","GET","PUT","DELETE","MKCOL","PROPPATCH"])
@app.route("/dav/<path:path>", methods=["OPTIONS","PROPFIND","GET","PUT","DELETE","MKCOL","PROPPATCH"])
def dav(path):
    if (resp := dav_auth()): return resp
    path = unquote(path)

    if request.method == "OPTIONS":
        resp = make_response("", 200)
        resp.headers["DAV"] = "1,2"
        resp.headers["Allow"] = "OPTIONS,GET,HEAD,PUT,DELETE,PROPFIND,MKCOL"
        return resp

    if request.method == "PROPFIND":
        depth = request.headers.get("Depth", "1")
        files = ia_list()
        if path and not path.endswith("/"): files = [f for f in files if f["name"] == path]
        elif path: files = [f for f in files if f["name"].startswith(path)]

        multistatus = Element("{DAV:}multistatus")
        # root
        for f in ([{"name":path,"size":0,"mtime":None,"is_dir":True}] + files if not path or depth!="0" else files):
            resp_el = SubElement(multistatus, "{DAV:}response")
            href = SubElement(resp_el, "{DAV:}href")
            href.text = f"/dav/{f['name']}" + ("/" if f.get("is_dir") else "")
            propstat = SubElement(resp_el, "{DAV:}propstat")
            prop = SubElement(propstat, "{DAV:}prop")
            SubElement(prop, "{DAV:}displayname").text = f["name"].split("/")[-1] or IA_BUCKET
            SubElement(prop, "{DAV:}getcontentlength").text = str(f["size"])
            SubElement(prop, "{DAV:}resourcetype").text = ""
            if f.get("is_dir"): SubElement(prop, "{DAV:}resourcetype")
            SubElement(propstat, "{DAV:}status").text = "HTTP/1.1 200 OK"

        xml = tostring(multistatus, encoding="utf-8", xml_declaration=True)
        resp = make_response(xml, 207)
        resp.headers["Content-Type"] = "application/xml; charset=utf-8"
        return resp

    if request.method == "GET":
        r = ia_get(path)
        if not r: return "Not found", 404
        return Response(r.iter_content(8192), headers={"Content-Type": r.headers.get("Content-Type","application/octet-stream")})

    if request.method == "PUT":
        ia_put(path, request.stream, request.content_type)
        return "", 201

    if request.method == "DELETE":
        ia_delete(path)
        return "", 204

    if request.method == "MKCOL":
        # IA has no folders, create a placeholder
        ia_put(path.rstrip("/")+"/.keep", b"", "text/plain")
        return "", 201

    return "", 200

# --- Web UI (keep your existing UI) ---
@app.route("/health")
def health(): return "ok"

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST" and request.form.get("pin")==LOGIN_PIN:
        session["ok"]=True; return redirect("/")
    return '<form method=post><input name=pin type=password><button>login</button></form>'

@app.route("/")
def home():
    return open(__file__).read().split("#WEBUI#")[1] if "#WEBUI#" in open(__file__).read() else "UI"

# [Paste your previous HTML UI here, or keep simple]
@app.route("/api/list")
def api_list(): return jsonify(ia_list())

@app.route("/api/upload", methods=["POST"])
def api_upload():
    f = request.files["file"]
    ia_put(secure_filename(f.filename), f.stream, f.content_type)
    return "",200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
