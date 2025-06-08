import os
import json
import re
from PIL import Image
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
import numpy as np
import pandas as pd
from collections import Counter
import shutil
from tqdm import tqdm
from enum import Enum

remove_word_list = [
    "masterpiece", 
    "ultra-HD", "cinematic lighting", "photorealistic", 
    "impressionism", "high detail", "depth of field", "blurred background",
    "dramatic lighting", "best quality", "very aesthetic", "8k",
    "realistic", "BREAK",
    "simple_background", "score_9", "score_8_", "score_7_", "score_6_",
    "asianguy, yongdong, taeil, teail, otherguy, neal, nodaeng",
    "short hair, handsome man, light skin, focus male, young man, amazing quality, soft anime style, art painting, fair skin, smooth skin, dynamic emotion, dynamic view, breeze style, boy, male focus, solo, "
]

for word in remove_word_list:
    if len(word.split(',')) > 1:
        remove_word_list.remove(word)
        remove_word_list.extend([p.strip() for p in word.split(',')])

class SocialType(Enum):
    civitai = 1
    instagram = 2
    patreon = 3

SOCIAL_CONFIG = {
    SocialType.civitai: 20,
    SocialType.instagram: 15,
    SocialType.patreon: 40
}

def extract_png_info(png_path):
    try:
        with Image.open(png_path) as img:
            parameters = img.info.get("parameters", "")
            return parameters
    except Exception as e:
        print(f"Error processing {png_path}: {e}")
        return None

def parse_metadata(raw_metadata, image_filename):
    result = {
        "positive_prompt": "",
        "negative_prompt": "",
        "sampler": "",
        "steps": "",
        "cfg_scale": "",
        "seed": "",
        "size": "",
        "model_hash": "",
        "filename": image_filename,
    }

    if "Negative prompt:" in raw_metadata:
        parts = raw_metadata.split("Negative prompt:")
        result["positive_prompt"] = parts[0].strip()
        rest = parts[1]
    else:
        rest = raw_metadata

    lines = rest.splitlines()
    if lines:
        result["negative_prompt"] = lines[0].strip()

    param_line = " ".join(lines[1:])

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

def clean_text_keep_comma_dot(text):
    return re.sub(r"[^a-zA-Z\s,.]", "", text)

def remove_lora_tags(prompt_text):
    cleaned_text = re.sub(r"<lora:[^>]+>,", "", prompt_text)
    cleaned_text = re.sub(r"BREAK", "", cleaned_text)
    return re.sub(r"\s+", " ", cleaned_text).strip()

def remove_word(text, remove_word_list=remove_word_list):
    cleaned_text = remove_lora_tags(text)
    parts = [p.strip() for p in cleaned_text.split(",")]
    cleaned_parts = [p for p in parts if not any(word in p for word in remove_word_list)]
    cleaned_text = ", ".join(cleaned_parts)
    return clean_text_keep_comma_dot(cleaned_text)

def process_images(folder_path):
    metadata_collection = []
    file_list = [filename for filename in os.listdir(folder_path) if filename.lower().endswith(".png")]
    print(f"Found {len(file_list)} images in {folder_path}")
    for file in tqdm(file_list, desc="Processing images", unit="image"):
        full_path = os.path.join(folder_path, file)
        raw = extract_png_info(full_path)
        if raw:
            parsed = parse_metadata(raw, file)
            metadata_collection.append(parsed)
    return metadata_collection

def ask_schedule_and_estimate_folders(social_type):
    try:
        if social_type == SocialType.instagram:
            days = int(input("Bạn muốn post trong bao nhiêu ngày? "))
            posts_per_day = int(input("Số lượng bài đăng mỗi ngày: "))
            return days * posts_per_day, [(day, idx+1) for day in range(1, days+1) for idx in range(posts_per_day)]
        else:
            days = int(input("Bạn muốn post trong bao nhiêu ngày? "))
            start_hour = int(input("Khung giờ bắt đầu trong ngày (ví dụ 6): "))
            end_hour = int(input("Khung giờ kết thúc trong ngày (ví dụ 22): "))
            real_start_hour = int(input("Giờ thực tế bạn muốn bắt đầu post (ví dụ 13): "))

            if not (start_hour <= real_start_hour < end_hour):
                print("⚠️ Giờ bắt đầu post phải nằm trong khoảng thời gian cho phép.")
                return 0, []

            folder_times = []
            for day in range(1, days + 1):
                for hour in range(real_start_hour if day == 1 else start_hour, end_hour):
                    suffix = "am" if hour < 12 else "pm"
                    hour_display = hour if hour <= 12 else hour - 12
                    folder_times.append((day, f"{suffix}{hour_display:02d}"))
            return len(folder_times), folder_times
    except ValueError:
        print("⚠️ Vui lòng nhập đúng định dạng số.")
        return 0, []

def optimized_kmeans(prompts, max_cluster, max_per_cluster):
    vectorizer = TfidfVectorizer(stop_words="english", max_features=2000)
    X = vectorizer.fit_transform(prompts)
    n_samples = X.shape[0]

    for n_clusters in range(max_cluster, 1, -1):
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=25, algorithm='elkan')
        labels = kmeans.fit_predict(X)
        counts = Counter(labels)
        largest_cluster = max(counts.values())
        ungrouped = n_samples - sum(v for v in counts.values() if v <= max_per_cluster)
        if largest_cluster <= max_per_cluster and ungrouped <= 6:
            return labels
    print("⚠️ Không tìm được phân cụm phù hợp, dùng mặc định.")
    kmeans = KMeans(n_clusters=2, random_state=42, n_init=25)
    return kmeans.fit_predict(X)

def move_file(filename, src_folder, dest_folder):
    src_path = os.path.join(src_folder, filename)
    dest_path = os.path.join(dest_folder, filename)
    if os.path.exists(src_path):
        shutil.move(src_path, dest_path)

def main():
    folder = input("📁 Nhập đường dẫn thư mục chứa ảnh PNG: ").strip()
    metadata_collection = process_images(folder)

    print("Chọn nền tảng:")
    print("1: Civitai")
    print("2: Instagram")
    print("3: Patreon")
    try:
        platform_choice = int(input("▶ "))
        social_type = SocialType(platform_choice)
    except (ValueError, KeyError):
        print("❌ Lựa chọn không hợp lệ.")
        return

    max_per_cluster = SOCIAL_CONFIG[social_type]
    max_cluster, folder_meta = ask_schedule_and_estimate_folders(social_type)
    if max_cluster == 0:
        return

    prompts = [item['positive_prompt'] for item in metadata_collection]
    labels = optimized_kmeans(prompts, max_cluster, max_per_cluster)

    df = pd.DataFrame(metadata_collection)
    df['cluster'] = labels

    valid_clusters = df['cluster'].unique()
    summary_rows = [] if social_type == SocialType.patreon else None
    print(f"Tổng số folder được tạo: {len(valid_clusters)} folder")
    for i, cluster_id in enumerate(valid_clusters):
        group = df[df["cluster"] == cluster_id]
        filenames = group["filename"].tolist()

        if i >= len(folder_meta):
            break

        if social_type == SocialType.instagram:
            day, index = folder_meta[i]
            folder_name = f"Day{day}_{index}"
        else:
            day, hour_tag = folder_meta[i]
            folder_name = f"Day{day}_{hour_tag}"

        folder_path = os.path.join(folder, folder_name)
        os.makedirs(folder_path, exist_ok=True)

        for filename in filenames:
            move_file(filename, folder, folder_path)

        print(f"{folder_path} : {len(filenames)}")

        if social_type == SocialType.patreon:
            keywords_summary = remove_word(group["positive_prompt"].tolist()[0])
            filename_joined = "|".join(filenames)
            summary_rows.append({
                "group_index": folder_name,
                "representative_prompt": keywords_summary,
                "image_filenames": filename_joined
            })

    if social_type == SocialType.patreon and summary_rows:
        summary_df = pd.DataFrame(summary_rows)
        out_path = os.path.join(folder, "group_prompt.csv")
        summary_df.to_csv(out_path, index=False)
        print("✅ Done! Summary saved to:", out_path)

if __name__ == "__main__":
    main()
