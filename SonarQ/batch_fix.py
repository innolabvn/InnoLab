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
    code_extensions = ['.py', '.js', '.ts', '.java', '.cpp', '.c', '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.html', '.css', '.jsx', '.tsx', '.vue', '.sql']
    
    code_files = []
    # Walk through all subdirectories
    for root, dirs, files in os.walk(directory):
        # Skip hidden directories and common build/cache directories
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'build', 'dist', 'target']]
        
        for file in files:
            file_path = os.path.join(root, file)
            # Check if file has a code extension
            if any(file.lower().endswith(ext) for ext in code_extensions):
                code_files.append(file_path)
    
    return code_files

def fix_code_file(model, file_path, custom_prompt=None):
    """Fix a single code file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            original_code = f.read()
        
        # Determine file type
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if custom_prompt:
            prompt = f"""
{custom_prompt}

Code cần sửa:
```
{original_code}
```

Chỉ trả về code đã sửa, không cần markdown formatting hay giải thích.
"""
        else:
            # Default prompts based on file type
            if file_ext == '.py':
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
8. Sửa các security vulnerabilities
9. Cải thiện code structure và readability

Chỉ trả về code Python đã sửa, không cần markdown formatting hay giải thích.
"""
            elif file_ext in ['.js', '.ts', '.jsx', '.tsx']:
                prompt = f"""
Hãy sửa tất cả các vấn đề trong JavaScript/TypeScript code này:

```javascript
{original_code}
```

Vui lòng:
1. Sửa các lỗi syntax
2. Sửa các logic error
3. Cải thiện code quality
4. Thêm error handling
5. Tối ưu hóa performance
6. Thêm type annotations (nếu là TypeScript)
7. Sửa security vulnerabilities
8. Cải thiện code structure

Chỉ trả về code đã sửa, không cần markdown formatting hay giải thích.
"""
            elif file_ext in ['.html', '.htm']:
                prompt = f"""
Hãy sửa và cải thiện HTML code này:

```html
{original_code}
```

Vui lòng:
1. Sửa các lỗi HTML syntax
2. Cải thiện semantic HTML
3. Thêm accessibility attributes
4. Tối ưu hóa SEO
5. Sửa security issues
6. Cải thiện structure

Chỉ trả về HTML code đã sửa, không cần markdown formatting hay giải thích.
"""
            elif file_ext == '.css':
                prompt = f"""
Hãy sửa và cải thiện CSS code này:

```css
{original_code}
```

Vui lòng:
1. Sửa các lỗi CSS syntax
2. Tối ưu hóa performance
3. Cải thiện responsive design
4. Sử dụng modern CSS features
5. Cải thiện code organization

Chỉ trả về CSS code đã sửa, không cần markdown formatting hay giải thích.
"""
            else:
                prompt = f"""
Hãy sửa và cải thiện code này:

```
{original_code}
```

Vui lòng:
1. Sửa các lỗi syntax
2. Sửa các logic error
3. Cải thiện code quality
4. Thêm error handling nếu cần
5. Tối ưu hóa performance
6. Sửa security vulnerabilities

Chỉ trả về code đã sửa, không cần markdown formatting hay giải thích.
"""
        
        response = model.generate_content(prompt)
        fixed_code = response.text.strip()
        
        # Remove markdown formatting if present
        if fixed_code.startswith('```python') or fixed_code.startswith('```javascript') or fixed_code.startswith('```html') or fixed_code.startswith('```css'):
            fixed_code = '\n'.join(fixed_code.split('\n')[1:])
        if fixed_code.startswith('```'):
            fixed_code = '\n'.join(fixed_code.split('\n')[1:])
        if fixed_code.endswith('```'):
            fixed_code = '\n'.join(fixed_code.split('\n')[:-1])
        
        return fixed_code.strip()
        
    except Exception as e:
        return f"# Error fixing file: {str(e)}\n{original_code}"

def get_custom_prompt():
    """Get custom prompt from user"""
    print("\n🎯 Tùy chọn prompt:")
    print("1. Sử dụng prompt mặc định (tự động theo loại file)")
    print("2. Nhập prompt tùy chỉnh")
    
    while True:
        choice = input("\nChọn tùy chọn (1 hoặc 2): ").strip()
        if choice == '1':
            return None
        elif choice == '2':
            print("\n📝 Nhập prompt tùy chỉnh của bạn:")
            print("(Nhấn Enter 2 lần để kết thúc)")
            lines = []
            while True:
                line = input()
                if line == "" and len(lines) > 0 and lines[-1] == "":
                    break
                lines.append(line)
            
            # Remove the last empty line
            if lines and lines[-1] == "":
                lines.pop()
            
            custom_prompt = "\n".join(lines).strip()
            if custom_prompt:
                return custom_prompt
            else:
                print("❌ Prompt không được để trống. Vui lòng thử lại.")
        else:
            print("❌ Lựa chọn không hợp lệ. Vui lòng chọn 1 hoặc 2.")

def main():
    print("🤖 Advanced Batch Fix Script")
    print("Công cụ sửa lỗi và cải thiện code tự động với AI")
    print("=" * 60)
    
    # Get directory from command line or user input
    if len(sys.argv) >= 2:
        directory = sys.argv[1]
    else:
        print("\n📁 Nhập đường dẫn thư mục cần scan:")
        print("Ví dụ: ./source_bug hoặc D:\\Project\\src")
        directory = input("Thư mục: ").strip()
        
        if not directory:
            print("❌ Đường dẫn không được để trống")
            return
    
    if not os.path.isdir(directory):
        print(f"❌ Lỗi: {directory} không phải là thư mục hợp lệ")
        return
    
    # Setup Gemini
    print("\n🔧 Đang khởi tạo Gemini AI...")
    model = setup_gemini()
    
    # Get all code files
    print(f"\n🔍 Đang scan thư mục: {directory}")
    code_files = get_code_files(directory)
    
    if not code_files:
        print(f"❌ Không tìm thấy file code nào trong: {directory}")
        return
    
    print(f"\n📊 Kết quả scan:")
    print(f"📁 Thư mục: {directory}")
    print(f"🔍 Tìm thấy {len(code_files)} file code")
    
    # Show file list
    print("\n📋 Danh sách file sẽ được xử lý:")
    for i, file_path in enumerate(code_files, 1):
        relative_path = os.path.relpath(file_path, directory)
        file_size = os.path.getsize(file_path)
        print(f"  {i:2d}. {relative_path} ({file_size} bytes)")
    
    # Get custom prompt
    custom_prompt = get_custom_prompt()
    
    if custom_prompt:
        print(f"\n📝 Sử dụng prompt tùy chỉnh: {custom_prompt[:100]}...")
    else:
        print("\n🎯 Sử dụng prompt mặc định theo loại file")
    
    # Confirm before processing
    print("\n⚠️  Xác nhận xử lý:")
    confirm = input(f"Bạn có muốn tiếp tục xử lý {len(code_files)} file? (y/N): ").strip().lower()
    if confirm not in ['y', 'yes']:
        print("❌ Đã hủy xử lý")
        return
    
    print("\n" + "=" * 60)
    print("🚀 Bắt đầu xử lý...")
    
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
            fixed_code = fix_code_file(model, file_path, custom_prompt)
            
            # Create output path
            fixed_file_path = os.path.join(fixed_dir, relative_path)
            fixed_file_dir = os.path.dirname(fixed_file_path)
            os.makedirs(fixed_file_dir, exist_ok=True)
            
            # Save fixed code
            with open(fixed_file_path, 'w', encoding='utf-8') as f:
                f.write(fixed_code)
            
            # Show file size comparison
            original_size = os.path.getsize(file_path)
            fixed_size = len(fixed_code.encode('utf-8'))
            size_diff = fixed_size - original_size
            size_change = f"({size_diff:+d} bytes)" if size_diff != 0 else "(không đổi)"
            
            print(f"✅ Đã sửa và lưu: {fixed_file_path} {size_change}")
            success_count += 1
            
        except Exception as e:
            print(f"❌ Lỗi khi xử lý {relative_path}: {str(e)}")
            error_count += 1
    
    print("\n" + "=" * 60)
    print(f"🎉 Hoàn thành xử lý!")
    print(f"✅ Thành công: {success_count} file")
    print(f"❌ Lỗi: {error_count} file")
    print(f"📁 Code đã sửa được lưu trong: {fixed_dir}")
    print(f"📊 Tỷ lệ thành công: {success_count/(success_count+error_count)*100:.1f}%" if (success_count+error_count) > 0 else "")
    
    if success_count > 0:
        print("\n💡 Gợi ý: Hãy kiểm tra và test code đã sửa trước khi sử dụng trong production!")

if __name__ == "__main__":
    main()