import os
import sys
import shutil
from pathlib import Path

from PyQt5.QtCore import (
    Qt, QSize, QDir, QModelIndex, QRect, QEvent, pyqtSignal, QTime
)
from PyQt5.QtGui import (
    QIcon, QStandardItemModel, QStandardItem, QPainter, QPixmap, QFontMetrics, QPalette, QFont, QFontDatabase
)
from PyQt5.QtGui import QKeySequence, QFontInfo
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog, QListView, QListWidget, QListWidgetItem,
    QTreeWidget, QTreeWidgetItem, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QTextEdit,
    QSplitter, QLineEdit, QStyle, QMessageBox, QTabWidget, QToolButton, QSizePolicy,
    QStyleOptionViewItem, QStyledItemDelegate, QComboBox, QSpinBox, QCheckBox, QGroupBox,
    QFormLayout, QTimeEdit,
)

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif'}

# ------------------------------ Helpers ------------------------------

def is_image(p: Path) -> bool:
    return p.suffix.lower() in IMAGE_EXTS


def human_sorted(paths):
    try:
        from natsort import natsorted
        return natsorted(paths)
    except Exception:
        return sorted(paths)


# ------------------------------ Deletion Manager ------------------------------
class DeletionManager:
    """Session-only deletions. Apply on close."""

    def __init__(self):
        self._pending = []  # list[Path]

    def mark_deleted(self, p: Path):
        if p.exists() and p not in self._pending:
            self._pending.append(p)

    def undo_delete(self, p: Path):
        if p in self._pending:
            self._pending.remove(p)

    def is_deleted(self, p: Path) -> bool:
        return p in self._pending

    def apply(self, parent: QWidget):
        errors = []
        for p in list(self._pending):
            try:
                if p.exists():
                    p.unlink()
                self._pending.remove(p)
            except Exception as e:
                errors.append(f"{p}: {e}")
        if errors:
            QMessageBox.warning(parent, "Delete errors", "\n".join(errors))


# ------------------------------ Delegates ------------------------------
class ThumbDelegate(QStyledItemDelegate):
    """Draws icon + ElideMiddle filename beneath, highlights pending items."""

    def __init__(self, get_pending_names_fn=None, thumb_w=200, thumb_h=200, parent=None):
        super().__init__(parent)
        self.thumb = QSize(thumb_w, thumb_h)
        self.get_pending = get_pending_names_fn or (lambda: set())

    def sizeHint(self, option, index):
        fm = option.fontMetrics
        text_h = fm.height()
        return QSize(self.thumb.width() + 16, self.thumb.height() + text_h + 20)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        rect = option.rect
        icon = index.data(Qt.DecorationRole)
        name = index.data(Qt.DisplayRole) or ""

        # background if pending
        pending = self.get_pending()
        if name in pending:
            painter.fillRect(rect, option.palette.color(QPalette.Highlight).lighter(170))

        # icon
        pix = icon.pixmap(self.thumb) if isinstance(icon, QIcon) else QPixmap()
        icon_x = rect.x() + (rect.width() - self.thumb.width()) // 2
        icon_y = rect.y() + 6
        painter.drawPixmap(QRect(icon_x, icon_y, self.thumb.width(), self.thumb.height()), pix)

        # elided text (Middle) sized to icon width
        fm = QFontMetrics(option.font)
        elided = fm.elidedText(name, Qt.ElideMiddle, self.thumb.width())
        text_rect = QRect(rect.x() + (rect.width() - self.thumb.width()) // 2,
                          icon_y + self.thumb.height() + 4,
                          self.thumb.width(), fm.height() + 2)
        painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, elided)
        painter.restore()


# ------------------------------ Custom Canvas for Detail Preview ------------------------------
class ImageCanvas(QWidget):
    """Canvas draws image centered, keep aspect, fit to widget. Arrow buttons follow size."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pix = QPixmap()
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.btn_left = QToolButton(self)
        self.btn_left.setIcon(self.style().standardIcon(QStyle.SP_ArrowLeft))
        self.btn_left.setStyleSheet(
            "QToolButton{background: rgba(0,0,0,40%); border-radius: 18px;}\n"
            "QToolButton:hover{background: rgba(0,0,0,55%);}"
        )
        self.btn_left.setIconSize(QSize(20, 20))
        self.btn_left.setFixedSize(36, 36)

        self.btn_right = QToolButton(self)
        self.btn_right.setIcon(self.style().standardIcon(QStyle.SP_ArrowRight))
        self.btn_right.setStyleSheet(
            "QToolButton{background: rgba(0,0,0,40%); border-radius: 18px;}\n"
            "QToolButton:hover{background: rgba(0,0,0,55%);}"
        )
        self.btn_right.setIconSize(QSize(20, 20))
        self.btn_right.setFixedSize(36, 36)

    def set_image(self, path: Path):
        self._pix = QPixmap(str(path)) if path and path.exists() else QPixmap()
        self.update()

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().brush(QPalette.Base))
        if self._pix.isNull():
            painter.setPen(self.palette().color(QPalette.Text))
            painter.drawText(self.rect(), Qt.AlignCenter, "No image")
            return
        scaled = self._pix.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        margin = 12
        y = margin
        self.btn_left.move(margin, y)
        self.btn_right.move(self.width() - self.btn_right.width() - margin, y)


# ------------------------------ Detail Image Browser ------------------------------
class ImageBrowserWidget(QWidget):
    """Detail view: big canvas + horizontal strip (20x20), click/arrow navigation, soft delete."""

    selectionChanged = pyqtSignal(Path)

    def __init__(self, deletion_mgr: DeletionManager, parent=None):
        super().__init__(parent)
        self.delmgr = deletion_mgr
        self._images = []  # list[Path]
        self._idx = -1

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.canvas = ImageCanvas()
        layout.addWidget(self.canvas, 1)

        # controls
        btn_bar = QHBoxLayout()
        self.btn_delete = QPushButton("Delete")
        self.btn_undo = QPushButton("Undo delete")
        self.btn_delete.clicked.connect(self.delete_current)
        self.btn_undo.clicked.connect(self.undo_current)
        btn_bar.addStretch(1)
        btn_bar.addWidget(self.btn_delete)
        btn_bar.addWidget(self.btn_undo)
        layout.addLayout(btn_bar)

        # horizontal strip
        self.strip = QListWidget()
        self.strip.setViewMode(QListView.IconMode)
        self.strip.setResizeMode(QListView.Adjust)
        self.strip.setMovement(QListView.Static)
        self.strip.setIconSize(QSize(50, 50))
        self.strip.setSpacing(4)
        self.strip.setUniformItemSizes(True)
        self.strip.setWrapping(False)  # single row
        self.strip.setFlow(QListView.LeftToRight)
        self.strip.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.strip.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.strip.setMaximumHeight(86)
        self.strip.itemClicked.connect(self._on_strip_clicked)
        layout.addWidget(self.strip, 0)

        self.setFocusPolicy(Qt.StrongFocus)
        self.canvas.btn_left.clicked.connect(self.prev_image)
        self.canvas.btn_right.clicked.connect(self.next_image)

    # --- public API ---
    def set_images(self, paths):
        self._images = [Path(p) for p in paths if is_image(Path(p)) and not self.delmgr.is_deleted(Path(p))]
        self.strip.clear()
        fm = self.fontMetrics()
        for p in self._images:
            it = QListWidgetItem()
            it.setIcon(QIcon(str(p)))
            elided = fm.elidedText(p.name, Qt.ElideMiddle, 160)
            it.setText(elided)
            it.setToolTip(p.name)
            self.strip.addItem(it)
        self._idx = 0 if self._images else -1
        self._refresh_preview()

    def current(self) -> Path:
        if 0 <= self._idx < len(self._images):
            return self._images[self._idx]
        return None

    # --- internals ---
    def _refresh_preview(self):
        p = self.current()
        if not p:
            self.canvas.set_image(Path())
            self.selectionChanged.emit(Path())
            return
        self.canvas.set_image(p)
        if 0 <= self._idx < self.strip.count():
            self.strip.setCurrentRow(self._idx)
        self.selectionChanged.emit(p)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Right, Qt.Key_Down, Qt.Key_D):
            self.next_image(); e.accept(); return
        if e.key() in (Qt.Key_Left, Qt.Key_Up, Qt.Key_A):
            self.prev_image(); e.accept(); return
        if e.key() == Qt.Key_Delete:
            self.delete_current(); e.accept(); return
        if e.matches(QKeySequence.Undo):
            self.undo_current(); e.accept(); return
        super().keyPressEvent(e)

    def next_image(self):
        if not self._images:
            return
        self._idx = (self._idx + 1) % len(self._images)
        self._refresh_preview()

    def prev_image(self):
        if not self._images:
            return
        self._idx = (self._idx - 1) % len(self._images)
        self._refresh_preview()

    def _on_strip_clicked(self, item: QListWidgetItem):
        row = self.strip.row(item)
        if 0 <= row < len(self._images):
            self._idx = row
            self._refresh_preview()

    def delete_current(self):
        p = self.current()
        if not p:
            return
        self.delmgr.mark_deleted(p)
        del self._images[self._idx]
        self.strip.takeItem(self._idx)
        if self._idx >= len(self._images):
            self._idx = len(self._images) - 1
        self._refresh_preview()

    def undo_current(self):
        p = self.current()
        if p and self.delmgr.is_deleted(p):
            self.delmgr.undo_delete(p)
            self.set_images(self._images)


# ------------------------------ Main Window ------------------------------
class ImageManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Folder Manager v3")
        self.resize(1280, 820)

        self.base_path: Path | None = None
        self.source_paths: list[Path] = []    # multiple sources
        self.destination_path: Path | None = None  # single destination

        self.deletion_mgr = DeletionManager()

        # central splitter
        self.splitter = QSplitter()
        self.setCentralWidget(self.splitter)

        # Left panel
        left = QWidget(); left_layout = QVBoxLayout(left)
        self.btn_pick_base = QPushButton("Chọn Folder Chính…")
        self.btn_pick_base.clicked.connect(self.pick_base_folder)
        left_layout.addWidget(self.btn_pick_base)

        self.tree = QTreeWidget(); self.tree.setHeaderLabels(["Thư mục", "#Ảnh"])
        self.tree.itemSelectionChanged.connect(self._on_tree_select)
        left_layout.addWidget(self.tree, 1)
        self.splitter.addWidget(left)

        # Right panel: top = (tabs | move), bottom = log with margin
        right_vsplit = QSplitter(Qt.Vertical)

        top_hsplit = QSplitter(Qt.Horizontal)
        # tabs
        self.tabs = QTabWidget()
        top_hsplit.addWidget(self.tabs)

        # Tab Grid
        grid_tab = QWidget(); grid_layout = QVBoxLayout(grid_tab)
        tools_row = QHBoxLayout()
        self.chk_click_rename = QCheckBox("Đổi tên file bằng click")
        self.spin_prefix = QSpinBox(); self.spin_prefix.setRange(0, 1_000_000); self.spin_prefix.setValue(1)
        tools_row.addWidget(self.chk_click_rename)
        tools_row.addWidget(QLabel("Bắt đầu từ:"))
        tools_row.addWidget(self.spin_prefix)
        tools_row.addStretch(1)
        grid_layout.addLayout(tools_row)

        self.thumb_model = QStandardItemModel()
        self.thumbnail_list = QListView()
        self.thumbnail_list.setViewMode(QListView.IconMode)
        self.thumbnail_list.setIconSize(QSize(200, 200))
        self.thumbnail_list.setResizeMode(QListView.Adjust)
        self.thumbnail_list.setMovement(QListView.Static)
        self.thumbnail_list.setSpacing(8)
        self.thumbnail_list.setModel(self.thumb_model)
        self.thumbnail_list.setSelectionMode(QListView.ExtendedSelection)
        self.thumbnail_list.setItemDelegate(ThumbDelegate(lambda: self._pending_rename_names, 200, 200, self))
        self.thumbnail_list.installEventFilter(self)  # for Delete key on grid
        grid_layout.addWidget(self.thumbnail_list, 1)
        self.tabs.addTab(grid_tab, "Grid")

        # Tab Detail
        self.detail_tab = ImageBrowserWidget(self.deletion_mgr)
        self.tabs.addTab(self.detail_tab, "Detail")

        # Move/Rename panel (v1 structure)
        move_panel = QWidget(); move_layout = QVBoxLayout(move_panel); move_layout.setAlignment(Qt.AlignTop)
        # Source
        source_layout = QHBoxLayout()
        self.lbl_source = QLabel("Nguồn:")
        self.txt_source = QLineEdit(); self.txt_source.setReadOnly(True)
        self.btn_set_source = QPushButton(">>"); self.btn_set_source.setToolTip("Đặt thư mục đang chọn làm NGUỒN")
        self.btn_set_source.clicked.connect(self.set_source)
        source_layout.addWidget(self.lbl_source); source_layout.addWidget(self.txt_source); source_layout.addWidget(self.btn_set_source)
        # Destination
        dest_layout = QHBoxLayout()
        self.lbl_dest = QLabel("Đích:  ")
        self.txt_dest = QLineEdit(); self.txt_dest.setReadOnly(True)
        self.btn_set_dest = QPushButton("<<"); self.btn_set_dest.setToolTip("Đặt thư mục đang chọn làm ĐÍCH")
        self.btn_set_dest.clicked.connect(self.set_destination)
        dest_layout.addWidget(self.lbl_dest); dest_layout.addWidget(self.txt_dest); dest_layout.addWidget(self.btn_set_dest)
        # Move button
        self.btn_move = QPushButton("Chuyển Files"); self.btn_move.clicked.connect(self.move_files)
        # Collision policy
        pol_row = QHBoxLayout(); pol_row.addWidget(QLabel("Collision policy:"))
        self.combo_policy = QComboBox(); self.combo_policy.addItems(["Rename", "Skip", "Overwrite"])  # default Rename
        pol_row.addWidget(self.combo_policy); pol_row.addStretch(1)
        # Rename group (placeholder hook)
        rename_group = QGroupBox("Rename Folder"); rename_layout = QFormLayout(); rename_group.setLayout(rename_layout)
        time_range_layout = QHBoxLayout()
        self.work_start_hour_spin = QSpinBox(); self.work_start_hour_spin.setRange(0, 23); self.work_start_hour_spin.setValue(6)
        self.work_end_hour_spin = QSpinBox(); self.work_end_hour_spin.setRange(1, 24); self.work_end_hour_spin.setValue(20)
        time_range_layout.addWidget(self.work_start_hour_spin); time_range_layout.addWidget(QLabel("đến")); time_range_layout.addWidget(self.work_end_hour_spin)
        rename_layout.addRow("Chọn khoảng thời gian (giờ):", time_range_layout)
        self.combo_step = QComboBox(); self.combo_step.addItems([str(i) for i in range(1, 7)])
        rename_layout.addRow("Chọn bước nhảy (giờ):", self.combo_step)
        self.time_sequence_start = QTimeEdit(QTime(6, 0)); self.time_sequence_start.setDisplayFormat("HH")
        rename_layout.addRow("Chọn giờ bắt đầu:", self.time_sequence_start)
        self.chk_patreon = QCheckBox("Xử lý file prompt cho Patreon"); rename_layout.addRow(self.chk_patreon)
        self.chk_desc_sort = QCheckBox("Sắp xếp theo chiều giảm dần (số ảnh)"); rename_layout.addRow(self.chk_desc_sort)
        self.btn_rename = QPushButton("Xử lí"); self.btn_rename.clicked.connect(self.process_rename)
        rename_layout.addWidget(self.btn_rename)
        # assemble
        move_layout.addLayout(source_layout)
        move_layout.addLayout(dest_layout)
        move_layout.addWidget(self.btn_move)
        move_layout.addLayout(pol_row)
        move_layout.addWidget(rename_group)

        top_hsplit.addWidget(move_panel)
        top_hsplit.setSizes([900, 400])

        # log with margin (padding)
        self.log = QTextEdit(); self.log.setReadOnly(True)
        self.log.setStyleSheet("QTextEdit{padding:10px; margin: 10px}")

        right_vsplit.addWidget(top_hsplit)
        right_vsplit.addWidget(self.log)
        right_vsplit.setSizes([640, 180])

        self.splitter.addWidget(right_vsplit)
        self.splitter.setSizes([360, 920])

        # internal state for grid rename highlighting
        self._pending_rename_names = set()

        # font setup for Vietnamese
        self._setup_vietnamese_font()

    # -------------------- Font for Vietnamese --------------------
    def _setup_vietnamese_font(self):
        # Try load bundled fonts if available
        tried = []
        for name in ["fonts/NotoSans-Regular.ttf", "fonts/DejaVuSans.ttf"]:
            try:
                if Path(name).exists():
                    QFontDatabase.addApplicationFont(name)
                    tried.append(name)
            except Exception:
                pass
        # Set a safe family stack
        fams = ["Segoe UI", "Noto Sans", "DejaVu Sans", "Arial Unicode MS", "Roboto", "Arial"]
        for fam in fams:
            f = QFont(fam, 10)
            if QFontInfo(f).family() != "":
                QApplication.instance().setFont(f)
                break

    # -------------------- Base folder & tree --------------------
    def pick_base_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn Folder Chính", QDir.homePath())
        if not d:
            return
        self.base_path = Path(d)
        self.populate_tree()

    def populate_tree(self):
        self.tree.clear()
        if not self.base_path:
            return
        for name in sorted(os.listdir(self.base_path)):
            p = self.base_path / name
            if p.is_dir():
                count = sum(1 for f in p.iterdir() if f.is_file() and is_image(f) and not self.deletion_mgr.is_deleted(f))
                item = QTreeWidgetItem([name, str(count)])
                item.setData(0, Qt.UserRole, str(p))
                self.tree.addTopLevelItem(item)
        self.tree.resizeColumnToContents(0)

    def _on_tree_select(self):
        items = self.tree.selectedItems()
        if not items:
            return
        folder = Path(items[0].data(0, Qt.UserRole))
        self.load_thumbnails(folder)

    # -------------------- Thumbnails & Detail --------------------
    def load_thumbnails(self, folder: Path):
        self.current_folder = folder
        self.thumb_model.clear()
        if not folder.exists():
            return
        imgs = [p for p in folder.iterdir() if p.is_file() and is_image(p) and not self.deletion_mgr.is_deleted(p)]
        imgs = human_sorted(imgs)
        for p in imgs:
            it = QStandardItem(QIcon(str(p)), p.name)
            it.setEditable(False)
            it.setToolTip(p.name)
            it.setData(str(p), Qt.UserRole)
            self.thumb_model.appendRow(it)
        # wire to detail
        self.detail_tab.set_images([str(p) for p in imgs])

    def eventFilter(self, obj, event):
        # Delete on Grid (multi-select)
        if obj is self.thumbnail_list and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Delete:
            indexes = self.thumbnail_list.selectedIndexes()
            # gather unique rows
            rows = sorted(set(idx.row() for idx in indexes), reverse=True)
            for r in rows:
                item = self.thumb_model.item(r)
                if not item:
                    continue
                path = Path(item.data(Qt.UserRole))
                self.deletion_mgr.mark_deleted(path)
                self.thumb_model.removeRow(r)
            # refresh detail too
            self._refresh_detail_after_grid_delete()
            return True
        return super().eventFilter(obj, event)

    def _refresh_detail_after_grid_delete(self):
        # rebuild from remaining model items
        paths = []
        for i in range(self.thumb_model.rowCount()):
            p = Path(self.thumb_model.item(i).data(Qt.UserRole))
            if not self.deletion_mgr.is_deleted(p):
                paths.append(str(p))
        self.detail_tab.set_images(paths)

    def _on_thumb_clicked(self, index: QModelIndex):
        if not self.chk_click_rename.isChecked():
            p = Path(index.data(Qt.UserRole))
            if p.exists():
                self.tabs.setCurrentWidget(self.detail_tab)
                self.detail_tab.set_images([self.thumb_model.item(i).data(Qt.UserRole) for i in range(self.thumb_model.rowCount()) if not self.deletion_mgr.is_deleted(Path(self.thumb_model.item(i).data(Qt.UserRole)))])
                try:
                    idx = [Path(self.detail_tab._images[i]) for i in range(len(self.detail_tab._images))].index(p)
                    self.detail_tab._idx = idx
                    self.detail_tab._refresh_preview()
                except ValueError:
                    pass
            return
        # click-to-rename staging toggle (optional visual)
        name = index.data(Qt.DisplayRole)
        if name not in self._pending_rename_names:
            self._pending_rename_names.add(name)
        else:
            self._pending_rename_names.remove(name)
        self.thumbnail_list.viewport().update()

    # -------------------- Source/Destination (v1 semantics + your rule) --------------------
    def set_source(self):
        folder = self._selected_folder()
        if not folder:
            return
        if self.destination_path and self.destination_path == folder:
            self.destination_path = None
            self.txt_dest.setText("")
        if folder not in self.source_paths:
            self.source_paths.append(folder)
        self._refresh_paths_ui()

    def set_destination(self):
        folder = self._selected_folder()
        if not folder:
            return
        if folder in self.source_paths:
            self.source_paths = [p for p in self.source_paths if p != folder]
        self.destination_path = folder
        self._refresh_paths_ui()

    def _selected_folder(self) -> Path | None:
        items = self.tree.selectedItems()
        if not items:
            return None
        return Path(items[0].data(0, Qt.UserRole))

    def _refresh_paths_ui(self):
        self.txt_source.setText(
            ", ".join(str(p.name) for p in self.source_paths)
        )
        self.txt_dest.setText(str(self.destination_path.name) if self.destination_path else "")

    # -------------------- Move files with collision policy --------------------
    def move_files(self):
        if (not self.source_paths) or (self.destination_path is None):
            QMessageBox.warning(self, "Thiếu thông tin", "Cần chọn ít nhất 1 nguồn và 1 đích.")
            return
        dest = self.destination_path
        if not dest.exists():
            QMessageBox.warning(self, "Lỗi", f"Đích không tồn tại: {dest}")
            return
        policy = self.combo_policy.currentText().lower()  # rename/skip/overwrite
        for src in list(self.source_paths):
            if src == dest:
                self.log.append(f"Bỏ qua vì nguồn == đích: {src}")
                continue
            if not src.exists():
                self.log.append(f"Nguồn không tồn tại: {src}")
                continue
            moved_any = False
            for f in src.iterdir():
                if not f.is_file():
                    continue
                target = dest / f.name
                try:
                    if target.exists():
                        if policy == 'overwrite':
                            os.replace(str(f), str(target)); moved_any = True
                        elif policy == 'skip':
                            self.log.append(f"Skip (đã tồn tại): {target.name}")
                            continue
                        else:  # rename
                            base, ext = target.stem, target.suffix
                            k = 1
                            new_target = dest / f"{base}_{k}{ext}"
                            while new_target.exists():
                                k += 1
                                new_target = dest / f"{base}_{k}{ext}"
                            shutil.move(str(f), str(new_target)); moved_any = True
                    else:
                        shutil.move(str(f), str(target)); moved_any = True
                except Exception as e:
                    self.log.append(f"Lỗi move {f.name}: {e}")
                    QApplication.processEvents()
            try:
                if moved_any and not any(src.iterdir()):
                    src.rmdir(); self.log.append(f"Đã xóa thư mục trống: {src.name}")
            except Exception as e:
                self.log.append(f"Không thể xóa {src.name}: {e}")
        self.populate_tree(); self._refresh_paths_ui()

    # -------------------- Rename processing (placeholder) --------------------
    def process_rename(self):
        QMessageBox.information(self, "Rename Folder", "Sẽ port logic rename theo lịch + Patreon từ bản trước.")

    # -------------------- Close: apply pending deletions --------------------
    def closeEvent(self, e):
        if self.deletion_mgr._pending:
            n = len(self.deletion_mgr._pending)
            ret = QMessageBox.question(
                self, "Xóa ảnh",
                f"Bạn có muốn xóa vĩnh viễn {n} ảnh đã đánh dấu không?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes
            )
            if ret == QMessageBox.Cancel:
                e.ignore(); return
            if ret == QMessageBox.Yes:
                self.deletion_mgr.apply(self)
        super().closeEvent(e)


# ------------------------------ main ------------------------------
if __name__ == '__main__':
    app = QApplication(sys.argv)
    try:
        with open("MacOS.qss", 'r') as f:
            app.setStyleSheet(f.read())
    except: pass
    w = ImageManager()
    w.show()
    sys.exit(app.exec_())
