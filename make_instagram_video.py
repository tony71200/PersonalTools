# Requirements:
# opencv-python==4.8.0
# numpy==1.26.4
# moviepy==1.0.3

import os
import cv2
import numpy as np
from moviepy.editor import *
import re
import shutil

class VideoGenerator:
    def __init__(self, logo_image_path):
        if not os.path.exists(logo_image_path):
            raise ValueError(f"❌ Không tìm thấy file logo: {logo_image_path}")
        self.logo_image_path = logo_image_path
        self.temp_dir = "temp_processed"

    @staticmethod
    def _extract_number(filename):
        match = re.search(r'\\d+', filename)
        return int(match.group()) if match else -1

    def _make_blurred_background(self, image_path, target_size=(1080, 1920)):
        img = cv2.imread(image_path)
        if img is None:
            print(f"⚠️ Không thể đọc file ảnh: {image_path}")
            return None, None

        h, w, _ = img.shape
        target_w, target_h = target_size

        scale = min(target_w / w, target_h / h)
        new_w, new_h = int(w * scale), int(h * scale)
        resized_img = cv2.resize(img, (new_w, new_h))

        background = cv2.resize(img, target_size)
        background = cv2.GaussianBlur(background, (101, 101), 0)

        x_offset = (target_w - new_w) // 2
        y_offset = (target_h - new_h) // 2
        background[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized_img

        temp_path = os.path.join(self.temp_dir, os.path.basename(image_path))
        cv2.imwrite(temp_path, background)
        return temp_path, (x_offset, y_offset, new_w, new_h)

    def _cleanup_temp_dir(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            print("🗑️  Đã dọn dẹp thư mục tạm.")

    def create_video(self, image_folder, output_path, total_duration=30, logo_size=(150, 150)):
        valid_ext = (".jpg", ".jpeg", ".png", ".bmp")
        if not os.path.isdir(image_folder):
            print(f"❌ Thư mục ảnh không tồn tại: {image_folder}")
            return

        image_files = sorted(
            [os.path.join(image_folder, f) for f in os.listdir(image_folder) if f.lower().endswith(valid_ext)],
            key=lambda x: self._extract_number(os.path.basename(x))
        )

        if len(image_files) < 7:
            print(f"ℹ️  Bỏ qua thư mục '{os.path.basename(image_folder)}' vì có ít hơn 7 ảnh.")
            return

        print(f"▶️  Bắt đầu xử lí {len(image_files)} ảnh từ thư mục '{os.path.basename(image_folder)}'...")
        
        os.makedirs(self.temp_dir, exist_ok=True)
        try:
            duration_per_image = total_duration / len(image_files)
            clips = []
            positions = []

            for img_path in image_files:
                processed_path, content_box = self._make_blurred_background(img_path)
                if processed_path:
                    clip = ImageClip(processed_path).set_duration(duration_per_image)
                    clips.append(clip)
                    positions.append(content_box)
            
            if not clips:
                print("❌ Không tạo được clip nào từ các ảnh đã cho.")
                return

            slideshow = concatenate_videoclips(clips)
            logo_img = (ImageClip(self.logo_image_path, transparent=True)
                        .resize(height=logo_size[1])
                        .set_duration(total_duration))

            x_offset, y_offset, _, content_h = positions[0]
            logo_position = (x_offset + 10, y_offset + content_h - logo_size[1] - 10)
            logo_img = logo_img.set_position(logo_position)

            final = CompositeVideoClip([slideshow, logo_img], size=(1080, 1920)).set_duration(total_duration)
            final.write_videofile(output_path, fps=30, codec="libx264", bitrate="6000k", audio=False, logger=None)
            print(f"✅ Video đã được tạo thành công: {output_path}")

        finally:
            self._cleanup_temp_dir()

def main_single():
    print("🎬 Tạo video 9:16 từ một thư mục ảnh và overlay logo")
    images_folder = input("Thư mục chứa ảnh: ").strip()
    logo_image_path = input("Đường dẫn file logo: ").strip()
    output_path = input("Tên video đầu ra (mặc định: final_output.mp4): ").strip()
    
    if not output_path:
        output_path = "final_output.mp4"
    if not os.path.isabs(output_path):
         output_path = os.path.join(os.path.dirname(images_folder) or '.', output_path)

    try:
        generator = VideoGenerator(logo_image_path)
        generator.create_video(images_folder, output_path)
    except ValueError as e:
        print(e)


def main_folder():
    print("🗂️  Tạo hàng loạt video 9:16 từ các thư mục con")
    base_folder = input("Thư mục cha chứa các thư mục ảnh: ").strip()
    logo_image_path = input("Đường dẫn file logo: ").strip()
    
    if not os.path.isdir(base_folder):
        print("❌ Thư mục cha không tồn tại.")
        return

    try:
        generator = VideoGenerator(logo_image_path)
        subfolders = [f.path for f in os.scandir(base_folder) if f.is_dir()]
        print(f"Tìm thấy {len(subfolders)} thư mục con để xử lý.")
        for folder in subfolders:
            output_filename = f"{os.path.basename(folder)}.mp4"
            output_path = os.path.join(base_folder, output_filename)
            generator.create_video(folder, output_path)
    except ValueError as e:
        print(e)


if __name__ == "__main__":
    print("Chọn chế độ chạy:")
    print("1. Xử lý một thư mục duy nhất")
    print("2. Xử lý hàng loạt thư mục con trong một thư mục cha")
    choice = input("Lựa chọn của bạn (1 hoặc 2): ").strip()

    if choice == '1':
        main_single()
    elif choice == '2':
        main_folder()
    else:
        print("Lựa chọn không hợp lệ.")
