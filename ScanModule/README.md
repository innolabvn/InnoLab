# ScanModule - Code Security Scanning Service

## 📋 Tổng quan

ScanModule cung cấp dịch vụ quét bảo mật code với tích hợp Bearer Scanner và SonarQube Scanner, hỗ trợ extensible scanner registry.

## 🚀 Khởi chạy

```bash
cd ScanModule
pip install -r requirements.txt
python main.py
```

Service sẽ chạy tại: http://localhost:8003

## 📁 Cấu trúc

```
ScanModule/
├── main.py              # FastAPI application
├── controller/          # API controllers
├── modules/             # Scanner implementations
│   ├── bearer.py       # Bearer Scanner
│   ├── sonar.py        # SonarQube Scanner
│   ├── registry.py     # Scanner registry
│   ├── base.py         # Base scanner interface
│   └── cli_service.py  # CLI service utilities
├── lib/                 # Shared libraries
├── utils/               # Utilities
└── requirements.txt     # Dependencies
```

## 🔧 API Endpoints

### Scan Operations
- `POST /api/v1/scan/single` - Scan single project
- `POST /api/v1/scan/batch` - Batch scan multiple projects
- `GET /api/v1/scan/scanners` - List available scanners
- `GET /api/v1/scan/results/{scan_id}` - Get scan results

### Health Check
- `GET /health` - Service health status

## ⚙️ Cấu hình

Tạo file `.env`:
```env
SONAR_TOKEN=your_sonar_token
SONAR_HOST_URL=http://localhost:9000
BEARER_API_KEY=your_bearer_api_key
SCAN_PORT=8003
LOG_LEVEL=INFO
```

## 🎯 Sử dụng

### Scan với Bearer
```bash
curl -X POST "http://localhost:8003/api/v1/scan/single" \
  -H "Content-Type: application/json" \
  -d '{
    "project_path": "./projects/demo_apps/Flask_App",
    "scanner_type": "bearer",
    "output_format": "json"
  }'
```

### Scan với SonarQube
```bash
curl -X POST "http://localhost:8003/api/v1/scan/single" \
  -H "Content-Type: application/json" \
  -d '{
    "project_path": "./projects/demo_apps/Flask_App",
    "scanner_type": "sonar",
    "project_key": "my-flask-app"
  }'
```

### Liệt kê scanners
```bash
curl http://localhost:8003/api/v1/scan/scanners
```

## 🧪 Testing

```bash
# Health check
curl http://localhost:8003/health

# API documentation
open http://localhost:8003/docs
```

## 📦 Dependencies

- FastAPI - Web framework
- Bearer CLI - Security scanning
- SonarQube Scanner - Code quality analysis
- Uvicorn - ASGI server
- Subprocess - CLI integration

## 🔧 Scanner Registry

ScanModule sử dụng registry pattern để quản lý các scanner:

```python
# Đăng ký scanner mới
scanner_registry.register("custom", CustomScanner, config)

# Lấy scanner
scanner = scanner_registry.get_scanner("bearer")

# Liệt kê scanners
scanners = scanner_registry.list_scanners()
```

## 🛡️ Supported Scanners

### Bearer Scanner
- **Chức năng**: Security vulnerability detection
- **Ngôn ngữ hỗ trợ**: Python, JavaScript, Java, Go, Ruby
- **Output formats**: JSON, SARIF, HTML

### SonarQube Scanner
- **Chức năng**: Code quality và security analysis
- **Ngôn ngữ hỗ trợ**: 25+ programming languages
- **Tích hợp**: SonarQube Server/Cloud

## 📊 Scan Results

Kết quả scan được trả về theo format chuẩn:

```json
{
  "scan_id": "uuid",
  "scanner_type": "bearer",
  "project_path": "./projects/demo_apps/Flask_App",
  "status": "completed",
  "issues_found": 5,
  "results": [...],
  "scan_time": "2024-01-15T10:30:00Z"
}
```

## 🔄 Extensibility

Thêm scanner mới bằng cách:

1. Tạo class kế thừa từ `Scanner`
2. Implement phương thức `scan()`
3. Đăng ký trong registry
4. Cấu hình trong main.py