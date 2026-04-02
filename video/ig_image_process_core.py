from PIL import Image, ImageFilter
from enum import Enum
from typing import Tuple

POST_BASE_SIZE: Tuple[int, int] = (1080, 1350)
POST_BASE_LOGO_SIZE: Tuple[int, int] = (90, 129)
POST_BASE_LOGO_POS: Tuple[int, int] = (60,  POST_BASE_SIZE[1] - 60 -POST_BASE_LOGO_SIZE[0])
OLD_LOGO_COVER_REF_FRAME: Tuple[int, int] = (381, 527)
OLD_LOGO_COVER_REF_SIZE: Tuple[int, int] = (90, 30)

class LogoPosition(Enum):
    TOP_LEFT = 1
    TOP_RIGHT = 2
    BOTTOM_LEFT = 3
    BOTTOM_RIGHT = 4

class ImageComposer:
    def __init__(self, blur_radius: int = 30, blur_downscale: float = 0.1):
        self.blur_radius = blur_radius
        self.blur_downscale = blur_downscale

    def create_blurred_background(self, img: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
        """Tạo nền mờ từ ảnh gốc theo kích thước mục tiêu."""
        tw, th = target_size
        
        # 1. Crop ảnh gốc để lấp đầy khung hình (Center Crop)
        img_aspect = img.width / img.height
        target_aspect = tw / th
        
        if img_aspect > target_aspect:
            # Ảnh gốc rộng hơn -> cắt hai bên
            new_width = int(img.height * target_aspect)
            offset = (img.width - new_width) // 2
            bg_base = img.crop((offset, 0, offset + new_width, img.height))
        else:
            # Ảnh gốc cao hơn -> cắt trên dưới
            new_height = int(img.width / target_aspect)
            offset = (img.height - new_height) // 2
            bg_base = img.crop((0, offset, img.width, offset + new_height))

        # 2. Downscale-Blur-Upscale để tạo hiệu ứng mờ nhanh
        sw, sh = max(10, int(tw * self.blur_downscale)), max(10, int(th * self.blur_downscale))
        bg = bg_base.resize((sw, sh), resample=Image.BOX)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=self.blur_radius * self.blur_downscale))
        return bg.resize((tw, th), resample=Image.LANCZOS)

    def process(
        self, 
        image_path: str, 
        logo_path: str, 
        aspect_ratio: Tuple[int, int] = (9, 16), 
        canvas_width: int = 1080,
        logo_pos: LogoPosition = LogoPosition.TOP_RIGHT,
        margin: Tuple[int, int] = (40, 40)
    ):
        # Đọc ảnh
        main_img = Image.open(image_path).convert("RGBA")
        logo = Image.open(logo_path).convert("RGBA")
        
        # Tính toán kích thước canvas
        canvas_height = int(canvas_width * aspect_ratio[1] / aspect_ratio[0])
        canvas_size = (canvas_width, canvas_height)

        # 1. Tạo nền mờ
        canvas = self.create_blurred_background(main_img, canvas_size)

        # 2. Chèn ảnh chính (Fit vào canvas, giữ nguyên tỉ lệ)
        main_img.thumbnail(canvas_size, Image.LANCZOS)
        # Căn giữa ảnh chính lên canvas
        offset_x = (canvas_width - main_img.width) // 2
        offset_y = (canvas_height - main_img.height) // 2
        canvas.paste(main_img, (offset_x, offset_y), main_img)

        # 3. Tính toán vị trí Logo
        lw, lh = logo.size
        iw, ih = canvas_size
        
        if logo_pos == LogoPosition.TOP_LEFT:
            pos = (margin[0], margin[1])
        elif logo_pos == LogoPosition.TOP_RIGHT:
            pos = (iw - lw - margin[0], margin[1])
        elif logo_pos == LogoPosition.BOTTOM_LEFT:
            pos = (margin[0], ih - lh - margin[1])
        elif logo_pos == LogoPosition.BOTTOM_RIGHT:
            pos = (iw - lw - margin[0], ih - lh - margin[1])

        # 4. Chèn Logo
        canvas.paste(logo, pos, logo)
        
        return canvas


def target_post_size(width: int, height: int) -> Tuple[int, int]:
    """IG post size: portrait -> 4:5 (1080x1350), else -> 1:1 (1080x1080)."""
    return POST_BASE_SIZE if height > width else (1080, 1080)


def scale_logo_rect_for_post(target_size: Tuple[int, int]) -> Tuple[int, int, int, int]:
    """Scale logo size/position from 1080x1350 base into target frame."""
    tw, th = target_size
    t_size_min = min(tw, th)
    b_size_min = min(POST_BASE_SIZE[0], POST_BASE_SIZE[1])

    # sx = tw / POST_BASE_SIZE[0]
    # sy = th / POST_BASE_SIZE[1]
    scaled = t_size_min / b_size_min

    # lw = max(1, int(round(POST_BASE_LOGO_SIZE[0] * sx)))
    # lh = max(1, int(round(POST_BASE_LOGO_SIZE[1] * sy)))
    # lx = max(0, int(round(POST_BASE_LOGO_POS[0] * sx)))
    # ly = max(0, int(round(POST_BASE_LOGO_POS[1] * sy)))
    lw = max(1, int(round(POST_BASE_LOGO_SIZE[0] * scaled)))
    lh = max(1, int(round(POST_BASE_LOGO_SIZE[1] * scaled)))
    lx = max(0, int(round(POST_BASE_LOGO_POS[0] * scaled)))
    ly = max(0, int(round(POST_BASE_LOGO_POS[1] * scaled)))

    lx = min(lx, max(0, tw - lw))
    ly = min(ly, max(0, th - lh))
    return lw, lh, lx, ly


def old_logo_cover_rect_bottom_right(target_size: Tuple[int, int]) -> Tuple[int, int, int, int]:
    """Bottom-right rect to hide old logo for video flow (scaled from 381x527 -> 90x26)."""
    tw, th = target_size
    rw, rh = OLD_LOGO_COVER_REF_FRAME
    cw = max(1, int(round(OLD_LOGO_COVER_REF_SIZE[0] * tw / rw)))
    ch = max(1, int(round(OLD_LOGO_COVER_REF_SIZE[1] * th / rh)))
    cw = min(cw, tw)
    ch = min(ch, th)
    cx = max(0, tw - cw)
    cy = max(0, th - ch)
    return cw, ch, cx, cy


def process_post_image_with_logo(image_path: str, logo_path: str, output_path: str) -> None:
    """Create IG post image with proportional logo.

    Updated 2026-02-28:
    - Chỉ tạo blur background khi ảnh nguồn lệch tỉ lệ target post.
    - Nếu ảnh đã đúng tỉ lệ target thì render trực tiếp (không blur padding).
    """
    composer = ImageComposer(blur_radius=36, blur_downscale=0.12)
    with Image.open(image_path) as src_raw, Image.open(logo_path) as logo_raw:
        src = src_raw.convert("RGBA")
        tw, th = target_post_size(src.width, src.height)

        src_ratio = (src.width / src.height) if src.height else 0.0
        dst_ratio = (tw / th) if th else 0.0
        same_ratio = abs(src_ratio - dst_ratio) <= 0.01

        if same_ratio:
            canvas = src.copy().resize((tw, th), Image.LANCZOS)
        else:
            canvas = composer.create_blurred_background(src.convert("RGB"), (tw, th)).convert("RGBA")
            fg = src.copy()
            fg.thumbnail((tw, th), Image.LANCZOS)
            ox = (tw - fg.width) // 2
            oy = (th - fg.height) // 2
            canvas.paste(fg, (ox, oy), fg)

        logo = logo_raw.convert("RGBA")
        lw, lh, lx, ly = scale_logo_rect_for_post((tw, th))
        logo = logo.resize((lw, lh), Image.LANCZOS)
        canvas.paste(logo, (lx, ly), logo)

        ext = output_path.lower().rsplit(".", 1)[-1] if "." in output_path else "png"
        if ext in {"jpg", "jpeg", "bmp"}:
            canvas.convert("RGB").save(output_path, quality=95)
        else:
            canvas.save(output_path)
    
# --- Cách sử dụng ---
# composer = ImageComposer(blur_radius=50)
# result = composer.process(
#     "image.jpg", 
#     "logo.png", 
#     aspect_ratio=(9, 16), 
#     logo_pos=LogoPosition.TOP_RIGHT
# )
# result.show()
