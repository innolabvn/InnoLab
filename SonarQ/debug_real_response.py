import json
import re
import ast
import os
import sys
sys.path.append('.')
from batch_fix import SecureFixProcessor
from dotenv import load_dotenv

# Load environment variables
load_dotenv(dotenv_path=r'd:\InnoLab\.env')

# Read the latest log file
log_file = './logs/template_usage_20250821_133745.log'

with open(log_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Extract AI response from log
ai_response_pattern = r'AI_RESPONSE: ({.*?})(?=\n|$)'
matches = re.findall(ai_response_pattern, content, re.DOTALL)

if matches:
    # Get the first AI response
    response_data = json.loads(matches[0])
    full_response = response_data.get('full_cleaned_response', '')
    
    print("=== FULL CLEANED RESPONSE ===")
    print(repr(full_response))
    print("\n=== FULL CLEANED RESPONSE (formatted) ===")
    print(full_response)
    
    # Test syntax validation
    try:
        ast.parse(full_response)
        print("\n✓ Syntax is valid!")
    except SyntaxError as e:
        print(f"\n✗ Syntax error: {e}")
        print(f"Line {e.lineno}: {e.text}")
        print(f"Error at position {e.offset}")
        
        # Show lines around the error
        lines = full_response.split('\n')
        error_line = e.lineno - 1
        print("\n=== CONTEXT AROUND ERROR ===")
        for i in range(max(0, error_line-2), min(len(lines), error_line+3)):
            marker = ">>> " if i == error_line else "    "
            print(f"{marker}{i+1:3}: {repr(lines[i])}")
else:
    print("No AI response found in log")
    print("Available content:")
    print(content)