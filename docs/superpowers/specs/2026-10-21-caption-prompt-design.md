# CaptionPrompt: Design

Date: 2026-10-21
Location: `prompt/CaptionPrompt/` (sibling of `prompt/prompt_Collector/`)
Style reference: `prompt/prompt_Collector/dist/index.html` (Sunny/Sky themes, rounded raised panels, gradient primary buttons, Sitka/Segoe/Cascadia fonts, toast).

## Goals

A local tool for working on image datasets, with three tabs. Each tab has the same left column (a folder picker and a tree) and its own right side.

1. **Captioned.** Browse images, view/zoom/pan/crop the image, and edit its same-name caption `.txt`. Insert saved snippets at the cursor. A small logger shows what happened.
2. **MiniMax H3.** Browse images that have `<image>_H3_<sfw|nsfw>[_suffix].txt` prompt files. Show the image and the file split into two editable sections, `CHARACTER & SCENE DEFINITION` and `SHOT STRUCTURE — MINIMAX H3`. Each section has a Copy button. Saving writes the file back with its original structure.
3. **Filt and Find.** A folder-only tree that shows image counts. Filter it to folders with 1 to N images. Show thumbnails of the selected folder.

## Platform

- Plain HTML + classic `<script src>` files, opened from disk (`file://`) in Chrome or Edge. No server, no build, no npm dependencies. This is the same approach as prompt_Collector.
- **No ES modules.** Chrome blocks module scripts on `file://`. Each script attaches one global (`window.CaptionCore`, `window.CaptionFS`, ...).
- File access uses the File System Access API: `showDirectoryPicker`, `showOpenFilePicker`, `showSaveFilePicker`, `FileSystemFileHandle.createWritable`.
- A browser cannot open a typed path. The folder textbox is **read-only** and shows the chosen folder name. The button next to it opens the folder picker.
- Firefox and Safari are not supported (they lack `showDirectoryPicker`).
- **First implementation step:** confirm that `showDirectoryPicker` and `createWritable` work from a `file://` page in the user's Chrome. If they do not, stop and report back before building further.

## Files

```
prompt/CaptionPrompt/
  dist/
    index.html          markup + CSS (themes copied from prompt_Collector) + tab switching, theme, toast
    core.js             pure logic, no DOM; window.CaptionCore, and module.exports for node
    fs.js               folder scan, read/write, remembered handles (IndexedDB); window.CaptionFS
    tab-caption.js      Tab 1
    tab-minimax.js      Tab 2
    tab-filter.js       Tab 3
    caption_words.json  default snippet file, same content as DEFAULT_WORDS
  test_core.mjs         node test for core.js (run: node test_core.mjs from prompt/CaptionPrompt)
```

Load order in `index.html`: `core.js`, `fs.js`, then the three tab scripts. Each tab script exports `init(rootEl)` and keeps its own state. Switching tabs never reloads or discards anything.

## Shared layout and behavior

- **Masthead:** logo tile, title "Caption Prompt", a pill switch with the three tabs (same style as the theme switch), and the Sunny/Sky switch.
- **Body:** two columns. Left column is about 340px wide. Right column fills the rest. Both are `.panel` cards. The page does not scroll; the tree, the thumbnail grid and the editors scroll inside their panels.
- **Folder row** (all tabs): read-only textbox, a **Chọn thư mục** button, and, when a folder from last time is remembered, a **Mở lại "<name>"** button. That button calls `requestPermission` (it needs a click) and rescans.
- **Persistence:**
  - `localStorage["captionPrompt.v1"] = { theme, tab }`.
  - IndexedDB stores one directory handle per tab (`dir.caption`, `dir.minimax`, `dir.filter`) and the snippet file handle (`wordsFile`).
- **Unsaved edits:** a dirty editor shows `●` next to its title. Switching to another image, or to another H3 variant, while dirty opens a `<dialog>` with **Lưu**, **Bỏ thay đổi**, **Huỷ**. `beforeunload` warns if any tab is dirty. Ctrl+S saves in the active tab.
- **Tree keyboard:** with the tree focused, ↑/↓ moves to the previous/next image (Tabs 1 and 2) or folder (Tab 3), and ←/→ collapses/expands a folder.
- **Feedback:** Tab 1 has a logger. Tabs 2 and 3 use a toast, as in prompt_Collector. Errors always show the file name and a short reason, never a raw stack.
- **Images:** shown through object URLs, revoked when replaced. Accepted extensions: `png`, `jpg`, `jpeg`, `webp` (case-insensitive).
- **Text files:** read as UTF-8 (`TextDecoder` drops a BOM), written as UTF-8 without BOM. The editors always work with `\n`. On save, text is converted back to the file's original line ending (`\r\n` if the original contained `\r\n`, otherwise `\n`). New files use `\n`.

## Folder scan (fs.js)

`scanDir(dirHandle) -> Node`, recursive, names only (no file reads):

```js
Node = {
  name: "Ryo",
  path: "day_52_1/Ryo",          // relative to the picked root; "" for the root itself
  handle: FileSystemDirectoryHandle,
  dirs: [Node],                   // sorted by name, natural order (numbers compared as numbers)
  files: [{ name, handle }]       // all files, sorted the same way
}
```

Folders whose names start with `.` are skipped. A folder that cannot be read is logged and skipped; the scan continues.

Other functions: `pickDir()`, `pickFile(opts)`, `createFile(opts)`, `ensurePermission(handle, "readwrite")`, `readText(fileHandle)`, `writeText(dirHandle, name, text)` (creates the file if missing), `writeBlob(fileHandle, blob)`, `remember(key, handle)`, `recall(key)`.

## Tab 1: Captioned

### Left column

- Summary line: `248 ảnh · 230 có txt`.
- Tree of folders and images. Folders with no images anywhere below them are hidden.
- An image that has `<base>.txt` in the same folder shows a filled accent dot. One without shows a hollow dot and muted text.
- The selected image is highlighted.

### Image viewer

- Takes about 55% of the right column's height. Toolbar: `−`, zoom percent, `+`, **Vừa khung** (fit), and a **Crop** toggle.
- The wheel zooms around the cursor (10% to 800%). Dragging pans. A new image opens at "fit".
- **Crop mode:**
  - Drag on the image to draw a rectangle. It has 8 handles and can be moved by dragging inside it.
  - A label shows its size in original image pixels (`768×1024`). The crop is free-form, with no fixed aspect ratio.
  - Zoom and pan still work with the wheel and with the middle mouse button.
  - **Áp dụng** asks "Ghi đè <file>?" in a `<dialog>`. On yes, the image is decoded at full resolution, the region is drawn to a canvas, encoded in the same format and written over the original file.
    - PNG: encoded losslessly, then `copyPngText` copies the original's text chunks (ComfyUI `prompt`, `workflow`, `parameters`) into the new file.
    - JPG/WebP: quality 0.95. EXIF metadata is lost; this is accepted.
  - **Huỷ** or Esc leaves crop mode without changes.
  - After a write, the viewer reloads the file and the log records `Crop <w>×<h> <file>`.
  - There is no undo. The overwrite is deliberate and the confirm dialog is the only guard.

### Caption editor

- A mono textarea holding `<base>.txt`. That file is unrelated to the `_H3_*.txt` files used by Tab 2.
- When the file is missing, the editor is empty with the placeholder "Chưa có file txt, sẽ tạo khi lưu". Saving an empty editor for a missing file creates nothing.
- **Lưu** button and Ctrl+S. Saving a new file updates the tree dot.

### Snippets

- A row of chips under the editor, one per word, showing its `label`.
- Clicking a chip inserts its `text` at the cursor, or replaces the selection. The insert uses `document.execCommand("insertText")`, so Ctrl+Z undoes it. `padSnippet` adds a space before and/or after the snippet when it would otherwise touch a neighboring word.
- A ⚙ button opens a `<dialog>` with:
  - The list of words (label + text), editable in place, with delete per row and an add row.
  - **Liên kết file JSON**: pick an existing JSON file, or create one (pre-filled with the defaults). The handle is remembered. Every change in the dialog is written to that file at once.
  - **Import JSON**: pick another file and merge its words. A word whose label already exists (case-insensitive) is skipped. The log reports `Import: +3, bỏ qua 1`.
- **Without a linked file:** chips show `DEFAULT_WORDS`, and the dialog shows "Chưa liên kết file JSON". Editing then requires linking first. When a remembered handle needs permission, a **Cho phép đọc caption_words.json** button appears above the chips.
- **File format:**

  ```json
  { "version": 1, "words": [ { "label": "Ivan", "text": "Ivan_Ryo, a 25yo Asian young man" } ] }
  ```

  Written with 2-space indent. On read, entries with an empty label or text are dropped. A file that is not valid JSON, or has no `words` array, is rejected with a log error and nothing changes.

### Logger

- A panel about 120px tall at the bottom of the right column, mono, newest line at the bottom, auto-scrolls.
- Each line has a time and a level: info (secondary color), ok `✓` (success), error `✕` (danger). It keeps the last 200 lines and has a **Xoá log** button.
- It records: folder loaded (image and txt counts), txt saved/created, crop applied, JSON linked/imported/written, and every error.

## Tab 2: MiniMax H3

### File naming

`parseH3Name(name)` matches `/^(.+)_H3_(sfw|nsfw)(?:_([^.]+))?\.txt$/i` and returns `{ base, rating: "sfw"|"nsfw", suffix }` or `null`. The file belongs to the image in the same folder whose name without extension equals `base` (case-insensitive).

| File | Result |
|---|---|
| `A_H3_sfw.txt` | `{ base: "A", rating: "sfw", suffix: "" }` |
| `A_H3_NSFW_v2.txt` | `{ base: "A", rating: "nsfw", suffix: "v2" }` |
| `A_H3.txt`, `A_H3_safe.txt`, `A.txt` | `null` |

### Left column

- Summary line: `3 ảnh có H3 · 5 file txt`.
- Tree of folders and images, with the same hiding rule as Tab 1.
- An image with at least one H3 file is highlighted with an accent wash and a tag: the rating (`sfw` or `nsfw`) when it has one file, or `<n> bản` when it has several. An image without H3 files is muted. It can still be selected; the right side then says "Ảnh này chưa có file H3".

### Right column

- **Top row:** a variant `<select>` (shown only when the image has 2 or more H3 files, sorted by file name), a rating tag, `●` when dirty, and **Lưu**.
- **Body:** the image at fit size in a column about 260px wide. Next to it, two stacked editors:
  - `CHARACTER & SCENE DEFINITION`
  - `SHOT STRUCTURE — MINIMAX H3`
  
  Each editor header shows its character count and a **Copy** button. Copy puts that editor's body (without the heading) on the clipboard. The button shows "Đã copy" for 1.5s and a toast confirms.
- No zoom or crop here.

### Split and join (core.js)

`splitH3(text) -> { parts: [head, body1, mid, body2, tail], eol, recognized }`, where `joinH3(parts) === text` for any input. `eol` is `"\r\n"` or `"\n"`.

The text is split into lines (keeping line endings). Boundaries:

1. **Heading 1:** the first line matching `/^\s*#*\s*CHARACTER\s*&\s*SCENE\s+DEFINITION\s*$/i`.
2. **Heading 2:** the first later line matching `/^\s*#*\s*SHOT\s+STRUCTURE\b/i`. If there is none, section 2 starts at the first line matching `/^\s*\[SHOT\s+\d+/i`, and that line belongs to `body2`.
3. **`head`:** everything up to and including heading 1, plus the blank lines right after it. With no heading 1, `head` is empty and `body1` starts at line 1.
4. **`mid`:** the trailing run of blank lines and `---` lines before section 2 starts, plus heading 2 and the blank lines right after it. With no heading 2, `mid` is only that trailing run.
5. **`body1`:** the lines between `head` and `mid`.
6. **`tail`:** the run of blank lines at the end of the file.
7. **`body2`:** the lines between `mid` and `tail`.
8. **No section 2 found** (no heading 2 and no `[SHOT` line): `recognized = false`, `body1` is everything after `head` (or the whole file), and `mid`/`body2` are empty. The UI shows "Không nhận ra cấu trúc H3, cả file nằm ở ô 1" and saves normally.

Editors show `body1`/`body2` with `\r\n` converted to `\n` and the final line ending removed. `setH3Bodies(split, b1, b2) -> string` puts the edited bodies back:

- It converts `\n` to `eol`. Each edited body gets back the final line ending its original had. If the original body was empty, a non-empty edit gets `eol`. This keeps the blank-line spacing around the headings and keeps a file with no final newline unchanged.
- Then it joins the five parts in their original order.

The three sample layouts this must handle:

| Layout | Example | head | mid |
|---|---|---|---|
| Plain headings | day_52 | `CHARACTER & SCENE DEFINITION` + blank | blank + `SHOT STRUCTURE — MINIMAX H3` + blank |
| Markdown headings with `---` | day_53 sfw, nsfw_v2 | `# CHARACTER ...` + blank | blank + `---` + blank + `# SHOT STRUCTURE ...` + blank |
| No headings | day_56 Rennoir2 | empty | the blank line before `[SHOT 01 ...]` |

`---` lines inside `body2` (between shots) stay in `body2`.

## Tab 3: Filt and Find

### Left column

- Folder row, then a filter row: a number input (min 1, step 1, default 5), a **Filt** button, and a **Bỏ lọc** button. Enter in the input runs Filt.
- A folder-only tree, starting at the picked root. Each row shows `countLabel(node)`:
  - `"<i> ảnh · <d> folder"` when the folder has subfolders.
  - `"<i> ảnh"` when it has none.
  
  `i` counts images directly in the folder. `d` counts direct subfolders.
- **Filt with N:**
  - `filterTree(root, N)` returns `{ matched: Set<path>, visible: Set<path> }`. A folder matches when `1 <= i <= N`.
  - Visible folders are the matched ones plus all their ancestors. Matched rows show their count in an accent pill. Ancestor-only rows are muted. Everything else is hidden.
  - A summary shows `Khớp <m> / <total> folder`. With no matches the tree shows "Không có folder nào có 1 đến N ảnh".
- **Bỏ lọc** shows all folders again.

### Right column

- Header: the folder path relative to the root, and its image count.
- A thumbnail grid, `repeat(auto-fill, minmax(140px, 1fr))`. Each cell is a 3:4 `object-fit: cover` image with the file name below, ellipsized, with the full name in `title`.
- Thumbnails load lazily: an `IntersectionObserver` creates the object URL when a cell scrolls near the viewport. All URLs are revoked when the folder changes.
- Clicking a thumbnail does nothing.
- A folder with no images shows "Folder này không có ảnh".

## core.js API (tested)

| Function | Purpose |
|---|---|
| `isImage(name)` | Extension check for png/jpg/jpeg/webp. |
| `baseName(name)` | File name without its last extension. |
| `naturalCompare(a, b)` | Sort names with numbers compared as numbers. |
| `pairFolder(fileNames)` | `[{ image, caption: name\|null, h3: [{ name, rating, suffix }] }]` for one folder. |
| `parseH3Name(name)` | See Tab 2. |
| `splitH3(text)`, `joinH3(parts)`, `setH3Bodies(split, b1, b2)` | See Tab 2. |
| `detectEol(text)`, `toEol(text, eol)` | Line-ending detection and conversion. |
| `filterTree(root, max)`, `countLabel(node)` | See Tab 3. The tree argument has the `Node` shape without handles. |
| `padSnippet(before, after, snippet)` | Returns the snippet with a leading space if `before` ends in a non-space character other than `(`, and a trailing space if `after` starts with a character other than whitespace or `,.;:!?)`. |
| `DEFAULT_WORDS`, `parseWords(jsonText)`, `mergeWords(current, incoming)` | Snippet file read/validate, and merge returning `{ words, added, skipped }`. |
| `copyPngText(srcBytes, dstBytes)` | Returns `dstBytes` with every `tEXt`/`iTXt`/`zTXt` chunk from `srcBytes` inserted right after `IHDR`. Chunks are copied byte for byte, CRC included. If either input is not a PNG, it returns `dstBytes` unchanged. |

## Testing

`node test_core.mjs` (no dependencies) covers:

- **H3 round trip:** for each of the three layouts, using hand-written fixtures with `\r\n` that mirror the sample structure, `joinH3(splitH3(t).parts) === t`. `setH3Bodies` with the unchanged bodies returns `t` exactly. Editing one body changes only that region. `---` between shots stays in body 2. Unrecognized text round-trips with `recognized === false`.
- **Names:** `parseH3Name` table above. `pairFolder` pairs captions and H3 files case-insensitively, and ignores a `.txt` with no image.
- **Filter:** counts, ancestors kept, `0`-image folders never match, the boundary `i === N` matches, `countLabel` both forms.
- **Snippets:** `padSnippet` at the start, middle and end of text, and next to punctuation. `parseWords` rejects bad JSON and a missing `words` array, and drops empty entries. `mergeWords` skips duplicate labels case-insensitively.
- **PNG:** build a tiny PNG in the test (using `node:zlib` for IDAT and a CRC helper) with `tEXt` `prompt` and `workflow` chunks, plus a second PNG without them. After `copyPngText`, the second has both chunks after `IHDR`, still starts with the PNG signature, and still ends with `IEND`. Non-PNG input is returned unchanged.

**Manual check in Chrome,** on a copy of `H:\004_Learn\PostIG\day_52_1`, `day_53_1` and `day_56_1` (never the originals):

- Crop a PNG, then confirm with Pillow that `prompt`/`workflow`/`parameters` are still in `Image.open(...).info`.
- Edit and save one body of each H3 layout. A diff with the original must show only that body changed.
- Run Filt on `H:\004_Learn\PostIG` with a few values of N.

DOM and file-access code has no automated tests.

## Out of scope

- Typing a path into the folder textbox (browsers cannot open a typed path).
- Undo after crop, rotate/flip/resize, crop aspect presets.
- Renaming, deleting or moving files.
- Per-shot copy buttons in Tab 2 (one Copy per section was chosen).
- Thumbnail click actions in Tab 3.
- EXIF preservation for JPG/WebP crops.
- Firefox/Safari support.
