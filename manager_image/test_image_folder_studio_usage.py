import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from image_folder_studio_core import scan_tree


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
