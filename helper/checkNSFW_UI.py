import os
import sys
import shutil
from typing import List

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread

import numpy as np
from PIL import Image
# try:
#     from nsfw_image_detector import NSFWDetector
# except ImportError:
#     # Install nfsw_image_detector via pip if not found
#     is_success = os.system(f"{sys.executable} -m pip install nsfw-image-detector")
#     if not is_success:
#         print("Module 'nsfw_image_detector' not found. Please install it to use NSFW detection. pip install nsfw-image-detector")
#         sys.exit(1)
#     else:
#         from nsfw_image_detector import NSFWDetector
from nsfw_image_detector import NSFWDetector

class NSFWImageDetector:
    def __init__(self):
        self.detector = NSFWDetector()

    def is_nsfw(self, image_path: str) -> bool:
        image = Image.open(image_path)
        return self.detector.is_nsfw(image)

    def predict_proba(self, image_path: str) -> dict:
        image = Image.open(image_path)
        return self.detector.predict_proba(image)
    
    def check_image(self, image_path: str):
        proba_dict = self.predict_proba(image_path)[0]
        HighRisk_Proba = proba_dict["high"]
        MediumRisk_Proba = proba_dict["medium"]
        LowRisk_Proba = proba_dict["low"]

        is_unsafe = HighRisk_Proba > 0.7 and MediumRisk_Proba > 0.6 and LowRisk_Proba > 0.5
        is_low_risk = LowRisk_Proba > 0.9
        return is_unsafe, is_low_risk, proba_dict


IMG_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
SETTING_ORG = "LongTools"
SETTING_APP = "NSFW_SFW_Filter"


def is_image_file(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in IMG_EXTENSIONS

def truncate_text(text, font, max_width):
    metrics = QtGui.QFontMetrics(font)
    return metrics.elidedText(text, Qt.ElideRight, max_width)

class NSFWModelManager:
    def __init__(self):
        self.detector = NSFWImageDetector()
        pass

    def check_image(self, image_path: str):
        is_unsafe, is_low_risk, proba_dict = self.detector.check_image(image_path)
        return is_unsafe, is_low_risk, proba_dict




# def load_nsfw_models() -> NSFWModelManager:
#     """
#     Gọi 1 lần ở đầu chương trình/UI để load model.
#     """
#     global _model_manager
#     _model_manager = NSFWModelManager(
        
#     )
#     return _model_manager


# def get_nsfw_manager() -> NSFWModelManager:
#     """
#     Lazy init: nếu chưa load_nsfw_models() thì tự load với default.
#     """
#     global _model_manager
#     if _model_manager is None:
#         _model_manager = NSFWModelManager()
#     return _model_manager


# def NSFW_check_image(image_path: str) -> tuple[bool, bool]:
#     """
#     Hàm đơn giản cho UI dùng:
#     - True: NSFW
#     - False: SFW
#     (Model chỉ load lần đầu, lần sau dùng lại)
#     """
#     manager = get_nsfw_manager()
#     is_unsafe, is_low_risk, _ = manager.check_image(image_path)
#     return is_unsafe, is_low_risk



class FolderFilterWorker(QObject):
    """
    Worker chạy trong QThread:
    - Nhận list folder cần xử lý + output_folder
    - Duyệt ảnh, check NSFW, copy SFW vào output_folder
    - Bắn signal về UI: tiến độ + ảnh mới copy
    """

    progress_folder = pyqtSignal(int, int, str)  # current, total, folder_path
    progress_percent = pyqtSignal(int)          # 0–100
    file_copied = pyqtSignal(str)              # dst_path
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, folders: List[str], output_folder: str, parent=None, model_manager: NSFWModelManager | None = None):
        super().__init__(parent)
        self.folders = folders
        self.output_folder = output_folder
        self._cancelled = False
        self._model_manager = model_manager or NSFWModelManager()

    @QtCore.pyqtSlot()
    def run(self):
        try:
            if not self.folders:
                self.finished.emit()
                return

            total_folders = len(self.folders)
            os.makedirs(self.output_folder, exist_ok=True)

            for idx, folder in enumerate(self.folders, start=1):
                if self._cancelled:
                    break

                self.progress_folder.emit(idx, total_folders, folder)

                # Gom tất cả ảnh trong folder (đệ quy)
                image_paths: List[str] = []
                for root, _, files in os.walk(folder):
                    for f in files:
                        full = os.path.join(root, f)
                        if is_image_file(full):
                            image_paths.append(full)

                # Nếu không có ảnh thì skip
                if not image_paths:
                    # update % luôn cho folder này
                    percent = int(idx * 100 / total_folders)
                    self.progress_percent.emit(percent)
                    continue

                for img_path in image_paths:
                    if self._cancelled:
                        break
                    try:
                        # NSFW_check_image: NSFW -> True, SFW -> False
                        # is_unsafe, is_lowRisk = NSFW_check_image(img_path)
                        if self._model_manager is None:
                            raise RuntimeError("Model manager not initialized.")
                        is_unsafe, is_lowRisk, _ = self._model_manager.check_image(img_path)
                        dst_name = os.path.basename(img_path)
                        if is_lowRisk:
                            # cảnh báo low-risk
                            print(f"Cảnh báo Low-Risk NSFW: {img_path}")
                            lowRisk_folder = os.path.join(os.path.dirname(self.output_folder), "low_risk")
                            os.makedirs(lowRisk_folder, exist_ok=True)
                            
                            dst_path = os.path.join(lowRisk_folder, dst_name)

                            if os.path.exists(dst_path):
                                base, ext = os.path.splitext(dst_name)
                                k = 1
                                while True:
                                    new_name = f"{base}_{k}{ext}"
                                    new_dst = os.path.join(lowRisk_folder, new_name)
                                    if not os.path.exists(new_dst):
                                        dst_path = new_dst
                                        break
                                    k += 1

                            shutil.copy2(img_path, dst_path)

                        if not is_unsafe:
                            # copy sang output folder.
                            # giữ tên file, nếu trùng thì thêm số đuôi
                            dst_path = os.path.join(self.output_folder, dst_name)

                            if os.path.exists(dst_path):
                                base, ext = os.path.splitext(dst_name)
                                k = 1
                                while True:
                                    new_name = f"{base}_{k}{ext}"
                                    new_dst = os.path.join(self.output_folder, new_name)
                                    if not os.path.exists(new_dst):
                                        dst_path = new_dst
                                        break
                                    k += 1

                            shutil.copy2(img_path, dst_path)
                            self.file_copied.emit(dst_path)
                    except Exception as e:
                        # không dừng toàn bộ, chỉ báo lỗi
                        self.error.emit(f"Lỗi khi xử lý ảnh {img_path}: {e}")

                percent = int(idx * 100 / total_folders)
                self.progress_percent.emit(percent)

        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()

    def cancel(self):
        self._cancelled = True


class NSFWFilterWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SFW Image Filter - PyQt5")
        self.resize(1280, 720)

        self.settings = QtCore.QSettings(SETTING_ORG, SETTING_APP)
        self.last_open_dir = self.settings.value("last_open_dir", "", type=str)

        self._worker_thread: QThread | None = None
        self._worker: FolderFilterWorker | None = None
        self.icon_size = 120

        self._setup_ui()

    # ---------- UI setup ----------

    def _setup_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        self.splitter = QtWidgets.QSplitter()
        self.splitter.setOrientation(Qt.Horizontal)
        main_layout.addWidget(self.splitter, 1)

        # left / middle / right
        self.splitter.addWidget(self._build_left_panel())
        self.splitter.addWidget(self._build_middle_panel())
        self.splitter.addWidget(self._build_right_panel())

        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 3)

        # progress bar bottom
        progress_container = QtWidgets.QWidget()
        progress_layout = QtWidgets.QHBoxLayout(progress_container)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(6)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Tiến độ: 0% (0/0 folder)")

        self.progress_label = QtWidgets.QLabel("")
        self.progress_label.setStyleSheet("color: #666;")

        progress_layout.addWidget(self.progress_bar, 3)
        progress_layout.addWidget(self.progress_label, 2)

        progress_container.setVisible(False)
        self.progress_container = progress_container

        main_layout.addWidget(progress_container, 0)

    def _build_left_panel(self) -> QtWidgets.QWidget:
        group = QtWidgets.QGroupBox("Thư mục nguồn")
        layout = QtWidgets.QVBoxLayout(group)
        layout.setSpacing(8)

        btn_layout = QtWidgets.QHBoxLayout()
        lbl = QtWidgets.QLabel("Thêm folder cha để scan ảnh:")
        lbl.setStyleSheet("font-weight: bold;")
        btn_add = QtWidgets.QPushButton("Thêm folder cha")
        btn_add.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogNewFolder))
        btn_add.clicked.connect(self._handle_add_root_folder)

        btn_clear = QtWidgets.QPushButton("Xóa tất cả")
        btn_clear.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_TrashIcon))
        btn_clear.clicked.connect(self._handle_clear_folders)

        btn_layout.addWidget(lbl)
        btn_layout.addStretch(1)
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_clear)

        self.folder_tree = QtWidgets.QTreeWidget()
        self.folder_tree.setHeaderHidden(False)
        self.folder_tree.setHeaderLabels(["Thư mục"])
        self.folder_tree.setRootIsDecorated(True)
        self.folder_tree.itemChanged.connect(self._on_folder_item_changed)

        helper = QtWidgets.QLabel("Tick vào folder muốn xử lý.\n"
                                  "Folder cha có thể bật/tắt toàn bộ con.")
        helper.setStyleSheet("color: #666; font-size: 11px;")

        layout.addLayout(btn_layout)
        layout.addWidget(self.folder_tree, 1)
        layout.addWidget(helper)

        return group

    def _build_middle_panel(self) -> QtWidgets.QWidget:
        group = QtWidgets.QGroupBox("Folder sẽ được xử lý")
        layout = QtWidgets.QVBoxLayout(group)
        layout.setSpacing(8)

        self.selected_list = QtWidgets.QListWidget()
        self.selected_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.selected_list.setFocusPolicy(Qt.NoFocus)

        info = QtWidgets.QLabel("Danh sách này chỉ đọc, tự cập nhật khi bạn tick/untick bên trái.")
        info.setStyleSheet("color: #666; font-size: 11px;")

        layout.addWidget(self.selected_list, 1)
        layout.addWidget(info)

        return group

    def _build_right_panel(self) -> QtWidgets.QWidget:
        group = QtWidgets.QGroupBox("Output & Kết quả")
        layout = QtWidgets.QVBoxLayout(group)
        layout.setSpacing(10)

        # Output folder selector
        out_layout = QtWidgets.QHBoxLayout()
        lbl = QtWidgets.QLabel("Folder output:")
        self.output_edit = QtWidgets.QLineEdit()
        self.output_edit.setPlaceholderText("Nếu bỏ trống, sẽ dùng folder mặc định.")
        self.output_button = QtWidgets.QPushButton("Chọn...")
        self.output_button.clicked.connect(self._handle_choose_output)

        out_layout.addWidget(lbl)
        out_layout.addWidget(self.output_edit, 1)
        out_layout.addWidget(self.output_button)

        # Run button
        self.run_button = QtWidgets.QPushButton("Run lọc SFW")
        self.run_button.setStyleSheet("font-size: 14px; font-weight: bold; padding: 6px 12px;")
        self.run_button.clicked.connect(self._start_filter)

        # Result list
        result_label = QtWidgets.QLabel("Ảnh đã copy vào folder output:")
        result_label.setStyleSheet("font-weight: bold;")

        self.result_list = QtWidgets.QListWidget()
        self.result_list.setViewMode(QtWidgets.QListView.IconMode)
        self.result_list.setIconSize(QtCore.QSize(self.icon_size, self.icon_size))
        self.result_list.setResizeMode(QtWidgets.QListView.Adjust)
        self.result_list.setMovement(QtWidgets.QListView.Static)
        self.result_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)

        btn_delete = QtWidgets.QPushButton("Xóa ảnh đã chọn (UI + file)")
        btn_delete.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_TrashIcon))
        btn_delete.clicked.connect(self._handle_delete_selected_results)

        layout.addLayout(out_layout)
        layout.addWidget(self.run_button, 0, alignment=Qt.AlignRight)
        layout.addWidget(result_label)
        layout.addWidget(self.result_list, 1)
        layout.addWidget(btn_delete, 0, alignment=Qt.AlignRight)

        return group

    # ---------- Folder tree / selection logic ----------

    def _handle_add_root_folder(self):
        start_dir = self.last_open_dir or os.path.expanduser("~")
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Chọn folder cha chứa ảnh", start_dir
        )
        if not folder:
            return

        self.last_open_dir = folder

        # Nếu folder đã tồn tại trong tree thì bỏ
        for i in range(self.folder_tree.topLevelItemCount()):
            it = self.folder_tree.topLevelItem(i)
            if it.data(0, Qt.UserRole) == folder:
                return

        root_item = QtWidgets.QTreeWidgetItem([os.path.basename(folder) or folder])
        root_item.setData(0, Qt.UserRole, folder)
        root_item.setFlags(root_item.flags() | Qt.ItemIsUserCheckable)
        root_item.setCheckState(0, Qt.Unchecked)

        # Thêm subfolder 1 level
        try:
            for name in sorted(os.listdir(folder)):
                sub_path = os.path.join(folder, name)
                if os.path.isdir(sub_path):
                    child = QtWidgets.QTreeWidgetItem([name])
                    child.setData(0, Qt.UserRole, sub_path)
                    child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                    child.setCheckState(0, Qt.Unchecked)
                    root_item.addChild(child)
        except Exception:
            pass

        self.folder_tree.addTopLevelItem(root_item)
        self.folder_tree.expandItem(root_item)

        self._update_selected_list()

    def _handle_clear_folders(self):
        self.folder_tree.clear()
        self._update_selected_list()

    def _on_folder_item_changed(self, item: QtWidgets.QTreeWidgetItem, column: int):
        if column != 0:
            return

        state = item.checkState(0)
        self.folder_tree.blockSignals(True)
        # Nếu là root -> áp cho con
        try:
            if item.parent() is None:
                # Nếu là root: áp trạng thái cho tất cả con
                for i in range(item.childCount()):
                    child = item.child(i)
                    child.setCheckState(0, state)
            else:
                # Nếu là child: cập nhật lại parent nhưng CHỈ 2 trạng thái
                parent = item.parent()
                all_checked = True
                for i in range(parent.childCount()):
                    st = parent.child(i).checkState(0)
                    if st != Qt.Checked:
                        all_checked = False
                        break
                parent.setCheckState(0, Qt.Checked if all_checked else Qt.Unchecked)
        finally:
            self.folder_tree.blockSignals(False)

        self._update_selected_list()

    def _iter_checked_folders(self) -> List[str]:
        paths: List[str] = []

        def collect_item(it: QtWidgets.QTreeWidgetItem):
            st = it.checkState(0)
            if st == Qt.Checked:
                p = it.data(0, Qt.UserRole)
                if p:
                    paths.append(p)

            for i in range(it.childCount()):
                collect_item(it.child(i))

        for i in range(self.folder_tree.topLevelItemCount()):
            collect_item(self.folder_tree.topLevelItem(i))

        # bỏ trùng
        unique = []
        seen = set()
        for p in paths:
            if p not in seen:
                seen.add(p)
                unique.append(p)
        return unique

    def _update_selected_list(self):
        self.selected_list.clear()
        for path in self._iter_checked_folders():
            text = os.path.basename(path) or path
            item = QtWidgets.QListWidgetItem(text)
            item.setToolTip(path)
            self.selected_list.addItem(item)

    # ---------- Output & run ----------

    def _handle_choose_output(self):
        start_dir = self.last_open_dir or os.path.expanduser("~")
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Chọn folder output", start_dir
        )
        if not folder:
            return
        self.output_edit.setText(folder)

    def _get_effective_output_folder(self) -> str | None:
        custom = self.output_edit.text().strip()
        if custom:
            return custom

        # default: nếu có ít nhất 1 folder nguồn -> tạo "sfw_output" trong folder cha đầu tiên
        selected = self._iter_checked_folders()
        if not selected:
            return None

        base = selected[0]
        default_out = os.path.join(base, "sfw_output")
        return default_out

    def _start_filter(self):
        if self._worker_thread is not None:
            QtWidgets.QMessageBox.warning(self, "Đang chạy",
                                          "Quá trình lọc hiện đang chạy, vui lòng đợi xong.")
            return

        folders = self._iter_checked_folders()
        if not folders:
            QtWidgets.QMessageBox.warning(self, "Thiếu dữ liệu",
                                          "Hãy chọn ít nhất 1 folder ở panel bên trái.")
            return

        out_folder = self._get_effective_output_folder()
        if not out_folder:
            QtWidgets.QMessageBox.warning(self, "Thiếu output",
                                          "Không xác định được folder output.")
            return
        
        try:
            self.model = NSFWModelManager()  # hoặc path bạn muốn
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Lỗi load model",
                f"Không load được model NSFW:\n{e}"
            )
            return

        # reset kết quả
        self.result_list.clear()

        # hiển thị progress
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Tiến độ: 0% (0/{})".format(len(folders)))
        self.progress_label.setText(f"Output: {out_folder}")
        self.progress_container.setVisible(True)

        # disable nút run
        self.run_button.setEnabled(False)

        # tạo thread + worker
        self._worker_thread = QThread(self)
        self._worker = FolderFilterWorker(folders, out_folder, self, model_manager=self.model)
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.progress_folder.connect(self._on_worker_progress_folder)
        self._worker.progress_percent.connect(self._on_worker_progress_percent)
        self._worker.file_copied.connect(self._on_worker_file_copied)
        self._worker.error.connect(self._on_worker_error)

        # dọn dẹp
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)

        self._worker_thread.start()

    def _on_worker_progress_folder(self, current: int, total: int, folder: str):
        self.progress_bar.setFormat(f"Tiến độ: %p% ({current}/{total} folder)")
        self.progress_label.setText(f"Đang xử lý folder: {folder}")

    def _on_worker_progress_percent(self, percent: int):
        self.progress_bar.setValue(percent)

    def _on_worker_file_copied(self, path: str):
        font = self.result_list.font()
        item = QtWidgets.QListWidgetItem()
        pixmap = QtGui.QPixmap(path)
        if not pixmap.isNull():
            item.setIcon(QtGui.QIcon(pixmap))
            item.setText(truncate_text(os.path.basename(path), font, self.icon_size))
        item.setData(Qt.UserRole, path)
        self.result_list.addItem(item)

    def _on_worker_error(self, msg: str):
        # Có thể log ra console, hoặc show message box nhẹ
        print("Worker error:", msg)

    def _on_worker_finished(self):
        self.run_button.setEnabled(True)
        self.progress_label.setText(self.progress_label.text() + "  |  Hoàn tất.")
        self._worker = None
        self._worker_thread = None

    def _handle_delete_selected_results(self):
        items = self.result_list.selectedItems()
        if not items:
            return

        answer = QtWidgets.QMessageBox.question(
            self,
            "Xóa ảnh",
            f"Bạn chắc chắn muốn xóa {len(items)} ảnh khỏi output (cả file thật)?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return

        for item in items:
            path = item.data(Qt.UserRole)
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    print("Lỗi xóa file:", path, e)
            row = self.result_list.row(item)
            self.result_list.takeItem(row)

    # ---------- Close & settings ----------

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        # Lưu last_open_dir
        if self.last_open_dir and os.path.exists(self.last_open_dir):
            self.settings.setValue("last_open_dir", self.last_open_dir)
        else:
            self.settings.setValue("last_open_dir", "")

        # Nếu worker đang chạy thì cho user lựa chọn
        if self._worker_thread and self._worker_thread.isRunning():
            answer = QtWidgets.QMessageBox.question(
                self,
                "Đang xử lý",
                "Quá trình lọc đang chạy. Bạn có muốn hủy và thoát không?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if answer == QtWidgets.QMessageBox.Yes:
                if self._worker:
                    self._worker.cancel()
                event.accept()
            else:
                event.ignore()
                return
        else:
            event.accept()

        super().closeEvent(event)


def main():
    QtWidgets.QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QtWidgets.QApplication(sys.argv)
    try:
        # nếu có file theme *.qss giống project IG thì dùng
        if os.path.exists("MacOS.qss"):
            with open("MacOS.qss", "r", encoding="utf-8") as f:
                app.setStyleSheet(f.read())
    except Exception:
        pass

    w = NSFWFilterWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
