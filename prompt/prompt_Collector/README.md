# Prompt Collector

Web UI chạy cục bộ để **gom, làm sạch và xuất prompt** tạo ảnh. Paste từng prompt vào, app tự dọn dẹp. Cuối buổi bạn xuất ra file TXT để đưa thẳng vào node **Text_Splitter** của ComfyUI (`Load_IO_Tony`), hoặc xuất JSON để lưu trữ.

Không cần cài đặt, không cần build, không cần Internet. Chỉ cần double-click file `dist/index.html`.

## Mục tiêu

- **Làm sạch prompt khi paste:**
  - Gộp các dòng trống liên tiếp (`\n\n`, `\n\n\n`, dòng chỉ có khoảng trắng) thành một `\n`. Nhờ vậy Text_Splitter không cắt nhầm một prompt thành hai.
  - Bỏ nguyên câu chứa từ khóa trong danh sách **Strip keywords**, ví dụ câu "Use face image of the uploaded photo…". Danh sách này bạn tự thêm hoặc bớt.
- **Tìm và thay thế ngay trong ô Paste:** thay từng từ bằng tay, hoặc lưu sẵn một danh sách cặp "tìm → thay". Mỗi lần paste, app tự quét danh sách và hỏi bạn trước khi thay.
- **Gắn trigger word lúc export:** ví dụ `Ivan_Ryo.`. Nếu prompt chưa mô tả nhân vật thì app thêm cả mô tả `A 25yo Asian young man.`. Trigger không bao giờ bị ghi vào nội dung prompt.
- **Gắn hậu tố lúc export:** một câu chung (ví dụ thông số máy ảnh, ánh sáng) được nối vào cuối mọi prompt khi bật. Câu này sửa được và cũng không ghi vào nội dung prompt.
- **Quản lý danh sách:** xem, sửa, sắp xếp lại, xóa (có Undo), và cảnh báo khi paste trùng.
- **Xuất file theo ngưỡng:** TXT và JSON được tự tách thành nhiều file khi số prompt vượt ngưỡng.
- **Tự lưu:** đóng cửa sổ giữa chừng thì lần mở sau dữ liệu vẫn còn.

## Cấu trúc thư mục

```
prompt_Collector/
├── dist/
│   ├── index.html   ← mở file này để chạy app (giao diện + phần gọi logic)
│   └── core.js      ← logic xử lý (bắt buộc nằm cạnh index.html)
├── test_core.mjs    ← test cho core.js (chỉ dành cho người sửa code)
└── README.md
```

## Cài đặt

Không cần cài gì. Bạn chỉ cần:

- **Trình duyệt:** Google Chrome hoặc Microsoft Edge bản mới (từ khoảng 122 trở lên; Chrome và Edge tự cập nhật nên thường đã đủ). Firefox và Safari không được hỗ trợ.
- **File:** hai file `index.html` và `core.js` nằm cùng một thư mục `dist/`.

Node.js **không** cần để dùng app. Nó chỉ cần khi bạn muốn chạy test sau khi sửa code (xem cuối file).

## Build ra folder `dist`

App **không có bước build**. Thư mục `dist/` chính là mã nguồn và cũng là bản chạy được: sửa thẳng `dist/index.html` hoặc `dist/core.js`, lưu lại, rồi tải lại trang (F5) là thấy thay đổi.

Muốn "đóng gói" để đem sang máy khác:

1. (Nên làm) Chạy test để chắc logic không hỏng, nếu máy có Node.js:

   ```bash
   cd prompt/prompt_Collector
   node test_core.mjs
   ```

2. Chép nguyên thư mục `dist/` (đủ 2 file `index.html` và `core.js`) sang máy kia, hoặc nén thành file zip bằng PowerShell:

   ```powershell
   cd prompt\prompt_Collector
   Compress-Archive -Path dist -DestinationPath prompt_Collector.zip -Force
   ```

   Bên máy nhận chỉ cần giải nén rồi mở `dist/index.html`.

## Cách sử dụng

### 1. Mở app

Double-click `dist/index.html`. Nếu file mở bằng trình duyệt khác, chuột phải → **Open with** → Chrome hoặc Edge.

### 2. Thêm prompt

1. Paste prompt vào ô **Paste prompt**.
2. Nhấn **Enter** để thêm. Muốn xuống dòng trong ô nhập thì dùng **Shift + Enter**.
3. Dòng nhỏ bên dưới ô nhập cho biết đã bỏ bao nhiêu câu và trigger nào sẽ được gắn.
4. Nếu prompt trùng với một prompt đã có (sau khi làm sạch), app hiện cảnh báo **Same as #N**. Chọn **Skip** để bỏ qua hoặc **Add anyway** để vẫn thêm.

Prompt mới nhất hiện ở **đầu** danh sách, ngay dưới ô nhập. Trang không tự cuộn và con trỏ vẫn ở ô nhập, nên bạn có thể paste tiếp liên tục.

### 3. Tìm và thay thế

Hàng ngay trên ô Paste có 2 ô và 3 nút. Chúng chỉ tác động lên **nội dung đang nằm trong ô Paste**, không đụng tới các prompt đã thêm vào danh sách.

- **Find…** + nút kính lúp: chọn (bôi đen) chỗ khớp tiếp theo trong ô Paste và báo `2 of 3`. Bấm lại để sang chỗ kế tiếp.
- **Replace with…** + nút mũi tên: thay **mọi** chỗ khớp trong ô Paste và báo `Replaced N`. **Ctrl + Z** trong ô Paste hoàn tác được.
- Nút **+**: lưu cặp đang gõ ("tìm → thay") vào **danh sách thay thế**.

Cách khớp: **nguyên từ, không phân biệt hoa thường**. Ví dụ `gym` khớp `Gym`, và khớp phần `gym` trong `gym-goer` (dấu `-` tách từ), nhưng không khớp `gyms`. Chữ tiếng Việt có dấu được tính là chữ, nên `ảnh` không khớp `ảnhh`. Để trống ô Replace with nghĩa là xoá từ đó.

**Danh sách thay thế** (nút ⇄ trên thanh công cụ, con số là số cặp):

- Thêm cặp ở cuối hộp thoại (**Add**), hoặc bấm **+** cạnh ô Find. Mỗi từ cần tìm chỉ có một cặp (không phân biệt hoa thường).
- Bấm **×** để xoá một cặp.
- **Mỗi lần paste**, app quét danh sách. Nếu prompt vừa paste chứa từ nào trong danh sách, một thanh báo hiện dưới ô Paste, liệt kê từng cặp kèm số lần xuất hiện, tất cả được tích sẵn:
  - Bỏ tích cặp nào không muốn thay, rồi bấm **Replace**.
  - **Skip** để giữ nguyên.
  - Nếu bạn gõ tiếp hoặc nhấn **Enter** để thêm prompt khi thanh báo còn hiện, prompt được giữ nguyên như đang thấy (coi như Skip).
- Việc thay diễn ra trước khi nhấn Enter, nên bước lọc Strip keywords luôn chạy trên nội dung đã thay.

### 4. Xem và sửa prompt

- Bấm một thẻ trong danh sách để mở nó ở khung bên phải. Phím **← / →** hoặc nút mũi tên chuyển giữa các prompt; số `N / Tổng` cho biết vị trí.
- Khung bên phải có ba tab:
  - **Cleaned**: nội dung đã làm sạch, sửa trực tiếp được. Prompt đã sửa tay hiện nhãn `edited`.
  - **Original**: bản gốc lúc paste, câu bị lọc được gạch đỏ.
  - **Export preview**: bản cuối cùng sẽ được xuất, đã gắn trigger và hậu tố. Tab này chỉ để xem.
- **Delete prompt** xóa prompt đang chọn. Thông báo hiện lên có nút **Undo** trong 5 giây.
- Kéo thả thẻ để đổi thứ tự.
- Số trên thẻ là **thứ tự khi export**: #1 là prompt cũ nhất, xuất đầu tiên.

### 5. Strip keywords (nút ✂)

Nút ✂ trên thanh công cụ mở danh sách từ khóa cần lọc. Mặc định gồm:

`uploaded photo`, `facial structure`, `exact body proportions`, `reference image`

- Câu nào chứa một trong các từ khóa (không phân biệt hoa/thường) sẽ bị bỏ **nguyên câu**.
- Thêm hoặc xóa từ khóa thì mọi prompt **chưa sửa tay** được lọc lại ngay. Prompt đã sửa tay giữ nguyên.

### 6. Trigger word

- Chọn trigger trong dropdown **Trigger** (hoặc **None** để tắt). Nút ✎ mở danh sách preset để thêm, sửa hoặc xóa.
- Mỗi preset gồm:
  - **Token**: ví dụ `Ivan_Ryo`.
  - **Description**: ví dụ `A 25yo Asian young man.`.
  - **Already described if prompt contains**: các cụm cách nhau bằng dấu phẩy, ví dụ `asian young man, young asian man, asian man`.
- Quy tắc gắn khi export:

| Prompt | Kết quả xuất |
|---|---|
| Không chứa cụm "đã mô tả" nào | `Ivan_Ryo. A 25yo Asian young man. <prompt>` |
| Có chứa một cụm "đã mô tả" | `Ivan_Ryo. <prompt>` |
| Đã có sẵn token `Ivan_Ryo` | `<prompt>` (không thêm gì) |

Trigger áp cho **toàn bộ** danh sách, kể cả prompt đã sửa tay. Đổi trigger lúc nào cũng được.

### 7. Hậu tố (Suffix)

- Nút **Suffix On / Off** trên thanh công cụ bật hoặc tắt hậu tố. Mặc định là **Off**.
- Nút ✎ cạnh đó mở hộp sửa câu hậu tố. Câu mặc định:

  `White balance 5500K, 50mm lens, f/1.8 aperture. Slightly blur the background for portrait shots. Remove unnecessary details; keep shadows natural and soft.`

  Bấm **Reset to default** để quay về câu này.
- Khi bật, hậu tố được nối vào **cuối mọi prompt lúc export**, sau trigger:
  - Prompt chưa kết thúc bằng `.`, `!` hoặc `?` thì app thêm `.` trước khi nối.
  - Prompt đã chứa nguyên câu hậu tố (không phân biệt hoa thường) thì không thêm lần nữa.
- Hậu tố **không** ghi vào nội dung prompt: tắt đi là file xuất trở lại như cũ. Xem trước ở tab **Export preview**; số ký tự ở dưới cũng đã tính hậu tố.

### 8. Xuất file

- **Prompts per file**: số prompt tối đa trong một file, mặc định 50. Danh sách hiện vạch chia `▲ file 02 · file 01 ▼` ở chỗ file sẽ được tách.
- **Export TXT**:
  - Mỗi prompt là một đoạn, các đoạn cách nhau đúng một dòng trống, đúng định dạng Text_Splitter đọc (`paragraph_sep = \n\n`).
  - Tên file: `prompt_20261021.txt`. Nếu có nhiều file: `prompt_20261021_01.txt`, `_02.txt`, …
- **Export JSON**: tách theo cùng ngưỡng. Mỗi prompt có bản xuất (`text`, đã gắn trigger và hậu tố), nội dung chưa gắn gì (`body`), bản gốc (`original`), các câu bị lọc (`removed`) và thời điểm thêm. Đầu file ghi trigger (`trigger`) và hậu tố (`suffix`, hoặc `null` khi tắt) đã dùng.
- File được tải về thư mục **Downloads** của trình duyệt. Lần đầu xuất nhiều file, Chrome/Edge sẽ hỏi cho phép tải nhiều file; chọn **Allow**.
- Prompt rỗng bị bỏ qua khi xuất. Export không xóa danh sách.
- **Clear list** xóa toàn bộ prompt (có hỏi xác nhận) nhưng giữ từ khóa, danh sách thay thế, trigger, hậu tố và ngưỡng.

### 9. Giao diện

Công tắc **Sunny / Sky** ở góc trên đổi bảng màu. Lựa chọn được nhớ cho lần mở sau.

### 10. Tự lưu

- **Lưu ở đâu:** mọi thay đổi (prompt, từ khóa, danh sách thay thế, trigger, hậu tố, theme) được lưu tự động vào **localStorage của trình duyệt** (dòng dưới tiêu đề ghi giờ lưu gần nhất). Mở lại file là dữ liệu quay về.
- **Mở nhiều tab:** các tab tự đồng bộ với nhau.
- **Dữ liệu không đọc được:** app giữ một bản sao ở key `promptCollector.v1.corrupt` rồi mới mở danh sách trống. Nếu ngay cả bản sao cũng không ghi được, app tạm dừng tự lưu (header ghi "Autosave paused") cho đến khi bạn bấm **Discard it**.
- Dữ liệu lưu từ bản cũ (chưa có danh sách thay thế và hậu tố) vẫn mở bình thường; hai mục mới tự lấy giá trị mặc định.

## Phím tắt

| Phím | Ở đâu | Tác dụng |
|---|---|---|
| **Enter** | ô Paste prompt | Thêm prompt vào danh sách |
| **Shift + Enter** | ô Paste prompt | Xuống dòng trong ô nhập |
| **Ctrl + Z** | ô Paste prompt | Hoàn tác lần Replace / thay từ danh sách |
| **Enter** | ô Find… | Tìm chỗ khớp tiếp theo |
| **Enter** | ô Replace with… | Thay tất cả chỗ khớp |
| **Enter** | ô thêm từ khóa / ô Replace with trong hộp danh sách thay thế | Thêm vào danh sách |
| **← / →** | ngoài các ô nhập | Chuyển prompt trước / sau ở khung bên phải |
| **Esc** | hộp thoại | Đóng hộp thoại |

## Đem folder sang máy khác có chạy được không?

**App thì chạy được.** Dữ liệu đang làm dở **không tự đi theo**.

- **Copy app:** copy cả thư mục `prompt_Collector` (hoặc chỉ `dist/` với đủ 2 file `index.html` và `core.js`) sang máy khác, rồi double-click `index.html`. Không cần cài gì thêm, không cần mạng. Xem thêm mục **Build ra folder `dist`** ở trên.
- **Hệ điều hành:** Windows chạy đúng như thiết kế. Trên macOS hoặc Linux app vẫn chạy với Chrome/Edge, nhưng font sẽ thay bằng font tương đương (Georgia, font hệ thống, Consolas hoặc monospace), nên giao diện hơi khác một chút.
- **Dữ liệu nằm trong trình duyệt, không nằm trong folder.** Danh sách prompt, từ khóa, danh sách thay thế, trigger, hậu tố và theme được lưu trong localStorage của trình duyệt trên máy đó. Copy folder không mang theo dữ liệu, và mở bằng trình duyệt khác (ví dụ Chrome thay vì Edge) cũng sẽ thấy danh sách trống.
- **App chưa có Import.** File TXT/JSON đã xuất không nạp ngược vào app được. Vì vậy hãy **Export** trước khi chuyển máy nếu bạn chỉ cần file kết quả.

Nếu muốn mang cả danh sách đang làm dở sang máy mới:

1. Trên máy cũ, mở app, nhấn **F12** → tab **Console**, gõ lệnh sau rồi Enter:

   ```js
   copy(JSON.stringify(localStorage.getItem("promptCollector.v1")))
   ```

   Dữ liệu đã nằm trong clipboard, dưới dạng một chuỗi bắt đầu và kết thúc bằng dấu `"`. Dán vào một file `.txt` để mang đi.
2. Trên máy mới, mở app, nhấn **F12** → **Console** và gõ `localStorage.setItem("promptCollector.v1", ` (có dấu phẩy và khoảng trắng ở cuối). Dán nguyên nội dung file vào ngay sau đó, kể cả hai dấu `"` ở đầu và cuối, gõ `)` rồi Enter. Tải lại trang (F5). Ví dụ:

   ```js
   localStorage.setItem("promptCollector.v1", "{\"version\":1,\"items\":[...]}")
   ```

   Lưu ý: lệnh này ghi đè danh sách đang có trên máy mới.

## Dành cho người sửa code

- `dist/core.js` chứa toàn bộ logic thuần, không có DOM: làm sạch, kiểm tra trùng, tìm/thay nguyên từ, quét danh sách thay thế, trigger, hậu tố, chia file, tạo nội dung TXT/JSON, đọc dữ liệu đã lưu. `dist/index.html` chứa giao diện và phần gọi các hàm đó.
- Giữ `<script src="core.js">` là script thường. Không dùng `type="module"`, vì Chrome chặn module khi mở bằng `file://`.
- Chạy test (cần Node.js):

  ```bash
  cd prompt/prompt_Collector
  node test_core.mjs
  ```

  Kết quả đúng: `core: all checks passed`.
- Thiết kế chi tiết nằm ở `docs/superpowers/specs/2026-10-08-prompt-collector-design.md` (v1) và `docs/superpowers/specs/2026-10-08-prompt-collector-v2-design.md` (v2). Tìm/thay và hậu tố được thêm sau, mô tả đầy đủ trong README này.
