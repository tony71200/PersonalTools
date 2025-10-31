import os
from pathlib import Path

def split_file(file_path, lines_per_file):
    """
    Splits a text file into smaller files with a specified number of lines per file.

    Args:
        file_path (str): The path to the text file.
        lines_per_file (int): The maximum number of lines per smaller file.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        lines = [line for line in lines if len(line.strip())>0]
        total_lines = len(lines)

        if total_lines == 0:
            print("File trống. Không có file nào được tạo.")
            return

        if lines_per_file <= 0:
            print("Số lượng dòng mỗi file phải lớn hơn 0.")
            return

        base_name = os.path.splitext(os.path.basename(file_path))[0]
        output_dir = base_name
        os.makedirs(output_dir, exist_ok=True)

        file_count = 0
        for i in range(0, total_lines, lines_per_file):
            chunk = lines[i:i + lines_per_file]
            file_count += 1
            output_filename = os.path.join(output_dir, f"{base_name}_{file_count}.txt")
            with open(output_filename, 'w', encoding='utf-8') as out_f:
                out_f.writelines(chunk)
        
        print(f"File đã được chia thành công thành {file_count} file trong thư mục '{output_dir}'.")

    except FileNotFoundError:
        print(f"Lỗi: Không tìm thấy file tại '{file_path}'.")
    except Exception as e:
        print(f"Đã xảy ra lỗi: {e}")

if __name__ == '__main__':
    # Example usage:
    file_path = input("Nhập đường dẫn file: ")
    lines_per_file = int(input("Nhập số lượng dòng mỗi file: "))

    file_path = Path(file_path)

    split_file(file_path, lines_per_file)
