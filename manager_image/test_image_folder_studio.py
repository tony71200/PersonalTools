import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QImage
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

from image_folder_studio import CompareTab, ManageTab
from image_folder_studio_core import (
    compare_trees,
    copy_file,
    create_numbered_folder,
    move_file,
    scan_tree,
    trash_file,
)
from image_folder_studio_widgets import ImageLoader, read_scaled_image


def make_file(root, name, data=b"sample"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


class FolderCoreTests(unittest.TestCase):
    def test_recursive_name_match(self):
        with TemporaryDirectory() as tmp:
            left, right = Path(tmp) / "A", Path(tmp) / "B"
            first = make_file(left, "one/Bien.JPG")
            second = make_file(left, "one/nested/bien.jpg")
            make_file(left, "bien.png")
            make_file(left, "caption.txt")
            counterpart = make_file(right, "other/bien.jpg")
            make_file(right, "rung.jpg")
            snapshot = scan_tree(left)
            result = compare_trees(snapshot, scan_tree(right))
            self.assertEqual((result.left_total, result.right_total), (3, 2))
            self.assertEqual((len(result.left_matches), len(result.right_matches)), (2, 1))
            self.assertEqual(result.common_names, 1)
            self.assertEqual(set(result.right_matches[counterpart]), {first, second})
            entry = snapshot.folders[left]
            self.assertEqual((len(entry.children), entry.descendant_count, entry.image_count), (1, 2, 3))

    def test_scan_keeps_readable_branch_and_reports_error(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            blocked = make_file(root, "blocked/image.jpg").parent
            make_file(root, "open/image.jpg")
            scandir = os.scandir

            def scan(path):
                if Path(path) == blocked:
                    raise PermissionError("access denied")
                return scandir(path)

            with patch("image_folder_studio_core.os.scandir", side_effect=scan):
                snapshot = scan_tree(root)
            self.assertEqual(snapshot.folders[root].image_count, 1)
            self.assertIn(str(blocked), snapshot.errors[0])

    def test_empty_and_linked_folders(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            root.mkdir()
            outside = make_file(Path(tmp), "outside/image.jpg").parent
            try:
                (root / "link").symlink_to(outside, target_is_directory=True)
            except OSError:
                # Windows can require Developer Mode to create symbolic links.
                pass
            snapshot = scan_tree(root)
            self.assertEqual(tuple(snapshot.folders), (root,))
            result = compare_trees(snapshot, snapshot)
            self.assertEqual((result.left_total, result.right_total, result.common_names), (0, 0, 0))

    def test_numbering_and_conflicts(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "009").mkdir()
            make_file(root, "010")
            destination = create_numbered_folder(root, root)
            self.assertEqual(destination.name, "011")
            source = make_file(root, "anh.png", b"source")
            existing = make_file(destination, source.name, b"existing")
            for operation in (copy_file, move_file):
                with self.assertRaises(FileExistsError):
                    operation(root, source, destination)
            self.assertEqual(source.read_bytes(), b"source")
            self.assertEqual(existing.read_bytes(), b"existing")

    def test_copy_and_move_stay_in_root(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            source = make_file(root, "001/ảnh.jpg")
            outside = make_file(Path(tmp), "outside/other.jpg").parent
            with self.assertRaises(OSError):
                copy_file(root, source, outside)
            destination = create_numbered_folder(root, root)
            copied = copy_file(root, source, destination)
            self.assertEqual(copied.read_bytes(), source.read_bytes())
            copied.unlink()
            moved = move_file(root, source, destination)
            self.assertFalse(source.exists())
            self.assertEqual(moved.read_bytes(), b"sample")

    def test_trash_failure_preserves_file(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_file(root, "anh.png")
            with patch("image_folder_studio_core.QFile") as file:
                file.return_value.moveToTrash.return_value = False
                file.return_value.errorString.return_value = "trash unavailable"
                with self.assertRaisesRegex(OSError, "trash unavailable"):
                    trash_file(root, source)
            self.assertTrue(source.is_file())


class QtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_thumbnail_keeps_aspect_ratio(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "wide.png"
            image = QImage(320, 160, QImage.Format_RGB32)
            image.fill(Qt.blue)
            self.assertTrue(image.save(str(path)))
            self.assertEqual(read_scaled_image(path, QSize(96, 96)).size(), QSize(96, 48))
            path.write_bytes(b"not a PNG")
            with self.assertRaises(OSError):
                read_scaled_image(path, QSize(96, 96))

    def test_loader_reuses_thumbnail_with_new_generation(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "wide.png"
            image = QImage(320, 160, QImage.Format_RGB32)
            image.fill(Qt.blue)
            self.assertTrue(image.save(str(path)))
            loader = ImageLoader()
            ready = QSignalSpy(loader.ready)
            for generation in (1, 2):
                loader.request(path, QSize(96, 96), generation)
                self.assertTrue(len(ready) == generation or ready.wait(3000))
                self.assertEqual(ready[-1][:2], [generation, path])
                self.assertEqual(ready[-1][2].size(), QSize(96, 48))

    def test_compare_tab_displays_both_directions_and_filters(self):
        with TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "A", Path(tmp) / "B"
            left = make_file(a, "001/x.jpg")
            make_file(a, "001/a.png")
            make_file(b, "other/X.JPG")
            make_file(b, "archive/x.jpg")
            tab = CompareTab()
            tab.set_root("A", a)
            tab.set_root("B", b)
            ready = QSignalSpy(tab.comparison_ready)
            tab.start_compare()
            self.assertTrue(ready.wait(3000))
            self.assertEqual(tab.rate_a.text(), "50% (1/2)")
            self.assertEqual(tab.rate_b.text(), "100% (2/2)")
            tab.panes["A"].tree.setCurrentItem(tab.panes["A"].tree.items[left])
            self.assertIn(str(Path("other/X.JPG")), tab.details.toPlainText())
            self.assertIn(str(Path("archive/x.jpg")), tab.details.toPlainText())
            self.assertEqual(tab.details.maximumBlockCount(), 0)
            self.assertTrue(tab.panes["A"].tree.items[left].text(0).startswith("✓"))
            self.assertTrue(tab.panes["A"].grid.currentItem().text().startswith("✓"))
            tab.filter.setCurrentIndex(2)
            self.assertNotIn(left, tab.panes["A"].tree.items)
            self.assertEqual(set(tab.panes["B"].tree.items), {b})

    def test_compare_ignores_result_after_root_change(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = make_file(root, "old/same.jpg").parent
            right = make_file(root, "right/same.jpg").parent
            new = make_file(root, "new/unique.png").parent
            jobs = []

            def enqueue(_owner, work, accept, _fail, **_options):
                jobs.append((work, accept))

            def deliver(index):
                work, accept = jobs[index]
                accept(work())

            tab = CompareTab()
            ready = QSignalSpy(tab.comparison_ready)
            with patch("image_folder_studio.run_background", side_effect=enqueue):
                tab.set_root("A", old)
                tab.set_root("B", right)
                tab.start_compare()
                tab.set_root("A", new)
            deliver(3)
            deliver(2)
            deliver(0)
            self.assertEqual(len(ready), 0)
            self.assertEqual(tab.rate_a.text(), "—")
            self.assertEqual(tab.panes["A"].snapshot.root, new)
            self.assertTrue(tab.compare.isEnabled())

    def test_compare_selection_locates_counterpart_in_both_directions(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            left = make_file(root, "A/source/deep/Bien.jpg")
            left_only = make_file(root, "A/source/deep/unique.png")
            right = make_file(root, "B/archive/old/bien.JPG")
            right_duplicate = make_file(root, "B/selected/bien.jpg")
            tab = CompareTab()
            tab.set_root("A", root / "A")
            tab.set_root("B", root / "B")
            ready = QSignalSpy(tab.comparison_ready)
            tab.start_compare()
            self.assertTrue(ready.wait(3000))
            pane_a, pane_b = tab.panes["A"], tab.panes["B"]

            pane_a.tree.setCurrentItem(pane_a.tree.items[left])
            self.assertEqual(pane_b.tree.currentItem().data(0, Qt.UserRole), right)
            self.assertEqual(pane_b.grid.currentItem().data(Qt.UserRole), right)
            self.assertTrue(pane_b.tree.items[right.parent].isExpanded())
            self.assertIn(str(right_duplicate.relative_to(pane_b.root)), tab.details.toPlainText())

            pane_b.tree.setCurrentItem(pane_b.tree.items[right_duplicate.parent])
            pane_a.tree.setCurrentItem(pane_a.tree.items[left_only])
            self.assertEqual(pane_b.selected, right_duplicate.parent)
            pane_b.grid.setCurrentRow(0)
            self.assertEqual(pane_a.tree.currentItem().data(0, Qt.UserRole), left)
            self.assertEqual(pane_a.grid.currentItem().data(Qt.UserRole), left)
            self.assertTrue(tab.details.toPlainText().splitlines()[1].startswith("B · "))

            pane_a.grid.itemClicked.emit(pane_a.grid.currentItem())
            self.assertEqual(pane_b.selected, right_duplicate)

            # Clicking an already-selected image should also locate it again.
            pane_b.tree.setCurrentItem(pane_b.tree.items[right_duplicate.parent])
            pane_a.tree.itemClicked.emit(pane_a.tree.items[left], 0)
            self.assertEqual(pane_b.selected, right)
            self.assertTrue(tab.details.toPlainText().splitlines()[1].startswith("A · "))

    def test_manage_tab_browses_and_creates_folder(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = make_file(root, "001/Đã chọn/rung.jpg")
            (root / "002").mkdir()
            tab = ManageTab()
            ready = QSignalSpy(tab.snapshot_ready)
            tab.set_root(root)
            self.assertTrue(ready.wait(3000))
            self.assertEqual([tab.tree.items[root].text(i) for i in range(1, 4)], ["2", "3", "1"])
            tab.select_path(image.parent)
            self.assertEqual(tab.current_folder, image.parent)
            self.assertEqual(tab.grid.item(0).data(Qt.UserRole), image)
            tab.grid.setCurrentRow(0)
            self.assertEqual(tab.current_file, image)
            with patch("image_folder_studio.QMessageBox.exec_", return_value=QMessageBox.Cancel):
                tab.delete_button.click()
            self.assertTrue(image.is_file())
            tab.select_path(root)
            tab.new_button.click()
            self.assertTrue(ready.wait(3000))
            self.assertEqual(tab.current_folder, root / "003")
            self.assertTrue((root / "003").is_dir())

    def test_manage_tab_copies_and_moves_then_refreshes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_file(root, "001/caption.txt")
            copy_destination = root / "002"
            move_destination = root / "003"
            copy_destination.mkdir()
            move_destination.mkdir()
            tab = ManageTab()
            ready = QSignalSpy(tab.snapshot_ready)
            tab.set_root(root)
            self.assertTrue(ready.wait(3000))
            tab.select_path(source)

            with patch("image_folder_studio.DestinationDialog") as dialog:
                dialog.return_value.exec_.return_value = QDialog.Accepted
                dialog.return_value.destination = copy_destination
                tab.copy_button.click()
                self.assertTrue(ready.wait(3000))
                self.assertEqual(tab.current_file, source)
                self.assertIn(copy_destination / source.name, tab.tree.items)

                dialog.return_value.destination = move_destination
                tab.move_button.click()
                self.assertTrue(ready.wait(3000))
            self.assertEqual(tab.current_folder, source.parent)
            self.assertIsNone(tab.current_file)
            self.assertNotIn(source, tab.tree.items)
            self.assertEqual((move_destination / source.name).read_bytes(), b"sample")
