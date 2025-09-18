import hashlib
import json # Replaced pickle with json for secure deserialization
import os
import subprocess # Replaced os.system with subprocess for security

data = "sensitive_data"
hashed = hashlib.sha256(data.encode()).hexdigest() # Replaced md5 with sha256
# result = pickle.loads(b"test") # Removed pickle usage due to security vulnerability
result = json.loads(r'{"test": "value"}') # Replaced pickle with json example

# os.system("echo hello") # Replaced os.system with subprocess.run
subprocess.run(["echo", "hello"]) # Replaced os.system with subprocess.run to avoid shell injection