"""Compare image folders by filename and organize files with PyQt5."""

import os
from pathlib import Path
import sys

from PyQt5.QtCore import QMimeDatabase, QSignalBlocker, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QSizePolicy, QSplitter, QStackedWidget, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from image_folder_studio_core import (
    compare_trees, copy_file, create_numbered_folder, is_image, move_file, scan_tree, trash_file,
)
from image_folder_studio_widgets import (
    MATCH_BACKGROUND, MATCH_FOREGROUND, ImageLoader, MatchDelegate, PreviewGrid, Tile, run_background,
)


class PathLabel(QLabel):
    def __init__(self, initial):
        super().__init__()
        self.setTextFormat(Qt.PlainText)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.set_value(initial)

    def set_value(self, value):
        self.setToolTip(str(value))
        self._elide()

    def _elide(self):
        self.setText(self.fontMetrics().elidedText(self.toolTip(), Qt.ElideMiddle, self.width()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()


class FolderTree(QTreeWidget):
    def __init__(self, *, counts=False):
        super().__init__()
        self.counts = counts
        self.items = {}
        if counts:
            self.setHeaderLabels(["Tên", "Con", "Thư mục", "Ảnh"])
            for column, description in enumerate(
                ("Tên", "Thư mục con trực tiếp", "Tổng thư mục ở các cấp bên dưới", "Tổng ảnh trong nhánh")
            ):
                self.headerItem().setToolTip(column, description)
            self.header().setSectionResizeMode(QHeaderView.ResizeToContents)
            self.header().setStretchLastSection(False)
            self.header().setSectionResizeMode(0, QHeaderView.Stretch)
        else:
            self.setHeaderHidden(True)
            self.setItemDelegate(MatchDelegate(self))
        self.setUniformRowHeights(True)

    def rebuild(self, snapshot, accepts, matches, *, hide_empty=False):
        expanded = {path for path, item in self.items.items() if item.isExpanded()}
        self.items.clear()
        self.clear()
        if snapshot is None or snapshot.root not in snapshot.folders:
            return
        visible_files = {}
        visible_folders = set()
        # Snapshots store child entries before their parents.
        for folder, entry in snapshot.folders.items():
            files = [path for path in entry.files if accepts(path)]
            visible_files[folder] = files
            if files or not hide_empty or folder == snapshot.root or visible_folders.intersection(entry.children):
                visible_folders.add(folder)
        root_item = self._folder_item(snapshot.root, snapshot.folders[snapshot.root])
        self.addTopLevelItem(root_item)
        pending = [snapshot.root]
        while pending:
            folder = pending.pop()
            item = self.items[folder]
            children = [path for path in snapshot.folders[folder].children if path in visible_folders]
            for child in children:
                item.addChild(self._folder_item(child, snapshot.folders[child]))
            for path in visible_files[folder]:
                matched = path in matches
                leaf = self._item(path, [f"✓ {path.name}" if matched else path.name])
                if matched:
                    leaf.setBackground(0, MATCH_BACKGROUND)
                    leaf.setForeground(0, MATCH_FOREGROUND)
                item.addChild(leaf)
            item.setExpanded(folder == snapshot.root or folder in expanded)
            pending.extend(reversed(children))

    def _folder_item(self, path, entry):
        columns = [path.name or str(path)]
        if self.counts:
            columns.extend(map(str, (len(entry.children), entry.descendant_count, entry.image_count)))
        return self._item(path, columns)

    def _item(self, path, columns):
        item = QTreeWidgetItem(columns)
        item.setData(0, Qt.UserRole, path)
        item.setToolTip(0, str(path))
        self.items[path] = item
        return item

    def select_path(self, path):
        item = self.items.get(path)
        self.setCurrentItem(item)
        if item is not None:
            self.scrollToItem(item)


def read_only_text(placeholder, *, max_blocks=0):
    view = QPlainTextEdit(readOnly=True)
    view.setPlaceholderText(placeholder)
    view.setMaximumBlockCount(max_blocks)
    return view


def pick_folder(parent, initial=None):
    path = QFileDialog.getExistingDirectory(parent, "Chọn thư mục", str(initial or ""))
    return Path(path) if path else None


def format_rate(matched: int, total: int) -> str:
    if not total:
        return "— (0/0)"
    value = f"{100 * matched / total:.2f}".rstrip("0").rstrip(".")
    return f"{value}% ({matched}/{total})"


class FolderPane(QGroupBox):
    path_selected = pyqtSignal(object)

    def __init__(self, side):
        super().__init__(f"Thư mục {side}")
        self.root = None
        self.snapshot = None
        self.generation = 0
        self.selected = None
        self._folder = None
        self._filter_mode = 0
        self._matches = {}
        self.pick = QPushButton("Chọn thư mục…")
        self.path = PathLabel("Chưa chọn thư mục")
        self.tree = FolderTree()
        self.grid = PreviewGrid()
        split = QSplitter(Qt.Vertical)
        split.setChildrenCollapsible(False)
        split.addWidget(self.tree)
        split.addWidget(self.grid)
        split.setSizes([310, 235])
        layout = QVBoxLayout(self)
        layout.addWidget(self.pick)
        layout.addWidget(self.path)
        layout.addWidget(split, 1)
        self.tree.currentItemChanged.connect(self._tree_selected)
        self.grid.currentItemChanged.connect(self._grid_selected)

    def rebuild(self, matches, mode):
        self._matches = matches
        self._filter_mode = mode
        with QSignalBlocker(self.tree):
            self.tree.rebuild(self.snapshot, self._accepts, matches, hide_empty=bool(mode))
            previous = self.selected
            if previous not in self.tree.items:
                previous = self._folder if self._folder in self.tree.items else self.root
            self._select(previous if previous in self.tree.items else None)

    def _accepts(self, path):
        if not is_image(path):
            return False
        return self._filter_mode == 0 or (path in self._matches) == (self._filter_mode == 1)

    def _tree_selected(self, item, _previous):
        if item is not None:
            path = item.data(0, Qt.UserRole)
            folder = path if path in self.snapshot.folders else path.parent
            self._select(path, rebuild_grid=folder != self._folder)
            self.path_selected.emit(self.selected)

    def _grid_selected(self, item, _previous):
        if item is not None:
            self._select(item.data(Qt.UserRole), rebuild_grid=False)
            self.path_selected.emit(self.selected)

    def _select(self, path, *, rebuild_grid=True):
        self.selected = path
        folders = self.snapshot.folders if self.snapshot else {}
        self._folder = path if path is None or path in folders else path.parent
        with QSignalBlocker(self.tree), QSignalBlocker(self.grid):
            self.tree.select_path(path)
            if rebuild_grid:
                entry = folders.get(self._folder)
                files = entry.files if entry else ()
                self.grid.set_tiles(
                    Tile(file, f"✓ {file.name}" if file in self._matches else file.name,
                         file, matched=file in self._matches)
                    for file in files if self._accepts(file)
                )
            self.grid.select_path(path)


class CompareTab(QWidget):
    comparison_ready = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._generation = 0
        self._result = None
        self._active_side = None
        self.panes = {side: FolderPane(side) for side in ("A", "B")}
        self.compare = QPushButton("So sánh")
        self.compare.setEnabled(False)
        self.filter = QComboBox()
        self.filter.addItems(["Tất cả", "Khớp tên", "Chỉ có một bên"])
        self.filter.setEnabled(False)
        self.rate_a = QLabel("—")
        self.rate_b = QLabel("—")
        self.details = read_only_text("Chọn một ảnh để xem đường dẫn và kết quả khớp.")
        self.log = read_only_text("Chọn hai thư mục rồi bấm So sánh.", max_blocks=350)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.compare)
        toolbar.addSpacing(10)
        toolbar.addWidget(QLabel("Hiển thị"))
        toolbar.addWidget(self.filter)
        toolbar.addStretch()

        results = QGroupBox("Kết quả so sánh")
        center = QVBoxLayout(results)
        for name, value in (("A có trong B", self.rate_a), ("B có trong A", self.rate_b)):
            row = QHBoxLayout()
            row.addWidget(QLabel(name))
            row.addStretch()
            font = value.font()
            font.setBold(True)
            value.setFont(font)
            row.addWidget(value)
            center.addLayout(row)
        center.addWidget(QLabel("Thông tin ảnh"))
        center.addWidget(self.details, 2)
        center.addWidget(QLabel("Nhật ký"))
        center.addWidget(self.log, 1)

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        for widget in (self.panes["A"], results, self.panes["B"]):
            split.addWidget(widget)
        split.setSizes([375, 330, 375])
        layout = QVBoxLayout(self)
        layout.addLayout(toolbar)
        layout.addWidget(split, 1)

        self.compare.clicked.connect(self.start_compare)
        self.filter.currentIndexChanged.connect(self._refresh_panes)
        for side, pane in self.panes.items():
            pane.pick.clicked.connect(lambda _checked, key=side: self._pick_root(key))
            pane.path_selected.connect(lambda path, key=side: self._show_file(key, path))
            pane.grid.image_error.connect(self.log.appendPlainText)

    def _pick_root(self, side):
        root = pick_folder(self, self.panes[side].root)
        if root is not None:
            self.set_root(side, root)

    def set_root(self, side: str, root: Path) -> None:
        root = Path(os.path.abspath(root))
        pane = self.panes[side]
        self._generation += 1
        pane.generation += 1
        generation = pane.generation
        pane.root, pane.snapshot, pane.selected = root, None, None
        pane.path.set_value(root)
        self._result = None
        self.rate_a.setText("—")
        self.rate_b.setText("—")
        with QSignalBlocker(self.filter):
            self.filter.setCurrentIndex(0)
        self.filter.setEnabled(False)
        self._refresh_panes()
        self.compare.setEnabled(all(item.root is not None for item in self.panes.values()))
        self.log.appendPlainText(f"{side} · Đang quét {root}")

        def accept(snapshot):
            if generation == pane.generation:
                pane.snapshot = snapshot
                pane.rebuild(self._matches(side), self.filter.currentIndex())
                self._log_scan(side, snapshot)

        def fail(message):
            if generation == pane.generation:
                self.log.appendPlainText(f"{side} · {message}")

        run_background(self, lambda: scan_tree(root), accept, fail)

    def start_compare(self) -> None:
        left, right = (self.panes[side].root for side in ("A", "B"))
        if left is None or right is None:
            return
        self._generation += 1
        generation = self._generation
        self.compare.setEnabled(False)
        self.log.appendPlainText("Đang so sánh hai cây thư mục…")

        def work():
            left_tree, right_tree = scan_tree(left), scan_tree(right)
            return left_tree, right_tree, compare_trees(left_tree, right_tree)

        def accept(data):
            if generation != self._generation:
                return
            left_tree, right_tree, result = data
            for side, snapshot in (("A", left_tree), ("B", right_tree)):
                pane = self.panes[side]
                pane.generation += 1
                pane.snapshot = snapshot
                self._log_scan(side, snapshot)
            self._result = result
            self.rate_a.setText(format_rate(len(result.left_matches), result.left_total))
            self.rate_b.setText(format_rate(len(result.right_matches), result.right_total))
            self.filter.setEnabled(True)
            self.compare.setEnabled(True)
            self._refresh_panes()
            self.log.appendPlainText(f"Tìm thấy {result.common_names} tên ảnh chung.")
            if left_tree.errors or right_tree.errors:
                self.log.appendPlainText("Kết quả chưa đầy đủ vì có thư mục không đọc được.")
            self.comparison_ready.emit(result)

        def fail(message):
            if generation == self._generation:
                self.log.appendPlainText(message)
                self.compare.setEnabled(True)

        run_background(self, work, accept, fail, priority=1)

    def _log_scan(self, side, snapshot):
        entry = snapshot.folders.get(snapshot.root)
        if entry is not None:
            summary = f"{entry.image_count} ảnh" if entry.image_count else "không có ảnh"
            self.log.appendPlainText(f"{side} · {summary}")
        for error in snapshot.errors:
            self.log.appendPlainText(error)

    def _matches(self, side):
        if self._result is None:
            return {}
        return self._result.left_matches if side == "A" else self._result.right_matches

    def _refresh_panes(self, *_):
        for side, pane in self.panes.items():
            pane.rebuild(self._matches(side), self.filter.currentIndex())
        if self._active_side is not None:
            self._show_file(self._active_side, self.panes[self._active_side].selected)

    def _show_file(self, side, path):
        self._active_side = side
        pane = self.panes[side]
        if path is None or pane.snapshot is None or path in pane.snapshot.folders:
            self.details.clear()
            return
        opposite = "B" if side == "A" else "A"
        other_root = self.panes[opposite].root
        matches = self._matches(side).get(path, ())
        lines = [path.name, f"{side} · {path.relative_to(pane.root)}"]
        if matches:
            lines.append("✓ Khớp tên")
            lines.extend(f"{opposite} · {match.relative_to(other_root)}" for match in matches)
        else:
            lines.append("Chỉ có ở một bên" if self._result else "Chưa so sánh")
        self.details.setPlainText("\n".join(lines))


class ImagePreview(QLabel):
    def __init__(self):
        super().__init__()
        self._image = QPixmap()
        self.setAlignment(Qt.AlignCenter)
        self.setTextFormat(Qt.PlainText)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

    def show_message(self, message):
        self._image = QPixmap()
        self.setText(message)

    def show_image(self, image):
        self._image = QPixmap.fromImage(image)
        self._fit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def _fit(self):
        if not self._image.isNull() and not self.contentsRect().size().isEmpty():
            self.setPixmap(self._image.scaled(
                self.contentsRect().size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))


class DestinationDialog(QDialog):
    def __init__(self, parent, title, source, snapshot):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(510, 390)
        self.tree = FolderTree()
        self.tree.rebuild(snapshot, lambda _path: False, {})
        self.tree.items[source.parent].setFlags(
            self.tree.items[source.parent].flags() & ~Qt.ItemIsSelectable
        )
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        choose = buttons.button(QDialogButtonBox.Ok)
        choose.setText("Chọn thư mục đích")
        choose.setEnabled(False)
        buttons.button(QDialogButtonBox.Cancel).setText("Hủy")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.tree.currentItemChanged.connect(
            lambda item, _previous: choose.setEnabled(item is not None and self.destination != source.parent)
        )
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("File nguồn"))
        layout.addWidget(PathLabel(source))
        layout.addWidget(QLabel("Chọn thư mục đích trong cây gốc"))
        layout.addWidget(self.tree)
        layout.addWidget(buttons)

    @property
    def destination(self):
        item = self.tree.currentItem()
        return item.data(0, Qt.UserRole) if item is not None else None


class ManageTab(QWidget):
    snapshot_ready = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.root = None
        self.snapshot = None
        self.current_folder = None
        self.current_file = None
        self._generation = 0
        self._preview_generation = 0
        self._busy = False

        self.pick = QPushButton("Chọn thư mục gốc…")
        self.root_path = PathLabel("Chưa chọn thư mục gốc")
        self.tree = FolderTree(counts=True)
        self.path = PathLabel("Chọn thư mục để xem nội dung")
        self.up_button = QPushButton("↑ Thư mục cha")
        self.new_button = QPushButton("+ Tạo thư mục số")
        self.copy_button = QPushButton("Sao chép…")
        self.move_button = QPushButton("Di chuyển…")
        self.delete_button = QPushButton("Xóa…")
        self.log = read_only_text("Kết quả thao tác sẽ xuất hiện tại đây.", max_blocks=350)
        self.log.setMinimumHeight(60)
        self.log.setMaximumHeight(118)
        self.grid = PreviewGrid()
        self.preview = ImagePreview()
        self.file_info = read_only_text("Thông tin file")
        self.content = QStackedWidget()
        for page in (self.grid, self.preview, self.file_info):
            self.content.addWidget(page)
        self._images = ImageLoader(self)
        self._images.ready.connect(self._show_preview)
        self._images.failed.connect(self._preview_error)

        left = QGroupBox("Cây thư mục")
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.pick)
        left_layout.addWidget(self.root_path)
        left_layout.addWidget(self.tree, 1)

        right = QGroupBox("Nội dung")
        right_layout = QVBoxLayout(right)
        location = QHBoxLayout()
        location.addWidget(self.path, 1)
        location.addWidget(self.up_button)
        right_layout.addLayout(location)
        toolbar = QHBoxLayout()
        for button in (self.new_button, self.copy_button, self.move_button, self.delete_button):
            toolbar.addWidget(button)
        toolbar.addStretch()
        right_layout.addLayout(toolbar)
        right_layout.addWidget(self.content, 1)
        right_layout.addWidget(QLabel("Nhật ký"))
        right_layout.addWidget(self.log)

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([435, 745])
        layout = QVBoxLayout(self)
        layout.addWidget(split)

        self.pick.clicked.connect(self._pick_root)
        self.up_button.clicked.connect(self._go_up)
        self.new_button.clicked.connect(self._create_folder)
        self.copy_button.clicked.connect(lambda: self._transfer("Sao chép", copy_file))
        self.move_button.clicked.connect(lambda: self._transfer("Di chuyển", move_file))
        self.delete_button.clicked.connect(self._confirm_delete)
        self.tree.currentItemChanged.connect(self._tree_selected)
        self.grid.currentItemChanged.connect(self._grid_selected)
        self.grid.image_error.connect(self.log.appendPlainText)
        self._update_buttons()

    def _pick_root(self):
        root = pick_folder(self, self.root)
        if root is not None:
            self.set_root(root)

    def set_root(self, root: Path) -> None:
        if self._busy:
            return
        self.root = root = Path(os.path.abspath(root))
        self._generation += 1
        generation = self._generation
        self.snapshot = self.current_folder = self.current_file = None
        self._preview_generation += 1
        self.root_path.set_value(root)
        self.path.set_value("Đang quét thư mục…")
        with QSignalBlocker(self.tree), QSignalBlocker(self.grid):
            self.tree.rebuild(None, lambda _path: True, {})
            self.grid.set_tiles(())
        self.content.setCurrentWidget(self.grid)
        self._update_buttons()
        self.log.appendPlainText(f"Đang quét {root}")

        def accept(snapshot):
            if generation == self._generation:
                self._apply_snapshot(snapshot, root)

        def fail(message):
            if generation == self._generation:
                self.path.set_value("Không đọc được thư mục.")
                self.log.appendPlainText(message)

        run_background(self, lambda: scan_tree(root), accept, fail)

    def _apply_snapshot(self, snapshot, preferred):
        self.snapshot = snapshot
        with QSignalBlocker(self.tree):
            self.tree.rebuild(snapshot, lambda _path: True, {})
        for error in snapshot.errors:
            self.log.appendPlainText(error)
        if snapshot.root in snapshot.folders:
            if preferred not in self.tree.items:
                preferred = next(
                    (parent for parent in preferred.parents if parent in snapshot.folders), snapshot.root
                )
            self.select_path(preferred)
        else:
            self.current_folder = self.current_file = None
            self._preview_generation += 1
            self.path.set_value("Không đọc được thư mục.")
            with QSignalBlocker(self.grid):
                self.grid.set_tiles(())
            self.content.setCurrentWidget(self.grid)
        self._update_buttons()
        self.snapshot_ready.emit(snapshot)

    def _tree_selected(self, item, _previous):
        if item is not None:
            self.select_path(item.data(0, Qt.UserRole))

    def _grid_selected(self, item, _previous):
        if item is not None:
            self.select_path(item.data(Qt.UserRole))

    def select_path(self, path: Path) -> None:
        if self.snapshot is None or path not in self.tree.items:
            return
        self._preview_generation += 1
        with QSignalBlocker(self.tree):
            self.tree.select_path(path)
        folders = self.snapshot.folders
        self.path.set_value(path)
        if path in folders:
            self.current_folder, self.current_file = path, None
            entry = folders[path]
            tiles = [
                Tile(child, f"{child.name}\n{folders[child].image_count} ảnh",
                     folders[child].cover, folder=True)
                for child in entry.children
            ]
            tiles.extend(Tile(file, file.name, file if is_image(file) else None) for file in entry.files)
            with QSignalBlocker(self.grid):
                self.grid.set_tiles(tiles)
            self.content.setCurrentWidget(self.grid)
        else:
            self.current_folder, self.current_file = path.parent, path
            if is_image(path):
                self.preview.show_message("Đang đọc ảnh…")
                self.content.setCurrentWidget(self.preview)
                self._images.request(path, QSize(1600, 1200), self._preview_generation, cache=False)
            else:
                self._show_file_info(path)
        self._update_buttons()

    def _show_file_info(self, path):
        generation = self._preview_generation
        self.file_info.setPlainText(path.name)
        self.content.setCurrentWidget(self.file_info)

        def accept(size):
            if generation == self._preview_generation:
                mime = QMimeDatabase().mimeTypeForFile(str(path), QMimeDatabase.MatchExtension)
                self.file_info.setPlainText(f"{path.name}\nLoại: {mime.name()}\nKích thước: {size:,} byte")

        def fail(message):
            if generation == self._preview_generation:
                self.file_info.setPlainText(f"{path.name}\nKhông đọc được thông tin file.")
                self.log.appendPlainText(message)

        run_background(self, lambda: path.stat().st_size, accept, fail)

    def _show_preview(self, generation, _path, image):
        if generation == self._preview_generation:
            self.preview.show_image(image)

    def _preview_error(self, generation, _path, message):
        if generation == self._preview_generation:
            self.preview.show_message("Không đọc được ảnh.")
            self.log.appendPlainText(message)

    def _go_up(self):
        if self.current_file is not None:
            self.select_path(self.current_folder)
        elif self.current_folder is not None and self.current_folder != self.root:
            self.select_path(self.current_folder.parent)

    def _update_buttons(self):
        self.pick.setEnabled(not self._busy)
        self.new_button.setEnabled(not self._busy and self.current_folder is not None)
        self.up_button.setEnabled(
            self.current_file is not None or self.current_folder not in (None, self.root)
        )
        for button in (self.copy_button, self.move_button, self.delete_button):
            button.setEnabled(not self._busy and self.current_file is not None)

    def _create_folder(self):
        root, parent = self.root, self.current_folder
        if parent is not None:
            self._mutate("Tạo thư mục số", lambda: create_numbered_folder(root, parent), parent, select_result=True)

    def _transfer(self, title, operation):
        source, root = self.current_file, self.root
        if source is None:
            return
        dialog = DestinationDialog(self, title, source, self.snapshot)
        if dialog.exec_() != QDialog.Accepted or dialog.destination is None:
            return
        destination = dialog.destination
        preferred = source if operation is copy_file else source.parent
        self._mutate(title, lambda: operation(root, source, destination), preferred)

    def _confirm_delete(self):
        source, root = self.current_file, self.root
        if source is None:
            return
        dialog = QMessageBox(
            QMessageBox.Question, "Xóa file", f"Chuyển file này vào Thùng rác?\n\n{source}",
            QMessageBox.Yes | QMessageBox.Cancel, self,
        )
        dialog.setTextFormat(Qt.PlainText)
        dialog.button(QMessageBox.Yes).setText("Đưa vào Thùng rác")
        dialog.button(QMessageBox.Cancel).setText("Hủy")
        dialog.setDefaultButton(QMessageBox.Cancel)
        if dialog.exec_() == QMessageBox.Yes:
            self._mutate("Đưa vào Thùng rác", lambda: trash_file(root, source), source.parent, target=source)

    def _mutate(self, title, action, preferred, *, select_result=False, target=None):
        if self._busy:
            return
        root = self.root
        self._busy = True
        self._update_buttons()
        self.log.appendPlainText(f"Đang thực hiện: {title}…")

        def work():
            selection = preferred
            try:
                result = action()
                message = f"✓ {title} · {result or target}"
                if select_result:
                    selection = result
            except OSError as error:
                message = f"{title} thất bại · {error}"
            return scan_tree(root), selection, message

        def accept(data):
            snapshot, selection, message = data
            self._busy = False
            self.log.appendPlainText(message)
            self.grid.clear_cache()
            self._apply_snapshot(snapshot, selection)

        def fail(message):
            self._busy = False
            self._update_buttons()
            self.log.appendPlainText(f"{title} thất bại · {message}")

        run_background(self, work, accept, fail, priority=1)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Folder Studio")
        self.resize(1180, 740)
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.tab_compare = CompareTab()
        self.tab_manage = ManageTab()
        self.tabs.addTab(self.tab_compare, "So sánh thư mục")
        self.tabs.addTab(self.tab_manage, "Quản lý thư mục")


def main() -> int:
    app = QApplication(sys.argv)
    stylesheet = Path(__file__).with_name("MacOS.qss")
    if stylesheet.is_file():
        app.setStyleSheet(stylesheet.read_text(encoding="utf-8"))
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
