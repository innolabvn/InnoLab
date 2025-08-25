#!/usr/bin/env python3
import json
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.scan.bearer import BearerScanner
from utils.logger import logger

def debug_bearer_conversion():
    """Debug Bearer conversion function."""
    
    # Read the actual Bearer results file
    bearer_file = "d:/InnoLab/projects/SonarQ/bearer_results/bearer_results_my-service.json"
    
    try:
        print(f"Reading file: {bearer_file}")
        print(f"File exists: {os.path.exists(bearer_file)}")
        
        # Read file content first
        with open(bearer_file, 'r', encoding='utf-8') as f:
            file_content = f.read()
            print(f"File size: {len(file_content)} chars")
            print(f"File content (first 200 chars): {repr(file_content[:200])}")
            
        # Parse JSON
        with open(bearer_file, 'r', encoding='utf-8') as f:
            bearer_data = json.load(f)
            print(f"JSON loaded successfully, type: {type(bearer_data)}")
        
        print(f"Bearer data keys: {list(bearer_data.keys())}")
        
        if "critical" in bearer_data:
            print(f"Critical issues: {len(bearer_data.get('critical', []))}")
            for i, issue in enumerate(bearer_data.get('critical', [])):
                print(f"  Critical {i+1}: {issue.get('id', 'unknown')} - {issue.get('title', 'no title')}")
        
        if "high" in bearer_data:
            print(f"High issues: {len(bearer_data.get('high', []))}")
            for i, issue in enumerate(bearer_data.get('high', [])):
                print(f"  High {i+1}: {issue.get('id', 'unknown')} - {issue.get('title', 'no title')}")
        
        # Test conversion
        scanner = BearerScanner(project_key="test")
        bugs = scanner._convert_bearer_to_bugs_format(bearer_data)
        
        print(f"\nConverted to {len(bugs)} bugs:")
        for i, bug in enumerate(bugs):
            print(f"  Bug {i+1}: {bug['rule']} - {bug['severity']} - {bug['component']}:{bug['line']}")
            print(f"    Message: {bug['message'][:100]}...")
        
        return bugs
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return []

if __name__ == "__main__":
    debug_bearer_conversion()