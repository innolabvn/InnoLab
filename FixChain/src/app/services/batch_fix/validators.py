# src/app/services/batch_fix/validators.py
from __future__ import annotations
import ast, re, subprocess, tempfile
from difflib import SequenceMatcher
from pathlib import Path
from typing import Tuple, List

def validate_python(code: str) -> Tuple[bool, List[str]]:
    try:
        ast.parse(code)
        return True, []
    except SyntaxError as e:
        return False, [f"Syntax Error: {e.msg} at line {e.lineno}"]
    except Exception as e:
        return False, [f"Parse Error: {str(e)}"]

def validate_js(code: str) -> Tuple[bool, List[str]]:
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
            f.write(code); f.flush()
            res = subprocess.run(["node","--check", f.name], capture_output=True, text=True, timeout=10)
        Path(f.name).unlink(missing_ok=True)
        if res.returncode != 0:
            return False, [f"JS Syntax Error: {res.stderr}"]
        return True, []
    except subprocess.TimeoutExpired:
        return False, ["Validation timeout"]
    except FileNotFoundError:
        return True, ["Node.js not available for validation"]
    except Exception as e:
        return False, [f"Validation error: {e}"]

def validate_html(code: str) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    lower = code.lower()
    if "<html" in lower and "</html>" not in lower: errors.append("Missing closing </html> tag")
    if "<head" in lower and "</head>" not in lower: errors.append("Missing closing </head> tag")
    if "<body" in lower and "</body>" not in lower: errors.append("Missing closing </body> tag")
    return len(errors) == 0, errors

def validate_css(code: str) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if code.count("{") != code.count("}"):
        errors.append(f"Mismatched braces: {code.count('{')} open, {code.count('}')} close")
    for i, line in enumerate(code.splitlines(), 1):
        s = line.strip()
        if s and ":" in s and not any(s.endswith(t) for t in (";", "{", "}")) and not any(x in s for x in ("{","}","@","/*")):
            errors.append(f"Line {i}: Missing semicolon")
    return len(errors) == 0, errors

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def validate_safety(original: str, fixed: str) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    if similarity(original, fixed) < 0.3:
        issues.append("Code changed too drastically (similarity < 0.3)")
    suspicious = ['eval(', 'exec(', 'os.system', 'subprocess.call', '__import__', 'file://', 'http://', 'https://']
    lo, lf = original.lower(), fixed.lower()
    for p in suspicious:
        if p in lf and p not in lo:
            issues.append(f"Suspicious pattern added: {p}")
    return len(issues) == 0, issues

def get_rules_for(path: str) -> str:
    ext = Path(path).suffix.lower()
    rules = {
        ".py": "- Must be valid Python syntax\n- Follow PEP 8 guidelines\n- No dangerous imports",
        ".js": "- Must be valid JavaScript syntax\n- Use modern ES6+ features\n- No eval() usage",
        ".jsx":"- Must be valid React JSX syntax\n- Follow React best practices",
        ".html":"- Must be valid HTML5 syntax\n- Proper tag nesting and closing\n- Use semantic HTML elements",
        ".css": "- Must be valid CSS syntax\n- Proper selector formatting\n- No missing semicolons or braces",
        ".txt": "- Maintain text formatting\n- Fix spelling and grammar\n- Preserve original structure",
    }
    return rules.get(ext, "- Maintain original functionality\n- Fix syntax errors only")

def validate_by_ext(path: str, code: str) -> Tuple[bool, List[str]]:
    ext = Path(path).suffix.lower()
    if ext == ".py": return validate_python(code)
    if ext in (".js", ".jsx"): return validate_js(code)
    if ext == ".html": return validate_html(code)
    if ext == ".css": return validate_css(code)
    return True, []
