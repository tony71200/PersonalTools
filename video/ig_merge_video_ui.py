import os
import sys
import random
import traceback
from typing import Callable, Dict, List, Optional
import time
import pickle

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
try:
    from moviepy.editor import VideoFileClip, CompositeVideoClip, concatenate_videoclips
except Exception:
    try:
        from moviepy.video.io.VideoFileClip import VideoFileClip
        from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
        from moviepy.video.compositing.concatenate import concatenate_videoclips
    except Exception:  # pragma: no cover - moviepy is an optional runtime dependency
        VideoFileClip = None
        CompositeVideoClip = None
        concatenate_videoclips = None
        raise ImportError("moviepy is required to run this script.")

from ig_merge_video_cmd import (
    TARGET_SIZE,
    TRANSITION_RANGE,
    apply_random_kenburns,
    build_logo_clip,
    fit_clip_with_blurred_bg,
)

try:
    import cv2
except ImportError:  # pragma: no cover - cv2 is an optional runtime dependency
    cv2 = None

# CONSTANTS
DEFAULT_ENCODING = "utf-8"
SETTING_LAST_OPEN_DIR = 'lastOpenDir'

def ustr(x):
    """py2/py3 unicode helper"""

    if sys.version_info < (3, 0, 0):
        from PyQt4.QtCore import QString
        if type(x) == str:
            return x.decode(DEFAULT_ENCODING)
        if type(x) == QString:
            # https://blog.csdn.net/friendan/article/details/51088476
            # https://blog.csdn.net/xxm524/article/details/74937308
            return unicode(x.toUtf8(), DEFAULT_ENCODING, 'ignore')
        return x
    else:
        return x

class Settings(object):
    """Simple settings storage using pickle."""

    def __init__(self):
        # Be default, the home will be in the same folder as labelImg
        home = os.path.expanduser("~")
        self.data = {}
        self.path = os.path.join(home, '.IGVideoSettings.pkl')

    def __setitem__(self, key, value):
        self.data[key] = value

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        if key in self.data:
            return self.data[key]
        return default

    def save(self):
        if self.path:
            with open(self.path, 'wb') as f:
                pickle.dump(self.data, f, pickle.HIGHEST_PROTOCOL)
                return True
        return False

    def load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, 'rb') as f:
                    self.data = pickle.load(f)
                    return True
        except:
            print('Loading setting failed')
        return False

    def reset(self):
        if os.path.exists(self.path):
            os.remove(self.path)
            print('Remove setting pkl file ${0}'.format(self.path))
        self.data = {}
        self.path = None

class ThumbnailCache:
    """Utility class to lazily create and store thumbnails for video files."""

    def __init__(self):
        self._cache: Dict[str, QtGui.QPixmap] = {}

    def get(self, path: str, size: QtCore.QSize) -> QtGui.QPixmap:
        if path in self._cache:
            return self._cache[path]

        pixmap = self._generate_thumbnail(path, size)
        self._cache[path] = pixmap
        return pixmap

    def clear(self) -> None:
        self._cache.clear()

    @staticmethod
    def _generate_thumbnail(path: str, size: QtCore.QSize) -> QtGui.QPixmap:
        if cv2 is None:  # pragma: no cover - cv2 is required by the original script
            return QtGui.QPixmap()

        cap = cv2.VideoCapture(path)
        success, frame = cap.read()
        cap.release()

        if not success or frame is None:
            placeholder = QtGui.QPixmap(size)
            placeholder.fill(Qt.darkGray)
            painter = QtGui.QPainter(placeholder)
            painter.setPen(Qt.white)
            painter.drawText(placeholder.rect(), Qt.AlignCenter, "Không có hình")
            painter.end()
            return placeholder

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, _ = frame.shape
        image = QtGui.QImage(frame.data, w, h, 3 * w, QtGui.QImage.Format_RGB888)
        pixmap = QtGui.QPixmap.fromImage(image)
        return pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


class MergeQueueItem(QtWidgets.QWidget):
    removeRequested = QtCore.pyqtSignal(str)

    def __init__(self, path: str, pixmap: QtGui.QPixmap, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._path = path
        self._setup_ui(pixmap)

    @property
    def path(self) -> str:
        return self._path

    def _setup_ui(self, pixmap: QtGui.QPixmap) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        thumb_label = QtWidgets.QLabel()
        thumb_label.setAlignment(Qt.AlignCenter)
        thumb_label.setPixmap(pixmap)
        thumb_label.setFixedSize(pixmap.size())

        name_label = QtWidgets.QLabel(os.path.basename(self._path))
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setStyleSheet("font-size: 11px;")

        remove_button = QtWidgets.QToolButton()
        remove_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogCloseButton))
        remove_button.setToolTip("Loại khỏi danh sách merge")
        remove_button.setFixedSize(24, 24)
        remove_button.clicked.connect(lambda: self.removeRequested.emit(self._path))

        layout.addWidget(thumb_label)
        layout.addWidget(name_label)
        layout.addWidget(remove_button, alignment=Qt.AlignCenter)


class MergeCancelledError(Exception):
    """Raised when a merge task is cancelled by the user."""


class MergeWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(str)
    status = QtCore.pyqtSignal(str)
    cancelled = QtCore.pyqtSignal(str)

    def __init__(self, paths: List[str], output_path: str, logo_path: str = ""):
        super().__init__()
        self._paths = paths
        self._output_path = output_path
        self._logo_path = logo_path
        self._cancel_requested = False

    @QtCore.pyqtSlot()
    def run(self) -> None:
        try:
            merge_videos(
                self._paths,
                self._output_path,
                logo_path=self._logo_path,
                status_callback=self.status.emit,
                should_cancel=self._should_cancel,
            )
        except MergeCancelledError:
            self.cancelled.emit(self._output_path)
        except Exception as exc:  # pragma: no cover - GUI runtime behaviour
            traceback.print_exc()
            self.error.emit(str(exc))
        else:
            self.finished.emit(self._output_path)

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def _should_cancel(self) -> bool:
        return self._cancel_requested


class VideoPreviewWidget(QtWidgets.QWidget):
    """Simple video preview widget backed by OpenCV decoding."""

    errorOccurred = QtCore.pyqtSignal(str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._cap: Optional["cv2.VideoCapture"] = None
        self._current_frame_index: int = 0
        self._frame_count: int = 0
        self._fps: float = 0.0
        self._is_playing = False
        self._seeking = False
        self._resume_after_seek = False
        self._current_image: Optional[QtGui.QImage] = None

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._advance_frame)

        self._setup_ui()
        self._update_controls(False)

    # region UI helpers
    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._video_label = QtWidgets.QLabel("Chưa có video")
        self._video_label.setAlignment(Qt.AlignCenter)
        self._video_label.setStyleSheet("background-color: #000; color: #ccc;")
        self._video_label.setMinimumHeight(240)
        layout.addWidget(self._video_label, 1)

        controls_layout = QtWidgets.QHBoxLayout()
        controls_layout.setSpacing(8)

        self._play_button = QtWidgets.QPushButton("▶ Phát")
        self._play_button.clicked.connect(self.toggle_playback)

        self._slider = QtWidgets.QSlider(Qt.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.setEnabled(False)
        self._slider.sliderPressed.connect(self._on_slider_pressed)
        self._slider.sliderReleased.connect(self._on_slider_released)
        self._slider.sliderMoved.connect(self._on_slider_moved)

        self._time_label = QtWidgets.QLabel("00:00 / 00:00")
        self._time_label.setMinimumWidth(110)
        self._time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        controls_layout.addWidget(self._play_button)
        controls_layout.addWidget(self._slider, 1)
        controls_layout.addWidget(self._time_label)

        layout.addLayout(controls_layout)

    def _update_controls(self, enabled: bool) -> None:
        self._play_button.setEnabled(enabled)
        self._slider.setEnabled(enabled)
        if not enabled:
            self._play_button.setText("▶ Phát")

    # endregion

    # region Playback logic
    def load(self, path: str, autoplay: bool = True) -> None:
        self.pause()
        self._release_capture()
        self._current_image = None
        self._current_frame_index = 0
        self._frame_count = 0
        self._fps = 0.0

        if not path:
            self._video_label.clear()
            self._video_label.setText("Chưa có video")
            self._update_controls(False)
            return

        if cv2 is None:
            self._video_label.clear()
            self._video_label.setText("Cần cài đặt OpenCV (cv2) để xem video.")
            self._update_controls(False)
            self.errorOccurred.emit("Thiếu thư viện cv2 để phát video.")
            return

        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            cap.release()
            self._video_label.clear()
            self._video_label.setText("Không phát được video.")
            self._update_controls(False)
            self.errorOccurred.emit("Không thể mở video đã chọn.")
            return

        self._cap = cap
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        self._fps = fps if fps and fps > 1e-2 else 25.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self._frame_count = frame_count if frame_count > 0 else 0

        slider_max = self._frame_count - 1 if self._frame_count > 0 else 0
        self._slider.blockSignals(True)
        self._slider.setRange(0, max(0, slider_max))
        self._slider.setValue(0)
        self._slider.blockSignals(False)
        self._update_time_label(0)

        self._update_controls(True)
        self._video_label.setText("Đang tải video...")

        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self._show_frame_at(0)

        if self._current_image is None:
            self._update_controls(False)
            return

        if autoplay:
            self.play()

    def play(self) -> None:
        if self._cap is None:
            return
        if self._frame_count and self._current_frame_index >= self._frame_count - 1:
            self._show_frame_at(0)
        interval = max(15, int(1000 / self._fps)) if self._fps else 40
        self._timer.start(interval)
        self._is_playing = True
        self._play_button.setText("❚❚ Tạm dừng")

    def pause(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
        self._is_playing = False
        self._play_button.setText("▶ Phát")

    def toggle_playback(self) -> None:
        if self._is_playing:
            self.pause()
        else:
            self.play()

    def shutdown(self) -> None:
        self.pause()
        self._release_capture()
        self._video_label.clear()
        self._video_label.setText("Chưa có video")
        self._current_image = None
        self._update_controls(False)

    def _advance_frame(self) -> None:
        if self._cap is None:
            self.pause()
            return

        success, frame = self._cap.read()
        if not success or frame is None:
            self.pause()
            if self._frame_count:
                self._show_frame_at(0)
            return

        index = int(max(0, self._cap.get(cv2.CAP_PROP_POS_FRAMES) - 1))
        self._current_frame_index = index
        self._set_slider_value(index)
        self._update_time_label(index)
        self._display_frame(frame)

    def _show_frame_at(self, frame_index: int) -> None:
        if self._cap is None:
            return
        max_index = self._frame_count - 1 if self._frame_count else frame_index
        frame_index = max(0, min(frame_index, max_index))
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        success, frame = self._cap.read()
        if not success or frame is None:
            self.errorOccurred.emit("Không thể đọc dữ liệu video.")
            return
        self._current_frame_index = frame_index
        self._set_slider_value(frame_index)
        self._update_time_label(frame_index)
        self._display_frame(frame)

    def _display_frame(self, frame: object) -> None:
        if cv2 is None:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, _ = rgb.shape
        image = QtGui.QImage(rgb.data, width, height, 3 * width, QtGui.QImage.Format_RGB888)
        self._current_image = image.copy()
        self._update_label_pixmap()

    def _update_label_pixmap(self) -> None:
        if self._current_image is None:
            return
        pixmap = QtGui.QPixmap.fromImage(self._current_image)
        self._video_label.setText("")
        self._video_label.setPixmap(
            pixmap.scaled(self._video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # pragma: no cover - GUI event
        super().resizeEvent(event)
        self._update_label_pixmap()

    def _on_slider_pressed(self) -> None:
        if not self._slider.isEnabled():
            return
        self._seeking = True
        self._resume_after_seek = self._is_playing
        self.pause()

    def _on_slider_released(self) -> None:
        if not self._seeking:
            return
        frame_index = self._slider.value()
        self._show_frame_at(frame_index)
        self._seeking = False
        if self._resume_after_seek:
            self.play()
        self._resume_after_seek = False

    def _on_slider_moved(self, value: int) -> None:
        self._update_time_label(value)

    def _set_slider_value(self, value: int) -> None:
        self._slider.blockSignals(True)
        self._slider.setValue(value)
        self._slider.blockSignals(False)

    def _update_time_label(self, frame_index: int) -> None:
        total_seconds = self._frame_count / self._fps if self._fps and self._frame_count else 0.0
        current_seconds = frame_index / self._fps if self._fps else 0.0
        self._time_label.setText(f"{self._format_time(current_seconds)} / {self._format_time(total_seconds)}")

    @staticmethod
    def _format_time(seconds: float) -> str:
        total_seconds = max(0, int(seconds))
        minutes, secs = divmod(total_seconds, 60)
        return f"{minutes:02d}:{secs:02d}"

    def _release_capture(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    # endregion

def merge_videos(
    paths: List[str],
    output_path: str,
    logo_path: str = "",
    status_callback: Optional[Callable[[str], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> str:
    if not paths:
        raise ValueError("Chưa có video nào để merge.")

    status = status_callback or (lambda message: None)
    cancel_check = should_cancel or (lambda: False)

    def ensure_not_cancelled() -> None:
        if cancel_check():
            raise MergeCancelledError("Quá trình merge đã bị hủy.")

    status("Đang chuẩn bị các đoạn video...")

    clips: List[CompositeVideoClip] = []
    positions = []
    slideshow: Optional[CompositeVideoClip] = None
    final_clip: Optional[CompositeVideoClip] = None
    logo_clip = None

    try:
        ensure_not_cancelled()
        for idx, path in enumerate(paths, start=1):
            status(f"Đang xử lý ({idx}/{len(paths)}): {os.path.basename(path)}")
            ensure_not_cancelled()
            clip = VideoFileClip(path)
            fitted, content_box = fit_clip_with_blurred_bg(clip, target_size=TARGET_SIZE)
            fitted = apply_random_kenburns(fitted)
            clips.append(fitted)
            positions.append(content_box)
            ensure_not_cancelled()

        if not clips:
            raise ValueError("Không thể tạo được clip nào từ danh sách đã chọn.")

        status("Đang ghép các đoạn video...")
        ensure_not_cancelled()
        transitions = [random.uniform(*TRANSITION_RANGE) for _ in range(len(clips) - 1)]
        merged_clips = [clips[0]]
        for idx, clip in enumerate(clips[1:], start=1):
            ensure_not_cancelled()
            merged_clips.append(clip.crossfadein(transitions[idx - 1]))

        slideshow = concatenate_videoclips(merged_clips, method="compose")
        ensure_not_cancelled()

        status("Đang chèn logo...")
        ensure_not_cancelled()
        x_off, y_off, _, h_fg = positions[0]
        logo_h = 150
        logo_clip = build_logo_clip(logo_path, logo_h, duration=slideshow.duration)
        logo_clip = logo_clip.set_position((x_off + 10, y_off + h_fg - logo_h - 10))

        final_clip = CompositeVideoClip([slideshow, logo_clip], size=TARGET_SIZE).set_duration(slideshow.duration)

        status("Đang xuất video...")
        ensure_not_cancelled()
        final_clip.write_videofile(
            output_path,
            fps=30,
            codec="libx264",
            audio=True,
            audio_codec="aac",
            audio_bitrate="192k",
            bitrate="6000k",
            threads=4,
            logger=None,
        )
        ensure_not_cancelled()
    finally:
        if final_clip is not None:
            try:
                final_clip.close()
            except Exception:
                pass
        if slideshow is not None:
            try:
                slideshow.close()
            except Exception:
                pass
        if logo_clip is not None:
            try:
                logo_clip.close()
            except Exception:
                pass
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass

    status("Hoàn tất")
    return output_path


class MergeWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IG Merge Video - PyQt5 UI")
        self.resize(1280, 720)

        self.thumbnail_cache = ThumbnailCache()
        self.progress_timer: Optional[QtCore.QTimer] = None
        self.progress_elapsed = QtCore.QElapsedTimer()
        self.progress_status_text = "Đang xử lý..."
        self.progress_bar: Optional[QtWidgets.QProgressBar] = None
        self.progress_container: Optional[QtWidgets.QWidget] = None
        self.progress_cancel_button: Optional[QtWidgets.QAbstractButton] = None
        self._current_output_path: str = ""
        self._pending_close = False

        self._merge_thread: Optional[QtCore.QThread] = None
        self._merge_worker: Optional[MergeWorker] = None
        self.settings = Settings()
        self.settings.load()
        settings = self.settings
        self.last_open_dir = ustr(settings.get(SETTING_LAST_OPEN_DIR, None))
        self.filePath = None

        self._setup_ui()

    # region UI setup
    def _setup_ui(self) -> None:

        self.splitter = QtWidgets.QSplitter()
        self.setCentralWidget(self.splitter)

        self.splitter.setContentsMargins(12, 12, 12, 12)
        
        self.splitter.addWidget(self._build_left_panel())
        self.splitter.addWidget(self._build_right_panel())

    def _build_left_panel(self) -> QtWidgets.QWidget:
        
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setSpacing(8)

        header_layout = QtWidgets.QHBoxLayout()
        header_label = QtWidgets.QLabel("Danh sách video đã chọn")
        header_label.setStyleSheet("font-weight: bold;")
        add_button = QtWidgets.QPushButton("Thêm video...")
        add_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogNewFolder))
        add_button.clicked.connect(self._handle_add_videos)

        clear_button = QtWidgets.QPushButton("Xoá tất cả")
        clear_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_TrashIcon))
        clear_button.clicked.connect(self._clear_video_list)

        header_layout.addWidget(header_label)
        header_layout.addStretch(1)
        header_layout.addWidget(add_button)
        header_layout.addWidget(clear_button)

        self.video_list = QtWidgets.QListWidget()
        self.video_list.setViewMode(QtWidgets.QListView.IconMode)
        self.video_list.setIconSize(QtCore.QSize(160, 90))
        self.video_list.setResizeMode(QtWidgets.QListView.Adjust)
        self.video_list.setMovement(QtWidgets.QListView.Static)
        self.video_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.video_list.itemSelectionChanged.connect(self._handle_video_selection_changed)
        self.video_list.itemDoubleClicked.connect(self._handle_add_to_merge_from_item)

        helper_label = QtWidgets.QLabel("Double-click để thêm vào danh sách merge")
        helper_label.setStyleSheet("color: #666;")

        layout.addLayout(header_layout)
        layout.addWidget(self.video_list, 1)
        layout.addWidget(helper_label)

        widget.setMinimumWidth(300)

        return widget

    def _build_right_panel(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout(widget)
        layout.setSpacing(12)

        layout.addWidget(self._build_player_group(), 0, 0, 1, 1)
        layout.addWidget(self._build_merge_group(), 1, 0, 1, 2)
        layout.addWidget(self._build_output_group(), 0, 1, 1, 1)

        return widget

    def _build_player_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Trình xem video")
        vlayout = QtWidgets.QVBoxLayout(group)
        vlayout.setSpacing(8)

        self.video_player = VideoPreviewWidget()
        self.video_player.errorOccurred.connect(
            lambda message: QtWidgets.QMessageBox.warning(self, "Lỗi phát video", message)
        )

        vlayout.addWidget(self.video_player, 1)

        return group

    def _build_merge_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Tạo video mới")
        layout = QtWidgets.QVBoxLayout(group)
        layout.setSpacing(8)

        list_header_layout = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel("Thứ tự merge")
        label.setStyleSheet("font-weight: bold;")
        add_selected_button = QtWidgets.QPushButton("Thêm các video đã chọn")
        add_selected_button.clicked.connect(self._handle_add_selected_to_merge)
        clear_selected_button = QtWidgets.QPushButton()
        clear_selected_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_TrashIcon))
        clear_selected_button.clicked.connect(self._handle_clear_selected_to_merge)

        list_header_layout.addWidget(label)
        list_header_layout.addStretch(1)
        list_header_layout.addWidget(add_selected_button)
        list_header_layout.addWidget(clear_selected_button)

        self.merge_list = QtWidgets.QListWidget()
        self.merge_list.setFlow(QtWidgets.QListView.LeftToRight)
        self.merge_list.setWrapping(False)
        self.merge_list.setSpacing(12)
        self.merge_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.merge_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.merge_list.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.merge_list.setFixedHeight(180)
        self.merge_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.merge_list.setFocusPolicy(Qt.NoFocus)
        self.merge_list.setDragEnabled(True)
        self.merge_list.setAcceptDrops(True)
        self.merge_list.setDefaultDropAction(Qt.MoveAction)
        self.merge_list.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)

        logo_layout = QtWidgets.QHBoxLayout()
        self.logo_edit = QtWidgets.QLineEdit()
        self.logo_edit.setPlaceholderText("Đường dẫn logo (tuỳ chọn)")
        logo_button = QtWidgets.QPushButton("Chọn logo...")
        logo_button.clicked.connect(self._handle_choose_logo)

        logo_layout.addWidget(self.logo_edit, 1)
        logo_layout.addWidget(logo_button)

        merge_button = QtWidgets.QPushButton("Merge video")
        merge_button.setStyleSheet("font-size: 14px; font-weight: bold; padding: 8px 12px;")
        merge_button.clicked.connect(self._start_merge)
        self.merge_button = merge_button

        layout.addLayout(list_header_layout)
        layout.addWidget(self.merge_list)
        layout.addLayout(logo_layout)
        layout.addWidget(merge_button, alignment=Qt.AlignRight)

        progress_container = QtWidgets.QWidget()
        progress_container.setVisible(False)
        progress_layout = QtWidgets.QHBoxLayout(progress_container)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(8)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.progress_bar.setFormat("Đang xử lý...")

        cancel_button = QtWidgets.QToolButton()
        cancel_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogCancelButton))
        cancel_button.setToolTip("Hủy quá trình tạo video")
        cancel_button.setAutoRaise(True)
        cancel_button.setFixedSize(28, 28)
        cancel_button.clicked.connect(self._cancel_merge)

        progress_layout.addWidget(self.progress_bar, 1)
        progress_layout.addWidget(cancel_button, 0, Qt.AlignRight)

        layout.addWidget(progress_container)

        self.progress_container = progress_container
        self.progress_cancel_button = cancel_button

        return group

    def _build_output_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Video đã tạo")
        layout = QtWidgets.QVBoxLayout(group)
        layout.setSpacing(8)

        self.output_list = QtWidgets.QListWidget()
        self.output_list.setViewMode(QtWidgets.QListView.IconMode)
        self.output_list.setIconSize(QtCore.QSize(160, 90))
        self.output_list.setResizeMode(QtWidgets.QListView.Adjust)
        self.output_list.setMovement(QtWidgets.QListView.Static)
        self.output_list.itemDoubleClicked.connect(self._handle_play_output)

        info_label = QtWidgets.QLabel("Double-click để phát video đã xuất")
        info_label.setStyleSheet("color: #666;")

        layout.addWidget(self.output_list, 1)
        layout.addWidget(info_label)

        return group

    # endregion UI setup

    # region Event handlers
    def _handle_add_videos(self) -> None:
        # Check file IG_video.dat include the last path which is saved in C://Users
        if self.last_open_dir and os.path.exists(self.last_open_dir):
            initial_dir = self.last_open_dir
        else:
            initial_dir = os.path.dirname(self.filePath) if self.filePath else '.'
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Chọn video",
            initial_dir,
            "Video Files (*.mp4 *.mov *.mkv *.avi *.m4v *.webm)"
        )
        if not paths:
            return
        
        self.filePath = paths[-1]
        self.last_open_dir = os.path.dirname(self.filePath)

        for path in paths:
            if not os.path.isfile(path):
                continue
            if any(self.video_list.item(i).data(Qt.UserRole) == path for i in range(self.video_list.count())):
                continue

            item = QtWidgets.QListWidgetItem(os.path.basename(path))
            pixmap = self.thumbnail_cache.get(path, QtCore.QSize(160, 90))
            if not pixmap.isNull():
                item.setIcon(QtGui.QIcon(pixmap))
            item.setData(Qt.UserRole, path)
            self.video_list.addItem(item)

    def _clear_video_list(self) -> None:
        self.video_list.clear()

    def _handle_video_selection_changed(self) -> None:
        items = self.video_list.selectedItems()
        if not items:
            return
        path = items[0].data(Qt.UserRole)
        self._play_video(path)

    def _handle_add_to_merge_from_item(self, item: QtWidgets.QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        self._add_to_merge(path)

    def _handle_add_selected_to_merge(self) -> None:
        for item in self.video_list.selectedItems():
            self._add_to_merge(item.data(Qt.UserRole))

    def _handle_clear_selected_to_merge(self) -> None:
        self.merge_list.clear()

    def _handle_choose_logo(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Chọn logo",
            "",
            "Hình ảnh (*.png *.jpg *.jpeg *.bmp)"
        )
        if path:
            self.logo_edit.setText(path)

    def _handle_play_output(self, item: QtWidgets.QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        if os.path.exists(path):
            self._play_video(path)
        else:
            QtWidgets.QMessageBox.warning(self, "Không tìm thấy", "File video không còn tồn tại.")

    # endregion

    # region Merge logic
    def _add_to_merge(self, path: str) -> None:
        if not path:
            return
        if any(self.merge_list.item(i).data(Qt.UserRole) == path for i in range(self.merge_list.count())):
            return

        pixmap = self.thumbnail_cache.get(path, QtCore.QSize(160, 90))
        widget = MergeQueueItem(path, pixmap)
        widget.removeRequested.connect(self._remove_from_merge)

        item = QtWidgets.QListWidgetItem()
        item.setData(Qt.UserRole, path)
        size_hint = widget.sizeHint()
        item.setSizeHint(size_hint)

        self.merge_list.addItem(item)
        self.merge_list.setItemWidget(item, widget)

    def _remove_from_merge(self, path: str) -> None:
        for idx in range(self.merge_list.count()):
            item = self.merge_list.item(idx)
            if item is not None and item.data(Qt.UserRole) == path:
                widget = self.merge_list.itemWidget(item)
                self.merge_list.takeItem(idx)
                if widget is not None:
                    widget.deleteLater()
                break

    def _start_merge(self) -> None:
        paths = [self.merge_list.item(i).data(Qt.UserRole) for i in range(self.merge_list.count())]
        paths = [p for p in paths if p]
        if not paths:
            QtWidgets.QMessageBox.information(self, "Thiếu dữ liệu", "Hãy thêm ít nhất một video vào danh sách merge.")
            return
        folder_name = os.path.dirname(paths[0])
        folder_save = os.path.dirname(self.last_open_dir) if self.last_open_dir and os.path.exists(self.last_open_dir) and os.path.exists(os.path.dirname(self.last_open_dir)) else folder_name
        output_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Lưu video", 
            os.path.join(folder_save, f"{folder_name}.mp4"),
            "MP4 Files (*.mp4)"
        )
        if not output_path:
            return

        logo_path = self.logo_edit.text().strip()

        self._merge_thread = QtCore.QThread(self)
        self._merge_worker = MergeWorker(paths, output_path, logo_path)
        self._merge_worker.moveToThread(self._merge_thread)

        self._merge_thread.started.connect(self._merge_worker.run)
        self._merge_worker.finished.connect(self._on_merge_finished)
        self._merge_worker.error.connect(self._on_merge_error)
        self._merge_worker.status.connect(self._on_merge_status)
        self._merge_worker.cancelled.connect(self._on_merge_cancelled)

        self._merge_worker.finished.connect(self._merge_thread.quit)
        self._merge_worker.error.connect(self._merge_thread.quit)
        self._merge_worker.cancelled.connect(self._merge_thread.quit)
        self._merge_worker.finished.connect(self._merge_worker.deleteLater)
        self._merge_worker.error.connect(self._merge_worker.deleteLater)
        self._merge_worker.cancelled.connect(self._merge_worker.deleteLater)
        self._merge_thread.finished.connect(self._merge_thread.deleteLater)

        self.merge_button.setEnabled(False)
        self.progress_status_text = "Đang chuẩn bị..."
        self._current_output_path = output_path
        self._show_progress_panel()

        self._merge_thread.start()

    def _on_merge_finished(self, output_path: str) -> None:
        self.merge_button.setEnabled(True)
        self._stop_progress_panel()
        self._merge_thread = None
        self._merge_worker = None

        QtWidgets.QMessageBox.information(self, "Hoàn tất", f"Đã tạo video: {output_path}")
        if os.path.exists(output_path):
            pixmap = self.thumbnail_cache.get(output_path, QtCore.QSize(160, 90))
            item = QtWidgets.QListWidgetItem(os.path.basename(output_path))
            if not pixmap.isNull():
                item.setIcon(QtGui.QIcon(pixmap))
            item.setData(Qt.UserRole, output_path)
            self.output_list.addItem(item)
            self._play_video(output_path)
        self._current_output_path = ""
        self._handle_pending_close_after_merge()

    def _on_merge_error(self, message: str) -> None:
        self.merge_button.setEnabled(True)
        self._stop_progress_panel()
        self._merge_thread = None
        self._merge_worker = None
        if self._current_output_path and os.path.exists(self._current_output_path):
            try:
                os.remove(self._current_output_path)
            except Exception:
                pass
        self._current_output_path = ""
        self._handle_pending_close_after_merge()
        QtWidgets.QMessageBox.critical(self, "Lỗi", f"Không thể merge video:\n{message}")

    def _on_merge_status(self, message: str) -> None:
        self.progress_status_text = message
        self._update_progress_panel()

    def _show_progress_panel(self) -> None:
        if self.progress_container is None or self.progress_bar is None:
            return

        if self.progress_timer is not None:
            self.progress_timer.stop()
            self.progress_timer.deleteLater()

        self.progress_timer = QtCore.QTimer(self)
        self.progress_timer.timeout.connect(self._update_progress_panel)
        self.progress_elapsed.start()
        self.progress_container.setVisible(True)
        if self.progress_cancel_button is not None:
            self.progress_cancel_button.setEnabled(True)
        self.progress_bar.setRange(0, 0)
        self._update_progress_panel()
        self.progress_timer.start(500)

    def _stop_progress_panel(self) -> None:
        if self.progress_timer is not None:
            self.progress_timer.stop()
            self.progress_timer.deleteLater()
            self.progress_timer = None
        if self.progress_container is not None:
            self.progress_container.setVisible(False)
        if self.progress_bar is not None:
            self.progress_bar.reset()
            self.progress_bar.setFormat("Đang xử lý...")
        if self.progress_cancel_button is not None:
            self.progress_cancel_button.setEnabled(True)

    def _update_progress_panel(self) -> None:
        if self.progress_bar is None or self.progress_container is None or not self.progress_container.isVisible():
            return
        elapsed = self.progress_elapsed.elapsed() / 1000.0

        def convert_seconds(seconds: float) -> str:
            return time.strftime("%H:%M:%S", time.gmtime(max(0.0, seconds)))

        self.progress_bar.setFormat(f"{self.progress_status_text} - Thời gian: {convert_seconds(elapsed)}")

    def _cancel_merge(self) -> None:
        if not self._merge_worker or not self._merge_thread or not self._merge_thread.isRunning():
            return
        self.progress_status_text = "Đang hủy tiến trình..."
        if self.progress_cancel_button is not None:
            self.progress_cancel_button.setEnabled(False)
        self._update_progress_panel()
        self._merge_worker.request_cancel()
        self._merge_thread.requestInterruption()

    def _on_merge_cancelled(self, output_path: str) -> None:
        self.merge_button.setEnabled(True)
        self._stop_progress_panel()
        self._merge_thread = None
        self._merge_worker = None
        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass
        self._current_output_path = ""
        self._handle_pending_close_after_merge()
        QtWidgets.QMessageBox.information(self, "Đã hủy", "Quá trình merge video đã bị hủy.")

    def _handle_pending_close_after_merge(self) -> None:
        if self._pending_close:
            self._pending_close = False
            QtCore.QTimer.singleShot(0, self.close)

    # endregion

    def _play_video(self, path: str) -> None:
        if not path:
            return
        self.video_player.load(path)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # pragma: no cover - GUI close behaviour
        if self._merge_thread and self._merge_thread.isRunning():
            answer = QtWidgets.QMessageBox.question(
                self,
                "Đang xử lý",
                "Quá trình merge đang diễn ra. Bạn có muốn hủy và thoát?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if answer == QtWidgets.QMessageBox.Yes:
                self._pending_close = True
                self._cancel_merge()
            event.ignore()
            return
        self.video_player.shutdown()
        self.thumbnail_cache.clear()
        # Save settings
        settings = self.settings
        if self.last_open_dir and os.path.exists(self.last_open_dir):
            settings[SETTING_LAST_OPEN_DIR] = self.last_open_dir
        else:
            settings[SETTING_LAST_OPEN_DIR] = ''
        settings.save()

        super().closeEvent(event)


def main() -> None:
    QtWidgets.QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QtWidgets.QApplication(sys.argv)
    try:
        with open("MacOS.qss", 'r') as f:
            app.setStyleSheet(f.read())
    except: pass
    window = MergeWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
