import os
import shutil
import subprocess
import sys

# Cài đặt nudenet nếu chưa có
try:
    from nudenet import NudeDetector
except ImportError:
    print("📦 'nudenet' chưa được cài. Đang tiến hành cài đặt...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "nudenet"])
    from nudenet import NudeDetector

import pandas as pd

def classify_images_in_folder(input_folder, output_mode='csv', output_path='output.csv'):
    detector = NudeDetector()
    results = []

    for filename in os.listdir(input_folder):
        if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            file_path = os.path.join(input_folder, filename)
            detections = detector.detect(file_path)

            # Nếu có vùng nhạy cảm -> unsafe, nếu không -> safe
            label = 'unsafe' if detections else 'safe'
            results.append({'filename': filename, 'label': label})

            if output_mode == 'folders':
                target_dir = os.path.join(input_folder, label)
                os.makedirs(target_dir, exist_ok=True)
                shutil.copy(file_path, os.path.join(target_dir, filename))

    if output_mode == 'csv':
        df = pd.DataFrame(results)
        df.to_csv(output_path, index=False)
        print(f"✅ CSV đã được lưu tại: {output_path}")
    else:
        print(f"✅ Ảnh đã được phân loại vào thư mục 'safe' và 'unsafe' trong: {input_folder}")

# 👉 Ví dụ sử dụng:
# classify_images_in_folder("path/to/images", output_mode="csv", output_path="results.csv")
# classify_images_in_folder("path/to/images", output_mode="folders")
if __name__ == "__main__":
    input_folder = input("👉👉 Input the image directory: ")
    #Print to choose option 1: csv mode, 2: move folder
    print("Choose option mode:")
    print("1: Save as csv file")
    print("2: Move folder safe/unsafe")
    option = input("👉👉 Option: ")
    if option == "1":
        classify_images_in_folder(input_folder, output_mode="csv", output_path="output.csv")
    elif option == "2":
        classify_images_in_folder(input_folder, output_mode="folders")
    else:
        print("Invalid option. Please choose 1 or 2.")
    
    