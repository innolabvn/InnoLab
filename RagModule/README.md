# RagModule - RAG Service

## 📋 Tổng quan

RagModule cung cấp dịch vụ RAG (Retrieval-Augmented Generation) với khả năng tìm kiếm vector, quản lý tài liệu và tích hợp AI.

## 🚀 Khởi chạy

```bash
cd RagModule
pip install -r requirements.txt
python main.py
```

Service sẽ chạy tại: http://localhost:8001

## 📁 Cấu trúc

```
RagModule/
├── main.py              # FastAPI application
├── controller/          # API controllers
│   ├── rag_controller.py      # RAG endpoints
│   └── rag_bug_controller.py  # Bug management
├── modules/             # Core modules
│   └── mongodb_service.py     # MongoDB operations
├── lib/                 # Shared libraries
├── utils/               # Utilities
└── requirements.txt     # Dependencies
```

## 🔧 API Endpoints

### RAG Operations
- `GET /api/v1/rag/search` - Vector search
- `POST /api/v1/rag/embed` - Generate embeddings
- `GET /api/v1/rag/collections` - List collections

### Bug Management
- `POST /api/v1/rag-bugs/import` - Import bugs
- `GET /api/v1/rag-bugs/search` - Search bugs
- `POST /api/v1/rag-bugs/generate-embeddings` - Generate embeddings

## ⚙️ Cấu hình

Tạo file `.env`:
```env
GEMINI_API_KEY=your_gemini_api_key
MONGODB_URI=mongodb://localhost:27017
RAG_PORT=8001
```

## 🧪 Testing

```bash
# Health check
curl http://localhost:8001/health

# API documentation
open http://localhost:8001/docs
```

## 📦 Dependencies

- FastAPI - Web framework
- MongoDB - Vector database
- Gemini AI - Embedding generation
- Uvicorn - ASGI server