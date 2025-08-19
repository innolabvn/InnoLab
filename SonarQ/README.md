# SonarQube Setup và Export Issues

## 1. Khởi động SonarQube

```bash
docker compose up -d
```

> **Lưu ý:** Setup này sử dụng SonarQube 10 Community Edition (phiên bản mới nhất)

Truy cập http://localhost:9000
- Username: admin
- Password: admin (sẽ được yêu cầu đổi lần đầu)

## 2. Tạo Token

1. Đăng nhập vào SonarQube
2. Vào **Administration** → **Security** → **Users**
3. Click vào **Tokens** của user admin
4. Tạo token mới và lưu lại

## 3. Cấu hình Token

Tạo file `.env` trong thư mục project với nội dung:
```
SONAR_TOKEN=your_token_here
```

## 4. Scan Project

### Cách 1: Sử dụng Docker Scanner

```bash
# Load token từ file .env
source .env

# Chạy scan từ thư mục root của project cần scan
docker run --rm \
  -e SONAR_HOST_URL="http://host.docker.internal:9000" \
  -e SONAR_LOGIN="$SONAR_TOKEN" \
  -v "$PWD:/usr/src" \
  sonarsource/sonar-scanner-cli:latest
```

### Cách 2: Sử dụng sonar-scanner local

```bash
# Cài đặt sonar-scanner
# Download từ https://docs.sonarqube.org/latest/analysis/scan/sonarscanner/

# Chạy scan
sonar-scanner \
  -Dsonar.projectKey=my-service \
  -Dsonar.sources=src \
  -Dsonar.host.url=http://localhost:9000 \
  -Dsonar.login=$SONAR_TOKEN
```

## 5. Export Issues

```bash
# Cài đặt dependencies (requests, python-dotenv, aider-chat)
pip install -r requirements.txt

# Export issues (script sẽ tự động load token từ .env)
python export_issues.py my-service

# Hoặc với custom host
python export_issues.py my-service http://localhost:9000
```

## 6. Cấu trúc Output JSON

Script sẽ xuất JSON với cấu trúc:

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
      "resolution": null,
      "created_at": "2024-01-01T00:00:00+0000",
      "updated_at": "2024-01-01T00:00:00+0000",
      "rule_description": "Detailed rule description",
      "code_excerpt": "Code context around the issue"
    }
  ]
}
```

## Troubleshooting

### SonarQube không khởi động được
- Kiểm tra Docker có đủ memory (ít nhất 2GB)
- Đợi PostgreSQL khởi động hoàn toàn trước khi SonarQube start

### Upgrade từ phiên bản cũ
Nếu bạn đang sử dụng phiên bản SonarQube cũ:
```bash
# Dừng containers hiện tại
docker compose down

# Pull image mới
docker compose pull

# Khởi động lại với phiên bản mới
docker compose up -d
```

### Scan bị lỗi
- Đảm bảo `sonar-project.properties` có đúng cấu hình
- Kiểm tra token có quyền scan project
- Đảm bảo network connectivity giữa scanner và SonarQube

### Export script bị lỗi
- Kiểm tra SONAR_TOKEN đã được set
- Đảm bảo project đã được scan và có issues
- Kiểm tra project key có đúng không