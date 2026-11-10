import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication

from image_folder_studio import MainWindow
from image_folder_studio_core import scan_tree
from image_folder_studio_usage import DiskUsageTab, DriveUsage, format_bytes, format_ratio, read_drives


class FolderUsageTests(unittest.TestCase):
    def test_folder_sizes_include_direct_and_nested_files(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "image.png").write_bytes(b"a" * 100)
            (root / "work" / "nested").mkdir(parents=True)
            (root / "work" / "file.cs").write_bytes(b"b" * 30)
            (root / "work" / "nested" / "file.py").write_bytes(b"c" * 20)
            (root / "empty").mkdir()
            snapshot = scan_tree(root)
            self.assertEqual(snapshot.folders[root].total_bytes, 150)
            self.assertEqual(snapshot.folders[root / "work"].total_bytes, 50)
            self.assertEqual(snapshot.folders[root / "empty"].total_bytes, 0)
            self.assertFalse(snapshot.root_unreadable)

    def test_denied_branch_keeps_other_sizes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            blocked = root / "blocked"
            blocked.mkdir()
            (root / "file.txt").write_bytes(b"hello")
            scandir = os.scandir

            def read(path):
                if Path(path) == blocked:
                    raise PermissionError("denied")
                return scandir(path)

            with patch("image_folder_studio_core.os.scandir", side_effect=read):
                snapshot = scan_tree(root)
            self.assertEqual(snapshot.folders[root].total_bytes, 5)
            self.assertIn("denied", snapshot.errors_by_folder[blocked][0])
            self.assertFalse(snapshot.root_unreadable)
            with patch("image_folder_studio_core.os.scandir", side_effect=PermissionError("denied")):
                self.assertTrue(scan_tree(root).root_unreadable)


class DriveUsageTests(unittest.TestCase):
    def test_reads_ready_drive_letters_in_order(self):
        def volume(path, label, total=1000, free=250, ready=True, valid=True):
            return SimpleNamespace(
                rootPath=lambda: path, name=lambda: label,
                isValid=lambda: valid, isReady=lambda: ready,
                bytesTotal=lambda: total, bytesFree=lambda: free,
            )

        mounted = [
            volume("E:\\", "Backup"), volume("C:/", "System"),
            volume("c:/", "Duplicate"), volume("D:/", "", ready=False),
            volume("C:/mount", "Mount"), volume("F:/", "", free=-1),
            volume("G:/", "", valid=False),
        ]
        with patch("image_folder_studio_usage.QStorageInfo.mountedVolumes", return_value=mounted):
            drives = read_drives()
        self.assertEqual([(d.letter, d.label, d.used_bytes) for d in drives],
                         [("C:", "System", 750), ("E:", "Backup", 750)])

    def test_format_size_and_empty_ratio(self):
        self.assertEqual(format_bytes(3_200_000_000), "3,2 GB")
        self.assertEqual(format_bytes(999), "999 B")
        self.assertEqual(format_bytes(1_000), "1 KB")
        self.assertEqual(format_ratio("Ảnh", 3_200_000_000, 10_000_000_000),
                         (3200, "Ảnh — 3,2 GB / 10 GB (32%)"))
        self.assertEqual(format_ratio("Rỗng", 0, 0), (0, "Rỗng — 0 B / 0 B (—)"))


class DiskUsageTabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_this_pc_and_folder_use_distinct_totals(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "direct.txt").write_bytes(b"abcd")
            (root / "branch").mkdir()
            (root / "branch" / "data.txt").write_bytes(b"ab")
            window = MainWindow()
            self.addCleanup(window.close)
            tab = window.tab_usage
            self.assertEqual(window.tabs.tabText(2), "Dung lượng")
            loaded = QSignalSpy(tab.loaded)
            with patch("image_folder_studio_usage.read_drives",
                       return_value=(DriveUsage("C:", "System", 1000, 250),)):
                with patch("image_folder_studio_usage.scan_tree") as scan:
                    window.tabs.setCurrentWidget(tab)
                    window.show()
                    self.assertTrue(len(loaded) or loaded.wait(3000))
                    scan.assert_not_called()
                drive = tab.tree.topLevelItem(0).child(0)
                self.assertEqual([drive.text(i) for i in range(1, 4)], ["750 B", "250 B", "1 KB"])
                tab.tree.setCurrentItem(drive)
                self.assertEqual(tab.bar.value(), 7500)
                tab.set_root(root)
                self.assertTrue(loaded.wait(3000))
                self.assertEqual(tab.bar.value(), 10_000)
                tab.tree.setCurrentItem(tab.tree.topLevelItem(1).child(0))
                self.assertEqual(tab.bar.value(), 3333)
                self.assertIn("2 B / 6 B (33,33%)", tab.summary.text())
                tab.tree.itemClicked.emit(tab.tree.topLevelItem(0), 0)
                self.assertTrue(loaded.wait(3000))
                self.assertEqual(tab.tree.topLevelItemCount(), 1)

    def test_folder_rows_sort_by_bytes_and_report_partial_scan(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for folder, size in (("a-small", 9), ("b-large", 2000), ("c-medium", 1000)):
                (root / folder).mkdir()
                (root / folder / "data.txt").write_bytes(b"a" * size)
            blocked = root / "blocked"
            blocked.mkdir()
            scandir = os.scandir

            def read(path):
                if Path(path) == blocked:
                    raise PermissionError("denied")
                return scandir(path)

            tab = DiskUsageTab()
            loaded = QSignalSpy(tab.loaded)
            with patch("image_folder_studio_core.os.scandir", side_effect=read):
                tab.set_root(root)
                self.assertTrue(loaded.wait(3000))
            folder = tab.tree.topLevelItem(1)
            self.assertEqual([folder.child(i).text(0) for i in range(folder.childCount())],
                             ["b-large", "c-medium", "a-small", "blocked"])
            self.assertIn("denied", folder.child(3).toolTip(0))
            tab.tree.setCurrentItem(folder.child(0))
            self.assertIn("Dung lượng chưa đầy đủ", tab.status.text())

    def test_root_errors_and_empty_folders_have_distinct_status(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            tab = DiskUsageTab()
            loaded = QSignalSpy(tab.loaded)
            tab.set_root(root)
            self.assertTrue(loaded.wait(3000))
            self.assertIn("0 B / 0 B (—)", tab.summary.text())
            self.assertEqual(tab.bar.value(), 0)
            tab.set_root(root / "missing")
            self.assertTrue(loaded.wait(3000))
            self.assertEqual(tab.tree.topLevelItemCount(), 1)
            self.assertIn("Không đọc được thư mục", tab.status.text())

    def test_discard_scan_after_switching_folder_or_returning_to_this_pc(self):
        with TemporaryDirectory() as tmp:
            first, second = Path(tmp) / "A", Path(tmp) / "B"
            first.mkdir()
            second.mkdir()
            jobs = []

            def enqueue(_owner, work, accept, _fail, **_options):
                jobs.append((work, accept))

            def deliver(index):
                work, accept = jobs[index]
                accept(work())

            tab = DiskUsageTab()
            with patch("image_folder_studio_usage.run_background", side_effect=enqueue), \
                 patch("image_folder_studio_usage.read_drives", return_value=()):
                tab.set_root(first)
                tab.set_root(second)
                deliver(1)
                deliver(0)
                self.assertEqual(tab.tree.topLevelItem(1).text(0), "B")
                tab.set_root(first)
                tab.tree.itemClicked.emit(tab.tree.topLevelItem(0), 0)
                deliver(3)
                deliver(2)
            self.assertEqual(tab.tree.topLevelItemCount(), 1)
            self.assertIn("Không có ổ đĩa", tab.status.text())
