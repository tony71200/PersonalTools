#!/usr/bin/env python3
# extract_frames_interactive.py

"""
Extract frames from video(s) using OpenCV (interactive, no argparse).

- Input: file path OR folder path
- Output: JPG only
- Size: original frame size (no resize)
- Sampling: save every N frames
- Naming:
  - <video_name>_<index>.jpg  (index counts saved frames: 0,1,2,...)
"""

from __future__ import annotations

import os
import sys
from typing import List, Tuple

import cv2


VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"}


def ask(prompt: str, default: str | None = None) -> str:
    if default is None:
        return input(prompt).strip()
    val = input(f"{prompt} [{default}]: ").strip()
    return val if val else default


def ask_int(prompt: str, default: int) -> int:
    while True:
        s = ask(prompt, str(default))
        try:
            v = int(s)
            if v < 1:
                raise ValueError
            return v
        except Exception:
            print("  -> Vui lòng nhập số nguyên >= 1.")


def ask_yes_no(prompt: str, default_yes: bool) -> bool:
    default = "y" if default_yes else "n"
    while True:
        s = ask(prompt + " (y/n)", default).lower()
        if s in {"y", "yes"}:
            return True
        if s in {"n", "no"}:
            return False
        print("  -> Nhập y hoặc n.")


def is_video_file(path: str) -> bool:
    return os.path.isfile(path) and os.path.splitext(path)[1].lower() in VIDEO_EXTS


def collect_videos(folder: str, recursive: bool) -> List[str]:
    vids: List[str] = []
    folder = os.path.abspath(folder)

    if recursive:
        for root, _dirs, files in os.walk(folder):
            for fn in files:
                p = os.path.join(root, fn)
                if is_video_file(p):
                    vids.append(p)
    else:
        for fn in os.listdir(folder):
            p = os.path.join(folder, fn)
            if is_video_file(p):
                vids.append(p)

    vids.sort(key=lambda p: os.path.basename(p).lower())
    return vids


def safe_output_path(output_dir: str, base_name: str, idx: int, zero_pad: int = 6) -> str:
    return os.path.join(output_dir, f"{base_name}_{str(idx).zfill(zero_pad)}.jpg")


def extract_frames_from_video(
    video_path: str,
    output_dir: str,
    every_n_frames: int,
    overwrite: bool,
    zero_pad: int = 6,
) -> Tuple[int, int]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"  !! Không mở được video: {video_path}")
        return 0, 0

    base_name = os.path.splitext(os.path.basename(video_path))[0]
    saved = 0
    frame_id = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if frame_id % every_n_frames == 0:
            out_path = safe_output_path(output_dir, base_name, saved, zero_pad=zero_pad)
            if (not overwrite) and os.path.exists(out_path):
                pass
            else:
                cv2.imwrite(out_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            saved += 1

        frame_id += 1

    cap.release()
    return saved, frame_id


def main() -> None:
    print("=== Extract Frames (interactive) ===")
    input_path = ask("Nhập đường dẫn video hoặc folder")
    if not input_path:
        raise SystemExit("Thiếu input path.")

    input_path = os.path.abspath(input_path)
    if not os.path.exists(input_path):
        raise SystemExit(f"Không tồn tại: {input_path}")

    output_dir = ask("Nhập thư mục output (nếu chưa có sẽ tạo)", os.path.join(os.getcwd(), "frames_out"))
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    every_n = ask_int("Bao nhiêu frames lấy 1 ảnh? (ví dụ 5 => 0,5,10,...)", 5)
    overwrite = ask_yes_no("Cho phép ghi đè nếu file đã tồn tại?", default_yes=False)

    recursive = False
    videos: List[str] = []
    if os.path.isfile(input_path):
        if not is_video_file(input_path):
            raise SystemExit("File không phải video hỗ trợ (mp4/mov/mkv/avi/m4v/webm).")
        videos = [input_path]
    else:
        recursive = ask_yes_no("Folder: quét đệ quy (recursive)?", default_yes=False)
        videos = collect_videos(input_path, recursive=recursive)
        if not videos:
            raise SystemExit("Không tìm thấy video trong folder.")

    print("\n=== Start ===")
    print(f"Input: {input_path}")
    print(f"Output dir: {output_dir}")
    print(f"Every N frames: {every_n}")
    print(f"Overwrite: {overwrite}")
    if os.path.isdir(input_path):
        print(f"Recursive: {recursive}")
        print(f"Videos found: {len(videos)}")

    total_saved = 0
    for i, vp in enumerate(videos, start=1):
        print(f"\n[{i}/{len(videos)}] {os.path.basename(vp)}")
        saved, total_frames = extract_frames_from_video(
            video_path=vp,
            output_dir=output_dir,
            every_n_frames=every_n,
            overwrite=overwrite,
            zero_pad=6,
        )
        print(f"  Frames read: {total_frames}")
        print(f"  Saved: {saved}")
        total_saved += saved

    print("\n=== Done ===")
    print(f"Total images saved: {total_saved}")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
