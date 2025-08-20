#!/usr/bin/env python3
"""
Enhanced Batch Fix Script with Best Practices
- Validation & Quality Gates
- Backup & Rollback
- Comprehensive Error Handling
- Security & Safety Checks
"""

import google.generativeai as genai
import os
import sys
import glob
import json
import ast
import shutil
import hashlib
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import tempfile

@dataclass
class FixResult:
    success: bool
    file_path: str
    original_size: int
    fixed_size: int
    issues_found: List[str]
    validation_errors: List[str]
    backup_path: Optional[str] = None
    processing_time: float = 0.0

class CodeValidator:
    """Validate code quality and syntax"""
    
    @staticmethod
    def validate_python_syntax(code: str) -> Tuple[bool, List[str]]:
        """Validate Python syntax"""
        errors = []
        try:
            ast.parse(code)
            return True, errors
        except SyntaxError as e:
            errors.append(f"Syntax Error: {e.msg} at line {e.lineno}")
            return False, errors
        except Exception as e:
            errors.append(f"Parse Error: {str(e)}")
            return False, errors
    
    @staticmethod
    def validate_javascript_syntax(code: str) -> Tuple[bool, List[str]]:
        """Basic JavaScript validation using Node.js if available"""
        errors = []
        try:
            # Create temp file and try to parse with Node.js
            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                f.write(code)
                f.flush()
                
                result = subprocess.run(
                    ['node', '--check', f.name], 
                    capture_output=True, 
                    text=True,
                    timeout=10
                )
                
                os.unlink(f.name)
                
                if result.returncode != 0:
                    errors.append(f"JS Syntax Error: {result.stderr}")
                    return False, errors
                
                return True, errors
                
        except subprocess.TimeoutExpired:
            errors.append("Validation timeout")
            return False, errors
        except FileNotFoundError:
            # Node.js not available, skip validation
            return True, ["Node.js not available for validation"]
        except Exception as e:
            errors.append(f"Validation error: {str(e)}")
            return False, errors
    
    @staticmethod
    def check_code_quality(original: str, fixed: str) -> Dict[str, any]:
        """Compare code quality metrics"""
        return {
            'size_change': len(fixed) - len(original),
            'line_change': len(fixed.split('\n')) - len(original.split('\n')),
            'similarity_ratio': CodeValidator._similarity_ratio(original, fixed)
        }
    
    @staticmethod
    def _similarity_ratio(str1: str, str2: str) -> float:
        """Calculate similarity ratio between two strings"""
        from difflib import SequenceMatcher
        return SequenceMatcher(None, str1, str2).ratio()

class SecureFixProcessor:
    """Enhanced fix processor with security and validation"""
    
    def __init__(self, api_key: str, backup_dir: str = None):
        self.model = self._setup_gemini(api_key)
        self.backup_dir = backup_dir or "./backups"
        self.validator = CodeValidator()
        self._create_backup_dir()
    
    def _setup_gemini(self, api_key: str):
        """Setup Gemini with proper configuration"""
        genai.configure(api_key=api_key)
        
        # Configure safety settings
        safety_settings = [
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            }
        ]
        
        return genai.GenerativeModel(
            'gemini-1.5-flash',
            safety_settings=safety_settings
        )
    
    def _create_backup_dir(self):
        """Create backup directory with timestamp"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.backup_dir = os.path.join(self.backup_dir, f"backup_{timestamp}")
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def _create_backup(self, file_path: str) -> str:
        """Create backup of original file"""
        backup_path = os.path.join(self.backup_dir, os.path.basename(file_path))
        shutil.copy2(file_path, backup_path)
        return backup_path
    
    def _validate_fix_safety(self, original: str, fixed: str) -> Tuple[bool, List[str]]:
        """Validate that the fix is safe and reasonable"""
        issues = []
        
        # Check for suspicious changes
        similarity = self.validator._similarity_ratio(original, fixed)
        if similarity < 0.3:
            issues.append(f"Code changed too drastically (similarity: {similarity:.2f})")
        
        # Check for potential malicious code patterns
        suspicious_patterns = [
            'eval(', 'exec(', 'os.system', 'subprocess.call',
            'import os', 'import subprocess', '__import__',
            'file://', 'http://', 'https://'
        ]
        
        for pattern in suspicious_patterns:
            if pattern in fixed.lower() and pattern not in original.lower():
                issues.append(f"Suspicious pattern added: {pattern}")
        
        return len(issues) == 0, issues
    
    def fix_file_with_validation(self, file_path: str, template_type: str = 'fix', 
                                custom_prompt: str = None, max_retries: int = 2) -> FixResult:
        """Fix file with comprehensive validation"""
        start_time = datetime.now()
        
        try:
            # Read original file
            with open(file_path, 'r', encoding='utf-8') as f:
                original_code = f.read()
            
            # Create backup
            backup_path = self._create_backup(file_path)
            
            # Attempt fix with retries
            fixed_code = None
            validation_errors = []
            
            for attempt in range(max_retries + 1):
                try:
                    # Load and render prompt template
                    template, template_vars = self._load_prompt_template(template_type, custom_prompt)
                    prompt = template.render(
                        original_code=original_code, 
                        **template_vars,
                        validation_rules=self._get_validation_rules(file_path)
                    )
                    
                    # Generate fix
                    response = self.model.generate_content(prompt)
                    candidate_fixed = self._clean_response(response.text)
                    
                    # Validate syntax
                    file_ext = Path(file_path).suffix.lower()
                    if file_ext == '.py':
                        is_valid, syntax_errors = self.validator.validate_python_syntax(candidate_fixed)
                    elif file_ext in ['.js', '.jsx']:
                        is_valid, syntax_errors = self.validator.validate_javascript_syntax(candidate_fixed)
                    else:
                        is_valid, syntax_errors = True, []  # Skip validation for other types
                    
                    if not is_valid:
                        validation_errors.extend(syntax_errors)
                        if attempt < max_retries:
                            print(f"  Retry {attempt + 1}: Syntax errors found, retrying...")
                            continue
                        else:
                            raise Exception(f"Syntax validation failed: {'; '.join(syntax_errors)}")
                    
                    # Validate safety
                    is_safe, safety_issues = self._validate_fix_safety(original_code, candidate_fixed)
                    if not is_safe:
                        validation_errors.extend(safety_issues)
                        if attempt < max_retries:
                            print(f"  Retry {attempt + 1}: Safety issues found, retrying...")
                            continue
                        else:
                            raise Exception(f"Safety validation failed: {'; '.join(safety_issues)}")
                    
                    # If we get here, the fix is valid
                    fixed_code = candidate_fixed
                    break
                    
                except Exception as e:
                    if attempt < max_retries:
                        print(f"  Retry {attempt + 1}: {str(e)}")
                        continue
                    else:
                        raise e
            
            # Calculate metrics
            processing_time = (datetime.now() - start_time).total_seconds()
            quality_metrics = self.validator.check_code_quality(original_code, fixed_code)
            
            return FixResult(
                success=True,
                file_path=file_path,
                original_size=len(original_code),
                fixed_size=len(fixed_code),
                issues_found=[f"Size change: {quality_metrics['size_change']} bytes"],
                validation_errors=validation_errors,
                backup_path=backup_path,
                processing_time=processing_time
            )
            
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            return FixResult(
                success=False,
                file_path=file_path,
                original_size=len(original_code) if 'original_code' in locals() else 0,
                fixed_size=0,
                issues_found=[str(e)],
                validation_errors=validation_errors,
                processing_time=processing_time
            )
    
    def _get_validation_rules(self, file_path: str) -> str:
        """Get validation rules based on file type"""
        file_ext = Path(file_path).suffix.lower()
        rules = {
            '.py': "- Must be valid Python syntax\n- Follow PEP 8 guidelines\n- No dangerous imports",
            '.js': "- Must be valid JavaScript syntax\n- Use modern ES6+ features\n- No eval() usage",
            '.jsx': "- Must be valid React JSX syntax\n- Follow React best practices"
        }
        return rules.get(file_ext, "- Maintain original functionality\n- Fix syntax errors only")
    
    def _load_prompt_template(self, template_type: str, custom_prompt: str = None):
        """Load prompt template (simplified version)"""
        if custom_prompt:
            template_content = f"""
Fix the following code according to this instruction: {custom_prompt}

Validation Rules:
{{{{ validation_rules }}}}

Original Code:
{{{{ original_code }}}}

Return only the fixed code without markdown formatting.
"""
        else:
            template_content = """
Fix the following code by:
1. Correcting syntax errors
2. Improving code quality and readability  
3. Following best practices
4. Maintaining original functionality

Validation Rules:
{{ validation_rules }}

Original Code:
{{ original_code }}

Return only the fixed code without markdown formatting.
"""
        
        # Simple template implementation
        class SimpleTemplate:
            def __init__(self, content):
                self.content = content
            def render(self, **kwargs):
                result = self.content
                for key, value in kwargs.items():
                    result = result.replace(f'{{{{ {key} }}}}', str(value))
                return result
        
        return SimpleTemplate(template_content), {}
    
    def _clean_response(self, response_text: str) -> str:
        """Clean LLM response to extract code"""
        text = response_text.strip()
        
        # Remove common markdown code blocks
        if text.startswith('```'):
            lines = text.split('\n')
            # Find first and last code block markers
            start_idx = 0
            end_idx = len(lines)
            
            for i, line in enumerate(lines):
                if line.startswith('```') and i == 0:
                    start_idx = 1
                elif line.strip() == '```' and i > 0:
                    end_idx = i
                    break
            
            text = '\n'.join(lines[start_idx:end_idx])
        
        return text.strip()

def main():
    print("🛡️ Enhanced Secure Batch Fix Script")
    print("Advanced AI-powered code fixing with validation & safety checks")
    print("=" * 70)
    
    # Setup
    load_dotenv()
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ Error: GEMINI_API_KEY not found in .env file")
        sys.exit(1)
    
    # Get directory
    if len(sys.argv) >= 2:
        directory = sys.argv[1]
    else:
        directory = input("📁 Enter directory path: ").strip()
    
    if not directory or not os.path.isdir(directory):
        print(f"❌ Invalid directory: {directory}")
        return
    
    # Get code files
    code_extensions = ['.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c']
    code_files = []
    
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if not d.startswith('.') and 
                  d not in ['node_modules', '__pycache__', 'build', 'dist']]
        
        for file in files:
            if any(file.lower().endswith(ext) for ext in code_extensions):
                code_files.append(os.path.join(root, file))
    
    if not code_files:
        print(f"❌ No code files found in: {directory}")
        return
    
    print(f"\n📊 Scan Results:")
    print(f"📁 Directory: {directory}")
    print(f"📄 Found {len(code_files)} code files")
    
    # Show previewg
    print("\n📋 Files to process:")
    for i, file_path in enumerate(code_files[:10], 1):
        relative_path = os.path.relpath(file_path, directory)
        print(f"  {i:2d}. {relative_path}")
    
    if len(code_files) > 10:
        print(f"  ... and {len(code_files) - 10} more files")
    
    # Confirm
    confirm = input(f"\n⚠️ Process {len(code_files)} files with validation? (y/N): ").strip().lower()
    if confirm not in ['y', 'yes']:
        print("❌ Cancelled")
        return
    
    print("\n" + "=" * 70)
    print("🚀 Starting secure processing...")
    
    # Process files
    processor = SecureFixProcessor(api_key)
    results = []
    
    for i, file_path in enumerate(code_files, 1):
        relative_path = os.path.relpath(file_path, directory)
        print(f"\n[{i}/{len(code_files)}] 🔧 Processing: {relative_path}")
        
        result = processor.fix_file_with_validation(file_path)
        results.append(result)
        
        if result.success:
            print(f"  ✅ Success ({result.processing_time:.1f}s)")
            if result.issues_found:
                print(f"  📝 Changes: {'; '.join(result.issues_found)}")
        else:
            print(f"  ❌ Failed: {'; '.join(result.issues_found)}")
    
    # Summary
    success_count = sum(1 for r in results if r.success)
    error_count = len(results) - success_count
    
    print("\n" + "=" * 70)
    print("🎉 Processing Complete!")
    print(f"✅ Successful: {success_count} files")
    print(f"❌ Failed: {error_count} files")
    print(f"📁 Backups saved in: {processor.backup_dir}")
    
    if success_count > 0:
        avg_time = sum(r.processing_time for r in results) / len(results)
        print(f"⏱️ Average processing time: {avg_time:.1f}s per file")
        print("\n💡 Recommendation: Review changes and run tests before deploying!")

if __name__ == "__main__":
    main()