"""Gom ảnh vào folder con theo <index> đọc từ tên file.

Format tên file khai báo theo 1 trong 2 kiểu:
  - Mẫu đánh số: 1_2_3_4_56  (mỗi số tra trong ELEMENTS)
  - Template:    {content}_{date}_{trigger}_{index}_{seed}{ext}
                 {*} = bỏ qua 1 đoạn bất kỳ, chữ khác là chữ cố định.
Kiểm tra nhanh: python groupImage_baseonID.py --test
"""
import os
import re
import shutil
import sys

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_FORMAT = "1_2_3_4_56"

# Số trong mẫu đánh số -> tên tag
ELEMENTS = {"1": "content", "2": "date", "3": "trigger", "4": "index", "5": "seed", "6": "ext"}

# Tag -> regex. Phần chữ co giãn (kể cả chứa "_"), phần số làm mốc để tách.
TAG_PATTERNS = {
    "content": r".+?",
    "date": r"\d{6}",               # YYMMDD
    "trigger": r".+?",
    "index": r"\d+",
    "seed": r"-?\d+(?:_\d+)?",      # -980726504406445 hoặc -980726504406445_00001
    "ext": r"\.\w+",
    "*": r".+?",
}

GUIDE = """
Khai báo format tên file (Enter = {default}):
  Kiểu 1 - Mẫu đánh số, mỗi số là 1 phần:
     1 = content  (chữ bất kỳ)     4 = index  (số, dùng để gom)
     2 = date     (YYMMDD, 6 số)   5 = seed   (-số hoặc -số_số)
     3 = trigger  (chữ bất kỳ)     6 = ext    (.png, .jpg...)
     Ví dụ: 1_2_3_4_56
  Kiểu 2 - Template có tên, dùng {{*}} để bỏ qua 1 đoạn, chữ khác giữ nguyên:
     {{content}}_{{date}}_{{trigger}}_{{index}}_{{seed}}{{ext}}
     {{*}}_{{date}}_{{*}}_{{index}}_{{*}}
     Krea2_I2I_v4_{{date}}_{{trigger}}_{{index}}_{{seed}}
  Bắt buộc có index. Mẹo: đặt index cạnh phần số (date/seed) để tách chắc chắn.
""".format(default=DEFAULT_FORMAT)


def mask_to_template(mask):
    """'1_2_3_4_56' -> '{content}_{date}_{trigger}_{index}_{seed}{ext}'."""
    return "".join("{%s}" % ELEMENTS[c] if c in ELEMENTS else c for c in mask)


def compile_format(fmt):
    """Dịch format thành (regex, has_ext). Ném ValueError nếu format sai."""
    template = fmt if "{" in fmt else mask_to_template(fmt)
    parts = re.split(r"\{([^{}]*)\}", template)  # chẵn = chữ cố định, lẻ = tag
    regex, seen = "", set()
    for i, part in enumerate(parts):
        if i % 2 == 0:
            regex += re.escape(part)
        elif part == "*":
            regex += "(?:%s)" % TAG_PATTERNS["*"]
        elif part not in TAG_PATTERNS:
            raise ValueError("Tag không hợp lệ: {%s}. Dùng: %s"
                             % (part, ", ".join("{%s}" % t for t in TAG_PATTERNS)))
        elif part in seen:
            raise ValueError("Tag {%s} xuất hiện hơn 1 lần." % part)
        else:
            seen.add(part)
            regex += "(?P<%s>%s)" % (part, TAG_PATTERNS[part])
    if "index" not in seen:
        raise ValueError("Format phải có {index} (hoặc số 4 trong mẫu đánh số).")
    return re.compile(regex), "ext" in seen


def parse_filename(name, pattern, has_ext):
    """Trả về dict các phần của tên file, hoặc None nếu không khớp."""
    target = name if has_ext else os.path.splitext(name)[0]
    m = pattern.fullmatch(target)
    return m.groupdict() if m else None


def list_images(folder):
    return sorted(f for f in os.listdir(folder)
                  if os.path.isfile(os.path.join(folder, f))
                  and os.path.splitext(f)[1].lower() in IMAGE_EXTS)


def group_files(names, pattern, has_ext):
    """Trả về ({index: [tên file]}, [tên file không khớp])."""
    groups, unmatched = {}, []
    for name in names:
        parts = parse_filename(name, pattern, has_ext)
        if parts:
            groups.setdefault(parts["index"], []).append(name)
        else:
            unmatched.append(name)
    return groups, unmatched


def transfer(folder, groups, move):
    """Copy/move ảnh vào folder/<index>/. Không ghi đè. Trả về (số file xong, list file bỏ qua)."""
    action = shutil.move if move else shutil.copy2
    done, skipped = 0, []
    for index, names in groups.items():
        dest_dir = os.path.join(folder, index)
        os.makedirs(dest_dir, exist_ok=True)
        for name in names:
            dest = os.path.join(dest_dir, name)
            if os.path.exists(dest):
                skipped.append(os.path.join(index, name))
                continue
            action(os.path.join(folder, name), dest)
            done += 1
    return done, skipped


def ask_format(sample):
    """Hỏi format cho tới khi người dùng xác nhận trên file mẫu."""
    print(GUIDE)
    print(f"sample like: {sample}")
    while True:
        fmt = input("Format: ").strip() or DEFAULT_FORMAT
        try:
            pattern, has_ext = compile_format(fmt)
        except ValueError as e:
            print("  Lỗi:", e)
            continue
        parts = parse_filename(sample, pattern, has_ext)
        print("  File mẫu:", sample)
        if parts is None:
            print("  -> Không khớp format này.")
        else:
            print("  -> " + " | ".join("%s=%s" % kv for kv in parts.items()))
        if input("Dùng format này? (Y/n): ").strip().lower() in ("", "y"):
            return pattern, has_ext


def main():
    folder = input("Input Folder Main: ").strip().strip('"')
    if not os.path.isdir(folder):
        print("Không tìm thấy folder:", folder)
        return
    images = list_images(folder)
    if not images:
        print("Folder không có ảnh (%s)." % ", ".join(sorted(IMAGE_EXTS)))
        return

    pattern, has_ext = ask_format(images[0])
    groups, unmatched = group_files(images, pattern, has_ext)
    if not groups:
        print("Không file nào khớp format. Kết thúc.")
        return

    print("\n%d ảnh khớp, chia thành %d nhóm:" % (len(images) - len(unmatched), len(groups)))
    for index in sorted(groups, key=int):
        print("  %s/: %d ảnh" % (index, len(groups[index])))
    if unmatched:
        print("%d ảnh không khớp (giữ nguyên chỗ cũ):" % len(unmatched))
        for name in unmatched[:10]:
            print("  -", name)
        if len(unmatched) > 10:
            print("  ... và %d ảnh khác" % (len(unmatched) - 10))

    mode = input("\nCopy (c) / Move (m) / Huỷ (Enter): ").strip().lower()
    if mode not in ("c", "m"):
        print("Đã huỷ.")
        return
    done, skipped = transfer(folder, groups, move=(mode == "m"))
    print("Xong: %s %d ảnh." % ("move" if mode == "m" else "copy", done))
    if skipped:
        print("Bỏ qua %d ảnh vì đã tồn tại ở đích:" % len(skipped))
        for path in skipped[:10]:
            print("  -", path)


def _selftest():
    import tempfile

    name = "Krea2_I2I_v4_261107_Ivan_Ryo_0_-980726504406445_00001.png"
    expected = {"content": "Krea2_I2I_v4", "date": "261107", "trigger": "Ivan_Ryo",
                "index": "0", "seed": "-980726504406445_00001", "ext": ".png"}
    p, e = compile_format(DEFAULT_FORMAT)
    assert parse_filename(name, p, e) == expected
    # trigger kết thúc bằng số vẫn tách đúng index
    assert parse_filename("A_261107_Char_5_3_123_00001.png", p, e)["index"] == "3"
    assert parse_filename("random.png", p, e) is None
    # template có tên, {*}, chữ cố định
    assert compile_format("{content}_{date}_{trigger}_{index}_{seed}{ext}")[0].pattern == p.pattern
    p2, e2 = compile_format("{*}_{date}_{*}_{index}_{*}")
    assert parse_filename(name, p2, e2) == {"date": "261107", "index": "0"}
    p3, e3 = compile_format("Krea2_I2I_v4_{date}_{trigger}_{index}_{seed}")
    assert parse_filename(name, p3, e3)["index"] == "0"
    assert parse_filename(name.replace("Krea2", "Flux"), p3, e3) is None
    for bad in ("1_2_3_56", "{foo}_{index}", "{index}_{index}"):
        try:
            compile_format(bad)
            raise AssertionError("phải lỗi: " + bad)
        except ValueError:
            pass

    # gom + copy/move thật trên folder tạm
    with tempfile.TemporaryDirectory() as tmp:
        files = [name, name.replace("_0_", "_1_"), name.replace("00001", "00002"), "note.png"]
        for f in files:
            open(os.path.join(tmp, f), "w").close()
        groups, unmatched = group_files(list_images(tmp), p, e)
        assert {k: len(v) for k, v in groups.items()} == {"0": 2, "1": 1} and unmatched == ["note.png"]
        assert transfer(tmp, groups, move=False) == (3, [])
        assert transfer(tmp, groups, move=True)[0] == 0  # đã tồn tại -> bỏ qua, không ghi đè
        assert os.path.exists(os.path.join(tmp, name))  # file gốc còn nguyên
    print("OK")


if __name__ == "__main__":
    _selftest() if "--test" in sys.argv else main()
