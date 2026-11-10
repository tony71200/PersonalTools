# Thiết kế tab Dung lượng cho Image Folder Studio

- **Ngày** 2026-11-10
- **Ứng dụng** `manager_image/image_folder_studio.py`
- **Môi trường** Python, PyQt5 và Qt 5.15 trên Windows

Tab thứ ba **Dung lượng** giúp xem nhanh dung lượng ổ đĩa và tìm thư mục chiếm nhiều chỗ trong một cây đã chọn. Tab có một nút **Chọn thư mục…**, một thanh tỷ lệ và một cây. Thông báo đang tải hoặc lỗi nằm cạnh thanh tỷ lệ. Mọi thao tác trong tab chỉ đọc.

## Mặc định — This PC

- Khi mở tab lần đầu, cây có nút gốc **This PC** và danh sách ổ đĩa Windows đang khả dụng. Lấy nhãn ổ và ký tự ổ, số byte tổng và còn trống từ thông tin ổ đĩa của Qt. Liệt kê mỗi ký tự ổ một lần theo thứ tự chữ cái. Ổ chưa sẵn sàng hoặc thiếu số liệu dung lượng được bỏ qua.
- Cây hiển thị tên ổ, dung lượng đã dùng, còn trống và tổng. Dung lượng đã dùng bằng tổng trừ dung lượng còn trống. Chọn một ổ để thanh hiển thị **đã dùng / tổng** của ổ đó. Khi chọn hàng **This PC**, thanh hướng dẫn chọn một ổ hoặc thư mục.
- Làm mới danh sách ổ khi vào chế độ **This PC**. Chế độ này chỉ đọc thông tin ổ đĩa và không quét cây thư mục của các ổ. Nếu không có ổ khả dụng, hiện thông báo cạnh thanh.

## Sau khi chọn thư mục

- Nút **Chọn thư mục…** mở hộp thoại chọn một thư mục gốc. Hủy hộp thoại giữ nguyên màn hình hiện tại. Khi xác nhận, cây hiện **This PC** ở đầu và trạng thái đang quét. Quét thư mục ở nền, không đọc nội dung file.
- Khi quét xong, cây hiển thị thư mục gốc và các thư mục con với cột tên và dung lượng. Mỗi thư mục cộng kích thước logic theo byte của các file thường trực tiếp và của tất cả thư mục con. Dung lượng của các file nằm trực tiếp ở gốc vẫn tính vào tổng. Cây chỉ có hàng thư mục. Mỗi nhóm thư mục cùng cấp được xếp theo số byte giảm dần, dùng tên thư mục khi số byte bằng nhau.
- Chọn thư mục gốc ngay khi có kết quả. Khi bấm vào một nhánh, thanh hiển thị **dung lượng nhánh / dung lượng thư mục gốc**. Ví dụ, `Ảnh — 3,2 GB / 10 GB (32%)`. Gốc có dung lượng lớn hơn 0 hiển thị 100%. Gốc có tổng 0 byte hiển thị `0 B / 0 B (—)` và thanh rỗng. Dùng đơn vị B, KB, MB, GB và TB theo hệ thập phân. Việc sắp xếp và tính tỷ lệ dùng số byte trước khi định dạng.
- Chọn hàng **This PC** để quay lại danh sách ổ đĩa và làm mới thông tin ổ. Có thể chọn thư mục khác ngay khi đang quét. Kết quả từ yêu cầu cũ bị bỏ qua sau khi chọn gốc mới hoặc quay lại **This PC**.

## Luồng xử lý và lỗi

- Tận dụng cách duyệt cây và xử lý liên kết của Image Folder Studio. Thu thập kích thước từ metadata đã đọc trong lượt quét rồi cộng từ lá về gốc. Bỏ qua symlink và junction. Chạy lấy thông tin ổ và quét thư mục bằng cơ chế tác vụ nền hiện có. Dữ liệu kết quả trở về luồng giao diện trước khi cập nhật cây và thanh.
- Nếu chỉ một số mục không đọc được, giữ số liệu từ các mục đọc được và hiện trạng thái **Dung lượng chưa đầy đủ** cạnh thanh. Hàng thư mục đọc lỗi có ghi chú theo đường dẫn. Nếu gốc không truy cập được, hiện lý do và để thanh trống. Người dùng có thể chọn lại thư mục hoặc quay về **This PC**.
- Số liệu thư mục là kích thước logic của file. Số liệu ổ lấy từ hệ thống. Hai chế độ dùng mẫu số riêng theo lựa chọn hiện tại.

## Tiêu chí kiểm tra

- Thay dữ liệu ổ đĩa bằng danh sách mẫu để kiểm tra thứ tự, bỏ ổ chưa sẵn sàng, tỷ lệ đã dùng và việc mở tab mà không quét cây ổ đĩa.
- Dùng thư mục tạm có file trực tiếp ở gốc, file lồng nhiều cấp, thư mục rỗng và nhánh lỗi đọc để đối chiếu tổng byte, thứ tự các hàng, tỷ lệ nhánh trên gốc và thông báo thiếu dữ liệu.
- Kiểm tra quay lại **This PC** và chọn gốc mới khi yêu cầu trước còn chạy. Kết quả cũ không được thay thế chế độ hay dữ liệu đang hiển thị.
- Mở cửa sổ PyQt5 và kiểm tra tab thứ ba có đủ nút chọn, thanh và cây. Chọn một ổ và một thư mục mẫu để kiểm tra nhãn, mẫu số và cách trình bày ở cả hai chế độ.
