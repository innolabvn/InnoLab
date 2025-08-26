# InnoLab - Modular Architecture

Dự án InnoLab đã được tái cấu trúc thành các module độc lập để dễ dàng phát triển, bảo trì và triển khai.

## 🏗️ Cấu trúc Module

### 📊 RagModule (Port 8001)
**Chức năng**: RAG (Retrieval-Augmented Generation) Service
- Vector search với MongoDB
- AI-powered document retrieval
- Embedding generation với Gemini
- Bug management với RAG

**Cấu trúc**:
```
RagModule/
├── main.py              # FastAPI application
├── controller/          # API controllers
│   ├── rag_controller.py
│   └── rag_bug_controller.py
├── modules/             # Core modules
│   └── mongodb_service.py
├── lib/                 # Libraries
├── utils/               # Utilities
└── requirements.txt
```

### 🔧 AutoFixModule (Port 8002)
**Chức năng**: Automated Code Fixing Service
- Tự động sửa lỗi code với AI
- Batch processing
- Template prompt system
- Code validation

**Cấu trúc**:
```
AutoFixModule/
├── main.py              # FastAPI application
├── batch_fix.py         # Core fixing logic
├── modules/             # Fixer implementations
│   ├── llm.py
│   └── base.py
├── prompt/              # Prompt templates
├── lib/                 # Libraries
├── utils/               # Utilities
└── requirements.txt
```

### 🔍 ScanModule (Port 8003)
**Chức năng**: Code Security Scanning Service
- Bearer Scanner integration
- SonarQube Scanner integration
- Extensible scanner registry
- Batch scanning

**Cấu trúc**:
```
ScanModule/
├── main.py              # FastAPI application
├── modules/             # Scanner implementations
│   ├── bearer.py
│   ├── sonar.py
│   ├── registry.py
│   └── base.py
├── lib/                 # Libraries
├── utils/               # Utilities
└── requirements.txt
```

### 📁 Projects Directory
**Chức năng**: Organized test projects and samples
```
projects/
├── demo_apps/           # Complete demo applications
│   └── Flask_App/
├── test_samples/        # Code samples for testing
│   └── SonarQ/
└── vulnerable_code/     # Security vulnerability examples
```

## 🚀 Khởi chạy các Module

### Khởi chạy tất cả module
```bash
# Terminal 1 - RagModule
cd RagModule
python main.py

# Terminal 2 - AutoFixModule  
cd AutoFixModule
python main.py

# Terminal 3 - ScanModule
cd ScanModule
python main.py
```

### Kiểm tra trạng thái
- RagModule: http://localhost:8001/docs
- AutoFixModule: http://localhost:8002/docs
- ScanModule: http://localhost:8003/docs

## 🔗 Tích hợp giữa các Module

### Workflow điển hình:
1. **ScanModule** quét code để tìm lỗi
2. **AutoFixModule** tự động sửa lỗi
3. **RagModule** lưu trữ và học từ các fix

### API Integration:
```python
# Scan code
response = requests.post("http://localhost:8003/api/v1/scan/single", json={
    "project_path": "./projects/demo_apps/Flask_App",
    "scanner_type": "bearer"
})

# Auto-fix issues
response = requests.post("http://localhost:8002/api/v1/fix/single", json={
    "file_path": "./projects/demo_apps/Flask_App/app.py",
    "template_type": "fix"
})

# Store in RAG
response = requests.post("http://localhost:8001/api/v1/rag-bugs/import", json={
    "bugs": [...],
    "generate_embeddings": True
})
```

## 📦 Dependencies

Mỗi module có file `requirements.txt` riêng:
- **RagModule**: FastAPI, MongoDB, Gemini AI
- **AutoFixModule**: FastAPI, Gemini AI, Jinja2
- **ScanModule**: FastAPI, Bearer, SonarQube

## 🔧 Cấu hình

Tạo file `.env` trong thư mục gốc:
```env
GEMINI_API_KEY=your_gemini_api_key
MONGODB_URI=your_mongodb_connection_string
SONAR_TOKEN=your_sonar_token
RAG_PORT=8001
AUTOFIX_PORT=8002
SCAN_PORT=8003
```

## 🧪 Testing

Mỗi module có thể được test độc lập:
```bash
# Test RagModule
curl http://localhost:8001/health

# Test AutoFixModule
curl http://localhost:8002/health

# Test ScanModule
curl http://localhost:8003/health
```

## 📈 Lợi ích của Modular Architecture

1. **Độc lập**: Mỗi module có thể phát triển và triển khai riêng
2. **Mở rộng**: Dễ dàng thêm scanner hoặc fixer mới
3. **Bảo trì**: Code được tổ chức rõ ràng theo chức năng
4. **Testing**: Test từng module một cách độc lập
5. **Deployment**: Triển khai theo nhu cầu (microservices)

## 🔄 Migration từ FixChain

Các thành phần đã được di chuyển:
- ✅ RAG functionality → RagModule
- ✅ Auto-fix functionality → AutoFixModule  
- ✅ Scanning functionality → ScanModule
- ✅ Shared libraries → Copied to each module
- ✅ Test projects → Organized in projects/

## 🎯 Roadmap

- [ ] API Gateway để tích hợp các module
- [ ] Shared authentication service
- [ ] Centralized logging và monitoring
- [ ] Docker containerization
- [ ] Kubernetes deployment configs