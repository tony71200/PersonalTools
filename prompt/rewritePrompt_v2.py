
import re
import os
from glob import glob


def parse_block(block):
    """
    Tách prompt, negative prompt, các trường kỹ thuật và kiểm tra block có dòng kết thúc bằng 'tony'.
    Tận dụng technical_fields và tech_pattern để lấy height, width, seed.
    """
    technical_fields = [
        r"Steps\s*:\s*\d+",
        r"Sampler\s*:\s*[^,\n]+",
        r"CFG scale\s*:\s*[^,\n]+",
        r"Size\s*:\s*\d+[xX×]\d+",
        r"Seed\s*:\s*\d+",
        r"Model\s*:\s*[^,\n]+",
        r"Width\s*:\s*\d+",
        r"Height\s*:\s*\d+"
    ]
    tech_pattern = re.compile(r"|".join(technical_fields), re.IGNORECASE)

    lines = [line.strip() for line in block.strip().split("\n") if line.strip()]
    if not lines:
        return "", False

    prompt_lines, negative_lines = [], []
    in_negative = False
    width = height = seed = None
    size_str = None

    for line in lines:
        # Tách negative prompt
        if line.lower().startswith("negative prompt:"):
            in_negative = True
            negative_lines.append(line.split(":", 1)[1].strip())
            continue
        if in_negative:
            if tech_pattern.match(line):
                in_negative = False
            else:
                negative_lines.append(line)
                continue
        # Tách các trường kỹ thuật
        if tech_pattern.match(line):
            # Lấy width
            m = re.search(r"Width\s*:\s*(\d+)", line, re.IGNORECASE)
            if m:
                width = int(m.group(1))
                
            m = re.search(r"Height\s*:\s*(\d+)", line, re.IGNORECASE)
            if m:
                height = int(m.group(1))
                
            m = re.search(r"Size\s*:\s*(\d+)[xX×](\d+)", line, re.IGNORECASE)
            if m:
                width = int(m.group(1))
                height = int(m.group(2))
                
            m = re.search(r"Seed\s*:\s*(\d+)", line, re.IGNORECASE)
            if m:
                seed = int(m.group(1))
                
            continue
        # Prompt lines
        if not line.lower().startswith("negative prompt:"):
            prompt_lines.append(line)

    prompt = " ".join(prompt_lines).replace("  ", " ").replace(" , ", ", ").strip()
    negative_prompt = " ".join(negative_lines).replace("  ", " ").replace(" , ", ",").strip()
    if not negative_prompt:
        negative_prompt = "(1girl, female, woman, vagina,pussy,vaginal,clitoris, beard)"

    # Xử lý size
    if width and height:
        if width > height:
            size_str = "1216x832"
        elif width < height:
            size_str = "832x1216"
        else:
            size_str = "1024x1024"
    else:
        size_str = "832x1216"
    seed_val = seed if seed is not None else -1

    formatted1 = f"{prompt}###{negative_prompt}###{size_str}###{seed_val}"
    formatted2 = f"{prompt}###{negative_prompt}###{size_str}###-1"
    has_tony = any(re.search(r"tony\s*$", line, re.IGNORECASE) for line in lines)
    return formatted1, formatted2, has_tony


def extract_prompt_blocks(filename):
    with open(filename, "r", encoding="utf-8") as f:
        content = f.read()
    blocks = re.split(r"\n\s*\n", content)
    results, safe_results = [], []
    for block in blocks:
        formatted1, formatted2, has_tony = parse_block(block)
        if formatted1:
            results.append(formatted1)
            results.append(formatted2)
            if has_tony:
                safe_results.append(formatted1)
    return results, safe_results


def write_output(prompts, safe_prompts, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        for line in prompts:
            f.write(line + "\n")
    if safe_prompts:
        safe_path = output_path.rsplit(".", 1)[0] + "_safe.txt"
        with open(safe_path, "w", encoding="utf-8") as f:
            for line in safe_prompts:
                f.write(line + "\n")
        print(f"✅ Safe prompts saved to: {safe_path}")
    print(f"✅ Done. Output saved to: {output_path}")

def rewrite_txt2txt(input_path, output_path):
    prompts, safe_prompts = extract_prompt_blocks(input_path)
    write_output(prompts, safe_prompts, output_path)


def rewrite_folder2txt(input_path, output_path):
    result, safe_result = [], []
    for file in glob(os.path.join(input_path, "*.txt")):
        with open(file, "r", encoding="utf-8") as f:
            block = f.read()
        formatted1, formatted2, has_tony = parse_block(block)
        if formatted1:
            result.append(formatted1)
            result.append(formatted2)
            if has_tony:
                safe_result.append(formatted1)
    write_output(result, safe_result, output_path)


if __name__ == "__main__":
    input_path = input("Enter input file: ").strip().strip('"')
    output_path = input("Enter output file: ").strip().strip('"')
    if input_path.endswith(".txt"):
        rewrite_txt2txt(input_path, output_path)
    else:
        rewrite_folder2txt(input_path, output_path)

    
