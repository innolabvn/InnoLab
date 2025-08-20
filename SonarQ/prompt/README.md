# Prompt Templates

Thư mục này chứa các template Jinja2 cho việc tạo prompt AI theo mục đích sử dụng.

## Các file template:

- `fix.j2` - Template để sửa lỗi và cải thiện code
- `analyze.j2` - Template để phân tích và đánh giá code
- `custom.j2` - Template cho custom prompt do người dùng nhập

## Cách sử dụng:

Các template sử dụng Jinja2 syntax với các biến:
- `{{ original_code }}` - Code gốc cần xử lý
- `{{ custom_prompt }}` - Custom prompt (chỉ trong custom.j2)

## Tùy chỉnh:

Bạn có thể chỉnh sửa các template để thay đổi cách AI xử lý code:
1. Mở file template tương ứng (`fix.j2` hoặc `analyze.j2`)
2. Chỉnh sửa nội dung prompt
3. Lưu file
4. Chạy lại batch_fix.py

## Ví dụ template:

```jinja2
Hãy {{ action }} code này:

```
{{ original_code }}
```

Vui lòng:
1. {{ instruction_1 }}
2. {{ instruction_2 }}

{{ output_format }}
```

## Lợi ích của cách tiếp cận theo mục đích:

- **Linh hoạt**: Không bị giới hạn bởi ngôn ngữ lập trình
- **Đơn giản**: Ít template hơn, dễ quản lý
- **Mở rộng**: Dễ dàng thêm template mới cho mục đích khác
- **Nhất quán**: Cùng một cách tiếp cận cho mọi ngôn ngữ