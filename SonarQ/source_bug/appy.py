from flask import Flask, request
import os
import sqlite3
import pickle
import hashlib
import requests
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Hardcoded secrets (loaded from environment variables)
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")  # Load from environment
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")  # Load from environment
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")  # Load from environment
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY")  # Load from environment

DB = "users.db"

@app.route("/search")
def search():
    # Fix: SQL Injection - Use parameterized query
    q = request.args.get("q", "")
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE name = ?", (q,))  # Vulnerable: SQL Injection
    rows = cur.fetchall()
    conn.close()
    return {"rows": rows}

@app.route("/run")
def run():
    # Removed: Command Injection -  os.system is inherently unsafe with user input
    return "Function removed for security reasons"

@app.route("/eval")
def do_eval():
    # Removed: Insecure Eval - eval is inherently unsafe with user input
    return "Function removed for security reasons"

@app.route("/upload", methods=["POST"])
def upload():
    # Removed: Insecure deserialization - pickle.loads is unsafe with untrusted data
    return "Function removed for security reasons"

@app.route("/hash", methods=["POST"])
def hash_password():
    # Fix: Weak hash - Use SHA256 instead of MD5
    password = request.form.get("password", "")
    h = hashlib.sha256(password.encode()).hexdigest()  # Use SHA256
    logging.info("User password SHA256: %s", h)
    return h

@app.route("/fetch")
def fetch():
    # Fix: Insecure SSL and logging - Enable SSL verification and remove sensitive logging
    url = request.args.get("url", "https://expired.badssl.com/")
    cc = request.args.get("credit_card")  # ví dụ dữ liệu nhạy cảm
    r = requests.get(url, verify=True)  # Enable SSL verification
    logging.info("Fetched %s", url)  # Remove logging of sensitive data
    return r.text

@app.route("/read")
def read_file():
    # Fix: Path traversal - Validate filename
    filename = request.args.get("file", "allowed_file.txt")
    
    # Sanitize the filename to prevent path traversal
    import os
    base_dir = "." # Only allow files in the current directory
    abs_path = os.path.abspath(os.path.join(base_dir, filename))
    if not abs_path.startswith(os.path.abspath(base_dir)):
        # If the absolute path is not within the base directory, reject the request
        return "Path traversal detected", 400  # Prevent path traversal
    with open(filename, "r") as f:
        return f.read()

if __name__ == "__main__":
    # Fix: Debug mode enabled - Disable debug mode in production
    app.run(host="0.0.0.0", port=5000, debug=False)  # Disable debug mode