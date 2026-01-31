"""
CMD app:
- chọn video/logo/output
- toggle audio
- chọn backend (fast_ffmpeg/moviepy)
- chọn encoder (Auto/CPU/GPU)
- merge theo thứ tự và xuất video
"""

from __future__ import annotations

import os
from tkinter import Tk, filedialog

from ig_merge_video_core3 import MergeOptions, VideoMerger, natural_key


def ask_video_files() -> list[str]:
    root = Tk()
    root.withdraw()
    paths = filedialog.askopenfilenames(
        title="Chọn các video để merge",
        filetypes=[("Video files", "*.mp4 *.mov *.mkv *.avi"), ("All files", "*.*")],
    )
    return list(paths)


def ask_logo_path() -> str | None:
    root = Tk()
    root.withdraw()
    p = filedialog.askopenfilename(
        title="Chọn logo (PNG/JPG) - có thể bỏ qua",
        filetypes=[("Image files", "*.png *.jpg *.jpeg"), ("All files", "*.*")],
    )
    return p or None


def ask_save_path() -> str | None:
    root = Tk()
    root.withdraw()
    p = filedialog.asksaveasfilename(
        title="Chọn nơi lưu video output",
        defaultextension=".mp4",
        filetypes=[("MP4", "*.mp4")],
    )
    return p or None


def ask_keep_audio() -> bool:
    try:
        ans = input("Giữ âm thanh? (Y/n): ").strip().lower()
        return ans != "n"
    except Exception:
        return True


def ask_backend() -> str:
    ans = (input("Backend? (1=fast_ffmpeg, 2=moviepy) [1]: ").strip() or "1").lower()
    return "moviepy" if ans in {"2", "moviepy"} else "fast_ffmpeg"


def ask_codec() -> str | None:
    supported = VideoMerger.supported_encoders()
    print("\nChọn encoder:")
    print("0) Auto")
    for i, e in enumerate(supported, start=1):
        print(f"{i}) {e.label} [{e.codec}]")
    try:
        sel = int(input("Chọn (0..N): ").strip() or "0")
    except Exception:
        sel = 0
    if sel <= 0:
        return None
    if 1 <= sel <= len(supported):
        return supported[sel - 1].codec
    return None


def main() -> None:
    video_paths = ask_video_files()
    if not video_paths:
        print("Không chọn video. Thoát.")
        return

    video_paths = sorted(video_paths, key=lambda p: natural_key(os.path.basename(p)))
    logo_path = ask_logo_path()
    output_path = ask_save_path()
    if not output_path:
        print("Không chọn nơi lưu. Thoát.")
        return

    keep_audio = ask_keep_audio()
    backend = ask_backend()
    force_codec = ask_codec()

    opts = MergeOptions(
        keep_audio=keep_audio,
        prefer_gpu=True,
        force_codec=force_codec,
        backend=backend,
    )
    merger = VideoMerger(opts)

    def status(msg: str) -> None:
        print(msg)

    try:
        res = merger.merge(video_paths, output_path, logo_path=logo_path, status=status)
        print(f"✅ Done: {res.output_path}")
        print(f"Backend: {res.debug.backend}")
        print(f"Encoder: {res.debug.encoder_label} | Codec: {res.debug.encoder_codec} | GPU: {res.debug.gpu_name}")
        if res.debug.ffmpeg_cmd:
            print("\nFFmpeg CMD:\n", res.debug.ffmpeg_cmd)
    except RuntimeError as e:
        print("❌ Lỗi:", e)
        raise


if __name__ == "__main__":
    main()
