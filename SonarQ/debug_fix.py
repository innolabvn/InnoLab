#!/usr/bin/env python3
"""
Debug script to test batch_fix.py with a simple case
"""

import os
import sys
import json
from pathlib import Path

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from batch_fix import SecureFixProcessor
from dotenv import load_dotenv

def test_simple_fix():
    """Test fixing a simple Python file"""
    
    # Load environment
    root_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    load_dotenv(root_env_path)
    api_key = os.getenv('GEMINI_API_KEY')
    
    if not api_key:
        print("Error: GEMINI_API_KEY not found")
        return
    
    # Test with source_bug directory
    source_dir = "source_bug"
    
    if not os.path.exists(source_dir):
        print(f"Directory {source_dir} not found")
        return
    
    # Create processor
    processor = SecureFixProcessor(api_key, source_dir)
    
    # Test file
    test_file = os.path.join(source_dir, "code.py")
    
    if not os.path.exists(test_file):
        print(f"Test file {test_file} not found")
        return
    
    print(f"Testing fix for: {test_file}")
    
    # Create simple issues data
    issues_data = [
        {
            "bug_id": "test1",
            "bug_name": "Remove useless self-assignment",
            "rule_key": "python:S1656",
            "severity": "MAJOR",
            "type": "BUG",
            "file_path": "code.py",
            "line": 17,
            "message": "Remove or correct this useless self-assignment."
        }
    ]
    
    try:
        # Test the fix
        result = processor.fix_file_with_validation(
            test_file,
            template_type='fix',
            custom_prompt=None,
            max_retries=1,  # Reduce retries for debugging
            issues_data=issues_data
        )
        
        print(f"\nResult: {result.success}")
        print(f"Issues found: {result.issues_found}")
        print(f"Validation errors: {result.validation_errors}")
        
        if not result.success:
            print("\nDebugging failed fix...")
            
    except Exception as e:
        print(f"Error during fix: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_simple_fix()