# MultiLabels_UI

## Chức năng chính

- Load thư mục ảnh và duyệt ảnh theo cấu trúc cây thư mục.
- Hiển thị trạng thái ảnh đã được gán tag hay chưa.
- Xem và gán tag cho ảnh hiện tại bằng cả:
  - ô nhập text + nút thêm
  - click chọn tag từ `global_tag_tree`.
- Hỗ trợ tag nhóm (group) với giao diện cây của toàn bộ tag đã tạo.
- Auto-save JSON khi thay đổi hoặc lưu thủ công.
- Convert dữ liệu nhãn sang file `.txt` cho từng ảnh.
- Copy nhanh toàn bộ tag từ ảnh trước sang ảnh hiện tại.
- Loại bỏ tag không có trong `default_labels.json` từ tất cả ảnh.
- Rút gọn đường dẫn ảnh dài trong thông tin ảnh hiện tại để không làm vỡ layout.
- Cột `Tên`/`Trạng thái` trong cây thư mục có tỷ lệ phù hợp.

## Kiến trúc dữ liệu

- Dữ liệu nhãn được lưu vào file `labels.json` nằm trong cùng thư mục root của folder ảnh.
- Cấu trúc JSON:
  - `label_names`: bảng ID → tên tag.
  - `list_image`: danh sách ảnh kèm `directory`, `image_name`, `labels`.
- `default_labels.json` chứa nhóm tag mặc định và được tải khi app bắt đầu.
- `labels.json` sẽ được khởi tạo hoặc cập nhật khi load thư mục.

## Điều kiện và yêu cầu khi xây dựng ứng dụng cho nền tảng khác

### Kiến trúc chung

- Ứng dụng phải kiểm tra và load file `default_labels.json` khi khởi động.
- Khi load folder ảnh, phải tìm và load `labels.json` từ cùng folder đó.
- Nếu `labels.json` không tồn tại, cần tạo mới file này với các tag mặc định hiện có.
- Nếu `labels.json` đã tồn tại nhưng thiếu các tag mới từ `default_labels.json`, cần cập nhật lại `labels.json` để bổ sung.
- Đảm bảo đường dẫn ảnh trong `labels.json` được chuẩn hóa để phù hợp với folder hiện tại.

### Web UI

- Hiển thị danh sách tag default rõ ràng, không ẩn tag mặc định vào menu ẩn.
- Cần có phần tree hoặc list nhóm tag dễ thao tác, để người dùng nhìn thấy tất cả tag cùng lúc.
- Checkbox hay toggle cho từng tag phải đồng bộ với ảnh đang chọn.
- Phần tag mặc định nên luôn xuất hiện trong danh sách và được ưu tiên hiển thị.
- Giữ nguyên chức năng auto-save / save thủ công khi sync dữ liệu JSON.

### Mobile app

- Thiết kế ưu tiên hiển thị các tag mặc định, không ẩn chúng đi sau menu collapsible.
- Nên có thanh tìm kiếm hoặc bộ lọc tag để dùng trên màn hình nhỏ.
- Cần hỗ trợ touch dễ dàng để chọn / bỏ chọn tag.
- Với app mobile, nên giữ `default_labels` luôn hiển thị ở mức độ cao, tránh ẩn trong sub-menu.
- Hỗ trợ lưu nhãn offline với file `labels.json` cùng folder (hoặc trong storage tương đương) và sync khi cần.

### Cross-platform / Desktop

- Ứng dụng desktop cần hỗ trợ load folder ảnh bằng file picker.
- Cần đảm bảo xử lý đúng đường dẫn trên Windows / macOS / Linux.
- `labels.json` phải nằm cùng thư mục gốc với ảnh, hoặc cấu trúc tương tự dễ tìm.
- Khuyến nghị: không dùng đường dẫn lưu tuyệt đối khi có thể tránh được, hoặc chuẩn hóa lại khi folder thay đổi.

## Lưu ý về `json` và cách check

- Luôn kiểm tra tồn tại của `default_labels.json` trước khi dùng.
- Load `labels.json` từ thư mục ảnh hiện tại:
  - nếu file tồn tại, parse JSON.
  - nếu parse lỗi, khởi tạo lại dữ liệu mặc định để tránh crash.
- Với `default_labels.json`, nếu file bị lỗi hoặc thiếu, app nên fallback an toàn và thông báo.
- `labels.json` phải được lưu lại sau mỗi thay đổi nếu auto-save bật, hoặc khi user nhấn lưu.

## Ưu tiên hiển thị tag default

- Với UI web hoặc mobile, phần tag default nên luôn hiện ra, không ẩn sau các tùy chọn mở rộng.
- Tag mặc định cần được hiển thị rõ ràng theo nhóm, để người dùng dễ gán.
- Tránh thiết kế chỉ cho phép add tag qua tìm kiếm; nên vẫn có danh sách hiển thị trực tiếp.
- Khi có tag mới tạo, vẫn nên giữ `default_labels` xuất hiện cùng với tag custom.

## Gợi ý mở rộng

- Thêm chức năng filter ảnh theo trạng thái đã label / chưa label.
- Thêm tìm kiếm tag trong `global_tag_tree`.
- Thêm chế độ dark/light theme cho web/mobile.
- Thêm export dữ liệu nhãn sang định dạng khác như CSV hoặc YAML.
