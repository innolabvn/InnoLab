#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to export SonarQube issues to JSON file with proper encoding
"""

import sys
import json
import os
from export_issues import main as export_main

def export_to_file(project_key, output_file=None):
    """
    Export SonarQube issues to a JSON file
    """
    if not output_file:
        output_file = f"issues_{project_key}.json"
    
    # Capture the output from export_issues
    import io
    from contextlib import redirect_stdout
    
    # Redirect stdout to capture JSON output
    f = io.StringIO()
    try:
        with redirect_stdout(f):
            # Call the main function from export_issues
            sys.argv = ['export_issues.py', project_key]
            export_main()
        
        # Get the captured output
        json_output = f.getvalue()
        
        # Parse and reformat JSON to ensure it's valid
        try:
            data = json.loads(json_output)
            
            # Remove existing file if it exists
            if os.path.exists(output_file):
                os.remove(output_file)
                print(f"Removed existing file: {output_file}")
            
            # Write to file with proper UTF-8 encoding
            with open(output_file, 'w', encoding='utf-8') as file:
                json.dump(data, file, indent=4, ensure_ascii=False)
            
            print(f"Issues exported successfully to: {output_file}")
            print(f"Total issues found: {len(data.get('issues', []))}")
            
            # Show statistics
            issues = data.get('issues', [])
            if issues:
                severity_counts = {}
                for issue in issues:
                    severity = issue.get('severity', 'UNKNOWN')
                    severity_counts[severity] = severity_counts.get(severity, 0) + 1
                
                print("\nIssues by severity:")
                for severity, count in severity_counts.items():
                    print(f"  {severity}: {count}")
            
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON output - {e}")
            # Write raw output for debugging
            with open(f"debug_{output_file}", 'w', encoding='utf-8') as file:
                file.write(json_output)
            return False
            
    except Exception as e:
        print(f"Error exporting issues: {e}")
        return False
    
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python export_to_file.py <project_key> [output_file]")
        sys.exit(1)
    
    project_key = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    success = export_to_file(project_key, output_file)
    sys.exit(0 if success else 1)