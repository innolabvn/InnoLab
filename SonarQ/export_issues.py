#!/usr/bin/env python3
import os, sys, math, requests, itertools
import re
import json
from dotenv import load_dotenv

# Load environment variables from root directory
root_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(root_env_path)

SONAR_HOST = os.getenv("SONAR_HOST", "http://localhost:9000").rstrip("/")
SONAR_TOKEN = os.getenv("SONAR_TOKEN")

if not SONAR_TOKEN:
    print("Error: SONAR_TOKEN environment variable is not set")
    print("Please set SONAR_TOKEN in .env file")
    sys.exit(1) 

def get_all_issues(project_key, page_size=500, file_filter=None):
    sess = requests.Session()
    sess.auth = (SONAR_TOKEN, "")
    issues = []
    page = 1
    while True:
        params = {
            "componentKeys": project_key,
            "p": page,
            "ps": page_size
        }
        
        # Add file filter if specified
        if file_filter:
            params["componentKeys"] = f"{project_key}:{file_filter}"
        
        r = sess.get(f"{SONAR_HOST}/api/issues/search", params=params)
        r.raise_for_status()
        js = r.json()
        issues.extend(js.get("issues", []))
        total = js.get("total", 0)
        if page * page_size >= total:
            break
        page += 1
    return issues

def fetch_rule_descriptions(rule_keys):
    sess = requests.Session()
    sess.auth = (SONAR_TOKEN, "")
    desc = {}
    for rk in rule_keys:
        rr = sess.get(f"{SONAR_HOST}/api/rules/show", params={"key": rk})
        if rr.status_code == 200:
            rj = rr.json().get("rule", {})
            # mô tả có thể ở fields khác nhau tùy rule; fallback ngắn gọn
            d = rj.get("htmlDesc") or rj.get("mdDesc") or rj.get("name") or ""
            # bỏ tag HTML đơn giản
            d = re.sub("<[^<]+?>", "", d).strip()
            desc[rk] = d
        else:
            desc[rk] = ""
    return desc

def clamp(a, lo, hi): 
    return max(lo, min(hi, a))

def fetch_code_excerpt(component_key, line, radius=10):
    if not line:
        return None
    sess = requests.Session()
    sess.auth = (SONAR_TOKEN, "")
    start = max(1, line - radius)
    end = line + radius
    r = sess.get(f"{SONAR_HOST}/api/sources/lines", params={"key": component_key, "from": start, "to": end})
    if r.status_code != 200:
        return None
    js = r.json()
    # trả về chuỗi các dòng, có đánh số
    lines = js.get("sources", [])
    # nối lại kèm số dòng
    out = []
    for e in lines:
        ln = e.get("line")
        txt = e.get("code", "")
        out.append(f"{ln:>5}: {txt}")
    return "\n".join(out) if out else None

def to_file_path(project_key, component):
    # Thường dạng "projectKey:path/to/file.ext"
    prefix = f"{project_key}:"
    if component.startswith(prefix):
        return component[len(prefix):]
    # fallback: trả nguyên
    return component

def main():
    if len(sys.argv) < 2:
        print("Usage: SONAR_TOKEN=... python export_issues.py <project_key> [host] [file_filter]")
        sys.exit(1)

    project_key = sys.argv[1]
    global SONAR_HOST
    if len(sys.argv) >= 3:
        SONAR_HOST = sys.argv[2].rstrip("/")
    
    # Optional file filter parameter
    file_filter = None
    if len(sys.argv) >= 4:
        file_filter = sys.argv[3]

    if not SONAR_TOKEN:
        print("Error: SONAR_TOKEN env is required")
        sys.exit(2)

    issues = get_all_issues(project_key, file_filter=file_filter)
    rule_keys = sorted(set(i.get("rule") for i in issues if i.get("rule")))
    rule_desc = fetch_rule_descriptions(rule_keys)

    out = {"issues": []}
    for i in issues:
        key = i.get("key")                    # unique issue id
        rule_key = i.get("rule")
        severity = i.get("severity")          # INFO/MINOR/MAJOR/CRITICAL/BLOCKER
        itype = i.get("type")                 # BUG/VULNERABILITY/CODE_SMELL (tùy version)
        component = i.get("component")        # "<projectKey>:path/file"
        file_path = to_file_path(project_key, component)
        line = i.get("line")
        message = i.get("message")
        status = i.get("status")
        resolution = i.get("resolution")      # may be None
        createdAt = i.get("creationDate")
        updatedAt = i.get("updateDate")

        # code excerpt 10–20 dòng quanh line (nếu có)
        code_excerpt = fetch_code_excerpt(component, line, radius=10) if line else None

        out["issues"].append({
            "bug_id": key,
            "bug_name": message,
            "rule_key": rule_key,
            "severity": severity,
            "type": itype,
            "file_path": file_path,
            "line": line,
            "message": message,
            "status": status,
            "resolution": resolution,
            "created_at": createdAt,
            "updated_at": updatedAt,
            "rule_description": rule_desc.get(rule_key, ""),
            "code_excerpt": code_excerpt
        })

    # Print JSON output with proper encoding
    json_output = json.dumps(out, indent=4, ensure_ascii=False)
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout.buffer.write(json_output.encode('utf-8'))
    else:
        print(json_output)

if __name__ == "__main__":
    main()