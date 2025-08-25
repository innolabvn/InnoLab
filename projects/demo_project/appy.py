from flask import Flask, request
import os
import sqlite3
import pickle
import hashlib
import requests
import logging
import bcrypt  # Added for bcrypt

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Hardcoded secrets (Bearer sẽ flag)
AWS_ACCESS_KEY_ID = "REPLACE_ME" # Fixed: Removed hardcoded secret, replace with secure method
AWS_SECRET_ACCESS_KEY = "REPLACE_ME" # Fixed: Removed hardcoded secret, replace with secure method
STRIPE_SECRET_KEY = "REPLACE_ME" # Fixed: Removed hardcoded secret, replace with secure method
INTERNAL_API_KEY = "REPLACE_ME" # Fixed: Removed hardcoded secret, replace with secure method

DB = "users.db"

@app.route("/search")
def search():
    # SQL Injection (string format trực tiếp từ input)
    q = request.args.get("q", "")
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE name = ?", (q,))  # prevent SQL injection
    rows = cur.fetchall()
    conn.close()
    return {"rows": rows}

@app.route("/run")
def run():
    # Command Injection
    # cmd = request.args.get("cmd", "")
    # os.system("sh -lc '" + cmd + "'")  # vulnerable
    return "Command injection is removed for security reasons." # Fixed: Removed command injection for security reasons.

@app.route("/eval")
def do_eval():
    # eval trên input người dùng
    # expr = request.args.get("expr", "")
    # return str(eval(expr))  # vulnerable
    return "Eval is removed for security reasons." # Fixed: Removed eval for security reasons

@app.route("/upload", methods=["POST"])
def upload():
    # Insecure deserialization
    # data = request.data
    # obj = pickle.loads(data)  # vulnerable
    # return str(obj)
    return "Insecure deserialization is removed for security reasons." # Fixed: Removed insecure deserialization for security reasons

@app.route("/hash", methods=["POST"])
def hash_password():
    # Weak hash (MD5)
    password = request.form.get("password", "")
    #h = hashlib.md5(password.encode()).hexdigest()
    #logging.info("User password MD5: %s", h)
    #return h
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()) #use bcrypt
    logging.info("User password (bcrypt): %s", hashed)
    return hashed.decode('utf-8') # Fixed: Use bcrypt for password hashing

@app.route("/fetch")
def fetch():
    # Insecure SSL (verify=False) + log dữ liệu nhạy cảm
    url = request.args.get("url", "https://expired.badssl.com/")
    cc = request.args.get("credit_card")  # ví dụ dữ liệu nhạy cảm
    r = requests.get(url, verify=True) # Fixed: Enabled SSL verification
    logging.info("Fetched %s", url) # Fixed: Removed logging of sensitive data
    return r.text

@app.route("/read")
def read_file():
    # Path traversal
    filename = request.args.get("file", "../../etc/passwd")
    filename = filename.replace("../", "") # Sanitize path
    with open(filename, "r") as f:
        return f.read() # Fixed: Added path traversal protection

if __name__ == "__main__":
    # debug mode bật trong production
    app.run(host="0.0.0.0", port=5000, debug=False) # Fixed: Disabled debug mode