"""Disk capacity and folder usage for Image Folder Studio."""

from dataclasses import dataclass
from pathlib import Path
import re

from PyQt5.QtCore import QSignalBlocker, QStorageInfo, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFileDialog, QHeaderView, QLabel, QProgressBar, QPushButton, QSizePolicy,
    QStyle, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from image_folder_studio_core import TreeSnapshot, scan_tree
from image_folder_studio_widgets import run_background


@dataclass(frozen=True)
class DriveUsage:
    letter: str
    label: str
    total_bytes: int
    free_bytes: int

    @property
    def used_bytes(self) -> int:
        return self.total_bytes - self.free_bytes


def read_drives() -> tuple[DriveUsage, ...]:
    drives = {}
    for volume in QStorageInfo.mountedVolumes():
        if not volume.isValid() or not volume.isReady():
            continue
        drive = re.fullmatch(r"([A-Za-z]:)/?", volume.rootPath().replace("\\", "/"))
        if drive is None:
            continue
        letter = drive[1].upper()
        total, free = volume.bytesTotal(), volume.bytesFree()
        if letter not in drives and total > 0 and 0 <= free <= total:
            drives[letter] = DriveUsage(letter, volume.name(), total, free)
    return tuple(drives[letter] for letter in sorted(drives))


def _format_number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def format_bytes(size: int) -> str:
    for unit, scale in (("TB", 10**12), ("GB", 10**9), ("MB", 10**6), ("KB", 10**3)):
        if size >= scale:
            return f"{_format_number(size / scale)} {unit}"
    return f"{size} B"


def format_ratio(name: str, used: int, total: int) -> tuple[int, str]:
    capacity = f"{name} — {format_bytes(used)} / {format_bytes(total)}"
    if total == 0:
        return 0, f"{capacity} (—)"
    ratio = used / total
    return round(10_000 * ratio), f"{capacity} ({_format_number(100 * ratio)}%)"


class DiskUsageTab(QWidget):
    loaded = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._generation = 0
        self._root = None
        self._snapshot = None
        self._this_pc_item = None

        pick = QPushButton("Chọn thư mục…")
        self.summary = QLabel()
        self.status = QLabel()
        for label in (self.summary, self.status):
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.bar = QProgressBar()
        self.bar.setRange(0, 10_000)
        self.bar.setTextVisible(False)
        self.bar.setValue(0)
        self.bar.setAccessibleName("Tỷ lệ dung lượng")

        self.tree = QTreeWidget()
        self.tree.setUniformRowHeights(True)
        self.tree.header().setStretchLastSection(False)

        layout = QVBoxLayout(self)
        layout.addWidget(pick, alignment=Qt.AlignLeft)
        layout.addWidget(self.summary)
        layout.addWidget(self.bar)
        layout.addWidget(self.status)
        layout.addWidget(self.tree, 1)

        pick.clicked.connect(self._pick_folder)
        self.tree.currentItemChanged.connect(self._select_item)
        self.tree.itemClicked.connect(self._activate_item)
        self.tree.itemActivated.connect(self._activate_item)

    def showEvent(self, event):
        super().showEvent(event)
        if self._generation == 0:
            self.show_this_pc()

    def _pick_folder(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục để xem dung lượng", str(self._root or "")
        )
        if directory:
            self.set_root(Path(directory))

    def show_this_pc(self) -> None:
        self._root = None
        self._reset_tree(["Tên", "Đã dùng", "Còn trống", "Tổng"])
        self._load(read_drives, self._render_drives, "Đang đọc thông tin ổ đĩa…")

    def set_root(self, root: Path) -> None:
        self._root = root
        self._reset_tree(["Tên", "Dung lượng"])
        self._load(lambda: scan_tree(root), self._render_folders, f"Đang quét {root}…")

    def _reset_tree(self, columns):
        self._snapshot = None
        with QSignalBlocker(self.tree):
            self.tree.clear()
            self.tree.setColumnCount(len(columns))
            self.tree.setHeaderLabels(columns)
            self.tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
            self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
            self._this_pc_item = QTreeWidgetItem(self.tree, ["This PC"])
            self._this_pc_item.setIcon(0, self.style().standardIcon(QStyle.SP_ComputerIcon))
            if self._root is not None:
                self._this_pc_item.setToolTip(0, "Quay lại danh sách ổ đĩa")
        self._select_item(None)

    def _load(self, work, render, loading):
        self._generation += 1
        generation = self._generation
        self._set_status(loading)

        def accept(result):
            if generation == self._generation:
                self._set_status("")
                render(result)
                self.loaded.emit()

        def fail(message):
            if generation == self._generation:
                self._set_status(message)
                self.loaded.emit()

        run_background(self, work, accept, fail)

    def _set_status(self, message):
        self.status.setText(message)
        self.status.setVisible(bool(message))

    def _render_drives(self, drives):
        icon = self.style().standardIcon(QStyle.SP_DriveHDIcon)
        for drive in drives:
            name = f"{drive.label} ({drive.letter})" if drive.label else drive.letter
            item = QTreeWidgetItem(self._this_pc_item, [
                name, format_bytes(drive.used_bytes), format_bytes(drive.free_bytes),
                format_bytes(drive.total_bytes),
            ])
            item.setIcon(0, icon)
            item.setData(0, Qt.UserRole, drive)
        self._this_pc_item.setExpanded(True)
        if not drives:
            self._set_status("Không có ổ đĩa khả dụng.")

    def _render_folders(self, snapshot: TreeSnapshot):
        if snapshot.root_unreadable:
            self._set_status(f"Không đọc được thư mục. {snapshot.errors[0]}")
            return

        self._snapshot = snapshot
        root_item = self._folder_item(self.tree, snapshot.root)
        pending = [(snapshot.root, root_item)]
        while pending:
            folder, item = pending.pop()
            children = sorted(snapshot.folders[folder].children, key=lambda child: (
                -snapshot.folders[child].total_bytes, child.name.casefold(), child.name,
            ))
            for child in children:
                pending.append((child, self._folder_item(item, child)))
        root_item.setExpanded(True)
        self.tree.setCurrentItem(root_item)
        if snapshot.errors:
            self._set_status(f"Dung lượng chưa đầy đủ · {len(snapshot.errors)} lỗi đọc.")

    def _folder_item(self, parent, folder):
        size = self._snapshot.folders[folder].total_bytes
        item = QTreeWidgetItem(parent, [folder.name or str(folder), format_bytes(size)])
        item.setData(0, Qt.UserRole, folder)
        errors = self._snapshot.errors_by_folder.get(folder, ())
        item.setToolTip(0, "\n".join((str(folder), *errors)))
        item.setToolTip(1, f"{size:,} B".replace(",", "."))
        return item

    def _select_item(self, item, _previous=None):
        data = item.data(0, Qt.UserRole) if item is not None else None
        if isinstance(data, DriveUsage):
            value, caption = format_ratio(item.text(0), data.used_bytes, data.total_bytes)
        elif isinstance(data, Path):
            folders = self._snapshot.folders
            value, caption = format_ratio(
                item.text(0), folders[data].total_bytes, folders[self._snapshot.root].total_bytes
            )
        else:
            value = 0
            caption = "Chọn một ổ đĩa hoặc thư mục." if self._root is None else ""
        self.bar.setValue(value)
        self.summary.setText(caption)

    def _activate_item(self, item, _column):
        if item is self._this_pc_item and self._root is not None:
            self.show_this_pc()
