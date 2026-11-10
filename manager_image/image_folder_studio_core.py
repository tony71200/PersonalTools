"""Folder snapshots, filename matching, and file operations for Image Folder Studio."""

from collections import defaultdict
from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat

from PyQt5.QtCore import QFile


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


@dataclass(frozen=True)
class FolderEntry:
    children: tuple[Path, ...]
    files: tuple[Path, ...]
    descendant_count: int
    image_count: int
    cover: Path | None
    total_bytes: int


@dataclass(frozen=True)
class TreeSnapshot:
    root: Path
    folders: dict[Path, FolderEntry]
    errors: tuple[str, ...]
    errors_by_folder: dict[Path, tuple[str, ...]]
    root_unreadable: bool


@dataclass(frozen=True)
class Comparison:
    left_total: int
    right_total: int
    left_matches: dict[Path, tuple[Path, ...]]
    right_matches: dict[Path, tuple[Path, ...]]
    common_names: int


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def _is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def _read_directory(folder: Path, errors: list[str]) -> tuple[list[Path], list[Path], int, bool]:
    children = []
    files = []
    direct_bytes = 0
    try:
        entries = os.scandir(folder)
    except OSError as error:
        errors.append(f"{folder}: {error}")
        return children, files, direct_bytes, False
    try:
        with entries:
            for entry in entries:
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError as error:
                    errors.append(f"{entry.path}: {error}")
                    continue
                if _is_link(info):
                    continue
                if stat.S_ISDIR(info.st_mode):
                    children.append(Path(entry.path))
                elif stat.S_ISREG(info.st_mode):
                    files.append(Path(entry.path))
                    direct_bytes += info.st_size
    except OSError as error:
        errors.append(f"{folder}: {error}")
    key = lambda path: (path.name.casefold(), path.name)
    return sorted(children, key=key), sorted(files, key=key), direct_bytes, True


def scan_tree(root: Path) -> TreeSnapshot:
    root = Path(os.path.abspath(root))
    try:
        info = root.lstat()
        if _is_link(info) or not stat.S_ISDIR(info.st_mode):
            raise OSError("Đường dẫn gốc phải là thư mục thường.")
    except OSError as error:
        errors = (f"{root}: {error}",)
        return TreeSnapshot(root, {}, errors, {root: errors}, True)

    directory_lists = {}
    errors_by_folder = {}
    root_unreadable = False
    pending = [root]
    while pending:
        folder = pending.pop()
        folder_errors = []
        children, files, direct_bytes, opened = _read_directory(folder, folder_errors)
        if folder_errors:
            errors_by_folder[folder] = tuple(folder_errors)
        if folder == root:
            root_unreadable = not opened
        directory_lists[folder] = (children, files, direct_bytes)
        pending.extend(reversed(children))

    folders = {}
    for folder, (children, files, direct_bytes) in reversed(directory_lists.items()):
        images = [path for path in files if is_image(path)]
        child_entries = [folders[child] for child in children]
        cover = images[0] if images else next(
            (entry.cover for entry in child_entries if entry.cover is not None), None
        )
        folders[folder] = FolderEntry(
            tuple(children), tuple(files),
            sum(1 + entry.descendant_count for entry in child_entries),
            len(images) + sum(entry.image_count for entry in child_entries),
            cover,
            direct_bytes + sum(entry.total_bytes for entry in child_entries),
        )
    errors = tuple(error for messages in errors_by_folder.values() for error in messages)
    return TreeSnapshot(root, folders, errors, errors_by_folder, root_unreadable)


def _image_index(snapshot: TreeSnapshot) -> dict[str, tuple[Path, ...]]:
    names = defaultdict(list)
    for folder in snapshot.folders.values():
        for path in folder.files:
            if is_image(path):
                names[path.name.casefold()].append(path)
    return {name: tuple(paths) for name, paths in names.items()}


def compare_trees(left: TreeSnapshot, right: TreeSnapshot) -> Comparison:
    left_index, right_index = _image_index(left), _image_index(right)
    common = left_index.keys() & right_index.keys()
    return Comparison(
        sum(map(len, left_index.values())),
        sum(map(len, right_index.values())),
        {path: right_index[name] for name in common for path in left_index[name]},
        {path: left_index[name] for name in common for path in right_index[name]},
        len(common),
    )


def _checked_path(root: Path, path: Path, *, directory: bool) -> Path:
    root, path = Path(os.path.abspath(root)), Path(os.path.abspath(path))
    if not path.is_relative_to(root):
        raise OSError(f"{path}: nằm ngoài thư mục gốc.")

    current = root
    info = current.lstat()
    if _is_link(info) or not stat.S_ISDIR(info.st_mode):
        raise OSError(f"{root}: thư mục gốc không hợp lệ.")
    for part in path.relative_to(root).parts:
        current /= part
        info = current.lstat()
        if _is_link(info):
            raise OSError(f"{current}: liên kết hoặc junction.")
    if not path.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
        raise OSError(f"{path}: nằm ngoài thư mục gốc.")
    valid_type = stat.S_ISDIR if directory else stat.S_ISREG
    if not valid_type(info.st_mode):
        raise OSError(f"{path}: cần {'thư mục' if directory else 'file'} thông thường.")
    return path


def create_numbered_folder(root: Path, parent: Path) -> Path:
    parent = _checked_path(root, parent, directory=True)
    numbers = [0]
    with os.scandir(parent) as entries:
        for entry in entries:
            if re.fullmatch(r"[0-9]+", entry.name):
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode) and not _is_link(info):
                    numbers.append(int(entry.name))
    number = max(numbers) + 1
    while True:
        candidate = parent / f"{number:03d}"
        try:
            candidate.mkdir()
        except FileExistsError:
            number += 1
        else:
            return candidate


def _transfer(root: Path, source: Path, destination_dir: Path, *, move: bool) -> Path:
    source = _checked_path(root, source, directory=False)
    destination_dir = _checked_path(root, destination_dir, directory=True)
    target = destination_dir / source.name
    if os.path.lexists(target):
        raise FileExistsError(f"{target}: đã có mục cùng tên.")
    file = QFile(str(source))
    operation = file.rename if move else file.copy
    if not operation(str(target)):
        raise OSError(f"{source} → {target}: {file.errorString()}")
    return target


def copy_file(root: Path, source: Path, destination_dir: Path) -> Path:
    return _transfer(root, source, destination_dir, move=False)


def move_file(root: Path, source: Path, destination_dir: Path) -> Path:
    return _transfer(root, source, destination_dir, move=True)


def trash_file(root: Path, source: Path) -> None:
    source = _checked_path(root, source, directory=False)
    file = QFile(str(source))
    if not file.moveToTrash():
        raise OSError(f"{source}: {file.errorString()}")
