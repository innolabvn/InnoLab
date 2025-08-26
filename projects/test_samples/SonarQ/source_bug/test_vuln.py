import os
import subprocess
from flask import Flask, request

app = Flask(__name__)

# SQL Injection vulnerability
@app.route('/user')
def get_user():
    user_id = request.args.get('id')
    query = f"SELECT * FROM users WHERE id = {user_id}"  # SQL injection
    return query

# Command injection vulnerability
@app.route('/ping')
def ping():
    host = request.args.get('host')
    result = os.system(f"ping {host}")  # Command injection
    return str(result)

# Hard-coded secret
API_KEY = "sk-1234567890abcdef"  # Hard-coded API key
DATABASE_PASSWORD = "admin123"  # Hard-coded password

if __name__ == '__main__':
    app.run(debug=True)  # Debug mode in production