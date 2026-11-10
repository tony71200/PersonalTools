# Image Folder Studio Disk Usage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm tab **Dung lượng** để xem các ổ đĩa trong **This PC** và tỷ lệ dung lượng các thư mục con theo thư mục gốc đã chọn.

**Architecture:** Mở rộng snapshot của trình quét hiện có để cộng kích thước từ metadata trong cùng một lượt duyệt. Đặt thông tin ổ đĩa, cách định dạng dung lượng và UI tab vào mô-đun riêng. Tab dùng `run_background` để đọc ổ hoặc quét thư mục và dùng số phiên yêu cầu để loại kết quả đến muộn.

**Tech Stack:** Python, PyQt5 và Qt 5.15 trên Windows. Dùng `QStorageInfo`, `QProgressBar`, `QTreeWidget`, `unittest` và `QSignalSpy`. Các phương thức `mountedVolumes`, `rootPath`, `name`, `isValid`, `isReady`, `bytesTotal` và `bytesFree` đều có trong môi trường hiện tại.

**Spec:** `docs/superpowers/specs/2026-11-10-image-folder-studio-disk-usage-design.md` (commit `65b2c4b`).

## Global Constraints

- Python, PyQt5 và Qt 5.15 trên Windows.
- Tab có một nút **Chọn thư mục…**, một thanh tỷ lệ và một cây. Thông báo đang tải hoặc lỗi nằm cạnh thanh tỷ lệ. Mọi thao tác trong tab chỉ đọc.
- **This PC** là chế độ mặc định. Chế độ này chỉ đọc thông tin ổ đĩa và không quét cây thư mục của các ổ.
- Dung lượng thư mục là kích thước logic theo byte. Tỷ lệ thư mục dùng tổng byte của thư mục gốc đã chọn. Dùng đơn vị B, KB, MB, GB và TB theo hệ thập phân.
- Bỏ qua symlink và junction. Kết quả từ yêu cầu cũ bị bỏ qua sau khi chọn gốc mới hoặc quay lại **This PC**.
- Tại thời điểm viết plan, `manager_image/image_folder_studio.py` và `manager_image/test_image_folder_studio.py` có thay đổi chưa commit cho chức năng chọn ảnh đối ứng. Giữ các thay đổi đó. Khi commit phần nối tab, chỉ stage hunk import và hunk `MainWindow` của tab mới nếu các thay đổi cũ vẫn chưa được commit.

---

## File Structure

| File | Thay đổi |
| --- | --- |
| `manager_image/image_folder_studio_core.py` | Cộng byte vào snapshot hiện có, giữ lỗi theo thư mục và nhận biết lỗi mở gốc. |
| `manager_image/image_folder_studio_usage.py` | Đọc ổ đĩa, định dạng byte và dựng `DiskUsageTab`. |
| `manager_image/image_folder_studio.py` | Thêm `DiskUsageTab` vào cửa sổ sau hai tab hiện tại. |
| `manager_image/test_image_folder_studio_usage.py` | Ca kiểm tra snapshot, ổ đĩa, hai chế độ và kết quả đến muộn. |
| `README.md` | Thêm một dòng hướng dẫn tab Dung lượng. |

Chạy từ gốc repo. Trong phiên PowerShell dùng sandbox, đặt TEMP/TMP vào workspace cho các ca dùng thư mục tạm.

```powershell
$env:TEMP = (Get-Location).Path
$env:TMP = $env:TEMP
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m unittest discover -s manager_image -p 'test_image_folder_studio*.py' -v
```

### Task 1 — Cộng kích thước thư mục từ metadata

**Files:** Sửa `manager_image/image_folder_studio_core.py`. Tạo `manager_image/test_image_folder_studio_usage.py`.

**Interfaces:** Giữ `scan_tree(root: Path) -> TreeSnapshot`. Thêm `FolderEntry.total_bytes: int`, `TreeSnapshot.errors_by_folder: dict[Path, tuple[str, ...]]` và `TreeSnapshot.root_unreadable: bool`. Giữ `TreeSnapshot.errors` dạng tuple chuỗi cho hai tab cũ.

- [x] **Viết ca kiểm tra tổng byte và lỗi.** Tạo test với `unittest.TestCase`, `TemporaryDirectory` và `Path`. Dùng cùng một file test cho ba task.

  ```python
  def test_folder_sizes_include_direct_and_nested_files(self):
      with TemporaryDirectory() as tmp:
          root = Path(tmp)
          (root / "image.png").write_bytes(b"a" * 100)
          (root / "work" / "nested").mkdir(parents=True)
          (root / "work" / "file.cs").write_bytes(b"b" * 30)
          (root / "work" / "nested" / "file.py").write_bytes(b"c" * 20)
          (root / "empty").mkdir()
          snapshot = scan_tree(root)
          self.assertEqual(snapshot.folders[root].total_bytes, 150)
          self.assertEqual(snapshot.folders[root / "work"].total_bytes, 50)
          self.assertEqual(snapshot.folders[root / "empty"].total_bytes, 0)
          self.assertFalse(snapshot.root_unreadable)

  def test_denied_branch_keeps_other_sizes(self):
      with TemporaryDirectory() as tmp:
          root = Path(tmp)
          blocked = root / "blocked"
          blocked.mkdir()
          (root / "file.txt").write_bytes(b"hello")
          scandir = os.scandir

          def read(path):
              if Path(path) == blocked:
                  raise PermissionError("denied")
              return scandir(path)

          with patch("image_folder_studio_core.os.scandir", side_effect=read):
              snapshot = scan_tree(root)
          self.assertEqual(snapshot.folders[root].total_bytes, 5)
          self.assertIn("denied", snapshot.errors_by_folder[blocked][0])
          self.assertFalse(snapshot.root_unreadable)
          with patch("image_folder_studio_core.os.scandir", side_effect=PermissionError("denied")):
              self.assertTrue(scan_tree(root).root_unreadable)
  ```

- [x] **Chạy đỏ.** Chạy bộ test với lệnh ở trên và xác nhận ca mới lỗi vì snapshot chưa có `total_bytes` và trạng thái lỗi mới.
- [x] **Cộng byte trong lượt quét hiện có.** Trong `_read_directory`, giữ cách lọc link và kiểu file bằng `entry.stat(follow_symlinks=False)`. Ghi tổng byte trực tiếp cùng danh sách con và file. Tách lỗi mở `os.scandir(folder)` khỏi lỗi xảy ra trong lúc duyệt một phần iterator. Trả cờ lỗi mở cùng dữ liệu để `scan_tree` gán `root_unreadable` khi gốc không mở được. Nhóm thông báo theo thư mục được duyệt và đồng thời giữ danh sách lỗi phẳng cũ. Trường hợp `lstat` của gốc thất bại cũng trả `root_unreadable=True` và lỗi gắn với gốc.

  ```python
  # Trong _read_directory, sau khi đã loại link và xác nhận file thường.
  files.append(Path(entry.path))
  direct_bytes += info.st_size

  # Trong vòng lặp từ lá về gốc của scan_tree.
  total_bytes = direct_bytes + sum(entry.total_bytes for entry in child_entries)
  ```

- [x] **Chạy xanh.** Chạy cả bộ test hiện có và mới. Kiểm tra các số đếm ảnh, phép đối chiếu và hành vi bỏ qua liên kết vẫn đạt. Chạy `git diff --check`.
- [x] **Commit phần quét.** Stage file core và file test mới. Dùng thông điệp `Track folder byte totals during image studio scans`.

### Task 2 — Số liệu ổ đĩa và cách định dạng

**Files:** Tạo `manager_image/image_folder_studio_usage.py`. Sửa `manager_image/test_image_folder_studio_usage.py`.

**Interfaces:** `DriveUsage(letter: str, label: str, total_bytes: int, free_bytes: int)` có thuộc tính `used_bytes: int`. `read_drives() -> tuple[DriveUsage, ...]`. `format_bytes(size: int) -> str`. `format_ratio(name: str, used: int, total: int) -> tuple[int, str]` trả giá trị thanh theo thang 0–10.000 và chuỗi có tỷ lệ.

- [x] **Viết ca ổ đĩa và định dạng.** Mock `mountedVolumes` bằng đối tượng có cùng các phương thức Qt. Kiểm tra ổ chưa sẵn sàng, trùng ký tự, mount path không phải gốc ổ và giá trị byte lỗi.

  ```python
  def test_reads_ready_drive_letters_in_order(self):
      def volume(path, label, total=1000, free=250, ready=True):
          return SimpleNamespace(
              rootPath=lambda: path, name=lambda: label,
              isValid=lambda: True, isReady=lambda: ready,
              bytesTotal=lambda: total, bytesFree=lambda: free,
          )

      mounted = [volume("E:/", "Backup"), volume("C:/", "System"),
                 volume("c:/", "Duplicate"), volume("D:/", "", ready=False),
                 volume("C:/mount", "Mount"), volume("F:/", "", free=-1)]
      with patch("image_folder_studio_usage.QStorageInfo.mountedVolumes", return_value=mounted):
          drives = read_drives()
      self.assertEqual([(d.letter, d.label, d.used_bytes) for d in drives],
                       [("C:", "System", 750), ("E:", "Backup", 750)])

  def test_format_size_and_empty_ratio(self):
      self.assertEqual(format_bytes(3_200_000_000), "3,2 GB")
      self.assertEqual(format_ratio("Ảnh", 3_200_000_000, 10_000_000_000),
                       (3200, "Ảnh — 3,2 GB / 10 GB (32%)"))
      self.assertEqual(format_ratio("Rỗng", 0, 0), (0, "Rỗng — 0 B / 0 B (—)"))
  ```

- [x] **Chạy đỏ.** Xác nhận lỗi import mô-đun usage hoặc các hàm mới.
- [x] **Đọc số liệu ổ.** Gọi `QStorageInfo.mountedVolumes()` một lần, lọc `isValid()` và `isReady()` trước khi đọc dung lượng. Chỉ nhận gốc dạng ký tự ổ. Loại các giá trị tổng không dương hoặc free nằm ngoài khoảng 0 đến tổng. Giữ lần đầu theo ký tự đã chuẩn hóa và trả theo thứ tự ký tự.

  ```python
  drive = re.fullmatch(r"([A-Za-z]:)/?", volume.rootPath().replace(chr(92), "/"))
  total, free = volume.bytesTotal(), volume.bytesFree()
  if drive and total > 0 and 0 <= free <= total:
      letter = drive[1].upper()
      drives.setdefault(letter, DriveUsage(letter, volume.name(), total, free))
  ```

- [x] **Định dạng số.** Chọn đơn vị lớn nhất có ngưỡng 1.000 tương ứng, tối đa TB. Dùng tối đa hai chữ số thập phân, bỏ số 0 cuối và dùng dấu phẩy. Tính tỷ lệ và giá trị thanh từ byte gốc. Giá trị thanh bằng `round(10_000 * used / total)` khi tổng dương, còn tổng bằng 0 dùng giá trị 0 và nhãn `—`.
- [x] **Chạy xanh và commit.** Chạy cả bộ test và `git diff --check`. Commit mô-đun usage và test với thông điệp `Add drive metadata and disk usage formatting`.

### Task 3 — Dựng tab và nối vào cửa sổ

**Files:** Sửa `manager_image/image_folder_studio_usage.py`, `manager_image/image_folder_studio.py`, `manager_image/test_image_folder_studio_usage.py` và `README.md`.

**Interfaces:** `DiskUsageTab(QWidget)` có `show_this_pc() -> None`, `set_root(root: Path) -> None`, `loaded = pyqtSignal()`, `tree`, `bar`, `summary` và `status`. Phát `loaded` sau khi cập nhật giao diện của yêu cầu hiện hành, kể cả khi lỗi. `MainWindow.tab_usage` là tab thứ ba. Dùng `run_background(owner, work, finished, failed, *, priority=0)` từ `image_folder_studio_widgets.py`.

- [x] **Viết ca cho hai chế độ và kết quả đến muộn.** Khởi tạo một `QApplication` cho nhóm test, dùng mock ổ đĩa và thư mục tạm. Dùng `QSignalSpy` để đợi kết quả trước khi đọc cây.

  ```python
  def test_this_pc_and_folder_use_distinct_totals(self):
      with TemporaryDirectory() as tmp:
          root = Path(tmp)
          (root / "direct.txt").write_bytes(b"abcd")
          (root / "branch").mkdir()
          (root / "branch" / "data.txt").write_bytes(b"ab")
          tab = DiskUsageTab()
          loaded = QSignalSpy(tab.loaded)
          with patch("image_folder_studio_usage.read_drives",
                     return_value=(DriveUsage("C:", "System", 1000, 250),)):
              with patch("image_folder_studio_usage.scan_tree") as scan:
                  tab.show()
                  self.assertTrue(len(loaded) or loaded.wait(3000))
                  scan.assert_not_called()
              tab.tree.setCurrentItem(tab.tree.topLevelItem(0).child(0))
              self.assertEqual(tab.bar.value(), 7500)
              tab.set_root(root)
              self.assertTrue(loaded.wait(3000))
              tab.tree.setCurrentItem(tab.tree.topLevelItem(1).child(0))
              self.assertEqual(tab.bar.value(), 3333)
              self.assertIn("2 B / 6 B (33,33%)", tab.summary.text())
              tab.tree.itemClicked.emit(tab.tree.topLevelItem(0), 0)
              self.assertTrue(loaded.wait(3000))
              self.assertEqual(tab.tree.topLevelItemCount(), 1)
          tab.close()
  ```

  Kiểm tra thứ tự theo byte bằng ba nhánh có 9 B, 1 KB và 2 KB. Mock `run_background` để giữ các callback của lần quét A và B. Gọi `set_root(A)`, `set_root(B)`, giao B trước rồi A và kiểm tra cây vẫn ở B. Lặp với `show_this_pc()` thay cho lần quét B. Với thư mục rỗng, kiểm tra thanh 0 và nhãn `0 B / 0 B (—)`. Dùng snapshot từ ca lỗi mở nhánh của Task 1 để kiểm tra cảnh báo và tooltip của nhánh lỗi.

- [x] **Chạy đỏ.** Xác nhận test thiếu `DiskUsageTab`.
- [x] **Dựng khung và điều phối tác vụ.** Dùng `QVBoxLayout`, một `QPushButton`, `QLabel` cho nhãn và trạng thái, `QProgressBar` thang 0–10.000 và `QTreeWidget`. Tắt nhãn mặc định của thanh để dùng `summary` làm nhãn. `showEvent` gọi `show_this_pc()` ở lần mở đầu tiên. Nút mở `QFileDialog.getExistingDirectory` và chỉ gọi `set_root` nếu kết quả có đường dẫn. Mỗi lần đổi chế độ tăng số phiên ngay trước khi tạo tác vụ.

  ```python
  self._generation += 1
  generation = self._generation

  def accept(result):
      if generation == self._generation:
          render(result)
          self.loaded.emit()

  def fail(message):
      if generation == self._generation:
          self.status.setText(message)
          self.loaded.emit()

  run_background(self, work, accept, fail)
  ```

- [x] **Hiển thị kết quả và xử lý chọn hàng.** Trong chế độ ổ đĩa, tạo một hàng cấp cao **This PC** và các ổ bên dưới, tự mở hàng này. Dùng cột tên, đã dùng, còn trống và tổng. Hàng ổ giữ `DriveUsage` trong `Qt.UserRole`. Trong chế độ thư mục, đặt **This PC** trước hàng gốc, dùng hai cột tên và dung lượng. Gán từng hàng thư mục một `Path`, chọn gốc sau khi dựng xong và dùng byte của gốc làm mẫu số. Tạo các hàng theo stack để cây sâu không phụ thuộc độ sâu đệ quy. Chặn tín hiệu chọn trong lúc thay cây. Bấm hoặc kích hoạt **This PC** trong chế độ thư mục để quay về danh sách ổ. Khi gốc không đọc được, chỉ giữ hàng quay về và hiển thị lỗi. Với lỗi một phần, giữ cảnh báo khi người dùng chuyển nhánh và gắn tooltip từ `errors_by_folder`.

  ```python
  children = sorted(entry.children, key=lambda child: (
      -snapshot.folders[child].total_bytes, child.name.casefold(), child.name,
  ))
  if isinstance(selected, DriveUsage):
      value, caption = format_ratio(selected.letter, selected.used_bytes, selected.total_bytes)
  elif isinstance(selected, Path):
      value, caption = format_ratio(
          selected.name or str(selected),
          snapshot.folders[selected].total_bytes,
          snapshot.folders[snapshot.root].total_bytes,
      )
  ```

- [x] **Nối cửa sổ và hướng dẫn.** Import `DiskUsageTab` trong `manager_image/image_folder_studio.py` và thêm dưới tab Quản lý thư mục.

  ```python
  self.tab_usage = DiskUsageTab()
  self.tabs.addTab(self.tab_usage, "Dung lượng")
  ```

  Thêm dòng **Dung lượng** trong mục Image Folder Studio của README với hướng dẫn xem ổ ở **This PC** và chọn thư mục để xem tỷ lệ theo gốc.

- [x] **Chạy xanh và kiểm tra tích hợp.** Chạy bộ unittest đầy đủ của Image Folder Studio. Trong PyQt5, mở tab thứ ba, kiểm tra **This PC**, bấm một ổ, chọn thư mục mẫu và thử bấm **This PC** khi còn đang quét. Kiểm tra lại thao tác chọn ảnh đối ứng giữa hai bên ở tab So sánh. Ghi rõ nếu kiểm tra ổ thật phải thay bằng danh sách giả lập do môi trường.
- [x] **Commit tab.** Kiểm tra diff đã stage, giữ riêng các hunk chọn ảnh đối ứng có từ trước. Dùng thông điệp `Add disk usage tab to Image Folder Studio`.
