"""Disk capacity and folder usage for Image Folder Studio."""

from dataclasses import dataclass
import re

from PyQt5.QtCore import QStorageInfo


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
