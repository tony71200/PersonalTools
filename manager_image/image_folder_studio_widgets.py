"""Background jobs and image views shared by the two folder tools."""

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Callable

from PyQt5.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QBrush, QColor, QIcon, QImage, QImageIOHandler, QImageReader, QPalette, QPixmap
from PyQt5.QtWidgets import QListView, QListWidget, QListWidgetItem, QStyle, QStyledItemDelegate


MATCH_BACKGROUND = QBrush(QColor("#cdeed8"))
MATCH_FOREGROUND = QBrush(QColor("#174b30"))
THUMB_SIZE = QSize(116, 84)


class MatchDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if index.data(Qt.BackgroundRole) == MATCH_BACKGROUND:
            option.palette.setColor(QPalette.Highlight, QColor("#a0d8b2"))
            option.palette.setBrush(QPalette.HighlightedText, MATCH_FOREGROUND)


class _JobSignals(QObject):
    result = pyqtSignal(object)
    error = pyqtSignal(str)


class _Runnable(QRunnable):
    def __init__(self, work):
        super().__init__()
        self.work = work
        self.signals = _JobSignals()

    def run(self):
        try:
            value = self.work()
        except Exception as error:
            self.signals.error.emit(str(error))
        else:
            self.signals.result.emit(value)


class BackgroundJob(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def start(self, work: Callable[[], object], priority: int = 0) -> None:
        task = _Runnable(work)
        task.signals.result.connect(self._deliver, Qt.QueuedConnection)
        task.signals.error.connect(self._fail, Qt.QueuedConnection)
        QThreadPool.globalInstance().start(task, priority)

    @pyqtSlot(object)
    def _deliver(self, value):
        self.finished.emit(value)
        self.deleteLater()

    @pyqtSlot(str)
    def _fail(self, message):
        self.failed.emit(message)
        self.deleteLater()


def run_background(owner, work, finished, failed, *, priority=0):
    job = BackgroundJob(owner)
    job.finished.connect(finished)
    job.failed.connect(failed)
    job.start(work, priority)


def read_scaled_image(path: Path, bounds: QSize) -> QImage:
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    decode_bounds = QSize(bounds)
    if reader.transformation() & QImageIOHandler.TransformationRotate90:
        decode_bounds.transpose()
    if size.isValid() and (size.width() > decode_bounds.width() or size.height() > decode_bounds.height()):
        reader.setScaledSize(size.scaled(decode_bounds, Qt.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        raise OSError(f"{path}: {reader.errorString()}")
    if image.width() > bounds.width() or image.height() > bounds.height():
        image = image.scaled(bounds, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return image


class ImageLoader(QObject):
    ready = pyqtSignal(int, object, QImage)
    failed = pyqtSignal(int, object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cache = OrderedDict()
        self._lock = Lock()

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def _thumbnail(self, path, bounds):
        info = path.stat()
        key = (path, info.st_mtime_ns, info.st_size, bounds.width(), bounds.height())
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        image = read_scaled_image(path, bounds)
        with self._lock:
            self._cache[key] = image
            if len(self._cache) > 256:
                self._cache.popitem(last=False)
        return image

    def request(self, path: Path, bounds: QSize, generation: int, *, cache: bool = True) -> None:
        read = self._thumbnail if cache else read_scaled_image
        run_background(
            self, lambda: read(path, bounds),
            lambda image: self.ready.emit(generation, path, image),
            lambda message: self.failed.emit(generation, path, message),
            priority=-1 if cache else 1,
        )


@dataclass(frozen=True)
class Tile:
    path: Path
    label: str
    preview: Path | None = None
    folder: bool = False
    matched: bool = False


class PreviewGrid(QListWidget):
    image_error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setWrapping(True)
        self.setWordWrap(True)
        self.setUniformItemSizes(True)
        self.setIconSize(THUMB_SIZE)
        self.setGridSize(QSize(150, 120))
        self.setItemDelegate(MatchDelegate(self))
        self.setVerticalScrollMode(QListView.ScrollPerPixel)
        self._folder_icon = self.style().standardIcon(QStyle.SP_DirIcon)
        self._file_icon = self.style().standardIcon(QStyle.SP_FileIcon)
        self._loader = ImageLoader(self)
        self._loader.ready.connect(self._apply_thumbnail)
        self._loader.failed.connect(self._thumbnail_error)
        self._tiles = {}
        self._items = {}
        self._visible = set()
        self._pending = set()
        self._loaded = set()
        self._failed = set()
        self._generation = 0
        self._timer = QTimer(self, singleShot=True, interval=40)
        self._timer.timeout.connect(self._request_visible)
        self.verticalScrollBar().valueChanged.connect(self._schedule)

    def clear_cache(self):
        self._loader.clear_cache()

    def set_tiles(self, tiles):
        self._generation += 1
        self._visible.clear()
        self._pending.clear()
        self._loaded.clear()
        self._failed.clear()
        self._tiles = {tile.path: tile for tile in tiles}
        self._items.clear()
        self.clear()
        for tile in self._tiles.values():
            item = QListWidgetItem(self._placeholder(tile), tile.label)
            item.setSizeHint(QSize(144, 113))
            item.setData(Qt.UserRole, tile.path)
            item.setToolTip(f"{tile.label}\n{tile.path}")
            if tile.matched:
                item.setBackground(MATCH_BACKGROUND)
                item.setForeground(MATCH_FOREGROUND)
            self._items[tile.path] = item
            self.addItem(item)
        self._schedule()

    def select_path(self, path):
        item = self._items.get(path)
        self.setCurrentItem(item)
        if item is not None:
            self.scrollToItem(item)

    def _placeholder(self, tile):
        return self._folder_icon if tile.folder else self._file_icon

    def _schedule(self, *_):
        self._timer.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule()

    def showEvent(self, event):
        super().showEvent(event)
        self._schedule()

    def _request_visible(self):
        if not self.isVisible():
            return
        bounds = self.viewport().rect()
        visible = {
            path for path, item in self._items.items()
            if self._tiles[path].preview and bounds.intersects(self.visualItemRect(item))
        }
        for path in self._loaded - visible:
            self._items[path].setIcon(self._placeholder(self._tiles[path]))
        self._loaded.intersection_update(visible)
        self._visible = visible
        # One source image can be the cover for both a folder and an image tile.
        for path in visible - self._loaded - self._failed:
            preview = self._tiles[path].preview
            if preview not in self._pending:
                self._pending.add(preview)
                self._loader.request(preview, THUMB_SIZE, self._generation)

    def _apply_thumbnail(self, generation, preview, image):
        if generation != self._generation:
            return
        self._pending.discard(preview)
        icon = QIcon(QPixmap.fromImage(image))
        for path in self._visible:
            if self._tiles[path].preview == preview:
                self._items[path].setIcon(icon)
                self._loaded.add(path)

    def _thumbnail_error(self, generation, preview, message):
        if generation == self._generation:
            self._pending.discard(preview)
            self._failed.update(path for path in self._tiles if self._tiles[path].preview == preview)
            self.image_error.emit(message)
