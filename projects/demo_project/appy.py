from flask import Flask, request
import os
import sqlite3
import pickle
import hashlib
import requests
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ❌ Hardcoded secrets (Bearer sẽ flag)
AWS_ACCESS_KEY_ID = "AKIA1234567890ABCD"
AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYzEXAMPLEKEY"
STRIPE_SECRET_KEY = "sk_live_FAKE_FAKE_FAKE_1234567890"
INTERNAL_API_KEY = "supersecretapikey_12345"

DB = "users.db"

@app.route("/search")
def search():
    # ❌ SQL Injection (string format trực tiếp từ input)
    q = request.args.get("q", "")
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM users WHERE name = '{q}'")  # vulnerable
    rows = cur.fetchall()
    conn.close()
    return {"rows": rows}

@app.route("/run")
def run():
    # ❌ Command Injection
    cmd = request.args.get("cmd", "")
    os.system("sh -lc '" + cmd + "'")  # vulnerable
    return "ok"

@app.route("/eval")
def do_eval():
    # ❌ eval trên input người dùng
    expr = request.args.get("expr", "")
    return str(eval(expr))  # vulnerable

@app.route("/upload", methods=["POST"])
def upload():
    # ❌ Insecure deserialization
    data = request.data
    obj = pickle.loads(data)  # vulnerable
    return str(obj)

@app.route("/hash", methods=["POST"])
def hash_password():
    # ❌ Weak hash (MD5)
    password = request.form.get("password", "")
    h = hashlib.md5(password.encode()).hexdigest()
    logging.info("User password MD5: %s", h)
    return h

@app.route("/fetch")
def fetch():
    # ❌ Insecure SSL (verify=False) + log dữ liệu nhạy cảm
    url = request.args.get("url", "https://expired.badssl.com/")
    cc = request.args.get("credit_card")  # ví dụ dữ liệu nhạy cảm
    r = requests.get(url, verify=False)
    logging.info("Fetched %s for credit_card=%s", url, cc)  # ❌ logging sensitive data
    return r.text

@app.route("/read")
def read_file():
    # ❌ Path traversal
    filename = request.args.get("file", "../../etc/passwd")
    with open(filename, "r") as f:
        return f.read()

if __name__ == "__main__":
    # ❌ debug mode bật trong production
    app.run(host="0.0.0.0", port=5000, debug=True)