# Template Usage Logging Guide

## Tổng quan

Script `batch_fix.py` tự động ghi lại thông tin chi tiết về việc sử dụng template và phản hồi AI vào file log để phân tích và đánh giá hiệu quả.

## Vị trí Log Files

Log files được lưu tại: `./logs/template_usage_TIMESTAMP.log`

Ví dụ: `./logs/template_usage_20250820_153121.log`

## Cấu trúc Log Entries

### 1. TEMPLATE_USAGE

Ghi lại thông tin về template được sử dụng:

```json
{
  "file_path": "path/to/file.py",
  "template_type": "fix|analyze|custom",
  "custom_prompt": "Custom prompt text hoặc null",
  "prompt_length": 2789,
  "prompt_preview": "200 ký tự đầu của prompt..."
}
```

### 2. AI_RESPONSE

Ghi lại thông tin về phản hồi từ AI:

```json
{
  "file_path": "path/to/file.py",
  "raw_response_length": 1140,
  "cleaned_response_length": 1108,
  "response_preview": "200 ký tự đầu của response..."
}
```

## Các Template Types

1. **fix**: Template mặc định từ `prompt/fix.j2`
2. **analyze**: Template phân tích từ `prompt/analyze.j2`
3. **custom**: Template tùy chỉnh từ `prompt/custom.j2` (khi dùng --prompt)

## Cách sử dụng Logs để đánh giá

### 1. Phân tích hiệu quả Template

```bash
# Tìm các template được sử dụng nhiều nhất
grep "TEMPLATE_USAGE" logs/template_usage_*.log | grep -o '"template_type":"[^"]*"' | sort | uniq -c

# Kiểm tra độ dài prompt trung bình
grep "prompt_length" logs/template_usage_*.log | grep -o '"prompt_length":[0-9]*' | cut -d: -f2 | awk '{sum+=$1; count++} END {print "Average:", sum/count}'
```

### 2. Phân tích chất lượng Response

```bash
# So sánh độ dài raw vs cleaned response
grep "AI_RESPONSE" logs/template_usage_*.log | grep -o '"raw_response_length":[0-9]*\|"cleaned_response_length":[0-9]*'

# Tìm các file có response dài bất thường
grep "raw_response_length" logs/template_usage_*.log | awk -F'[,:]' '{if($4 > 5000) print $0}'
```

### 3. Theo dõi Custom Prompts

```bash
# Liệt kê tất cả custom prompts đã sử dụng
grep "custom_prompt" logs/template_usage_*.log | grep -v '"custom_prompt":null' | grep -o '"custom_prompt":"[^"]*"'
```

## Ví dụ Log thực tế

### Template Usage với fix template:
```
2025-08-20 15:29:47,793 - INFO - TEMPLATE_USAGE: {"file_path": "test_log\\test_simple.py", "template_type": "fix", "custom_prompt": null, "prompt_length": 2789, "prompt_preview": "### Role\nYou are a Senior Software Engineer..."}
```

### Template Usage với custom prompt:
```
2025-08-20 15:31:21,849 - INFO - TEMPLATE_USAGE: {"file_path": "test_custom\\test_custom.py", "template_type": "fix", "custom_prompt": "Chuyển đổi code Python 2 sang Python 3", "prompt_length": 240, "prompt_preview": "Chuyển đổi code Python 2 sang Python 3\n\nCode cần sửa..."}
```

### AI Response:
```
2025-08-20 15:31:23,642 - INFO - AI_RESPONSE: {"file_path": "test_custom\\test_custom.py", "raw_response_length": 123, "cleaned_response_length": 108, "response_preview": "# Test file for custom prompt\ndef hello():\n    print(\"Hello world\")..."}
```

## Lưu ý

- Log files được tạo mới cho mỗi lần chạy script
- Logs chỉ được tạo khi chạy ở chế độ `--fix`, không có logs cho `--scan-only`
- Mỗi lần retry sẽ tạo thêm log entries
- Log files sử dụng encoding UTF-8 để hỗ trợ tiếng Việt

## Phân tích nâng cao

Bạn có thể sử dụng Python để phân tích logs:

```python
import json
import re
from collections import Counter

def analyze_logs(log_file):
    template_types = []
    prompt_lengths = []
    response_lengths = []
    
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            if 'TEMPLATE_USAGE' in line:
                data = json.loads(line.split('TEMPLATE_USAGE: ')[1])
                template_types.append(data['template_type'])
                prompt_lengths.append(data['prompt_length'])
            elif 'AI_RESPONSE' in line:
                data = json.loads(line.split('AI_RESPONSE: ')[1])
                response_lengths.append(data['cleaned_response_length'])
    
    print(f"Template types: {Counter(template_types)}")
    print(f"Average prompt length: {sum(prompt_lengths)/len(prompt_lengths):.1f}")
    print(f"Average response length: {sum(response_lengths)/len(response_lengths):.1f}")

# Sử dụng:
# analyze_logs('./logs/template_usage_20250820_153121.log')
```