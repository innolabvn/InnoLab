# Hướng Dẫn Sử Dụng batch_fix.py

## Tổng Quan
`batch_fix.py` là công cụ tự động sửa lỗi code sử dụng AI, hỗ trợ nhiều ngôn ngữ lập trình và có khả năng logging chi tiết.

## Cài Đặt
```bash
pip install -r requirements.txt
```

## Cách Sử Dụng Cơ Bản

### 1. Quét và Phân Tích (Scan Only)
```bash
python batch_fix.py --scan-only source_directory
```
- Chỉ quét và phân tích các file có lỗi
- Không thực hiện sửa chữa
- Hiển thị danh sách các file cần sửa

### 2. Sửa Lỗi Tự Động
```bash
python batch_fix.py --fix source_directory
```
- Quét và sửa lỗi tự động
- Tạo backup trước khi sửa
- Hiển thị kết quả chi tiết

### 3. Sử Dụng Prompt Tùy Chỉnh
```bash
python batch_fix.py --fix source_directory --prompt "Chuyển đổi code Python 2 sang Python 3"
```
- Sử dụng prompt tùy chỉnh thay vì template mặc định
- Hữu ích cho các yêu cầu đặc biệt

### 4. Copy Toàn Bộ Project (Mới)
```bash
python batch_fix.py --fix source_directory --output output_directory --copy-all
```
- Copy toàn bộ project vào thư mục output
- Sửa các file có lỗi
- Giữ nguyên cấu trúc thư mục
- Hỗ trợ .fixignore để loại trừ file không cần thiết

## Tùy Chọn Nâng Cao

### Auto Mode
```bash
python batch_fix.py --fix source_directory --auto
```
- Tự động xác nhận tất cả thao tác
- Không cần tương tác người dùng
- Phù hợp cho automation

### Backup và Restore
```bash
# Tạo backup thủ công
python batch_fix.py --backup source_directory

# Khôi phục từ backup
python batch_fix.py --restore backup_directory source_directory
```

### Cấu Hình .fixignore
Tạo file `.fixignore` trong thư mục gốc để loại trừ các file/thư mục:
```
# Loại trừ thư mục
node_modules/
.git/
__pycache__/

# Loại trừ file theo extension
*.log
*.tmp
*.cache

# Loại trừ file cụ thể
config.json
secrets.env
```

## Logging và Phân Tích

### Vị Trí Log Files
- Thư mục: `logs/`
- Format: `template_usage_YYYYMMDD_HHMMSS.log`
- Encoding: UTF-8

### Nội Dung Log
Mỗi log entry bao gồm:
- **TEMPLATE_USAGE**: Thông tin template được sử dụng
- **AI_RESPONSE**: Phản hồi từ AI và kết quả xử lý

### Phân Tích Hiệu Quả
```bash
# Xem log gần nhất
type logs\template_usage_*.log | findstr "SUCCESS\|FAILED"

# Thống kê theo template
type logs\template_usage_*.log | findstr "Template Type"
```

## Ví Dụ Thực Tế

### 1. Sửa Lỗi Flask App
```bash
python batch_fix.py --fix "Flask App" --auto
```

### 2. Chuyển Đổi Python 2 → 3
```bash
python batch_fix.py --fix old_python_code --prompt "Convert Python 2 to Python 3 syntax" --auto
```

### 3. Copy và Sửa Toàn Bộ Project
```bash
python batch_fix.py --fix source_project --output fixed_project --copy-all --auto
```

### 4. Phân Tích Trước Khi Sửa
```bash
# Bước 1: Quét và xem danh sách lỗi
python batch_fix.py --scan-only source_directory

# Bước 2: Sửa với prompt tùy chỉnh
python batch_fix.py --fix source_directory --prompt "Fix security vulnerabilities" --auto
```

## Template System

### Templates Có Sẵn
- `fix.j2`: Template sửa lỗi chung
- `analyze.j2`: Template phân tích code
- `custom.j2`: Template cho prompt tùy chỉnh

### Tùy Chỉnh Template
1. Tạo file `.j2` mới trong thư mục `prompt/`
2. Sử dụng Jinja2 syntax
3. Bao gồm các biến: `{{code}}`, `{{file_path}}`, `{{custom_prompt}}`

## Troubleshooting

### Lỗi Thường Gặp
1. **"No API key found"**: Thiết lập biến môi trường `GEMINI_API_KEY`
2. **"Invalid directory"**: Kiểm tra đường dẫn thư mục
3. **"Template not found"**: Đảm bảo thư mục `prompt/` tồn tại

### Performance Tips
- Sử dụng `--auto` cho batch processing
- Cấu hình `.fixignore` để loại trừ file không cần thiết
- Sử dụng `--copy-all` khi cần giữ nguyên cấu trúc project

## Kết Luận
`batch_fix.py` là công cụ mạnh mẽ cho việc sửa lỗi code tự động với khả năng:
- Hỗ trợ nhiều ngôn ngữ lập trình
- Template system linh hoạt
- Logging chi tiết cho phân tích
- Copy toàn bộ project với cấu trúc nguyên vẹn
- Tùy chỉnh cao thông qua prompt và template

Để biết thêm chi tiết về logging, xem `LOGGING_GUIDE.md`.