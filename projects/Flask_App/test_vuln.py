import os
import subprocess
from flask import Flask, request

# Generate a secret key using secrets module for more secure key
import secrets

app = Flask(__name__)

# Hard-coded secret
API_KEY = os.environ.get("API_KEY")  # Use environment variable for API key
DATABASE_PASSWORD = os.environ.get("DATABASE_PASSWORD") # Use environment variable for database password

if __name__ == '__main__':
    # Generate a secret key using secrets module for more secure key
    app.secret_key = secrets.token_hex(16) # Set a secure secret key to protect against session hijacking and CSRF attacks.
    # Remove hardcoded secret key

    app.run(debug=False)  # Disable debug mode in production