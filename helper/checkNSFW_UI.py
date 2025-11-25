import os
import sys
import shutil
from typing import List

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread

import cv2
import numpy as np
# from nudenet import NudeDetector

# import onnxruntime as ort
from PIL import Image
# import tensorflow.lite as tflite

# import hàm check NSFW từ file hiện có
# đảm bảo file checkNFSW.py nằm cùng folder với file UI này
# from checkNFSW import NSFW_check_image  # type: ignore
# from checkNFSW import NSFW_check_image, load_nsfw_models


IMG_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
SETTING_ORG = "LongTools"
SETTING_APP = "NSFW_SFW_Filter"


def is_image_file(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in IMG_EXTENSIONS

# Option 1: NudeNet Classifier
# class NudeNetChecker:
#     def __init__(self):
#         self.detector = NudeDetector()
        
#         self.dict_thresholds = {
#             "FEMALE_GENITALIA_COVERED": 0.4,
#             "FACE_FEMALE": 0.9,
#             "BUTTOCKS_EXPOSED": 0.3,
#             "FEMALE_BREAST_EXPOSED": 0.9,
#             "FEMALE_GENITALIA_EXPOSED": 0.6,
#             "MALE_BREAST_EXPOSED": 0.9,
#             "ANUS_EXPOSED": 0.4,
#             "FEET_EXPOSED": 0.8,
#             "BELLY_COVERED": 0.9,
#             "FEET_COVERED": 0.9,
#             "ARMPITS_COVERED": 0.9,
#             "ARMPITS_EXPOSED": 0.8,
#             "FACE_MALE": 0.9,
#             "BELLY_EXPOSED": 0.8,
#             "MALE_GENITALIA_EXPOSED": 0.4,
#             "ANUS_COVERED": 0.9,
#             "FEMALE_BREAST_COVERED": 0.9,
#             "BUTTOCKS_COVERED": 0.5,
#         }

#     def detect(self, image_path):
#         """
#         Trả về danh sách các vùng nhạy cảm và điểm số vi phạm.
#         """
#         return self.detector.detect(image_path)
    
#     def is_unsafe(self, image_path, threshold=0.7):
#         """
#         Kiểm tra xem ảnh có vùng nhạy cảm đáng kể không (ví dụ score > 0.7).
#         Nếu có, return True.
#         """
#         detections = self.detect(image_path)
#         for region in detections:
#             region_class = region['class']
#             region_threshold = self.dict_thresholds.get(region_class, threshold)
#             region_score = region['score']
#             #
#             print(region_class, region_score, region_threshold)
#             if region_score >= region_threshold:
#                 return True
#         return False

# Option 2: Rule-based skin exposure checker (OpenCV)
class SkinRatioChecker:
    def __init__(self, lower_thresh=(0, 133, 77), upper_thresh=(255, 173, 127)):
        self.lower_thresh = np.array(lower_thresh, dtype="uint8")
        self.upper_thresh = np.array(upper_thresh, dtype="uint8")

    def compute_skin_ratio(self, image_path):
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError("Không thể đọc ảnh: " + image_path)
        image_ycrcb = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)
        skin_mask = cv2.inRange(image_ycrcb, self.lower_thresh, self.upper_thresh)
        skin_ratio = np.count_nonzero(skin_mask) / skin_mask.size
        return skin_ratio

# Option 3: NSFW Classifier via ONNX
# class ONNXNSFWChecker:
#     def __init__(self, model_path):
#         if not os.path.exists(model_path):
#             raise FileNotFoundError(f"Model {model_path} not found.")
#         self.session = ort.InferenceSession(model_path)
#         self.input_name = self.session.get_inputs()[0].name

#     def preprocess(self, image_path):
#         image = Image.open(image_path).convert('RGB').resize((224, 224))
#         image_np = np.array(image).astype('float32') / 255.0
#         image_np = image_np.transpose(2, 0, 1)  # HWC to CHW
#         return np.expand_dims(image_np, axis=0)

#     def predict(self, image_path):
#         input_tensor = self.preprocess(image_path)
#         outputs = self.session.run(None, {self.input_name: input_tensor})
#         nsfw_score = float(outputs[0][0][1])  # Index 1 = 'nsfw' class
#         return {'nsfw_score': nsfw_score, 'sfw_score': 1 - nsfw_score}
    
# Option 4: NSFW TFLite
# class NSFWTFLiteChecker:
#     def __init__(self, model_path):
        
#         if not os.path.exists(model_path):
#             raise FileNotFoundError(f"Model {model_path} not found.")
#         self.interpreter = tflite.Interpreter(model_path=model_path)
#         self.interpreter.allocate_tensors()
#         self.input_details = self.interpreter.get_input_details()
#         self.output_details = self.interpreter.get_output_details()
#         self.input_size = (224, 224)
#         self.labels = ["Drawing", "Hentai", "Neutral", "Porn", "Sexy"]
#         self.dict_thresholds = {
#             "Drawing": 1,
#             "Hentai": 0.6,
#             "Neutral": 1,
#             "Porn": 0.6,
#             "Sexy": 0.5,
#         }

#     def preprocess(self, image_path):
#         image = Image.open(image_path).convert('RGB').resize(self.input_size)
#         img_np = np.array(image).astype('float32') / 255.0
#         img_np = np.expand_dims(img_np, axis=0)  # shape [1, 224, 224, 3]
#         return img_np.astype(self.input_details[0]["dtype"])

#     def predict(self, image_path):
#         input_tensor = self.preprocess(image_path)
#         self.interpreter.set_tensor(self.input_details[0]['index'], input_tensor)
#         self.interpreter.invoke()
#         output_data = self.interpreter.get_tensor(self.output_details[0]['index'])[0]
#         scores = {label: round(float(score), 4) for label, score in zip(self.labels, output_data)}
#         print(f"scores: {scores}")
#         scores["max_class"] = max(scores, key=lambda k: scores[k])
#         # nsfw_score = float(output_data[1])  # Index 1 = 'nsfw' class
#         # print(f"NSFW score: {nsfw_score}, SFW score: {1 - nsfw_score}")
#         return scores
    
#     def predict_unsafe(self, image_path):
#         scores = self.predict(image_path)
#         max_class = scores["max_class"]
#         max_score = scores[max_class]
#         threshold = self.dict_thresholds.get(max_class, 0.7)
#         return max_score >= threshold



class NSFWModelManager:
    def __init__(self, tflite_model_path="saved_model.tflite",
                 skin_ratio_thr: float = 0.5):
        self.skin_ratio_thr = skin_ratio_thr

        # NudeNet
        # self.nude_checker = None
        # if NudeDetector is not None:
        #     try:
        #         self.nude_checker = NudeNetChecker()
        #     except Exception as e:
        #         print("Không khởi tạo được NudeNetChecker:", e)

        # Skin ratio (nhẹ, load luôn)
        self.skin_checker = SkinRatioChecker()

        # TFLite
        # self.tflite_checker = None
        # try:
        #     self.tflite_checker = NSFWTFLiteChecker(tflite_model_path)
        # except Exception as e:
        #     print("Không khởi tạo được NSFWTFLiteChecker:", e)

    def check_image(self, image_path: str):
        """
        Trả về:
            is_unsafe: bool
            details: dict chứa các kết quả con
        """
        # nudedet_is_unsafe = False
        # if self.nude_checker is not None:
        #     try:
        #         nudedet_is_unsafe = self.nude_checker.is_unsafe(image_path)
        #     except Exception as e:
        #         print("Lỗi NudeNet:", e)

        # Skin ratio
        skin_ratio = 0.0
        skin_is_unsafe = False
        try:
            skin_ratio = self.skin_checker.compute_skin_ratio(image_path)
            skin_is_unsafe = skin_ratio >= self.skin_ratio_thr
        except Exception as e:
            print("Lỗi tính skin ratio:", e)

        # TFLite
        # tflite_is_unsafe = False
        # if self.tflite_checker is not None:
        #     try:
        #         tflite_is_unsafe = self.tflite_checker.predict_unsafe(image_path)
        #     except Exception as e:
        #         print("Lỗi TFLite:", e)

        # is_unsafe = nudedet_is_unsafe or skin_is_unsafe or tflite_is_unsafe
        is_unsafe = skin_is_unsafe

        return is_unsafe, {
            # "nudedet_is_unsafe": nudedet_is_unsafe,
            "skin_ratio": skin_ratio,
            "skin_is_unsafe": skin_is_unsafe,
            # "tflite_is_unsafe": tflite_is_unsafe,
        }


# Singleton manager dùng chung
_model_manager: NSFWModelManager | None = None


def load_nsfw_models(tflite_model_path: str = "saved_model.tflite",
                     skin_ratio_thr: float = 0.5) -> NSFWModelManager:
    """
    Gọi 1 lần ở đầu chương trình/UI để load model.
    """
    global _model_manager
    _model_manager = NSFWModelManager(
        tflite_model_path=tflite_model_path,
        skin_ratio_thr=skin_ratio_thr,
    )
    return _model_manager


def get_nsfw_manager() -> NSFWModelManager:
    """
    Lazy init: nếu chưa load_nsfw_models() thì tự load với default.
    """
    global _model_manager
    if _model_manager is None:
        _model_manager = NSFWModelManager()
    return _model_manager


def NSFW_check_image(image_path: str) -> bool:
    """
    Hàm đơn giản cho UI dùng:
    - True: NSFW
    - False: SFW
    (Model chỉ load lần đầu, lần sau dùng lại)
    """
    manager = get_nsfw_manager()
    is_unsafe, _ = manager.check_image(image_path)
    return is_unsafe



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

    def __init__(self, folders: List[str], output_folder: str, parent=None):
        super().__init__(parent)
        self.folders = folders
        self.output_folder = output_folder
        self._cancelled = False

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
                        is_unsafe = NSFW_check_image(img_path)
                        if not is_unsafe:
                            # copy sang output folder.
                            # giữ tên file, nếu trùng thì thêm số đuôi
                            dst_name = os.path.basename(img_path)
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
        self.result_list.setIconSize(QtCore.QSize(120, 120))
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
            load_nsfw_models("saved_model.tflite")  # hoặc path bạn muốn
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
        self._worker = FolderFilterWorker(folders, out_folder)
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
        item = QtWidgets.QListWidgetItem(os.path.basename(path))
        pixmap = QtGui.QPixmap(path)
        if not pixmap.isNull():
            item.setIcon(QtGui.QIcon(pixmap))
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
