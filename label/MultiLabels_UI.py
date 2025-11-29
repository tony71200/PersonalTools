import os
import sys
import json
from typing import Dict, List

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt


IMG_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
LABEL_JSON_PATH = "labels.json"


def is_image_file(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in IMG_EXTENSIONS


# ======================= FlowLayout cho tag chip =======================

class FlowLayout(QtWidgets.QLayout):
    def __init__(self, parent=None, margin=0, spacing=4):
        super().__init__(parent)
        self.item_list: List[QtWidgets.QLayoutItem] = []
        self.setSpacing(spacing)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self.item_list.append(item)

    def count(self):
        return len(self.item_list)

    def itemAt(self, index):
        if 0 <= index < len(self.item_list):
            return self.item_list[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.item_list):
            return self.item_list.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.do_layout(QtCore.QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QtCore.QSize()
        for item in self.item_list:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QtCore.QSize(
            margins.left() + margins.right(),
            margins.top() + margins.bottom(),
        )
        return size

    def do_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_height = 0

        for item in self.item_list:
            wid = item.widget()
            space_x = self.spacing()
            space_y = self.spacing()
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(
                    QtCore.QRect(QtCore.QPoint(x, y), item.sizeHint())
                )

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y()


# ======================= Tag chip widget =======================

class TagChip(QtWidgets.QFrame):
    removed = QtCore.pyqtSignal(str)   # emit tag_text

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.tag_text = text

        self.setObjectName("TagChip")
        self.setStyleSheet("""
        #TagChip {
            border-radius: 12px;
            border: 1px solid #555;
            background-color: #2c2c2c;
        }
        QLabel {
            color: white;
        }
        QPushButton {
            border: none;
            background: transparent;
            color: #aaaaaa;
            font-weight: bold;
        }
        QPushButton:hover {
            color: #ff6666;
        }
        """)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(4)

        self.label = QtWidgets.QLabel(text)
        self.close_button = QtWidgets.QPushButton("×")
        self.close_button.setFixedSize(14, 14)
        self.close_button.clicked.connect(self._on_close_clicked)
        self.close_button.setVisible(False)

        layout.addWidget(self.label)
        layout.addWidget(self.close_button)

    def enterEvent(self, event: QtCore.QEvent):
        self.close_button.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent):
        self.close_button.setVisible(False)
        super().leaveEvent(event)

    def _on_close_clicked(self):
        self.removed.emit(self.tag_text)


# ======================= Data manager =======================

class LabelDataManager:
    """
    Quản lý JSON:
    {
      "label_names": {0: "tag1", 1: "tag2", ...},
      "list_image": [
        {
          "directory": "...full path...",
          "image_name": "...",
          "labels": "tag1,tag2"
        }, ...
      ]
    }
    """
    def __init__(self, json_path: str = LABEL_JSON_PATH):
        self.json_path = json_path
        self.label_names: Dict[int, str] = {}
        self.label_to_id: Dict[str, int] = {}
        self.image_entries: Dict[str, Dict] = {}  # key = full_path
        self._load()

    # ---------- IO ----------

    def _load(self):
        if not os.path.exists(self.json_path):
            self._init_empty()
            return
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            self._init_empty()
            return

        self.label_names = {
            int(k): v for k, v in data.get("label_names", {}).items()
        }
        self.label_to_id = {v: k for k, v in self.label_names.items()}

        self.image_entries.clear()
        for item in data.get("list_image", []):
            directory = item.get("directory", "")
            image_name = item.get("image_name", "")
            labels_str = item.get("labels", "").strip()
            full_path = os.path.join(directory, image_name)
            self.image_entries[full_path] = {
                "directory": directory,
                "image_name": image_name,
                "labels_str": labels_str,
            }

    def _init_empty(self):
        self.label_names = {}
        self.label_to_id = {}
        self.image_entries = {}

    def save(self):
        data = {
            "label_names": {int(k): v for k, v in self.label_names.items()},
            "list_image": []
        }
        for full_path, entry in self.image_entries.items():
            data["list_image"].append({
                "directory": entry["directory"],
                "image_name": entry["image_name"],
                "labels": entry.get("labels_str", ""),
            })

        os.makedirs(os.path.dirname(self.json_path) or ".", exist_ok=True)
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---------- Labels ----------

    def ensure_label(self, tag: str) -> int:
        tag = tag.strip()
        if not tag:
            return -1
        if tag in self.label_to_id:
            return self.label_to_id[tag]
        new_id = max(self.label_names.keys(), default=-1) + 1
        self.label_names[new_id] = tag
        self.label_to_id[tag] = new_id
        return new_id

    def get_all_labels(self) -> List[str]:
        return [self.label_names[k] for k in sorted(self.label_names.keys())]

    # ---------- Per-image labels ----------

    def get_image_labels(self, full_path: str) -> List[str]:
        if full_path not in self.image_entries:
            return []
        labels_str = self.image_entries[full_path].get("labels_str", "").strip()
        if not labels_str:
            return []
        return [t for t in labels_str.split(",") if t.strip()]

    def set_image_labels(self, full_path: str, tags: List[str]):
        tags = [t.strip() for t in tags if t.strip()]
        dir_path, fname = os.path.split(full_path)
        labels_str = ",".join(sorted(set(tags)))

        if full_path not in self.image_entries:
            self.image_entries[full_path] = {
                "directory": dir_path,
                "image_name": fname,
                "labels_str": labels_str,
            }
        else:
            self.image_entries[full_path]["labels_str"] = labels_str


# ======================= Main window =======================

class ImageTaggerWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Multi-label Image Tagger")
        self.resize(1400, 800)

        self.data_manager = LabelDataManager()
        self.auto_save = True

        self.image_paths: List[str] = []
        self.current_index: int = -1

        # map full_path -> tree item
        self.item_by_path: Dict[str, QtWidgets.QTreeWidgetItem] = {}

        self._setup_ui()
        self._refresh_global_label_list()
        self._update_autosave_state()

    # ---------- UI ----------

    def _setup_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        main_layout = QtWidgets.QHBoxLayout(central)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        splitter = QtWidgets.QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_middle_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 1)

    # ----- Left -----

    def _build_left_panel(self) -> QtWidgets.QWidget:
        group = QtWidgets.QGroupBox("Thư mục & ảnh")
        layout = QtWidgets.QVBoxLayout(group)

        # buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_load = QtWidgets.QPushButton("Load folder")
        self.btn_load.clicked.connect(self._on_load_folder)
        self.lbl_info_left = QtWidgets.QLabel("Checkbox chỉ để hiển thị trạng thái đã label.")
        self.lbl_info_left.setStyleSheet("color:#888; font-size:11px;")
        btn_layout.addWidget(self.btn_load)
        btn_layout.addStretch(1)

        # tree
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(False)
        self.tree.setHeaderLabels(["Tên", "Trạng thái"])
        self.tree.itemClicked.connect(self._on_tree_item_clicked)

        layout.addLayout(btn_layout)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.lbl_info_left)
        return group

    # ----- Middle -----

    def _build_middle_panel(self) -> QtWidgets.QWidget:
        group = QtWidgets.QGroupBox("Ảnh & Tag hiện tại")
        layout = QtWidgets.QVBoxLayout(group)

        # Nav
        nav_layout = QtWidgets.QHBoxLayout()
        self.btn_prev = QtWidgets.QPushButton("← Previous")
        self.btn_next = QtWidgets.QPushButton("Next →")
        self.btn_prev.clicked.connect(self._on_prev_image)
        self.btn_next.clicked.connect(self._on_next_image)
        self.lbl_current_path = QtWidgets.QLabel("No image selected")
        self.lbl_current_path.setStyleSheet("color:#aaa;")
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.btn_next)
        nav_layout.addStretch(1)
        nav_layout.addWidget(self.lbl_current_path)

        # Image display
        self.image_label = QtWidgets.QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumHeight(300)
        self.image_label.setStyleSheet("background-color:#202020; border:1px solid #444;")

        # Tags area
        tags_container = QtWidgets.QWidget()
        self.tags_layout = FlowLayout(tags_container, margin=4, spacing=4)

        tags_scroll = QtWidgets.QScrollArea()
        tags_scroll.setWidgetResizable(True)
        tags_scroll.setWidget(tags_container)
        tags_scroll.setMinimumHeight(120)
        tags_scroll.setStyleSheet("background:#141414; border:1px solid #444;")

        # Add tag input
        add_layout = QtWidgets.QHBoxLayout()
        self.tag_input = QtWidgets.QLineEdit()
        self.tag_input.setPlaceholderText("Nhập tag rồi nhấn Enter hoặc dấu +")
        self.tag_input.returnPressed.connect(self._on_add_tag_from_input)
        self.btn_add_tag = QtWidgets.QPushButton("+")
        self.btn_add_tag.setFixedWidth(40)
        self.btn_add_tag.clicked.connect(self._on_add_tag_from_input)
        add_layout.addWidget(self.tag_input, 1)
        add_layout.addWidget(self.btn_add_tag, 0)

        layout.addLayout(nav_layout)
        layout.addWidget(self.image_label, 3)
        layout.addWidget(QtWidgets.QLabel("Tag cho ảnh này:"))
        layout.addWidget(tags_scroll, 1)
        layout.addLayout(add_layout)

        return group

    # ----- Right -----

    def _build_right_panel(self) -> QtWidgets.QWidget:
        group = QtWidgets.QGroupBox("Tag global & Lưu dữ liệu")
        layout = QtWidgets.QVBoxLayout(group)

        layout.addWidget(QtWidgets.QLabel("Tất cả tag đã tạo:"))
        self.global_tag_list = QtWidgets.QListWidget()
        self.global_tag_list.itemClicked.connect(self._on_global_tag_clicked)
        layout.addWidget(self.global_tag_list, 3)

        self.chk_autosave = QtWidgets.QCheckBox("Auto-save JSON khi thay đổi")
        self.chk_autosave.setChecked(True)
        self.chk_autosave.stateChanged.connect(self._on_autosave_changed)
        layout.addWidget(self.chk_autosave)

        self.btn_save_json = QtWidgets.QPushButton("Save JSON ngay")
        self.btn_save_json.clicked.connect(self._on_save_json_clicked)
        layout.addWidget(self.btn_save_json)

        self.btn_convert_txt = QtWidgets.QPushButton("Convert → .txt cho từng ảnh")
        self.btn_convert_txt.clicked.connect(self._on_convert_txt_clicked)
        layout.addWidget(self.btn_convert_txt)

        layout.addStretch(1)
        return group

    # ======================= Folder / tree logic =======================

    def _on_load_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Chọn folder chứa ảnh", os.path.expanduser("~")
        )
        if not folder:
            return
        self._build_tree_from_folder(folder)

    def _build_tree_from_folder(self, root_folder: str):
        self.tree.clear()
        self.item_by_path.clear()
        self.image_paths.clear()
        self.current_index = -1
        self._set_image_pixmap(None)

        root_item = self._create_folder_item(root_folder, is_root=True)
        self.tree.addTopLevelItem(root_item)
        self.tree.expandItem(root_item)

        self._update_all_folder_check_state()

    def _create_folder_item(self, folder: str, is_root=False) -> QtWidgets.QTreeWidgetItem:
        name = os.path.basename(folder) or folder
        item = QtWidgets.QTreeWidgetItem([name, ""])
        item.setData(0, Qt.UserRole, ("folder", folder))

        # icon folder
        item.setIcon(0, self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon))

        # checkbox read-only: set checkstate nhưng bỏ UserCheckable
        item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable & ~Qt.ItemIsEditable)

        # children
        try:
            entries = sorted(os.listdir(folder))
        except Exception:
            entries = []

        for e in entries:
            full = os.path.join(folder, e)
            if os.path.isdir(full):
                child = self._create_folder_item(full)
                item.addChild(child)
            elif is_image_file(full):
                child = self._create_image_item(full)
                item.addChild(child)

        return item

    def _create_image_item(self, full_path: str) -> QtWidgets.QTreeWidgetItem:
        fname = os.path.basename(full_path)
        item = QtWidgets.QTreeWidgetItem([fname, ""])
        item.setData(0, Qt.UserRole, ("image", full_path))
        item.setIcon(0, self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon))
        item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable & ~Qt.ItemIsEditable)

        self.image_paths.append(full_path)
        self.item_by_path[full_path] = item

        # set check + text state dựa trên data
        self._update_image_item_state(item, full_path)
        return item

    def _update_image_item_state(self, item: QtWidgets.QTreeWidgetItem, full_path: str):
        tags = self.data_manager.get_image_labels(full_path)
        if tags:
            item.setCheckState(0, Qt.Checked)
            item.setText(1, "Labeled")
        else:
            item.setCheckState(0, Qt.Unchecked)
            item.setText(1, "")

    def _update_all_folder_check_state(self):
        def recurse(it: QtWidgets.QTreeWidgetItem):
            for i in range(it.childCount()):
                recurse(it.child(i))
            self._update_single_folder_check_state(it)

        for i in range(self.tree.topLevelItemCount()):
            recurse(self.tree.topLevelItem(i))

    def _update_single_folder_check_state(self, item: QtWidgets.QTreeWidgetItem):
        type_data = item.data(0, Qt.UserRole)
        if not type_data or type_data[0] != "folder":
            return

        total_images = 0
        labeled_images = 0

        def visit_children(it: QtWidgets.QTreeWidgetItem):
            nonlocal total_images, labeled_images
            for i in range(it.childCount()):
                child = it.child(i)
                dt = child.data(0, Qt.UserRole)
                if not dt:
                    continue
                if dt[0] == "image":
                    total_images += 1
                    if child.checkState(0) == Qt.Checked:
                        labeled_images += 1
                elif dt[0] == "folder":
                    visit_children(child)

        visit_children(item)

        if total_images == 0:
            item.setCheckState(0, Qt.Unchecked)
            item.setText(1, "")
        elif labeled_images == total_images:
            item.setCheckState(0, Qt.Checked)
            item.setText(1, f"{labeled_images}/{total_images}")
        else:
            item.setCheckState(0, Qt.Unchecked)
            item.setText(1, f"{labeled_images}/{total_images}")

    def _on_tree_item_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int):
        dt = item.data(0, Qt.UserRole)
        if not dt:
            return
        if dt[0] != "image":
            return
        full = dt[1]
        if full in self.image_paths:
            self.current_index = self.image_paths.index(full)
            self._load_current_image()

    # ======================= Image display & tags =======================

    def _load_current_image(self):
        if not (0 <= self.current_index < len(self.image_paths)):
            self.lbl_current_path.setText("No image selected")
            self._set_image_pixmap(None)
            self._clear_tag_widgets()
            return

        full = self.image_paths[self.current_index]
        self.lbl_current_path.setText(full)
        self._set_image_pixmap(full)

        tags = self.data_manager.get_image_labels(full)
        self._set_tag_widgets(tags)

        # chọn item trong tree cho đồng bộ
        item = self.item_by_path.get(full)
        if item:
            self.tree.setCurrentItem(item)

    def _set_image_pixmap(self, path: str | None):
        if path is None:
            self.image_label.setPixmap(QtGui.QPixmap())
            return
        pixmap = QtGui.QPixmap(path)
        if pixmap.isNull():
            self.image_label.setPixmap(QtGui.QPixmap())
            return
        scaled = pixmap.scaled(
            self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)

    def resizeEvent(self, event: QtGui.QResizeEvent):
        super().resizeEvent(event)
        # scale lại ảnh khi window resize
        if 0 <= self.current_index < len(self.image_paths):
            self._set_image_pixmap(self.image_paths[self.current_index])

    def _clear_tag_widgets(self):
        while self.tags_layout.count():
            item = self.tags_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _set_tag_widgets(self, tags: List[str]):
        self._clear_tag_widgets()
        for tag in sorted(set(tags)):
            self._add_single_tag_chip(tag)

    def _add_single_tag_chip(self, tag: str):
        chip = TagChip(tag)
        chip.removed.connect(self._on_tag_chip_removed)
        self.tags_layout.addWidget(chip)

    # ----- tag events -----

    def _on_add_tag_from_input(self):
        text = self.tag_input.text().strip()
        if not text:
            return
        self.tag_input.clear()
        self._add_tag_to_current_image(text)

    def _add_tag_to_current_image(self, tag: str):
        if not (0 <= self.current_index < len(self.image_paths)):
            return

        full = self.image_paths[self.current_index]
        # ensure label exists in vocab
        self.data_manager.ensure_label(tag)

        current_tags = self.data_manager.get_image_labels(full)
        if tag in current_tags:
            return
        current_tags.append(tag)
        self.data_manager.set_image_labels(full, current_tags)

        self._add_single_tag_chip(tag)
        # update left tree item
        item = self.item_by_path.get(full)
        if item:
            self._update_image_item_state(item, full)
            # update folder parents
            parent = item.parent()
            while parent:
                self._update_single_folder_check_state(parent)
                parent = parent.parent()

        self._refresh_global_label_list()
        self._maybe_save()

    def _on_tag_chip_removed(self, tag: str):
        if not (0 <= self.current_index < len(self.image_paths)):
            return
        full = self.image_paths[self.current_index]
        tags = self.data_manager.get_image_labels(full)
        if tag not in tags:
            return
        tags = [t for t in tags if t != tag]
        self.data_manager.set_image_labels(full, tags)

        # remove widget
        for i in range(self.tags_layout.count()):
            item = self.tags_layout.itemAt(i)
            w = item.widget()
            if isinstance(w, TagChip) and w.tag_text == tag:
                item = self.tags_layout.takeAt(i)
                w.deleteLater()
                break

        # update tree
        item_tree = self.item_by_path.get(full)
        if item_tree:
            self._update_image_item_state(item_tree, full)
            parent = item_tree.parent()
            while parent:
                self._update_single_folder_check_state(parent)
                parent = parent.parent()

        self._maybe_save()

    # ----- global tag list -----

    def _refresh_global_label_list(self):
        self.global_tag_list.clear()
        for tag in sorted(self.data_manager.get_all_labels()):
            self.global_tag_list.addItem(tag)

    def _on_global_tag_clicked(self, item: QtWidgets.QListWidgetItem):
        tag = item.text()
        self._add_tag_to_current_image(tag)

    # ----- navigation -----

    def _on_prev_image(self):
        if not self.image_paths:
            return
        if self.current_index <= 0:
            self.current_index = 0
        else:
            self.current_index -= 1
        self._load_current_image()

    def _on_next_image(self):
        if not self.image_paths:
            return
        if self.current_index < 0:
            self.current_index = 0
        elif self.current_index >= len(self.image_paths) - 1:
            self.current_index = len(self.image_paths) - 1
        else:
            self.current_index += 1
        self._load_current_image()

    # ----- autosave / save / convert txt -----

    def _on_autosave_changed(self, state: int):
        self.auto_save = (state == Qt.Checked)
        self._update_autosave_state()

    def _update_autosave_state(self):
        if self.auto_save:
            self.chk_autosave.setText("Auto-save JSON khi thay đổi (ON)")
        else:
            self.chk_autosave.setText("Auto-save JSON khi thay đổi (OFF)")

    def _maybe_save(self):
        if self.auto_save:
            self.data_manager.save()

    def _on_save_json_clicked(self):
        self.data_manager.save()
        QtWidgets.QMessageBox.information(self, "Saved", f"Đã lưu {LABEL_JSON_PATH}")

    def _on_convert_txt_clicked(self):
        # Tạo .txt cho từng ảnh
        count = 0
        for full, entry in self.data_manager.image_entries.items():
            labels_str = entry.get("labels_str", "").strip()
            if not labels_str:
                continue
            txt_path = os.path.splitext(full)[0] + ".txt"
            try:
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(labels_str)
                count += 1
            except Exception as e:
                print("Error writing txt for", full, e)

        QtWidgets.QMessageBox.information(
            self, "Convert xong",
            f"Đã tạo/ghi lại .txt cho {count} ảnh có label."
        )


def main():
    QtWidgets.QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QtWidgets.QApplication(sys.argv)

    # nếu bạn có file .qss thì load thêm
    if os.path.exists("MacOS.qss"):
        try:
            with open("MacOS.qss", "r", encoding="utf-8") as f:
                app.setStyleSheet(f.read())
        except Exception:
            pass

    w = ImageTaggerWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
