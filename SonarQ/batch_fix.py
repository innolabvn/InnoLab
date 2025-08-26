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
import requests

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
    similarity_ratio: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    meets_threshold: bool = True

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
    """Enhanced secure processor with comprehensive validation"""
    
    def __init__(self, api_key: str, source_dir: str, backup_dir: str = None, similarity_threshold: float = 0.85):
        self.similarity_threshold = similarity_threshold  # Ngưỡng chấp nhận độ tương thích
        self.model = self._setup_gemini(api_key)
        self.source_dir = os.path.abspath(source_dir)  # Store absolute path of source directory
        self.validator = CodeValidator()
        self.ignore_patterns = []
        
        # Create unique backup directory with timestamp - DISABLED
        # if backup_dir:
        #     self.backup_dir = os.path.abspath(backup_dir)
        # else:
        #     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        #     self.backup_dir = os.path.abspath(f"./backups/backup_{timestamp}")
        
        # self._create_backup_dir()
        self.backup_dir = None
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
                                 issues_data: List[Dict] = None, enable_rag: bool = False) -> FixResult:
        """Fix file with comprehensive validation"""
        start_time = datetime.now()
        
        try:
            # Read original file
            with open(file_path, 'r', encoding='utf-8') as f:
                original_code = f.read()
            
            # Create backup - DISABLED
            # backup_path = self._create_backup(file_path)
            backup_path = None
            
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
                    if template is None:
                        raise Exception("Template not found. Please add template files to prompt directory.")
                    
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
                    
                    # Extract token usage from response
                    input_tokens = 0
                    output_tokens = 0
                    total_tokens = 0
                    
                    if hasattr(response, 'usage_metadata') and response.usage_metadata:
                        input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0)
                        output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0)
                        total_tokens = getattr(response.usage_metadata, 'total_token_count', 0)
                    
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
            similarity_ratio = quality_metrics['similarity_ratio']
            meets_threshold = similarity_ratio >= self.similarity_threshold
            
            # Create FixResult object
            fix_result = FixResult(
                success=True,
                file_path=output_path,
                original_size=len(original_code),
                fixed_size=len(fixed_code),
                issues_found=[f"Size change: {quality_metrics['size_change']} bytes", f"Similarity: {similarity_ratio:.1%}"],
                validation_errors=validation_errors,
                backup_path=backup_path,
                processing_time=processing_time,
                similarity_ratio=similarity_ratio,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                meets_threshold=meets_threshold
            )
            
            # Add bug fix information to RAG system if fix was successful and RAG is enabled
            if enable_rag:
                try:
                    self.add_bug_to_rag(
                        fix_result=fix_result,
                        issues_data=issues_data,
                        raw_response=response.text if 'response' in locals() else "",
                        fixed_code=fixed_code
                    )
                except Exception as rag_error:
                    print(f"  ⚠️ Warning: Failed to add to RAG system: {str(rag_error)}")
            
            return fix_result
            
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            return FixResult(
                success=False,
                file_path=file_path,
                original_size=len(original_code) if 'original_code' in locals() else 0,
                fixed_size=0,
                issues_found=[str(e)],
                validation_errors=validation_errors,
                processing_time=processing_time,
                similarity_ratio=0.0,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                meets_threshold=False
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
                        # Return None để người dùng bổ sung template
                        return None, {}
            else:
                # Return None để người dùng bổ sung template khi prompt directory không tồn tại
                return None, {}
        
        except Exception as e:
            print(f"Warning: Could not load template from prompt directory: {e}")
            # Break để người dùng bổ sung template khi có lỗi
            return None, {}
        
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
                'response_preview': cleaned_response[:200] + '...' if len(cleaned_response) > 200 else cleaned_response,
                'full_cleaned_response': cleaned_response  # Add full response for debugging
            }
            
            self.template_logger.info(f"AI_RESPONSE: {json.dumps(log_data, ensure_ascii=False)}")
        except Exception as e:
            print(f"Warning: Could not log AI response: {e}")
    
    def add_bug_to_rag(self, fix_result: FixResult, issues_data: List[Dict] = None, 
                       raw_response: str = "", fixed_code: str = "") -> bool:
        """Add fixed bug information to RAG system via API"""
        try:
            # Prepare bug context from issues_data
            bug_context = []
            fix_summary = []
            
            if issues_data:
                for issue in issues_data:
                    if issue.get('component', '').endswith(os.path.basename(fix_result.file_path)):
                        bug_context.append(f"Line {issue.get('line', 'N/A')}: {issue.get('message', 'No message')}")
                        fix_summary.append({
                            "title": issue.get('message', 'Bug fix'),
                            "why": f"Issue type: {issue.get('type', 'Unknown')}, Severity: {issue.get('severity', 'Unknown')}",
                            "change": "Applied AI-generated fix to resolve the issue"
                        })
            
            # Determine code language from file extension
            file_ext = Path(fix_result.file_path).suffix.lower()
            language_map = {
                '.py': 'python',
                '.js': 'javascript', 
                '.jsx': 'javascript',
                '.ts': 'typescript',
                '.tsx': 'typescript',
                '.java': 'java',
                '.cpp': 'cpp',
                '.c': 'c',
                '.html': 'html',
                '.css': 'css'
            }
            code_language = language_map.get(file_ext, 'text')
            
            # Build JSON payload according to the specified format
            payload = {
                "content": f"Bug: Fixed {len(fix_summary)} issues in {os.path.basename(fix_result.file_path)}",
                "metadata": {
                    "bug_title": f"Fixed issues in {os.path.basename(fix_result.file_path)}",
                    "bug_context": bug_context if bug_context else ["No specific bug context available"],
                    "fix_summary": fix_summary if fix_summary else [{
                        "title": "General code improvement",
                        "why": "Applied AI-generated fixes",
                        "change": "Code quality and bug fixes"
                    }],
                    "fixed_source_present": bool(fixed_code),
                    "code_language": code_language,
                    "code": fixed_code if fixed_code else "",
                    "file_path": fix_result.file_path,
                    "original_size": fix_result.original_size,
                    "fixed_size": fix_result.fixed_size,
                    "similarity_ratio": fix_result.similarity_ratio,
                    "input_tokens": fix_result.input_tokens,
                    "output_tokens": fix_result.output_tokens,
                    "total_tokens": fix_result.total_tokens,
                    "processing_time": fix_result.processing_time,
                    "meets_threshold": fix_result.meets_threshold,
                    "validation_errors": fix_result.validation_errors,
                    "issues_found": fix_result.issues_found,
                    "raw_ai_response": raw_response[:1000] if raw_response else ""  # Limit to 1000 chars
                }
            }
            
            # Send POST request to RAG API
            api_url = "http://192.168.5.11:8000/api/v1/rag/reasoning/add"
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            response = requests.post(api_url, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200 or response.status_code == 201:
                print(f"  ✅ Successfully added bug fix to RAG: {os.path.basename(fix_result.file_path)}")
                return True
            else:
                print(f"  ❌ Failed to add to RAG (HTTP {response.status_code}): {response.text[:200]}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"  ❌ RAG API request failed: {str(e)}")
            return False
        except Exception as e:
            print(f"  ❌ Error adding to RAG: {str(e)}")
            return False
    
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
        
        # First try to extract from "## 3. Fixed Source Code" section
        if "## 3. Fixed Source Code" in text:
            lines = text.split('\n')
            start_idx = None
            
            for i, line in enumerate(lines):
                if "## 3. Fixed Source Code" in line:
                    start_idx = i + 1
                    break
            
            if start_idx is not None:
                # Extract everything after the section header
                code_lines = lines[start_idx:]
                # Remove any leading empty lines
                while code_lines and not code_lines[0].strip():
                    code_lines.pop(0)
                
                # Remove markdown code blocks if present
                if code_lines and code_lines[0].startswith('```'):
                    code_lines.pop(0)  # Remove opening ```
                    # Remove closing ``` if present
                    while code_lines and code_lines[-1].strip() == '```':
                        code_lines.pop()
                
                # Join and return the code
                if code_lines:
                    return '\n'.join(code_lines).strip()
        
        # Fallback: Remove common markdown code blocks
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
        """Save fixed file directly to original location"""
        # Always overwrite original file
        with open(original_path, 'w', encoding='utf-8') as f:
            f.write(fixed_content)
        return original_path
    


def main():
    parser = argparse.ArgumentParser(description='Enhanced Secure Batch Fix Script - AI-powered code fixing with validation & safety checks')
    parser.add_argument('destination', nargs='?', help='Directory path to scan and fix')
    parser.add_argument('--fix', action='store_true', help='Enable fixing mode (default: scan only)')
    parser.add_argument('--scan-only', action='store_true', help='Scan only mode, no fixing')
    parser.add_argument('--prompt', type=str, help='Custom prompt for AI fixing')


    parser.add_argument('--auto', action='store_true', help='Auto mode: skip confirmation prompts')
    parser.add_argument('--issues-file', type=str, help='JSON file containing issues from SonarQube or other tools')
    parser.add_argument('--enable-rag', action='store_true', help='Enable RAG integration to store fixed bugs information')
    
    args = parser.parse_args()
    
    print("Enhanced Secure Batch Fix Script")
    print("Advanced AI-powered code fixing with validation & safety checks")
    print("=" * 70)
    
    # Setup - Load environment variables from root directory
    root_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    load_dotenv(root_env_path)
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

        print("  python batch_fix.py source_bug --fix --prompt \"Fix security issues\" # Fix with custom prompt")

        print("  python batch_fix.py /path/to/code --fix --auto                # Fix specific directory automatically")
        print("  python batch_fix.py source_bug --fix --issues-file issues.json # Fix using SonarQube issues")
        print("  python batch_fix.py source_bug --fix --enable-rag             # Fix and store results in RAG system")
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

            print("  python batch_fix.py source_bug --fix --prompt \"Fix security issues\"")

            print("  python batch_fix.py source_bug --fix --issues-file issues.json")
            print("\nLogging:")
            print("  Template usage and AI responses are logged to ./logs/template_usage_TIMESTAMP.log")
            print("  Logs include template type, prompts, response metrics, and processing details")
        return
    
    # Determine mode and output directory
    fix_mode = args.fix and not args.scan_only
    mode_text = "FIXING" if fix_mode else "SCANNING"
    print(f"\n{mode_text} Mode Enabled")
    
    if fix_mode:
        print("Fixing files in-place (overwriting originals)")
    
    # Custom prompt
    custom_prompt = args.prompt
    if custom_prompt:
        print(f"Using custom prompt: {custom_prompt[:50]}{'...' if len(custom_prompt) > 50 else ''}")
    
    # RAG integration
    if args.enable_rag:
        print("RAG Integration: Enabled - Fixed bugs will be stored in RAG system")
    
    # Load issues file if provided
    issues_by_file = {}
    if args.issues_file:
        if os.path.exists(args.issues_file):
            print(f"Loading issues from: {args.issues_file}")
            temp_processor = SecureFixProcessor(api_key, directory, backup_dir="temp")
            issues_by_file = temp_processor.load_issues_from_file(args.issues_file)
        else:
            print(f"Issues file not found: {args.issues_file}")
    
    # Get code files
    code_extensions = ['.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.html', '.css', '.txt']
    code_files = []
    
    # Create temporary processor to load ignore patterns
    temp_processor = SecureFixProcessor(api_key, directory, backup_dir="temp")
    temp_processor.load_ignore_patterns(directory)
    
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
    processor = SecureFixProcessor(api_key, directory)
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
                issues_data=file_issues,
                enable_rag=args.enable_rag
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
    

    
    # Summary
    success_count = sum(1 for r in results if r.success)
    error_count = len(results) - success_count

    # Calculate metrics
    total_input_tokens = sum(r.input_tokens for r in results if r.success)
    total_output_tokens = sum(r.output_tokens for r in results if r.success)
    total_tokens = sum(r.total_tokens for r in results if r.success)
    avg_similarity = sum(r.similarity_ratio for r in results if r.success) / max(success_count, 1)
    threshold_met_count = sum(1 for r in results if r.success and r.meets_threshold)

    summary = {
        "success": True,
        "fixed_count": success_count,
        "failed_count": error_count,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_tokens,
        "average_similarity": avg_similarity,
        "threshold_met_count": threshold_met_count,
        "similarity_threshold": processor.similarity_threshold,
    }

    print("\n" + "=" * 70)
    if fix_mode:
        print("BATCH_FIX_RESULT: SUCCESS")
        print(f"FIXED_FILES: {success_count}")
        print(f"FAILED_FILES: {error_count}")
        print(f"TOTAL_INPUT_TOKENS: {total_input_tokens}")
        print(f"TOTAL_OUTPUT_TOKENS: {total_output_tokens}")
        print(f"TOTAL_TOKENS: {total_tokens}")
        print(f"AVERAGE_SIMILARITY: {avg_similarity:.3f}")
        print(f"THRESHOLD_MET_COUNT: {threshold_met_count}")
        print(f"SIMILARITY_THRESHOLD: {processor.similarity_threshold}")
        
        # Detailed results for parsing
        print("\nDETAILED_RESULTS:")
        for r in results:
            status = "SUCCESS" if r.success else "FAILED"
            rel_path = os.path.relpath(r.file_path, directory)
            print(f"FILE: {rel_path} | STATUS: {status} | SIMILARITY: {r.similarity_ratio:.3f} | INPUT_TOKENS: {r.input_tokens} | OUTPUT_TOKENS: {r.output_tokens} | TOTAL_TOKENS: {r.total_tokens} | THRESHOLD_MET: {r.meets_threshold}")
    else:
        print("BATCH_SCAN_RESULT: SUCCESS")
        print(f"SCANNED_FILES: {success_count}")
        print(f"FAILED_FILES: {error_count}")
        
        # Count files with issues
        files_with_issues = sum(1 for r in results if r.success and r.issues_found != ["No issues found"])
        clean_files = success_count - files_with_issues
        print(f"FILES_WITH_ISSUES: {files_with_issues}")
        print(f"CLEAN_FILES: {clean_files}")
    
    if results:
        avg_time = sum(r.processing_time for r in results) / len(results)
        print(f"AVERAGE_PROCESSING_TIME: {avg_time:.1f}")
        summary["average_processing_time"] = avg_time

    print("\nEND_BATCH_RESULT")
    print(json.dumps(summary))

if __name__ == "__main__":
    main()
