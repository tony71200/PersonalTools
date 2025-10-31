import os
import sys
import random
import traceback
from typing import Callable, Dict, List, Optional

from PyQt5 import QtCore, QtGui, QtWidgets, QtMultimedia, QtMultimediaWidgets
from PyQt5.QtCore import Qt

from moviepy.editor import VideoFileClip, CompositeVideoClip, concatenate_videoclips

from video.ig_merge_video_cmd import (
    TARGET_SIZE,
    TRANSITION_RANGE,
    apply_random_kenburns,
    build_logo_clip,
    fit_clip_with_blurred_bg,
)


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

    @staticmethod
    def _generate_thumbnail(path: str, size: QtCore.QSize) -> QtGui.QPixmap:
        try:
            import cv2
        except ImportError:  # pragma: no cover - cv2 is required by the original script
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


class MergeWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(str)
    status = QtCore.pyqtSignal(str)

    def __init__(self, paths: List[str], output_path: str, logo_path: str = ""):
        super().__init__()
        self._paths = paths
        self._output_path = output_path
        self._logo_path = logo_path

    @QtCore.pyqtSlot()
    def run(self) -> None:
        try:
            merge_videos(
                self._paths,
                self._output_path,
                logo_path=self._logo_path,
                status_callback=self.status.emit,
            )
        except Exception as exc:  # pragma: no cover - GUI runtime behaviour
            traceback.print_exc()
            self.error.emit(str(exc))
        else:
            self.finished.emit(self._output_path)


def merge_videos(
    paths: List[str],
    output_path: str,
    logo_path: str = "",
    status_callback: Optional[Callable[[str], None]] = None,
) -> str:
    if not paths:
        raise ValueError("Chưa có video nào để merge.")

    status = status_callback or (lambda message: None)
    status("Đang chuẩn bị các đoạn video...")

    clips: List[CompositeVideoClip] = []
    positions = []
    slideshow: Optional[CompositeVideoClip] = None
    final_clip: Optional[CompositeVideoClip] = None
    logo_clip = None

    try:
        for idx, path in enumerate(paths, start=1):
            status(f"Đang xử lý ({idx}/{len(paths)}): {os.path.basename(path)}")
            clip = VideoFileClip(path)
            fitted, content_box = fit_clip_with_blurred_bg(clip, target_size=TARGET_SIZE)
            fitted = apply_random_kenburns(fitted)
            clips.append(fitted)
            positions.append(content_box)

        if not clips:
            raise ValueError("Không thể tạo được clip nào từ danh sách đã chọn.")

        status("Đang ghép các đoạn video...")
        transitions = [random.uniform(*TRANSITION_RANGE) for _ in range(len(clips) - 1)]
        merged_clips = [clips[0]]
        for idx, clip in enumerate(clips[1:], start=1):
            merged_clips.append(clip.crossfadein(transitions[idx - 1]))

        slideshow = concatenate_videoclips(merged_clips, method="compose")

        status("Đang chèn logo...")
        x_off, y_off, _, h_fg = positions[0]
        logo_h = 150
        logo_clip = build_logo_clip(logo_path, logo_h, duration=slideshow.duration)
        logo_clip = logo_clip.set_position((x_off + 10, y_off + h_fg - logo_h - 10))

        final_clip = CompositeVideoClip([slideshow, logo_clip], size=TARGET_SIZE).set_duration(slideshow.duration)

        status("Đang xuất video...")
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
        self.progress_dialog: Optional[QtWidgets.QProgressDialog] = None
        self.progress_timer: Optional[QtCore.QTimer] = None
        self.progress_elapsed = QtCore.QElapsedTimer()
        self.progress_status_text = "Đang xử lý..."

        self._merge_thread: Optional[QtCore.QThread] = None
        self._merge_worker: Optional[MergeWorker] = None

        self._setup_ui()

    # region UI setup
    def _setup_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        main_layout = QtWidgets.QHBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        main_layout.addLayout(self._build_left_panel(), 1)
        main_layout.addLayout(self._build_right_panel(), 2)

    def _build_left_panel(self) -> QtWidgets.QLayout:
        layout = QtWidgets.QVBoxLayout()
        layout.setSpacing(8)

        header_layout = QtWidgets.QHBoxLayout()
        header_label = QtWidgets.QLabel("Danh sách video đã chọn")
        header_label.setStyleSheet("font-weight: bold;")
        add_button = QtWidgets.QPushButton("Thêm video...")
        add_button.clicked.connect(self._handle_add_videos)

        header_layout.addWidget(header_label)
        header_layout.addStretch(1)
        header_layout.addWidget(add_button)

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

        return layout

    def _build_right_panel(self) -> QtWidgets.QLayout:
        layout = QtWidgets.QVBoxLayout()
        layout.setSpacing(12)

        layout.addWidget(self._build_player_group(), 2)
        layout.addWidget(self._build_merge_group())
        layout.addWidget(self._build_output_group(), 1)

        return layout

    def _build_player_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Trình xem video")
        vlayout = QtWidgets.QVBoxLayout(group)
        vlayout.setSpacing(8)

        self.media_player = QtMultimedia.QMediaPlayer(None, QtMultimedia.QMediaPlayer.VideoSurface)
        self.video_widget = QtMultimediaWidgets.QVideoWidget()
        self.media_player.setVideoOutput(self.video_widget)

        control_layout = QtWidgets.QHBoxLayout()
        self.play_button = QtWidgets.QPushButton("▶ Phát")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self._toggle_playback)

        self.position_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderMoved.connect(self.media_player.setPosition)

        self.media_player.positionChanged.connect(self._on_position_changed)
        self.media_player.durationChanged.connect(self._on_duration_changed)
        self.media_player.stateChanged.connect(self._on_state_changed)

        control_layout.addWidget(self.play_button)
        control_layout.addWidget(self.position_slider, 1)

        vlayout.addWidget(self.video_widget, 1)
        vlayout.addLayout(control_layout)

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

        list_header_layout.addWidget(label)
        list_header_layout.addStretch(1)
        list_header_layout.addWidget(add_selected_button)

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
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Chọn video",
            "",
            "Video Files (*.mp4 *.mov *.mkv *.avi *.m4v *.webm)"
        )
        if not paths:
            return

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

    def _toggle_playback(self) -> None:
        if self.media_player.state() == QtMultimedia.QMediaPlayer.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def _on_position_changed(self, position: int) -> None:
        self.position_slider.blockSignals(True)
        self.position_slider.setValue(position)
        self.position_slider.blockSignals(False)

    def _on_duration_changed(self, duration: int) -> None:
        self.position_slider.setRange(0, duration)
        self.play_button.setEnabled(duration > 0)

    def _on_state_changed(self, state: QtMultimedia.QMediaPlayer.State) -> None:
        if state == QtMultimedia.QMediaPlayer.PlayingState:
            self.play_button.setText("⏸ Tạm dừng")
        else:
            self.play_button.setText("▶ Phát")

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

        output_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Lưu video", "merged_output.mp4", "MP4 Files (*.mp4)"
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

        self._merge_worker.finished.connect(self._merge_thread.quit)
        self._merge_worker.error.connect(self._merge_thread.quit)
        self._merge_worker.finished.connect(self._merge_worker.deleteLater)
        self._merge_worker.error.connect(self._merge_worker.deleteLater)
        self._merge_thread.finished.connect(self._merge_thread.deleteLater)

        self.merge_button.setEnabled(False)
        self.progress_status_text = "Đang chuẩn bị..."
        self._show_progress_dialog()

        self._merge_thread.start()

    def _on_merge_finished(self, output_path: str) -> None:
        self.merge_button.setEnabled(True)
        self._stop_progress_dialog()
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

    def _on_merge_error(self, message: str) -> None:
        self.merge_button.setEnabled(True)
        self._stop_progress_dialog()
        self._merge_thread = None
        self._merge_worker = None
        QtWidgets.QMessageBox.critical(self, "Lỗi", f"Không thể merge video:\n{message}")

    def _on_merge_status(self, message: str) -> None:
        self.progress_status_text = message

    def _show_progress_dialog(self) -> None:
        self.progress_dialog = QtWidgets.QProgressDialog("Đang xử lý...", None, 0, 0, self)
        self.progress_dialog.setWindowTitle("Merge video")
        self.progress_dialog.setCancelButton(None)
        self.progress_dialog.setWindowModality(Qt.ApplicationModal)
        self.progress_dialog.show()

        self.progress_elapsed.start()
        self.progress_timer = QtCore.QTimer(self)
        self.progress_timer.timeout.connect(self._update_progress_dialog)
        self.progress_timer.start(500)

    def _stop_progress_dialog(self) -> None:
        if self.progress_timer is not None:
            self.progress_timer.stop()
            self.progress_timer.deleteLater()
            self.progress_timer = None
        if self.progress_dialog is not None:
            self.progress_dialog.close()
            self.progress_dialog.deleteLater()
            self.progress_dialog = None

    def _update_progress_dialog(self) -> None:
        if self.progress_dialog is None:
            return
        elapsed = self.progress_elapsed.elapsed() / 1000.0
        self.progress_dialog.setLabelText(f"{self.progress_status_text}\nThời gian: {elapsed:.1f}s")

    # endregion

    def _play_video(self, path: str) -> None:
        if not path:
            return
        url = QtCore.QUrl.fromLocalFile(path)
        self.media_player.setMedia(QtMultimedia.QMediaContent(url))
        self.media_player.play()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # pragma: no cover - GUI close behaviour
        if self._merge_thread and self._merge_thread.isRunning():
            QtWidgets.QMessageBox.warning(self, "Đang xử lý", "Vui lòng đợi quá trình merge kết thúc.")
            event.ignore()
            return
        super().closeEvent(event)


def main() -> None:
    QtWidgets.QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QtWidgets.QApplication(sys.argv)
    window = MergeWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
