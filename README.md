# PersonalTools

Bộ sưu tập các script hỗ trợ quản lý ảnh, video và prompt sáng tạo nội dung.

## Cấu trúc thư mục

```
PersonalTools/
├── README.md — Giới thiệu dự án và sơ đồ thư mục.
├── helper/ — Các tiện ích thao tác file và metadata.
│   ├── ReadMeta.py — Trích xuất metadata từ PNG rồi lưu ra TXT/JSON/CSV.
│   ├── batch_prompt_advanced.py — Tiện ích Gradio tạo loạt prompt cho Stable Diffusion.
│   ├── model_filter.py — Lọc ảnh theo metadata model và Lora hash.
│   ├── moveFile.py — Gom toàn bộ ảnh từ thư mục con về thư mục gốc, tránh trùng tên.
│   └── rename_schedule_folder.py — Đổi tên loạt thư mục theo lịch đăng tải.
├── manager_image/ — Công cụ sắp xếp và phân loại hình ảnh.
│   ├── MacOS.qss — Giao diện tối ưu cho macOS.
│   ├── classifyNSFW.py — Phân loại ảnh an toàn/nhạy cảm bằng NudeNet.
│   ├── cluster_image.py — Gom cụm ảnh dựa trên metadata và từ khóa.
│   ├── manager_folder2.py — Tổ chức thư mục ảnh theo cấu hình mạng xã hội.
│   └── softChoice.py — Lọc ảnh có khuôn mặt và gom nhóm bằng CLIP + InsightFace.
├── prompt/ — Xử lý và chuẩn hoá prompt.
│   ├── groupPrompt_v2.py — Gom nhóm prompt theo độ tương đồng và tóm tắt từ khóa.
│   ├── replace_sensitive_word.py — Thay thế từ ngữ nhạy cảm trong prompt.
│   ├── rewritePrompt_v2.py — Viết lại prompt với tham số tùy chỉnh.
│   ├── sensitive_prompt_keywords_v2.json — Bộ từ khóa nhạy cảm mở rộng.
│   └── splitprompt2file.py — Tách prompt dài thành nhiều file nhỏ.
└── video/ — Công cụ xử lý video.
    ├── MacOS.qss — Tệp giao diện cho ứng dụng video trên macOS.
    ├── __init__.py — Đánh dấu thư mục video là gói Python.
    ├── decode_logo_base64.py — Giải mã logo mặc định từ chuỗi base64.
    ├── default_logo.png — Logo mẫu sử dụng khi ghép video.
    ├── ig_merge_video_cmd.py — Logic ghép video Instagram ở dạng dòng lệnh.
    ├── ig_merge_video_ui.py — Giao diện PyQt5 để xem trước và ghép video.
    └── make_instagram_video.py — Tạo video định dạng Instagram từ ảnh/dữ liệu đầu vào.
```

## Sử dụng nhanh

Mỗi thư mục con chứa script độc lập; hãy đọc phần đầu file tương ứng để biết cách chạy và yêu cầu phụ thuộc.
