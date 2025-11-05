# Requirements:
# moviepy==1.0.3
# opencv-python==4.8.0
# pillow==10.3.0
# numpy==1.26.4

import os
import re
import sys
import cv2
import time
import itertools
import threading
import numpy as np
from moviepy.editor import ImageClip, CompositeVideoClip, concatenate_videoclips
from PIL import Image, ImageOps

# ------------------ CẤU HÌNH ------------------
TARGET_SIZE = (1080, 1920)   # 9:16
DEFAULT_DURATION = 0.2       # giây/ảnh
FPS = 30
BLUR_KSIZE = 101             # kernel Gaussian (lớn để blur mịn)
FORCE_PORTRAIT = True        # True: quay ảnh nằm ngang về dọc
VALID_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

# ------------------ TIỆN ÍCH ------------------
def natural_key(s: str):
    """Sắp xếp theo thứ tự tự nhiên: img2 < img10."""
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]

def spinner(label="Đang xử lý"):
    for c in itertools.cycle("|/-\\"):
        sys.stdout.write(f"\r{label}... {c}")
        sys.stdout.flush()
        time.sleep(0.1)

def correct_exif_orientation(pil_img: Image.Image) -> Image.Image:
    """
    Sửa hướng EXIF về pixel thật (tránh hiện tượng hiển thị bị xoay trong video).
    """
    return ImageOps.exif_transpose(pil_img)

def ensure_portrait(pil_img: Image.Image) -> Image.Image:
    """
    Nếu FORCE_PORTRAIT = True và ảnh là landscape (w > h) -> xoay 90° CW.
    """
    if FORCE_PORTRAIT:
        w, h = pil_img.size
        if w > h:
            pil_img = pil_img.rotate(-90, expand=True)  # -90: xoay CW
    return pil_img

def pil_to_rgb_array(pil_img: Image.Image) -> np.ndarray:
    """
    Đưa PIL image về numpy RGB (moviepy sử dụng RGB).
    """
    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")
    return np.array(pil_img)

def make_blurred_bg_and_foreground(rgb_arr: np.ndarray, target_size=(1080, 1920), blur_ksize=101):
    """
    Tạo frame 9:16:
      - background: ảnh fill khung rồi blur + crop đúng target
      - foreground: ảnh fit vào khung, đặt giữa
    Trả về: frame RGB (numpy array) đã hợp thành.
    """
    th = target_size[1]
    tw = target_size[0]
    H, W= rgb_arr.shape[:2]

    # ----- Background: fill -----
    # Scale để BG phủ kín khung (max)
    scale_bg = max(tw / W, th / H)
    bg_w = max(1, int(round(W * scale_bg)))
    bg_h = max(1, int(round(H * scale_bg)))
    bg = cv2.resize(rgb_arr, (bg_w, bg_h), interpolation=cv2.INTER_LINEAR)

    x0 = (bg_w - tw) // 2
    y0 = (bg_h - th) // 2
    x1 = x0 + tw
    y1 = y0 + th

    bg_crop = np.zeros((th, tw, 3), dtype=bg.dtype)

    # Clamp nguồn
    sx0 = max(0, x0); sy0 = max(0, y0)
    sx1 = min(bg_w, x1); sy1 = min(bg_h, y1)
    src_w = max(0, sx1 - sx0)
    src_h = max(0, sy1 - sy0)

    # Tính vị trí đặt vào đích sao cho luôn nằm trong 0..tw/th
    dx0 = max(0, -x0); dy0 = max(0, -y0)
    dx1 = min(tw, dx0 + src_w); dy1 = min(th, dy0 + src_h)

    if src_w > 0 and src_h > 0 and dx1 > dx0 and dy1 > dy0:
        bg_crop[dy0:dy1, dx0:dx1] = bg[sy0:sy1, sx0:sx1]
    # Nếu vì lý do gì đó vẫn rỗng, fallback: resize cứng
    else:
        bg_crop = cv2.resize(rgb_arr, (tw, th), interpolation=cv2.INTER_LINEAR)

    # Blur BG (RGB<->BGR)
    bgr = cv2.cvtColor(bg_crop, cv2.COLOR_RGB2BGR)
    # Đảm bảo kernel lẻ và >=3
    k = blur_ksize if blur_ksize % 2 == 1 else blur_ksize + 1
    k = max(3, k)
    bgr_blur = cv2.GaussianBlur(bgr, (k, k), 0)
    bg_blur = cv2.cvtColor(bgr_blur, cv2.COLOR_BGR2RGB)

    # ----- Foreground: fit -----
    scale_fg = min(tw / W, th / H)
    new_w = max(1, int(round(W * scale_fg)))
    new_h = max(1, int(round(H * scale_fg)))
    fg = cv2.resize(rgb_arr, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

    # Tính vị trí dán fg và clamp nếu cần
    x_off = (tw - new_w) // 2
    y_off = (th - new_h) // 2

    # Vùng đích (clamp)
    dx0 = max(0, x_off); dy0 = max(0, y_off)
    dx1 = min(tw, x_off + new_w); dy1 = min(th, y_off + new_h)
    dst_w = max(0, dx1 - dx0); dst_h = max(0, dy1 - dy0)

    # Vùng nguồn tương ứng
    sx0 = max(0, -x_off); sy0 = max(0, -y_off)
    sx1 = sx0 + dst_w;    sy1 = sy0 + dst_h

    frame = bg_blur.copy()
    if dst_w > 0 and dst_h > 0:
        frame[dy0:dy1, dx0:dx1] = fg[sy0:sy1, sx0:sx1]

    # # Crop tâm về đúng (tw, th)
    # x0 = (bg_w - tw) // 2 if (bg_w - tw) > 0 else 0
    # y0 = (bg_h - th) // 2 if (bg_h - th) > 0 else 0
    # bg_crop = bg[y0:y0+th, x0:x0+tw].copy()

    # # Blur BG (chuyển RGB->BGR cho cv2, xong lại về RGB)
    # bgr = cv2.cvtColor(bg_crop, cv2.COLOR_RGB2BGR)
    # bgr_blur = cv2.GaussianBlur(bgr, (blur_ksize, blur_ksize), 0)
    # bg_blur = cv2.cvtColor(bgr_blur, cv2.COLOR_BGR2RGB)

    # # ----- Foreground: fit -----
    # scale_fg = min(tw / W, th / H)
    # new_w, new_h = int(W * scale_fg), int(H * scale_fg)
    # fg = cv2.resize(rgb_arr, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

    # # Paste FG vào BG giữa khung
    # x_off = (tw - new_w) // 2
    # y_off = (th - new_h) // 2
    # frame = bg_blur.copy()
    # frame[y_off:y_off+new_h, x_off:x_off+new_w] = fg

    return frame

def build_frame_clip_from_image(path: str, duration: float, target_size=TARGET_SIZE, blur_ksize=BLUR_KSIZE) -> ImageClip:
    """
    Đọc ảnh, sửa EXIF orientation, (tuỳ chọn) ép dọc, 
    tạo frame 9:16 có nền mờ và ảnh fit giữa → trả về ImageClip(duration=...)
    """
    # Đọc bằng PIL để giữ EXIF + sửa orientation
    with Image.open(path) as im:
        im = correct_exif_orientation(im)
        im = ensure_portrait(im)

        rgb = pil_to_rgb_array(im)
        frame = make_blurred_bg_and_foreground(rgb, target_size=target_size, blur_ksize=blur_ksize)

    # Tạo clip từ numpy array (RGB)
    return ImageClip(frame).set_duration(duration)

# ------------------ CHÍNH ------------------
def images_to_video_portrait(folder: str, seconds_per_image: float = DEFAULT_DURATION, fps: int = FPS):
    if not os.path.isdir(folder):
        print(f"❌ Thư mục không tồn tại: {folder}")
        return

    # Lấy danh sách ảnh hợp lệ + sort tự nhiên
    img_files = [
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith(VALID_EXTS)
    ]
    if not img_files:
        print("❌ Không tìm thấy ảnh hợp lệ trong thư mục.")
        return

    img_files.sort(key=lambda p: natural_key(os.path.basename(p)))
    print(f"▶️  Ảnh hợp lệ: {len(img_files)} | Thời lượng mỗi ảnh = {seconds_per_image:.3f}s | 9:16 + BG blur")

    # Tạo clips từng ảnh
    clips = []
    for path in img_files:
        try:
            clip = build_frame_clip_from_image(path, duration=seconds_per_image, target_size=TARGET_SIZE, blur_ksize=BLUR_KSIZE)
            clips.append(clip)
        except Exception as e:
            print(f"⚠️ Bỏ qua ảnh lỗi: {path} ({e})")

    if not clips:
        print("❌ Không tạo được clip nào từ các ảnh.")
        return

    # Ghép (compose để an toàn dù khung đã đồng nhất)
    video = concatenate_videoclips(clips, method="compose")

    # File đầu ra trong chính thư mục ảnh
    out_name = f"{os.path.basename(os.path.abspath(folder))}_916.mp4"
    out_path = os.path.join(folder, out_name)
    print(f"💾 Xuất video: {out_path}")

    # Spinner trong khi ghi video
    done = False
    spin_thread = threading.Thread(target=spinner, args=("🎬 Đang kết xuất video (9:16, BG blur)",))
    spin_thread.daemon = True
    spin_thread.start()

    def write_video():
        nonlocal done
        video.write_videofile(
            out_path,
            fps=fps,
            codec="libx264",
            bitrate="6000k",
            audio=False,
            logger=None
        )
        done = True

    writer = threading.Thread(target=write_video)
    writer.start()

    while not done:
        time.sleep(0.2)

    sys.stdout.write("\r✅ Hoàn tất xuất video.                 \n")
    sys.stdout.flush()

if __name__ == "__main__":
    folder = input("Thư mục chứa ảnh: ").strip()
    dur = input(f"Thời lượng mỗi ảnh (giây, mặc định {DEFAULT_DURATION}): ").strip()
    seconds = float(dur) if dur else DEFAULT_DURATION
    images_to_video_portrait(folder, seconds_per_image=seconds, fps=FPS)
