import os
import re
import base64
import sqlite3
import hashlib
import subprocess
import tempfile
import tarfile
import pickle
import requests
import yaml
import jwt  # PyJWT
from flask import Flask, request, jsonify

# ============================
# 1) Hardcoded secrets (VULN: hard-coded credentials)
# ============================
AWS_ACCESS_KEY_ID = "AKIAFAKEEXAMPLE1234"
AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYFAKEKEY"
GITHUB_TOKEN = "ghp_FAKEexample1234567890token"
PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----\nMIIBUgIBADANBgkqhkiG9w0BAQEFAASCAT8wggE7AgEAAkEAuFakeKeyFakeKey\nFakeKeyFakeKeyFakeKeyFakeKeyFakeKeyFakeKeyFakeKeyFakeKeyFakeKey==\n-----END PRIVATE KEY-----"""

app = Flask(__name__)
app.config["SECRET_KEY"] = "supersecret123"  # VULN: hardcoded secret key

# DB setup (not safe for prod)
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users(name TEXT, password TEXT)")
conn.commit()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================
# 2) Weak crypto (MD5/SHA1), logging PII, insecure password storage
# ============================
@app.route("/signup", methods=["POST"])
def signup():
    data = request.get_json(force=True)
    name = data.get("name")
    password = data.get("password")
    credit_card = data.get("credit_card")  # PII

    # VULN: logging PII
    print(f"[DEBUG] New signup: name={name}, credit_card={credit_card}")

    # VULN: weak, unsalted hash (MD5)
    pwd_hash = hashlib.md5(password.encode()).hexdigest()

    cursor.execute(
        f"INSERT INTO users(name, password) VALUES ('{name}', '{pwd_hash}')"  # VULN: SQL injection on 'name'
    )
    conn.commit()

    return jsonify({"ok": True, "hash": pwd_hash})

# ============================
# 3) SQL Injection
# ============================
@app.route("/find")
def find_user():
    username = request.args.get("username", "")
    # VULN: raw string interpolation into SQL
    q = f"SELECT name, password FROM users WHERE name = '{username}'"
    print("[DEBUG] Executing:", q)
    try:
        rows = list(cursor.execute(q))
        return jsonify(rows)
    except Exception as e:
        # VULN: swallowing exceptions
        return jsonify({"error": str(e)})

# ============================
# 4) Command Injection
# ============================
@app.route("/exec")
def run_cmd():
    cmd = request.args.get("cmd", "echo hi")
    # VULN: shell=True with user-controlled input
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return jsonify({"cmd": cmd, "stdout": out.stdout, "stderr": out.stderr})

# ============================
# 5) SSRF + TLS verification disabled
# ============================
@app.route("/fetch")
def fetch_url():
    url = request.args.get("url", "http://localhost:80")
    # VULN: SSRF + verify=False leaks
    r = requests.get(url, verify=False, timeout=2)
    return jsonify({"status": r.status_code, "body": r.text[:400]})

# ============================
# 6) Path Traversal / Arbitrary File Read
# ============================
@app.route("/read")
def read_file():
    rel_path = request.args.get("path", "README.md")
    # VULN: no normalization or allowlist -> traversal
    target = os.path.join(BASE_DIR, rel_path)
    try:
        with open(target, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(500)
    except Exception as e:
        return f"ERR: {e}", 400

# ============================
# 7) Unsafe YAML deserialization
# ============================
@app.route("/yaml", methods=["POST"])
def yaml_load():
    content = request.data.decode("utf-8", errors="ignore")
    # VULN: yaml.load is unsafe (should use safe_load)
    data = yaml.load(content, Loader=yaml.FullLoader)
    return jsonify({"loaded": bool(data), "type": str(type(data))})

# ============================
# 8) Insecure Pickle deserialization
# ============================
@app.route("/pickle", methods=["POST"])
def pickle_load():
    b64 = request.get_data() or b""
    try:
        blob = base64.b64decode(b64)
        # VULN: arbitrary code execution risk
        obj = pickle.loads(blob)
        return jsonify({"ok": True, "type": str(type(obj))})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

# ============================
# 9) JWT verification disabled
# ============================
@app.route("/jwt")
def jwt_parse():
    token = request.args.get("token", "")
    try:
        # VULN: signature verification disabled
        payload = jwt.decode(token, options={"verify_signature": False, "verify_aud": False})
        return jsonify({"payload": payload})
    except Exception as e:
        return jsonify({"error": str(e)})

# ============================
# 10) Dangerous tar extraction (path traversal via tar entries)
# ============================
@app.route("/untar", methods=["POST"])
def untar():
    tmp = tempfile.mktemp(suffix=".tar")  # VULN: mktemp is insecure (race)
    with open(tmp, "wb") as f:
        f.write(request.get_data())
    # VULN: extractall without sanitization
    with tarfile.open(tmp) as tar:
        tar.extractall(BASE_DIR)
    return jsonify({"ok": True, "extracted_to": BASE_DIR})

# ============================
# 11) eval/exec on user input
# ============================
@app.route("/calc")
def calc():
    expr = request.args.get("expr", "1+1")
    # VULN: Remote code execution
    try:
        result = eval(expr)
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)})

# ============================
# 12) Leaking environment & secrets
# ============================
@app.route("/debug")
def debug_dump():
    # VULN: exposes sensitive env vars
    return jsonify(dict(os.environ))

# ============================
# 13) Sending sensitive data over plaintext HTTP
# ============================
@app.route("/notify", methods=["POST"])
def notify_plain_http():
    data = request.get_json(force=True)
    password = data.get("password", "")
    # VULN: sending secrets over HTTP (no TLS) + no timeout + no error handling
    try:
        requests.post("http://example.com/collect", json={"pwd": password})
    except Exception:
        pass
    return jsonify({"ok": True})

# ============================
# 14) Regex DoS (catastrophic backtracking)
# ============================
@app.route("/regex")
def bad_regex():
    text = request.args.get("text", "a" * 100000)
    # VULN: evil regex
    pattern = re.compile(r"^(a+)+$")
    return jsonify({"matched": bool(pattern.match(text))})


if __name__ == "__main__":
    # VULN: debug True in production
    app.run(host="0.0.0.0", port=5000, debug=True)