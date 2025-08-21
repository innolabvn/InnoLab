#!/usr/bin/env python3
"""
Test script for RAG integration in batch_fix.py
"""

import os
import sys
import json
import tempfile
from pathlib import Path

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from batch_fix import SecureFixProcessor, FixResult
from dotenv import load_dotenv

def create_test_file():
    """Create a test Python file with some issues"""
    test_code = '''
# Test file with some issues
import os
import sys

def test_function():
    # Unused variable
    unused_var = "hello"
    
    # Missing return statement
    if True:
        print("test")
    
    # Potential security issue
    eval("print('hello')")

if __name__ == "__main__":
    test_function()
'''
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(test_code)
        return f.name

def create_test_issues():
    """Create test issues data"""
    return [
        {
            "key": "test:unused_variable",
            "component": "test.py",
            "line": 8,
            "message": "Remove this unused local variable 'unused_var'.",
            "severity": "MINOR",
            "type": "CODE_SMELL",
            "status": "OPEN"
        },
        {
            "key": "test:eval_usage",
            "component": "test.py", 
            "line": 14,
            "message": "Make sure that this use of 'eval' is safe here.",
            "severity": "CRITICAL",
            "type": "VULNERABILITY",
            "status": "OPEN"
        }
    ]

def test_rag_integration():
    """Test RAG integration functionality"""
    print("Testing RAG Integration...")
    
    # Load environment
    load_dotenv()
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ Error: GEMINI_API_KEY not found in .env file")
        return False
    
    # Create test file
    test_file = create_test_file()
    print(f"📁 Created test file: {test_file}")
    
    try:
        # Create processor
        processor = SecureFixProcessor(api_key, os.path.dirname(test_file))
        
        # Create test issues
        test_issues = create_test_issues()
        
        # Test add_bug_to_rag function directly
        print("\n🧪 Testing add_bug_to_rag function...")
        
        # Create a mock FixResult
        fix_result = FixResult(
            success=True,
            file_path=test_file,
            original_size=100,
            fixed_size=95,
            issues_found=["Fixed unused variable", "Removed eval usage"],
            validation_errors=[],
            processing_time=2.5,
            similarity_ratio=0.92,
            input_tokens=150,
            output_tokens=80,
            total_tokens=230,
            meets_threshold=True
        )
        
        # Test RAG integration
        rag_success = processor.add_bug_to_rag(
            fix_result=fix_result,
            issues_data=test_issues,
            raw_response="Mock AI response for testing",
            fixed_code="# Fixed code content\nprint('Hello, World!')"
        )
        
        if rag_success:
            print("✅ RAG integration test passed!")
            return True
        else:
            print("❌ RAG integration test failed!")
            return False
            
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")
        return False
    finally:
        # Clean up
        if os.path.exists(test_file):
            os.unlink(test_file)
            print(f"🗑️ Cleaned up test file: {test_file}")

if __name__ == "__main__":
    print("RAG Integration Test")
    print("=" * 50)
    
    success = test_rag_integration()
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 All tests passed!")
        sys.exit(0)
    else:
        print("💥 Tests failed!")
        sys.exit(1)