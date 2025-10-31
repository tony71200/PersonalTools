# arrange_img_v2.py
import os
import re
from PIL import Image
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
import pandas as pd
from collections import Counter, defaultdict
import math
import shutil
from tqdm import tqdm
from enum import Enum

# ========= Text cleaning & metadata parsing =========

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

# expand comma-joined strings into individual tokens
for word in list(remove_word_list):
    if len(word.split(',')) > 1:
        remove_word_list.remove(word)
        remove_word_list.extend([p.strip() for p in word.split(',')])

class SocialType(Enum):
    civitai = 1
    instagram = 2
    custom = 3  # NEW

SOCIAL_CONFIG = {
    SocialType.civitai: 20,
    SocialType.instagram: 15,
    SocialType.custom: 20,   # fixed by requirement
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
    # (giữ nguyên ý tưởng parse)  ─ tham chiếu code gốc
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
    # return re.sub(r"[^a-zA-Z\s,.]", " ", text)
    # giữ chữ, số, khoảng trắng, dấu , .  (đổi về space cho ký tự lạ)
    text = re.sub(r"[^0-9A-Za-z\s,\.]", " ", text)
    # gộp khoảng trắng
    return re.sub(r"\s+", " ", text).strip()

def remove_lora_tags(prompt_text):
    cleaned_text = re.sub(r"<lora:[^>]+>,", " ", prompt_text)
    cleaned_text = re.sub(r"\bBREAK\b", " ", cleaned_text)
    return re.sub(r"\s+", " ", cleaned_text).strip()

def remove_word(text, remove_word_list=remove_word_list):
    cleaned_text = remove_lora_tags(text)
    parts = [p.strip() for p in cleaned_text.split(",")]
    cleaned_parts = []
    for p in parts:
        # print(p in remove_word_list)
        if not any(p in word for word in remove_word_list):
            cleaned_parts.append(p)
    # cleaned_parts = [p for p in parts if not any(word in p for word in remove_word_list)]
    cleaned_text = ", ".join(cleaned_parts)
    return clean_text_keep_comma_dot(cleaned_text)

# ========= IO & scheduling =========

def process_images(folder_path):
    metadata_collection = []
    file_list = [f for f in os.listdir(folder_path) if f.lower().endswith(".png")]
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
            slots = [(day, idx + 1) for day in range(1, days + 1) for idx in range(posts_per_day)]
            return len(slots), slots

        elif social_type == SocialType.civitai:
            # Giữ nguyên kiểu hỏi “khung giờ bắt đầu/kết thúc + giờ thực tế bắt đầu”
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
                    hour12 = hour if hour <= 12 else hour - 12
                    folder_times.append((day, f"{suffix}{hour12:02}"))
            return len(folder_times), folder_times

        else:  # SocialType.custom
            # Mặc định 4 slot / ngày: 06, 10, 14, 18
            days = int(input("Số ngày muốn post (Custom): "))
            fixed_hours = [6, 10, 14, 18]
            folder_times = []
            for day in range(1, days + 1):
                for hour in fixed_hours:
                    suffix = "am" if hour < 12 else "pm"
                    hour12 = hour if hour <= 12 else hour - 12
                    folder_times.append((day, f"{suffix}_{hour12:02}"))
            return len(folder_times), folder_times

    except ValueError:
        print("⚠️ Vui lòng nhập đúng định dạng số.")
        return 0, []

# ========= Clustering with constraints (min=4, max=20) =========

def vectorize_prompts_for_clustering(items):
    texts = []
    valid_idx = []  # map về index của metadata_collection

    for i, it in enumerate(items):
        raw_pos = it.get("positive_prompt", "") or ""
        pos = remove_word(raw_pos)  # đã clean theo list + lora
        pos = pos.strip()

        mh  = (it.get("model_hash") or "").strip()
        mh_tok = f"mh_{mh}" if mh else ""

        # Fallback kế tiếp nếu sau clean mà rỗng
        if not pos and mh_tok:
            pos = mh_tok

        if not pos:
            # fallback nữa: dùng tên file (stem) để còn token hóa được
            fname = (it.get("filename") or "").strip()
            stem = os.path.splitext(fname)[0]
            stem = re.sub(r"[^0-9A-Za-z]+", " ", stem).strip()
            pos = stem

        # nếu vẫn rỗng thì bỏ qua doc này
        if pos:
            texts.append(pos)
            valid_idx.append(i)

    if not texts:
        raise ValueError(
            "Không còn document hợp lệ để vectorize. Có thể do prompt rỗng hoặc bị filter quá tay. "
            "Hãy kiểm tra remove_word_list hoặc đảm bảo ảnh có metadata 'parameters'."
        )

    # TF-IDF bớt khắt khe, chấp nhận token chữ/số/_
    vec = TfidfVectorizer(
        stop_words="english",
        token_pattern=r"(?u)\b\w+\b",
        strip_accents="unicode",
        max_features=8000,
        lowercase=True,
    )
    X = vec.fit_transform(texts)
    return X, valid_idx

def choose_k_range(n_samples, max_cluster_slots, min_per=4, max_per=20):
    k_min = max(1, math.ceil(n_samples / max_per))
    k_max_by_size = max(1, n_samples // min_per)
    k_max = max(1, min(max_cluster_slots, k_max_by_size))
    if k_min > k_max:
        k_min, k_max = k_max, k_min  # swap fallback
    return k_min, k_max

def score_partition(counts, min_per=4, max_per=20):
    # penalty-based scoring: 0 is perfect
    too_small = sum(max(0, min_per - c) for c in counts if c < min_per)
    too_big   = sum(c - max_per for c in counts if c > max_per)
    spread    = (max(counts) - min(counts)) if counts else 0
    # weight big violations heavier
    return 3*too_big + 2*too_small + 0.2*spread

def run_kmeans_with_constraints(X, k_min, k_max, min_per=4, max_per=20, random_state=123):
    best = None
    for k in range(k_min, k_max + 1):
        km = KMeans(n_clusters=k, random_state=random_state, n_init=25)
        labels = km.fit_predict(X)
        counts = list(Counter(labels).values())
        penalty = score_partition(counts, min_per, max_per)
        if best is None or penalty < best[0]:
            best = (penalty, labels)
            if penalty == 0:  # perfect fit
                break
    return best[1] if best else KMeans(n_clusters=2, random_state=42, n_init=25).fit_predict(X)

def merge_small_clusters(df, min_per=4, max_per=20):
    """
    - Gom các cụm có size < min_per lại với nhau, mỗi bin ≤ max_per.
    - Nếu còn bin < min_per, mượn mẫu từ cụm lớn (>min_per) lân cận.
    Trả về: series nhãn mới (0..M-1), danh sách nhóm.
    """
    groups = []
    small_bins = []
    large_bins = []

    # gom theo cluster hiện tại
    for cid, g in df.groupby("cluster"):
        idxs = list(g.index)
        if len(idxs) < min_per:
            small_bins.append(idxs)
        elif len(idxs) <= max_per:
            groups.append(idxs)
        else:
            # tách cụm quá lớn thành các mảnh ≤max_per
            for i in range(0, len(idxs), max_per):
                chunk = idxs[i:i+max_per]
                groups.append(chunk)

    # pack các cụm nhỏ vào bin ≤max_per
    buffer = []
    cur = []
    cur_size = 0
    for s in small_bins:
        if cur_size + len(s) <= max_per:
            cur.extend(s)
            cur_size += len(s)
        else:
            if cur:
                buffer.append(cur)
            cur = list(s)
            cur_size = len(s)
    if cur:
        buffer.append(cur)

    # đảm bảo mỗi buffer bin ≥ min_per (nếu thiếu, mượn từ groups lớn)
    def borrow(from_groups, need):
        # mượn rải đều từ các nhóm còn >min_per
        taken = []
        for grp in from_groups:
            while len(grp) > min_per and need > 0:
                taken.append(grp.pop())
                need -= 1
                if need == 0:
                    break
            if need == 0:
                break
        return taken, need

    fixed = []
    for bin_idxs in buffer:
        if len(bin_idxs) < min_per:
            need = min_per - len(bin_idxs)
            taken, remain = borrow(groups, need)
            bin_idxs.extend(taken)
            if remain > 0:
                # vẫn thiếu -> gộp chung với bin kế tiếp hoặc bin nhỏ nhất
                # fallback: nhập vào nhóm nhỏ nhất hiện có
                if fixed:
                    fixed[0].extend(bin_idxs)  # nhập vào nhóm đầu
                elif groups:
                    groups[0].extend(bin_idxs)  # nhập vào nhóm bất kỳ
                else:
                    fixed.append(bin_idxs)  # để nguyên
                continue
        fixed.append(bin_idxs)

    all_groups = groups + fixed
    # reindex labels
    new_labels = pd.Series(index=df.index, dtype=int)
    for i, idxs in enumerate(all_groups):
        new_labels.loc[idxs] = i
    return new_labels, all_groups

# ========= File moving =========

def move_file(filename, src_folder, dest_folder):
    src_path = os.path.join(src_folder, filename)
    dest_path = os.path.join(dest_folder, filename)
    if os.path.exists(src_path):
        shutil.move(src_path, dest_path)

# ========= Main =========

def main():
    folder = input("📁 Nhập đường dẫn thư mục chứa ảnh PNG: ").strip()
    metadata_collection = process_images(folder)
    if not metadata_collection:
        print("❌ Không tìm thấy metadata hợp lệ.")
        return

    print("Chọn nền tảng:")
    print("1: Civitai")
    print("2: Instagram")
    print("3: Custom")  # NEW
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

    # Vector hoá prompt (đã làm sạch) + token model_hash nhẹ
    X, valid_idx = vectorize_prompts_for_clustering(metadata_collection)
    n_samples = X.shape[0]
    if n_samples < 4:
        raise ValueError("Quá ít ảnh hợp lệ sau khi làm sạch (cần >= 4 để gom cụm hợp lệ).")

    k_min, k_max = choose_k_range(n_samples, max_cluster, min_per=2, max_per=20)
    raw_labels = run_kmeans_with_constraints(X, k_min, k_max, min_per=2, max_per=20, random_state=42)

    # gán label cho ONLY những ảnh hợp lệ; ảnh không hợp lệ (nếu còn) cho vào cụm riêng hoặc bỏ qua
    df = pd.DataFrame(metadata_collection)
    df['cluster'] = -1  # default cho ảnh không vectorize được
    for i_local, idx_global in enumerate(valid_idx):
        df.at[idx_global, 'cluster'] = raw_labels[i_local]

    # drop ảnh cluster = -1 (không đủ text để vectorize)
    df = df[df['cluster'] != -1].copy()
    if df.empty:
        raise ValueError("Tất cả ảnh bị loại sau khi vectorize. Kiểm tra lại bước làm sạch prompt.")

    # rồi mới merge_small_clusters như cũ
    new_labels, groups = merge_small_clusters(df, min_per=4, max_per=20)
    df['cluster'] = new_labels

    valid_clusters = df['cluster'].unique().tolist()

    print(f"Tổng số folder được tạo: {len(valid_clusters)} folder")
    # map cụm -> slot lịch (cắt nếu cụm > slot)
    for i, cluster_id in enumerate(valid_clusters):
        if i >= len(folder_meta):
            break
        group = df[df["cluster"] == cluster_id]
        filenames = group["filename"].tolist()

        if social_type == SocialType.instagram:
            day, index = folder_meta[i]
            folder_name = f"Day{day}_{index}"
        elif social_type == SocialType.custom:
            # folder_meta: (day, "am_06"/"am_10"/"pm_02"/"pm_06")
            day, tag = folder_meta[i]
            # chuẩn hoá hiển thị theo yêu cầu "<ngày thứ n>_<am/pm>_<giờ>"
            folder_name = f"Day{day}_{tag}"
        else:  # civitai giữ format cũ "Day<day>_<am/pm><hh>"
            day, hour_tag = folder_meta[i]
            folder_name = f"Day{day}_{hour_tag}"

        folder_path = os.path.join(folder, folder_name)
        os.makedirs(folder_path, exist_ok=True)
        for filename in filenames:
            move_file(filename, folder, folder_path)

        print(f"{folder_path} : {len(filenames)}")

if __name__ == "__main__":
    main()
