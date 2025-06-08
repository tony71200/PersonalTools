import sys
import os
import shutil
import csv
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QTreeWidget, QTreeWidgetItem, QListView,
    QLineEdit, QLabel, QTextEdit, QMessageBox, QSplitter, QGroupBox,
    QFormLayout, QTimeEdit, QComboBox, QCheckBox
)
from PyQt5.QtGui import QIcon, QStandardItemModel, QStandardItem
from PyQt5.QtCore import Qt, QSize, QTime

class ImageManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chương trình Quản lý Ảnh")
        self.setGeometry(100, 100, 900, 600)

        self.base_path = ""
        self.current_selected_folder = ""
        self.source_path = []
        self.destination_path = ""
        self.image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif']

        self.init_ui()

    def init_ui(self):
        # Main widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # --- Left Panel ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        self.btn_select_folder = QPushButton("Chọn Folder Chính")
        self.btn_select_folder.clicked.connect(self.select_base_folder)
        
        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderLabels(["Thư mục", "Số lượng ảnh"])
        self.folder_tree.setColumnWidth(0, 200)
        self.folder_tree.currentItemChanged.connect(self.on_folder_selection_changed)

        left_layout.addWidget(self.btn_select_folder)
        left_layout.addWidget(self.folder_tree)

        # --- Right Panel ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # --- Top Right (Thumbnails and Move Operations) ---
        top_right_splitter = QSplitter(Qt.Horizontal)

        # Thumbnail List
        self.thumbnail_list_view = QListView()
        self.thumbnail_list_view.setViewMode(QListView.IconMode)
        self.thumbnail_list_view.setIconSize(QSize(100, 100))
        self.thumbnail_list_view.setResizeMode(QListView.Adjust)
        self.thumbnail_list_view.setWordWrap(True)
        self.thumbnail_model = QStandardItemModel(self)
        self.thumbnail_list_view.setModel(self.thumbnail_model)

        # Move Operations Panel
        move_panel = QWidget()
        move_layout = QVBoxLayout(move_panel)
        move_layout.setAlignment(Qt.AlignTop)

        # Source
        source_layout = QHBoxLayout()
        self.lbl_source = QLabel("Nguồn:")
        self.txt_source = QLineEdit()
        self.txt_source.setReadOnly(True)
        self.btn_set_source = QPushButton(">>")
        self.btn_set_source.setToolTip("Đặt thư mục đang chọn làm NGUỒN")
        self.btn_set_source.clicked.connect(self.set_source)
        source_layout.addWidget(self.lbl_source)
        source_layout.addWidget(self.txt_source)
        source_layout.addWidget(self.btn_set_source)

        # Destination
        dest_layout = QHBoxLayout()
        self.lbl_dest = QLabel("Đích:  ")
        self.txt_dest = QLineEdit()
        self.txt_dest.setReadOnly(True)
        self.btn_set_dest = QPushButton(">>")
        self.btn_set_dest.setToolTip("Đặt thư mục đang chọn làm ĐÍCH")
        self.btn_set_dest.clicked.connect(self.set_destination)
        dest_layout.addWidget(self.lbl_dest)
        dest_layout.addWidget(self.txt_dest)
        dest_layout.addWidget(self.btn_set_dest)

        # Move Button
        self.btn_move = QPushButton("Chuyển Files")
        self.btn_move.clicked.connect(self.move_files)

        # --- Rename Panel ---
        rename_group = QGroupBox("Rename Folder")
        rename_layout = QFormLayout()
        rename_group.setLayout(rename_layout)

        # Time Range
        self.time_work_start = QTimeEdit(QTime(8, 0))
        self.time_work_start.setDisplayFormat("HH:mm")
        self.time_work_end = QTimeEdit(QTime(17, 0))
        self.time_work_end.setDisplayFormat("HH:mm")
        
        time_range_layout = QHBoxLayout()
        time_range_layout.addWidget(self.time_work_start)
        time_range_layout.addWidget(QLabel("đến"))
        time_range_layout.addWidget(self.time_work_end)
        rename_layout.addRow("Chọn khoảng thời gian:", time_range_layout)
        
        # Step
        self.combo_step = QComboBox()
        self.combo_step.addItems([str(i) for i in range(1, 7)])
        rename_layout.addRow("Chọn bước nhảy (giờ):", self.combo_step)

        # Start Time
        self.time_sequence_start = QTimeEdit(QTime(8, 0))
        self.time_sequence_start.setDisplayFormat("HH:mm")
        rename_layout.addRow("Chọn giờ bắt đầu:", self.time_sequence_start)

        # Patreon Checkbox
        self.chk_patreon = QCheckBox("Xử lý file prompt cho Patreon")
        rename_layout.addRow(self.chk_patreon)

        # Process Button
        self.btn_rename = QPushButton("Xử lí")
        self.btn_rename.clicked.connect(self.process_rename)
        rename_layout.addWidget(self.btn_rename)

        move_layout.addLayout(source_layout)
        move_layout.addLayout(dest_layout)
        move_layout.addWidget(self.btn_move)
        move_layout.addWidget(rename_group)
        
        move_panel.setLayout(move_layout)

        top_right_splitter.addWidget(self.thumbnail_list_view)
        top_right_splitter.addWidget(move_panel)
        top_right_splitter.setSizes([400, 250]) # Initial size distribution

        # --- Bottom Right (Log Box) ---
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)

        # Splitter for top and bottom right panels
        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.addWidget(top_right_splitter)
        right_splitter.addWidget(self.log_box)
        right_splitter.setSizes([400, 200])

        right_layout.addWidget(right_splitter)

        # --- Main Splitter ---
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(right_panel)
        main_splitter.setSizes([250, 650])

        main_layout.addWidget(main_splitter)

    def log(self, message):
        self.log_box.append(message)
        print(message)
        QApplication.processEvents() # Update UI

    def select_base_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Chọn thư mục chính")
        if path:
            self.base_path = path
            self.log(f"Đã chọn thư mục chính: {self.base_path}")
            self.populate_folder_tree()

    def count_images_in_folder(self, folder_path):
        count = 0
        try:
            for item in os.listdir(folder_path):
                if os.path.isfile(os.path.join(folder_path, item)):
                    if any(item.lower().endswith(ext) for ext in self.image_extensions):
                        count += 1
        except OSError as e:
            self.log(f"Lỗi khi truy cập {folder_path}: {e}")
        return count

    def populate_folder_tree(self):
        self.folder_tree.clear()
        if not self.base_path:
            return
        
        self.log("Bắt đầu quét các thư mục con...")
        try:
            for item in os.listdir(self.base_path):
                item_path = os.path.join(self.base_path, item)
                if os.path.isdir(item_path):
                    image_count = self.count_images_in_folder(item_path)
                    tree_item = QTreeWidgetItem(self.folder_tree, [item, str(image_count)])
                    tree_item.setData(0, Qt.UserRole, item_path) # Store full path
            self.log("Hoàn tất quét thư mục.")
        except OSError as e:
            self.log(f"Lỗi khi quét thư mục: {e}")

    def on_folder_selection_changed(self, current, previous):
        if current:
            self.current_selected_folder = current.data(0, Qt.UserRole)
            self.log(f"Đã chọn thư mục: {os.path.basename(self.current_selected_folder)}")
            self.populate_thumbnail_view()

    def populate_thumbnail_view(self):
        self.thumbnail_model.clear()
        if not self.current_selected_folder:
            return

        try:
            for item_name in os.listdir(self.current_selected_folder):
                if any(item_name.lower().endswith(ext) for ext in self.image_extensions):
                    full_path = os.path.join(self.current_selected_folder, item_name)
                    item = QStandardItem()
                    icon = QIcon(full_path)
                    item.setIcon(icon)
                    item.setText(item_name)
                    item.setEditable(False)
                    item.setData(full_path, Qt.UserRole)
                    self.thumbnail_model.appendRow(item)
        except OSError as e:
            self.log(f"Lỗi khi đọc ảnh thumbnail: {e}")

    def set_source(self):
        if self.current_selected_folder:
            self.source_path.append(self.current_selected_folder)
            src_txt = ",".join(self.source_path)
            self.txt_source.setText(src_txt)
            self.log(f"Đặt thư mục NGUỒN: {src_txt}")
            # self.source_path = self.current_selected_folder
            # self.txt_source.setText(self.source_path)
            # self.log(f"Đặt thư mục NGUỒN: {self.source_path}")
        else:
            self.log("Vui lòng chọn một thư mục từ danh sách bên trái trước.")

    def set_destination(self):
        if self.current_selected_folder:
            self.destination_path = self.current_selected_folder
            self.txt_dest.setText(self.destination_path)
            self.log(f"Đặt thư mục ĐÍCH: {self.destination_path}")
        else:
            self.log("Vui lòng chọn một thư mục từ danh sách bên trái trước.")

    def move_files(self):
        if not self.source_path and len(self.source_path) > 0 or not self.destination_path:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng đặt cả thư mục Nguồn và Đích.")
            return

        if self.destination_path in self.source_path:
            QMessageBox.warning(self, "Lỗi logic", "Thư mục Nguồn và Đích không được trùng nhau.")
            return
        txt_src = ','.join([os.path.basename(s) for s in self.source_path])
        reply = QMessageBox.question(self, 'Xác nhận di chuyển và xóa',
                                     f"Bạn có chắc muốn chuyển TẤT CẢ file từ:\n"
                                     f"Nguồn: {self.source_path}\n"
                                     f"Đến:\n"
                                     f"Đích: {self.destination_path}?\n\n"
                                     f"LƯU Ý: Thư mục nguồn '{txt_src}' sẽ bị XÓA sau khi hoàn tất.",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            for src in self.source_path:
                self.log(f"Bắt đầu di chuyển từ '{os.path.basename(src)}' đến '{os.path.basename(self.destination_path)}'...")
                try:
                    # 1. Move files
                    files_to_move = [f for f in os.listdir(src) if os.path.isfile(os.path.join(src, f))]
                    
                    if not files_to_move:
                        self.log("Thư mục nguồn không có file nào để chuyển.")
                    else:
                        for filename in files_to_move:
                            source_file = os.path.join(src, filename)
                            destination_file = os.path.join(self.destination_path, filename)
                            shutil.move(source_file, destination_file)
                            self.log(f"  - Đã chuyển: {filename}")
                        self.log("Di chuyển file hoàn tất!")

                    # 2. Delete source folder
                    self.log(f"Tiến hành xóa thư mục nguồn: {src}")
                    shutil.rmtree(src)
                    self.log("Đã xóa thư mục nguồn thành công.")

                except Exception as e:
                    self.log(f"Lỗi nghiêm trọng trong quá trình xử lý: {e}")
                    QMessageBox.critical(self, "Lỗi", f"Đã xảy ra lỗi: {e}")
            # 3. Reset paths and refresh UI
            self.source_path = []
            self.destination_path = ""
            self.txt_source.clear()
            self.txt_dest.clear()
            self.populate_folder_tree() # Refresh folder counts, this will reflect the deletion
            self.thumbnail_model.clear() 

    def update_patreon_csv(self, rename_map):
        csv_path = os.path.join(self.base_path, "group_prompt.csv")
        if not os.path.isfile(csv_path):
            self.log("Info: Cờ Patreon được chọn nhưng file 'group_prompt.csv' không tồn tại. Bỏ qua.")
            return

        self.log("Bắt đầu xử lý file 'group_prompt.csv' cho Patreon...")

        try:
            original_rows = []
            fieldnames = []
            # Read all data using DictReader for safety
            with open(csv_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                if not fieldnames:
                    self.log("Warning: file 'group_prompt.csv' trống hoặc không có header.")
                    return
                original_rows = list(reader)

            if not original_rows:
                self.log("Info: 'group_prompt.csv' không có dòng dữ liệu nào.")
                return

            folder_name_col = fieldnames[0]

            # Filter rows to keep only those corresponding to folders that will be renamed
            current_folder_names = {os.path.basename(p) for p in rename_map.keys()}
            filtered_data = [row for row in original_rows if row.get(folder_name_col) in current_folder_names]

            if len(filtered_data) < len(original_rows):
                self.log(f"  - Đã lọc CSV: giữ lại {len(filtered_data)} trên {len(original_rows)} dòng dữ liệu.")

            # Create a name-to-name map for renaming
            name_map = {os.path.basename(old): os.path.basename(new) for old, new in rename_map.items()}

            updated_data = []
            for row_dict in filtered_data:
                old_name = row_dict.get(folder_name_col)
                if old_name in name_map:
                    new_row_dict = row_dict.copy()
                    new_row_dict[folder_name_col] = name_map[old_name]
                    updated_data.append(new_row_dict)

            # Write the updated data back to the CSV using DictWriter
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(updated_data)

            self.log("Cập nhật file 'group_prompt.csv' thành công.")

        except Exception as e:
            self.log(f"Lỗi nghiêm trọng khi xử lý file 'group_prompt.csv': {e}")
            # Re-raise to stop the rename process
            raise Exception(f"Xử lý CSV thất bại, hủy thao tác đổi tên. Lỗi: {e}")

    def process_rename(self):
        self.log("Bắt đầu quá trình đổi tên hàng loạt...")

        if not self.base_path:
            QMessageBox.warning(self, "Chưa chọn thư mục", "Vui lòng chọn thư mục chính trước.")
            self.log("Lỗi: Chưa chọn thư mục chính.")
            return

        # Get all folder items from the tree
        root = self.folder_tree.invisibleRootItem()
        folder_items = []
        for i in range(root.childCount()):
            folder_items.append(root.child(i))

        if not folder_items:
            QMessageBox.information(self, "Không có thư mục", "Không có thư mục nào để đổi tên.")
            self.log("Không tìm thấy thư mục con nào để đổi tên.")
            return

        # Get parameters from UI
        work_start_time = self.time_work_start.time()
        work_end_time = self.time_work_end.time()
        step_hours = int(self.combo_step.currentText())
        current_time = self.time_sequence_start.time()
        day_counter = 1

        self.log(f"Cấu hình: Giờ làm việc {work_start_time.toString('HH:mm')}-{work_end_time.toString('HH:mm')}, bước nhảy {step_hours} giờ, bắt đầu từ {current_time.toString('HH:mm')}")

        reply = QMessageBox.question(self, 'Xác nhận Đổi Tên',
                                     f"Bạn có chắc muốn đổi tên {len(folder_items)} thư mục theo cấu hình đã chọn không?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            self.log("Người dùng đã hủy thao tác đổi tên.")
            return

        folders_to_rename = sorted([item.data(0, Qt.UserRole) for item in folder_items])
        
        rename_map = {}

        try:
            # First pass: generate all new names and check for conflicts
            for old_path in folders_to_rename:
                if current_time > work_end_time:
                    day_counter += 1
                    current_time = work_start_time

                am_pm = "am" if current_time.hour() < 12 else "pm"
                
                hour_12 = current_time.hour()
                if hour_12 == 0: hour_12 = 12
                elif hour_12 > 12: hour_12 -= 12

                new_folder_name = f"Day{day_counter}_{am_pm}_{hour_12}"
                new_path = os.path.join(self.base_path, new_folder_name)
                
                if old_path == new_path:
                    self.log(f"Bỏ qua: Tên mới '{new_folder_name}' trùng với tên cũ.")
                    current_time = current_time.addSecs(step_hours * 3600)
                    continue

                if new_path in rename_map.values() or os.path.exists(new_path):
                    self.log(f"Lỗi: Tên thư mục mới '{new_folder_name}' đã tồn tại hoặc bị trùng lặp. Hủy bỏ.")
                    QMessageBox.critical(self, "Lỗi Tên Bị Trùng", f"Tên thư mục mới '{new_folder_name}' đã tồn tại. Thao tác đã bị hủy.")
                    return

                rename_map[old_path] = new_path
                current_time = current_time.addSecs(step_hours * 3600)

            # Handle Patreon CSV processing if checked
            if self.chk_patreon.isChecked():
                self.update_patreon_csv(rename_map)

            # Second pass: perform the rename
            self.log(f"Thực hiện đổi tên cho {len(rename_map)} thư mục...")
            for old_path, new_path in rename_map.items():
                shutil.move(old_path, new_path)
                self.log(f"  - '{os.path.basename(old_path)}' -> '{os.path.basename(new_path)}'")
            
            self.log("Đổi tên hàng loạt hoàn tất!")

        except Exception as e:
            self.log(f"Lỗi nghiêm trọng trong quá trình đổi tên: {e}")
            QMessageBox.critical(self, "Lỗi", f"Đã xảy ra lỗi khi đổi tên: {e}")
        finally:
            self.populate_folder_tree()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_win = ImageManager()
    main_win.show()
    sys.exit(app.exec_()) 