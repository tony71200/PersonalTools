import os
import csv
import json
import re
from PIL import Image

def extract_png_info(png_path):
    try:
        img = Image.open(png_path)
        parameters = img.info.get("parameters", "")
        return parameters
    except Exception as e:
        print(f"Lỗi khi đọc {png_path}: {e}")
    return None

def parse_metadata(raw_metadata):
    result = {
        "positive_prompt": "",
        "negative_prompt": "",
        "sampler": "",
        "steps": "",
        "cfg_scale": "",
        "seed": "",
        "size": "",
        "model_hash": ""
    }

    if "Negative prompt:" in raw_metadata:
        parts = raw_metadata.split("Negative prompt:")
        result["positive_prompt"] = parts[0].strip()
        rest = parts[1]
    else:
        rest = raw_metadata

    # Lấy negative prompt và các thông số
    lines = rest.splitlines()
    if lines:
        result["negative_prompt"] = lines[0].strip()

    # Ghép lại các dòng còn lại để phân tích tham số
    param_line = " ".join(lines[1:])

    # Regex đơn giản để tách tham số
    matches = {
        "sampler": re.search(r"Sampler:\s*([^,]+)", param_line),
        "steps": re.search(r"Steps:\s*(\d+)", param_line),
        "cfg_scale": re.search(r"CFG scale:\s*([\d.]+)", param_line),
        "seed": re.search(r"Seed:\s*(\d+)", param_line),
        "size": re.search(r"Size:\s*([\dx]+)", param_line),
        "model_hash": re.search(r"Model hash:\s*([0-9a-fA-F]+)", param_line),
    }

    for key, match in matches.items():
        if match:
            result[key] = match.group(1)

    return result

def save_as_txt(png_path, raw_metadata):
    txt_path = os.path.splitext(png_path)[0] + ".txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(raw_metadata)
    print(f"✅ TXT: {os.path.basename(txt_path)}")

def save_as_json(png_path, parsed_metadata):
    json_path = os.path.splitext(png_path)[0] + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(parsed_metadata, f, indent=4, ensure_ascii=False)
    print(f"✅ JSON: {os.path.basename(json_path)}")

def save_all_to_csv(folder_path, metadata_list):
    csv_path = os.path.join(folder_path, "metadata_all.csv")
    keys = ["filename"] + list(metadata_list[0].keys())
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for item in metadata_list:
            writer.writerow(item)
    print(f"\n✅ Đã lưu toàn bộ metadata vào: {csv_path}")

def process_images(folder_path, mode):
    metadata_collection = []
    for file in os.listdir(folder_path):
        if file.lower().endswith(".png"):
            full_path = os.path.join(folder_path, file)
            raw = extract_png_info(full_path)
            if raw:
                parsed = parse_metadata(raw)
                if mode == 1:
                    save_as_txt(full_path, raw)
                elif mode == 2:
                    save_as_json(full_path, parsed)
                elif mode == 3:
                    parsed["filename"] = file
                    metadata_collection.append(parsed)
            else:
                print(f"⚠️ Không có metadata trong {file}")
    if mode == 3 and metadata_collection:
        save_all_to_csv(folder_path, metadata_collection)

# === Menu chương trình ===
if __name__ == "__main__":
    print("📁 Nhập đường dẫn thư mục chứa ảnh PNG:")
    folder = input("▶ ").strip('"')

    print("\n🧩 Chọn chế độ:")
    print("1️⃣  Xuất metadata ra TXT (từng ảnh)")
    print("2️⃣  Xuất metadata ra JSON (từng ảnh)")
    print("3️⃣  Gộp tất cả metadata vào 1 file CSV")

    try:
        mode = int(input("▶ "))
        if mode not in [1, 2, 3]:
            raise ValueError
        process_images(folder, mode)
    except ValueError:
        print("❌ Vui lòng nhập số 1, 2 hoặc 3.")
