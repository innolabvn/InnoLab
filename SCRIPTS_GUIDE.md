# 📜 InnoLab Scripts Guide

Hướng dẫn sử dụng các script tự động hóa cho InnoLab modular architecture.

## 🚀 Quick Start

### Cách đơn giản nhất (tương tự lệnh cũ):

```powershell
# Tương đương với: python run_demo.py --project Flask_App --scanners bearer --fixers llm --mode local
.\run_demo.ps1

# Hoặc với tùy chọn cụ thể
.\run_demo.ps1 -Project Flask_App -Scanner bearer -UseRag
```

## 📋 Available Scripts

### 1. `run_demo.ps1` - Demo Script (Recommended)
**Mục đích**: Script chính để chạy demo, tương tự như lệnh cũ

**Cú pháp**:
```powershell
.\run_demo.ps1 [options]
```

**Parameters**:
- `-Project`: Tên project (default: "Flask_App")
- `-Scanner`: Loại scanner ("bearer" | "sonar", default: "bearer")
- `-Fixer`: Loại fixer ("llm", default: "llm")
- `-Mode`: Chế độ ("local" | "api", default: "local")
- `-UseRag`: Sử dụng RAG service (switch)
- `-AutoStart`: Tự động khởi chạy services (default: true)

**Examples**:
```powershell
# Basic usage
.\run_demo.ps1

# Với RAG
.\run_demo.ps1 -UseRag

# Project khác
.\run_demo.ps1 -Project SonarQ -Scanner sonar

# Custom path
.\run_demo.ps1 -Project "./projects/vulnerable_code/example"
```

### 2. `start_services.ps1` - Services Manager
**Mục đích**: Khởi chạy tất cả các module services

**Cú pháp**:
```powershell
.\start_services.ps1 [options]
```

**Parameters**:
- `-SkipRag`: Bỏ qua RagModule (switch)
- `-WaitForServices`: Đợi services sẵn sàng (default: true)

**Examples**:
```powershell
# Khởi chạy tất cả services
.\start_services.ps1

# Chỉ Scan và AutoFix modules
.\start_services.ps1 -SkipRag

# Không đợi services ready
.\start_services.ps1 -WaitForServices:$false
```

### 3. `run_workflow.ps1` - Advanced Workflow
**Mục đích**: Workflow chi tiết với nhiều tùy chọn

**Cú pháp**:
```powershell
.\run_workflow.ps1 -ProjectPath <path> [options]
```

**Parameters**:
- `-ProjectPath`: Đường dẫn project (required)
- `-Scanner`: Loại scanner ("bearer" | "sonar")
- `-TemplateType`: Template ("fix" | "analyze" | "custom")
- `-UseRag`: Sử dụng RAG (switch)
- `-SkipScan`: Bỏ qua bước scan (switch)
- `-BatchFix`: Batch fix toàn bộ project (default: true)

**Examples**:
```powershell
# Full workflow
.\run_workflow.ps1 -ProjectPath "./projects/demo_apps/Flask_App"

# Chỉ fix, không scan
.\run_workflow.ps1 -ProjectPath "./projects/demo_apps/Flask_App" -SkipScan

# Với SonarQube
.\run_workflow.ps1 -ProjectPath "./projects/test_samples/SonarQ" -Scanner sonar
```

## 🎯 Workflow Comparison

### Cũ (FixChain):
```bash
cd FixChain/run
python run_demo.py --project Flask_App --scanners bearer --fixers llm --mode local
```

### Mới (Modular):
```powershell
# Option 1: Simple (recommended)
.\run_demo.ps1 -Project Flask_App -Scanner bearer

# Option 2: Manual control
.\start_services.ps1
.\run_workflow.ps1 -ProjectPath "./projects/demo_apps/Flask_App" -Scanner bearer
```

## 📊 Service Ports

| Service | Port | URL | Documentation |
|---------|------|-----|---------------|
| ScanModule | 8003 | http://localhost:8003 | http://localhost:8003/docs |
| AutoFixModule | 8002 | http://localhost:8002 | http://localhost:8002/docs |
| RagModule | 8001 | http://localhost:8001 | http://localhost:8001/docs |

## 📁 Project Structure

```
projects/
├── demo_apps/
│   └── Flask_App/          # Main demo application
├── test_samples/
│   └── SonarQ/             # SonarQube test samples
└── vulnerable_code/        # Security vulnerability examples
```

## 🔧 Troubleshooting

### Services không khởi chạy được
```powershell
# Kiểm tra port conflicts
netstat -an | findstr ":800"

# Khởi chạy manual từng service
cd ScanModule && python main.py
cd AutoFixModule && python main.py
cd RagModule && python main.py
```

### Project không tìm thấy
```powershell
# Liệt kê available projects
Get-ChildItem "./projects" -Recurse -Directory -Depth 2

# Sử dụng absolute path
.\run_demo.ps1 -Project "d:\InnoLab\projects\demo_apps\Flask_App"
```

### API calls thất bại
```powershell
# Test service health
Invoke-RestMethod -Uri "http://localhost:8003/health"
Invoke-RestMethod -Uri "http://localhost:8002/health"
Invoke-RestMethod -Uri "http://localhost:8001/health"
```

## 📈 Advanced Usage

### Custom Workflow
```powershell
# 1. Start only required services
.\start_services.ps1 -SkipRag

# 2. Run custom scan
$scanResult = Invoke-RestMethod -Uri "http://localhost:8003/api/v1/scan/single" -Method POST -ContentType "application/json" -Body '{
  "project_path": "./projects/demo_apps/Flask_App",
  "scanner_type": "bearer"
}'

# 3. Process results and fix
$fixResult = Invoke-RestMethod -Uri "http://localhost:8002/api/v1/fix/batch" -Method POST -ContentType "application/json" -Body '{
  "directory": "./projects/demo_apps/Flask_App",
  "template_type": "fix"
}'
```

### Batch Processing Multiple Projects
```powershell
$projects = @("Flask_App", "SonarQ")
foreach ($project in $projects) {
    .\run_workflow.ps1 -ProjectPath "./projects/demo_apps/$project" -Scanner bearer
}
```

## 📝 Results and Logging

- **Results**: Lưu trong thư mục `./results/`
- **Logs**: Mỗi module có logs riêng trong thư mục `logs/`
- **Reports**: JSON format với timestamp

## 🔄 Migration Notes

| Old Command | New Equivalent |
|-------------|----------------|
| `--project Flask_App` | `-Project Flask_App` |
| `--scanners bearer` | `-Scanner bearer` |
| `--fixers llm` | `-Fixer llm` (auto-mapped to template) |
| `--mode local` | `-Mode local` |
| N/A | `-UseRag` (new feature) |

## 💡 Tips

1. **Sử dụng `run_demo.ps1`** cho hầu hết các use cases
2. **Check service health** trước khi chạy workflow
3. **Sử dụng absolute paths** nếu gặp vấn đề với relative paths
4. **Monitor logs** trong các terminal windows riêng biệt
5. **Save results** được tự động thực hiện với timestamp