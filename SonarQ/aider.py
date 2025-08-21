#!/usr/bin/env python3
"""
Simple Aider-like command line tool using Gemini API
Usage: python aider.py [file_path] [--fix] [--analyze] [--question "your question"]
"""

import google.generativeai as genai
import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv
import glob

def setup_gemini():
    """Setup Gemini API"""
    # Load environment variables from root directory
    root_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    load_dotenv(root_env_path)
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ Lỗi: GEMINI_API_KEY không tìm thấy trong file .env")
        sys.exit(1)
    
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-1.5-flash')

def analyze_file(model, file_path):
    """Analyze a code file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code_content = f.read()
        
        prompt = f"""
Phân tích file code này và cung cấp:
1. Đánh giá chất lượng code
2. Các vấn đề tiềm ẩn
3. Đề xuất cải thiện

File: {file_path}

```
{code_content}
```

Trả lời bằng tiếng Việt, ngắn gọn và súc tích.
"""
        
        response = model.generate_content(prompt)
        return response.text
        
    except FileNotFoundError:
        return f"❌ Không tìm thấy file: {file_path}"
    except Exception as e:
        return f"❌ Lỗi: {str(e)}"

def fix_file(model, file_path):
    """Fix issues in a code file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code_content = f.read()
        
        prompt = f"""
Hãy sửa các vấn đề trong code này và cung cấp code đã được cải thiện:

File: {file_path}

```
{code_content}
```

Vui lòng:
1. Sửa các lỗi syntax nếu có
2. Cải thiện code quality
3. Thêm comments nếu cần
4. Tối ưu hóa performance

Chỉ trả về code đã sửa, không cần giải thích dài dòng.
"""
        
        response = model.generate_content(prompt)
        return response.text
        
    except FileNotFoundError:
        return f"❌ Không tìm thấy file: {file_path}"
    except Exception as e:
        return f"❌ Lỗi: {str(e)}"

def ask_question(model, question):
    """Ask a coding question"""
    prompt = f"""
Câu hỏi lập trình: {question}

Vui lòng trả lời ngắn gọn với ví dụ code cụ thể (nếu có).
Trả lời bằng tiếng Việt.
"""
    
    response = model.generate_content(prompt)
    return response.text

def get_code_files(path):
    """Get all code files from a path (file or directory)"""
    code_extensions = ['.py', '.js', '.ts', '.java', '.cpp', '.c', '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt']
    
    if os.path.isfile(path):
        return [path]
    
    elif os.path.isdir(path):
        code_files = []
        for ext in code_extensions:
            pattern = os.path.join(path, f"**/*{ext}")
            code_files.extend(glob.glob(pattern, recursive=True))
        return code_files
    
    else:
        return []

def analyze_directory(model, dir_path):
    """Analyze all code files in a directory"""
    code_files = get_code_files(dir_path)
    
    if not code_files:
        return f"❌ Không tìm thấy file code nào trong: {dir_path}"
    
    results = []
    results.append(f"📁 Phân tích thư mục: {dir_path}")
    results.append(f"🔍 Tìm thấy {len(code_files)} file code:")
    
    for file_path in code_files:
        results.append(f"\n{'='*50}")
        results.append(f"📄 File: {os.path.relpath(file_path, dir_path)}")
        results.append(f"{'='*50}")
        
        try:
            analysis = analyze_file(model, file_path)
            results.append(analysis)
        except Exception as e:
            results.append(f"❌ Lỗi khi phân tích {file_path}: {str(e)}")
    
    return "\n".join(results)

def fix_directory(model, dir_path):
    """Fix all code files in a directory"""
    code_files = get_code_files(dir_path)
    
    if not code_files:
        return f"❌ Không tìm thấy file code nào trong: {dir_path}"
    
    results = []
    results.append(f"📁 Sửa lỗi thư mục: {dir_path}")
    results.append(f"🔧 Đang xử lý {len(code_files)} file code:")
    
    for file_path in code_files:
        results.append(f"\n{'='*50}")
        results.append(f"📄 File: {os.path.relpath(file_path, dir_path)}")
        results.append(f"{'='*50}")
        
        try:
            fixed_code = fix_file(model, file_path)
            results.append(fixed_code)
            
            # Optionally save the fixed code to a new file
            fixed_file_path = file_path.replace('.py', '_fixed.py').replace('.js', '_fixed.js')
            # Uncomment the next lines if you want to save fixed files
            # with open(fixed_file_path, 'w', encoding='utf-8') as f:
            #     f.write(fixed_code)
            # results.append(f"💾 Đã lưu code đã sửa vào: {fixed_file_path}")
            
        except Exception as e:
            results.append(f"❌ Lỗi khi sửa {file_path}: {str(e)}")
    
    return "\n".join(results)

def main():
    parser = argparse.ArgumentParser(description='Gemini AI Coding Assistant')
    parser.add_argument('file', nargs='?', help='File path to analyze or fix')
    parser.add_argument('--analyze', action='store_true', help='Analyze the file')
    parser.add_argument('--fix', action='store_true', help='Fix issues in the file')
    parser.add_argument('--question', type=str, help='Ask a coding question')
    
    args = parser.parse_args()
    
    # Setup Gemini
    model = setup_gemini()
    
    if args.question:
        print("🤔 Đang suy nghĩ...")
        result = ask_question(model, args.question)
        print("\n💡 Trả lời:")
        print(result)
    
    elif args.file:
        if os.path.isdir(args.file):
            # Handle directory
            if args.analyze:
                print(f"🔍 Đang phân tích thư mục {args.file}...")
                result = analyze_directory(model, args.file)
                print("\n📋 Kết quả phân tích:")
                print(result)
            
            elif args.fix:
                print(f"🔧 Đang sửa lỗi thư mục {args.file}...")
                result = fix_directory(model, args.file)
                print("\n🛠️ Kết quả sửa lỗi:")
                print(result)
            
            else:
                # Default to analyze for directory
                print(f"🔍 Đang phân tích thư mục {args.file}...")
                result = analyze_directory(model, args.file)
                print("\n📋 Kết quả phân tích:")
                print(result)
        
        else:
            # Handle single file
            if args.analyze:
                print(f"🔍 Đang phân tích {args.file}...")
                result = analyze_file(model, args.file)
                print("\n📋 Kết quả phân tích:")
                print(result)
            
            elif args.fix:
                print(f"🔧 Đang sửa lỗi {args.file}...")
                result = fix_file(model, args.file)
                print("\n🛠️ Code đã sửa:")
                print(result)
            
            else:
                # Default to analyze
                print(f"🔍 Đang phân tích {args.file}...")
                result = analyze_file(model, args.file)
                print("\n📋 Kết quả phân tích:")
                print(result)
    
    else:
        print("🤖 Gemini AI Coding Assistant")
        print("\nCách sử dụng:")
        print("  python aider.py file.py --analyze    # Phân tích file")
        print("  python aider.py file.py --fix        # Sửa lỗi file")
        print('  python aider.py --question "câu hỏi" # Hỏi về lập trình')
        print("\nVí dụ:")
        print("  python aider.py test.py")
        print("  python aider.py test.py --fix")
        print('  python aider.py --question "Cách sử dụng list comprehension?"')

if __name__ == "__main__":
    main()