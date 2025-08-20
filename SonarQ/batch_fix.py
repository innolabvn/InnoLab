#!/usr/bin/env python3
"""
Enhanced Batch Fix Script with Best Practices - CORRECTED VERSION
- Fixed infinite directory creation loop
- Improved backup and output directory handling
- Better path normalization and validation
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
import argparse
from pathlib import Path
import logging
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import tempfile
import fnmatch

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
    def validate_html_syntax(code: str) -> Tuple[bool, List[str]]:
        """Basic HTML validation"""
        errors = []
        try:
            # Basic HTML structure checks
            if '<html' in code.lower() and '</html>' not in code.lower():
                errors.append("Missing closing </html> tag")
            if '<head' in code.lower() and '</head>' not in code.lower():
                errors.append("Missing closing </head> tag")
            if '<body' in code.lower() and '</body>' not in code.lower():
                errors.append("Missing closing </body> tag")
            
            # Check for basic tag matching
            import re
            open_tags = re.findall(r'<([a-zA-Z][^>]*)>', code)
            close_tags = re.findall(r'</([a-zA-Z][^>]*)>', code)
            
            return len(errors) == 0, errors
        except Exception as e:
            errors.append(f"HTML validation error: {str(e)}")
            return False, errors
    
    @staticmethod
    def validate_css_syntax(code: str) -> Tuple[bool, List[str]]:
        """Basic CSS validation"""
        errors = []
        try:
            # Basic CSS structure checks
            open_braces = code.count('{')
            close_braces = code.count('}')
            if open_braces != close_braces:
                errors.append(f"Mismatched braces: {open_braces} open, {close_braces} close")
            
            # Check for basic CSS syntax
            lines = code.split('\n')
            for i, line in enumerate(lines, 1):
                line = line.strip()
                if line and not line.startswith('/*') and not line.endswith('*/') and ':' in line and not line.endswith(';') and not line.endswith('{') and not line.endswith('}'):
                    if not any(char in line for char in ['{', '}', '@']):
                        errors.append(f"Line {i}: Missing semicolon")
            
            return len(errors) == 0, errors
        except Exception as e:
            errors.append(f"CSS validation error: {str(e)}")
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
    
    def __init__(self, api_key: str, source_dir: str, backup_dir: str = None, output_dir: str = None):
        self.model = self._setup_gemini(api_key)
        self.source_dir = os.path.abspath(source_dir)  # Store absolute path of source directory
        self.validator = CodeValidator()
        self.output_dir = os.path.abspath(output_dir) if output_dir else None
        self.ignore_patterns = []
        
        # Create unique backup directory with timestamp
        if backup_dir:
            self.backup_dir = os.path.abspath(backup_dir)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.backup_dir = os.path.abspath(f"./backups/backup_{timestamp}")
        
        self._create_backup_dir()
        self._setup_logging()
    
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
            'gemini-2.0-flash',
            safety_settings=safety_settings
        )
    
    def _create_backup_dir(self):
        """Create backup directory"""
        os.makedirs(self.backup_dir, exist_ok=True)
        print(f"Backup directory: {self.backup_dir}")
    
    def _setup_logging(self):
        """Setup logging for template usage tracking"""
        log_dir = "./logs"
        os.makedirs(log_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"template_usage_{timestamp}.log")
        
        # Create a separate logger for template usage
        self.template_logger = logging.getLogger('template_usage')
        self.template_logger.setLevel(logging.INFO)
        
        # Remove existing handlers to avoid duplicates
        for handler in self.template_logger.handlers[:]:
            self.template_logger.removeHandler(handler)
        
        # Create file handler
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        # Add handler to logger
        self.template_logger.addHandler(file_handler)
        
        print(f"Template usage logging enabled: {log_file}")
    
    def load_ignore_patterns(self, base_dir: str):
        """Load ignore patterns from .fixignore file"""
        fixignore_path = os.path.join(base_dir, '.fixignore')
        self.ignore_patterns = []
        
        # Default ignore patterns
        default_patterns = [
            '*.pyc', '__pycache__/', '*.pyo', '*.pyd',
            '.git/', '.svn/', '.hg/', '.bzr/',
            'node_modules/', '.npm/', '.yarn/',
            '.env', '.env.*', '*.log', '*.tmp',
            '.DS_Store', 'Thumbs.db',
            '*.min.js', '*.min.css',
            'dist/', 'build/', 'target/',
            '.idea/', '.vscode/', '*.swp', '*.swo',
            'backups/', 'logs/', 'fixed/'  # Add common output directories to ignore
        ]
        self.ignore_patterns.extend(default_patterns)
        
        # Load custom patterns from .fixignore
        if os.path.exists(fixignore_path):
            try:
                with open(fixignore_path, 'r', encoding='utf-8') as f:
                    custom_count = 0
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            self.ignore_patterns.append(line)
                            custom_count += 1
                print(f"Loaded {custom_count} custom ignore patterns from .fixignore")
            except Exception as e:
                print(f"Warning: Could not read .fixignore file: {e}")
    
    def should_ignore_file(self, file_path: str, base_dir: str) -> bool:
        """Check if file should be ignored based on patterns"""
        try:
            # Get absolute paths to avoid path issues
            abs_file_path = os.path.abspath(file_path)
            abs_base_dir = os.path.abspath(base_dir)
            
            # Skip if file is outside the base directory
            if not abs_file_path.startswith(abs_base_dir):
                return True
            
            # Skip if file is in backup or output directory to prevent loops
            if self.backup_dir and abs_file_path.startswith(self.backup_dir):
                return True
            if self.output_dir and abs_file_path.startswith(self.output_dir):
                return True
            
            # Get relative path from base directory
            rel_path = os.path.relpath(abs_file_path, abs_base_dir)
            # Normalize path separators for cross-platform compatibility
            rel_path = rel_path.replace('\\', '/')
            
            for pattern in self.ignore_patterns:
                # Handle directory patterns
                if pattern.endswith('/'):
                    if rel_path.startswith(pattern) or f'/{pattern}' in f'/{rel_path}/':
                        return True
                # Handle file patterns
                elif fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(os.path.basename(file_path), pattern):
                    return True
            
            return False
        except Exception as e:
            print(f"Warning: Error checking ignore patterns for {file_path}: {e}")
            return False
    
    def _create_backup(self, file_path: str) -> str:
        """Create backup of original file"""
        # Create a unique backup filename to avoid collisions
        filename = os.path.basename(file_path)
        backup_filename = f"{filename}.backup"
        backup_path = os.path.join(self.backup_dir, backup_filename)
        
        # Handle filename collisions by adding counter
        counter = 1
        while os.path.exists(backup_path):
            name, ext = os.path.splitext(filename)
            backup_filename = f"{name}_{counter}{ext}.backup"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            counter += 1
        
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
    
    def scan_file_only(self, file_path: str) -> FixResult:
        """Scan file for issues without fixing"""
        start_time = datetime.now()
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                original_code = f.read()
            
            # Basic analysis
            file_ext = Path(file_path).suffix.lower()
            issues_found = []
            
            # Check file size
            file_size = len(original_code)
            if file_size > 10000:
                issues_found.append("Large file (>10KB)")
            
            # Basic syntax check
            if file_ext == '.py':
                is_valid, syntax_errors = self.validator.validate_python_syntax(original_code)
                if not is_valid:
                    issues_found.extend([f"Python: {err}" for err in syntax_errors])
            elif file_ext in ['.js', '.jsx']:
                is_valid, syntax_errors = self.validator.validate_javascript_syntax(original_code)
                if not is_valid:
                    issues_found.extend([f"JS: {err}" for err in syntax_errors])
            elif file_ext == '.html':
                is_valid, syntax_errors = self.validator.validate_html_syntax(original_code)
                if not is_valid:
                    issues_found.extend([f"HTML: {err}" for err in syntax_errors])
            elif file_ext == '.css':
                is_valid, syntax_errors = self.validator.validate_css_syntax(original_code)
                if not is_valid:
                    issues_found.extend([f"CSS: {err}" for err in syntax_errors])
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            return FixResult(
                success=True,
                file_path=file_path,
                original_size=file_size,
                fixed_size=file_size,
                issues_found=issues_found if issues_found else ["No issues found"],
                validation_errors=[]
            )
            
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            return FixResult(
                success=False,
                file_path=file_path,
                original_size=0,
                fixed_size=0,
                issues_found=[f"Scan error: {str(e)}"],
                validation_errors=[]
            )
    
    def fix_file_with_validation(self, file_path: str, template_type: str = 'fix', 
                                 custom_prompt: str = None, max_retries: int = 2, 
                                 issues_data: List[Dict] = None) -> FixResult:
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
                    # Prepare issues log
                    if issues_data:
                        issues_log = json.dumps(issues_data, indent=2, ensure_ascii=False)
                    else:
                        issues_log = "No specific issues reported. Please analyze the code for potential bugs, code smells, and vulnerabilities."
                    
                    # Load and render prompt template
                    template, template_vars = self._load_prompt_template(template_type, custom_prompt)
                    prompt = template.render(
                        original_code=original_code, 
                        **template_vars,
                        validation_rules=self._get_validation_rules(file_path),
                        issues_log=issues_log
                    )
                    
                    # Log template usage
                    self._log_template_usage(file_path, template_type, custom_prompt, prompt)
                    
                    # Generate fix
                    response = self.model.generate_content(prompt)
                    candidate_fixed = self._clean_response(response.text)
                    
                    # Log AI response
                    self._log_ai_response(file_path, response.text, candidate_fixed)
                    
                    # Validate syntax
                    file_ext = Path(file_path).suffix.lower()
                    if file_ext == '.py':
                        is_valid, syntax_errors = self.validator.validate_python_syntax(candidate_fixed)
                    elif file_ext in ['.js', '.jsx']:
                        is_valid, syntax_errors = self.validator.validate_javascript_syntax(candidate_fixed)
                    elif file_ext == '.html':
                        is_valid, syntax_errors = self.validator.validate_html_syntax(candidate_fixed)
                    elif file_ext == '.css':
                        is_valid, syntax_errors = self.validator.validate_css_syntax(candidate_fixed)
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
            
            # Save fixed file
            output_path = self._save_fixed_file(file_path, fixed_code)
            
            # Calculate metrics
            processing_time = (datetime.now() - start_time).total_seconds()
            quality_metrics = self.validator.check_code_quality(original_code, fixed_code)
            
            return FixResult(
                success=True,
                file_path=output_path,
                original_size=len(original_code),
                fixed_size=len(fixed_code),
                issues_found=[f"Size change: {quality_metrics['size_change']} bytes", f"Similarity: {quality_metrics['similarity_ratio']:.1%}"],
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
            '.jsx': "- Must be valid React JSX syntax\n- Follow React best practices",
            '.html': "- Must be valid HTML5 syntax\n- Proper tag nesting and closing\n- Use semantic HTML elements",
            '.css': "- Must be valid CSS syntax\n- Proper selector formatting\n- No missing semicolons or braces",
            '.txt': "- Maintain text formatting\n- Fix spelling and grammar\n- Preserve original structure"
        }
        return rules.get(file_ext, "- Maintain original functionality\n- Fix syntax errors only")
    
    def _load_prompt_template(self, template_type: str, custom_prompt: str = None):
        """Load prompt template from files or use custom prompt"""
        try:
            # Setup Jinja2 environment for template loading
            prompt_dir = os.path.join(os.path.dirname(__file__), 'prompt')
            
            if os.path.exists(prompt_dir):
                env = Environment(loader=FileSystemLoader(prompt_dir))
                
                # Map template types to files
                template_files = {
                    'fix': 'fix.j2',
                    'analyze': 'analyze.j2',
                    'custom': 'custom.j2'
                }
                
                if custom_prompt:
                    # Use custom template with custom prompt
                    template_file = template_files.get('custom', 'custom.j2')
                    if os.path.exists(os.path.join(prompt_dir, template_file)):
                        template = env.get_template(template_file)
                        return template, {'custom_prompt': custom_prompt}
                    else:
                        # Fallback to inline custom template
                        template_content = f"""
{custom_prompt}

Code cần sửa:
{{{{ original_code }}}}

Chỉ trả về code đã sửa, không cần markdown formatting hay giải thích.
"""
                else:
                    # Use template file based on type
                    template_file = template_files.get(template_type, 'fix.j2')
                    if os.path.exists(os.path.join(prompt_dir, template_file)):
                        template = env.get_template(template_file)
                        return template, {}
                    else:
                        # Fallback to default fix template
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
            else:
                # Prompt directory doesn't exist, use fallback
                if custom_prompt:
                    template_content = f"""
{custom_prompt}

Code cần sửa:
{{{{ original_code }}}}

Chỉ trả về code đã sửa, không cần markdown formatting hay giải thích.
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
        
        except Exception as e:
            print(f"Warning: Could not load template from prompt directory: {e}")
            # Fallback to simple template
            if custom_prompt:
                template_content = f"""
{custom_prompt}

Code cần sửa:
{{{{ original_code }}}}

Chỉ trả về code đã sửa, không cần markdown formatting hay giải thích.
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
        
        # Simple template implementation as fallback
        class SimpleTemplate:
            def __init__(self, content):
                self.content = content
            def render(self, **kwargs):
                result = self.content
                for key, value in kwargs.items():
                    result = result.replace(f'{{{{ {key} }}}}', str(value))
                return result
        
        return SimpleTemplate(template_content), {}
    
    def _log_template_usage(self, file_path: str, template_type: str, custom_prompt: str, rendered_prompt: str):
        """Log template usage for analysis"""
        try:
            log_data = {
                'file_path': file_path,
                'template_type': template_type,
                'custom_prompt': custom_prompt,
                'prompt_length': len(rendered_prompt),
                'prompt_preview': rendered_prompt[:200] + '...' if len(rendered_prompt) > 200 else rendered_prompt
            }
            
            self.template_logger.info(f"TEMPLATE_USAGE: {json.dumps(log_data, ensure_ascii=False)}")
        except Exception as e:
            print(f"Warning: Could not log template usage: {e}")
    
    def _log_ai_response(self, file_path: str, raw_response: str, cleaned_response: str):
        """Log AI response for analysis"""
        try:
            log_data = {
                'file_path': file_path,
                'raw_response_length': len(raw_response),
                'cleaned_response_length': len(cleaned_response),
                'response_preview': cleaned_response[:200] + '...' if len(cleaned_response) > 200 else cleaned_response
            }
            
            self.template_logger.info(f"AI_RESPONSE: {json.dumps(log_data, ensure_ascii=False)}")
        except Exception as e:
            print(f"Warning: Could not log AI response: {e}")
    
    def load_issues_from_file(self, issues_file_path: str) -> Dict[str, List[Dict]]:
        """Load issues from JSON file and organize by file path"""
        issues_by_file = {}
        try:
            with open(issues_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            issues = data.get('issues', [])
            print(f"Loaded {len(issues)} issues from {issues_file_path}")
            
            for issue in issues:
                file_path = issue.get('file_path', '')
                if file_path:
                    # Normalize file path
                    file_path = os.path.normpath(file_path)
                    if file_path not in issues_by_file:
                        issues_by_file[file_path] = []
                    issues_by_file[file_path].append(issue)
            
            print(f"Issues found in {len(issues_by_file)} files")
            return issues_by_file
            
        except Exception as e:
            print(f"Warning: Could not load issues file: {e}")
            return {}
    
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
    
    def _save_fixed_file(self, original_path: str, fixed_content: str) -> str:
        """Save fixed file to appropriate location"""
        if self.output_dir:
            # Calculate relative path from source directory
            rel_path = os.path.relpath(original_path, self.source_dir)
            output_path = os.path.join(self.output_dir, rel_path)
            
            # Create output directory structure
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Write fixed content
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(fixed_content)
            
            return output_path
        else:
            # Overwrite original file
            with open(original_path, 'w', encoding='utf-8') as f:
                f.write(fixed_content)
            return original_path
    
    def copy_non_fixed_files(self, processed_files: set):
        """Copy all non-fixed files to output directory maintaining structure"""
        if not self.output_dir:
            return
        
        print(f"\nCopying non-fixed files to {self.output_dir}...")
        copied_count = 0
        skipped_count = 0
        
        for root, dirs, files in os.walk(self.source_dir):
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if not self.should_ignore_file(os.path.join(root, d), self.source_dir)]
            
            for file in files:
                file_path = os.path.join(root, file)
                
                # Skip if file should be ignored
                if self.should_ignore_file(file_path, self.source_dir):
                    skipped_count += 1
                    continue
                
                # Skip if file was already processed (fixed)
                if file_path in processed_files:
                    continue
                
                try:
                    # Calculate relative path and output path
                    relative_path = os.path.relpath(file_path, self.source_dir)
                    output_path = os.path.join(self.output_dir, relative_path)
                    
                    # Create output directory structure
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    
                    # Copy file
                    shutil.copy2(file_path, output_path)
                    copied_count += 1
                    
                except Exception as e:
                    print(f"Warning: Could not copy {file_path}: {e}")
        
        print(f"Copied {copied_count} non-fixed files, skipped {skipped_count} ignored files")

def main():
    parser = argparse.ArgumentParser(description='Enhanced Secure Batch Fix Script - AI-powered code fixing with validation & safety checks')
    parser.add_argument('destination', nargs='?', help='Directory path to scan and fix')
    parser.add_argument('--fix', action='store_true', help='Enable fixing mode (default: scan only)')
    parser.add_argument('--scan-only', action='store_true', help='Scan only mode, no fixing')
    parser.add_argument('--prompt', type=str, help='Custom prompt for AI fixing')
    parser.add_argument('--output', type=str, help='Output directory for fixed files')
    parser.add_argument('--copy-all', action='store_true', help='Copy all files to output directory (including non-fixed files)')
    parser.add_argument('--auto', action='store_true', help='Auto mode: skip confirmation prompts')
    parser.add_argument('--issues-file', type=str, help='JSON file containing issues from SonarQube or other tools')
    
    args = parser.parse_args()
    
    print("Enhanced Secure Batch Fix Script")
    print("Advanced AI-powered code fixing with validation & safety checks")
    print("=" * 70)
    
    # Setup
    load_dotenv()
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("Error: GEMINI_API_KEY not found in .env file")
        sys.exit(1)
    
    # Get directory
    if args.destination:
        directory = args.destination
    else:
        print("\nUsage Examples:")
        print("  python batch_fix.py source_bug --scan-only                    # Scan only")
        print("  python batch_fix.py source_bug --fix                          # Scan and fix")
        print("  python batch_fix.py source_bug --fix --auto                   # Fix without confirmation")
        print("  python batch_fix.py source_bug --fix --output fixed_code      # Fix and save to specific directory")
        print("  python batch_fix.py source_bug --fix --prompt \"Fix security issues\" # Fix with custom prompt")
        print("  python batch_fix.py source_bug --fix --copy-all --auto        # Fix and copy all files automatically")
        print("  python batch_fix.py /path/to/code --fix --auto                # Fix specific directory automatically")
        print("  python batch_fix.py source_bug --fix --issues-file issues.json # Fix using SonarQube issues")
        print("\nLogging:")
        print("  Template usage and AI responses are automatically logged to ./logs/template_usage_TIMESTAMP.log")
        print("  Log entries include template type, custom prompts, response quality metrics, and file paths")
        print("  Use these logs to analyze template effectiveness and AI response quality")
        print("\n")
        directory = input("Enter directory path: ").strip()
    
    if not directory or not os.path.isdir(directory):
        print(f"Invalid directory: {directory}")
        if not args.destination:
            print("\nUsage Examples:")
            print("  python batch_fix.py source_bug --scan-only")
            print("  python batch_fix.py source_bug --fix")
            print("  python batch_fix.py source_bug --fix --auto")
            print("  python batch_fix.py source_bug --fix --output fixed_code")
            print("  python batch_fix.py source_bug --fix --prompt \"Fix security issues\"")
            print("  python batch_fix.py source_bug --fix --copy-all --auto")
            print("  python batch_fix.py source_bug --fix --issues-file issues.json")
            print("\nLogging:")
            print("  Template usage and AI responses are logged to ./logs/template_usage_TIMESTAMP.log")
            print("  Logs include template type, prompts, response metrics, and processing details")
        return
    
    # Determine mode and output directory
    fix_mode = args.fix and not args.scan_only
    mode_text = "FIXING" if fix_mode else "SCANNING"
    print(f"\n{mode_text} Mode Enabled")
    
    # Setup output directory for fixed files
    output_dir = args.output
    if fix_mode and args.copy_all and not output_dir:
        # Default output directory for copy-all mode
        output_dir = os.path.join(directory, 'fixed')
    
    if fix_mode and output_dir:
        print(f"Output directory: {output_dir}")
        # Ensure output directory is different from source
        abs_source = os.path.abspath(directory)
        abs_output = os.path.abspath(output_dir)
        if abs_source == abs_output:
            print("Error: Output directory cannot be the same as source directory")
            return
    elif fix_mode:
        print("Fixing files in-place (overwriting originals)")
    
    # Custom prompt
    custom_prompt = args.prompt
    if custom_prompt:
        print(f"Using custom prompt: {custom_prompt[:50]}{'...' if len(custom_prompt) > 50 else ''}")
    
    # Load issues file if provided
    issues_by_file = {}
    if args.issues_file:
        if os.path.exists(args.issues_file):
            print(f"Loading issues from: {args.issues_file}")
            temp_processor = SecureFixProcessor(api_key, directory, backup_dir="temp", output_dir="temp")
            issues_by_file = temp_processor.load_issues_from_file(args.issues_file)
        else:
            print(f"Issues file not found: {args.issues_file}")
    
    # Get code files
    code_extensions = ['.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.html', '.css', '.txt']
    code_files = []
    
    # Create temporary processor to load ignore patterns
    temp_processor = SecureFixProcessor(api_key, directory, backup_dir="temp", output_dir="temp")
    temp_processor.load_ignore_patterns(os.getcwd())
    
    for root, dirs, files in os.walk(directory):
        # Filter out ignored directories
        dirs[:] = [d for d in dirs if not temp_processor.should_ignore_file(os.path.join(root, d), directory)]
        
        for file in files:
            file_path = os.path.join(root, file)
            # Skip ignored files
            if temp_processor.should_ignore_file(file_path, directory):
                continue
            if any(file.lower().endswith(ext) for ext in code_extensions):
                code_files.append(file_path)
    
    if not code_files:
        print(f"No code files found in: {directory}")
        return
    
    print(f"\nScan Results:")
    print(f"Directory: {directory}")
    print(f"Found {len(code_files)} code files")
    
    # Show preview
    print("\nFiles to process:")
    for i, file_path in enumerate(code_files[:10], 1):
        relative_path = os.path.relpath(file_path, directory)
        print(f"  {i:2d}. {relative_path}")
    
    if len(code_files) > 10:
        print(f"  ... and {len(code_files) - 10} more files")
    
    # Confirm (skip if auto mode)
    if not args.auto:
        action_text = "fix" if fix_mode else "scan"
        confirm = input(f"\n{action_text.title()} {len(code_files)} files? (y/N): ").strip().lower()
        if confirm not in ['y', 'yes']:
            print("Cancelled")
            return
    else:
        print("\nAuto mode: proceeding without confirmation")
    
    print("\n" + "=" * 70)
    if fix_mode:
        print("Starting secure fixing...")
    else:
        print("Starting file scanning...")
    
    # Process files
    processor = SecureFixProcessor(api_key, directory, output_dir=output_dir if fix_mode else None)
    processor.load_ignore_patterns(directory)
    results = []
    processed_files = set()  # Track processed files for copy-all feature
    
    for i, file_path in enumerate(code_files, 1):
        relative_path = os.path.relpath(file_path, directory)
        action_icon = "Fixing" if fix_mode else "Scanning"
        print(f"\n[{i}/{len(code_files)}] {action_icon}: {relative_path}")
        
        if fix_mode:
            # Get issues for this specific file
            relative_path_key = os.path.relpath(file_path, directory)
            file_issues = issues_by_file.get(relative_path_key, [])
            
            result = processor.fix_file_with_validation(
                file_path, 
                template_type='fix', 
                custom_prompt=custom_prompt,
                issues_data=file_issues
            )
        else:
            result = processor.scan_file_only(file_path)
        
        results.append(result)
        processed_files.add(file_path)  # Track processed file
        
        if result.success:
            if fix_mode:
                print(f"  Success ({result.processing_time:.1f}s)")
                if result.issues_found and result.issues_found != ["No issues found"]:
                    print(f"  Changes: {'; '.join(result.issues_found)}")
            else:
                print(f"  Scanned ({result.processing_time:.1f}s)")
                if result.issues_found and result.issues_found != ["No issues found"]:
                    print(f"  Issues: {'; '.join(result.issues_found)}")
                else:
                    print(f"  Clean: No issues found")
        else:
            print(f"  Failed: {'; '.join(result.issues_found)}")
    
    # Copy non-fixed files if --copy-all is enabled and in fix mode
    if fix_mode and args.copy_all and processor.output_dir:
        processor.copy_non_fixed_files(processed_files)
    
    # Summary
    success_count = sum(1 for r in results if r.success)
    error_count = len(results) - success_count
    
    print("\n" + "=" * 70)
    if fix_mode:
        print("Fixing Complete!")
        print(f"Fixed: {success_count} files")
        print(f"Failed: {error_count} files")
        print(f"Backups saved in: {processor.backup_dir}")
        if processor.output_dir:
            print(f"Fixed files saved in: {processor.output_dir}")
    else:
        print("Scanning Complete!")
        print(f"Scanned: {success_count} files")
        print(f"Failed: {error_count} files")
        
        # Count files with issues
        files_with_issues = sum(1 for r in results if r.success and r.issues_found != ["No issues found"])
        clean_files = success_count - files_with_issues
        print(f"Files with issues: {files_with_issues}")
        print(f"Clean files: {clean_files}")
    
    if results:
        avg_time = sum(r.processing_time for r in results) / len(results)
        print(f"Average processing time: {avg_time:.1f}s per file")
    
    if fix_mode:
        print("\nRecommendation: Review changes and run tests before deploying!")
    else:
        print("\nTip: Use --fix flag to automatically fix detected issues!")

if __name__ == "__main__":
    main()