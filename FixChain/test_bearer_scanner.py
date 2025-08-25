#!/usr/bin/env python3
"""
Test script for Bearer Scanner
This script tests the Bearer scanner functionality
"""

import os
import sys
import json
from pathlib import Path

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.scan.bearer import BearerScanner
from utils.logger import logger

def test_bearer_scanner():
    """Test Bearer scanner with a sample project."""
    
    # Test configuration
    project_key = "test-project"
    scan_directory = "projects/demo_project"  # Relative to InnoLab root directory
    
    logger.info("Starting Bearer Scanner test...")
    
    try:
        # Initialize Bearer scanner
        scanner = BearerScanner(project_key=project_key, scan_directory=scan_directory)
        
        # Run the scan
        logger.info(f"Running Bearer scan for project: {project_key}")
        bugs = scanner.scan()
        
        # Display results
        logger.info(f"Bearer scan completed. Found {len(bugs)} security issues.")
        
        if bugs:
            logger.info("Sample findings:")
            for i, bug in enumerate(bugs[:3]):  # Show first 3 findings
                logger.info(f"  {i+1}. {bug['rule']} - {bug['severity']} - {bug['component']}:{bug['line']}")
                logger.info(f"     Message: {bug['message'][:100]}...")
        
        # Save results to file for inspection
        output_file = f"bearer_test_results_{project_key}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(bugs, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Results saved to: {output_file}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error during Bearer scanner test: {e}")
        return False

def test_bearer_json_parsing():
    """Test Bearer JSON parsing with sample data."""
    
    logger.info("Testing Bearer JSON parsing...")
    
    # Sample Bearer JSON data (new format)
    sample_bearer_data = {
        "findings": [
            {
                "id": "javascript_lang_hardcoded_secret",
                "title": "Hardcoded Secret",
                "description": "Hardcoded secrets detected in source code",
                "severity": "high",
                "filename": "/scan/app.js",
                "line_number": 15,
                "source": {
                    "start": 15,
                    "column": {
                        "start": 10,
                        "end": 25
                    }
                },
                "cwe_ids": ["798"],
                "type": "security",
                "confidence": "high"
            },
            {
                "id": "javascript_lang_sql_injection",
                "title": "SQL Injection",
                "description": "Potential SQL injection vulnerability",
                "severity": "critical",
                "filename": "/scan/database.js",
                "line_number": 42,
                "source": {
                    "start": 42,
                    "column": {
                        "start": 5,
                        "end": 30
                    }
                },
                "cwe_ids": ["89"],
                "type": "security",
                "confidence": "high"
            }
        ]
    }
    
    try:
        scanner = BearerScanner(project_key="test-parsing")
        bugs = scanner._convert_bearer_to_bugs_format(sample_bearer_data)
        
        logger.info(f"Parsed {len(bugs)} findings from sample data")
        
        for bug in bugs:
            logger.info(f"  - {bug['rule']} ({bug['severity']}) in {bug['component']}:{bug['line']}")
            logger.info(f"    Tags: {', '.join(bug['tags'])}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error during JSON parsing test: {e}")
        return False

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Bearer Scanner Test Suite")
    logger.info("=" * 60)
    
    # Test JSON parsing first
    logger.info("\n1. Testing Bearer JSON parsing...")
    parsing_success = test_bearer_json_parsing()
    
    # Test actual scanner
    logger.info("\n2. Testing Bearer scanner...")
    scanner_success = test_bearer_scanner()
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Test Results Summary:")
    logger.info(f"  JSON Parsing Test: {'PASSED' if parsing_success else 'FAILED'}")
    logger.info(f"  Scanner Test: {'PASSED' if scanner_success else 'FAILED'}")
    logger.info("=" * 60)
    
    if parsing_success and scanner_success:
        logger.info("All tests PASSED! Bearer scanner is ready to use.")
    else:
        logger.warning("Some tests FAILED. Please check the logs above.")