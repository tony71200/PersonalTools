# Thiết kế Image Folder Studio

- **Ngày** 2026-11-09
- **File chạy** `manager_image/image_folder_studio.py`
- **Môi trường** Python, PyQt5 và Qt 5.15 trên Windows

Image Folder Studio là ứng dụng desktop độc lập gồm hai tab. Cửa sổ dùng thanh công cụ, tab, panel kéo đổi kích thước, thumbnail và vùng log theo cách bố trí của `video/ig_merge_video_ui.py`. Các thao tác duyệt thư mục và xem ảnh lấy tham chiếu từ `manager_image/manager_folder2.py`. File chạy có thể mở bằng `python manager_image/image_folder_studio.py` từ thư mục gốc repo.

## Tab 1 — So sánh thư mục

- Hai cột ngoài có nút **Chọn thư mục**, đường dẫn gốc, cây thư mục và lưới thumbnail. Chọn thư mục trong cây để xem các ảnh trực tiếp trong thư mục đó. Chọn ảnh trong cây hoặc lưới để mở thông tin tương ứng ở cột giữa.
- Nút **So sánh** quét ảnh trong hai thư mục đã chọn, gồm cả các cấp con. Đổi thư mục làm kết quả cũ mất hiệu lực. Log hiển thị số ảnh quét được, số tên chung và lỗi đọc nếu có.
- Đối chiếu bằng tên file đầy đủ gồm phần mở rộng và bỏ qua hoa/thường theo cách dùng trên Windows. Ví dụ `Ngay-01/Bien.JPG` khớp `Da-chon/bien.jpg`. `bien.png` là một tên khác. Đường dẫn và nội dung ảnh độc lập với kết quả khớp tên.
- Với mỗi ảnh ở A, tính là khớp nếu tên xuất hiện ít nhất một lần ở B. Tính tương tự cho B. Mỗi đường dẫn ảnh được tính một lần trong thư mục của nó. Nếu nhiều ảnh cùng tên nằm ở các nhánh khác nhau, hiển thị tất cả các đường dẫn tương ứng để người dùng kiểm tra.
- Cột giữa hiển thị **A có trong B** và **B có trong A**, mỗi tỷ lệ đi kèm số ảnh khớp trên tổng ảnh. Ví dụ với A có 4 ảnh, B có 5 ảnh và mỗi bên có 3 ảnh khớp, kết quả là `75% (3/4)` và `60% (3/5)`. Với bên không có ảnh, hiển thị `— (0/0)` và ghi trạng thái thư mục trống.
- Hàng trong cây và thumbnail của ảnh khớp có nền xanh cùng dấu ✓. Bộ lọc **Tất cả**, **Khớp tên** và **Chỉ có một bên** áp dụng đồng thời cho hai cột, giữ lại các nhánh chứa kết quả. Khi chọn ảnh, cột giữa hiển thị tên, trạng thái và đường dẫn tương đối của ảnh đó cùng mọi ảnh khớp bên kia. Tab này chỉ đọc file.

## Tab 2 — Quản lý thư mục

- Bên trái có nút **Chọn thư mục gốc** và cây thư mục. Mỗi nút thư mục hiển thị số thư mục con trực tiếp, tổng số thư mục ở các cấp bên dưới và tổng số ảnh trong nhánh. Cây cũng cho chọn các file trong nhánh đang duyệt.
- Bên phải có đường dẫn hiện tại, nút về thư mục cha và các nút thao tác. Chọn một thư mục để thấy lưới các thư mục con và file trực tiếp. Ô thư mục dùng ảnh đại diện từ nhánh nếu có, kèm tên và số ảnh. Chọn một ảnh để xem lớn theo đúng tỷ lệ. File khác hiển thị biểu tượng và thông tin tên, loại và kích thước.
- **Tạo thư mục số** tạo một thư mục dưới thư mục hiện tại. Nếu đang chọn file thì dùng thư mục chứa file. Tên lấy số lớn nhất trong các thư mục con có tên chỉ gồm chữ số rồi cộng một. Tên có tối thiểu ba chữ số, bắt đầu bằng `001`. Nếu tên đã có trên đĩa, thử số tiếp theo.
- **Sao chép** và **Di chuyển** áp dụng cho file đang chọn. Hộp thoại hiển thị file nguồn và cho chọn thư mục đích trong cây gốc. Nếu đích đã có file cùng tên thì báo xung đột và giữ cả hai file hiện có.
- **Xóa** hiển thị tên file và yêu cầu xác nhận trước khi chuyển vào Thùng rác qua Qt. Khi Thùng rác không khả dụng, hiển thị lỗi trong log và giữ file ở chỗ cũ.
- Sau mỗi thao tác, tải lại các nhánh bị ảnh hưởng, cập nhật số đếm và thumbnail, rồi ghi kết quả vào log. Tạo thư mục xong thì mở thư mục mới. Sau khi di chuyển hoặc xóa, giữ panel ở thư mục nguồn để tiếp tục duyệt.

## Luồng xử lý và giới hạn thao tác

- Tách xử lý đường dẫn, lập chỉ mục tên ảnh, tính tỷ lệ và thao tác file khỏi mã hiển thị. Hai tab dùng chung cách nhận diện định dạng ảnh và tạo thumbnail. Phần giao diện dùng PyQt5 và thư viện chuẩn, giữ độc lập với các thư viện xử lý video.
- Quét và đọc thumbnail ngoài luồng giao diện. Kết quả trả về theo thư mục đang mở, bỏ qua dữ liệu cũ nếu người dùng đổi thư mục giữa lúc quét. Dùng bộ nhớ đệm thumbnail có giới hạn và đọc ảnh lớn khi người dùng chọn ảnh.
- Kiểm tra thư mục gốc và đích trước khi thao tác. Bỏ qua liên kết và junction khi duyệt cây để giữ thao tác trong thư mục gốc và tránh vòng lặp. Ghi lỗi truy cập hoặc ảnh hỏng với đường dẫn liên quan. Kết quả so sánh có lỗi quét phải ghi rõ dữ liệu chưa đầy đủ. Ảnh có tên hợp lệ nhưng không đọc được thumbnail vẫn xuất hiện trong kết quả khớp tên.

## Tiêu chí kiểm tra

- Quét hai cây mẫu có ảnh cùng tên khác đường dẫn, tên khác hoa/thường, tên giống phần thân nhưng khác đuôi, nhiều đường dẫn cùng tên, ảnh lỗi và thư mục trống. Kiểm tra tỷ lệ từng bên, màu xanh, bộ lọc và đường dẫn đối ứng.
- Mở cây có nhiều cấp và đối chiếu số thư mục trực tiếp, tổng số thư mục con và số ảnh. Kiểm tra thumbnail, ảnh lớn và nút về thư mục cha.
- Dùng thư mục tạm để kiểm tra tạo số tiếp theo, sao chép, di chuyển, xung đột tên và thao tác xóa có xác nhận. Kiểm tra log và dữ liệu làm mới sau từng thao tác.
- Mở cả hai tab bằng PyQt5 và kiểm tra đổi thư mục trong khi quét, thu hẹp cửa sổ và kéo thay đổi độ rộng panel.
