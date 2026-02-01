#!/usr/bin/env python3
# extract_frames.py
import cv2
import os
import math
import argparse

def parse_time_to_sec(s: str) -> float:
    """Hỗ trợ định dạng 90 | 01:30 | 00:01:30.500"""
    if s is None: return None
    parts = s.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2:
            m, sec = parts
            return int(m)*60 + float(sec)
        elif len(parts) == 3:
            h, m, sec = parts
            return int(h)*3600 + int(m)*60 + float(sec)
        else:
            raise ValueError
    except Exception:
        raise argparse.ArgumentTypeError(f"Thời gian không hợp lệ: {s}")

def main():
    ap = argparse.ArgumentParser(
        description="Tách video thành ảnh (PNG/JPEG) với OpenCV. Hỗ trợ cắt theo thời gian, target FPS hoặc mỗi N frame."
    )
    ap.add_argument("input", help="Đường dẫn video")
    ap.add_argument("output_dir", help="Thư mục lưu khung hình")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--every-n-frames", type=int, default=None,
                       help="Lưu mỗi N frame (ví dụ: 5 nghĩa là lưu frame 0,5,10,...)")
    group.add_argument("--target-fps", type=float, default=None,
                       help="Lưu theo FPS đích (ví dụ: 2.0 => 2 ảnh/giây; xử lý theo timestamp nên ổn với VFR)")
    ap.add_argument("--start", type=parse_time_to_sec, default=0,
                    help="Thời điểm bắt đầu, vd: 5 | 01:23 | 00:01:23.5 (mặc định 0)")
    ap.add_argument("--duration", type=parse_time_to_sec, default=None,
                    help="Thời lượng cần trích (giây). Bỏ trống để chạy đến hết video.")
    ap.add_argument("--ext", choices=["jpg", "png"], default="jpg", help="Định dạng ảnh (mặc định: jpg)")
    ap.add_argument("--quality", type=int, default=95, help="Chất lượng JPEG (0–100) hoặc PNG compression level (0–9)")
    ap.add_argument("--width", type=int, default=None, help="Resize chiều rộng (giữ tỉ lệ nếu chỉ set width)")
    ap.add_argument("--height", type=int, default=None, help="Resize chiều cao (giữ tỉ lệ nếu chỉ set height)")
    ap.add_argument("--zero-pad", type=int, default=6, help="Số chữ số zero-padding cho chỉ số frame (mặc định 6)")
    ap.add_argument("--prefix", default="frame", help="Tiền tố tên file (mặc định: frame)")
    ap.add_argument("--overwrite", action="store_true", help="Cho phép ghi đè nếu file đã tồn tại")
    ap.add_argument("--dry-run", action="store_true", help="Chạy thử: không ghi file, chỉ log")
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    cap = cv2.VideoCapture(args.input)
    if not cap.isOpened():
        raise SystemExit(f"Không mở được video: {args.input}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) if cap.get(cv2.CAP_PROP_FRAME_COUNT) > 0 else -1
    duration_video = total_frames / fps if (fps > 0 and total_frames > 0) else None

    start_sec = max(0.0, args.start or 0.0)
    end_sec = None
    if args.duration is not None:
        end_sec = start_sec + args.duration
    elif duration_video is not None:
        end_sec = duration_video
    # Seek đến start
    if fps > 0:
        cap.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000.0)
    else:
        # VFR hoặc không đọc được FPS: vẫn set theo msec
        cap.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000.0)

    # Thiết lập bước lấy mẫu
    use_every_n = args.every_n_frames is not None
    if not use_every_n and args.target_fps is None:
        # mặc định: lưu tất cả frame
        use_every_n = True
        args.every_n_frames = 1

    next_t_ms = None
    if args.target_fps and args.target_fps > 0:
        step_ms = 1000.0 / args.target_fps
        next_t_ms = start_sec * 1000.0

    # Thiết lập encode options
    if args.ext == "jpg":
        imwrite_params = [cv2.IMWRITE_JPEG_QUALITY, int(max(0, min(args.quality, 100)))]
    else:  # png
        # PNG compression level: 0 (no compression) to 9 (max)
        imwrite_params = [cv2.IMWRITE_PNG_COMPRESSION, int(max(0, min(args.quality, 9)))]

    saved = 0
    idx = 0  # chỉ số file output
    frame_id = 0  # chỉ số frame thực tế (để every-n-frames)
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        # timestamp hiện tại (ms)
        t_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
        if end_sec is not None and t_ms >= end_sec * 1000.0:
            break

        should_save = False
        if args.target_fps and args.target_fps > 0:
            # Lưu khi timestamp >= mốc tiếp theo
            if t_ms + 0.01 >= next_t_ms:  # +epsilon
                should_save = True
                # nhảy mốc tiếp theo (có thể nhảy qua nhiều step nếu video bị lag timestamp)
                while next_t_ms <= t_ms:
                    next_t_ms += step_ms
        else:
            # Lưu theo mỗi N frame
            if frame_id % args.every_n_frames == 0:
                should_save = True

        if should_save:
            # Resize nếu cần
            if args.width or args.height:
                h, w = frame.shape[:2]
                if args.width and args.height:
                    new_w, new_h = args.width, args.height
                elif args.width:
                    ratio = args.width / float(w)
                    new_w, new_h = args.width, int(round(h * ratio))
                else:
                    ratio = args.height / float(h)
                    new_w, new_h = int(round(w * ratio)), args.height
                frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

            # Tên file: {prefix}_{idx}_{timestamp}.ext
            ts_ms = int(round(t_ms))
            filename = f"{args.prefix}_{str(idx).zfill(args.zero_pad)}_{str(ts_ms).zfill(8)}.{args.ext}"
            out_path = os.path.join(args.output_dir, filename)

            if not args.overwrite and os.path.exists(out_path):
                pass  # bỏ qua nếu đã tồn tại
            else:
                if not args.dry_run:
                    cv2.imwrite(out_path, frame, imwrite_params)
                saved += 1

        frame_id += 1
        idx += 1 if should_save else 0

    cap.release()
    print(f"Đã lưu {saved} ảnh vào: {args.output_dir}")

if __name__ == "__main__":
    main()
