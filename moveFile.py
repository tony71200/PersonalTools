import os
import shutil

# Nhập đường dẫn thư mục chính từ dòng lệnh
main_folder = input("Nhập đường dẫn thư mục chính: ")

# Đảm bảo đường dẫn là tuyệt đối
main_folder = os.path.abspath(main_folder)

# Duyệt qua toàn bộ thư mục con
for root, dirs, files in os.walk(main_folder):
    if root == main_folder:
        continue  # bỏ qua folder chính

    for file in files:
        # Kiểm tra phần mở rộng của ảnh
        if file.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')):
            src_path = os.path.join(root, file)
            dst_path = os.path.join(main_folder, file)

            # Nếu file trùng tên thì đổi tên
            counter = 1
            while os.path.exists(dst_path):
                name, ext = os.path.splitext(file)
                dst_path = os.path.join(main_folder, f"{name}_{counter}{ext}")
                counter += 1

            # Di chuyển ảnh
            shutil.move(src_path, dst_path)
            print(f"Đã chuyển: {src_path} → {dst_path}")
