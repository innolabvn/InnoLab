# Hướng Dẫn Chạy Dự Án ILA

Dự án ILA bao gồm hai phần chính:
1. **FixChain** - Hệ thống quản lý bug và RAG (Retrieval-Augmented Generation) với MongoDB và Gemini AI
2. **SonarQ** - Hệ thống phân tích code quality với SonarQube

## 📋 Yêu Cầu Hệ Thống

- Docker và Docker Compose
- Python 3.8+
- Git
- Ít nhất 4GB RAM (cho SonarQube)

## 🚀 Phần 1: FixChain - Hệ Thống Quản Lý Bug và RAG

### Cấu Trúc Dự Án
```
FixChain/
├── controller/          # API controllers
├── service/             # Business logic services  
├── lib/                 # Utilities và sample data
├── test/               # Test files
├── main.py             # Entry point
├── docker-compose.yml  # Docker configuration
└── requirements.txt    # Python dependencies
```

### Các Service
- **Bug Import API** (Port 8001) - Import và quản lý bugs
- **RAG MongoDB API** (Port 8000) - Document storage và AI Q&A
- **RAG Bug Management API** (Port 8002) - Bug management với AI

### Cách Chạy

#### Option 1: Docker (Khuyến nghị)

1. **Chuẩn bị môi trường:**
   ```bash
   cd FixChain
   ```

2. **Tạo file `.env`:**
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   MONGODB_URI=mongodb://mongodb:27017/rag_db
   ```

3. **Khởi động services:**
   ```bash
   docker-compose up -d
   ```

4. **Kiểm tra services:**
   - RAG API: http://localhost:8000/docs
   - MongoDB Express: http://localhost:8081
   - Bug Import API: http://localhost:8001/docs
   - RAG Bug API: http://localhost:8002/docs

#### Option 2: Local Development

1. **Cài đặt dependencies:**
   ```bash
   cd FixChain
   pip install -r requirements.txt
   ```

2. **Cấu hình `.env`:**
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   MONGODB_URI=your_local_mongodb_connection_string
   ```

3. **Chạy từng service:**
   ```bash
   # Terminal 1 - Bug Import API
   python -m controller.bug_controller
   
   # Terminal 2 - RAG API  
   python -m controller.rag_controller
   
   # Terminal 3 - RAG Bug Management API
   python -m controller.rag_bug_controller
   ```

### Testing
```bash
cd FixChain

# Test bug import
python test/test_bug_import.py

# Test CSV import
python test/test_csv_import.py

# Test RAG bug management
python test/test_rag_bug.py
```

### Sample Data
- `mocks/sample_bugs.csv` - Dữ liệu bug mẫu cho CSV import
- `mocks/sample_rag_bugs.json` - Dữ liệu bug mẫu cho RAG import
- `mocks/sample_rag_bug_detector.json` - Dữ liệu bug detector mẫu cho RAG import

---

## 🔍 Phần 2: SonarQ - Phân Tích Code Quality

### Cấu Trúc Dự Án
```
SonarQ/
├── docker-compose.yml      # SonarQube + PostgreSQL
├── export_issues.py        # Script export issues
├── export_to_file.py       # Export utility
└── sonar-project.properties # Cấu hình scan

projects/
└── demo_project/           # Dự án mẫu để scan
    ├── sonar-project.properties
    └── ... (mã nguồn cần kiểm tra)
```

Bạn có thể thêm testcase mới bằng cách tạo thư mục theo cấu trúc `projects/<tên_dự_án>` và đặt mã nguồn cùng file `sonar-project.properties` bên trong.

### Cách Chạy

#### Bước 1: Khởi động SonarQube

1. **Start SonarQube:**
   ```bash
   cd SonarQ
   docker-compose up -d
   ```

2. **Đợi services khởi động** (khoảng 2-3 phút)

3. **Truy cập SonarQube:**
   - URL: http://localhost:9000
   - Username: `admin`
   - Password: `admin` (sẽ được yêu cầu đổi lần đầu)

#### Bước 2: Tạo Token

1. Đăng nhập vào SonarQube
2. Vào **Administration** → **Security** → **Users**
3. Click **Tokens** của user admin
4. Tạo token mới và lưu lại

#### Bước 3: Cấu hình Token

Tạo file `.env` trong thư mục `SonarQ`:
```env
SONAR_TOKEN=your_sonar_token_here
```

#### Bước 4: Scan Project

**Cách 1: Sử dụng Docker Scanner (Khuyến nghị)**
```bash
cd SonarQ

# Load environment variables
$env:SONAR_TOKEN = "your_token_here"

# Scan project
docker run --rm `
  -e SONAR_HOST_URL="http://host.docker.internal:9000" `
  -e SONAR_LOGIN="$env:SONAR_TOKEN" `
  -v "${PWD}:/usr/src" `
  sonarsource/sonar-scanner-cli:latest
```

**Cách 2: Sử dụng batch file**
```bash
# Chỉnh sửa run_scan.bat với token của bạn
.\run_scan.bat
```

#### Bước 5: Export Issues

1. **Cài đặt Python dependencies:**
   ```bash
   pip install requests python-dotenv
   ```

2. **Export issues:**
   ```bash
   # Export với project key mặc định
   python export_issues.py my-service
   
   # Hoặc với custom host
   python export_issues.py my-service http://localhost:9000
   ```

3. **Kết quả:** File `issues_my-service.json` sẽ được tạo với format:
   ```json
   {
     "issues": [
       {
         "bug_id": "unique_issue_id",
         "rule_key": "rule_identifier", 
         "severity": "MAJOR|MINOR|CRITICAL|BLOCKER|INFO",
         "type": "BUG|VULNERABILITY|CODE_SMELL",
         "file_path": "relative/path/to/file.ext",
         "line": 123,
         "message": "Issue description",
         "status": "OPEN|CONFIRMED|RESOLVED",
         "code_excerpt": "Code context"
       }
     ]
   }
   ```

## 🔧 Troubleshooting

### FixChain Issues
- **MongoDB connection failed:** Kiểm tra MongoDB container đã chạy
- **Gemini API error:** Verify API key trong file `.env`
- **Port conflicts:** Đảm bảo ports 8000, 8001, 8002, 8081, 27017 không bị sử dụng

### SonarQ Issues
- **SonarQube không khởi động:** Đảm bảo có ít nhất 2GB RAM free
- **Scan failed:** Kiểm tra token và network connectivity
- **Export script error:** Verify project đã được scan và có issues

## 📝 Lưu Ý Quan Trọng

1. **Gemini API Key:** Cần đăng ký tại [Google AI Studio](https://makersuite.google.com/app/apikey)
2. **Memory Requirements:** SonarQube cần ít nhất 2GB RAM
3. **Network:** Đảm bảo các ports cần thiết không bị block
4. **Data Persistence:** Dữ liệu MongoDB và SonarQube được lưu trong Docker volumes

## 🚀 Quick Start (Chạy Cả Hai Dự Án)

```bash
# Terminal 1 - FixChain
cd FixChain
docker-compose up -d

# Terminal 2 - SonarQ  
cd ../SonarQ
docker-compose up -d

# Đợi 2-3 phút để services khởi động hoàn toàn
# Sau đó truy cập:
# - FixChain APIs: http://localhost:8000/docs, http://localhost:8001/docs, http://localhost:8002/docs
# - SonarQube: http://localhost:9000
# - MongoDB Express: http://localhost:8081
```

---

**Tác giả:** ILA Team  
**Cập nhật:** $(Get-Date -Format "yyyy-MM-dd")