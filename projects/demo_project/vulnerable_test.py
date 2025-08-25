import os
import subprocess
import hashlib

# Security vulnerability: hardcoded password
PASSWORD = "admin123"

# Security vulnerability: SQL injection
def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return query

# Security vulnerability: command injection
def run_command(user_input):
    cmd = f"ls {user_input}"
    subprocess.call(cmd, shell=True)

# Security vulnerability: weak hash
def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()

# Security vulnerability: path traversal
def read_file(filename):
    with open(f"/var/log/{filename}", 'r') as f:
        return f.read()

# Security vulnerability: eval usage
def calculate(expression):
    return eval(expression)

if __name__ == "__main__":
    print("Testing vulnerable code")
    print(get_user("1 OR 1=1"))
    run_command("../../../etc/passwd")
    print(hash_password(PASSWORD))
    print(read_file("../../../etc/passwd"))
    print(calculate("__import__('os').system('whoami')"))