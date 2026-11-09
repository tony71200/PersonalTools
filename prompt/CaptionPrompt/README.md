# Caption Prompt

Web UI chạy cục bộ, có 3 tab để làm việc với bộ ảnh và prompt đi kèm:

- **Captioned**: xem ảnh, zoom/kéo/crop ảnh, viết caption trong file `.txt` cùng tên, chèn nhanh các từ mẫu.
- **MiniMax H3**: mở file prompt `<tên ảnh>_H3_<sfw|nsfw>.txt`, tách thành 2 phần để sửa và copy nhanh, rồi lưu lại đúng thứ tự cũ.
- **Filt and Find**: xem cây thư mục kèm số ảnh, lọc các folder có ít ảnh, xem thumbnail.

App đọc và ghi **thẳng vào file trên ổ đĩa** của bạn. Không cần cài đặt, không cần build, không cần Internet.

## Cấu trúc thư mục

```
CaptionPrompt/
├── dist/
│   ├── index.html          ← mở file này để chạy app
│   ├── core.js             ← logic xử lý (tách file H3, lọc folder, ...)
│   ├── fs.js               ← đọc/ghi file, nhớ thư mục đã mở
│   ├── ui.js               ← cây thư mục, hộp hỏi, thông báo dùng chung
│   ├── viewer.js           ← khung xem ảnh: zoom, kéo, crop
│   ├── words.js            ← chip từ mẫu và cửa sổ ⚙
│   ├── tab-caption.js      ← Tab 1
│   ├── tab-minimax.js      ← Tab 2
│   ├── tab-filter.js       ← Tab 3
│   └── caption_words.json  ← bộ từ mẫu mặc định (có thể liên kết để dùng)
├── test_core.mjs           ← test cho core.js (chỉ dành cho người sửa code)
└── README.md
```

Mọi file trong `dist/` phải nằm cùng nhau.

## Cài đặt

Không cần cài gì. Bạn chỉ cần:

- **Trình duyệt:** Google Chrome hoặc Microsoft Edge bản mới. Firefox và Safari **không** chạy được, vì thiếu tính năng mở thư mục (File System Access API).
- Node.js **không** cần để dùng app. Nó chỉ cần khi chạy test sau khi sửa code (xem cuối file).

## Build ra folder `dist`

App **không có bước build**. Thư mục `dist/` chính là mã nguồn và cũng là bản chạy được: sửa thẳng các file trong `dist/`, lưu lại, rồi tải lại trang (F5) là thấy thay đổi.

Muốn "đóng gói" để đem sang máy khác:

1. (Nên làm) Chạy test để chắc logic không hỏng, nếu máy có Node.js 22 trở lên:

   ```bash
   cd prompt/CaptionPrompt
   node test_core.mjs
   ```

2. Chép nguyên thư mục `dist/` (đủ mọi file liệt kê ở trên) sang máy kia, hoặc nén thành file zip bằng PowerShell:

   ```powershell
   cd prompt\CaptionPrompt
   Compress-Archive -Path dist -DestinationPath CaptionPrompt.zip -Force
   ```

   Bên máy nhận chỉ cần giải nén rồi mở `dist/index.html` bằng Chrome hoặc Edge.

## Cách sử dụng

### Mở app

Mở `dist/index.html` bằng Chrome hoặc Edge (double-click; nếu file mở bằng trình duyệt khác thì chuột phải → **Open with** → Chrome/Edge).

Góc trên có:
- 3 nút chuyển tab **Captioned / MiniMax H3 / Filt and Find**.
- Công tắc màu **Sunny / Sky**.

App nhớ tab và màu đang chọn cho lần mở sau.

### Chọn thư mục (giống nhau ở cả 3 tab)

1. Bấm **Chọn thư mục**, chọn thư mục ảnh rồi bấm **Cho phép / Allow** khi trình duyệt hỏi quyền xem và sửa file.
2. Ô bên cạnh hiện tên thư mục. Trình duyệt không cho gõ đường dẫn tay, nên ô này chỉ để xem.
3. Lần sau mở app, mỗi tab có nút **Mở lại "<tên>"**. Bấm vào rồi cho phép là mở lại đúng thư mục cũ.

Lưu ý:
- Mỗi tab nhớ thư mục riêng.
- Chrome không cho mở một số thư mục hệ thống, như gốc ổ `C:\`, `C:\Users\...\AppData`, hoặc toàn bộ `Desktop` / `Documents`. Hãy chọn một thư mục con cụ thể.
- Thư mục có tên bắt đầu bằng dấu `.` bị bỏ qua.

Ảnh được nhận: `png`, `jpg`, `jpeg`, `webp`.

### Tab 1: Captioned

**Cây bên trái** chỉ hiện folder có ảnh.
- Chấm **đặc** là ảnh đã có file caption `<tên ảnh>.txt`; chấm **rỗng** là chưa có.
- Dòng trên cùng đếm số ảnh, ví dụ `248 ảnh · 230 có txt`.
- Click vào cây rồi dùng **↑ / ↓** để chuyển ảnh.

**Khung ảnh:**
- **Lăn chuột** để zoom quanh vị trí con trỏ. **Kéo chuột** để di chuyển ảnh. Nút `−` / `+` zoom; **Vừa khung** đưa ảnh về vừa khung.
- **✂ Crop** bật chế độ crop. Một khung 80% hiện sẵn, kèm kích thước thật (ví dụ `768×1024`).
  - Kéo 8 tay nắm để chỉnh, kéo bên trong khung để di chuyển, hoặc kéo ra ngoài để vẽ khung mới. Crop tự do, không khoá tỉ lệ.
  - Trong lúc crop vẫn zoom được bằng lăn chuột, và kéo ảnh bằng chuột giữa.
  - **Áp dụng** → **Ghi đè**: ảnh được cắt ở độ phân giải gốc và **ghi đè file gốc. Không hoàn tác được.**
  - Với PNG, metadata của ComfyUI (`prompt`, `workflow`, `parameters`) được giữ lại, nên vẫn kéo ảnh vào ComfyUI để mở workflow được. Với JPG/WebP, ảnh lưu ở chất lượng 0.95 và mất EXIF.
  - **Huỷ** hoặc phím **Esc** để thoát crop.

**Ô Prompt** là nội dung file `<tên ảnh>.txt`.
- Sửa xong bấm **Lưu** hoặc **Ctrl+S**. Dấu **●** nghĩa là chưa lưu.
- Ảnh chưa có txt: gõ nội dung rồi lưu, app tạo file mới. Để trống thì không tạo gì.
- Kiểu xuống dòng của file gốc (Windows CRLF hay LF) được giữ nguyên.
- Đang sửa dở mà chuyển ảnh, app hỏi **Lưu / Bỏ thay đổi / Huỷ**.

**Từ mẫu (chip):** click một chip để chèn nội dung của nó vào **vị trí con trỏ**. App tự thêm khoảng trắng nếu chữ bị dính. **Ctrl+Z** hoàn tác được.

**Nút ⚙** mở danh sách từ mẫu. Mỗi từ có **nhãn** (chữ trên chip) và **nội dung chèn**.
- Lần đầu, bấm **Liên kết file JSON** để chọn một file có sẵn (ví dụ `dist/caption_words.json`), hoặc **Tạo file mới**. App nhớ file này; mỗi lần mở app có thể phải bấm **Cho phép đọc …** một lần.
- Khi đã liên kết, mọi thay đổi (thêm, sửa, xoá) được **ghi thẳng vào file** đó.
- **Import JSON** gộp thêm từ một file khác; từ trùng nhãn (không phân biệt hoa thường) bị bỏ qua.
- Chưa liên kết file thì app dùng bộ từ mặc định và không cho sửa.

Định dạng file từ mẫu:

```json
{
  "version": 1,
  "words": [
    { "label": "Ivan", "text": "Ivan_Ryo, a 25yo Asian young man" }
  ]
}
```

**Logger** ở cuối ghi lại mọi việc kèm giờ: nạp thư mục, lưu/tạo txt, crop, đọc/ghi file từ mẫu, và mọi lỗi. Giữ 200 dòng gần nhất; **Xoá log** để dọn.

### Tab 2: MiniMax H3

**Cây bên trái:**
- Ảnh có file prompt H3 được **tô sáng**, kèm tag `sfw`, `nsfw`, hoặc `3 bản` nếu có nhiều file. Ảnh không có H3 hiện mờ.
- File được nhận theo mẫu `<tên ảnh>_H3_<sfw|nsfw>[_hậu tố].txt`, không phân biệt hoa thường. Ví dụ `ABC_H3_sfw.txt` hay `ABC_H3_nsfw_v2.txt`.

**Bên phải:**
- Ảnh có nhiều file H3 thì có combobox **Bản** để chọn file. Bản gốc luôn đứng trước bản `_v2`.
- Hai ô soạn thảo:
  - **CHARACTER & SCENE DEFINITION**
  - **SHOT STRUCTURE — MINIMAX H3**
- Mỗi ô có số ký tự và nút **Copy**. Copy chỉ chép nội dung, không kèm dòng tiêu đề.
- **Lưu** hoặc **Ctrl+S** ghi lại file. Các dòng tiêu đề, dấu `---`, dòng trống và kiểu xuống dòng được giữ nguyên; chỉ phần bạn sửa thay đổi.

App đọc được 3 dạng file:

| Dạng | Cách nhận biết | Chỗ tách |
|---|---|---|
| Tiêu đề thường | dòng `CHARACTER & SCENE DEFINITION` và `SHOT STRUCTURE — MINIMAX H3` | tại 2 dòng tiêu đề |
| Tiêu đề Markdown | `# CHARACTER ...`, có `---` ngăn cách | tại 2 dòng tiêu đề; `---` giữa các shot vẫn nằm trong phần 2 |
| Không có tiêu đề | bắt đầu ngay bằng `subject_definitions:` | tại dòng `[SHOT 01 ...]` đầu tiên |

Nếu không nhận ra cấu trúc nào, cả file nằm ở ô 1, ô 2 bị khoá, và app hiện cảnh báo. Lưu vẫn không làm hỏng file.

### Tab 3: Filt and Find

**Cây bên trái chỉ hiện folder.**
- Mỗi folder có số ảnh **nằm trực tiếp** trong nó và số folder con, ví dụ `12 ảnh · 3 folder`. Folder không có folder con chỉ hiện `12 ảnh`.
- Nhập số N vào ô **Số ảnh ≤**, bấm **Filt** hoặc Enter.
  - Folder khớp là folder có từ 1 đến N ảnh; số đếm của nó được tô màu.
  - Folder cha của folder khớp hiện mờ để cây liền mạch. Các folder khác bị ẩn.
  - Dòng trên cùng ghi `Khớp m / tổng folder`.
- **Bỏ lọc** để hiện lại toàn bộ.
- Click vào cây rồi dùng **↑ / ↓** để chuyển folder, **← / →** để đóng/mở folder đang chọn.

**Bên phải** là lưới thumbnail của folder đang chọn. Ảnh chỉ được nạp khi cuộn tới, nên folder nhiều ảnh vẫn mượt. Click thumbnail không làm gì.

## Phím tắt

| Phím / thao tác | Ở đâu | Tác dụng |
|---|---|---|
| **Ctrl + S** | mọi tab | Lưu file đang sửa (caption ở Tab 1, file H3 ở Tab 2) |
| **↑ / ↓** | cây bên trái (click vào cây trước) | Chuyển ảnh trước / sau (Tab 1, 2), folder trước / sau (Tab 3) |
| **← / →** | cây ở Tab 3 | Đóng / mở folder đang chọn |
| **Lăn chuột** | khung ảnh Tab 1 | Zoom quanh vị trí con trỏ |
| **Kéo chuột trái** | khung ảnh Tab 1 | Di chuyển ảnh (khi không ở chế độ crop) |
| **Kéo chuột giữa** | khung ảnh Tab 1 | Di chuyển ảnh (cả khi đang crop) |
| **Esc** | khung ảnh Tab 1 | Thoát chế độ crop |
| **Ctrl + Z** | ô Prompt Tab 1 | Hoàn tác, kể cả lần chèn chip từ mẫu |
| **Enter** | ô Số ảnh ≤ (Tab 3) | Chạy Filt |
| **Enter** | ô Nội dung chèn trong cửa sổ ⚙ | Thêm từ mẫu |
| **Esc** | hộp thoại | Đóng hộp thoại |

## Dữ liệu được lưu ở đâu?

- **Caption, file H3, ảnh crop, file từ mẫu:** ghi thẳng vào file thật trên ổ đĩa.
- **Thư mục đã mở và file từ mẫu đã liên kết:** trình duyệt nhớ trong IndexedDB (`captionPrompt`). Đây chỉ là "lối tắt" để bấm **Mở lại**, không chứa nội dung file.
- **Tab và màu đang chọn:** `localStorage` (key `captionPrompt.v1`).

Vì vậy copy thư mục `CaptionPrompt` sang máy khác là chạy được ngay. Chỉ có các nút **Mở lại** là bắt đầu trống: chọn lại thư mục và liên kết lại file từ mẫu một lần.

## Lưu ý an toàn

- **Crop ghi đè ảnh gốc, không hoàn tác được.** Nếu cần giữ bản gốc, hãy sao lưu thư mục trước.
- Nếu app không đọc được một file txt, ô soạn thảo bị khoá, để không vô tình ghi đè file đó.
- Đóng tab khi còn thay đổi chưa lưu, trình duyệt sẽ hỏi xác nhận.

## Dành cho người sửa code

- `dist/core.js` chứa toàn bộ logic thuần, không có DOM: ghép ảnh với txt, nhận tên file H3, tách/ghép H3 (giữ nguyên từng byte phần không sửa), lọc cây thư mục, chèn từ mẫu, đọc file từ mẫu, chép metadata PNG.
- Mỗi tab có `init(el)` trả về `{ open(handle), isDirty?, save? }`, gom vào `window.tabs`. Gọi `tabs.<caption|minimax|filter>.open(handle)` với một `FileSystemDirectoryHandle` (ví dụ lấy từ `navigator.storage.getDirectory()`) để thử app mà không cần hộp thoại chọn thư mục.
- Giữ các `<script src>` là script thường. Không dùng `type="module"`, vì Chrome chặn module khi mở bằng `file://`.
- Chạy test (cần Node.js 22 trở lên, vì test dùng `zlib.crc32`):

  ```bash
  cd prompt/CaptionPrompt
  node test_core.mjs
  ```

  Kết quả đúng: `core tests passed`.
- Thiết kế: `docs/superpowers/specs/2026-10-21-caption-prompt-design.md`. Kế hoạch triển khai: `docs/superpowers/plans/2026-10-21-caption-prompt.md`.
