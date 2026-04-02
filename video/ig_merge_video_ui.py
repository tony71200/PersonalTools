# File: ig_merge_video_ui_v2.py
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
import json
from typing import Callable, Dict, List, Optional, Set, Tuple
from abc import ABC, abstractmethod

from dataclasses import dataclass

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
    QTabWidget, 
    QTreeWidget, 
    QTreeWidgetItem, 
    QLineEdit
)

from ig_merge_video_core import MergeOptions, ImageVideoOptions, VideoMerger, natural_key, FFmpegProbe
from ig_image_process_core import process_post_image_with_logo, target_post_size, scale_logo_rect_for_post, old_logo_cover_rect_bottom_right


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

class ThumbnailCache(ABC):
    """Abstract thumbnail cache."""
    def __init__(self, thumb: int = 110) -> None:
        self.thumb = int(thumb)
        self._cache: Dict[str, QIcon] = {}

    def get(self, path: str) -> QIcon:
        if path in self._cache:
            return self._cache[path]
        ico = self._make(path)
        self._cache[path] = ico
        return ico
    
    @abstractmethod
    def _make(self, path: str) -> QIcon:
        pass

class VideoThumbnailCache(ThumbnailCache):
    """Video thumbnail (first frame) icon cache: square-crop is OK for videos."""
    def __init__(self, thumb: int = 110) -> None:
        super().__init__(thumb)

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

class ImageThumbnailCache(ThumbnailCache):
    """Image thumbnail icon cache: preserve aspect ratio."""
    def __init__(self, thumb: int = 110) -> None:
        super().__init__(thumb)

    def _make(self, path: str) -> QIcon:
        pix = QPixmap(path)
        if pix is None:
            return QIcon()

        canvas = QPixmap(self.thumb, self.thumb)
        canvas.fill(Qt.transparent)

        scaled = pix.scaled(self.thumb, self.thumb, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = (self.thumb - scaled.width()) // 2
        y = (self.thumb - scaled.height()) // 2
        from PyQt5.QtGui import QPainter
        painter = QPainter(canvas)
        painter.drawPixmap(x, y, scaled)
        painter.end()
        return QIcon(canvas)

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


def compact_filename(filename: str, prefix: int = 5, suffix: int = 4) -> str:
    """Shorten long names for UI only, e.g. 00057....6799.png."""
    if len(filename) <= 22:
        return filename
    stem, ext = os.path.splitext(filename)
    if len(stem) <= (prefix + suffix + 4):
        return filename
    return f"{stem[:prefix]}....{stem[-suffix:]}{ext}"


class CheckableThumbItemWidget(QFrame):
    def __init__(self, icon: QIcon, filename: str, checked: bool, on_checked_changed: Callable[[bool], None],
                 on_remove: Optional[Callable[[], None]] = None,
                 checkbox_enabled: bool = True) -> None:
        super().__init__()
        self.setFrameShape(QFrame.NoFrame)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self.chk = QCheckBox("Che logo cũ")
        self.chk.setChecked(bool(checked))
        self.chk.setEnabled(bool(checkbox_enabled))
        self.chk.toggled.connect(on_checked_changed)
        top.addWidget(self.chk)
        top.addStretch(1)
        if on_remove is not None:
            btn = QToolButton()
            btn.setText("×")
            btn.setAutoRaise(True)
            btn.setToolTip("Xoá item này")
            btn.setFixedSize(22, 22)
            btn.clicked.connect(on_remove)
            top.addWidget(btn)

        thumb = QLabel()
        thumb.setFixedSize(110, 110)
        thumb.setPixmap(icon.pixmap(110, 110))
        thumb.setAlignment(Qt.AlignCenter)

        txt = QLabel(compact_filename(filename))
        txt.setAlignment(Qt.AlignHCenter)
        txt.setFixedWidth(110)
        txt.setToolTip(filename)

        lay.addLayout(top)
        lay.addWidget(thumb, 0, Qt.AlignCenter)
        lay.addWidget(txt, 0, Qt.AlignCenter)
        self.setFixedSize(132, 168)


class CheckableThumbListWidget(QListWidget):
    CHECK_ROLE = Qt.UserRole + 1

    def checked_paths(self) -> List[str]:
        out: List[str] = []
        for i in range(self.count()):
            item = self.item(i)
            if bool(item.data(self.CHECK_ROLE)):
                p = item.data(Qt.UserRole)
                if p:
                    out.append(p)
        return out

    def add_thumb_item(self, path: str, icon: QIcon, checked: bool = False,
                      on_remove: Optional[Callable[[], None]] = None,
                      on_checked_changed: Optional[Callable[[bool], None]] = None,
                      checkbox_enabled: bool = True) -> QListWidgetItem:
        base = os.path.basename(path)
        item = QListWidgetItem()
        item.setData(Qt.UserRole, path)
        item.setData(self.CHECK_ROLE, bool(checked))
        item.setSizeHint(QSize(136, 170))
        self.addItem(item)

        def _on_checked(v: bool) -> None:
            item.setData(self.CHECK_ROLE, bool(v))
            if on_checked_changed:
                on_checked_changed(bool(v))

        w = CheckableThumbItemWidget(
            icon=icon,
            filename=base,
            checked=checked,
            on_checked_changed=_on_checked,
            on_remove=on_remove,
            checkbox_enabled=checkbox_enabled,
        )
        self.setItemWidget(item, w)
        return item

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

class Worker(QObject):
    finished = pyqtSignal(str, str, bool, str)
    error = pyqtSignal(str, str)
    status = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self,
                 input_paths: List[str],
                 output_path: str,
                 logo_path: Optional[str],
                 keep_audio: bool,
                 backend: str,
                 force_codec: Optional[str]) -> None:
        super().__init__()
        self.input_paths = input_paths
        self.output_path = output_path
        self.logo_path = logo_path
        self.keep_audio = keep_audio
        self.backend = str(backend)
        self.force_codec = force_codec
        self._cancel_requested = False
    def request_cancel(self) -> None:
        self._cancel_requested = True

    def _should_cancel(self) -> bool:
        return self._cancel_requested
    
    def run(self) -> None:
        raise NotImplementedError

class VideoMergeWorker(Worker):
    def __init__(self, input_paths, output_path, logo_path, keep_audio, backend, force_codec,
                 remove_old_logo_paths: Optional[List[str]] = None):
        super().__init__(input_paths, output_path, logo_path, keep_audio, backend, force_codec)
        self.remove_old_logo_paths = [norm(p) for p in (remove_old_logo_paths or []) if p]

    def run(self) -> None:
        video_paths = [p for p in self.input_paths if os.path.isfile(p) and p.lower().endswith(('.mp4', '.mov'))]
        if not video_paths:
            self.error.emit("Lỗi input", "Không có video hợp lệ để merge.")
            return
        try:
            opts = MergeOptions(
                keep_audio=self.keep_audio,
                prefer_gpu=True,
                force_codec=self.force_codec,
                backend=self.backend,
                remove_old_logo_paths=tuple(self.remove_old_logo_paths),
            )
            merger = VideoMerger(opts)

            def s(msg: str) -> None:
                self.status.emit(msg)

            res = merger.merge(
                video_paths,
                self.output_path,
                logo_path=(self.logo_path.strip() or None),
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

class MergeVideoTab(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.thumb_cache = VideoThumbnailCache(thumb=110)
        self.duration_cache: Dict[str, float] = {}

        self.video_paths: List[str] = []
        self.logo_path: Optional[str] = None

        self._worker_thread: Optional[QThread] = None
        self._worker: Optional[VideoMergeWorker] = None

        self._setup_ui()
        self._load_encoder_choices()
        self._apply_default_split()

    # ---------------- UI ----------------

    def _setup_ui(self) -> None:
        root = QHBoxLayout(self)

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
        # toolbar.addStretch(1)
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

        self.merge_list = CheckableThumbListWidget()
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
        self.btn_merge = QPushButton("Merge")
        self.btn_merge.clicked.connect(self._start_merge)

        self.btn_cancel = QPushButton("Huỷ")
        self.btn_cancel.clicked.connect(self._cancel_merge)
        self.btn_cancel.hide()

        btn_row.addWidget(self.btn_clear_merge)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_merge)
        btn_row.addWidget(self.btn_cancel)
        sel_lay.addLayout(btn_row)

        right_lay.addWidget(gb_selected, 3)

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
        icon = self.thumb_cache.get(path)
        item: Optional[QListWidgetItem] = None

        def on_remove() -> None:
            if item is None:
                return
            row = self.merge_list.row(item)
            if row >= 0:
                self.merge_list.takeItem(row)

        item = self.merge_list.add_thumb_item(path=path, icon=icon, checked=False, on_remove=on_remove)

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
        if (len(ordered) > 0):
            filename = os.path.dirname(ordered[0])
        else:
            filename = ""

        out_path, _ = QFileDialog.getSaveFileName(self, "Chọn nơi lưu output", f"{filename}.mp4", "MP4 (*.mp4)")
        if not out_path:
            return
        out_path = norm(out_path)

        keep_audio = self.chk_keep_audio.isChecked()
        force_codec = self.encoder_combo.currentData()
        backend = self.backend_combo.currentData()
        remove_old_logo_paths = self.merge_list.checked_paths()

        tmp = VideoMerger(MergeOptions(keep_audio=keep_audio, prefer_gpu=True, force_codec=force_codec, backend=backend))
        self.lbl_chip.setText(f"Chip: {tmp.processing_backend_label()} | Backend: {backend}")
        self._append_log(
            f"== Start merge ==\nBackend={backend}\nEncoder={tmp.processing_backend_label()}\n"
            f"Audio={'ON' if keep_audio else 'OFF'}\nOutput={out_path}\n"
        )

        self._set_running(True)
        self._set_status("Đang khởi tạo...")

        self._worker_thread = QThread()
        self._worker = VideoMergeWorker(ordered, out_path, self.logo_path, 
                                        keep_audio=keep_audio, force_codec=force_codec, backend=backend,
                                        remove_old_logo_paths=remove_old_logo_paths)
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


# ---------------- Make Video From Image (Fast FFmpeg) ----------------
import subprocess
import tempfile
import shutil
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v")

def _ensure_ffmpeg_available() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("Không tìm thấy ffmpeg/ffprobe trong PATH. Cài ffmpeg và thử lại.")

def _list_images(folder: str) -> List[str]:
    items: List[str] = []
    try:
        for name in os.listdir(folder):
            p = os.path.join(folder, name)
            if os.path.isfile(p) and name.lower().endswith(IMAGE_EXTS):
                items.append(p)
    except Exception:
        return []
    items.sort(key=natural_key)
    return items

def _is_addlogo_temp_file(name: str) -> bool:
    lname = name.lower()
    return lname.startswith(".") and ".tmp_addlogo" in lname


def _list_media_files(folder: str) -> List[str]:
    items: List[str] = []
    try:
        for name in os.listdir(folder):
            p = os.path.join(folder, name)
            if not os.path.isfile(p):
                continue
            if _is_addlogo_temp_file(name):
                # Bỏ qua file tạm nội bộ còn sót lại từ chế độ overwrite-in-place.
                continue
            lname = name.lower()
            if lname.endswith(IMAGE_EXTS) or lname.endswith(VIDEO_EXTS):
                items.append(p)
    except Exception:
        return []
    items.sort(key=natural_key)
    return items


def _probe_video_size(path: str) -> Optional[Tuple[int, int]]:
    # Updated 2026-02-28: probe size bằng ffprobe JSON để tránh phụ thuộc FFmpegProbe.probe (không tồn tại).
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json",
            path,
        ]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, text=True, encoding="utf-8", errors="ignore")
        data = json.loads((p.stdout or "{}").strip() or "{}")
        streams = data.get("streams") or []
        if streams:
            w = int((streams[0] or {}).get("width", 0) or 0)
            h = int((streams[0] or {}).get("height", 0) or 0)
            if w > 0 and h > 0:
                return w, h
    except Exception:
        pass

    # Fallback: dùng OpenCV để đọc kích thước nếu ffprobe không trả kết quả.
    try:
        cap = cv2.VideoCapture(path)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            cap.release()
            if w > 0 and h > 0:
                return w, h
    except Exception:
        pass
    return None


def _run_add_logo_video_ffmpeg(input_path: str, output_path: str, logo_path: str, fps: int = 30, remove_old_logo: bool = False) -> None:
    # Updated 2026-03-13: với video, thứ tự xử lý là che logo cũ (tuỳ chọn) -> blur background -> chèn logo mới.
    size = _probe_video_size(input_path)
    if not size:
        raise RuntimeError(f"Không đọc được metadata video: {input_path}")

    tw, th = target_post_size(size[0], size[1])
    lw, lh, lx, ly = scale_logo_rect_for_post((tw, th))

    cover_w, cover_h, _, _ = old_logo_cover_rect_bottom_right((tw, th))
    src_w, src_h = size
    patch_w = max(1, min(int(cover_w), int(src_w)))
    patch_h = max(1, min(int(cover_h), int(src_h)))
    patch_x = max(0, int(src_w) - patch_w)
    patch_y = max(0, int(src_h) - patch_h)

    x_expr = str(patch_x)
    y_expr = str(patch_y)
    w_expr = str(patch_w)
    h_expr = str(patch_h)
    cover_filter = ""
    if remove_old_logo:
        bx_expr = str(max(0, patch_x - 2))
        by_expr = str(max(0, patch_y - 2))
        cover_filter = (
            f"[0:v]split=2[srcbase][srcblur];"
            f"[srcblur]boxblur=15:3,crop=w={w_expr}:h={h_expr}:x={x_expr}:y={y_expr}[srcpatch];"
            f"[srcbase][srcpatch]overlay=x={x_expr}:y={y_expr},"
            f"drawbox=x={bx_expr}:y={by_expr}:w={w_expr}:h={h_expr}:color=black@0.12:t=2[src];"
        )
    else:
        cover_filter = "[0:v]null[src];"

    vf = (
        f"{cover_filter}"
        f"[src]split=2[bgsrc][fgsrc];"
        f"[bgsrc]scale={tw}:{th},gblur=sigma=30[bg];"
        f"[fgsrc]scale={tw}:{th}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[mid];"
        f"[1:v]scale={lw}:{lh}[logo];"
        f"[mid][logo]overlay={lx}:{ly},format=yuv420p[v]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-i", logo_path,
        "-filter_complex", vf,
        "-map", "[v]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-r", str(max(1, int(fps))),
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "ffmpeg lỗi").strip())

class ImageMakeWorker(Worker):
    outfilename = pyqtSignal(str)
    processpercent = pyqtSignal(float)
    def __init__(self, input_paths: List[str], 
                 output_path: str, 
                 logo_path: Optional[str], 
                 backend:str, 
                 force_codec: Optional[str],
                 total_duration_s: float,
                 fps: int,
                 min_images: int) -> None:
        super().__init__(input_paths, 
                         output_path, 
                         logo_path,
                         keep_audio=False,
                         backend=backend,
                         force_codec=force_codec)
        self.total_duration_s = float(total_duration_s)
        self.fps = int(fps)
        self.min_images = int(max(1, min_images))
    
    def run(self) -> None:
        try:
            _ensure_ffmpeg_available()
            os.makedirs(self.output_path, exist_ok=True)

            mopts = MergeOptions(
                backend=self.backend,
                keep_audio=self.keep_audio,
                fps=self.fps,
                force_codec=self.force_codec,
            )

            merger = VideoMerger(mopts)

            img_opts = ImageVideoOptions(
                total_duration_s=self.total_duration_s,
                min_images=self.min_images,
            )

            for idx, folder in enumerate(self.input_paths, start=1):
                if self._should_cancel():
                    self.cancelled.emit()
                    return

                name = os.path.basename(folder.rstrip(os.sep))
                out_path = os.path.join(self.output_path, f"{name}.mp4")
                

                res = merger.make_video_from_image_folder(
                    image_folder=folder,
                    output_path=out_path,
                    logo_path=(self.logo_path.strip() or None),
                    img_opts=img_opts,
                    should_cancel=self._should_cancel,
                )
                self.status.emit(f"[{idx}/{len(self.input_paths)}] {name} -> {out_path}")
                if res.output_path:
                    self.outfilename.emit(os.path.basename(res.output_path))
                self.processpercent.emit(idx / len(self.input_paths) * 100.0)
                
        except Exception as e:
            self.error.emit("Lỗi tạo video từ ảnh", f"{e}\n\n{traceback.format_exc()}")
        finally:
            self.finished.emit(self.output_path, "", False, "")
        

class MakeVideoFromImageTab(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.img_thumb_cache = ImageThumbnailCache(thumb=110)
        self.vid_thumb_cache = VideoThumbnailCache(thumb=110)
        self.logo_path: Optional[str] = None

        self._worker_thread: Optional[QThread] = None
        self._worker: Optional[ImageMakeWorker] = None
        self._current_single_folder: Optional[str] = None
        self._last_parent_folder: Optional[str] = None

        self._setup_ui()
        self._load_encoder_choices()
        self._sync_left_mode()

    def _setup_ui(self) -> None:
        root = QHBoxLayout(self)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        # LEFT
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(8, 8, 8, 8)
        left_lay.setSpacing(8)

        toolbar = QHBoxLayout()
        self.btn_add = QPushButton("＋")
        self.btn_add.setToolTip("Chọn folder (tùy Batch Parent Folder)")
        self.btn_add.clicked.connect(self._handle_plus)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self._clear_left)

        self.chk_batch_from_parent = QCheckBox("Batch Parent Folder")
        self.chk_batch_from_parent.setChecked(True)
        self.chk_batch_from_parent.stateChanged.connect(self._sync_left_mode)

        toolbar.addWidget(self.btn_add)
        toolbar.addStretch(1)
        toolbar.addWidget(self.btn_clear)
        left_lay.addLayout(toolbar)
        left_lay.addWidget(self.chk_batch_from_parent)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Folders"])
        self.tree.itemSelectionChanged.connect(self._on_tree_selection)

        self.image_name_list = QListWidget()
        self.image_name_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.image_name_list.currentItemChanged.connect(self._on_image_name_select)
        
        left_lay.addWidget(self.tree, 1)
        left_lay.addWidget(self.image_name_list, 1)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(120)
        left_lay.addWidget(self.log_box)

        splitter.addWidget(left)

        # RIGHT
        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(8, 8, 8, 8)
        rlay.setSpacing(8)

        top = QGroupBox("Preview Images")
        top_lay = QHBoxLayout(top)

        self.thumb_list = QListWidget()
        self.thumb_list.setViewMode(QListWidget.IconMode)
        self.thumb_list.setResizeMode(QListWidget.Adjust)
        self.thumb_list.setMovement(QListWidget.Static)
        self.thumb_list.setIconSize(QSize(110, 110))
        self.thumb_list.setSpacing(6)
        self.thumb_list.setSelectionMode(QAbstractItemView.NoSelection)

        self.outname_list = QListWidget()
        self.outname_list.setViewMode(QListWidget.ListMode)
        self.outname_list.setResizeMode(QListWidget.Adjust)
        self.outname_list.setMovement(QListWidget.Static)
        self.outname_list.setSelectionMode(QAbstractItemView.NoSelection)

        top_lay.addWidget(self.thumb_list, 3)
        top_lay.addWidget(self.outname_list, 1)

        rlay.addWidget(top, 2)

        out_group = QGroupBox("Output")
        out_lay = QGridLayout(out_group)

        self.out_dir = QLineEdit()
        self.out_dir.setPlaceholderText("Output folder (mặc định: folder cha)")
        self.btn_pick_out = QPushButton("Browse")
        self.btn_pick_out.clicked.connect(self._pick_output_dir)

        self.in_duration = QLineEdit("30")
        self.in_fps = QLineEdit("30")
        self.in_min_images = QLineEdit("7")

        self.logo_line = QLineEdit()
        self.logo_line.setPlaceholderText("Logo (tuỳ chọn)")
        self.btn_pick_logo = QPushButton("Browse")
        self.btn_pick_logo.clicked.connect(self._pick_logo)

        self.backend_combo = QComboBox()
        self.backend_combo.addItem("Fast FFmpeg (khuyến nghị)", "fast_ffmpeg")
        self.backend_combo.addItem("MoviePy (fallback)", "moviepy")

        self.encoder_combo = QComboBox()

        self.btn_make = QPushButton("Make")
        self.btn_make.clicked.connect(self._start_make)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self._cancel_make)
        self.btn_cancel.setEnabled(False)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)

        row = 0
        out_lay.addWidget(QLabel("Output dir"), row, 0)
        out_lay.addWidget(self.out_dir, row, 1, 1, 2)
        out_lay.addWidget(self.btn_pick_out, row, 3)
        row += 1

        out_lay.addWidget(QLabel("Duration (s)"), row, 0)
        out_lay.addWidget(self.in_duration, row, 1, 1, 2)
        out_lay.addWidget(QLabel(""), row, 3)
        row += 1

        out_lay.addWidget(QLabel("FPS"), row, 0)
        out_lay.addWidget(self.in_fps, row, 1,  1, 2)
        out_lay.addWidget(QLabel(""), row, 3)
        row += 1

        out_lay.addWidget(QLabel("Min Number Image"), row, 0)
        out_lay.addWidget(self.in_min_images, row, 1,  1, 2)
        out_lay.addWidget(QLabel(""), row, 3)
        row += 1

        out_lay.addWidget(QLabel("Logo"), row, 0)
        out_lay.addWidget(self.logo_line, row, 1,  1, 2)
        out_lay.addWidget(self.btn_pick_logo, row, 3)
        row += 1

        out_lay.addWidget(QLabel("Backend"), row, 0)
        out_lay.addWidget(self.backend_combo, row, 1)
        out_lay.addWidget(QLabel("Encoder"), row, 2)
        out_lay.addWidget(self.encoder_combo, row, 3)
        row += 1

        out_lay.addWidget(self.btn_make, row, 2)
        out_lay.addWidget(self.btn_cancel, row, 3)
        row += 1

        out_lay.addWidget(self.progress, row, 0, 1, 4)

        rlay.addWidget(out_group, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

    def _load_encoder_choices(self) -> None:
        self.encoder_combo.clear()
        self.encoder_combo.addItem("Auto (ưu tiên GPU nếu có)", None)
        try:
            for enc in VideoMerger.supported_encoders():
                self.encoder_combo.addItem(f"{enc.label} [{enc.codec}]", enc.codec)
        except Exception:
            pass

    def _append_log(self, line: str) -> None:
        self.log_box.append(line)
        self.log_box.moveCursor(self.log_box.textCursor().End)

    def _sync_left_mode(self) -> None:
        batch = self.chk_batch_from_parent.isChecked()
        self.tree.setVisible(batch)
        self.image_name_list.setVisible(not batch)
        self._clear_preview_only()

    def _clear_preview_only(self) -> None:
        self.thumb_list.clear()

    def _clear_left(self) -> None:
        self.tree.clear()
        self.image_name_list.clear()
        self._current_single_folder = None
        self._last_parent_folder = None
        self._clear_preview_only()

    def _handle_plus(self) -> None:
        if self.chk_batch_from_parent.isChecked():
            d = QFileDialog.getExistingDirectory(self, "Chọn folder cha")
            if not d:
                return
            d = norm(d)
            self._last_parent_folder = d
            self._load_parent_folder(d)
        else:
            d = QFileDialog.getExistingDirectory(self, "Chọn 1 folder ảnh")
            if not d:
                return
            d = norm(d)
            self._current_single_folder = d
            self._load_single_folder_images(d)

    def _load_parent_folder(self, root: str) -> None:
        self.tree.clear()
        root_item = QTreeWidgetItem([root])
        root_item.setData(0, Qt.UserRole, root)
        self.tree.addTopLevelItem(root_item)

        try:
            subs = [os.path.join(root, name) for name in os.listdir(root)]
            subs = [p for p in subs if os.path.isdir(p)]
            subs.sort(key=natural_key)
            for p in subs:
                child = QTreeWidgetItem([os.path.basename(p)])
                child.setData(0, Qt.UserRole, p)
                root_item.addChild(child)
        except Exception as e:
            self._append_log(f"⚠️ Không đọc subfolder: {e}")

        root_item.setExpanded(True)
        self._append_log(f"Parent: {root} (subfolders={root_item.childCount()})")

    def _load_single_folder_images(self, folder: str) -> None:
        self.image_name_list.clear()
        imgs = _list_images(folder)
        for p in imgs:
            it = QListWidgetItem(os.path.basename(p))
            it.setData(Qt.UserRole, p)
            self.image_name_list.addItem(it)
        self._append_log(f"Single folder: {folder} (images={len(imgs)})")

        # auto preview using this folder
        self._preview_folder(folder)

    def _pick_output_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Chọn output folder")
        if d:
            self.out_dir.setText(norm(d))

    def _pick_logo(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "Chọn logo", filter="Images (*.png *.jpg *.jpeg *.webp)")
        if p:
            self.logo_line.setText(norm(p))
            self.logo_path = norm(p)
            self._append_log(f"Logo: {norm(p)}")

    def _selected_folder_from_tree(self) -> Optional[str]:
        items = self.tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, Qt.UserRole)

    def _folders_to_process(self) -> List[str]:
        if self.chk_batch_from_parent.isChecked():
            sel_items = self.tree.selectedItems()
            if not sel_items:
                # default: process all children under the (only) root if exists
                if self.tree.topLevelItemCount() == 1:
                    root = self.tree.topLevelItem(0)
                    return [root.child(i).data(0, Qt.UserRole) for i in range(root.childCount())]
                return []
            item = sel_items[0]
            # if selecting root => all its children (1-level)
            if item.parent() is None and item.childCount() > 0:
                return [item.child(i).data(0, Qt.UserRole) for i in range(item.childCount())]
            # leaf => only that folder
            folder = item.data(0, Qt.UserRole)
            return [folder] if folder else []
        # single mode: not batch => only current folder is process target
        return [self._current_single_folder] if self._current_single_folder else []

    def _on_tree_selection(self) -> None:
        folder = self._selected_folder_from_tree()
        if not folder:
            return
        # preview only: show images inside selected folder
        self._preview_folder(folder)

    def _on_image_name_select(self, cur: Optional[QListWidgetItem], _prev: Optional[QListWidgetItem]) -> None:
        # Only update preview list for the folder; selection is for preview purpose only
        if not self._current_single_folder:
            return
        self._preview_folder(self._current_single_folder)

    def _preview_folder(self, folder: str) -> None:
        images = _list_images(folder)
        self.thumb_list.clear()

        if not images:
            self.thumb_list.addItem(QListWidgetItem("No images"))
            return

        for p in images[:300]:
            it = QListWidgetItem(self.img_thumb_cache.get(p), "")
            it.setToolTip(p)
            self.thumb_list.addItem(it)


    def _start_make(self) -> None:
        folders = self._folders_to_process()
        if not folders:
            QMessageBox.warning(self, "Thiếu folder", "Chọn folder hoặc folder cha để xử lý.")
            return

        out_dir = self.out_dir.text().strip()
        if not out_dir:
            if self.chk_batch_from_parent.isChecked():
                out_dir = self._last_parent_folder or (os.path.dirname(folders[0]) if folders else "")
            else:
                out_dir = os.path.dirname(folders[0]) if folders else ""
            out_dir = norm(out_dir) if out_dir else ""
        
        if not out_dir:
            QMessageBox.warning(self, "Thiếu output", "Không xác định được output folder.")
            return

        try:
            duration = float(self.in_duration.text().strip())
            fps = int(float(self.in_fps.text().strip()))
            min_images = int(float(self.in_min_images.text().strip()))
        except Exception:
            QMessageBox.warning(self, "Sai input", "Duration/FPS/Min Number Image không hợp lệ.")
            return
        backend = self.backend_combo.currentData()
        force_codec = self.encoder_combo.currentData()

        self._append_log(
            f"== Start make ==\nBackend={backend}\nEncoder={force_codec or 'auto'}\n"
            f"OutputDir={out_dir}\nFolders={len(folders)}\n"
        )
        self.outname_list.clear()
        self._set_running(True)

        self._worker_thread = QThread()
        self._worker = ImageMakeWorker(
            input_paths=folders,
            output_path=norm(out_dir),
            logo_path=(self.logo_path.strip() or None),
            backend=backend,
            force_codec=force_codec,
            total_duration_s=duration,
            fps=fps,
            min_images=min_images,
        )
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self._worker.run)
        self._worker.status.connect(self._append_log)
        self._worker.finished.connect(self._on_make_done)
        self._worker.cancelled.connect(self._on_make_cancelled)
        self._worker.error.connect(self._on_make_error)
        self._worker.outfilename.connect(lambda name: self.outname_list.addItem(name))
        self._worker.processpercent.connect(lambda p: self.progress.setValue(int(p)))

        # self._worker.finished.connect(self._worker_thread.quit)
        # self._worker.error.connect(lambda *_: self._worker_thread.quit())
        # self._worker.cancelled.connect(self._worker_thread.quit)

        self._worker_thread.finished.connect(self._cleanup_worker)

        self._append_log("▶️ Start make video from images...")
        self._worker_thread.start()
    
    def _set_running(self, on: bool) -> None:
        self.progress.setVisible(on)
        self.btn_cancel.setEnabled(on)
        self.btn_make.setEnabled(not on)
        self.btn_add.setEnabled(not on)
        self.btn_clear.setEnabled(not on)

    def _cancel_make(self) -> None:
        if self._worker:
            self._append_log("⏹ Cancel requested...")
            self._worker.request_cancel()

    def _on_make_done(self, out_dir: str, encoder: str, isgpu: bool, backend:str) -> None:
        self._append_log("== Done ==")
        self._cleanup_worker()
        self._set_running(False)
        QMessageBox.information(self, "Hoàn tất", f"Xuất xong vào:\n{out_dir}")

    def _on_make_cancelled(self) -> None:
        self._append_log("== CANCELLED ==")
        self._cleanup_worker()
        self._set_running(False)
        QMessageBox.information(self, "Đã huỷ", "Đã huỷ tác vụ.")

    def _on_make_error(self, title: str, detail: str) -> None:
        self._append_log("== ERROR ==")
        self._append_log(detail)
        self._cleanup_worker()
        self._set_running(False)
        QMessageBox.critical(self, "Lỗi", f"{title}\n\nXem log để biết chi tiết.")

    def _cleanup_worker(self) -> None:
        if self._worker_thread:
            self._worker_thread.quit()
            self._worker_thread.wait(1500)
        self._worker_thread = None
        self._worker = None


class AddLogoWorker(Worker):
    outfilename = pyqtSignal(str)
    processpercent = pyqtSignal(float)

    def __init__(self, input_paths: List[str], output_path: str, logo_path: str, fps: int = 30,
                 overwrite_in_place: bool = False, remove_old_logo_paths: Optional[List[str]] = None) -> None:
        super().__init__(
            input_paths=input_paths,
            output_path=output_path,
            logo_path=logo_path,
            keep_audio=True,
            backend="fast_ffmpeg",
            force_codec="libx264",
        )
        self.fps = int(max(1, fps))
        self.overwrite_in_place = bool(overwrite_in_place)
        self.remove_old_logo_paths: Set[str] = {
            os.path.normcase(norm(p)) for p in (remove_old_logo_paths or []) if p
        }

    def _make_output_file(self, src: str, out_folder: Optional[str]) -> str:
        # Updated 2026-02-28: giữ nguyên tên file output, không thêm hậu tố _logo.
        if self.overwrite_in_place or not out_folder:
            return src
        return os.path.join(out_folder, os.path.basename(src))

    def _make_tmp_file_for_overwrite(self, src: str, is_video: bool) -> str:
        folder = os.path.dirname(src)
        stem, ext = os.path.splitext(os.path.basename(src))
        temp_ext = ext or (".mp4" if is_video else ".png")
        return os.path.join(folder, f".{stem}.tmp_addlogo{temp_ext}")

    def run(self) -> None:
        try:
            _ensure_ffmpeg_available()
            os.makedirs(self.output_path, exist_ok=True)

            folders = [p for p in self.input_paths if p and os.path.isdir(p)]
            if not folders:
                raise RuntimeError("Không có folder hợp lệ để xử lý.")
            if not self.logo_path or not os.path.isfile(self.logo_path):
                raise RuntimeError("Vui lòng chọn logo hợp lệ.")

            total_files = sum(len(_list_media_files(f)) for f in folders)
            if total_files <= 0:
                raise RuntimeError("Không tìm thấy ảnh/video trong các folder đã chọn.")

            done = 0
            for fidx, folder in enumerate(folders, start=1):
                if self._should_cancel():
                    self.cancelled.emit()
                    return
                media_files = _list_media_files(folder)
                folder_name = os.path.basename(folder.rstrip(os.sep)) or f"folder_{fidx}"
                out_folder: Optional[str] = None
                if not self.overwrite_in_place:
                    out_folder = os.path.join(self.output_path, folder_name)
                    os.makedirs(out_folder, exist_ok=True)

                self.status.emit(f"[{fidx}/{len(folders)}] {folder_name}: {len(media_files)} file(s)")

                for src in media_files:
                    if self._should_cancel():
                        self.cancelled.emit()
                        return

                    name = os.path.basename(src)
                    stem, ext = os.path.splitext(name)
                    ext_l = ext.lower()
                    is_video = ext_l in VIDEO_EXTS
                    final_out = self._make_output_file(src, out_folder)
                    work_out = final_out
                    if self.overwrite_in_place:
                        work_out = self._make_tmp_file_for_overwrite(src, is_video=is_video)

                    if is_video:
                        src_key = os.path.normcase(norm(src))
                        _run_add_logo_video_ffmpeg(
                            src,
                            work_out,
                            self.logo_path,
                            fps=self.fps,
                            remove_old_logo=(src_key in self.remove_old_logo_paths),
                        )
                    else:
                        process_post_image_with_logo(src, self.logo_path, work_out)

                    if self.overwrite_in_place:
                        os.replace(work_out, final_out)

                    done += 1
                    if self.overwrite_in_place:
                        shown = final_out
                    else:
                        shown = os.path.relpath(final_out, self.output_path)
                    self.outfilename.emit(shown)
                    self.status.emit(f"  ✓ {name}")
                    self.processpercent.emit(done / total_files * 100.0)

            self.finished.emit(self.output_path, "libx264", False, "fast_ffmpeg")
        except Exception as e:
            self.error.emit("Lỗi Add Logo", f"{e}\n\n{traceback.format_exc()}")


class AddLogoTab(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.img_thumb_cache = ImageThumbnailCache(thumb=110)
        self.vid_thumb_cache = VideoThumbnailCache(thumb=110)
        self.logo_path: Optional[str] = None

        self._worker_thread: Optional[QThread] = None
        self._worker: Optional[AddLogoWorker] = None
        self._current_single_folder: Optional[str] = None
        self._last_parent_folder: Optional[str] = None
        self._cover_old_logo_by_path: Dict[str, bool] = {}

        self._setup_ui()
        self._sync_left_mode()

    def _setup_ui(self) -> None:
        root = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(8, 8, 8, 8)
        left_lay.setSpacing(8)

        toolbar = QHBoxLayout()
        self.btn_add = QPushButton("＋")
        self.btn_add.setToolTip("Chọn folder (tùy Batch Parent Folder)")
        self.btn_add.clicked.connect(self._handle_plus)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self._clear_left)

        self.chk_batch_from_parent = QCheckBox("Batch Parent Folder")
        self.chk_batch_from_parent.setChecked(True)
        self.chk_batch_from_parent.stateChanged.connect(self._sync_left_mode)

        toolbar.addWidget(self.btn_add)
        toolbar.addStretch(1)
        toolbar.addWidget(self.btn_clear)
        left_lay.addLayout(toolbar)
        left_lay.addWidget(self.chk_batch_from_parent)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Folders"])
        self.tree.itemSelectionChanged.connect(self._on_tree_selection)

        self.media_name_list = QListWidget()
        self.media_name_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.media_name_list.currentItemChanged.connect(self._on_media_name_select)

        left_lay.addWidget(self.tree, 1)
        left_lay.addWidget(self.media_name_list, 1)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(120)
        left_lay.addWidget(self.log_box)
        splitter.addWidget(left)

        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(8, 8, 8, 8)
        rlay.setSpacing(8)

        top = QGroupBox("Preview Media")
        top_lay = QHBoxLayout(top)

        self.thumb_list = CheckableThumbListWidget()
        self.thumb_list.setViewMode(QListWidget.IconMode)
        self.thumb_list.setResizeMode(QListWidget.Adjust)
        self.thumb_list.setMovement(QListWidget.Static)
        self.thumb_list.setIconSize(QSize(110, 110))
        self.thumb_list.setSpacing(6)
        self.thumb_list.setSelectionMode(QAbstractItemView.NoSelection)

        self.outname_list = QListWidget()
        self.outname_list.setViewMode(QListWidget.ListMode)
        self.outname_list.setResizeMode(QListWidget.Adjust)
        self.outname_list.setMovement(QListWidget.Static)
        self.outname_list.setSelectionMode(QAbstractItemView.NoSelection)

        top_lay.addWidget(self.thumb_list, 3)
        top_lay.addWidget(self.outname_list, 1)
        rlay.addWidget(top, 2)

        out_group = QGroupBox("Output")
        out_lay = QGridLayout(out_group)

        self.out_dir = QLineEdit()
        self.out_dir.setPlaceholderText("Output folder (mặc định: folder cha)")
        self.btn_pick_out = QPushButton("Browse")
        self.btn_pick_out.clicked.connect(self._pick_output_dir)

        self.in_fps = QLineEdit("30")

        self.logo_line = QLineEdit()
        self.logo_line.setPlaceholderText("Logo (bắt buộc)")
        self.btn_pick_logo = QPushButton("Browse")
        self.btn_pick_logo.clicked.connect(self._pick_logo)
        self.btn_run = QPushButton("Run")
        self.btn_run.clicked.connect(self._start_add_logo)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self._cancel_add_logo)
        self.btn_cancel.setEnabled(False)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)

        row = 0
        out_lay.addWidget(QLabel("Output dir"), row, 0)
        out_lay.addWidget(self.out_dir, row, 1, 1, 2)
        out_lay.addWidget(self.btn_pick_out, row, 3)
        row += 1

        out_lay.addWidget(QLabel("FPS (video output)"), row, 0)
        out_lay.addWidget(self.in_fps, row, 1, 1, 2)
        out_lay.addWidget(QLabel(""), row, 3)
        row += 1

        out_lay.addWidget(QLabel("Logo"), row, 0)
        out_lay.addWidget(self.logo_line, row, 1, 1, 2)
        out_lay.addWidget(self.btn_pick_logo, row, 3)
        row += 1

        out_lay.addWidget(self.btn_run, row, 2)
        out_lay.addWidget(self.btn_cancel, row, 3)
        row += 1

        out_lay.addWidget(self.progress, row, 0, 1, 4)
        rlay.addWidget(out_group, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

    def _append_log(self, line: str) -> None:
        self.log_box.append(line)
        self.log_box.moveCursor(self.log_box.textCursor().End)

    def _sync_left_mode(self) -> None:
        batch = self.chk_batch_from_parent.isChecked()
        self.tree.setVisible(batch)
        self.media_name_list.setVisible(not batch)
        self.thumb_list.clear()

    def _clear_left(self) -> None:
        self.tree.clear()
        self.media_name_list.clear()
        self.thumb_list.clear()
        self._current_single_folder = None
        self._last_parent_folder = None
        self._cover_old_logo_by_path.clear()

    def _handle_plus(self) -> None:
        if self.chk_batch_from_parent.isChecked():
            d = QFileDialog.getExistingDirectory(self, "Chọn folder cha")
            if not d:
                return
            d = norm(d)
            self._last_parent_folder = d
            self._load_parent_folder(d)
        else:
            d = QFileDialog.getExistingDirectory(self, "Chọn 1 folder media")
            if not d:
                return
            d = norm(d)
            self._current_single_folder = d
            self._load_single_folder_media(d)

    def _load_parent_folder(self, root: str) -> None:
        self.tree.clear()
        root_item = QTreeWidgetItem([root])
        root_item.setData(0, Qt.UserRole, root)
        self.tree.addTopLevelItem(root_item)
        try:
            subs = [os.path.join(root, name) for name in os.listdir(root)]
            subs = [p for p in subs if os.path.isdir(p)]
            subs.sort(key=natural_key)
            for p in subs:
                child = QTreeWidgetItem([os.path.basename(p)])
                child.setData(0, Qt.UserRole, p)
                root_item.addChild(child)
        except Exception as e:
            self._append_log(f"⚠️ Không đọc subfolder: {e}")
        root_item.setExpanded(True)
        self._append_log(f"Parent: {root} (subfolders={root_item.childCount()})")

    def _load_single_folder_media(self, folder: str) -> None:
        self.media_name_list.clear()
        media = _list_media_files(folder)
        for p in media:
            it = QListWidgetItem(os.path.basename(p))
            it.setData(Qt.UserRole, p)
            self.media_name_list.addItem(it)
        self._append_log(f"Single folder: {folder} (files={len(media)})")
        self._preview_folder(folder)

    def _pick_output_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Chọn output folder")
        if d:
            self.out_dir.setText(norm(d))

    def _pick_logo(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "Chọn logo", filter="Images (*.png *.jpg *.jpeg *.webp)")
        if p:
            self.logo_line.setText(norm(p))
            self.logo_path = norm(p)
            self._append_log(f"Logo: {norm(p)}")

    def _selected_folder_from_tree(self) -> Optional[str]:
        items = self.tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, Qt.UserRole)

    def _folders_to_process(self) -> List[str]:
        if self.chk_batch_from_parent.isChecked():
            sel_items = self.tree.selectedItems()
            if not sel_items:
                if self.tree.topLevelItemCount() == 1:
                    root = self.tree.topLevelItem(0)
                    return [root.child(i).data(0, Qt.UserRole) for i in range(root.childCount())]
                return []
            item = sel_items[0]
            if item.parent() is None and item.childCount() > 0:
                return [item.child(i).data(0, Qt.UserRole) for i in range(item.childCount())]
            folder = item.data(0, Qt.UserRole)
            return [folder] if folder else []
        return [self._current_single_folder] if self._current_single_folder else []

    def _on_tree_selection(self) -> None:
        folder = self._selected_folder_from_tree()
        if folder:
            self._preview_folder(folder)

    def _on_media_name_select(self, _cur: Optional[QListWidgetItem], _prev: Optional[QListWidgetItem]) -> None:
        if self._current_single_folder:
            self._preview_folder(self._current_single_folder)

    def _preview_folder(self, folder: str) -> None:
        media = _list_media_files(folder)
        self.thumb_list.clear()
        if not media:
            self.thumb_list.addItem(QListWidgetItem("No media"))
            return
        for p in media[:300]:
            is_video = p.lower().endswith(VIDEO_EXTS)
            if is_video:
                icon = self.vid_thumb_cache.get(p)
            else:
                icon = self.img_thumb_cache.get(p)

            checked = bool(self._cover_old_logo_by_path.get(norm(p), False))

            def on_checked(v: bool, path: str = norm(p)) -> None:
                self._cover_old_logo_by_path[path] = bool(v)

            self.thumb_list.add_thumb_item(
                path=p,
                icon=icon,
                checked=checked,
                on_checked_changed=on_checked,
                checkbox_enabled=is_video,
            )

    def _start_add_logo(self) -> None:
        folders = self._folders_to_process()
        if not folders:
            QMessageBox.warning(self, "Thiếu folder", "Chọn folder hoặc folder cha để xử lý.")
            return
        logo_path = self.logo_line.text().strip()
        if not logo_path or not os.path.isfile(logo_path):
            QMessageBox.warning(self, "Thiếu logo", "Vui lòng chọn logo hợp lệ.")
            return

        out_dir_input = self.out_dir.text().strip()
        out_dir = norm(out_dir_input) if out_dir_input else ""

        # Updated 2026-02-28:
        # - Nếu out dir rỗng hoặc trùng input -> ghi đè file cũ.
        overwrite_in_place = False
        if not out_dir:
            overwrite_in_place = True
        else:
            folder_norms = {norm(f) for f in folders}
            if out_dir in folder_norms:
                overwrite_in_place = True

        if overwrite_in_place:
            out_dir = folders[0]

        try:
            fps = int(float(self.in_fps.text().strip()))
        except Exception:
            QMessageBox.warning(self, "Sai input", "FPS không hợp lệ.")
            return

        self._append_log(
            f"== Start add logo ==\nOutputDir={out_dir}\nOverwriteInPlace={'YES' if overwrite_in_place else 'NO'}\nFolders={len(folders)}\n"
            f"Logo={logo_path}\n"
        )
        self.outname_list.clear()
        self._set_running(True)

        self._worker_thread = QThread()
        self._worker = AddLogoWorker(
            input_paths=folders,
            output_path=norm(out_dir),
            logo_path=logo_path,
            fps=fps,
            overwrite_in_place=overwrite_in_place,
            remove_old_logo_paths=[p for p, v in self._cover_old_logo_by_path.items() if v],
        )
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self._worker.run)
        self._worker.status.connect(self._append_log)
        self._worker.finished.connect(self._on_done)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.error.connect(self._on_error)
        self._worker.outfilename.connect(lambda name: self.outname_list.addItem(name))
        self._worker.processpercent.connect(lambda p: self.progress.setValue(int(p)))
        self._worker_thread.finished.connect(self._cleanup_worker)

        self._append_log("▶️ Start add logo...")
        self._worker_thread.start()

    def _set_running(self, on: bool) -> None:
        self.progress.setVisible(on)
        self.btn_cancel.setEnabled(on)
        self.btn_run.setEnabled(not on)
        self.btn_add.setEnabled(not on)
        self.btn_clear.setEnabled(not on)

    def _cancel_add_logo(self) -> None:
        if self._worker:
            self._append_log("⏹ Cancel requested...")
            self._worker.request_cancel()

    def _on_done(self, out_dir: str, _encoder: str, _isgpu: bool, _backend: str) -> None:
        self._append_log("== Done ==")
        self._cleanup_worker()
        self._set_running(False)
        QMessageBox.information(self, "Hoàn tất", f"Xuất xong vào:\n{out_dir}")

    def _on_cancelled(self) -> None:
        self._append_log("== CANCELLED ==")
        self._cleanup_worker()
        self._set_running(False)
        QMessageBox.information(self, "Đã huỷ", "Đã huỷ tác vụ.")

    def _on_error(self, title: str, detail: str) -> None:
        self._append_log("== ERROR ==")
        self._append_log(detail)
        self._cleanup_worker()
        self._set_running(False)
        QMessageBox.critical(self, "Lỗi", f"{title}\n\nXem log để biết chi tiết.")

    def _cleanup_worker(self) -> None:
        if self._worker_thread:
            self._worker_thread.quit()
            self._worker_thread.wait(1500)
        self._worker_thread = None
        self._worker = None


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("IG Tools v2")
        self.setMinimumSize(1180, 720)

        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        self.tab_merge = MergeVideoTab()
        self.tab_make = MakeVideoFromImageTab()
        self.tab_add_logo = AddLogoTab()

        tabs.addTab(self.tab_merge, "Merge Video")
        tabs.addTab(self.tab_make, "Make Video from Image")
        tabs.addTab(self.tab_add_logo, "Add Logo")


def main() -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app = QApplication(sys.argv)
    try:
        with open(os.path.join(base_dir,"MacOS.qss"), "r") as f:
            app.setStyleSheet(f.read())
    except Exception:
        pass
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
