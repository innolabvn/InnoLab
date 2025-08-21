import os
import sys
sys.path.append('.')
from batch_fix import SecureFixProcessor
from dotenv import load_dotenv

# Load environment variables from root directory
load_dotenv(dotenv_path=r'd:\InnoLab\.env')

# Initialize processor
api_key = os.getenv('GEMINI_API_KEY')
processor = SecureFixProcessor(api_key, './source_bug')

# Test sample response
sample_response = '''## 1. Bug Context
The log reports one issue:

- **test1 (python:S1656): Remove useless self-assignment (MAJOR, BUG) at code.py:17**. Label: True Positive ("bug").

## 2. Fix Summary
- Fixed useless self-assignment at line 17

## 3. Fixed Source Code

import re 

def rethrow_same_exception(value: str) -> int:
    try:
        return int(value)
    except ValueError as e:
        raise e 

def self_assign_example():
    x = 5
    # Fixed: removed useless self-assignment x = x
    return x
'''

# Test extraction
extracted = processor._clean_response(sample_response)
print("=== EXTRACTED CODE ===")
print(repr(extracted))
print("=== EXTRACTED CODE (formatted) ===")
print(extracted)

# Test syntax validation
import ast
try:
    ast.parse(extracted)
    print("\n✓ Syntax is valid!")
except SyntaxError as e:
    print(f"\n✗ Syntax error: {e}")
    print(f"Line {e.lineno}: {e.text}")