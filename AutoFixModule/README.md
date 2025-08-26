# AutoFixModule - Automated Code Fixing Service

## 📋 Tổng quan

AutoFixModule cung cấp dịch vụ tự động sửa lỗi code với AI, hỗ trợ batch processing và template prompt system.

## 🚀 Khởi chạy

```bash
cd AutoFixModule
pip install -r requirements.txt
python main.py
```

Service sẽ chạy tại: http://localhost:8002

## 📁 Cấu trúc

```
AutoFixModule/
├── main.py              # FastAPI application
├── batch_fix.py         # Core fixing logic
├── controller/          # API controllers
├── modules/             # Fixer implementations
│   ├── llm.py          # LLM-based fixer
│   ├── base.py         # Base fixer interface
│   └── cli_service.py  # CLI service utilities
├── prompt/              # Prompt templates
│   ├── fix.j2          # Fix template
│   ├── analyze.j2      # Analysis template
│   └── custom.j2       # Custom template
├── lib/                 # Shared libraries
├── utils/               # Utilities
└── requirements.txt     # Dependencies
```

## 🔧 API Endpoints

### Fix Operations
- `POST /api/v1/fix/single` - Fix single file
- `POST /api/v1/fix/batch` - Batch fix multiple files
- `POST /api/v1/fix/analyze` - Analyze code issues
- `GET /api/v1/fix/templates` - List available templates

### Health Check
- `GET /health` - Service health status

## ⚙️ Cấu hình

Tạo file `.env`:
```env
GEMINI_API_KEY=your_gemini_api_key
AUTOFIX_PORT=8002
LOG_LEVEL=INFO
```

## 🎯 Sử dụng

### Fix single file
```bash
curl -X POST "http://localhost:8002/api/v1/fix/single" \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "./projects/demo_apps/Flask_App/app.py",
    "template_type": "fix",
    "use_rag": false
  }'
```

### Batch fix
```bash
curl -X POST "http://localhost:8002/api/v1/fix/batch" \
  -H "Content-Type: application/json" \
  -d '{
    "directory": "./projects/demo_apps/Flask_App",
    "template_type": "fix",
    "file_extensions": [".py", ".js"]
  }'
```

## 🧪 Testing

```bash
# Health check
curl http://localhost:8002/health

# API documentation
open http://localhost:8002/docs
```

## 📦 Dependencies

- FastAPI - Web framework
- Gemini AI - Code analysis and fixing
- Jinja2 - Template engine
- Uvicorn - ASGI server
- AST - Python code parsing

## 🔧 Template System

AutoFixModule sử dụng Jinja2 templates trong thư mục `prompt/`:

- **fix.j2**: Template cho việc sửa lỗi code
- **analyze.j2**: Template cho phân tích code
- **custom.j2**: Template tùy chỉnh

## 📊 Logging

Logs được lưu trong thư mục `logs/` với format:
- Template usage logs
- Fix operation results
- Error tracking