# File: ig_merge_video_core.py
"""
ig_merge_video_core.py
======================

Core merge video dọc 9:16: blur nền + fit foreground + crossfade + logo.

Requirements (khuyến nghị đã test):
- Python >= 3.10
- numpy==1.26.4
- opencv-python==4.8.0
- pillow==10.3.0
- moviepy==1.0.3 (chỉ cần nếu dùng backend MoviePy)
- ffmpeg + ffprobe (bắt buộc cho backend Fast FFmpeg)

Tối ưu tốc độ:
- Backend "fast_ffmpeg": ffmpeg filtergraph native (nhanh hơn MoviePy).
- Backend "moviepy": fallback / tương thích.

GPU encode:
- NVIDIA: h264_nvenc
- Intel : h264_qsv
- AMD   : h264_amf
- Fallback: libx264

Lưu ý quan trọng (FIX lỗi bạn gặp):
- Trong ffmpeg filtergraph, dấu phẩy "," là separator filter.
  => Mọi dấu phẩy trong expression (min(), if(), lt(), max(), ...) phải escape: "\,"
  => Không escape sẽ gây: "No option name near '0'" / "Error parsing filterchain".
"""

from __future__ import annotations

import io
import os
import re
import shlex
import random
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# MoviePy optional (only used by MoviePy backend)
try:
    from moviepy.editor import (
        VideoFileClip,
        ImageClip,
        CompositeVideoClip,
        concatenate_videoclips,
        vfx,
    )
except Exception:  # pragma: no cover
    VideoFileClip = None
    ImageClip = None
    CompositeVideoClip = None
    concatenate_videoclips = None
    vfx = None


TARGET_SIZE: Tuple[int, int] = (1080, 1920)
TRANSITION_RANGE: Tuple[float, float] = (0.4, 0.8)
KENBURNS_MAX_ZOOM: float = 0.06
KENBURNS_MAX_PAN: int = 80

DEFAULT_FPS: int = 30
DEFAULT_VIDEO_BITRATE: str = "6000k"
DEFAULT_AUDIO_BITRATE: str = "192k"
DEFAULT_THREADS: int = 4

CancelFn = Callable[[], bool]
StatusFn = Callable[[str], None]


@dataclass(frozen=True)
class EncoderChoice:
    codec: str
    is_gpu: bool
    label: str
    ffmpeg_params: Tuple[str, ...] = ()


@dataclass
class MergeOptions:
    target_size: Tuple[int, int] = TARGET_SIZE
    transition_range: Tuple[float, float] = TRANSITION_RANGE
    kenburns_max_zoom: float = KENBURNS_MAX_ZOOM
    kenburns_max_pan: int = KENBURNS_MAX_PAN

    fps: int = DEFAULT_FPS
    video_bitrate: str = DEFAULT_VIDEO_BITRATE
    audio_bitrate: str = DEFAULT_AUDIO_BITRATE
    threads: int = DEFAULT_THREADS

    keep_audio: bool = True  # muteOption
    random_seed: Optional[int] = None

    # moviepy blur optimization
    blur_downscale: float = 0.25
    blur_ksize: int = 31

    # encode selection
    prefer_gpu: bool = True
    force_codec: Optional[str] = None
    try_hwaccel_decode: bool = False

    force_yuv420p: bool = True
    faststart: bool = True

    fallback_to_cpu_on_fail: bool = True

    backend: str = "fast_ffmpeg"  # "fast_ffmpeg" | "moviepy"

@dataclass
class ImageVideoOptions:
    """Options for creating a vertical IG video from a folder of images.

    The output duration is controlled by ``total_duration_s``. Crossfade overlaps are
    accounted for so the final video length stays close to ``total_duration_s``:

    total ~= sum(durations) - sum(transitions)
    => per_image_duration = (total_duration_s + sum(transitions)) / n

    Notes:
    - Audio is always OFF for image-based videos.
    - Ken Burns + transitions reuse the same ffmpeg filtergraph as video merge.
    """

    total_duration_s: float = 30.0
    min_images: int = 7
    duration_scale_trigger: float = 1.5
    min_transition_s: Optional[float] = None
    max_transition_s: Optional[float] = None
    image_exts: Tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp")

@dataclass
class ImageMakeOptions:
    fps: int = DEFAULT_FPS
    total_duration: float = 30.0
    output_size: Tuple[int, int] = (1080, 1920)
    video_bitrate: str = "6000k"

@dataclass(frozen=True)
class MergeDebugInfo:
    backend: str
    encoder_label: str
    encoder_codec: str
    is_gpu: bool
    gpu_name: Optional[str]
    ffmpeg_cmd: Optional[str]
    ffmpeg_stderr_tail: Optional[str]


@dataclass(frozen=True)
class MergeResult:
    output_path: str
    duration_s: float
    debug: MergeDebugInfo


def natural_key(s: str) -> List[object]:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def ensure_odd(n: int) -> int:
    return n if n % 2 == 1 else n + 1


def safe_call_status(status: Optional[StatusFn], msg: str) -> None:
    if status:
        status(msg)


def safe_cancelled(should_cancel: Optional[CancelFn]) -> bool:
    return bool(should_cancel and should_cancel())


def shell_join(cmd: Sequence[str]) -> str:
    return " ".join(shlex.quote(x) for x in cmd)


def ff_escape_commas(expr: str) -> str:
    """
    Escape commas inside ffmpeg expressions.
    Why: ffmpeg uses ',' to separate filters; commas in expressions must be escaped '\,'.
    """
    return expr.replace(",", r"\,")


class HardwareInfo:
    @staticmethod
    def _run(cmd: Sequence[str], timeout_s: int = 3) -> str:
        try:
            p = subprocess.run(
                list(cmd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=timeout_s,
            )
            return (p.stdout or "").strip()
        except Exception:
            return ""

    @classmethod
    def detect_gpu_name(cls, encoder_codec: str) -> Optional[str]:
        codec = (encoder_codec or "").lower()
        if "nvenc" in codec:
            out = cls._run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
            line = (out.splitlines() or [""])[0].strip()
            return line or "NVIDIA GPU"
        if "qsv" in codec:
            return "Intel Quick Sync"
        if "amf" in codec:
            return "AMD GPU (AMF)"
        return None


class FFmpegDetector:
    @staticmethod
    def _run_ffmpeg(args: Sequence[str]) -> str:
        try:
            p = subprocess.run(
                ["ffmpeg", *args],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
            return p.stdout or ""
        except Exception:
            return ""

    @classmethod
    def available_encoders_text(cls) -> str:
        return cls._run_ffmpeg(["-hide_banner", "-encoders"])

    @classmethod
    def list_supported_codecs(cls) -> List[EncoderChoice]:
        enc_text = cls.available_encoders_text().lower()
        out: List[EncoderChoice] = [EncoderChoice(codec="libx264", is_gpu=False, label="CPU (libx264)")]
        if "h264_nvenc" in enc_text:
            out.append(EncoderChoice(codec="h264_nvenc", is_gpu=True, label="GPU (NVIDIA NVENC)", ffmpeg_params=("-preset", "p4")))
        if "h264_qsv" in enc_text:
            out.append(EncoderChoice(codec="h264_qsv", is_gpu=True, label="GPU (Intel Quick Sync)", ffmpeg_params=("-preset", "veryfast")))
        if "h264_amf" in enc_text:
            out.append(EncoderChoice(codec="h264_amf", is_gpu=True, label="GPU (AMD AMF)", ffmpeg_params=("-quality", "speed")))
        return out

    @classmethod
    def choose_encoder(cls, opts: MergeOptions) -> EncoderChoice:
        supported = {e.codec: e for e in cls.list_supported_codecs()}
        if opts.force_codec:
            return supported.get(opts.force_codec) or EncoderChoice(
                codec=opts.force_codec,
                is_gpu=opts.force_codec != "libx264",
                label=opts.force_codec,
            )
        if not opts.prefer_gpu:
            return supported["libx264"]
        for pref in ("h264_nvenc", "h264_qsv", "h264_amf"):
            if pref in supported:
                return supported[pref]
        return supported["libx264"]


class LogoFactory:
    @staticmethod
    def default_logo_png_bytes(size_px: int = 220) -> bytes:
        img = Image.new("RGBA", (size_px, size_px), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((0, 0, size_px - 1, size_px - 1), fill=(0, 0, 0, 160), outline=(255, 255, 255, 180), width=4)

        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(size_px * 0.38))
        except Exception:
            font = ImageFont.load_default()

        text = "IG"
        bbox = d.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(((size_px - tw) / 2, (size_px - th) / 2 - 6), text, font=font, fill=(255, 255, 255, 220))

        bio = io.BytesIO()
        img.save(bio, format="PNG")
        return bio.getvalue()

    @classmethod
    def ensure_logo_file(cls, logo_path: Optional[str]) -> str:
        if logo_path and os.path.isfile(logo_path):
            return logo_path
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        tmp.write(cls.default_logo_png_bytes())
        tmp.flush()
        tmp.close()
        return tmp.name


class FrameProcessor:
    def __init__(self, blur_downscale: float = 0.25, blur_ksize: int = 31) -> None:
        self.blur_downscale = float(max(0.05, min(1.0, blur_downscale)))
        self.blur_ksize = ensure_odd(max(3, blur_ksize))

    def fast_blur_rgb(self, frame_rgb: np.ndarray) -> np.ndarray:
        frame_rgb = np.ascontiguousarray(frame_rgb)
        if self.blur_downscale >= 0.999:
            bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
            bgr_blur = cv2.GaussianBlur(bgr, (self.blur_ksize, self.blur_ksize), 0)
            return cv2.cvtColor(bgr_blur, cv2.COLOR_BGR2RGB)

        h, w = frame_rgb.shape[:2]
        sw, sh = max(2, int(w * self.blur_downscale)), max(2, int(h * self.blur_downscale))

        bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        small = cv2.resize(bgr, (sw, sh), interpolation=cv2.INTER_AREA)

        k = ensure_odd(min(self.blur_ksize, max(3, min(sw, sh) // 2 * 2 - 1)))
        blurred_small = cv2.GaussianBlur(small, (k, k), 0)
        blurred = cv2.resize(blurred_small, (w, h), interpolation=cv2.INTER_LINEAR)
        return cv2.cvtColor(blurred, cv2.COLOR_BGR2RGB)


class FFmpegProbe:
    @staticmethod
    def duration_seconds(path: str) -> float:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ]
        try:
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, text=True, encoding="utf-8", errors="ignore")
            val = (p.stdout or "").strip()
            return float(val) if val else 0.0
        except Exception:
            return 0.0


class FFmpegMerger:
    def __init__(self, opts: MergeOptions, encoder: EncoderChoice) -> None:
        self.opts = opts
        self.encoder = encoder
        if self.opts.random_seed is not None:
            random.seed(self.opts.random_seed)

    def _expr_min(self, a: str, b: str) -> str:
        # min(a,b) contains comma => must escape: min(a\,b)
        return ff_escape_commas(f"min({a},{b})")

    def _kenburns_filter(self, label_in: str, label_out: str, duration: float) -> str:
        tw, th = self.opts.target_size
        d = max(duration, 0.001)

        modes = [
            "none",
            "zoom_in",
            "zoom_out",
            "pan_lr",
            "pan_rl",
            "pan_tb",
            "pan_bt",
            "zoom_pan_lr",
            "zoom_pan_rl",
            "zoom_pan_tb",
            "zoom_pan_bt",
        ]
        mode = random.choice(modes)
        z = float(self.opts.kenburns_max_zoom)
        pan = float(self.opts.kenburns_max_pan)

        if mode == "none":
            return f"[{label_in}]null[{label_out}]"

        if mode in {"zoom_in", "zoom_pan_lr", "zoom_pan_rl", "zoom_pan_tb", "zoom_pan_bt"}:
            scale_expr = f"(1+{z}*t/{d})"
        elif mode == "zoom_out":
            scale_expr = f"(1+{z}*(1-t/{d}))"
        else:
            scale_expr = "1"

        # IMPORTANT: escape comma inside min()
        if mode in {"pan_lr", "zoom_pan_lr"}:
            xlim = self._expr_min(str(pan), f"(in_w-{tw})")
            x_expr = f"{xlim}*t/{d}"
            y_expr = "0"
        elif mode in {"pan_rl", "zoom_pan_rl"}:
            xlim = self._expr_min(str(pan), f"(in_w-{tw})")
            x_expr = f"{xlim}*(1-t/{d})"
            y_expr = "0"
        elif mode in {"pan_tb", "zoom_pan_tb"}:
            ylim = self._expr_min(str(pan), f"(in_h-{th})")
            x_expr = "0"
            y_expr = f"{ylim}*t/{d}"
        elif mode in {"pan_bt", "zoom_pan_bt"}:
            ylim = self._expr_min(str(pan), f"(in_h-{th})")
            x_expr = "0"
            y_expr = f"{ylim}*(1-t/{d})"
        else:
            x_expr = "0"
            y_expr = "0"

        # NOTE: scale has no commas; crop expressions already escaped if needed above
        return (
            f"[{label_in}]"
            f"scale=w={tw}*{scale_expr}:h={th}*{scale_expr}:eval=frame,"
            f"crop={tw}:{th}:x={x_expr}:y={y_expr}"
            f"[{label_out}]"
        )

    def _build_filter_complex(
        self,
        input_paths: Sequence[str],
        durations: Sequence[float],
        transitions: Sequence[float],
        logo_input_index: int,
        logo_size_ratio: float = 0.14,
        logo_margin: int = 30,
    ) -> Tuple[str, str, Optional[str]]:
        tw, th = self.opts.target_size

        parts: List[str] = []
        v_labels: List[str] = []
        a_labels: List[str] = []

        for i, dur in enumerate(durations):
            vin = f"{i}:v"
            ain = f"{i}:a"

            seg_base = f"seg{i}"
            parts.append(
                f"[{vin}]"
                f"scale={tw}:{th}:force_original_aspect_ratio=increase,"
                f"crop={tw}:{th},"
                f"gblur=sigma=28"
                f"[bg{i}];"
                f"[{vin}]"
                f"scale={tw}:{th}:force_original_aspect_ratio=decrease"
                f"[fg{i}];"
                f"[bg{i}][fg{i}]overlay=(W-w)/2:(H-h)/2"
                f"[{seg_base}]"
            )

            seg_kb = f"v{i}"
            parts.append(self._kenburns_filter(seg_base, seg_kb, dur))
            v_labels.append(seg_kb)

            if self.opts.keep_audio:
                parts.append(f"[{ain}]atrim=0:{dur},asetpts=PTS-STARTPTS[a{i}]")
                a_labels.append(f"a{i}")

        # Video xfade chain
        if len(v_labels) == 1:
            v_out = v_labels[0]
        else:
            offset = durations[0] - transitions[0]
            cur = v_labels[0]
            for i in range(1, len(v_labels)):
                nxt = v_labels[i]
                t = transitions[i - 1]
                out = f"vx{i}"
                parts.append(f"[{cur}][{nxt}]xfade=transition=fade:duration={t}:offset={offset}[{out}]")
                if i < len(transitions):
                    offset += durations[i] - transitions[i]
                cur = out
            v_out = cur

        # Audio acrossfade chain
        a_out: Optional[str] = None
        if self.opts.keep_audio:
            if len(a_labels) == 1:
                a_out = a_labels[0]
            else:
                cur = a_labels[0]
                for i in range(1, len(a_labels)):
                    t = transitions[i - 1]
                    out = f"ax{i}"
                    parts.append(f"[{cur}][{a_labels[i]}]acrossfade=d={t}:c1=tri:c2=tri[{out}]")
                    cur = out
                a_out = cur

        logo_label = "logo"
        logo_w = int(min(tw, th) * logo_size_ratio)
        parts.append(f"[{logo_input_index}:v]scale={logo_w}:-1[{logo_label}]")
        v_final = "vfinal"
        parts.append(f"[{v_out}][{logo_label}]overlay={logo_margin}:{th}-h-{logo_margin}[{v_final}]")

        filter_complex = ";".join(parts)
        return filter_complex, v_final, a_out

    def _compose_ffmpeg_cmd(
        self,
        input_paths: Sequence[str],
        logo_path: str,
        output_path: str,
        durations: Sequence[float],
        transitions: Sequence[float],
    ) -> List[str]:
        encoder = self.encoder
        fps = self.opts.fps
        logo_index = len(input_paths)

        filter_complex, vmap, amap = self._build_filter_complex(
            input_paths=input_paths,
            durations=durations,
            transitions=transitions,
            logo_input_index=logo_index,
        )

        cmd: List[str] = ["ffmpeg", "-y", "-hide_banner"]

        if self.opts.try_hwaccel_decode:
            cmd += ["-hwaccel", "auto"]

        for p in input_paths:
            cmd += ["-i", p]
        cmd += ["-i", logo_path]

        cmd += ["-filter_complex", filter_complex, "-map", f"[{vmap}]"]

        if self.opts.keep_audio and amap:
            cmd += ["-map", f"[{amap}]"]
        else:
            cmd += ["-an"]

        cmd += ["-r", str(fps), "-c:v", encoder.codec]
        cmd += list(encoder.ffmpeg_params)
        cmd += ["-b:v", self.opts.video_bitrate]

        if self.opts.keep_audio:
            cmd += ["-c:a", "aac", "-b:a", self.opts.audio_bitrate]

        if self.opts.force_yuv420p:
            cmd += ["-pix_fmt", "yuv420p"]

        if self.opts.faststart:
            cmd += ["-movflags", "+faststart"]

        cmd += [output_path]
        return cmd

    def merge(
        self,
        input_paths: Sequence[str],
        output_path: str,
        logo_path: Optional[str],
        should_cancel: Optional[CancelFn],
        status: Optional[StatusFn],
    ) -> Tuple[float, str, str]:
        if not input_paths:
            raise ValueError("Không có video.")

        safe_call_status(status, "Probe durations...")
        durations = [FFmpegProbe.duration_seconds(p) for p in input_paths]
        durations = [d if d > 0 else 5.0 for d in durations]

        tmin, tmax = self.opts.transition_range
        transitions = [random.uniform(tmin, tmax) for _ in range(len(input_paths) - 1)]

        logo_file = LogoFactory.ensure_logo_file(logo_path)

        cmd = self._compose_ffmpeg_cmd(
            input_paths=input_paths,
            logo_path=logo_file,
            output_path=output_path,
            durations=durations,
            transitions=transitions,
        )

        safe_call_status(status, "FFmpeg running...")
        safe_call_status(status, shell_join(cmd))

        stderr_lines: List[str] = []
        started = time.time()

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            bufsize=1,
            universal_newlines=True,
        )

        try:
            while True:
                if safe_cancelled(should_cancel):
                    proc.kill()
                    raise RuntimeError("CANCELLED")

                line = proc.stderr.readline() if proc.stderr else ""
                if line:
                    line = line.rstrip()
                    stderr_lines.append(line)
                    if len(stderr_lines) > 600:
                        stderr_lines = stderr_lines[-600:]
                    if status and ("frame=" in line or "time=" in line or "Error" in line or "error" in line):
                        safe_call_status(status, line)
                else:
                    if proc.poll() is not None:
                        break
                    time.sleep(0.02)

            rc = proc.wait()
            tail = "\n".join(stderr_lines[-200:])
            if rc != 0:
                raise RuntimeError(
                    f"FFmpeg failed (rc={rc}).\n\nCMD:\n{shell_join(cmd)}\n\nSTDERR tail:\n{tail}"
                )

            wall_s = max(0.0, time.time() - started)
            return wall_s, shell_join(cmd), tail

        finally:
            if (not logo_path) and os.path.isfile(logo_file):
                try:
                    os.unlink(logo_file)
                except Exception:
                    pass



    def make_from_images(
        self,
        image_paths: Sequence[str],
        output_path: str,
        total_duration_s: float,
        logo_path: Optional[str],
        should_cancel: Optional[CancelFn],
        status: Optional[StatusFn],
        min_transition_s: Optional[float] = None,
        max_transition_s: Optional[float] = None,
    ) -> Tuple[float, str, str]:
        """Create a vertical IG video from still images using ffmpeg (fast).

        - Each image becomes a looping video segment with Ken Burns.
        - Segments are joined using xfade transitions (fade).
        - Audio is always disabled.
        """
        if not image_paths:
            raise ValueError("Không có hình ảnh.")

        fps = self.opts.fps
        n = len(image_paths)

        tmin, tmax = self.opts.transition_range
        if min_transition_s is not None:
            tmin = float(min_transition_s)
        if max_transition_s is not None:
            tmax = float(max_transition_s)
        if tmin < 0:
            tmin = 0.0
        if tmax < tmin:
            tmax = tmin

        transitions = [random.uniform(tmin, tmax) for _ in range(max(0, n - 1))]
        total_overlap = float(sum(transitions))
        total_duration_s = float(max(0.1, total_duration_s))
        per_img = (total_duration_s + total_overlap) / max(1, n)
        durations = [per_img for _ in range(n)]

        logo_file = LogoFactory.ensure_logo_file(logo_path)
        safe_call_status(status, f"Make from images: n={n} | total={total_duration_s:.2f}s | per={per_img:.2f}s | overlap={total_overlap:.2f}s")

        filter_complex, vmap, _amap = self._build_filter_complex(
            input_paths=image_paths,
            durations=durations,
            transitions=transitions,
            logo_input_index=n,
        )

        cmd: List[str] = ["ffmpeg", "-y", "-hide_banner"]

        # Loop image inputs
        for p, dur in zip(image_paths, durations):
            cmd += ["-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", p]

        cmd += ["-i", logo_file]
        cmd += ["-filter_complex", filter_complex, "-map", f"[{vmap}]", "-an"]

        cmd += ["-r", str(fps), "-c:v", self.encoder.codec]
        cmd += list(self.encoder.ffmpeg_params)
        cmd += ["-b:v", self.opts.video_bitrate, "-threads", str(self.opts.threads)]

        if self.opts.force_yuv420p:
            cmd += ["-pix_fmt", "yuv420p"]
        if self.opts.faststart:
            cmd += ["-movflags", "+faststart"]

        cmd += [output_path]

        started = time.time()
        safe_call_status(status, "Run ffmpeg (images)...")

        stderr_lines: List[str] = []
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            bufsize=1,
        )

        try:
            while True:
                if should_cancel and should_cancel():
                    safe_call_status(status, "Cancel requested. Terminating ffmpeg...")
                    proc.terminate()
                    raise RuntimeError("Cancelled by user.")

                if proc.stderr is not None:
                    line = proc.stderr.readline()
                    if line:
                        stderr_lines.append(line.rstrip())
                        if ("time=" in line) or ("frame=" in line) or ("Error" in line) or ("error" in line):
                            safe_call_status(status, line.rstrip())
                if proc.poll() is not None:
                    break
                time.sleep(0.02)

            rc = proc.wait()
            tail = "\n".join(stderr_lines[-200:])
            if rc != 0:
                raise RuntimeError(
                    f"FFmpeg failed (rc={rc}).\n\nCMD:\n{shell_join(cmd)}\n\nSTDERR tail:\n{tail}"
                )

            wall_s = max(0.0, time.time() - started)
            return wall_s, shell_join(cmd), tail

        finally:
            if (not logo_path) and os.path.isfile(logo_file):
                try:
                    os.unlink(logo_file)
                except Exception:
                    pass

class MoviePyMerger:
    def __init__(self, opts: MergeOptions, encoder: EncoderChoice) -> None:
        if VideoFileClip is None:
            raise RuntimeError("moviepy not installed but backend='moviepy'. Please install moviepy==1.0.3.")
        self.opts = opts
        self.encoder = encoder
        if self.opts.random_seed is not None:
            random.seed(self.opts.random_seed)
        self.frame_processor = FrameProcessor(self.opts.blur_downscale, self.opts.blur_ksize)

    def fit_clip_with_blurred_bg(self, vclip: "VideoFileClip") -> Tuple["CompositeVideoClip", Tuple[int, int, int, int]]:
        tw, th = self.opts.target_size
        w, h = vclip.size

        scale_fg = min(tw / w, th / h)
        new_w, new_h = int(w * scale_fg), int(h * scale_fg)
        x_off = (tw - new_w) // 2
        y_off = (th - new_h) // 2

        scale_bg = max(tw / w, th / h)
        bg_w, bg_h = int(w * scale_bg), int(h * scale_bg)

        bg = (
            vclip.resize((bg_w, bg_h))
            .fx(vfx.crop, width=tw, height=th, x_center=bg_w / 2, y_center=bg_h / 2)
            .fl_image(self.frame_processor.fast_blur_rgb)
        )

        fg = vclip.resize((new_w, new_h)).set_position((x_off, y_off))
        comp = CompositeVideoClip([bg, fg], size=(tw, th)).set_duration(vclip.duration)
        return comp, (x_off, y_off, new_w, new_h)

    def apply_random_kenburns(self, clip: "CompositeVideoClip") -> "CompositeVideoClip":
        modes = [
            "none",
            "zoom_in", "zoom_out",
            "pan_lr", "pan_rl", "pan_tb", "pan_bt",
            "zoom_pan_lr", "zoom_pan_rl", "zoom_pan_tb", "zoom_pan_bt",
        ]
        mode = random.choice(modes)
        d = max(float(clip.duration or 0.0), 1e-6)

        max_zoom = float(self.opts.kenburns_max_zoom)
        max_pan = float(self.opts.kenburns_max_pan)

        if mode in {"zoom_in", "zoom_pan_lr", "zoom_pan_rl", "zoom_pan_tb", "zoom_pan_bt"}:
            clip = clip.resize(lambda t: 1.0 + max_zoom * (t / d))
        elif mode == "zoom_out":
            clip = clip.resize(lambda t: 1.0 + max_zoom * (1.0 - t / d))

        if mode in {"pan_lr", "zoom_pan_lr"}:
            clip = clip.set_position(lambda t: (-max_pan * (t / d), "center"))
        elif mode in {"pan_rl", "zoom_pan_rl"}:
            clip = clip.set_position(lambda t: (-max_pan * (1.0 - t / d), "center"))
        elif mode in {"pan_tb", "zoom_pan_tb"}:
            clip = clip.set_position(lambda t: ("center", -max_pan * (t / d)))
        elif mode in {"pan_bt", "zoom_pan_bt"}:
            clip = clip.set_position(lambda t: ("center", -max_pan * (1.0 - t / d)))
        return clip

    def _build_transitioned_timeline(self, clips: List["CompositeVideoClip"], status: Optional[StatusFn]) -> "CompositeVideoClip":
        if len(clips) == 1:
            return clips[0]
        tmin, tmax = self.opts.transition_range
        safe_call_status(status, "Ghép timeline (crossfade)...")
        final = clips[0]
        for i in range(1, len(clips)):
            t = random.uniform(tmin, tmax)
            clips[i] = clips[i].crossfadein(t)
            final = concatenate_videoclips([final, clips[i]], method="compose", padding=-t)
        return final

    def _compose_ffmpeg_params(self) -> List[str]:
        params = list(self.encoder.ffmpeg_params)
        if self.opts.try_hwaccel_decode:
            params = ["-hwaccel", "auto", *params]
        if self.opts.force_yuv420p:
            params += ["-pix_fmt", "yuv420p"]
        if self.opts.faststart:
            params += ["-movflags", "+faststart"]
        return params

    def merge(
        self,
        input_paths: Sequence[str],
        output_path: str,
        logo_path: Optional[str],
        should_cancel: Optional[CancelFn],
        status: Optional[StatusFn],
    ) -> Tuple[float, Optional[str], Optional[str]]:
        if not input_paths:
            raise ValueError("Không có video.")

        tw, th = self.opts.target_size
        clips_to_close: List["VideoFileClip"] = []
        processed: List["CompositeVideoClip"] = []
        try:
            for idx, path in enumerate(input_paths, start=1):
                if safe_cancelled(should_cancel):
                    raise RuntimeError("CANCELLED")
                safe_call_status(status, f"Đọc video {idx}/{len(input_paths)}: {os.path.basename(path)}")
                vclip = VideoFileClip(path, audio=self.opts.keep_audio)
                clips_to_close.append(vclip)
                comp, _ = self.fit_clip_with_blurred_bg(vclip)
                comp = self.apply_random_kenburns(comp)
                processed.append(comp)

            final = self._build_transitioned_timeline(processed, status=status)

            logo_file = LogoFactory.ensure_logo_file(logo_path)
            logo = ImageClip(logo_file).set_duration(final.duration).resize(width=int(min(tw, th) * 0.14))
            final = CompositeVideoClip([final, logo.set_position((30, th - logo.h - 30))], size=(tw, th)).set_duration(final.duration)

            ffmpeg_params = self._compose_ffmpeg_params()
            safe_call_status(status, f"Export ({self.encoder.label})...")
            started = time.time()
            final.write_videofile(
                output_path,
                fps=self.opts.fps,
                codec=self.encoder.codec,
                audio=self.opts.keep_audio,
                audio_codec="aac" if self.opts.keep_audio else None,
                bitrate=self.opts.video_bitrate,
                audio_bitrate=self.opts.audio_bitrate if self.opts.keep_audio else None,
                threads=self.opts.threads,
                ffmpeg_params=ffmpeg_params or None,
            )
            return max(0.0, time.time() - started), None, None
        finally:
            for c in processed:
                try:
                    c.close()
                except Exception:
                    pass
            for c in clips_to_close:
                try:
                    c.close()
                except Exception:
                    pass


    def make_from_images(
        self,
        image_paths: Sequence[str],
        output_path: str,
        total_duration_s: float,
        logo_path: Optional[str],
        should_cancel: Optional[CancelFn],
        status: Optional[StatusFn],
        min_transition_s: Optional[float] = None,
        max_transition_s: Optional[float] = None,
    ) -> Tuple[float, str, str]:
        """Fallback slideshow builder using MoviePy.

        - Forces codec to libx264 to avoid GPU driver issues.
        - Uses random transition durations within range (default: opts.transition_range).
        - Audio is always OFF.
        """
        if not image_paths:
            raise ValueError("Không có hình ảnh.")

        tmin, tmax = self.opts.transition_range
        if min_transition_s is not None:
            tmin = float(min_transition_s)
        if max_transition_s is not None:
            tmax = float(max_transition_s)
        tmin = max(0.0, tmin)
        tmax = max(tmin, tmax)

        total_duration_s = float(max(0.1, total_duration_s))
        n = len(image_paths)
        transitions = [random.uniform(tmin, tmax) for _ in range(max(0, n - 1))]
        total_overlap = float(sum(transitions))
        per_img = (total_duration_s + total_overlap) / max(1, n)

        safe_call_status(status, f"Backend: moviepy | Encoder: libx264 (forced) | Audio: OFF")
        safe_call_status(status, f"Make from images (moviepy): n={n} total={total_duration_s:.2f}s per={per_img:.2f}s")

        processed: List[CompositeVideoClip] = []
        clips_to_close: List[object] = []

        try:
            clips: List[CompositeVideoClip] = []
            for p in image_paths:
                if should_cancel and should_cancel():
                    raise RuntimeError("CANCELLED")
                base = ImageClip(p).set_duration(per_img)
                clips_to_close.append(base)
                fitted, _pos = self.fit_clip_with_blurred_bg(base)
                fitted = fitted.set_duration(per_img)
                fitted = self.apply_random_kenburns(fitted)
                processed.append(fitted)
                clips.append(fitted)

            if not clips:
                raise ValueError("Không có clip hợp lệ.")

            out = clips[0]
            for i in range(1, len(clips)):
                tr = transitions[i - 1] if i - 1 < len(transitions) else 0.0
                if tr > 0:
                    clips[i] = clips[i].crossfadein(tr)
                    out = concatenate_videoclips([out, clips[i]], method="compose", padding=-tr)
                else:
                    out = concatenate_videoclips([out, clips[i]], method="compose")

            # logo overlay (optional)
            logo_file = LogoFactory.ensure_logo_file(logo_path)
            if logo_file and os.path.isfile(logo_file):
                try:
                    tw, th = self.opts.target_size
                    logo_h = int(min(tw, th) * 0.14)
                    margin = 30
                    logo = ImageClip(logo_file).set_duration(out.duration).resize(height=logo_h)
                    clips_to_close.append(logo)
                    logo = logo.set_position((margin, th - logo_h - margin))
                    out = CompositeVideoClip([out, logo], size=(tw, th)).set_duration(out.duration)
                except Exception:
                    pass

            started = time.time()
            out.write_videofile(
                output_path,
                fps=int(self.opts.fps),
                codec="libx264",
                audio=False,
                bitrate=self.opts.video_bitrate,
                threads=self.opts.threads,
                logger=None,
            )
            wall_s = max(0.0, time.time() - started)
            return wall_s, "moviepy_write_videofile(codec=libx264)", ""
        finally:
            for c in processed:
                try:
                    c.close()
                except Exception:
                    pass
            for c in clips_to_close:
                try:
                    c.close()
                except Exception:
                    pass


class VideoMerger:
    def __init__(self, opts: Optional[MergeOptions] = None) -> None:
        self.opts = opts or MergeOptions()
        if self.opts.random_seed is not None:
            random.seed(self.opts.random_seed)
        self.encoder = FFmpegDetector.choose_encoder(self.opts)
        self.gpu_name = HardwareInfo.detect_gpu_name(self.encoder.codec)

    @staticmethod
    def supported_encoders() -> List[EncoderChoice]:
        return FFmpegDetector.list_supported_codecs()

    def processing_backend_label(self) -> str:
        if self.encoder.is_gpu:
            return f"{self.encoder.label} ({self.gpu_name or 'GPU'})"
        return self.encoder.label

    def _debug(self, backend: str, cmd: Optional[str], tail: Optional[str]) -> MergeDebugInfo:
        return MergeDebugInfo(
            backend=backend,
            encoder_label=self.encoder.label,
            encoder_codec=self.encoder.codec,
            is_gpu=self.encoder.is_gpu,
            gpu_name=self.gpu_name,
            ffmpeg_cmd=cmd,
            ffmpeg_stderr_tail=tail,
        )

    def merge(
        self,
        video_paths: Sequence[str],
        output_path: str,
        logo_path: Optional[str] = None,
        should_cancel: Optional[CancelFn] = None,
        status: Optional[StatusFn] = None,
    ) -> MergeResult:
        if not video_paths:
            raise ValueError("Không có video nào để merge.")

        safe_call_status(status, f"Backend: {self.opts.backend} | Encoder: {self.processing_backend_label()} | Audio: {'ON' if self.opts.keep_audio else 'OFF'}")

        if self.opts.backend == "fast_ffmpeg":
            ffm = FFmpegMerger(self.opts, self.encoder)
            try:
                wall_s, cmd, tail = ffm.merge(video_paths, output_path, logo_path, should_cancel, status)
                return MergeResult(output_path=output_path, duration_s=wall_s, debug=self._debug("fast_ffmpeg", cmd, tail))
            except RuntimeError as e:
                if self.encoder.is_gpu and self.opts.fallback_to_cpu_on_fail:
                    safe_call_status(status, f"⚠️ GPU encode lỗi. Retry CPU libx264...\n{e}")
                    self.encoder = EncoderChoice(codec="libx264", is_gpu=False, label="CPU (libx264)")
                    self.gpu_name = None
                    ffm2 = FFmpegMerger(self.opts, self.encoder)
                    wall_s, cmd, tail = ffm2.merge(video_paths, output_path, logo_path, should_cancel, status)
                    return MergeResult(output_path=output_path, duration_s=wall_s, debug=self._debug("fast_ffmpeg", cmd, tail))
                raise

        if self.opts.backend == "moviepy":
            mp = MoviePyMerger(self.opts, self.encoder)
            try:
                wall_s, cmd, tail = mp.merge(video_paths, output_path, logo_path, should_cancel, status)
                return MergeResult(output_path=output_path, duration_s=wall_s, debug=self._debug("moviepy", cmd, tail))
            except OSError as e:
                if self.encoder.is_gpu and self.opts.fallback_to_cpu_on_fail:
                    safe_call_status(status, f"⚠️ GPU encode lỗi (MoviePy). Retry CPU libx264...\n{e}")
                    self.encoder = EncoderChoice(codec="libx264", is_gpu=False, label="CPU (libx264)")
                    self.gpu_name = None
                    mp2 = MoviePyMerger(self.opts, self.encoder)
                    wall_s, cmd, tail = mp2.merge(video_paths, output_path, logo_path, should_cancel, status)
                    return MergeResult(output_path=output_path, duration_s=wall_s, debug=self._debug("moviepy", cmd, tail))
                raise

        raise ValueError(f"Unknown backend: {self.opts.backend}")



    def make_video_from_image_folder(
        self,
        image_folder: str,
        output_path: str,
        logo_path: Optional[str] = None,
        img_opts: Optional[ImageVideoOptions] = None,
        should_cancel: Optional[CancelFn] = None,
        status: Optional[StatusFn] = None,
    ) -> MergeResult:
        """Create an IG-style vertical video from images in a folder (Fast FFmpeg).

        Skip creation if number of images < ``img_opts.min_images``.
        If number of images > ``min_images * duration_scale_trigger``, increase total duration proportionally.
        """
        opts = img_opts or ImageVideoOptions()

        if not os.path.isdir(image_folder):
            raise ValueError(f"Folder không tồn tại: {image_folder}")

        exts = tuple(e.lower() for e in opts.image_exts)
        files = [
            os.path.join(image_folder, f)
            for f in os.listdir(image_folder)
            if os.path.isfile(os.path.join(image_folder, f)) and os.path.splitext(f)[1].lower() in exts
        ]
        files.sort(key=natural_key)
        n = len(files)
        if n == 0:
            raise ValueError("Folder không có hình ảnh hợp lệ.")

        if n < int(max(1, opts.min_images)):
            safe_call_status(status, f"Skip: {os.path.basename(image_folder)} (images={n} < min={opts.min_images})")
            return MergeResult(output_path="", duration_s=0.0, debug=self._debug("fast_ffmpeg_images_skip", "", ""))

        total_duration = float(max(0.1, opts.total_duration_s))
        trigger = float(max(1.0, opts.duration_scale_trigger))
        if n > (opts.min_images * trigger):
            total_duration = total_duration * (n / (opts.min_images * trigger))
            safe_call_status(status, f"Auto duration: n={n} > min*{trigger:g} => total={total_duration:.2f}s")

        
        prev_backend = self.opts.backend
        prev_keep_audio = self.opts.keep_audio
        prev_bitrate = self.opts.video_bitrate
        try:
            target_backend = prev_backend if prev_backend in ("fast_ffmpeg", "moviepy") else "fast_ffmpeg"
            self.opts.backend = target_backend
            self.opts.keep_audio = False
            self.opts.video_bitrate = DEFAULT_VIDEO_BITRATE  # fixed 6000k

            if target_backend == "fast_ffmpeg":
                self.encoder = FFmpegDetector.choose_encoder(self.opts)
                self.gpu_name = HardwareInfo.detect_gpu_name(self.encoder.codec)

                safe_call_status(
                    status,
                    f"Backend: fast_ffmpeg | Encoder: {self.processing_backend_label()} | Audio: OFF",
                )
                ffm = FFmpegMerger(self.opts, self.encoder)

                wall_s, cmd, tail = ffm.make_from_images(
                    image_paths=files,
                    output_path=output_path,
                    total_duration_s=total_duration,
                    logo_path=logo_path,
                    should_cancel=should_cancel,
                    status=status,
                    min_transition_s=opts.min_transition_s,
                    max_transition_s=opts.max_transition_s,
                )
                return MergeResult(
                    output_path=output_path,
                    duration_s=wall_s,
                    debug=self._debug("fast_ffmpeg_images", cmd, tail),
                )

            # MoviePy fallback (forces libx264 inside)
            self.encoder = EncoderChoice(label="CPU (libx264)", codec="libx264", is_gpu=False)
            self.gpu_name = None

            safe_call_status(
                status,
                "Backend: moviepy | Encoder: libx264 (forced) | Audio: OFF",
            )
            mp = MoviePyMerger(self.opts, self.encoder)
            wall_s, cmd, tail = mp.make_from_images(
                image_paths=files,
                output_path=output_path,
                total_duration_s=total_duration,
                logo_path=logo_path,
                should_cancel=should_cancel,
                status=status,
                min_transition_s=opts.min_transition_s,
                max_transition_s=opts.max_transition_s,
            )
            return MergeResult(
                output_path=output_path,
                duration_s=wall_s,
                debug=self._debug("moviepy_images", cmd, tail),
            )
        finally:
            self.opts.backend = prev_backend
            self.opts.keep_audio = prev_keep_audio
            self.opts.video_bitrate = prev_bitrate

    def make_videos_from_parent_folder(
        self,
        parent_folder: str,
        output_dir: str,
        logo_path: Optional[str] = None,
        img_opts: Optional[ImageVideoOptions] = None,
        should_cancel: Optional[CancelFn] = None,
        status: Optional[StatusFn] = None,
    ) -> List[MergeResult]:
        """Batch create videos from each direct subfolder (1-level)."""
        if not os.path.isdir(parent_folder):
            raise ValueError(f"Folder không tồn tại: {parent_folder}")

        os.makedirs(output_dir, exist_ok=True)
        subfolders = [
            os.path.join(parent_folder, d)
            for d in os.listdir(parent_folder)
            if os.path.isdir(os.path.join(parent_folder, d))
        ]
        subfolders.sort(key=natural_key)

        results: List[MergeResult] = []
        for i, sub in enumerate(subfolders, 1):
            if should_cancel and should_cancel():
                safe_call_status(status, "Cancel requested.")
                break

            name = os.path.basename(sub.rstrip("/\\"))
            out_path = os.path.join(output_dir, f"{name}.mp4")

            safe_call_status(status, f"[{i}/{len(subfolders)}] Folder: {name}")
            try:
                res = self.make_video_from_image_folder(
                    image_folder=sub,
                    output_path=out_path,
                    logo_path=logo_path,
                    img_opts=img_opts,
                    should_cancel=should_cancel,
                    status=status,
                )
                results.append(res)
            except Exception as e:
                safe_call_status(status, f"Error folder '{name}': {e}")

        return results
