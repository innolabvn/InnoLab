#!/usr/bin/env python3
"""
Batch Fix Script - Auto fix and save all code files in a directory
Usage: python batch_fix.py [directory_path]
"""

import google.generativeai as genai
import os
import sys
import glob
from pathlib import Path
from dotenv import load_dotenv

def setup_gemini():
    """Setup Gemini API"""
    load_dotenv()
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ Lỗi: GEMINI_API_KEY không tìm thấy trong file .env")
        sys.exit(1)
    
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-1.5-flash')

def get_code_files(directory):
    """Get all code files from a directory"""
    code_extensions = ['.py', '.js', '.ts', '.java', '.cpp', '.c', '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt']
    
    code_files = []
    for ext in code_extensions:
        pattern = os.path.join(directory, f"**/*{ext}")
        code_files.extend(glob.glob(pattern, recursive=True))
    
    return code_files

def fix_code_file(model, file_path):
    """Fix a single code file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            original_code = f.read()
        
        prompt = f"""
Hãy sửa tất cả các vấn đề trong code Python này:

```python
{original_code}
```

Vui lòng:
1. Sửa các lỗi syntax
2. Sửa các logic error
3. Cải thiện code quality
4. Thêm error handling nếu cần
5. Tối ưu hóa performance
6. Thêm type hints nếu thiếu
7. Thêm docstring cho các function

Chỉ trả về code Python đã sửa, không cần markdown formatting hay giải thích.
"""
        
        response = model.generate_content(prompt)
        fixed_code = response.text.strip()
        
        # Remove markdown formatting if present
        if fixed_code.startswith('```python'):
            fixed_code = fixed_code[9:]
        if fixed_code.startswith('```'):
            fixed_code = fixed_code[3:]
        if fixed_code.endswith('```'):
            fixed_code = fixed_code[:-3]
        
        return fixed_code.strip()
        
    except Exception as e:
        return f"# Error fixing file: {str(e)}\n{original_code}"

def main():
    if len(sys.argv) != 2:
        print("🤖 Batch Fix Script")
        print("Cách sử dụng: python batch_fix.py [thư_mục]")
        print("Ví dụ: python batch_fix.py ./source_bug")
        return
    
    directory = sys.argv[1]
    
    if not os.path.isdir(directory):
        print(f"❌ Lỗi: {directory} không phải là thư mục hợp lệ")
        return
    
    # Setup Gemini
    model = setup_gemini()
    
    # Get all code files
    code_files = get_code_files(directory)
    
    if not code_files:
        print(f"❌ Không tìm thấy file code nào trong: {directory}")
        return
    
    print(f"🔧 Batch Fix Script")
    print(f"📁 Thư mục: {directory}")
    print(f"🔍 Tìm thấy {len(code_files)} file code")
    print("=" * 50)
    
    # Create fixed directory
    fixed_dir = os.path.join(directory, "fixed")
    os.makedirs(fixed_dir, exist_ok=True)
    
    success_count = 0
    error_count = 0
    
    for i, file_path in enumerate(code_files, 1):
        relative_path = os.path.relpath(file_path, directory)
        print(f"\n[{i}/{len(code_files)}] 🔧 Đang sửa: {relative_path}")
        
        try:
            # Fix the code
            fixed_code = fix_code_file(model, file_path)
            
            # Create output path
            fixed_file_path = os.path.join(fixed_dir, relative_path)
            fixed_file_dir = os.path.dirname(fixed_file_path)
            os.makedirs(fixed_file_dir, exist_ok=True)
            
            # Save fixed code
            with open(fixed_file_path, 'w', encoding='utf-8') as f:
                f.write(fixed_code)
            
            print(f"✅ Đã sửa và lưu: {fixed_file_path}")
            success_count += 1
            
        except Exception as e:
            print(f"❌ Lỗi khi xử lý {relative_path}: {str(e)}")
            error_count += 1
    
    print("\n" + "=" * 50)
    print(f"🎉 Hoàn thành!")
    print(f"✅ Thành công: {success_count} file")
    print(f"❌ Lỗi: {error_count} file")
    print(f"📁 Code đã sửa được lưu trong: {fixed_dir}")

if __name__ == "__main__":
    main()