from PIL import Image, ImageFilter
from enum import Enum
from typing import Tuple

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
    
# --- Cách sử dụng ---
# composer = ImageComposer(blur_radius=50)
# result = composer.process(
#     "image.jpg", 
#     "logo.png", 
#     aspect_ratio=(9, 16), 
#     logo_pos=LogoPosition.TOP_RIGHT
# )
# result.show()