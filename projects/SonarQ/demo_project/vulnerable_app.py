#!/usr/bin/env python3
import pickle
import subprocess
import hashlib
import os
import sqlite3

# Hardcoded password vulnerability
PASSWORD = "admin123"
API_KEY = "sk-1234567890abcdef"

def unsafe_pickle_load(data):
    """Unsafe pickle deserialization"""
    return pickle.loads(data)

def sql_injection_vulnerable(user_input):
    """SQL injection vulnerability"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE name = '{user_input}'"
    cursor.execute(query)
    return cursor.fetchall()

def command_injection_vulnerable(filename):
    """Command injection vulnerability"""
    cmd = f"cat {filename}"
    return subprocess.call(cmd, shell=True)

def weak_hash(password):
    """Weak hashing algorithm"""
    return hashlib.md5(password.encode()).hexdigest()

def path_traversal_vulnerable(filename):
    """Path traversal vulnerability"""
    with open(f"/var/www/{filename}", 'r') as f:
        return f.read()

def eval_vulnerability(user_code):
    """Code injection via eval"""
    return eval(user_code)

if __name__ == "__main__":
    # Test the vulnerabilities
    print("Testing vulnerable functions...")
    print(f"Password: {PASSWORD}")
    print(f"API Key: {API_KEY}")