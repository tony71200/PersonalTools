import os
import sys
import shutil
from PIL import Image
from PIL.PngImagePlugin import PngImageFile
from tqdm import tqdm
import re

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
        "model_hash": "",
        "model_name": "",
        "lora_hashes": []
    }
    # Lấy model hash
    match_hash = re.search(r"Model hash:\s*([0-9a-fA-F]+)", raw_metadata)
    if match_hash:
        result["model_hash"] = match_hash.group(1)
    # Lấy model name (nếu có)
    match_name = re.search(r"Model:\s*([^\n,]+)", raw_metadata)
    if match_name:
        result["model_name"] = match_name.group(1).strip()
    # Lấy đoạn chứa Lora hashes
    lora_section = None
    lora_section_match = re.search(r"Lora hashes?:\s*(.*?)(?:\n\w|$)", raw_metadata, re.DOTALL | re.IGNORECASE)
    if lora_section_match:
        lora_section = lora_section_match.group(1)
    if lora_section:
        lora_pattern = re.compile(r'"([\w\- .]+): ([0-9a-fA-F]{10,})"')
        lora_hashes = lora_pattern.findall(lora_section)
        result["lora_hashes"] = [f"{name.strip()}:{hash.strip()}" for name, hash in lora_hashes]
    return result

def find_images(root_folder):
    image_exts = ('.png',)
    image_files = []
    for dirpath, _, filenames in os.walk(root_folder):
        for fname in filenames:
            if fname.lower().endswith(image_exts):
                image_files.append(os.path.join(dirpath, fname))
    return image_files

def get_model_lora_info(img_path):
    ext = os.path.splitext(img_path)[1].lower()
    if ext == ".png":
        raw_metadata = extract_png_info(img_path)
        if raw_metadata:
            meta = parse_metadata(raw_metadata)
            return meta
    return {"model_hash": "", "model_name": "", "lora_hashes": []}

def choose_copy_move():
    while True:
        choice = input("Bạn muốn copy hay move ảnh? (c/m): ").strip().lower()
        return choice == "c"
        print("Lựa chọn không hợp lệ. Vui lòng nhập 'c' để copy hoặc 'm' để move.")

def main():
    src_folder = input("Nhập đường dẫn folder ảnh: ").strip()
    if not os.path.isdir(src_folder):
        print("Thư mục không tồn tại.")
        sys.exit(1)

    print("Chọn chế độ lọc:")
    print("1. Lọc theo model")
    print("2. Lọc theo LoRA")
    while True:
        mode = input("Nhập lựa chọn (1 hoặc 2): ").strip()
        if mode in ("1", "2"):
            break
        print("Lựa chọn không hợp lệ.")

    print("Đang tìm ảnh...")
    images = find_images(src_folder)
    print(f"Tìm thấy {len(images)} ảnh.")

    # Thu thập metadata
    model_to_images = {}
    model_info_dict = {}
    lora_to_images = {}
    lora_info_dict = {}
    for img_path in tqdm(images, desc="Đang xử lý ảnh"):
        meta = get_model_lora_info(img_path)
        model_hash = meta["model_hash"]
        model_name = meta["model_name"]
        lora_hashes = meta["lora_hashes"]
        # Model
        if model_hash:
            model_to_images.setdefault(model_hash, []).append(img_path)
            if model_hash not in model_info_dict:
                model_info_dict[model_hash] = model_name
        # LoRA
        for lora in lora_hashes:
            lora_to_images.setdefault(lora, []).append(img_path)
            if lora not in lora_info_dict:
                lora_info_dict[lora] = lora

    if mode == "1":
        if not model_to_images:
            print("Không tìm thấy model hash nào trong metadata ảnh.")
            sys.exit(0)
        print("Danh sách model hash:")
        model_list = list(model_to_images.keys())
        for idx, model in enumerate(model_list, 1):
            model_name = model_info_dict.get(model, "")
            if model_name:
                print(f"{idx}. {model} | {model_name} ({len(model_to_images[model])} ảnh)")
            else:
                print(f"{idx}. {model} ({len(model_to_images[model])} ảnh)")
        print(f"{idx+1}. Chọn tất cả (copy/ move tất cả ảnh)")
        choice_all = False
        while True:
            try:
                choice = int(input("Chọn số thứ tự model muốn copy: "))
                if 1 <= choice <= len(model_list):
                    break
                elif choice == 0:
                    sys.exit(0)
                elif choice == len(model_list) + 1:
                    choice_all = True
                    break
                else:
                    print("Số không hợp lệ.")
            except ValueError:
                print("Vui lòng nhập số.")
        if choice_all:
            selected_model = None
            print("Bạn đã chọn tất cả các model.")
            model_list = list(model_to_images.keys())
            dest_folder = input("Nhập đường dẫn folder lưu ảnh: ").strip()
            os.makedirs(dest_folder, exist_ok=True)
            cpy_mv_mode = choose_copy_move()
            ## Tạo các folder con cho từng model theo format model_hash_model_name
            for model in model_list:
                model_name = model_info_dict.get(model, "unknown_model")
                model_folder = f"{model}_{model_name}".replace(" ", "_").replace("/", "_")
                model_dest_folder = os.path.join(dest_folder, model_folder)
                os.makedirs(model_dest_folder, exist_ok=True)
                
                print(f"Đang {'copy' if cpy_mv_mode else 'move'} {len(model_to_images[model])} ảnh cho model {model} sang {model_dest_folder} ...")
                for img_path in tqdm(model_to_images[model], desc=f"Đang {'copy' if cpy_mv_mode else 'move'} ảnh cho model {model}"):
                    image_dest_path = os.path.join(model_dest_folder, os.path.basename(img_path))
                    if cpy_mv_mode:
                        shutil.copy2(img_path, image_dest_path)
                    else:
                        shutil.move(img_path, image_dest_path)
                        
        else:
            selected_model = model_list[choice - 1]
            dest_folder = input("Nhập đường dẫn folder lưu ảnh: ").strip()
            
            # model_name = model_info_dict.get(model, "unknown_model")
            model_name = model_info_dict.get(selected_model, "unknown_model")
            model_folder = f"{model}_{model_name}".replace(" ", "_")
            model_dest_folder = os.path.join(dest_folder, model_folder)
            os.makedirs(model_dest_folder, exist_ok=True)
            cpy_mv_mode = choose_copy_move()
            # print(f"Đang copy {len(model_to_images[selected_model])} ảnh sang {dest_folder} ...")
            for img_path in tqdm(model_to_images[selected_model], desc=f"Đang {'copy' if cpy_mv_mode else 'move'} ảnh"):
                image_dest_path = os.path.join(model_dest_folder, os.path.basename(img_path))
                if cpy_mv_mode:
                    shutil.copy2(img_path, image_dest_path)
                else:
                    shutil.move(img_path, image_dest_path)
            print("Hoàn thành.")
    else:
        if not lora_to_images:
            print("Không tìm thấy LoRA nào trong metadata ảnh.")
            sys.exit(0)
        print("Danh sách LoRA:")
        lora_list = list(lora_to_images.keys())
        for idx, lora in enumerate(lora_list, 1):
            print(f"{idx}. {lora} ({len(lora_to_images[lora])} ảnh)")
        print(f"{idx+1}. Chọn tất cả (copy tất cả ảnh)")
        choice_all = False
        while True:
            try:
                choice = int(input("Chọn số thứ tự LoRA muốn copy: "))
                if 1 <= choice <= len(lora_list):
                    break
                elif choice == 0:
                    sys.exit(0)
                elif choice == len(lora_list) + 1:
                    choice_all = True
                    break
                else:
                    print("Số không hợp lệ.")
            except ValueError:
                print("Vui lòng nhập số.")
        if choice_all:
            selected_lora = None
            print("Bạn đã chọn tất cả các LoRA.")
            lora_list = list(lora_to_images.keys())
            dest_folder = input("Nhập đường dẫn folder lưu ảnh: ").strip()
            os.makedirs(dest_folder, exist_ok=True)
            cpy_mv_mode = choose_copy_move()
            ## Tạo các folder con cho từng LoRA theo format <Tên Lora>_<hash>
            for lora in lora_list:
                lora_folder = lora.replace(":", "_").replace(" ", "_").replace("/", "_")
                lora_dest_folder = os.path.join(dest_folder, lora_folder)
                os.makedirs(lora_dest_folder, exist_ok=True)
                
                print(f"Đang {'copy' if cpy_mv_mode else 'move'} {len(lora_to_images[lora])} ảnh cho LoRA {lora} sang {lora_dest_folder} ...")
                for img_path in tqdm(lora_to_images[lora], desc=f"Đang {'copy' if cpy_mv_mode else 'move'} ảnh cho {lora}"):
                    image_dest_path = os.path.join(lora_dest_folder, os.path.basename(img_path))
                    if cpy_mv_mode:
                        shutil.copy2(img_path, image_dest_path)
                    else:
                        shutil.move(img_path, image_dest_path)
        else:
            selected_lora = lora_list[choice - 1]
            dest_folder = input("Nhập đường dẫn folder lưu ảnh: ").strip()
            os.makedirs(dest_folder, exist_ok=True)
            cpy_mv_mode = choose_copy_move()
            print(f"Đang {'copy' if cpy_mv_mode else 'move'} {len(lora_to_images[selected_lora])} ảnh sang {dest_folder} ...")
            for img_path in tqdm(lora_to_images[selected_lora], desc=f"Đang {'copy' if cpy_mv_mode else 'move'} ảnh"):
                image_dest_path = os.path.join(dest_folder, os.path.basename(img_path))
                if cpy_mv_mode:
                    shutil.copy2(img_path, image_dest_path)
                else:
                    shutil.move(img_path, image_dest_path)
            print("Hoàn thành.")

if __name__ == "__main__":
    main()
