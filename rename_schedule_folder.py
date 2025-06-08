import os

def ask_rename_schedule():
    try:
        print("Chọn nền tảng để định dạng tên folder mới:")
        print("1: Civitai")
        print("2: Instagram")
        print("3: Patreon")
        platform_choice = int(input("▶ "))

        if platform_choice == 2:
            days = int(input("Bạn muốn post trong bao nhiêu ngày? "))
            posts_per_day = int(input("Số lượng bài đăng mỗi ngày: "))
            return platform_choice, [(day, idx+1) for day in range(1, days+1) for idx in range(posts_per_day)]
        else:
            days = int(input("Bạn muốn post trong bao nhiêu ngày? "))
            start_hour = int(input("Khung giờ bắt đầu trong ngày (ví dụ 6): "))
            end_hour = int(input("Khung giờ kết thúc trong ngày (ví dụ 22): "))
            real_start_hour = int(input("Giờ thực tế bạn muốn bắt đầu post (ví dụ 13): "))

            if not (start_hour <= real_start_hour < end_hour):
                print("⚠️ Giờ bắt đầu post phải nằm trong khoảng thời gian cho phép.")
                return None, []

            folder_times = []
            for day in range(1, days + 1):
                for hour in range(real_start_hour if day == 1 else start_hour, end_hour):
                    suffix = "am" if hour < 12 else "pm"
                    hour_display = hour if hour <= 12 else hour - 12
                    folder_times.append((day, f"{suffix}{hour_display:02d}"))
            return platform_choice, folder_times
    except ValueError:
        print("⚠️ Vui lòng nhập đúng định dạng số.")
        return None, []

def rename_folders(base_folder):
    subfolders = [f for f in os.listdir(base_folder) if os.path.isdir(os.path.join(base_folder, f))]
    print(f"📁 Tổng cộng {len(subfolders)} folder con được tìm thấy.")

    platform, new_names_meta = ask_rename_schedule()
    if not new_names_meta or len(subfolders) > len(new_names_meta):
        print("❌ Không đủ tên mới để đổi hoặc dữ liệu không hợp lệ.")
        return

    print("Danh sách tên folder mới:")
    new_names = []
    for item in new_names_meta:
        if platform == 2:
            day, index = item
            new_names.append(f"Day{day}_{index}")
        else:
            day, hour_tag = item
            new_names.append(f"Day{day}_{hour_tag}")

    for old_name, new_name in zip(subfolders, new_names):
        src = os.path.join(base_folder, old_name)
        dst = os.path.join(base_folder, new_name)
        os.rename(src, dst)
        print(f"✅ Đã đổi: {old_name} -> {new_name}")

if __name__ == "__main__":
    folder = input("📂 Nhập đường dẫn folder cha: ").strip()
    rename_folders(folder)