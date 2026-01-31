# File: ig_merge_video_ui.py
"""
IG Merge Video UI (PyQt5)
========================

Layout (theo mock):
- Cột trái: toolbar (+, ->, x) + sort combo + danh sách input + log box
- Khu vực phải:
  - Hàng trên: Preview (trái) + Output (phải)
  - Khối giữa: Logo + toggle âm thanh + backend + encoder + chip label
  - Khối dưới: Selected area (merge order, drag reorder) + progress + Merge

Additions:
- (a) Selected item có nút X overlay để remove từng item.
- (b) Output list hiển thị thumbnail + filename + duration.

Fix overflow:
- QSplitter sizes + status elide + log textedit (scroll).
- Không đưa ffmpeg cmd dài vào QLabel.

Requires:
- PyQt5
- opencv-python
- numpy
- ig_merge_video_core.py (VideoMerger, MergeOptions, natural_key, FFmpegProbe)
"""

from __future__ import annotations

import os
import sys
import traceback
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PyQt5.QtCore import Qt, QSize, QTimer, QThread, pyqtSignal, QObject
from PyQt5.QtGui import QPixmap, QImage, QFontMetrics, QIcon
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QFileDialog,
    QMessageBox,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QPushButton,
    QGroupBox,
    QSlider,
    QStyle,
    QAbstractItemView,
    QComboBox,
    QCheckBox,
    QProgressBar,
    QTextEdit,
    QSplitter,
    QSizePolicy,
    QToolButton,
    QFrame,
    QGridLayout,
)

from ig_merge_video_core import MergeOptions, VideoMerger, natural_key, FFmpegProbe


def norm(p: str) -> str:
    return os.path.normpath(p)


def elide_middle(text: str, fm: QFontMetrics, max_px: int) -> str:
    return fm.elidedText(text, Qt.ElideMiddle, max_px)


def format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "--:--"
    s = int(round(seconds))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h > 0:
        return f"{h:d}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


class ThumbnailCache:
    def __init__(self, thumb: int = 110) -> None:
        self.thumb = int(thumb)
        self._cache: Dict[str, QIcon] = {}

    def get(self, path: str) -> QIcon:
        if path in self._cache:
            return self._cache[path]
        ico = self._make(path)
        self._cache[path] = ico
        return ico

    def _make(self, path: str) -> QIcon:
        cap = cv2.VideoCapture(path)
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            return QIcon()

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = np.ascontiguousarray(frame)

        h, w = frame.shape[:2]
        side = min(h, w)
        y0 = (h - side) // 2
        x0 = (w - side) // 2
        frame = frame[y0 : y0 + side, x0 : x0 + side]
        frame = cv2.resize(frame, (self.thumb, self.thumb), interpolation=cv2.INTER_AREA)
        frame = np.ascontiguousarray(frame)

        qimg = QImage(frame.data, frame.shape[1], frame.shape[0], frame.strides[0], QImage.Format_RGB888)
        return QIcon(QPixmap.fromImage(qimg.copy()))


class VideoPreviewWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.cap: Optional[cv2.VideoCapture] = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

        self.fps = 30.0
        self.frame_count = 0
        self.cur_frame = 0
        self.playing = False

        self.video_label = QLabel("Preview")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumHeight(260)
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.valueChanged.connect(self._on_seek)

        self.btn_play = QPushButton()
        self.btn_play.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.btn_play.clicked.connect(self._toggle_play)

        row = QHBoxLayout()
        row.addWidget(self.btn_play)
        row.addWidget(self.slider, 1)

        lay = QVBoxLayout(self)
        lay.addWidget(self.video_label, 1)
        lay.addLayout(row)

    def load(self, path: str) -> None:
        self.stop()
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            self.video_label.setText("Không mở được video")
            return
        self.cap = cap
        self.fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self.cur_frame = 0

        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, self.frame_count - 1))
        self.slider.setValue(0)
        self.slider.blockSignals(False)

        self._render_frame(0)

    def stop(self) -> None:
        self.playing = False
        self.timer.stop()
        if self.cap:
            self.cap.release()
            self.cap = None
        self.btn_play.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))

    def _toggle_play(self) -> None:
        if not self.cap:
            return
        self.playing = not self.playing
        if self.playing:
            self.btn_play.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
            interval_ms = int(1000 / max(1.0, self.fps))
            self.timer.start(max(10, interval_ms))
        else:
            self.btn_play.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
            self.timer.stop()

    def _on_seek(self, v: int) -> None:
        if self.cap:
            self._render_frame(v)

    def _tick(self) -> None:
        if not self.cap:
            return
        nxt = min(self.cur_frame + 1, max(0, self.frame_count - 1))
        self._render_frame(nxt)
        if nxt >= self.frame_count - 1:
            self._toggle_play()

    def _render_frame(self, idx: int) -> None:
        if not self.cap:
            return
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = self.cap.read()
        if not ok or frame is None:
            return

        self.cur_frame = idx
        self.slider.blockSignals(True)
        self.slider.setValue(idx)
        self.slider.blockSignals(False)

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = np.ascontiguousarray(frame)
        h, w = frame.shape[:2]
        qimg = QImage(frame.data, w, h, frame.strides[0], QImage.Format_RGB888)
        pix = QPixmap.fromImage(qimg.copy())
        self.video_label.setPixmap(pix.scaled(self.video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))


class SelectedThumbWidget(QFrame):
    """
    Widget dùng cho Selected area:
    - Thumbnail + filename (elide)
    - Nút X overlay góc phải để remove item
    """
    def __init__(self, icon: QIcon, filename: str, max_text_px: int, on_remove: callable) -> None:
        super().__init__()
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        grid = QGridLayout(self)
        grid.setContentsMargins(2, 2, 2, 2)
        grid.setSpacing(2)

        thumb_lbl = QLabel()
        thumb_lbl.setFixedSize(110, 110)
        thumb_lbl.setPixmap(icon.pixmap(110, 110))
        thumb_lbl.setAlignment(Qt.AlignCenter)

        btn = QToolButton()
        btn.setText("×")
        btn.setAutoRaise(True)
        btn.setToolTip("Xoá item này")
        btn.setFixedSize(22, 22)
        btn.clicked.connect(on_remove)

        text_lbl = QLabel(filename)
        text_lbl.setAlignment(Qt.AlignHCenter)
        text_lbl.setFixedWidth(110)
        fm = QFontMetrics(text_lbl.font())
        text_lbl.setText(elide_middle(filename, fm, max_text_px))

        grid.addWidget(thumb_lbl, 0, 0, 1, 1, Qt.AlignCenter)
        grid.addWidget(btn, 0, 0, 1, 1, Qt.AlignTop | Qt.AlignRight)
        grid.addWidget(text_lbl, 1, 0, 1, 1, Qt.AlignCenter)

        self.setFixedSize(114, 142)


class OutputRowWidget(QFrame):
    """
    Widget cho Output:
    - thumbnail + filename + duration
    """
    def __init__(self, icon: QIcon, filename: str, duration_text: str) -> None:
        super().__init__()
        self.setFrameShape(QFrame.NoFrame)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(8)

        thumb_lbl = QLabel()
        thumb_lbl.setFixedSize(56, 56)
        thumb_lbl.setPixmap(icon.pixmap(56, 56))
        thumb_lbl.setAlignment(Qt.AlignCenter)

        mid = QVBoxLayout()
        name_lbl = QLabel(filename)
        name_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        dur_lbl = QLabel(f"Duration: {duration_text}")
        dur_lbl.setStyleSheet("color: #666;")

        mid.addWidget(name_lbl)
        mid.addWidget(dur_lbl)

        lay.addWidget(thumb_lbl)
        lay.addLayout(mid, 1)


class MergeWorker(QObject):
    finished = pyqtSignal(str, str, bool, str)
    error = pyqtSignal(str, str)
    status = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(
        self,
        video_paths: List[str],
        output_path: str,
        logo_path: Optional[str],
        keep_audio: bool,
        force_codec: Optional[str],
        backend: str,
    ) -> None:
        super().__init__()
        self.video_paths = video_paths
        self.output_path = output_path
        self.logo_path = logo_path
        self.keep_audio = keep_audio
        self.force_codec = force_codec
        self.backend = backend
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def _should_cancel(self) -> bool:
        return self._cancel_requested

    def run(self) -> None:
        try:
            opts = MergeOptions(
                keep_audio=self.keep_audio,
                prefer_gpu=True,
                force_codec=self.force_codec,
                backend=self.backend,
            )
            merger = VideoMerger(opts)

            def s(msg: str) -> None:
                self.status.emit(msg)

            res = merger.merge(
                self.video_paths,
                self.output_path,
                logo_path=self.logo_path,
                should_cancel=self._should_cancel,
                status=s,
            )
            self.finished.emit(res.output_path, res.debug.encoder_label, res.debug.is_gpu, res.debug.backend)

        except RuntimeError as e:
            if str(e) == "CANCELLED":
                self.cancelled.emit()
                return
            self.error.emit("Lỗi merge", f"{e}\n\n{traceback.format_exc()}")
        except Exception:
            self.error.emit("Lỗi merge", traceback.format_exc())


class MergeWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("IG Merge Video")
        self.setMinimumSize(1180, 720)

        self.thumb_cache = ThumbnailCache(thumb=110)
        self.duration_cache: Dict[str, float] = {}

        self.video_paths: List[str] = []
        self.logo_path: Optional[str] = None

        self._worker_thread: Optional[QThread] = None
        self._worker: Optional[MergeWorker] = None

        self._setup_ui()
        self._load_encoder_choices()
        self._apply_default_split()

    # ---------------- UI ----------------

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)
        self.main_splitter = splitter

        # LEFT
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(8, 8, 8, 8)
        left_lay.setSpacing(8)

        toolbar = QHBoxLayout()
        self.btn_add = QPushButton("＋")
        self.btn_add.setToolTip("Thêm video")
        self.btn_add.clicked.connect(self._handle_add_videos)

        self.btn_to_merge = QPushButton("→")
        self.btn_to_merge.setToolTip("Thêm video đã chọn vào Selected")
        self.btn_to_merge.clicked.connect(self._handle_add_selected_to_merge)

        self.btn_remove = QPushButton("×")
        self.btn_remove.setToolTip("Xoá video đã chọn khỏi Input")
        self.btn_remove.clicked.connect(self._remove_selected_from_input)

        toolbar.addWidget(self.btn_add)
        toolbar.addWidget(self.btn_to_merge)
        toolbar.addWidget(self.btn_remove)
        toolbar.addStretch(1)
        left_lay.addLayout(toolbar)

        # IMPORTANT: sort combo dưới nút thêm video (giữ đúng yêu cầu)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(
            [
                "Xếp theo tên (A→Z)",
                "Xếp theo thời gian sửa đổi (mới→cũ)",
                "Xếp theo thời gian tạo (mới→cũ)",
            ]
        )
        self.sort_combo.currentIndexChanged.connect(self._apply_sort_and_refresh)
        left_lay.addWidget(self.sort_combo)

        self.video_list = QListWidget()
        self.video_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.video_list.currentItemChanged.connect(self._on_input_select)
        self.video_list.itemDoubleClicked.connect(self._on_input_double_click)
        left_lay.addWidget(self.video_list, 3)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setPlaceholderText("Log...")
        self.log_box.setMinimumHeight(180)
        self.log_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        left_lay.addWidget(self.log_box, 0)

        # RIGHT
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(8, 8, 8, 8)
        right_lay.setSpacing(8)

        top_split = QSplitter(Qt.Horizontal)
        right_lay.addWidget(top_split, 3)
        self.top_splitter = top_split

        gb_preview = QGroupBox("Preview")
        pv_lay = QVBoxLayout(gb_preview)
        self.preview = VideoPreviewWidget()
        pv_lay.addWidget(self.preview, 1)
        top_split.addWidget(gb_preview)

        gb_output = QGroupBox("Output")
        out_lay = QVBoxLayout(gb_output)
        self.output_list = QListWidget()
        self.output_list.itemDoubleClicked.connect(self._on_output_double_click)
        out_lay.addWidget(self.output_list, 1)
        top_split.addWidget(gb_output)

        gb_controls = QGroupBox("Cấu hình")
        ctl = QVBoxLayout(gb_controls)

        row1 = QHBoxLayout()
        self.btn_logo = QPushButton("Logo...")
        self.btn_logo.clicked.connect(self._choose_logo)
        self.lbl_logo = QLabel("(chưa chọn)")
        self.lbl_logo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.chk_keep_audio = QCheckBox("Giữ âm thanh")
        self.chk_keep_audio.setChecked(True)

        row1.addWidget(self.btn_logo)
        row1.addWidget(self.lbl_logo, 1)
        row1.addStretch(1)
        row1.addWidget(self.chk_keep_audio)
        ctl.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Backend:"))
        self.backend_combo = QComboBox()
        self.backend_combo.addItem("Fast FFmpeg (khuyến nghị)", "fast_ffmpeg")
        self.backend_combo.addItem("MoviePy (fallback)", "moviepy")
        row2.addWidget(self.backend_combo, 1)

        row2.addWidget(QLabel("Encoder:"))
        self.encoder_combo = QComboBox()
        row2.addWidget(self.encoder_combo, 1)
        ctl.addLayout(row2)

        self.lbl_chip = QLabel("Chip: (chưa chạy)")
        self.lbl_chip.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        ctl.addWidget(self.lbl_chip)

        right_lay.addWidget(gb_controls, 0)

        gb_selected = QGroupBox("Selected area (thứ tự merge)")
        sel_lay = QVBoxLayout(gb_selected)

        self.merge_list = QListWidget()
        self.merge_list.setViewMode(QListWidget.IconMode)
        self.merge_list.setIconSize(QSize(110, 110))
        self.merge_list.setResizeMode(QListWidget.Adjust)
        self.merge_list.setMovement(QListWidget.Snap)
        self.merge_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.merge_list.setSpacing(10)
        self.merge_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        sel_lay.addWidget(self.merge_list, 1)

        btn_row = QHBoxLayout()
        self.btn_clear_merge = QPushButton("Xoá danh sách merge")
        self.btn_clear_merge.clicked.connect(self._clear_merge)
        btn_row.addWidget(self.btn_clear_merge)
        btn_row.addStretch(1)
        sel_lay.addLayout(btn_row)

        right_lay.addWidget(gb_selected, 3)

        bottom = QHBoxLayout()
        self.btn_merge = QPushButton("Merge")
        self.btn_merge.clicked.connect(self._start_merge)

        self.btn_cancel = QPushButton("Huỷ")
        self.btn_cancel.clicked.connect(self._cancel_merge)
        self.btn_cancel.hide()

        bottom.addStretch(1)
        bottom.addWidget(self.btn_merge)
        bottom.addWidget(self.btn_cancel)
        right_lay.addLayout(bottom)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        right_lay.addWidget(self.progress)

        self.lbl_status = QLabel("")
        self.lbl_status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.lbl_status.setWordWrap(False)
        right_lay.addWidget(self.lbl_status)

        splitter.addWidget(left)
        splitter.addWidget(right)

        left.setMinimumWidth(340)
        right.setMinimumWidth(760)

    def _apply_default_split(self) -> None:
        self.main_splitter.setSizes([360, 920])
        self.top_splitter.setSizes([560, 420])

    def _load_encoder_choices(self) -> None:
        self.encoder_combo.clear()
        self.encoder_combo.addItem("Auto (ưu tiên GPU nếu có)", None)
        for enc in VideoMerger.supported_encoders():
            self.encoder_combo.addItem(f"{enc.label} [{enc.codec}]", enc.codec)

    # ---------------- Input ----------------

    def _handle_add_videos(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn video",
            "",
            "Video Files (*.mp4 *.mov *.mkv *.avi);;All Files (*)",
        )
        if not paths:
            return
        self.video_paths.extend([norm(p) for p in paths])
        self._apply_sort_and_refresh()

    def _apply_sort_and_refresh(self) -> None:
        idx = self.sort_combo.currentIndex()
        if idx == 0:
            self.video_paths = sorted(self.video_paths, key=lambda p: natural_key(os.path.basename(p)))
        elif idx == 1:
            self.video_paths = sorted(self.video_paths, key=lambda p: os.path.getmtime(p), reverse=True)
        else:
            self.video_paths = sorted(self.video_paths, key=lambda p: os.path.getctime(p), reverse=True)
        self._refresh_input_list()

    def _refresh_input_list(self) -> None:
        self.video_list.clear()
        fm = QFontMetrics(self.video_list.font())
        max_px = 260
        for p in self.video_paths:
            base = os.path.basename(p)
            it = QListWidgetItem()
            it.setData(Qt.UserRole, p)
            it.setIcon(self.thumb_cache.get(p))
            it.setText(elide_middle(base, fm, max_px))
            self.video_list.addItem(it)

    def _remove_selected_from_input(self) -> None:
        selected = [it.data(Qt.UserRole) for it in self.video_list.selectedItems()]
        if not selected:
            return
        sset = set(selected)
        self.video_paths = [p for p in self.video_paths if p not in sset]
        self._refresh_input_list()

    def _on_input_select(self, cur: Optional[QListWidgetItem], _prev: Optional[QListWidgetItem]) -> None:
        if not cur:
            return
        p = cur.data(Qt.UserRole)
        if p and os.path.isfile(p):
            self.preview.load(p)

    def _on_input_double_click(self, item: QListWidgetItem) -> None:
        p = item.data(Qt.UserRole)
        if p:
            self._add_to_merge(p)

    def _handle_add_selected_to_merge(self) -> None:
        for it in self.video_list.selectedItems():
            p = it.data(Qt.UserRole)
            if p:
                self._add_to_merge(p)

    # ---------------- Selected area (with overlay X) ----------------

    def _add_to_merge(self, path: str) -> None:
        base = os.path.basename(path)
        icon = self.thumb_cache.get(path)

        item = QListWidgetItem()
        item.setData(Qt.UserRole, path)
        item.setSizeHint(QSize(114, 142))
        self.merge_list.addItem(item)

        def on_remove() -> None:
            row = self.merge_list.row(item)
            if row >= 0:
                self.merge_list.takeItem(row)

        # text should fit within thumbnail width
        w = int(self.merge_list.iconSize().width())
        widget = SelectedThumbWidget(icon=icon, filename=base, max_text_px=w, on_remove=on_remove)
        self.merge_list.setItemWidget(item, widget)

    def _clear_merge(self) -> None:
        self.merge_list.clear()

    # ---------------- Output (thumbnail + duration) ----------------

    def _probe_duration(self, path: str) -> float:
        if path in self.duration_cache:
            return self.duration_cache[path]
        d = FFmpegProbe.duration_seconds(path)
        self.duration_cache[path] = d
        return d

    def _add_output_item(self, path: str) -> None:
        base = os.path.basename(path)
        icon = self.thumb_cache.get(path)
        dur = self._probe_duration(path)
        dur_text = format_duration(dur)

        it = QListWidgetItem()
        it.setData(Qt.UserRole, path)
        it.setSizeHint(QSize(200, 70))
        self.output_list.addItem(it)

        w = OutputRowWidget(icon=icon, filename=base, duration_text=dur_text)
        self.output_list.setItemWidget(it, w)

    def _on_output_double_click(self, item: QListWidgetItem) -> None:
        p = item.data(Qt.UserRole)
        if p and os.path.isfile(p):
            self.preview.load(p)

    # ---------------- Logo ----------------

    def _choose_logo(self) -> None:
        p, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn logo (PNG/JPG)",
            "",
            "Image Files (*.png *.jpg *.jpeg);;All Files (*)",
        )
        if not p:
            self.logo_path = None
            self.lbl_logo.setText("(chưa chọn)")
            return
        self.logo_path = norm(p)
        self.lbl_logo.setText(os.path.basename(self.logo_path))

    # ---------------- Merge run ----------------

    def _start_merge(self) -> None:
        ordered: List[str] = []
        for i in range(self.merge_list.count()):
            ordered.append(self.merge_list.item(i).data(Qt.UserRole))

        if not ordered:
            QMessageBox.warning(self, "Thiếu video", "Selected area đang trống.")
            return

        out_path, _ = QFileDialog.getSaveFileName(self, "Chọn nơi lưu output", "", "MP4 (*.mp4)")
        if not out_path:
            return
        out_path = norm(out_path)

        keep_audio = self.chk_keep_audio.isChecked()
        force_codec = self.encoder_combo.currentData()
        backend = self.backend_combo.currentData()

        tmp = VideoMerger(MergeOptions(keep_audio=keep_audio, prefer_gpu=True, force_codec=force_codec, backend=backend))
        self.lbl_chip.setText(f"Chip: {tmp.processing_backend_label()} | Backend: {backend}")
        self._append_log(
            f"== Start merge ==\nBackend={backend}\nEncoder={tmp.processing_backend_label()}\n"
            f"Audio={'ON' if keep_audio else 'OFF'}\nOutput={out_path}\n"
        )

        self._set_running(True)
        self._set_status("Đang khởi tạo...")

        self._worker_thread = QThread()
        self._worker = MergeWorker(ordered, out_path, self.logo_path, keep_audio, force_codec, backend)
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self._worker.run)
        self._worker.status.connect(self._on_worker_status)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.error.connect(self._on_worker_error)
        self._worker.cancelled.connect(self._on_worker_cancelled)

        self._worker_thread.start()

    def _on_worker_status(self, msg: str) -> None:
        self._append_log(msg)
        if msg.startswith("ffmpeg ") or "-filter_complex" in msg:
            self._set_status("FFmpeg running...")
            return
        if msg.startswith("Backend:"):
            self.lbl_chip.setText(msg.replace("Backend:", "Chip:"))
            self._set_status("Đang chạy...")
            return
        self._set_status(msg)

    def _on_worker_finished(self, output_path: str, encoder_label: str, is_gpu: bool, backend: str) -> None:
        self._append_log("== Done ==")
        self._cleanup_worker()
        self._set_running(False)

        chip = "GPU" if is_gpu else "CPU"
        self.lbl_chip.setText(f"Chip: {encoder_label} ({chip}) | Backend: {backend}")
        self._set_status("✅ Done")

        self._add_output_item(output_path)
        QMessageBox.information(self, "Hoàn tất", f"Xuất xong:\n{output_path}\n\n{encoder_label}\nBackend: {backend}")

    def _on_worker_error(self, title: str, detail: str) -> None:
        self._append_log("== ERROR ==")
        self._append_log(detail)
        self._cleanup_worker()
        self._set_running(False)
        self._set_status("❌ Lỗi")
        QMessageBox.critical(self, title, "Merge thất bại. Xem log ở khung Log (góc trái dưới).")

    def _on_worker_cancelled(self) -> None:
        self._append_log("== CANCELLED ==")
        self._cleanup_worker()
        self._set_running(False)
        self._set_status("⛔ Đã huỷ")

    def _cancel_merge(self) -> None:
        if self._worker:
            self._worker.request_cancel()
            self._set_status("Đang huỷ...")
            self._append_log("Cancel requested...")

    def _cleanup_worker(self) -> None:
        if self._worker_thread:
            self._worker_thread.quit()
            self._worker_thread.wait(1500)
        self._worker_thread = None
        self._worker = None

    # ---------------- UI helpers ----------------

    def _set_running(self, on: bool) -> None:
        self.progress.setVisible(on)
        self.btn_cancel.setVisible(on)
        self.btn_merge.setEnabled(not on)

    def _set_status(self, text: str) -> None:
        fm = QFontMetrics(self.lbl_status.font())
        self.lbl_status.setText(elide_middle(text, fm, max(200, self.lbl_status.width() - 10)))

    def _append_log(self, line: str) -> None:
        self.log_box.append(line)
        self.log_box.moveCursor(self.log_box.textCursor().End)

    def closeEvent(self, event) -> None:
        try:
            if self._worker:
                self._worker.request_cancel()
        except Exception:
            pass
        self.preview.stop()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    try:
        with open("MacOS.qss", 'r') as f:
            app.setStyleSheet(f.read())
    except: pass
    w = MergeWindow()
    w.resize(1280, 760)
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
