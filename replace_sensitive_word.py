import json
import os
from PIL import Image, PngImagePlugin

# Danh sách từ nhạy cảm và từ thay thế (rút gọn mẫu)
sensitive_terms = {
    "handsome man": "aesthetic_male_form",
    "shirtless": "tasteful_sensuality",
    "penis": "male anatomy",
    "testicles": "male anatomy",
    "vagina": "female anatomy",
    "boobs": "bosom",
    "nipples": "torso detail",
    "sexy pose": "suggestive composition",
    "underwear": "delicate attire",
    "nude": "undraped figure",
    "topless": "undraped torso",
    "pussy": "female anatomy",
    "cock": "male anatomy",
    "tits": "bust",
    "naked": "bare-skinned",
    "blowjob": "male intimate pleasure"
}

def load_json(path_json:str, sensitive_terms:dict):
    with open(path_json, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    sensitive_terms.update(json_data)
    return sensitive_terms
    
# Lưu thành file JSON
json_path = r"sensitive_prompt_keywords_v2.json"
# with open(json_path, "r", encoding="utf-8") as f:
#     json.dump(sensitive_terms, f, ensure_ascii=False, indent=2)
if os.path.exists(json_path):
    load_json(json_path, sensitive_terms)

# Hàm thay từ trong prompt
def sanitize_positive_prompt(prompt_text: str) -> str:
    for word, replacement in sensitive_terms.items():
        prompt_text = prompt_text.replace(word, replacement)
    return prompt_text

# Hàm xử lý metadata của ảnh PNG
def process_png_metadata(image_path: str, output_path: str = None):
    with Image.open(image_path) as im:
        metadata = im.info

        if "parameters" not in metadata:
            print(f"No 'parameters' metadata in {image_path}")
            return

        original_params = metadata["parameters"]
        lines = original_params.split("Negative prompt:")
        if not lines:
            return

        # Xử lý dòng đầu (positive prompt)
        positive_prompt = lines[0]
        sanitized_prompt = sanitize_positive_prompt(positive_prompt)

        # Giữ nguyên cấu trúc
        modified_parameters = " ".join([sanitized_prompt] + ["Negative prompt:"] + lines[1:])

        # Ghi metadata mới
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("parameters", modified_parameters)

        # Đặt tên file mới nếu không ghi đè
        output_path = output_path or image_path #.replace(".png", "_sanitized.png")
        im.save(output_path, pnginfo=pnginfo)
        print(f"Sanitized: {os.path.basename(output_path)}")

def main(path_folder:str, replace = True):
    if not os.path.exists(path_folder):
        print(f"Folder not found: {path_folder}")
        return
    if not os.path.exists(json_path):
        print(f"JSON file not found: {json_path}")
        return
    load_json(json_path, sensitive_terms)
    if replace:
        if not os.path.exists(os.path.join(path_folder, "sanitized")):
            os.makedirs(os.path.join(path_folder, "sanitized"))
    print(f"Processing images in folder: {path_folder}")
    file_names = [filename for filename in os.listdir(path_folder) if filename.lower().endswith(".png")]
    
    for file_name in file_names:
        image_path = os.path.join(path_folder, file_name)
        if not replace:
            process_png_metadata(image_path)
        else:
            process_png_metadata(image_path, os.path.join(path_folder, "sanitized", file_name))
        print(f"Processed image: {file_name}")
    print("All images processed.")

if __name__ == "__main__":
    folder_path = input("Enter the folder path: ")
    replace = input("New folder? Y/N:")
    if replace == "Y":
        main(folder_path, True)
    else:
        main(folder_path, False)




