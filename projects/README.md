# Projects Directory

Thư mục này chứa các source code mẫu và dự án để test các module của InnoLab.

## Cấu trúc thư mục

### 📁 demo_apps/
Chứa các ứng dụng demo hoàn chỉnh để test các chức năng:
- **Flask_App/**: Ứng dụng Flask với các lỗ hổng bảo mật mẫu
- Các ứng dụng web khác
- API services
- Microservices examples

### 📁 test_samples/
Chứa các mẫu code để test scanner và auto-fix:
- **SonarQ/**: Kết quả scan từ SonarQube
- Code samples với các loại lỗi khác nhau
- Unit test cases
- Integration test examples

### 📁 vulnerable_code/
Chứa các mẫu code có lỗ hổng bảo mật để test:
- SQL Injection examples
- XSS vulnerabilities
- CSRF examples
- Authentication bypass
- Authorization issues
- Input validation problems

## Cách sử dụng

### Với ScanModule
```bash
# Scan một project demo
curl -X POST "http://localhost:8003/api/v1/scan/single" \
  -H "Content-Type: application/json" \
  -d '{
    "project_path": "./projects/demo_apps/Flask_App",
    "scanner_type": "bearer"
  }'
```

### Với AutoFixModule
```bash
# Auto-fix một file
curl -X POST "http://localhost:8002/api/v1/fix/single" \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "./projects/demo_apps/Flask_App/app.py",
    "template_type": "fix"
  }'
```

### Với RagModule
```bash
# Import bugs vào RAG system
curl -X POST "http://localhost:8001/api/v1/rag-bugs/import" \
  -H "Content-Type: application/json" \
  -d '{
    "source_file": "./projects/test_samples/SonarQ/bearer_results/issues.json"
  }'
```

## Thêm project mới

1. **Demo Apps**: Thêm vào `demo_apps/` cho các ứng dụng hoàn chỉnh
2. **Test Samples**: Thêm vào `test_samples/` cho các mẫu code test
3. **Vulnerable Code**: Thêm vào `vulnerable_code/` cho các mẫu lỗ hổng bảo mật

## Best Practices

- Mỗi project nên có file `README.md` riêng
- Sử dụng `.gitignore` phù hợp
- Thêm `sonar-project.properties` cho SonarQube scan
- Bao gồm `requirements.txt` hoặc `package.json` cho dependencies
- Thêm test cases khi có thể

## Lưu ý bảo mật

⚠️ **CẢNH BÁO**: Thư mục `vulnerable_code/` chứa code có lỗ hổng bảo mật.
- Chỉ sử dụng cho mục đích testing
- Không deploy lên production
- Không chứa thông tin nhạy cảm thật
- Luôn chạy trong môi trường isolated