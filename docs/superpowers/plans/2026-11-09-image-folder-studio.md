# Image Folder Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xây dựng Image Folder Studio để đối chiếu tên ảnh giữa hai cây thư mục và quản lý file trong một thư mục gốc.

**Architecture:** Một cửa sổ PyQt5 chứa hai tab. Mô-đun xử lý cung cấp cây thư mục, thống kê, so sánh và thao tác file. Hai tab dùng chung luồng chạy nền và thành phần hiển thị ảnh, mỗi tab quản lý trạng thái chọn thư mục và ảnh riêng.

**Tech Stack:** Python, PyQt5 và Qt 5.15 trên Windows. Môi trường đã kiểm tra có Python 3.12.9, PyQt5 5.15.11, Qt 5.15.2 và `QFile.moveToTrash`.

**Spec:** `docs/superpowers/specs/2026-11-09-image-folder-studio-design.md`

## Global Constraints

- File chạy là `manager_image/image_folder_studio.py`. Chạy từ repo bằng `python manager_image/image_folder_studio.py`.
- Giao diện dùng PyQt5 và thư viện chuẩn, giữ độc lập với các thư viện xử lý video.
- Dùng thanh công cụ, tab, panel kéo đổi kích thước, thumbnail và vùng log theo cách bố trí của `video/ig_merge_video_ui.py`. Tham khảo `ImageThumbnailCache` và `MainWindow` trong file mẫu, cùng thao tác duyệt và xem trước của `manager_image/manager_folder2.py`.
- Tab so sánh chỉ đọc file. Tên khớp gồm phần mở rộng và bỏ qua hoa/thường. Mỗi đường dẫn ảnh được tính một lần trong thư mục của nó.
- Bỏ qua liên kết và junction khi duyệt cây. Nếu đích đã có file cùng tên thì báo xung đột và giữ cả hai file hiện có. Xóa qua Thùng rác sau xác nhận.
- Quét và đọc thumbnail ngoài luồng giao diện. Bỏ qua dữ liệu cũ nếu người dùng đổi thư mục giữa lúc quét. Dùng bộ nhớ đệm thumbnail có giới hạn.

---

## File Structure

| File | Trách nhiệm |
| --- | --- |
| `manager_image/image_folder_studio_core.py` | Quét cây, thống kê, so tên và thao tác file có kiểm tra đường dẫn. |
| `manager_image/image_folder_studio_widgets.py` | Chạy tác vụ nền, đọc ảnh bằng Qt, bộ đệm, lưới và xem trước dùng chung. |
| `manager_image/image_folder_studio.py` | Điểm chạy, cửa sổ, lớp `CompareTab` và `ManageTab`, nối tín hiệu với dịch vụ. |
| `manager_image/test_image_folder_studio.py` | Các ca hồi quy cho tên trùng, thay đổi file và trạng thái tab. |
| `README.md` | Mục Image Folder Studio, lệnh chạy và quy tắc so tên. |

Chạy các lệnh từ thư mục gốc repo. Dùng `unittest discover` với `-s manager_image` để test dùng cùng cách import mô-đun cùng thư mục với file chạy. Các ca filesystem tạo dữ liệu trong `TemporaryDirectory`. Các ca giao diện dùng một `QApplication` với `QT_QPA_PLATFORM=offscreen` và `QSignalSpy` hoặc chờ sự kiện có giới hạn thời gian.

### Task 1 — Chỉ mục cây và tỷ lệ khớp

**Files:** Tạo `manager_image/image_folder_studio_core.py` và `manager_image/test_image_folder_studio.py`.

**Interfaces:** `scan_tree(root: Path) -> TreeSnapshot`, `compare_trees(left: TreeSnapshot, right: TreeSnapshot) -> Comparison`, `is_image(path: Path) -> bool`. Snapshot có `root`, `folders: dict[Path, FolderEntry]` và `errors: tuple[str, ...]`. Mỗi `FolderEntry` có `children`, `files` (tuple đường dẫn tuyệt đối), `descendant_count`, `image_count`, `cover: Path | None`. `Comparison` có `left_total`, `right_total`, `left_matches` và `right_matches` (ánh xạ đường dẫn ảnh sang tuple đường dẫn khớp phía bên kia), `common_names: int`.

- [ ] **Viết ca hồi quy** cho tên có nhiều đường dẫn, khác đuôi, hoa/thường, file văn bản và thư mục lồng. Bổ sung ca thư mục trống, lỗi đọc một nhánh bằng cách mock trình duyệt thư mục ném `PermissionError`, và bỏ qua symlink hoặc junction ở nơi hệ điều hành cho phép tạo.

  ```python
  def test_recursive_name_match(self):
      with TemporaryDirectory() as tmp:
          left, right = Path(tmp) / "A", Path(tmp) / "B"
          for root, name in [
              (left, "one/Bien.JPG"), (left, "one/nested/bien.jpg"),
              (left, "bien.png"), (left, "caption.txt"),
              (right, "other/bien.jpg"), (right, "rung.jpg"),
          ]:
              path = root / name
              path.parent.mkdir(parents=True, exist_ok=True)
              path.touch()
          snapshot = scan_tree(left)
          result = compare_trees(snapshot, scan_tree(right))
          self.assertEqual((result.left_total, result.right_total), (3, 2))
          self.assertEqual((len(result.left_matches), len(result.right_matches)), (2, 1))
          self.assertEqual(result.common_names, 1)
          self.assertEqual(set(result.right_matches[right / "other/bien.jpg"]),
                           {left / "one/Bien.JPG", left / "one/nested/bien.jpg"})
          root = snapshot.folders[left]
          self.assertEqual((len(root.children), root.descendant_count, root.image_count), (1, 2, 3))
  ```

- [ ] **Chạy đỏ.** `python -m unittest discover -s manager_image -p test_image_folder_studio.py -v` phải báo thiếu mô-đun hoặc hàm trước khi triển khai.
- [ ] **Triển khai quét.** Dùng `os.scandir`, xử lý lỗi mở thư mục và lỗi đọc từng mục riêng để một nhánh lỗi không làm mất dữ liệu nhánh khác. Dùng `lstat` trên Windows để bỏ qua điểm nối và các mục có thuộc tính `stat.FILE_ATTRIBUTE_REPARSE_POINT` trước khi đi xuống. Duyệt bằng stack và tổng hợp số đếm từ lá lên. Sắp xếp tên ổn định trước khi chọn ảnh bìa. Cố định nhóm đuôi ban đầu là `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.gif`, `.tif`, `.tiff`. Quét theo tên nên ca kiểm thử có thể dùng file ảnh trống. Dữ liệu quét giữ tất cả file thường để tab quản lý hiển thị được file phụ.
- [ ] **Triển khai đối chiếu.** Lập chỉ mục mỗi bên bằng đoạn sau. Tạo tuple một lần cho từng tên rồi dùng lại tuple đó trong các ánh xạ khớp để nhiều ảnh trùng tên không nhân bộ nhớ theo tích hai bên.

  ```python
  names = defaultdict(list)
  for folder in snapshot.folders.values():
      for path in folder.files:
          if is_image(path):
              names[path.name.casefold()].append(path)
  index = {name: tuple(paths) for name, paths in names.items()}
  ```

- [ ] **Chạy xanh và commit.** Chạy lại lệnh unittest và `git diff --check`. Commit hai file với thông điệp `Add image folder indexing and name comparison`.

### Task 2 — Thao tác file an toàn trong cây gốc

**Files:** Sửa `manager_image/image_folder_studio_core.py` và `manager_image/test_image_folder_studio.py`.

**Interfaces:** `create_numbered_folder(root: Path, parent: Path) -> Path`, `copy_file(root: Path, source: Path, destination_dir: Path) -> Path`, `move_file(root: Path, source: Path, destination_dir: Path) -> Path`, `trash_file(root: Path, source: Path) -> None`. Các hàm ném `OSError` hoặc lớp con với đường dẫn và lý do.

- [ ] **Viết ca hồi quy** cho nguồn ngoài cây gốc, sao chép và di chuyển thành công, xung đột tên và lỗi Thùng rác. Mock `QFile.moveToTrash` trả về lỗi trong test để không đưa file kiểm thử vào Thùng rác thật.

  ```python
  def test_numbering_and_copy_conflict(self):
      with TemporaryDirectory() as tmp:
          root = Path(tmp)
          (root / "009").mkdir()
          (root / "010").touch()
          destination = create_numbered_folder(root, root)
          self.assertEqual(destination.name, "011")
          source = root / "anh.png"
          source.write_bytes(b"source")
          existing = destination / source.name
          existing.write_bytes(b"existing")
          with self.assertRaises(FileExistsError):
              copy_file(root, source, destination)
          with self.assertRaises(FileExistsError):
              move_file(root, source, destination)
          self.assertEqual(source.read_bytes(), b"source")
          self.assertEqual(existing.read_bytes(), b"existing")
  ```

- [ ] **Chạy đỏ.** Dùng lệnh unittest của Task 1. Lỗi dự kiến là các hàm thao tác chưa tồn tại.
- [ ] **Triển khai xác thực và đánh số.** Kiểm tra nguồn là file thường và đích là thư mục có thật. Xác minh đường dẫn nằm trong gốc cả trước và sau khi resolve. Kiểm tra từng thành phần dưới gốc bằng cùng quy tắc reparse point của Task 1. Với tên số, chỉ lấy tên ASCII khớp `[0-9]+` của các thư mục con hợp lệ. Dùng `mkdir(exist_ok=False)` để tránh đụng tên khi có tiến trình tạo trước.

  ```python
  while True:
      candidate = parent / f"{number:03d}"
      try:
          candidate.mkdir()
      except FileExistsError:
          number += 1
      else:
          return candidate
  ```

- [ ] **Triển khai copy, move và trash.** Tạo `target = destination_dir / source.name`. Báo `FileExistsError` nếu đích tồn tại hoặc là link hỏng. Dùng `QFile.copy` và `QFile.rename` qua đối tượng `QFile` để thao tác từ chối đích đã tồn tại. Kiểm tra giá trị trả về và đưa `errorString()` vào lỗi. Với xóa, gọi `QFile(str(source)).moveToTrash()`. Nếu API báo lỗi, trả lỗi cho UI và giữ nguyên thao tác ở trạng thái thất bại.
- [ ] **Chạy xanh và commit.** Chạy lệnh unittest và `git diff --check`. Commit hai file với thông điệp `Add guarded image folder file operations`.

### Task 3 — Ảnh thu nhỏ và luồng nền dùng chung

**Files:** Tạo `manager_image/image_folder_studio_widgets.py`. Sửa `manager_image/test_image_folder_studio.py`.

**Interfaces:** `BackgroundJob(QObject)` có `start(work: Callable[[], object]) -> None` và tín hiệu `finished(object)`, `failed(str)`. `read_scaled_image(path: Path, bounds: QSize) -> QImage` ném `OSError` nếu ảnh lỗi. `ImageLoader(QObject)` có `request(path: Path, bounds: QSize, generation: int) -> None`, `clear_cache() -> None` và tín hiệu `ready(int, object, QImage)`, `failed(int, object, str)` mang generation và path. `make_grid() -> QListWidget` tạo lưới chọn một mục.

- [ ] **Viết ca hồi quy.** Tạo PNG 320 × 160 với `QImage`, thử đọc trong khung 96 × 96 và thử file hỏng. Kiểm tra `ImageLoader.ready` giữ đúng generation kể cả khi lấy từ cache.

  ```python
  def test_thumbnail_keeps_aspect_ratio(self):
      with TemporaryDirectory() as tmp:
          path = Path(tmp) / "wide.png"
          image = QImage(320, 160, QImage.Format_RGB32)
          image.fill(Qt.blue)
          self.assertTrue(image.save(str(path)))
          self.assertEqual(read_scaled_image(path, QSize(96, 96)).size(), QSize(96, 48))
          path.write_bytes(b"not a PNG")
          with self.assertRaises(OSError):
              read_scaled_image(path, QSize(96, 96))
  ```

- [ ] **Chạy đỏ.** Chạy `$env:QT_QPA_PLATFORM = 'offscreen'; python -m unittest discover -s manager_image -p test_image_folder_studio.py -v`. Lỗi dự kiến là thiếu mô-đun widgets.
- [ ] **Triển khai ảnh và worker.** Dùng `QThreadPool` và `QRunnable` để chạy việc đọc, quét và thao tác file. Tín hiệu kết quả về `QObject` ở luồng UI qua kết nối queued. Worker giữ đường dẫn và hàm công việc, không truy cập widget. Mỗi yêu cầu dùng một `BackgroundJob`, giữ tham chiếu tới khi có kết quả hoặc lỗi và để Qt ngắt kết nối khi widget nhận bị hủy. Dùng `QImageReader.setAutoTransform(True)`, đặt `setScaledSize` theo khung giữ tỷ lệ khi kích thước nguồn hợp lệ và giới hạn ảnh lần cuối sau khi áp dụng xoay. Đưa `reader.errorString()` và tên file vào lỗi. Chuyển sang `QPixmap` trong slot UI.
- [ ] **Triển khai cache và lưới.** Dùng LRU 256 thumbnail theo `(path, mtime_ns, size_bytes, width, height)`, bỏ mục cũ nhất khi đầy. Ảnh xem lớn đọc theo kích thước panel khi chọn, không lưu vào cache thumbnail. Dùng `QListView.IconMode`, `QListView.Adjust`, `QListView.Static`, chế độ chọn một mục và `Qt.UserRole` cho đường dẫn. Lỗi ảnh chỉ hiện placeholder và được báo về tab để ghi log.
- [ ] **Chạy xanh và commit.** Chạy lại test ở chế độ offscreen, sau đó `git diff --check`. Commit widget và test với thông điệp `Add asynchronous image previews for folder studio`.

### Task 4 — Cửa sổ và tab So sánh thư mục

**Files:** Tạo `manager_image/image_folder_studio.py`. Sửa `manager_image/test_image_folder_studio.py`.

**Interfaces:** `main() -> int`, `MainWindow(QMainWindow)`, `CompareTab(QWidget)`, `CompareTab.set_root(side: str, root: Path) -> None`, `CompareTab.start_compare() -> None`, tín hiệu `comparison_ready(object)` phát sau khi cập nhật tỷ lệ, log và danh sách. Nút so sánh gọi `start_compare`, hộp thoại chọn thư mục gọi `set_root`.

- [ ] **Viết ca hồi quy** cho định dạng tỷ lệ và kết quả đi qua tab. Kiểm tra chọn ảnh hiển thị mọi đường dẫn đối ứng, cả hai pane giữ đúng bộ lọc, và kết quả chậm từ thư mục cũ bị bỏ qua sau khi đổi A.

  ```python
  def test_compare_tab_displays_both_directions(self):
      with TemporaryDirectory() as tmp:
          a, b = Path(tmp) / "A", Path(tmp) / "B"
          for folder, filenames in [(a, ["x.jpg", "a.png"]), (b, ["X.JPG"])]:
              folder.mkdir()
              for name in filenames:
                  (folder / name).touch()
          tab = CompareTab()
          tab.set_root("A", a)
          tab.set_root("B", b)
          ready = QSignalSpy(tab.comparison_ready)
          tab.start_compare()
          self.assertTrue(ready.wait(3000))
          self.assertEqual(tab.rate_a.text(), "50% (1/2)")
          self.assertEqual(tab.rate_b.text(), "100% (1/1)")
  ```

- [ ] **Chạy đỏ.** Chạy bộ unittest offscreen và xác nhận ca mới lỗi do thiếu `CompareTab`.
- [ ] **Nối cửa sổ và hai pane.** Tạo `QTabWidget`, một `QSplitter(Qt.Horizontal)` cho ba cột và splitter dọc cho cây/lưới ở mỗi bên. Cột giữa dùng `QLabel` cho hai tỷ lệ, vùng thông tin cuộn được và `QPlainTextEdit` chỉ đọc cho log. Khi đổi root, tăng generation so sánh, bỏ kết quả so sánh, quét riêng root mới để duyệt, giữ nút **So sánh** khả dụng khi đã chọn đủ hai root. Mỗi pane giữ số yêu cầu quét riêng. Khi bấm **So sánh**, tăng generation so sánh và số yêu cầu của cả hai pane để kết quả quét riêng cũ không ghi đè kết quả mới. Worker quét mới cả hai root rồi trả snapshot và kết quả. So mã yêu cầu trước khi áp dữ liệu. Giữ đường dẫn dài trong label có tooltip hoặc vùng cuộn để chúng không kéo giãn splitter.
- [ ] **Nối chọn ảnh, tỷ lệ và bộ lọc.** Dùng `Qt.UserRole` cho đường dẫn. Đồng bộ chọn cây và lưới bằng chặn tín hiệu trong lượt cập nhật đối ứng. Kiểm tra khớp bằng `path in result.left_matches` hoặc `path in result.right_matches`. Dùng cùng nền xanh và ✓ cho cả hai dạng. Khi lọc, giữ thư mục tổ tiên của ảnh còn hiện và giữ thư mục đang chọn nếu nhánh vẫn còn. Cột giữa hiển thị tất cả đường dẫn đối ứng tương đối theo gốc. Báo rõ dữ liệu chưa đầy đủ nếu snapshot có lỗi.

  ```python
  def format_rate(matched: int, total: int) -> str:
      if not total:
          return "— (0/0)"
      return f"{100 * matched / total:.2f}".rstrip("0").rstrip(".") + f"% ({matched}/{total})"
  ```

- [ ] **Chạy xanh và commit.** Chạy test offscreen, rồi chạy `python manager_image/image_folder_studio.py` trên desktop. Chọn hai thư mục mẫu, thu hẹp cửa sổ và kéo splitter. Commit file chạy và test với thông điệp `Build Image Folder Studio comparison tab`.

### Task 5 — Tab Quản lý thư mục

**Files:** Sửa `manager_image/image_folder_studio.py` và `manager_image/test_image_folder_studio.py`.

**Interfaces:** `ManageTab(QWidget)`, `ManageTab.set_root(root: Path) -> None`, `ManageTab.select_path(path: Path) -> None`, tín hiệu `snapshot_ready(object)` phát sau khi cây và panel đã nhận snapshot. Tab dùng bốn hàm thao tác file của Task 2 và widget của Task 3.

- [ ] **Viết ca hồi quy** cho luồng chọn gốc, đi vào thư mục con và mở ảnh. Kiểm tra đổi root khi đang quét, làm mới sau khi tạo thư mục và đóng xác nhận xóa mà file vẫn còn.

  ```python
  def test_manage_tab_opens_nested_folder(self):
      with TemporaryDirectory() as tmp:
          root = Path(tmp)
          nested = root / "001" / "Đã chọn"
          nested.mkdir(parents=True)
          (nested / "rung.jpg").touch()
          tab = ManageTab()
          ready = QSignalSpy(tab.snapshot_ready)
          tab.set_root(root)
          self.assertTrue(ready.wait(3000))
          tab.select_path(nested)
          self.assertEqual(tab.current_folder, nested)
          self.assertEqual(tab.grid.count(), 1)
          self.assertEqual(tab.grid.item(0).data(Qt.UserRole), nested / "rung.jpg")
  ```

- [ ] **Chạy đỏ.** Chạy unittest offscreen và xác nhận ca mới lỗi do thiếu `ManageTab`.
- [ ] **Dựng cây và panel phải.** Thêm tab thứ hai vào `MainWindow`. Panel trái có picker, đường dẫn và `QTreeWidget` với cột tên, thư mục trực tiếp, tổng thư mục và ảnh. Panel phải có đường dẫn, nút về thư mục cha, nút thao tác, `QStackedWidget` chứa lưới, ảnh lớn hoặc thông tin file và log. Khi chọn thư mục, điền ô từ `entry.children` và `entry.files`. Khi chọn file, đặt `current_folder = path.parent` và chuyển sang trang xem trước. Trong chế độ xem ảnh, nút cha quay lại lưới thư mục chứa ảnh.

  ```python
  entry = snapshot.folders[folder]
  columns = [
      folder.name, str(len(entry.children)),
      str(entry.descendant_count), str(entry.image_count),
  ]
  item = QTreeWidgetItem(columns)
  item.setData(0, Qt.UserRole, folder)
  ```

- [ ] **Nối bốn thao tác.** Nút tạo dùng `current_folder`. Nút sao chép và di chuyển mở dialog hiển thị file nguồn, liệt kê đường dẫn thư mục trong snapshot và vô hiệu hóa đích là thư mục nguồn. Nút xóa dùng `QMessageBox` với lựa chọn mặc định **Hủy**. Khi xác nhận, khóa các nút thao tác của tab đến khi worker kết thúc để tránh chạy trùng. Khi thành công, làm mới snapshot và cache của tab. Giữ nhánh đang xem cho sao chép, quay về thư mục nguồn cho di chuyển và xóa, mở thư mục vừa tạo sau khi quét lại. Nếu lỗi, ghi đường dẫn và lý do vào log, trả lại điều khiển và làm mới cây để phản ánh trạng thái đĩa.
- [ ] **Chạy xanh và commit.** Chạy unittest offscreen. Trên desktop, dùng thư mục mẫu với `001/Đã chọn`, `002`, một ảnh và một file văn bản. Thử bốn thao tác, kiểm tra số đếm và thử hủy hộp thoại xóa trước khi kiểm tra đưa file mẫu vào Thùng rác. Commit file chạy và test với thông điệp `Add Image Folder Studio management tab`.

### Task 6 — Hướng dẫn chạy và kiểm tra tích hợp

**Files:** Sửa `README.md`.

- [ ] **Thêm hướng dẫn cạnh nhóm công cụ ảnh** bằng đoạn sau.

  ````markdown
  ### Image Folder Studio

  Chạy trên Windows với PyQt5 và Qt 5.15.

  ```powershell
  python manager_image/image_folder_studio.py
  ```

  - **So sánh thư mục** quét cả thư mục con và tính tỷ lệ theo hai chiều bằng tên file đầy đủ. Các tên khớp được tô xanh.
  - **Quản lý thư mục** duyệt cây, xem ảnh và tạo thư mục đánh số. Chọn file để sao chép, di chuyển hoặc đưa vào Thùng rác.
  ````

- [ ] **Kiểm tra tích hợp.** Chạy `$env:QT_QPA_PLATFORM = 'offscreen'; python -m unittest discover -s manager_image -p test_image_folder_studio.py -v`, rồi `Remove-Item Env:QT_QPA_PLATFORM` trước khi chạy GUI thật. Dùng cây A gồm 4 ảnh và cây B gồm 5 ảnh với 3 tên chung ở các đường dẫn khác nhau. Xác nhận `75% (3/4)`, `60% (3/5)`, đúng màu và bộ lọc. Trong tab 2, tạo `003` cạnh `001`, `002`, thử đổi gốc trong lúc quét, và kiểm tra các ảnh cùng tên ở đích được giữ nguyên khi thao tác thất bại. Thử một đường dẫn dài để xác nhận pane vẫn thu hẹp được. Ghi lại những ca chưa kiểm chứng nếu môi trường thiếu desktop hoặc Thùng rác.
- [ ] **Kiểm tra diff và commit.** Chạy `git diff --check` và `git status --short`. Commit phần README với thông điệp `Document Image Folder Studio usage`.
