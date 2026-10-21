# CaptionPrompt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local page (`prompt/CaptionPrompt/dist/index.html`, opened from disk in Chrome/Edge) with three tabs: Captioned (image + same-name caption txt, zoom/pan/crop, snippet chips, logger), MiniMax H3 (split `_H3_*.txt` into two editable sections with Copy, saved back in original order), and Filt and Find (folder tree with image counts, filter by count, thumbnail grid).

**Architecture:** Classic `<script src>` files, no build, no modules (Chrome blocks modules on `file://`). `core.js` is pure logic tested by `node test_core.mjs`. `fs.js` wraps the File System Access API and IndexedDB. `ui.js` holds pieces shared by all tabs (tree, folder row, dialogs, toast). `viewer.js` is the zoom/pan/crop widget and `words.js` the snippet chips and word-list dialog. Each tab lives in its own script and exposes `init(el) -> { open(handle), isDirty?, save? }`. `index.html` holds all markup and CSS and a small boot script.

**Tech Stack:** Plain HTML/CSS/ES2022 JavaScript, Chrome/Edge, File System Access API, IndexedDB. Node 22 (installed, has `zlib.crc32`) only for `test_core.mjs`. Python 3.12 + Pillow (installed) only for the final manual metadata check.

**Spec:** `docs/superpowers/specs/2026-10-21-caption-prompt-design.md`

## Global Constraints

- Runs by opening `dist/index.html` from disk in Chrome/Edge. No server, no build, no npm packages, no network requests, system fonts only.
- Scripts are classic `<script src>`; no `type="module"`. Load order: `core.js`, `fs.js`, `ui.js`, `viewer.js`, `words.js`, `tab-caption.js`, `tab-minimax.js`, `tab-filter.js`, then the inline boot script.
- UI text is Vietnamese, exactly as written in this plan. Heading strings `CHARACTER & SCENE DEFINITION` and `SHOT STRUCTURE — MINIMAX H3` stay English.
- Image extensions: `png`, `jpg`, `jpeg`, `webp` (case-insensitive). H3 file regex: `/^(.+)_H3_(sfw|nsfw)(?:_([^.]+))?\.txt$/i`.
- Text files are read with `Blob.text()` (UTF-8, BOM dropped) and written as UTF-8 without BOM. Editors use `\n`; saving converts back to the file's original line ending (`\r\n` if the original contained one), and new files use `\n`.
- `localStorage["captionPrompt.v1"] = { theme: "sunny"|"sky", tab: "caption"|"minimax"|"filter" }`. IndexedDB database `captionPrompt`, store `handles`, keys `dir.caption`, `dir.minimax`, `dir.filter`, `wordsFile`.
- Themes and component styles are copied from `prompt/prompt_Collector/dist/index.html` (Sunny/Sky tokens, `.btn`, `.panel`, `.label`, `textarea`, `dialog`, `.toast`).
- Crop overwrites the original file after a confirm dialog. PNG crops keep every `tEXt`/`iTXt`/`zTXt` chunk. JPG/WebP use quality 0.95.
- Work on branch `ver004`. Every commit message ends with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## File Structure

```
prompt/CaptionPrompt/
  dist/
    index.html          markup for all tabs + CSS + boot script (Task 4)
    core.js             pure logic, window.CaptionCore + module.exports (Tasks 1-3)
    fs.js               scan/read/write + remembered handles, window.CaptionFS (Task 4)
    ui.js               toast, ask dialog, confirmLeave, folderRow, tree, window.CaptionUI (Task 4)
    viewer.js           zoom/pan/crop widget, window.CaptionViewer (Task 7)
    words.js            snippet chips + word-list dialog, window.CaptionWords (Task 8)
    tab-caption.js      Tab 1, window.CaptionTab (Task 7, wired to words in Task 8)
    tab-minimax.js      Tab 2, window.MiniMaxTab (Task 6)
    tab-filter.js       Tab 3, window.FilterTab (Task 5)
    caption_words.json  default word file (Task 8)
  test_core.mjs         node test_core.mjs (Tasks 1-3)
README.md               add the folder to the tree (Task 9)
```

`ui.js`, `viewer.js` and `words.js` are not in the spec's file list. They split shared or self-contained parts out of the tab scripts so each file has one job. Behavior is unchanged.

All commands run from the repo root `D:\001_PersonalProject\PersonalTools` unless stated otherwise.

## How to check UI tasks (4-8)

An agent cannot click the native folder picker, so UI checks use the browser's private file system (OPFS) instead of real folders. Nothing on disk is touched.

1. Serve the page in the background:

   ```bash
   python -m http.server 8765 -d prompt/CaptionPrompt/dist
   ```

2. Open `http://localhost:8765/` in the built-in browser.
3. Run this seed script with the browser JavaScript tool. It wipes OPFS, writes a small `PostIG` tree, and leaves its handle in `window.seedRoot`:

   ```js
   const R = await navigator.storage.getDirectory();
   for await (const k of R.keys()) await R.removeEntry(k, { recursive: true });
   async function put(path, data) {
     const p = path.split("/"); let d = R;
     for (const s of p.slice(0, -1)) d = await d.getDirectoryHandle(s, { create: true });
     const w = await (await d.getFileHandle(p.at(-1), { create: true })).createWritable();
     await w.write(data); await w.close();
   }
   async function png(w, h, color) {
     const c = Object.assign(document.createElement("canvas"), { width: w, height: h });
     const g = c.getContext("2d"); g.fillStyle = color; g.fillRect(0, 0, w, h);
     g.fillStyle = "#fff"; g.fillRect(w / 4, h / 4, w / 2, h / 2);
     return new Promise(r => c.toBlob(r, "image/png"));
   }
   const A = "CHARACTER & SCENE DEFINITION\r\n\r\nA man.\r\n\r\nSHOT STRUCTURE — MINIMAX H3\r\n\r\n[SHOT 01 | DURATION: 10s | PRIMARY CAMERA SETUP: close-up]\r\nHe waves.\r\n";
   const B = "# CHARACTER & SCENE DEFINITION\r\n\r\n**summary:**\r\n\r\nA man dances.\r\n\r\n---\r\n\r\n# SHOT STRUCTURE — MINIMAX H3\r\n\r\n[SHOT 01 | DURATION: 8s | PRIMARY CAMERA SETUP: dolly]\r\n\r\nStep one.\r\n\r\n---\r\n\r\n[SHOT 02 | DURATION: 7s | PRIMARY CAMERA SETUP: medium]\r\n\r\nStep two.\r\n";
   const H = "subject_definitions:\r\n\r\nA swimmer.\r\n\r\n[SHOT 01 | DURATION: 12s | PRIMARY CAMERA SETUP: mirror]\r\n\r\nHe waves.\r\n";
   await put("PostIG/day_52_1/Ryo/A.png", await png(300, 400, "#f80"));
   await put("PostIG/day_52_1/Ryo/A.txt", "Ivan_Ryo, a 25yo Asian young man\r\n");
   await put("PostIG/day_52_1/Ryo/A_H3_sfw.txt", A);
   await put("PostIG/day_53_1/Ryo/B.png", await png(400, 300, "#08f"));
   await put("PostIG/day_53_1/Ryo/B_H3_nsfw.txt", B);
   await put("PostIG/day_53_1/Ryo/B_H3_nsfw_v2.txt", B.replace("Step two.", "Step two, v2."));
   await put("PostIG/day_53_1/Ryo/B_H3_sfw.txt", H);
   await put("PostIG/day_56_1/Rennoir2/C.png", await png(200, 200, "#2a4"));
   await put("PostIG/day_56_1/Rennoir2/C_H3_sfw.txt", H);
   for (let i = 1; i <= 6; i++) await put(`PostIG/big/img${i}.png`, await png(120, 160, "#a3c"));
   await (await R.getDirectoryHandle("PostIG")).getDirectoryHandle("empty", { create: true });
   window.seedRoot = await R.getDirectoryHandle("PostIG");
   window.readSeed = async path => { const p = path.split("/"); let d = R; for (const s of p.slice(0, -1)) d = await d.getDirectoryHandle(s); return (await (await d.getFileHandle(p.at(-1))).getFile()).text(); };
   window.seedB = B;
   "seeded";
   ```

4. Open a tab on the seed with `await tabs.<caption|minimax|filter>.open(seedRoot)`, then check with screenshots, `read_page`, `find`, clicks, and `readSeed("PostIG/...")`.
5. **Answer `<dialog>` prompts (`askDlg`) with real clicks** (the browser `computer` tool on a `find` ref), not `button.click()` from a script. A scripted click closes the dialog, but its `close` event may not arrive, so the awaiting code never continues. Wait about 1s after the click before reading results; the crop write can take a moment.
6. The wheel over the image viewer zooms the image (by design). To scroll the right column, scroll outside the viewer or set `document.querySelector("#tab-caption .main").scrollTop = 0`.
7. Check the console has no errors. Stop the server when the task is done.

This flow was dry-run on 2026-10-21 against the code in this plan: Tab 3 counts and filter, Tab 2 variant order and byte-exact save, and Tab 1 caption save (CRLF kept), new txt via the unsaved dialog, chip insert, and crop to 240×320 all behaved as the checks below describe.

Seeded tree (9 folders): `PostIG` (0 images), `day_52_1`, `day_52_1/Ryo` (1), `day_53_1`, `day_53_1/Ryo` (1), `day_56_1`, `day_56_1/Rennoir2` (1), `big` (6), `empty` (0).

---

### Task 0: Confirm file access works from `file://` (controller + user)

The spec requires this before any build work. It is a throwaway check, not committed.

- [ ] **Step 1: Write the check page** to the session scratchpad as `fs_check.html`:

```html
<!doctype html><meta charset="utf-8"><title>FS check</title>
<button id="b">Chọn một thư mục trống để thử</button><pre id="o"></pre>
<script>
o.textContent = "isSecureContext=" + isSecureContext + ", showDirectoryPicker=" + typeof showDirectoryPicker;
b.onclick = async () => {
  try {
    const d = await showDirectoryPicker({ mode: "readwrite" });
    const f = await d.getFileHandle("fs_check.txt", { create: true });
    const w = await f.createWritable(); await w.write("ok " + new Date().toISOString()); await w.close();
    o.textContent = "OK: đã ghi fs_check.txt vào " + d.name + "\n" + await (await f.getFile()).text();
  } catch (e) { o.textContent = "LỖI: " + e.name + ": " + e.message; }
};
</script>
```

- [ ] **Step 2: Ask the user** to open that file (full absolute path) by double-clicking it in Chrome, press the button, pick an empty folder, allow access, and report the text shown.
- [ ] **Step 3: Decide.** If it shows `OK: ...`, continue to Task 1. If it shows `LỖI` or `showDirectoryPicker=undefined`, stop and report to the user; the platform choice must be revisited before any other task.

---

### Task 1: Core names, pairing and folder-tree helpers

**Files:**
- Create: `prompt/CaptionPrompt/dist/core.js`
- Create: `prompt/CaptionPrompt/test_core.mjs`

**Interfaces:**
- Produces (on `window.CaptionCore` and `module.exports`):
  - `isImage(name: string) -> boolean`
  - `baseName(name: string) -> string` (drops the last extension)
  - `naturalCompare(a: string, b: string) -> number`
  - `parseH3Name(name) -> { base, rating: "sfw"|"nsfw", suffix } | null`
  - `pairFolder(names: string[]) -> Array<{ image: string, caption: string|null, h3: Array<{ name, rating, suffix }> }>`, images in natural order, `h3` in natural order
  - Tree `Node = { name, path, dirs: Node[], files: Array<{ name, handle? }> }` (path relative to the root, `""` for the root)
  - `imageCount(node) -> number` (images directly in the folder)
  - `anyImage(node) -> boolean` (images in the folder or any subfolder)
  - `countLabel(node) -> string` (`"<i> ảnh · <d> folder"` or `"<i> ảnh"`)
  - `filterTree(root, max) -> { matched: Set<path>, visible: Set<path>, total: number }`

- [ ] **Step 1: Write the failing test** `prompt/CaptionPrompt/test_core.mjs`:

```js
// Run: node test_core.mjs   (from prompt/CaptionPrompt)
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const C = createRequire(import.meta.url)("./dist/core.js");

// --- names ---
for (const n of ["a.png", "a.PNG", "b.jpg", "c.JPEG", "d.webp"]) assert.equal(C.isImage(n), true, n);
for (const n of ["a.gif", "a.txt", "png", ".png"]) assert.equal(C.isImage(n), false, n);
assert.equal(C.baseName("a.b.png"), "a.b");
assert.equal(C.baseName("noext"), "noext");
assert.deepEqual(["img10.png", "img2.png", "img1.png"].sort(C.naturalCompare), ["img1.png", "img2.png", "img10.png"]);

// --- parseH3Name ---
assert.deepEqual(C.parseH3Name("A_H3_sfw.txt"), { base: "A", rating: "sfw", suffix: "" });
assert.deepEqual(C.parseH3Name("A_H3_NSFW_v2.txt"), { base: "A", rating: "nsfw", suffix: "v2" });
assert.deepEqual(C.parseH3Name("ZImage_2026_06_06_101818_60_00001_H3_nsfw_v2.txt"),
  { base: "ZImage_2026_06_06_101818_60_00001", rating: "nsfw", suffix: "v2" });
for (const n of ["A_H3.txt", "A_H3_safe.txt", "A.txt", "A_H3_sfw.md"]) assert.equal(C.parseH3Name(n), null, n);

// --- pairFolder ---
{
  const p = C.pairFolder(["B.png", "b.txt", "b_H3_nsfw_v2.txt", "B_H3_sfw.txt", "a.jpg", "orphan.txt", "x_H3_sfw.txt", "notes.md"]);
  assert.deepEqual(p.map(e => e.image), ["a.jpg", "B.png"]);
  assert.equal(p[0].caption, null);
  assert.deepEqual(p[0].h3, []);
  assert.equal(p[1].caption, "b.txt");                       // caption matched case-insensitively
  assert.deepEqual(p[1].h3.map(h => h.name), ["b_H3_nsfw_v2.txt", "B_H3_sfw.txt"]);
  assert.deepEqual(p[1].h3[0], { name: "b_H3_nsfw_v2.txt", rating: "nsfw", suffix: "v2" });
}
// the plain variant sorts before its _v2
assert.deepEqual(C.pairFolder(["A.png", "A_H3_nsfw_v2.txt", "A_H3_sfw.txt", "A_H3_nsfw.txt"])[0].h3.map(h => h.name),
  ["A_H3_nsfw.txt", "A_H3_nsfw_v2.txt", "A_H3_sfw.txt"]);
// an H3 file is never taken as a caption
assert.equal(C.pairFolder(["A.png", "A_H3_sfw.txt"])[0].caption, null);

// --- folder tree ---
const T = (name, path, files, dirs = []) => ({ name, path, files: files.map(n => ({ name: n })), dirs });
const tree = T("PostIG", "", ["readme.txt"], [
  T("day_52_1", "day_52_1", [], [T("Ryo", "day_52_1/Ryo", ["a.png", "a_H3_sfw.txt"])]),
  T("day_53_1", "day_53_1", [], [T("Ryo", "day_53_1/Ryo", ["a.png", "b.jpg", "c.webp"])]),
  T("empty", "empty", []),
]);
assert.equal(C.imageCount(tree.dirs[1].dirs[0]), 3);
assert.equal(C.imageCount(tree), 0);
assert.equal(C.anyImage(tree), true);
assert.equal(C.anyImage(tree.dirs[2]), false);
assert.equal(C.countLabel(tree), "0 ảnh · 3 folder");
assert.equal(C.countLabel(tree.dirs[0].dirs[0]), "1 ảnh");
{
  const f = C.filterTree(tree, 2);
  assert.deepEqual([...f.matched], ["day_52_1/Ryo"]);
  assert.deepEqual([...f.visible].sort(), ["", "day_52_1", "day_52_1/Ryo"]);
  assert.equal(f.total, 6);
}
assert.deepEqual([...C.filterTree(tree, 3).matched].sort(), ["day_52_1/Ryo", "day_53_1/Ryo"]); // i === N matches
assert.equal(C.filterTree(tree, 0).matched.size, 0); // 0-image folders never match

console.log("core tests passed");
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd prompt/CaptionPrompt && node test_core.mjs`
Expected: FAIL with `Cannot find module './dist/core.js'`.

- [ ] **Step 3: Write** `prompt/CaptionPrompt/dist/core.js`:

```js
/* CaptionPrompt core: pure logic, no DOM.
   Loaded by dist/index.html as a classic script (window.CaptionCore) and by test_core.mjs via require. */
(function (root) {
  "use strict";

  // ---- files and folders ----
  const IMAGE_EXT = new Set(["png", "jpg", "jpeg", "webp"]);
  const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

  function ext(name) {
    const i = name.lastIndexOf(".");
    return i > 0 ? name.slice(i + 1).toLowerCase() : "";
  }
  function isImage(name) { return IMAGE_EXT.has(ext(name)); }
  function baseName(name) {
    const i = name.lastIndexOf(".");
    return i > 0 ? name.slice(0, i) : name;
  }
  function naturalCompare(a, b) { return collator.compare(a, b); }

  const H3_RE = /^(.+)_H3_(sfw|nsfw)(?:_([^.]+))?\.txt$/i;
  function parseH3Name(name) {
    const m = H3_RE.exec(name);
    return m ? { base: m[1], rating: m[2].toLowerCase(), suffix: m[3] || "" } : null;
  }

  // Pair each image in one folder with its caption "<base>.txt" and its H3 files. Names match case-insensitively.
  function pairFolder(names) {
    const out = [], byBase = new Map();
    for (const n of names.filter(isImage).sort(naturalCompare)) {
      const e = { image: n, caption: null, h3: [] };
      out.push(e);
      const k = baseName(n).toLowerCase();
      if (!byBase.has(k)) byBase.set(k, e);
    }
    for (const n of names) {
      if (ext(n) !== "txt") continue;
      const h = parseH3Name(n);
      const e = byBase.get((h ? h.base : baseName(n)).toLowerCase());
      if (!e) continue;
      if (h) e.h3.push({ name: n, rating: h.rating, suffix: h.suffix });
      else e.caption = n;
    }
    // Compare without ".txt" so "x_H3_nsfw" sorts before "x_H3_nsfw_v2".
    for (const e of out) e.h3.sort((a, b) => naturalCompare(baseName(a.name), baseName(b.name)));
    return out;
  }

  // ---- folder tree: Node = { name, path, dirs: [Node], files: [{ name }] } ----
  function imageCount(node) { return node.files.filter(f => isImage(f.name)).length; }
  function anyImage(node) { return imageCount(node) > 0 || node.dirs.some(anyImage); }
  function countLabel(node) {
    const i = imageCount(node), d = node.dirs.length;
    return d ? `${i} ảnh · ${d} folder` : `${i} ảnh`;
  }
  // A folder matches when 1 <= direct images <= max. Visible = matched folders plus all their ancestors.
  function filterTree(rootNode, max) {
    const matched = new Set(), visible = new Set();
    let total = 0;
    (function walk(n, ancestors) {
      total++;
      const i = imageCount(n);
      if (i >= 1 && i <= max) {
        matched.add(n.path);
        visible.add(n.path);
        ancestors.forEach(p => visible.add(p));
      }
      n.dirs.forEach(d => walk(d, [...ancestors, n.path]));
    })(rootNode, []);
    return { matched, visible, total };
  }

  // ---- exports ----
  const api = { isImage, baseName, naturalCompare, parseH3Name, pairFolder, imageCount, anyImage, countLabel, filterTree };
  root.CaptionCore = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `cd prompt/CaptionPrompt && node test_core.mjs`
Expected: `core tests passed`

- [ ] **Step 5: Commit**

```bash
git add prompt/CaptionPrompt/dist/core.js prompt/CaptionPrompt/test_core.mjs
git commit -m "Add CaptionPrompt core: file pairing, H3 names and folder filter

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: H3 split and join

**Files:**
- Modify: `prompt/CaptionPrompt/dist/core.js` (new section before `  // ---- exports ----`, extend `api`)
- Modify: `prompt/CaptionPrompt/test_core.mjs` (new block before `console.log("core tests passed");`)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces:
  - `detectEol(text) -> "\r\n" | "\n"`
  - `toEol(text, eol) -> string` (normalizes any `\r\n`/`\r`/`\n` to `eol`)
  - `splitH3(text) -> { parts: [head, body1, mid, body2, tail], eol, recognized: boolean }`, with `parts.join("") === text`
  - `joinH3(parts) -> string`
  - `h3Bodies(split) -> [string, string]`, the editor texts (`\n` endings, one final line ending removed)
  - `setH3Bodies(split, b1, b2) -> string`, the file text with edited bodies, everything else byte-identical

- [ ] **Step 1: Add the failing test.** In `test_core.mjs`, insert this block right before `console.log("core tests passed");`:

```js
// --- H3 split / join ---
// Layout 1: plain headings (like day_52_1)
const H3_PLAIN =
  "CHARACTER & SCENE DEFINITION\r\n\r\n" +
  "<Subject 1> A man.\r\n\r\n[reference generation] He smiles.\r\n" +
  "\r\nSHOT STRUCTURE — MINIMAX H3\r\n\r\n" +
  "[SHOT 01 | DURATION: 10s | PRIMARY CAMERA SETUP: close-up]\r\nHe waves.\r\n\r\n" +
  "[SHOT 02 | DURATION: 10s | PRIMARY CAMERA SETUP: wide]\r\nHe leaves.\r\n";
// Layout 2: markdown headings with --- (like day_53_1 sfw / nsfw_v2)
const H3_MD =
  "# CHARACTER & SCENE DEFINITION\r\n\r\n" +
  "**summary:**\r\n\r\nA man dances.\r\n" +
  "\r\n---\r\n\r\n# SHOT STRUCTURE — MINIMAX H3\r\n\r\n" +
  "[SHOT 01 | DURATION: 8s | PRIMARY CAMERA SETUP: dolly]\r\n\r\nStep one.\r\n\r\n---\r\n\r\n" +
  "[SHOT 02 | DURATION: 7s | PRIMARY CAMERA SETUP: medium]\r\n\r\nStep two.\r\n";
// Layout 3: no headings (like day_56_1/Rennoir2)
const H3_BARE =
  "subject_definitions:\r\n\r\nA swimmer.\r\n\r\nnon_diegetic_music:\r\n\r\nNONE\r\n" +
  "\r\n" +
  "[SHOT 01 | DURATION: 12s | PRIMARY CAMERA SETUP: mirror]\r\n\r\nsubject_definitions:\r\n\r\nSame swimmer.\r\n\r\nnon_diegetic_music:\r\n" +
  "\r\n";

assert.equal(C.detectEol(H3_PLAIN), "\r\n");
assert.equal(C.detectEol("a\nb"), "\n");
assert.equal(C.toEol("a\r\nb\nc\rd", "\r\n"), "a\r\nb\r\nc\r\nd");
assert.equal(C.toEol("a\r\nb", "\n"), "a\nb");

{
  const s = C.splitH3(H3_PLAIN);
  assert.equal(s.recognized, true);
  assert.equal(s.eol, "\r\n");
  assert.deepEqual(s.parts, [
    "CHARACTER & SCENE DEFINITION\r\n\r\n",
    "<Subject 1> A man.\r\n\r\n[reference generation] He smiles.\r\n",
    "\r\nSHOT STRUCTURE — MINIMAX H3\r\n\r\n",
    "[SHOT 01 | DURATION: 10s | PRIMARY CAMERA SETUP: close-up]\r\nHe waves.\r\n\r\n[SHOT 02 | DURATION: 10s | PRIMARY CAMERA SETUP: wide]\r\nHe leaves.\r\n",
    "",
  ]);
  assert.deepEqual(C.h3Bodies(s), [
    "<Subject 1> A man.\n\n[reference generation] He smiles.",
    "[SHOT 01 | DURATION: 10s | PRIMARY CAMERA SETUP: close-up]\nHe waves.\n\n[SHOT 02 | DURATION: 10s | PRIMARY CAMERA SETUP: wide]\nHe leaves.",
  ]);
}
{
  const s = C.splitH3(H3_MD);
  assert.deepEqual(s.parts.slice(0, 3), [
    "# CHARACTER & SCENE DEFINITION\r\n\r\n",
    "**summary:**\r\n\r\nA man dances.\r\n",
    "\r\n---\r\n\r\n# SHOT STRUCTURE — MINIMAX H3\r\n\r\n",
  ]);
  assert.ok(s.parts[3].includes("\r\n---\r\n"), "--- between shots stays in body 2");
}
{
  const s = C.splitH3(H3_BARE);
  assert.equal(s.recognized, true);
  assert.equal(s.parts[0], "");
  assert.equal(s.parts[1], "subject_definitions:\r\n\r\nA swimmer.\r\n\r\nnon_diegetic_music:\r\n\r\nNONE\r\n");
  assert.equal(s.parts[2], "\r\n");
  assert.ok(s.parts[3].startsWith("[SHOT 01"));
  assert.equal(s.parts[4], "\r\n");
}
// round trip, byte for byte, for every layout
for (const t of [H3_PLAIN, H3_MD, H3_BARE]) {
  const s = C.splitH3(t);
  assert.equal(C.joinH3(s.parts), t);
  const [b1, b2] = C.h3Bodies(s);
  assert.equal(C.setH3Bodies(s, b1, b2), t);
}
// editing one body changes only that body
{
  const s = C.splitH3(H3_PLAIN);
  const out = C.setH3Bodies(s, "<Subject 1> A woman.\n\n[reference generation] She smiles.", C.h3Bodies(s)[1]);
  assert.equal(out, H3_PLAIN.replace("A man.", "A woman.").replace("He smiles.", "She smiles."));
}
{
  const s = C.splitH3(H3_MD);
  const out = C.setH3Bodies(s, C.h3Bodies(s)[0], C.h3Bodies(s)[1].replace("Step two.", "Step 2."));
  assert.equal(out, H3_MD.replace("Step two.", "Step 2."));
}
// a file with no final newline stays without one
{
  const t = "CHARACTER & SCENE DEFINITION\nA\nSHOT STRUCTURE\n[SHOT 01]\nB";
  const s = C.splitH3(t);
  assert.equal(C.setH3Bodies(s, ...C.h3Bodies(s)), t);
  assert.equal(C.setH3Bodies(s, "A", "[SHOT 01]\nC"), "CHARACTER & SCENE DEFINITION\nA\nSHOT STRUCTURE\n[SHOT 01]\nC");
}
// unrecognized text: everything in body 1, still round-trips
{
  const t = "Just a note.\r\nSecond line.\r\n\r\n";
  const s = C.splitH3(t);
  assert.equal(s.recognized, false);
  assert.deepEqual(s.parts, ["", "Just a note.\r\nSecond line.\r\n", "", "", "\r\n"]);
  assert.equal(C.setH3Bodies(s, ...C.h3Bodies(s)), t);
  assert.equal(C.joinH3(C.splitH3("").parts), "");
}
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd prompt/CaptionPrompt && node test_core.mjs`
Expected: FAIL with `TypeError: C.detectEol is not a function`.

- [ ] **Step 3: Implement.** In `core.js`, insert this section right before `  // ---- exports ----`:

```js
  // ---- line endings ----
  function detectEol(text) { return text.includes("\r\n") ? "\r\n" : "\n"; }
  function toEol(text, eol) {
    const lf = text.replace(/\r\n?/g, "\n");
    return eol === "\n" ? lf : lf.replace(/\n/g, eol);
  }

  // ---- H3 prompt files ----
  // parts = [head, body1, mid, body2, tail]; parts.join("") is always the input.
  const H1_RE = /^\s*#*\s*CHARACTER\s*&\s*SCENE\s+DEFINITION\s*$/i;
  const H2_RE = /^\s*#*\s*SHOT\s+STRUCTURE\b/i;
  const SHOT_RE = /^\s*\[SHOT\s+\d+/i;

  function splitH3(text) {
    const L = text.match(/[^\n]*\n|[^\n]+$/g) || [];   // lines with their endings
    const n = L.length;
    const line = i => L[i].replace(/\r?\n$/, "");
    const blank = i => !line(i).trim();
    const join = (a, b) => L.slice(a, b).join("");
    const eol = detectEol(text);

    let headEnd = 0;
    const h1 = L.findIndex((_, i) => H1_RE.test(line(i)));
    if (h1 >= 0) { headEnd = h1 + 1; while (headEnd < n && blank(headEnd)) headEnd++; }

    let h2 = -1, s2 = -1;
    for (let i = headEnd; i < n; i++) if (H2_RE.test(line(i))) { h2 = i; break; }
    if (h2 >= 0) s2 = h2;
    else for (let i = headEnd; i < n; i++) if (SHOT_RE.test(line(i))) { s2 = i; break; }

    let tailStart = n;
    while (tailStart > headEnd && blank(tailStart - 1)) tailStart--;

    if (s2 < 0) {
      return { parts: [join(0, headEnd), join(headEnd, tailStart), "", "", join(tailStart, n)], eol, recognized: false };
    }
    let midStart = s2;
    while (midStart > headEnd && (blank(midStart - 1) || line(midStart - 1).trim() === "---")) midStart--;
    let b2 = s2;
    if (h2 >= 0) { b2 = h2 + 1; while (b2 < n && blank(b2)) b2++; }
    tailStart = Math.max(tailStart, b2);
    return {
      parts: [join(0, headEnd), join(headEnd, midStart), join(midStart, b2), join(b2, tailStart), join(tailStart, n)],
      eol, recognized: true,
    };
  }
  function joinH3(parts) { return parts.join(""); }

  const bodyText = part => part.replace(/\r\n/g, "\n").replace(/\n$/, "");
  function h3Bodies(split) { return [bodyText(split.parts[1]), bodyText(split.parts[3])]; }

  // Unchanged bodies are kept byte for byte. An edited body gets back its original final line ending.
  function putBody(orig, edited, eol) {
    if (edited === bodyText(orig)) return orig;
    if (!edited) return "";
    return toEol(edited, eol) + (!orig || orig.endsWith("\n") ? eol : "");
  }
  function setH3Bodies(split, b1, b2) {
    const [head, o1, mid, o2, tail] = split.parts;
    return head + putBody(o1, b1, split.eol) + mid + putBody(o2, b2, split.eol) + tail;
  }

```

Then replace the `api` line with:

```js
  const api = {
    isImage, baseName, naturalCompare, parseH3Name, pairFolder, imageCount, anyImage, countLabel, filterTree,
    detectEol, toEol, splitH3, joinH3, h3Bodies, setH3Bodies,
  };
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `cd prompt/CaptionPrompt && node test_core.mjs`
Expected: `core tests passed`

- [ ] **Step 5: Commit**

```bash
git add prompt/CaptionPrompt/dist/core.js prompt/CaptionPrompt/test_core.mjs
git commit -m "Split and rejoin MiniMax H3 prompt files without changing untouched bytes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Snippets, word file and PNG text chunks

**Files:**
- Modify: `prompt/CaptionPrompt/dist/core.js` (new section before `  // ---- exports ----`, extend `api`)
- Modify: `prompt/CaptionPrompt/test_core.mjs` (imports at the top, new block before `console.log("core tests passed");`)

**Interfaces:**
- Produces:
  - `padSnippet(before: string, after: string, snippet: string) -> string`
  - `DEFAULT_WORDS: Array<{ label, text }>`
  - `parseWords(jsonText) -> Array<{ label, text }>`; throws `Error` with a Vietnamese message on bad input
  - `mergeWords(current, incoming) -> { words, added, skipped }` (input arrays not mutated)
  - `wordsJson(words) -> string` (`{ version: 1, words }`, 2-space indent, trailing `\n`)
  - `copyPngText(srcBytes: Uint8Array, dstBytes: Uint8Array) -> Uint8Array`

- [ ] **Step 1: Add the failing test.** At the top of `test_core.mjs`, after the existing `import` lines, add:

```js
import { deflateSync, crc32 } from "node:zlib";
```

Then insert this block right before `console.log("core tests passed");`:

```js
// --- padSnippet ---
assert.equal(C.padSnippet("", "", "x"), "x");
assert.equal(C.padSnippet("a man", "", "tall"), " tall");
assert.equal(C.padSnippet("a man ", "", "tall"), "tall");
assert.equal(C.padSnippet("a\n", "", "x"), "x");
assert.equal(C.padSnippet("(", ")", "x"), "x");
assert.equal(C.padSnippet("a", "b", "x"), " x ");
assert.equal(C.padSnippet("a", ", b", "x"), " x");
assert.equal(C.padSnippet("a ", " b", "x"), "x");

// --- word file ---
assert.ok(C.DEFAULT_WORDS.length > 0 && C.DEFAULT_WORDS.every(w => w.label && w.text));
assert.deepEqual(
  C.parseWords('{"version":1,"words":[{"label":" Ivan ","text":"Ivan_Ryo"},{"label":"","text":"x"},{"label":"y"},{"label":"Gym","text":"in a gym"}]}'),
  [{ label: "Ivan", text: "Ivan_Ryo" }, { label: "Gym", text: "in a gym" }]);
assert.throws(() => C.parseWords("not json"), /JSON/);
assert.throws(() => C.parseWords('{"x":1}'), /words/);
{
  const cur = [{ label: "Ivan", text: "Ivan_Ryo" }];
  const m = C.mergeWords(cur, [{ label: "ivan", text: "other" }, { label: "Gym", text: "in a gym" }]);
  assert.deepEqual(m, { words: [{ label: "Ivan", text: "Ivan_Ryo" }, { label: "Gym", text: "in a gym" }], added: 1, skipped: 1 });
  assert.equal(cur.length, 1, "input not mutated");
}
{
  const j = C.wordsJson(C.DEFAULT_WORDS);
  assert.ok(j.startsWith('{\n  "version": 1,') && j.endsWith("\n"));
  assert.deepEqual(C.parseWords(j), C.DEFAULT_WORDS);
}

// --- copyPngText ---
const SIG = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
function pngChunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type, "latin1"), data]);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
}
function pngChunks(b) {
  const out = [];
  for (let p = 8; p + 12 <= b.length;) {
    const len = b.readUInt32BE(p), type = b.toString("latin1", p + 4, p + 8);
    out.push({ type, ok: crc32(b.subarray(p + 4, p + 8 + len)) === b.readUInt32BE(p + 8 + len) });
    p += 12 + len;
  }
  return out;
}
const IHDR = pngChunk("IHDR", Buffer.from([0, 0, 0, 1, 0, 0, 0, 1, 8, 0, 0, 0, 0]));
const IDAT = pngChunk("IDAT", deflateSync(Buffer.from([0, 0])));
const IEND = pngChunk("IEND", Buffer.alloc(0));
const plainPng = Buffer.concat([SIG, IHDR, IDAT, IEND]);
const taggedPng = Buffer.concat([SIG, IHDR,
  pngChunk("tEXt", Buffer.from('prompt\0{"a":1}', "latin1")),
  pngChunk("tEXt", Buffer.from("workflow\0{}", "latin1")), IDAT, IEND]);
{
  const out = Buffer.from(C.copyPngText(new Uint8Array(taggedPng), new Uint8Array(plainPng)));
  assert.ok(out.subarray(0, 8).equals(SIG));
  assert.deepEqual(pngChunks(out).map(c => c.type), ["IHDR", "tEXt", "tEXt", "IDAT", "IEND"]);
  assert.ok(pngChunks(out).every(c => c.ok), "every CRC still valid");
  assert.ok(out.includes('prompt\0{"a":1}') && out.includes("workflow\0{}"));
}
{
  const dst = new Uint8Array(plainPng), junk = new Uint8Array([1, 2, 3]);
  assert.equal(C.copyPngText(junk, dst), dst);                       // source not a PNG
  assert.equal(C.copyPngText(new Uint8Array(taggedPng), junk), junk); // target not a PNG
  assert.equal(C.copyPngText(new Uint8Array(plainPng), dst), dst);    // nothing to copy
}
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd prompt/CaptionPrompt && node test_core.mjs`
Expected: FAIL with `TypeError: C.padSnippet is not a function`.

- [ ] **Step 3: Implement.** In `core.js`, insert this section right before `  // ---- exports ----`:

```js
  // ---- snippets ----
  // Add a space so the snippet does not touch a neighboring word.
  function padSnippet(before, after, snippet) {
    const lead = before && !/[\s(]$/.test(before) ? " " : "";
    const trail = after && !/^[\s,.;:!?)]/.test(after) ? " " : "";
    return lead + snippet + trail;
  }

  const DEFAULT_WORDS = [
    { label: "Ivan", text: "Ivan_Ryo, a 25yo Asian young man" },
    { label: "Close-up", text: "close-up shot" },
    { label: "Soft light", text: "soft natural light" },
    { label: "Gym", text: "in a gym" },
  ];
  function parseWords(jsonText) {
    let d;
    try { d = JSON.parse(jsonText); } catch (e) { throw new Error("File không phải JSON hợp lệ"); }
    if (!d || !Array.isArray(d.words)) throw new Error('File thiếu mảng "words"');
    return d.words
      .filter(w => w && typeof w.label === "string" && typeof w.text === "string")
      .map(w => ({ label: w.label.trim(), text: w.text.trim() }))
      .filter(w => w.label && w.text);
  }
  function mergeWords(current, incoming) {
    const seen = new Set(current.map(w => w.label.toLowerCase()));
    const words = current.slice();
    let added = 0, skipped = 0;
    for (const w of incoming) {
      const k = w.label.toLowerCase();
      if (seen.has(k)) { skipped++; continue; }
      seen.add(k);
      words.push(w);
      added++;
    }
    return { words, added, skipped };
  }
  function wordsJson(words) { return JSON.stringify({ version: 1, words }, null, 2) + "\n"; }

  // ---- PNG text chunks ----
  const PNG_SIG = [137, 80, 78, 71, 13, 10, 26, 10];
  const isPng = b => b && b.length >= 8 && PNG_SIG.every((v, i) => b[i] === v);
  function pngChunks(b) {
    const out = [];
    for (let p = 8; p + 12 <= b.length;) {
      const len = ((b[p] << 24) | (b[p + 1] << 16) | (b[p + 2] << 8) | b[p + 3]) >>> 0;
      const end = p + 12 + len;
      if (end > b.length) break;
      out.push({ type: String.fromCharCode(b[p + 4], b[p + 5], b[p + 6], b[p + 7]), start: p, end });
      p = end;
    }
    return out;
  }
  // Copy the source's text chunks (ComfyUI prompt/workflow/parameters) into the target, right after IHDR.
  // Chunks are copied whole, CRC included, so nothing is recomputed.
  function copyPngText(src, dst) {
    if (!isPng(src) || !isPng(dst)) return dst;
    const text = pngChunks(src).filter(c => c.type === "tEXt" || c.type === "iTXt" || c.type === "zTXt");
    const ihdr = pngChunks(dst)[0];
    if (!text.length || !ihdr || ihdr.type !== "IHDR") return dst;
    const extra = text.reduce((s, c) => s + c.end - c.start, 0);
    const out = new Uint8Array(dst.length + extra);
    out.set(dst.subarray(0, ihdr.end), 0);
    let p = ihdr.end;
    for (const c of text) { out.set(src.subarray(c.start, c.end), p); p += c.end - c.start; }
    out.set(dst.subarray(ihdr.end), p);
    return out;
  }

```

Then replace the `api` block with:

```js
  const api = {
    isImage, baseName, naturalCompare, parseH3Name, pairFolder, imageCount, anyImage, countLabel, filterTree,
    detectEol, toEol, splitH3, joinH3, h3Bodies, setH3Bodies,
    padSnippet, DEFAULT_WORDS, parseWords, mergeWords, wordsJson, copyPngText,
  };
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `cd prompt/CaptionPrompt && node test_core.mjs`
Expected: `core tests passed`

- [ ] **Step 5: Commit**

```bash
git add prompt/CaptionPrompt/dist/core.js prompt/CaptionPrompt/test_core.mjs
git commit -m "Add snippet padding, word file parsing and PNG metadata copy to core

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Page shell, file access and shared UI

**Files:**
- Create: `prompt/CaptionPrompt/dist/index.html`
- Create: `prompt/CaptionPrompt/dist/fs.js`
- Create: `prompt/CaptionPrompt/dist/ui.js`

**Interfaces:**
- Consumes: `CaptionCore.naturalCompare`.
- Produces:
  - `window.CaptionFS`:
    - `remember(key, handle) -> Promise`, `recall(key) -> Promise<handle|undefined>`
    - `pickDir() -> Promise<FileSystemDirectoryHandle>`, `pickFile(opts) -> Promise<FileSystemFileHandle>`, `createFile(opts) -> Promise<FileSystemFileHandle>`. These reject with `AbortError` when the user cancels.
    - `ensurePermission(handle, mode = "readwrite") -> Promise<boolean>`
    - `scanDir(dirHandle, onError?) -> Promise<Node>`, where `Node = { name, path, handle, dirs, files: [{ name, handle }] }`, sorted naturally, skipping folders that start with `.`, and calling `onError(path, error)` for unreadable folders
    - `readText(fileHandle) -> Promise<string>`, `writeFile(fileHandle, data) -> Promise`, `writeText(dirHandle, name, text) -> Promise<fileHandle>`
  - `window.CaptionUI`:
    - `$(id)`, `esc(str)`, `toast(msg)`
    - `ask(msg, buttons: [{ id, label, kind? }]) -> Promise<id | "cancel">`
    - `confirmLeave(isDirty: () => boolean, save: () => Promise<boolean>) -> Promise<boolean>`
    - `folderRow(sideEl, key, onRoot: handle => void)`
    - `tree(el, opts) -> { setRoot(node), render(), clear() }`, where `opts = { selectable?: "leaf"|"folder", folder?(node) -> { hidden?, cls?, aside? }, leaves?(node) -> [{ key, label, cls?, aside?, icon?, ...extra }], canLeave?() -> Promise<boolean>, onSelect(row) }`. A `row` has `{ key, node, folder, leaf }`, and `leaf` is the object returned by `leaves`. The root row is never hidden.
  - Markup ids used by later tasks, all defined in this task's `index.html`. Each tab is `<main class="tab" id="tab-<caption|minimax|filter>">`, containing `<aside class="panel side">` with `.dirname`, `.pick`, `.reopen`.
  - Boot: `window.tabs[name] = window.<CaptionTab|MiniMaxTab|FilterTab>.init(el)` for each tab module that is loaded. Ctrl+S calls `tabs[active].save()`. `beforeunload` warns when any `tabs[x].isDirty()` is true.

- [ ] **Step 1: Write** `prompt/CaptionPrompt/dist/fs.js`:

```js
/* CaptionPrompt file access: File System Access API, plus handles remembered in IndexedDB. window.CaptionFS */
(function () {
  "use strict";
  const C = window.CaptionCore;
  const DB = "captionPrompt", STORE = "handles";

  function openDb() {
    return new Promise((res, rej) => {
      const r = indexedDB.open(DB, 1);
      r.onupgradeneeded = () => r.result.createObjectStore(STORE);
      r.onsuccess = () => res(r.result);
      r.onerror = () => rej(r.error);
    });
  }
  async function idb(mode, fn) {
    const db = await openDb();
    try {
      return await new Promise((res, rej) => {
        const req = fn(db.transaction(STORE, mode).objectStore(STORE));
        req.onsuccess = () => res(req.result);
        req.onerror = () => rej(req.error);
      });
    } finally { db.close(); }
  }
  const remember = (key, handle) => idb("readwrite", s => s.put(handle, key));
  const recall = key => idb("readonly", s => s.get(key));

  const pickDir = () => window.showDirectoryPicker({ mode: "readwrite" });
  const pickFile = async opts => (await window.showOpenFilePicker(opts))[0];
  const createFile = opts => window.showSaveFilePicker(opts);

  async function ensurePermission(handle, mode = "readwrite") {
    if (!handle.queryPermission) return true; // OPFS handles (used in checks) need no permission
    if ((await handle.queryPermission({ mode })) === "granted") return true;
    return (await handle.requestPermission({ mode })) === "granted";
  }

  async function scanDir(handle, onError, path = "") {
    const node = { name: handle.name, path, handle, dirs: [], files: [] };
    try {
      for await (const [name, h] of handle.entries()) {
        if (h.kind === "directory") {
          if (!name.startsWith(".")) node.dirs.push(await scanDir(h, onError, path ? path + "/" + name : name));
        } else node.files.push({ name, handle: h });
      }
    } catch (e) { if (onError) onError(path || handle.name, e); }
    node.dirs.sort((a, b) => C.naturalCompare(a.name, b.name));
    node.files.sort((a, b) => C.naturalCompare(a.name, b.name));
    return node;
  }

  async function readText(fileHandle) { return (await fileHandle.getFile()).text(); } // UTF-8, BOM dropped
  async function writeFile(fileHandle, data) {
    const w = await fileHandle.createWritable();
    try { await w.write(data); await w.close(); }
    catch (e) { await w.abort().catch(() => {}); throw e; }
  }
  async function writeText(dirHandle, name, text) {
    const fh = await dirHandle.getFileHandle(name, { create: true });
    await writeFile(fh, text);
    return fh;
  }

  window.CaptionFS = { remember, recall, pickDir, pickFile, createFile, ensurePermission, scanDir, readText, writeFile, writeText };
})();
```

- [ ] **Step 2: Write** `prompt/CaptionPrompt/dist/ui.js`:

```js
/* CaptionPrompt shared UI: toast, ask dialog, unsaved-changes guard, folder row, tree. window.CaptionUI */
(function () {
  "use strict";
  const FS = window.CaptionFS;
  const $ = id => document.getElementById(id);
  const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  let toastTimer = null;
  function toast(msg) {
    $("toastMsg").textContent = msg;
    $("toast").classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => $("toast").classList.remove("show"), 4000);
  }

  // Resolves with the clicked button's id, or "cancel" on Esc.
  function ask(msg, buttons) {
    return new Promise(res => {
      const d = $("askDlg");
      $("askMsg").textContent = msg;
      $("askBtns").innerHTML = buttons.map(b => `<button class="btn ${b.kind || ""}" value="${esc(b.id)}">${esc(b.label)}</button>`).join("");
      d.returnValue = "";
      d.onclose = () => res(d.returnValue || "cancel");
      d.showModal();
    });
  }

  // true = go ahead (saved or discarded), false = stay.
  async function confirmLeave(isDirty, save) {
    if (!isDirty()) return true;
    const r = await ask("Có thay đổi chưa lưu.", [
      { id: "save", label: "Lưu", kind: "primary" }, { id: "discard", label: "Bỏ thay đổi" }, { id: "cancel", label: "Huỷ" }]);
    if (r === "save") return save();
    return r === "discard";
  }

  // Wires the folder picker and the "Mở lại" button inside one tab's side panel.
  async function folderRow(side, key, onRoot) {
    const reopen = side.querySelector(".reopen");
    side.querySelector(".pick").onclick = async () => {
      let h;
      try { h = await FS.pickDir(); }
      catch (e) { if (e.name !== "AbortError") toast("Không mở được thư mục: " + e.message); return; }
      FS.remember(key, h).catch(() => {});
      reopen.hidden = true;
      onRoot(h);
    };
    const old = await FS.recall(key).catch(() => null);
    if (!old) return;
    reopen.textContent = `Mở lại "${old.name}"`;
    reopen.hidden = false;
    reopen.onclick = async () => {
      if (!(await FS.ensurePermission(old))) { toast("Chưa được cấp quyền đọc thư mục."); return; }
      reopen.hidden = true;
      onRoot(old);
    };
  }

  // Folder tree. Rows are rebuilt on every render; selection is kept by key.
  function tree(el, o) {
    const want = o.selectable || "leaf";
    const closed = new Set();
    let root = null, sel = null, rows = [];

    function build() {
      rows = [];
      if (!root) return;
      (function walk(n, depth) {
        const f = o.folder ? o.folder(n) : {};
        if (depth > 0 && f.hidden) return;
        rows.push({ key: "d:" + n.path, node: n, depth, folder: true, label: n.name, cls: f.cls || "", aside: f.aside || "" });
        if (closed.has(n.path)) return;
        n.dirs.forEach(c => walk(c, depth + 1));
        for (const l of o.leaves ? o.leaves(n) : []) {
          rows.push({ key: "f:" + l.key, node: n, depth: depth + 1, folder: false, leaf: l,
            label: l.label, cls: l.cls || "", aside: l.aside || "", icon: l.icon || "" });
        }
      })(root, 0);
    }
    function render() {
      build();
      el.innerHTML = rows.map((r, i) =>
        `<div class="trow ${r.folder ? "folder" : "leaf"} ${r.cls}${r.key === sel ? " sel" : ""}" data-i="${i}" style="--d:${r.depth}" role="treeitem"` +
        (r.folder ? ` aria-expanded="${!closed.has(r.node.path)}">` : ">") +
        (r.folder ? `<span class="tw">${closed.has(r.node.path) ? "▸" : "▾"}</span>` : r.icon) +
        `<span class="nm" title="${esc(r.label)}">${esc(r.label)}</span>` +
        (r.aside ? `<span class="aside">${r.aside}</span>` : "") + `</div>`).join("");
      el.querySelector(".sel")?.scrollIntoView({ block: "nearest" });
    }
    const pickable = r => (want === "folder" ? r.folder : !r.folder);
    async function choose(r) {
      if (r.key === sel) return;
      if (o.canLeave && !(await o.canLeave())) return;
      sel = r.key;
      render();
      o.onSelect(r);
    }
    function toggle(path, open = closed.has(path)) {
      if (open) closed.delete(path); else closed.add(path);
      render();
    }
    el.addEventListener("click", e => {
      const row = e.target.closest(".trow");
      if (!row) return;
      const r = rows[+row.dataset.i];
      if (r.folder && (want !== "folder" || e.target.closest(".tw"))) { toggle(r.node.path); return; }
      if (pickable(r)) choose(r);
    });
    el.addEventListener("keydown", e => {
      const list = rows.filter(pickable);
      const i = list.findIndex(r => r.key === sel);
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const next = list[e.key === "ArrowDown" ? Math.min(list.length - 1, i + 1) : Math.max(0, i - 1)];
        if (next) choose(next);
      } else if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && i >= 0 && list[i].folder) {
        e.preventDefault();
        toggle(list[i].node.path, e.key === "ArrowRight");
      }
    });
    return {
      setRoot(r) { root = r; sel = null; closed.clear(); render(); },
      render,
      clear() { sel = null; render(); },
    };
  }

  window.CaptionUI = { $, esc, toast, ask, confirmLeave, folderRow, tree };
})();
```

Note: ←/→ act on a selected folder row, which only exists in Tab 3. In Tabs 1 and 2, folders open and close by click.

- [ ] **Step 3: Write** `prompt/CaptionPrompt/dist/index.html`:

```html
<!doctype html>
<html lang="vi" data-theme="sunny">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Caption Prompt</title>
<script>/* apply the saved theme before first paint */ try { if (JSON.parse(localStorage.getItem("captionPrompt.v1")).theme === "sky") document.documentElement.dataset.theme = "sky"; } catch (e) {}</script>
<style>
:root{
  --serif:"Sitka Heading","Sitka Text",Cambria,Georgia,serif;
  --sans:"Segoe UI Variable Text","Segoe UI",system-ui,sans-serif;
  --mono:"Cascadia Mono","Cascadia Code",Consolas,monospace;
  --r-lg:16px; --r:12px; --r-sm:9px;
}
[data-theme=sunny]{
  --bg:#FFF6E9; --card:#FFFFFF; --ink:#2A2140; --ink-2:#5B5170; --muted:#8C8299; --line:#F1DFC6;
  --primary:#FF6A3D; --primary-2:#FF9A3D; --on-primary:#FFFFFF; --accent:#12B3A3; --accent-wash:#DDF6F2;
  --danger:#E5384F; --danger-wash:#FFE3E6; --shadow:43 25 10;
}
[data-theme=sky]{
  --bg:#EEF6FF; --card:#FFFFFF; --ink:#13233F; --ink-2:#3E5070; --muted:#7486A3; --line:#D5E4F7;
  --primary:#2E6BFF; --primary-2:#22B8FF; --on-primary:#FFFFFF; --accent:#FFB020; --accent-wash:#FFF1D6;
  --danger:#E5384F; --danger-wash:#FFE3E6; --shadow:20 50 120;
}
:root{
  --sh-1:0 1px 2px rgb(var(--shadow)/.08),0 2px 6px rgb(var(--shadow)/.06);
  --sh-2:0 2px 4px rgb(var(--shadow)/.06),0 10px 24px -6px rgb(var(--shadow)/.16);
  --sh-3:0 4px 10px rgb(var(--shadow)/.08),0 20px 40px -12px rgb(var(--shadow)/.28);
  --inset:inset 0 2px 4px rgb(var(--shadow)/.06);
  --ring:0 0 0 2px var(--card),0 0 0 5px color-mix(in srgb,var(--primary) 70%,transparent);
}
*{box-sizing:border-box}
[hidden]{display:none!important}
html,body{margin:0;height:100%;background:var(--bg);color:var(--ink);font:14px/1.5 var(--sans)}
body{display:flex;flex-direction:column;overflow:hidden}
button,input,textarea,select{font:inherit;color:inherit}
button:disabled,textarea:disabled,input:disabled{opacity:.45;cursor:default}
button:disabled{pointer-events:none}

/* masthead */
.mast{display:flex;align-items:center;gap:16px;padding:18px 32px}
.logo{width:42px;height:42px;border-radius:13px;display:grid;place-items:center;color:var(--on-primary);font:700 20px var(--serif);background:linear-gradient(135deg,var(--primary),var(--primary-2));box-shadow:var(--sh-2)}
.mast h1{font:700 28px/1 var(--serif);margin:0;letter-spacing:-.01em}
.mast .sub{color:var(--muted);font-size:12.5px;margin-top:4px}
.spacer{flex:1}
.themes{display:inline-flex;gap:4px;padding:4px;border-radius:999px;background:var(--card);box-shadow:var(--sh-1)}
.themes button{border:0;border-radius:999px;padding:6px 14px;font-size:12px;font-weight:650;cursor:pointer;background:transparent;color:var(--ink-2);transition:background .15s,color .15s}
.themes button[aria-pressed=true],.themes button[aria-selected=true]{background:linear-gradient(135deg,var(--primary),var(--primary-2));color:var(--on-primary);box-shadow:var(--sh-1)}
.themes button:focus-visible{outline:none;box-shadow:var(--ring)}

/* controls */
.btn{height:38px;border:0;border-radius:var(--r);padding:0 16px;font-weight:650;font-size:13px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:7px;white-space:nowrap;background:var(--card);color:var(--ink);box-shadow:var(--sh-1),inset 0 0 0 1px var(--line);transition:transform .14s,box-shadow .14s,background .14s}
.btn:hover{transform:translateY(-1px);box-shadow:var(--sh-2),inset 0 0 0 1px var(--line)}
.btn:active{transform:translateY(1px) scale(.98);box-shadow:var(--sh-1)}
.btn:focus-visible{outline:none;box-shadow:var(--sh-1),var(--ring)}
.btn.primary,.btn[aria-pressed=true]{color:var(--on-primary);background:linear-gradient(135deg,var(--primary),var(--primary-2));box-shadow:var(--sh-2),inset 0 1px 0 rgb(255 255 255/.35)}
.btn.primary:hover{box-shadow:var(--sh-3),inset 0 1px 0 rgb(255 255 255/.35)}
.btn.danger{color:var(--danger);background:transparent;box-shadow:none}
.btn.danger:hover{background:var(--danger-wash)}
.btn.primary:focus-visible,.btn.danger:focus-visible{outline:none;box-shadow:var(--sh-2),var(--ring)}
.btn.icon{width:38px;padding:0}
.btn.sm{height:30px;padding:0 12px;font-size:12px}
.panel{background:var(--card);border-radius:var(--r-lg);box-shadow:var(--sh-2);padding:18px}
.label{display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:12px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--ink-2);margin-bottom:8px}
.label em{font-style:normal;text-transform:none;letter-spacing:0;font-weight:400;color:var(--muted)}
.fname{text-transform:none;letter-spacing:0;font:500 12px var(--mono);color:var(--muted)}
.field{display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--ink-2)}
.field select,.numin,.folderrow input{height:36px;padding:0 10px;border:1px solid var(--line);border-radius:var(--r-sm);background:var(--bg);box-shadow:var(--inset);outline:none;min-width:0;transition:border-color .15s,box-shadow .15s}
.field select{min-width:220px;font-weight:600;cursor:pointer}
.numin{width:72px;font-family:var(--mono)}
.field select:focus,.numin:focus{border-color:var(--primary);box-shadow:var(--inset),var(--ring)}
textarea{width:100%;resize:vertical;padding:14px 16px;border:1px solid var(--line);border-radius:var(--r);background:var(--bg);box-shadow:var(--inset);font:13px/1.6 var(--mono);outline:none;transition:border-color .15s,box-shadow .15s,background .15s}
textarea:focus{background:var(--card);border-color:var(--primary);box-shadow:var(--inset),var(--ring)}
.empty{color:var(--muted);font-size:13px;margin:12px 2px}
.dirty{color:var(--primary);font-size:16px;line-height:1}
.tag{display:inline-flex;font-size:11px;font-weight:650;padding:1px 8px;border-radius:999px;background:var(--accent-wash);color:color-mix(in srgb,var(--accent) 65%,var(--ink))}
.tag.nsfw{background:var(--danger-wash);color:var(--danger)}
.tag.cnt{background:var(--bg);color:var(--muted);font-weight:500}

/* tab layout */
.tab{flex:1;min-height:0;display:grid;grid-template-columns:340px minmax(0,1fr);gap:20px;padding:0 32px 24px}
.side{display:flex;flex-direction:column;gap:10px;min-height:0}
.main{display:flex;flex-direction:column;gap:14px;min-height:0;overflow:auto}
.folderrow{display:flex;gap:8px}
.folderrow input{flex:1;font-weight:600;color:var(--ink-2)}
.summary{font-size:12px;color:var(--muted);min-height:18px}

/* tree */
.tree{flex:1;min-height:0;overflow:auto;outline:none;margin:0 -8px;padding:2px 8px;border-radius:var(--r)}
.tree:focus-visible{box-shadow:var(--ring)}
.trow{display:flex;align-items:center;gap:7px;padding:5px 8px 5px calc(8px + var(--d) * 16px);border-radius:var(--r-sm);cursor:pointer;font-size:13px;white-space:nowrap}
.trow:hover{background:var(--bg)}
.trow.folder{font-weight:650;color:var(--ink-2)}
.trow .tw{width:12px;flex:none;text-align:center;color:var(--muted)}
.trow .nm{overflow:hidden;text-overflow:ellipsis}
.trow .aside{margin-left:auto;flex:none}
.trow.muted{color:var(--muted);font-weight:400}
.trow.hl{background:var(--accent-wash)}
.trow.sel{background:linear-gradient(135deg,var(--primary),var(--primary-2));color:var(--on-primary)}
.trow.sel .tw{color:var(--on-primary)}
.trow.sel .tag{background:rgb(255 255 255/.22);color:#fff}
.dot{width:8px;height:8px;border-radius:50%;background:var(--accent);flex:none}
.dot.no{background:none;box-shadow:inset 0 0 0 1.5px var(--muted)}

/* Tab 1: viewer, editor, snippets, logger */
.vbar{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.zoomv{font:600 12px var(--mono);min-width:48px;text-align:center;color:var(--ink-2)}
.vname{font:12px var(--mono);color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.viewer{position:relative;height:55vh;min-height:240px;overflow:hidden;border-radius:var(--r);background:var(--bg);box-shadow:var(--inset);cursor:grab;touch-action:none;user-select:none}
.viewer.panning{cursor:grabbing}
.viewer.cropping{cursor:crosshair}
.viewer img{position:absolute;left:0;top:0;transform-origin:0 0;max-width:none;pointer-events:none}
.viewer img:not([src]){display:none}
.vhint{position:absolute;inset:0;display:grid;place-items:center;margin:0;color:var(--muted);font-size:13px}
.croprect{position:absolute;border:2px dashed var(--primary);box-shadow:0 0 0 9999px rgb(0 0 0/.38);cursor:move}
.csize{position:absolute;left:-2px;top:-26px;font:600 11px var(--mono);padding:2px 7px;border-radius:6px;background:var(--primary);color:var(--on-primary);white-space:nowrap}
.h{position:absolute;width:12px;height:12px;margin:-7px 0 0 -7px;background:var(--card);border:2px solid var(--primary);border-radius:3px}
.h[data-h=nw]{left:0;top:0;cursor:nwse-resize}.h[data-h=n]{left:50%;top:0;cursor:ns-resize}.h[data-h=ne]{left:100%;top:0;cursor:nesw-resize}.h[data-h=e]{left:100%;top:50%;cursor:ew-resize}
.h[data-h=se]{left:100%;top:100%;cursor:nwse-resize}.h[data-h=s]{left:50%;top:100%;cursor:ns-resize}.h[data-h=sw]{left:0;top:100%;cursor:nesw-resize}.h[data-h=w]{left:0;top:50%;cursor:ew-resize}
.cropbar{position:absolute;right:12px;bottom:12px;display:flex;gap:8px}
#capEd{min-height:120px}
.chips{display:flex;align-items:flex-start;gap:8px;margin-top:10px}
.chiplist{display:flex;flex-wrap:wrap;gap:6px;flex:1}
.chip{border:0;border-radius:999px;padding:5px 12px;font-size:12px;font-weight:650;cursor:pointer;background:var(--accent-wash);color:color-mix(in srgb,var(--accent) 65%,var(--ink));transition:transform .12s}
.chip:hover{transform:translateY(-1px)}
.chip:focus-visible{outline:none;box-shadow:var(--ring)}
.wordsnote{margin-top:8px;font-size:12px;color:var(--muted)}
.log{height:120px;overflow:auto;font:12px/1.6 var(--mono);padding:8px 12px;border-radius:var(--r);background:var(--bg);box-shadow:var(--inset)}
.ll.info{color:var(--ink-2)}.ll.ok{color:color-mix(in srgb,var(--accent) 75%,var(--ink))}.ll.err{color:var(--danger)}
.wordlist{max-height:50vh;overflow:auto}
.wordrow,.wordadd{display:grid;grid-template-columns:120px minmax(0,1fr) auto;gap:8px;margin-bottom:8px}
.wordrow input,.wordadd input{height:36px;padding:0 10px;border:1px solid var(--line);border-radius:var(--r-sm);background:var(--bg);box-shadow:var(--inset);font:12.5px var(--mono);outline:none;min-width:0}
.wordrow input:focus,.wordadd input:focus{border-color:var(--primary);box-shadow:var(--inset),var(--ring)}

/* Tab 2 */
.mmtop{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.mmname{font:12px var(--mono);color:var(--muted)}
.warn{margin:0;padding:8px 12px;border-radius:var(--r);background:var(--danger-wash);color:var(--danger);font-size:12.5px}
.mmbody{display:grid;grid-template-columns:260px minmax(0,1fr);gap:16px}
.mmimg img{width:100%;max-height:72vh;object-fit:contain;border-radius:var(--r);background:var(--bg);display:block}
.mmeds{display:flex;flex-direction:column;gap:14px}
.mmeds textarea{height:32vh;min-height:180px}
.secr{display:flex;align-items:center;gap:10px}

/* Tab 3 */
.filtrow{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.gridhead{display:flex;align-items:baseline;gap:10px}
.gridhead h2{font:700 18px/1.2 var(--serif);margin:0;word-break:break-all}
.gridhead span{font-size:12px;color:var(--muted)}
.thumbs{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:12px}
.thumb{margin:0}
.thumb .ph{aspect-ratio:3/4;border-radius:var(--r);background:var(--bg);box-shadow:var(--inset);overflow:hidden}
.thumb img{width:100%;height:100%;object-fit:cover;display:block}
.thumb img:not([src]){visibility:hidden}
.thumb.bad .ph{background:var(--danger-wash)}
.thumb figcaption{font:11px var(--mono);color:var(--ink-2);margin-top:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

/* dialogs, toast */
dialog{width:560px;max-width:calc(100vw - 32px);padding:0;border:0;border-radius:20px;background:var(--card);color:var(--ink);box-shadow:var(--sh-3)}
dialog[open]{animation:pop .24s cubic-bezier(.2,.9,.3,1.2)}
dialog::backdrop{background:rgb(var(--shadow)/.28);backdrop-filter:blur(3px)}
.dlg{padding:20px 22px 22px;margin:0}
.dlghead{display:flex;justify-content:space-between;align-items:center}
.dlghead h3{font:700 18px/1.2 var(--serif);margin:0}
.dlg p{margin:6px 0 14px;font-size:12.5px;color:var(--muted)}
.dlg p.askmsg{font-size:14px;color:var(--ink);margin:0}
.dlgbtns{display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap;margin-top:16px}
.toast{position:fixed;left:50%;bottom:24px;transform:translate(-50%,90px);opacity:0;pointer-events:none;max-width:calc(100vw - 32px);background:var(--ink);color:var(--card);padding:10px 18px;border-radius:999px;font-size:13px;box-shadow:var(--sh-3);transition:transform .25s cubic-bezier(.2,.9,.3,1.2),opacity .2s}
.toast.show{transform:translate(-50%,0);opacity:1}

@keyframes pop{from{opacity:0;transform:translateY(8px) scale(.97)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
@media (max-width:900px){
  body{overflow:auto}
  .mast{flex-wrap:wrap;padding:16px}
  .tab{grid-template-columns:1fr;padding:0 16px 16px}
  .tree{max-height:40vh}
  .mmbody{grid-template-columns:1fr}
}
</style>
</head>
<body>

<header class="mast">
  <div class="logo" aria-hidden="true">C</div>
  <div>
    <h1>Caption Prompt</h1>
    <div class="sub">Caption, MiniMax H3 và lọc folder ảnh</div>
  </div>
  <div class="spacer"></div>
  <div class="themes" role="tablist" aria-label="Tab" id="tabsw">
    <button role="tab" data-tab="caption">Captioned</button><button role="tab" data-tab="minimax">MiniMax H3</button><button role="tab" data-tab="filter">Filt and Find</button>
  </div>
  <div class="themes" role="group" aria-label="Theme" id="themesw">
    <button data-theme-set="sunny">Sunny</button><button data-theme-set="sky">Sky</button>
  </div>
</header>

<!-- Tab 1: Captioned -->
<main class="tab" id="tab-caption" hidden>
  <aside class="panel side">
    <div class="folderrow"><input class="dirname" readonly placeholder="Chưa chọn thư mục" aria-label="Thư mục"><button class="btn primary pick">Chọn thư mục</button></div>
    <button class="btn reopen" hidden></button>
    <div class="summary" id="capSummary"></div>
    <div class="tree" id="capTree" tabindex="0" role="tree" aria-label="Ảnh"></div>
  </aside>
  <section class="main">
    <div class="panel">
      <div class="vbar">
        <button class="btn icon" id="capZoomOut" aria-label="Thu nhỏ">−</button>
        <span class="zoomv" id="capZoom">100%</span>
        <button class="btn icon" id="capZoomIn" aria-label="Phóng to">+</button>
        <button class="btn" id="capFit">Vừa khung</button>
        <span class="vname" id="capImgName"></span>
        <div class="spacer"></div>
        <button class="btn" id="capCrop" aria-pressed="false">✂ Crop</button>
      </div>
      <div class="viewer" id="capViewer">
        <img id="capImg" alt="" draggable="false">
        <div class="croprect" id="capRect" hidden>
          <span class="csize" id="capSize"></span>
          <i class="h" data-h="nw"></i><i class="h" data-h="n"></i><i class="h" data-h="ne"></i><i class="h" data-h="e"></i><i class="h" data-h="se"></i><i class="h" data-h="s"></i><i class="h" data-h="sw"></i><i class="h" data-h="w"></i>
        </div>
        <div class="cropbar" id="capCropBar" hidden><button class="btn" id="capCropCancel">Huỷ</button><button class="btn primary" id="capCropApply">Áp dụng</button></div>
        <p class="vhint" id="capHint">Chọn một ảnh ở cây bên trái</p>
      </div>
    </div>
    <div class="panel">
      <div class="label"><span>Prompt <span class="fname" id="capTxtName"></span> <span class="dirty" id="capDirty" hidden>●</span></span><button class="btn primary sm" id="capSave">Lưu</button></div>
      <textarea id="capEd" rows="5" placeholder="Chưa có file txt, sẽ tạo khi lưu" disabled aria-label="Prompt"></textarea>
      <div class="chips"><div class="chiplist" id="capChips"></div><button class="btn icon" id="capWordsOpen" aria-label="Sửa từ mẫu" title="Sửa từ mẫu">⚙</button></div>
      <div class="wordsnote" id="capWordsNote" hidden></div>
    </div>
    <div class="panel">
      <div class="label"><span>Logger</span><button class="btn danger sm" id="capLogClear">Xoá log</button></div>
      <div class="log" id="capLog" role="log" aria-live="polite"></div>
    </div>
  </section>
</main>

<!-- Tab 2: MiniMax H3 -->
<main class="tab" id="tab-minimax" hidden>
  <aside class="panel side">
    <div class="folderrow"><input class="dirname" readonly placeholder="Chưa chọn thư mục" aria-label="Thư mục"><button class="btn primary pick">Chọn thư mục</button></div>
    <button class="btn reopen" hidden></button>
    <div class="summary" id="mmSummary"></div>
    <div class="tree" id="mmTree" tabindex="0" role="tree" aria-label="Ảnh"></div>
  </aside>
  <section class="main panel">
    <div class="mmtop">
      <label class="field" id="mmVarWrap" hidden>Bản <select id="mmVar"></select></label>
      <span id="mmTag"></span>
      <span class="mmname" id="mmName"></span>
      <div class="spacer"></div>
      <span class="dirty" id="mmDirty" hidden>●</span>
      <button class="btn primary" id="mmSave" disabled>Lưu</button>
    </div>
    <p class="warn" id="mmWarn" hidden>Không nhận ra cấu trúc H3, cả file nằm ở ô 1</p>
    <p class="empty" id="mmEmpty">Chọn một ảnh ở cây bên trái</p>
    <div class="mmbody" id="mmBody" hidden>
      <div class="mmimg"><img id="mmImg" alt=""></div>
      <div class="mmeds">
        <div><div class="label"><span>CHARACTER &amp; SCENE DEFINITION</span><span class="secr"><em id="mmCount1"></em><button class="btn sm" id="mmCopy1">Copy</button></span></div><textarea id="mmEd1" aria-label="Character and scene definition"></textarea></div>
        <div><div class="label"><span>SHOT STRUCTURE — MINIMAX H3</span><span class="secr"><em id="mmCount2"></em><button class="btn sm" id="mmCopy2">Copy</button></span></div><textarea id="mmEd2" aria-label="Shot structure"></textarea></div>
      </div>
    </div>
  </section>
</main>

<!-- Tab 3: Filt and Find -->
<main class="tab" id="tab-filter" hidden>
  <aside class="panel side">
    <div class="folderrow"><input class="dirname" readonly placeholder="Chưa chọn thư mục" aria-label="Thư mục"><button class="btn primary pick">Chọn thư mục</button></div>
    <button class="btn reopen" hidden></button>
    <div class="filtrow"><label class="field">Số ảnh ≤ <input type="number" class="numin" id="fltN" min="1" step="1" value="5"></label><button class="btn primary" id="fltGo">Filt</button><button class="btn" id="fltClear">Bỏ lọc</button></div>
    <div class="summary" id="fltSummary"></div>
    <div class="tree" id="fltTree" tabindex="0" role="tree" aria-label="Folder"></div>
    <p class="empty" id="fltNone" hidden></p>
  </aside>
  <section class="main panel">
    <div class="gridhead"><h2 id="fltPath"></h2><span id="fltCount"></span></div>
    <p class="empty" id="fltEmpty">Chọn một folder ở cây bên trái</p>
    <div class="thumbs" id="fltGrid"></div>
  </section>
</main>

<dialog id="askDlg" aria-label="Xác nhận"><form method="dialog" class="dlg"><p class="askmsg" id="askMsg"></p><div class="dlgbtns" id="askBtns"></div></form></dialog>

<dialog id="wordsDlg" aria-label="Từ mẫu">
  <div class="dlg">
    <div class="dlghead"><h3>Từ mẫu</h3><button class="btn icon" id="wordsClose" aria-label="Đóng">&times;</button></div>
    <p id="wordsFileInfo"></p>
    <div class="wordlist" id="wordsList"></div>
    <div class="wordadd"><input id="wordsNewLabel" placeholder="Nhãn" aria-label="Nhãn mới"><input id="wordsNewText" placeholder="Nội dung chèn" aria-label="Nội dung mới"><button class="btn" id="wordsAdd">Thêm</button></div>
    <div class="dlgbtns"><button class="btn" id="wordsLink">Liên kết file JSON</button><button class="btn" id="wordsCreate">Tạo file mới</button><button class="btn" id="wordsImport">Import JSON</button></div>
  </div>
</dialog>

<div class="toast" id="toast" role="status"><span id="toastMsg"></span></div>

<script src="core.js"></script>
<script src="fs.js"></script>
<script src="ui.js"></script>
<script>
"use strict";
(function () {
  const KEY = "captionPrompt.v1", TABS = ["caption", "minimax", "filter"];
  const { $ } = window.CaptionUI;
  const st = { theme: "sunny", tab: "caption" };
  try { Object.assign(st, JSON.parse(localStorage.getItem(KEY)) || {}); } catch (e) { /* blocked or unreadable: defaults */ }
  if (st.theme !== "sky") st.theme = "sunny";
  if (!TABS.includes(st.tab)) st.tab = "caption";
  const persist = () => { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) { /* not saved, harmless */ } };

  function apply() {
    document.documentElement.dataset.theme = st.theme;
    document.querySelectorAll("[data-theme-set]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.themeSet === st.theme)));
    document.querySelectorAll("[data-tab]").forEach(b => b.setAttribute("aria-selected", String(b.dataset.tab === st.tab)));
    for (const t of TABS) $("tab-" + t).hidden = t !== st.tab;
  }
  $("themesw").addEventListener("click", e => { const b = e.target.closest("[data-theme-set]"); if (b) { st.theme = b.dataset.themeSet; persist(); apply(); } });
  $("tabsw").addEventListener("click", e => { const b = e.target.closest("[data-tab]"); if (b) { st.tab = b.dataset.tab; persist(); apply(); } });

  const mods = { caption: window.CaptionTab, minimax: window.MiniMaxTab, filter: window.FilterTab };
  const tabs = window.tabs = {};
  for (const t of TABS) if (mods[t]) tabs[t] = mods[t].init($("tab-" + t));

  addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); tabs[st.tab]?.save?.(); }
  });
  addEventListener("beforeunload", e => {
    if (Object.values(tabs).some(t => t.isDirty && t.isDirty())) { e.preventDefault(); e.returnValue = ""; }
  });
  apply();
})();
</script>
</body>
</html>
```

- [ ] **Step 4: Check in the browser** (see "How to check UI tasks"; no seed needed yet).
  - The page loads with no console errors, and the Captioned tab shows the folder row, an empty tree, the viewer hint "Chọn một ảnh ở cây bên trái", a disabled prompt editor, and an empty logger.
  - Clicking MiniMax H3 / Filt and Find switches tabs; Sky switches colors. After a reload, the same tab and theme come back.
  - `await CaptionFS.scanDir(await navigator.storage.getDirectory())` returns an object with `dirs` and `files` arrays.
  - Run `CaptionUI.ask("Thử?", [{id:"a",label:"A",kind:"primary"},{id:"b",label:"B"}]).then(v => window.__ask = v)` (do not await it). The dialog opens. Click B with a real click: after about 1s, `window.__ask === "b"`. Repeat and press Esc: `window.__ask === "cancel"`.
  - At 375px wide, the columns stack and nothing scrolls sideways.

- [ ] **Step 5: Run core tests again** (unchanged, must still pass): `cd prompt/CaptionPrompt && node test_core.mjs` → `core tests passed`.

- [ ] **Step 6: Commit**

```bash
git add prompt/CaptionPrompt/dist/index.html prompt/CaptionPrompt/dist/fs.js prompt/CaptionPrompt/dist/ui.js
git commit -m "Add CaptionPrompt page shell, file access and shared tree UI

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Tab 3, Filt and Find

**Files:**
- Create: `prompt/CaptionPrompt/dist/tab-filter.js`
- Modify: `prompt/CaptionPrompt/dist/index.html` (add `<script src="tab-filter.js"></script>` right after `<script src="ui.js"></script>`)

**Interfaces:**
- Consumes: `CaptionCore.{isImage, countLabel, filterTree}`, `CaptionFS.scanDir`, `CaptionUI.{$, esc, toast, folderRow, tree}`, and the markup ids `fltN fltGo fltClear fltSummary fltTree fltNone fltPath fltCount fltEmpty fltGrid`.
- Produces: `window.FilterTab = { init(el) -> { open(dirHandle) -> Promise } }`.

- [ ] **Step 1: Write** `prompt/CaptionPrompt/dist/tab-filter.js`:

```js
/* Tab 3: Filt and Find. Folder tree with image counts, filter by count, lazy thumbnail grid. window.FilterTab */
(function () {
  "use strict";
  const C = window.CaptionCore, FS = window.CaptionFS, UI = window.CaptionUI;
  const { $, esc, toast } = UI;

  function init(el) {
    const side = el.querySelector(".side");
    let root = null, total = 0;
    let filt = null;            // { matched, visible, total, max } while a filter is on
    let urls = [], io = null;   // thumbnail object URLs and their observer

    const tr = UI.tree($("fltTree"), {
      selectable: "folder",
      folder(n) {
        const label = esc(C.countLabel(n));
        if (!filt) return { aside: `<span class="tag cnt">${label}</span>` };
        if (filt.matched.has(n.path)) return { aside: `<span class="tag">${label}</span>` };
        return { hidden: !filt.visible.has(n.path), cls: "muted", aside: `<span class="tag cnt">${label}</span>` };
      },
      onSelect: r => showFolder(r.node),
    });

    function clearGrid() {
      if (io) io.disconnect();
      io = null;
      urls.forEach(u => URL.revokeObjectURL(u));
      urls = [];
      $("fltGrid").innerHTML = "";
    }
    function resetRight() {
      clearGrid();
      $("fltPath").textContent = "";
      $("fltCount").textContent = "";
      $("fltEmpty").textContent = "Chọn một folder ở cây bên trái";
      $("fltEmpty").hidden = false;
    }
    function showFolder(n) {
      clearGrid();
      const imgs = n.files.filter(f => C.isImage(f.name));
      $("fltPath").textContent = [root.name, n.path].filter(Boolean).join(" / ");
      $("fltCount").textContent = imgs.length + " ảnh";
      $("fltEmpty").textContent = "Folder này không có ảnh";
      $("fltEmpty").hidden = imgs.length > 0;
      $("fltGrid").innerHTML = imgs.map((f, i) =>
        `<figure class="thumb" data-i="${i}"><div class="ph"><img alt=""></div><figcaption title="${esc(f.name)}">${esc(f.name)}</figcaption></figure>`).join("");
      const mine = io = new IntersectionObserver(entries => {
        for (const en of entries) {
          if (!en.isIntersecting) continue;
          mine.unobserve(en.target);
          imgs[+en.target.dataset.i].handle.getFile().then(file => {
            if (io !== mine) return; // folder changed while loading
            const u = URL.createObjectURL(file);
            urls.push(u);
            en.target.querySelector("img").src = u;
          }).catch(() => en.target.classList.add("bad"));
        }
      }, { root: el.querySelector(".main"), rootMargin: "300px" });
      $("fltGrid").querySelectorAll(".thumb").forEach(t => mine.observe(t));
    }

    function updateSummary() {
      $("fltSummary").textContent = !root ? "" : filt ? `Khớp ${filt.matched.size} / ${filt.total} folder` : `${total} folder`;
      $("fltNone").hidden = !filt || filt.matched.size > 0;
      $("fltNone").textContent = filt ? `Không có folder nào có 1 đến ${filt.max} ảnh` : "";
    }
    function runFilter() {
      const n = Number($("fltN").value);
      if (!Number.isInteger(n) || n < 1) { toast("Nhập một số nguyên từ 1 trở lên"); $("fltN").focus(); return; }
      if (!root) { toast("Chọn thư mục trước"); return; }
      filt = { ...C.filterTree(root, n), max: n };
      updateSummary();
      tr.render();
    }
    $("fltGo").onclick = runFilter;
    $("fltN").addEventListener("keydown", e => { if (e.key === "Enter") runFilter(); });
    $("fltClear").onclick = () => { filt = null; updateSummary(); tr.render(); };

    async function open(h) {
      side.querySelector(".dirname").value = h.name;
      resetRight();
      $("fltSummary").textContent = "Đang quét…";
      root = await FS.scanDir(h, (p, e) => toast(`Bỏ qua ${p}: ${e.message}`));
      total = C.filterTree(root, 0).total; // filterTree counts every folder it walks
      filt = null;
      tr.setRoot(root);
      updateSummary();
    }

    UI.folderRow(side, "dir.filter", open);
    return { open };
  }

  window.FilterTab = { init };
})();
```

- [ ] **Step 2: Add the script tag.** In `index.html`, change `<script src="ui.js"></script>` to:

```html
<script src="ui.js"></script>
<script src="tab-filter.js"></script>
```

- [ ] **Step 3: Check in the browser.** Seed, switch to Filt and Find, then run `await tabs.filter.open(seedRoot)`.
  - The textbox shows `PostIG` and the summary shows `9 folder`. The rows read `PostIG 0 ảnh · 5 folder`, `day_52_1 0 ảnh · 1 folder`, `Ryo 1 ảnh`, …, `big 6 ảnh`, `empty 0 ảnh`.
  - Set N = 2 and click Filt. The summary shows `Khớp 3 / 9 folder`. The three `Ryo`/`Rennoir2` rows have accent pills, and their parents are muted. `big` and `empty` are hidden.
  - Set N = 0 and click Filt: a toast says "Nhập một số nguyên từ 1 trở lên". Set N = 1 and press Enter: 3 matches.
  - Click `big`: the header shows `PostIG / big`, `6 ảnh`, and 6 thumbnails load. Click `empty`: "Folder này không có ảnh" shows and the grid is empty. Click a thumbnail: nothing happens.
  - With the tree focused, ↑/↓ moves between folders and ←/→ closes/opens the selected folder.
  - **Bỏ lọc** shows all 9 folders again.

- [ ] **Step 4: Commit**

```bash
git add prompt/CaptionPrompt/dist/tab-filter.js prompt/CaptionPrompt/dist/index.html
git commit -m "Add Filt and Find tab: folder counts, count filter and lazy thumbnails

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Tab 2, MiniMax H3

**Files:**
- Create: `prompt/CaptionPrompt/dist/tab-minimax.js`
- Modify: `prompt/CaptionPrompt/dist/index.html` (add `<script src="tab-minimax.js"></script>` right before `<script src="tab-filter.js"></script>`)

**Interfaces:**
- Consumes: `CaptionCore.{pairFolder, anyImage, splitH3, h3Bodies, setH3Bodies}`, `CaptionFS.{scanDir, readText, writeFile}`, `CaptionUI.{$, esc, toast, confirmLeave, folderRow, tree}`, and the markup ids `mmSummary mmTree mmVarWrap mmVar mmTag mmName mmDirty mmSave mmWarn mmEmpty mmBody mmImg mmEd1 mmEd2 mmCount1 mmCount2 mmCopy1 mmCopy2`.
- Produces: `window.MiniMaxTab = { init(el) -> { open(dirHandle), isDirty() -> boolean, save() -> Promise<boolean> } }`.

- [ ] **Step 1: Write** `prompt/CaptionPrompt/dist/tab-minimax.js`:

```js
/* Tab 2: MiniMax H3. Image + its _H3_ prompt split into two editable sections. window.MiniMaxTab */
(function () {
  "use strict";
  const C = window.CaptionCore, FS = window.CaptionFS, UI = window.CaptionUI;
  const { $, esc, toast } = UI;

  const tag = (text, nsfw) => `<span class="tag${nsfw ? " nsfw" : ""}">${esc(text)}</span>`;
  const tagOf = list => list.length === 1
    ? tag(list[0].rating, list[0].rating === "nsfw")
    : tag(`${list.length} bản`, list.some(h => h.rating === "nsfw"));

  function init(el) {
    const side = el.querySelector(".side");
    const pairs = new Map(); // folder node -> pairFolder() result
    const pairsOf = n => { if (!pairs.has(n)) pairs.set(n, C.pairFolder(n.files.map(f => f.name))); return pairs.get(n); };
    const fileOf = (n, name) => n.files.find(f => f.name === name).handle;
    let root = null;
    let cur = null;          // { node, entry, v, handle, split, url }
    let saved = ["", ""];    // editor texts as last loaded or saved

    const isDirty = () => !!(cur && cur.split) && ($("mmEd1").value !== saved[0] || $("mmEd2").value !== saved[1]);

    const tr = UI.tree($("mmTree"), {
      folder: n => ({ hidden: !C.anyImage(n) }),
      leaves: n => pairsOf(n).map(e => ({
        key: (n.path ? n.path + "/" : "") + e.image, label: e.image, entry: e,
        cls: e.h3.length ? "hl" : "muted", aside: e.h3.length ? tagOf(e.h3) : "",
      })),
      canLeave: () => UI.confirmLeave(isDirty, save),
      onSelect: r => show(r.node, r.leaf.entry),
    });

    function refresh() {
      $("mmDirty").hidden = !isDirty();
      $("mmCount1").textContent = $("mmEd1").value.length + " ký tự";
      $("mmCount2").textContent = $("mmEd2").value.length + " ký tự";
    }
    function resetRight(msg) {
      if (cur && cur.url) URL.revokeObjectURL(cur.url);
      cur = null;
      saved = ["", ""];
      $("mmImg").removeAttribute("src");
      $("mmVarWrap").hidden = true;
      $("mmTag").innerHTML = "";
      $("mmName").textContent = "";
      $("mmSave").disabled = true;
      $("mmWarn").hidden = true;
      $("mmBody").hidden = true;
      $("mmEmpty").textContent = msg;
      $("mmEmpty").hidden = false;
      refresh();
    }

    async function show(node, entry) {
      resetRight("Ảnh này chưa có file H3");
      $("mmName").textContent = entry.image;
      if (!entry.h3.length) return;
      const my = cur = { node, entry, v: 0, handle: null, split: null, url: null };
      $("mmVar").innerHTML = entry.h3.map((h, i) => `<option value="${i}">${esc(h.name)}</option>`).join("");
      $("mmVarWrap").hidden = entry.h3.length < 2;
      $("mmEmpty").hidden = true;
      $("mmBody").hidden = false;
      $("mmSave").disabled = false;
      try {
        const file = await fileOf(node, entry.image).getFile();
        if (cur !== my) return;
        my.url = URL.createObjectURL(file);
        $("mmImg").src = my.url;
      } catch (e) { toast(`Không đọc được ${entry.image}: ${e.message}`); }
      await loadVariant(0);
    }

    async function loadVariant(i) {
      const my = cur, h = my.entry.h3[i];
      let text;
      try { text = await FS.readText(fileOf(my.node, h.name)); }
      catch (e) { toast(`Không đọc được ${h.name}: ${e.message}`); return; }
      if (cur !== my) return;
      my.v = i;
      my.handle = fileOf(my.node, h.name);
      my.split = C.splitH3(text);
      saved = C.h3Bodies(my.split);
      $("mmEd1").value = saved[0];
      $("mmEd2").value = saved[1];
      $("mmEd2").disabled = !my.split.recognized;
      $("mmWarn").hidden = my.split.recognized;
      $("mmVar").value = String(i);
      $("mmTag").innerHTML = tagOf([h]);
      refresh();
    }

    async function save() {
      if (!cur || !cur.split) return false;
      if (!isDirty()) return true;
      const name = cur.entry.h3[cur.v].name;
      const text = C.setH3Bodies(cur.split, $("mmEd1").value, $("mmEd2").value);
      try { await FS.writeFile(cur.handle, text); }
      catch (e) { toast(`Không lưu được ${name}: ${e.message}`); return false; }
      cur.split = C.splitH3(text);
      saved = [$("mmEd1").value, $("mmEd2").value];
      refresh();
      toast(`Đã lưu ${name}`);
      return true;
    }

    async function copy(ed, btn) {
      try { await navigator.clipboard.writeText(ed.value); }
      catch (e) { ed.select(); document.execCommand("copy"); }
      btn.textContent = "Đã copy";
      setTimeout(() => { btn.textContent = "Copy"; }, 1500);
      toast("Đã copy");
    }

    $("mmVar").addEventListener("change", async e => {
      const i = +e.target.value;
      if (!(await UI.confirmLeave(isDirty, save))) { e.target.value = String(cur.v); return; }
      loadVariant(i);
    });
    $("mmEd1").addEventListener("input", refresh);
    $("mmEd2").addEventListener("input", refresh);
    $("mmCopy1").onclick = () => copy($("mmEd1"), $("mmCopy1"));
    $("mmCopy2").onclick = () => copy($("mmEd2"), $("mmCopy2"));
    $("mmSave").onclick = save;

    function summary() {
      let imgs = 0, files = 0;
      (function walk(n) {
        for (const e of pairsOf(n)) if (e.h3.length) { imgs++; files += e.h3.length; }
        n.dirs.forEach(walk);
      })(root);
      $("mmSummary").textContent = `${imgs} ảnh có H3 · ${files} file txt`;
    }
    async function open(h) {
      if (!(await UI.confirmLeave(isDirty, save))) return;
      side.querySelector(".dirname").value = h.name;
      resetRight("Chọn một ảnh ở cây bên trái");
      $("mmSummary").textContent = "Đang quét…";
      root = await FS.scanDir(h, (p, e) => toast(`Bỏ qua ${p}: ${e.message}`));
      pairs.clear();
      tr.setRoot(root);
      summary();
    }

    UI.folderRow(side, "dir.minimax", open);
    return { open, isDirty, save };
  }

  window.MiniMaxTab = { init };
})();
```

- [ ] **Step 2: Add the script tag.** In `index.html`, change `<script src="tab-filter.js"></script>` to:

```html
<script src="tab-minimax.js"></script>
<script src="tab-filter.js"></script>
```

- [ ] **Step 3: Check in the browser.** Seed, switch to MiniMax H3, then run `await tabs.minimax.open(seedRoot)`.
  - The summary shows `3 ảnh có H3 · 5 file txt`. `A.png` and `C.png` have an `sfw` tag, and `B.png` has a red `3 bản` tag. `big`'s six images show muted with no tag. `empty` is hidden because it has no images.
  - Click `B.png`. The combobox lists `B_H3_nsfw.txt`, `B_H3_nsfw_v2.txt`, `B_H3_sfw.txt`. Editor 1 shows `**summary:**\n\nA man dances.`. Editor 2 starts with `[SHOT 01` and contains `---`.
  - Change editor 2's `Step two.` to `Step 2.`. The ● appears. Press Ctrl+S: a toast says `Đã lưu B_H3_nsfw.txt`. Then `(await readSeed("PostIG/day_53_1/Ryo/B_H3_nsfw.txt")) === seedB.replace("Step two.", "Step 2.")` returns `true`.
  - Edit editor 1, then pick `B_H3_sfw.txt` in the combobox. The "Có thay đổi chưa lưu." dialog appears. **Huỷ** keeps the combobox on the old file with the edit intact. **Bỏ thay đổi** switches files; `B_H3_sfw.txt` (headless layout) shows editor 1 `subject_definitions:\n\nA swimmer.`.
  - Click Copy on editor 1. The button reads "Đã copy" briefly, and the clipboard holds the editor text (check with `await navigator.clipboard.readText()`).
  - Click `img1.png` under `big`. The right side shows only "Ảnh này chưa có file H3", the name `img1.png`, and a disabled **Lưu**.

- [ ] **Step 4: Commit**

```bash
git add prompt/CaptionPrompt/dist/tab-minimax.js prompt/CaptionPrompt/dist/index.html
git commit -m "Add MiniMax H3 tab: split editors, variant picker, copy and in-order save

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Tab 1, viewer with zoom, pan and crop, caption editor and logger

**Files:**
- Create: `prompt/CaptionPrompt/dist/viewer.js`
- Create: `prompt/CaptionPrompt/dist/tab-caption.js`
- Modify: `prompt/CaptionPrompt/dist/index.html` (add `<script src="viewer.js"></script>` and `<script src="tab-caption.js"></script>` right before `<script src="tab-minimax.js"></script>`)

**Interfaces:**
- Consumes: `CaptionCore.{pairFolder, anyImage, baseName, detectEol, toEol, copyPngText}`, `CaptionFS.{scanDir, readText, writeFile, writeText}`, `CaptionUI.{$, ask, confirmLeave, folderRow, tree}`, and the markup ids `capSummary capTree capZoomOut capZoom capZoomIn capFit capImgName capCrop capViewer capImg capRect capSize capCropBar capCropCancel capCropApply capHint capTxtName capDirty capSave capEd capLog capLogClear`.
- Produces:
  - `window.CaptionViewer = { create(box, img, rectEl, sizeEl, onChange) -> { load(url) -> Promise<{ w, h }>, clear(), fit(), zoomBy(factor), setCrop(on), rect() -> { x, y, w, h } | null } }`. `onChange({ zoom })` fires after each view change. `rect()` is in integer original-image pixels.
  - `window.CaptionTab = { init(el) -> { open(dirHandle), isDirty(), save() -> Promise<boolean>, log(level: "info"|"ok"|"err", msg) } }`.

- [ ] **Step 1: Write** `prompt/CaptionPrompt/dist/viewer.js`:

```js
/* Image viewer: wheel zoom around the cursor, drag to pan, crop rectangle with 8 handles. window.CaptionViewer */
(function () {
  "use strict";
  const MIN = 0.1, MAX = 8;
  const norm = (a, b, c, d) => ({ x: Math.min(a, c), y: Math.min(b, d), w: Math.abs(c - a), h: Math.abs(d - b) });

  function create(box, img, rectEl, sizeEl, onChange) {
    let W = 0, H = 0;          // image size in pixels
    let s = 1, tx = 0, ty = 0; // screen = t + image * s
    let crop = null;           // { x, y, w, h } in image pixels while crop mode is on
    let cropOn = false, drag = null;

    function rect() {
      if (!crop) return null;
      const x = Math.round(crop.x), y = Math.round(crop.y);
      const w = Math.min(W - x, Math.round(crop.w)), h = Math.min(H - y, Math.round(crop.h));
      return w >= 1 && h >= 1 ? { x, y, w, h } : null;
    }
    function apply() {
      img.style.transform = `translate(${tx}px, ${ty}px) scale(${s})`;
      rectEl.hidden = !(cropOn && crop);
      if (cropOn && crop) {
        Object.assign(rectEl.style, { left: tx + crop.x * s + "px", top: ty + crop.y * s + "px", width: crop.w * s + "px", height: crop.h * s + "px" });
        const r = rect();
        sizeEl.textContent = r ? `${r.w}×${r.h}` : "0×0";
      }
      if (onChange) onChange({ zoom: s });
    }
    function fit() {
      if (!W) return;
      const bw = box.clientWidth, bh = box.clientHeight;
      s = Math.min(bw / W, bh / H);
      tx = (bw - W * s) / 2;
      ty = (bh - H * s) / 2;
      apply();
    }
    function zoomAt(f, mx, my) {
      const ns = Math.min(MAX, Math.max(MIN, s * f));
      tx = mx - (mx - tx) * (ns / s);
      ty = my - (my - ty) * (ns / s);
      s = ns;
      apply();
    }
    const zoomBy = f => { if (W) zoomAt(f, box.clientWidth / 2, box.clientHeight / 2); };
    function toImg(e) {
      const b = box.getBoundingClientRect();
      return { x: Math.min(W, Math.max(0, (e.clientX - b.left - tx) / s)), y: Math.min(H, Math.max(0, (e.clientY - b.top - ty) / s)) };
    }

    box.addEventListener("wheel", e => {
      if (!W) return;
      e.preventDefault();
      const b = box.getBoundingClientRect();
      zoomAt(e.deltaY < 0 ? 1.1 : 1 / 1.1, e.clientX - b.left, e.clientY - b.top);
    }, { passive: false });

    box.addEventListener("pointerdown", e => {
      if (!W || e.target.closest(".cropbar")) return;
      if (!cropOn || e.button === 1) drag = { kind: "pan", x: e.clientX, y: e.clientY, tx, ty };
      else if (e.button !== 0) return;
      else if (e.target.dataset.h) drag = { kind: "resize", h: e.target.dataset.h, start: { ...crop } };
      else if (rectEl.contains(e.target)) drag = { kind: "move", p: toImg(e), start: { ...crop } };
      else { const p = toImg(e); drag = { kind: "new", p }; crop = { x: p.x, y: p.y, w: 0, h: 0 }; }
      box.setPointerCapture(e.pointerId);
      box.classList.toggle("panning", drag.kind === "pan");
      e.preventDefault();
    });
    box.addEventListener("pointermove", e => {
      if (!drag) return;
      if (drag.kind === "pan") {
        tx = drag.tx + e.clientX - drag.x;
        ty = drag.ty + e.clientY - drag.y;
      } else {
        const p = toImg(e), c = drag.start;
        if (drag.kind === "new") crop = norm(drag.p.x, drag.p.y, p.x, p.y);
        else if (drag.kind === "move") {
          crop = { ...c, x: Math.min(W - c.w, Math.max(0, c.x + p.x - drag.p.x)), y: Math.min(H - c.h, Math.max(0, c.y + p.y - drag.p.y)) };
        } else {
          let l = c.x, t = c.y, r = c.x + c.w, b = c.y + c.h;
          if (drag.h.includes("w")) l = p.x;
          if (drag.h.includes("e")) r = p.x;
          if (drag.h.includes("n")) t = p.y;
          if (drag.h.includes("s")) b = p.y;
          crop = norm(l, t, r, b);
        }
      }
      apply();
    });
    const end = () => { drag = null; box.classList.remove("panning"); };
    box.addEventListener("pointerup", end);
    box.addEventListener("pointercancel", end);

    function load(url) {
      return new Promise((res, rej) => {
        img.onload = () => { W = img.naturalWidth; H = img.naturalHeight; fit(); res({ w: W, h: H }); };
        img.onerror = () => rej(new Error("không giải mã được ảnh"));
        img.src = url;
      });
    }
    function clear() { W = H = 0; crop = null; img.removeAttribute("src"); apply(); }
    function setCrop(on) {
      cropOn = on && W > 0;
      crop = cropOn ? { x: W * 0.1, y: H * 0.1, w: W * 0.8, h: H * 0.8 } : null; // start with a centered 80% box
      box.classList.toggle("cropping", cropOn);
      apply();
    }
    return { load, clear, fit, zoomBy, setCrop, rect };
  }

  window.CaptionViewer = { create };
})();
```

- [ ] **Step 2: Write** `prompt/CaptionPrompt/dist/tab-caption.js`:

```js
/* Tab 1: Captioned. Image tree, viewer with crop, same-name caption txt, logger. window.CaptionTab */
(function () {
  "use strict";
  const C = window.CaptionCore, FS = window.CaptionFS, UI = window.CaptionUI;
  const { $ } = UI;
  const MIME = { png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", webp: "image/webp" };

  function init(el) {
    const side = el.querySelector(".side");
    const pairs = new Map(); // folder node -> pairFolder() result (entries are updated in place)
    const pairsOf = n => { if (!pairs.has(n)) pairs.set(n, C.pairFolder(n.files.map(f => f.name))); return pairs.get(n); };
    const fileOf = (n, name) => n.files.find(f => f.name === name).handle;
    let root = null;
    let cur = null; // { node, entry, eol, saved, url }

    // ---- logger ----
    function log(level, msg) {
      const box = $("capLog"), line = document.createElement("div");
      line.className = "ll " + level;
      line.textContent = `${new Date().toTimeString().slice(0, 8)} ${level === "ok" ? "✓" : level === "err" ? "✕" : "·"} ${msg}`;
      box.append(line);
      while (box.childElementCount > 200) box.firstElementChild.remove();
      box.scrollTop = box.scrollHeight;
    }
    $("capLogClear").onclick = () => { $("capLog").innerHTML = ""; };

    // ---- tree ----
    const isDirty = () => !!cur && !$("capEd").disabled && $("capEd").value !== cur.saved;
    const tr = UI.tree($("capTree"), {
      folder: n => ({ hidden: !C.anyImage(n) }),
      leaves: n => pairsOf(n).map(e => ({
        key: (n.path ? n.path + "/" : "") + e.image, label: e.image, entry: e,
        cls: e.caption ? "" : "muted", icon: `<span class="dot${e.caption ? "" : " no"}"></span>`,
      })),
      canLeave: () => UI.confirmLeave(isDirty, save),
      onSelect: r => show(r.node, r.leaf.entry),
    });
    function summary() {
      let imgs = 0, txt = 0;
      (function walk(n) { for (const e of pairsOf(n)) { imgs++; if (e.caption) txt++; } n.dirs.forEach(walk); })(root);
      $("capSummary").textContent = `${imgs} ảnh · ${txt} có txt`;
      return { imgs, txt };
    }

    // ---- viewer and crop ----
    const view = window.CaptionViewer.create($("capViewer"), $("capImg"), $("capRect"), $("capSize"),
      st => { $("capZoom").textContent = Math.round(st.zoom * 100) + "%"; });
    let cropOn = false;
    function setCrop(on) {
      cropOn = on && !!cur;
      view.setCrop(cropOn);
      $("capCrop").setAttribute("aria-pressed", String(cropOn));
      $("capCropBar").hidden = !cropOn;
    }
    $("capZoomIn").onclick = () => view.zoomBy(1.25);
    $("capZoomOut").onclick = () => view.zoomBy(1 / 1.25);
    $("capFit").onclick = () => view.fit();
    $("capCrop").onclick = () => setCrop(!cropOn);
    $("capCropCancel").onclick = () => setCrop(false);
    $("capCropApply").onclick = applyCrop;
    document.addEventListener("keydown", e => {
      if (e.key === "Escape" && cropOn && !el.hidden && !document.querySelector("dialog[open]")) setCrop(false);
    });

    async function applyCrop() {
      const r = view.rect();
      if (!cur || !r) { log("err", "Khung crop trống"); return; }
      const name = cur.entry.image;
      const ok = await UI.ask(`Ghi đè ${name}? Không hoàn tác được.`, [{ id: "ok", label: "Ghi đè", kind: "primary" }, { id: "cancel", label: "Huỷ" }]);
      if (ok !== "ok") return;
      const fh = fileOf(cur.node, name);
      const type = MIME[name.split(".").pop().toLowerCase()];
      try {
        const file = await fh.getFile();
        const bmp = await createImageBitmap(file);
        const cv = document.createElement("canvas");
        cv.width = r.w;
        cv.height = r.h;
        cv.getContext("2d").drawImage(bmp, r.x, r.y, r.w, r.h, 0, 0, r.w, r.h);
        bmp.close();
        const blob = await new Promise((res, rej) => cv.toBlob(b => (b ? res(b) : rej(new Error("không mã hoá được ảnh"))), type, 0.95));
        let bytes = new Uint8Array(await blob.arrayBuffer());
        if (type === "image/png") bytes = C.copyPngText(new Uint8Array(await file.arrayBuffer()), bytes);
        await FS.writeFile(fh, bytes);
        log("ok", `Crop ${r.w}×${r.h} ${name}` + (type === "image/png" ? ", giữ metadata PNG" : ""));
        setCrop(false);
        await showImage();
      } catch (e) { log("err", `Không crop được ${name}: ${e.message}`); }
    }

    async function showImage() {
      const my = cur;
      try {
        const file = await fileOf(my.node, my.entry.image).getFile();
        if (cur !== my) return;
        if (my.url) URL.revokeObjectURL(my.url);
        my.url = URL.createObjectURL(file);
        const { w, h } = await view.load(my.url);
        if (cur !== my) return;
        $("capImgName").textContent = `${my.entry.image} · ${w}×${h}`;
        $("capHint").hidden = true;
      } catch (e) { log("err", `Không đọc được ${my.entry.image}: ${e.message}`); }
    }

    // ---- caption editor ----
    const txtName = entry => entry.caption || C.baseName(entry.image) + ".txt";
    function refreshDirty() { $("capDirty").hidden = !isDirty(); }
    $("capEd").addEventListener("input", refreshDirty);

    async function show(node, entry) {
      setCrop(false);
      if (cur && cur.url) URL.revokeObjectURL(cur.url);
      const my = cur = { node, entry, eol: "\n", saved: "", url: null };
      const ed = $("capEd");
      ed.disabled = true;
      ed.value = "";
      $("capTxtName").textContent = txtName(entry);
      refreshDirty();
      showImage();
      if (entry.caption) {
        try {
          const t = await FS.readText(fileOf(node, entry.caption));
          if (cur !== my) return;
          my.eol = C.detectEol(t);
          my.saved = C.toEol(t, "\n");
        } catch (e) {
          log("err", `Không đọc được ${entry.caption}: ${e.message}`);
          return; // editor stays disabled so an unread file is never overwritten
        }
      }
      if (cur !== my) return;
      ed.value = my.saved;
      ed.disabled = false;
      refreshDirty();
    }

    async function save() {
      if (!cur || $("capEd").disabled) return false;
      if (!isDirty()) return true;
      const text = $("capEd").value, name = txtName(cur.entry), isNew = !cur.entry.caption;
      let fh;
      try { fh = await FS.writeText(cur.node.handle, name, C.toEol(text, cur.eol)); }
      catch (e) { log("err", `Không lưu được ${name}: ${e.message}`); return false; }
      cur.saved = text;
      refreshDirty();
      if (isNew) {
        cur.node.files.push({ name, handle: fh });
        cur.entry.caption = name;
        tr.render();
        summary();
        log("ok", `Đã tạo ${name}`);
      } else log("ok", `Đã lưu ${name}`);
      return true;
    }
    $("capSave").onclick = save;

    // ---- folder ----
    async function open(h) {
      if (!(await UI.confirmLeave(isDirty, save))) return;
      side.querySelector(".dirname").value = h.name;
      setCrop(false);
      if (cur && cur.url) URL.revokeObjectURL(cur.url);
      cur = null;
      view.clear();
      $("capHint").hidden = false;
      $("capImgName").textContent = "";
      $("capTxtName").textContent = "";
      $("capEd").value = "";
      $("capEd").disabled = true;
      refreshDirty();
      $("capSummary").textContent = "Đang quét…";
      root = await FS.scanDir(h, (p, e) => log("err", `Bỏ qua ${p}: ${e.message}`));
      pairs.clear();
      tr.setRoot(root);
      const s = summary();
      log("info", `Nạp ${h.name}: ${s.imgs} ảnh, ${s.txt} txt`);
    }

    UI.folderRow(side, "dir.caption", open);
    return { open, isDirty, save, log };
  }

  window.CaptionTab = { init };
})();
```

- [ ] **Step 3: Add the script tags.** In `index.html`, change `<script src="tab-minimax.js"></script>` to:

```html
<script src="viewer.js"></script>
<script src="tab-caption.js"></script>
<script src="tab-minimax.js"></script>
```

- [ ] **Step 4: Check in the browser.** Seed, switch to Captioned, then run `await tabs.caption.open(seedRoot)`.
  - The logger shows `· Nạp PostIG: 9 ảnh, 1 txt` and the summary shows `9 ảnh · 1 có txt`. `A.png` has a filled dot; the others have hollow dots and muted text. `empty` is hidden.
  - Click `A.png`. The image is fit-centered, and the bar shows `A.png · 300×400`. The editor value is `"Ivan_Ryo, a 25yo Asian young man\n"` (the file's final CRLF shown as one `\n`).
  - Wheel over the image: the zoom percent changes and the point under the cursor stays put. Drag: the image pans. `+`/`−` change zoom; **Vừa khung** fits again.
  - Edit the text and press Ctrl+S. The logger shows `✓ Đã lưu A.txt`, and `await readSeed("PostIG/day_52_1/Ryo/A.txt")` ends with `\r\n` (original CRLF kept).
  - Click `B.png` and type `hello`, then click `C.png`. The unsaved dialog appears. Choose **Lưu**. The logger shows `✓ Đã tạo B.txt`, `B.png` now has a filled dot, and the summary shows `2 có txt`. `await readSeed("PostIG/day_53_1/Ryo/B.txt") === "hello"` (new file, `\n` style, no extra newline).
  - Click `A.png`, then **✂ Crop**: an 80% box shows with its size label `240×320`. Drag the `se` handle inward: the label shrinks. Esc leaves crop mode.
  - Crop again, click **Áp dụng**, then **Ghi đè**. The logger shows `✓ Crop <w>×<h> A.png, giữ metadata PNG`, and the image reloads at the new size.
  - Click **Xoá log**: the logger empties.

- [ ] **Step 5: Commit**

```bash
git add prompt/CaptionPrompt/dist/viewer.js prompt/CaptionPrompt/dist/tab-caption.js prompt/CaptionPrompt/dist/index.html
git commit -m "Add Captioned tab: image tree, zoom/pan/crop viewer, caption editor and logger

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Snippet chips and the word-list JSON file

**Files:**
- Create: `prompt/CaptionPrompt/dist/words.js`
- Create: `prompt/CaptionPrompt/dist/caption_words.json`
- Modify: `prompt/CaptionPrompt/dist/index.html` (add `<script src="words.js"></script>` right before `<script src="tab-caption.js"></script>`)
- Modify: `prompt/CaptionPrompt/dist/tab-caption.js` (one line after `$("capSave").onclick = save;`)

**Interfaces:**
- Consumes: `CaptionCore.{padSnippet, DEFAULT_WORDS, parseWords, mergeWords, wordsJson}`, `CaptionFS.{remember, recall, pickFile, createFile, ensurePermission, readText, writeFile}`, `CaptionUI.{$, esc, toast}`, the markup ids `capChips capWordsOpen capWordsNote wordsDlg wordsClose wordsFileInfo wordsList wordsNewLabel wordsNewText wordsAdd wordsLink wordsCreate wordsImport`, and Tab 1's `log(level, msg)`.
- Produces: `window.CaptionWords = { init({ editor: HTMLTextAreaElement, log }) }`.

- [ ] **Step 1: Write** `prompt/CaptionPrompt/dist/caption_words.json` (same content as `DEFAULT_WORDS`):

```json
{
  "version": 1,
  "words": [
    {
      "label": "Ivan",
      "text": "Ivan_Ryo, a 25yo Asian young man"
    },
    {
      "label": "Close-up",
      "text": "close-up shot"
    },
    {
      "label": "Soft light",
      "text": "soft natural light"
    },
    {
      "label": "Gym",
      "text": "in a gym"
    }
  ]
}
```

Check it matches the default: `cd prompt/CaptionPrompt && node -e "const C=require('./dist/core.js');const fs=require('fs');console.log(fs.readFileSync('dist/caption_words.json','utf8')===C.wordsJson(C.DEFAULT_WORDS))"` → `true`.

- [ ] **Step 2: Write** `prompt/CaptionPrompt/dist/words.js`:

```js
/* Snippet chips under the caption editor, and the word-list dialog backed by a linked JSON file. window.CaptionWords */
(function () {
  "use strict";
  const C = window.CaptionCore, FS = window.CaptionFS, UI = window.CaptionUI;
  const { $, esc, toast } = UI;
  const JSON_TYPES = [{ description: "JSON", accept: { "application/json": [".json"] } }];

  function init({ editor, log }) {
    let words = C.DEFAULT_WORDS.map(w => ({ ...w }));
    let handle = null; // linked JSON file, set only after it was read

    // ---- chips ----
    function renderChips() {
      $("capChips").innerHTML = words.map((w, i) => `<button class="chip" data-i="${i}" title="${esc(w.text)}">${esc(w.label)}</button>`).join("");
    }
    $("capChips").addEventListener("mousedown", e => { if (e.target.closest(".chip")) e.preventDefault(); }); // keep the caret in the editor
    $("capChips").addEventListener("click", e => {
      const b = e.target.closest(".chip");
      if (!b || editor.disabled) return;
      editor.focus();
      const s = editor.selectionStart, end = editor.selectionEnd;
      // execCommand keeps the insert on the editor's undo stack (Ctrl+Z) and fires "input".
      document.execCommand("insertText", false, C.padSnippet(editor.value.slice(0, s), editor.value.slice(end), words[+b.dataset.i].text));
    });

    // ---- JSON file ----
    function note(html) { $("capWordsNote").innerHTML = html; $("capWordsNote").hidden = !html; }
    async function load(h) {
      try {
        words = C.parseWords(await FS.readText(h));
        handle = h;
        note("");
        log("ok", `Đọc ${h.name}: ${words.length} từ`);
      } catch (e) { log("err", `${h.name}: ${e.message}`); }
      renderChips();
      renderList();
    }
    async function write() {
      if (!handle) return;
      try { await FS.writeFile(handle, C.wordsJson(words)); log("ok", `Đã ghi ${handle.name}`); }
      catch (e) { log("err", `Không ghi được ${handle.name}: ${e.message}`); }
    }
    async function link(h) {
      FS.remember("wordsFile", h).catch(() => {});
      await load(h);
    }

    // ---- dialog ----
    function renderList() {
      const off = handle ? "" : " disabled";
      $("wordsFileInfo").textContent = handle
        ? `Đã liên kết: ${handle.name}. Thay đổi được ghi vào file ngay.`
        : "Chưa liên kết file JSON. Liên kết hoặc tạo file mới để sửa danh sách.";
      $("wordsList").innerHTML = words.map((w, i) =>
        `<div class="wordrow" data-i="${i}"><input data-f="label" value="${esc(w.label)}" aria-label="Nhãn"${off}>` +
        `<input data-f="text" value="${esc(w.text)}" aria-label="Nội dung"${off}>` +
        `<button class="btn icon danger" data-del="${i}" aria-label="Xoá ${esc(w.label)}"${off}>&times;</button></div>`).join("");
      for (const id of ["wordsNewLabel", "wordsNewText", "wordsAdd", "wordsImport"]) $(id).disabled = !handle;
    }
    $("capWordsOpen").onclick = () => { renderList(); $("wordsDlg").showModal(); };
    $("wordsClose").onclick = () => $("wordsDlg").close();
    $("wordsDlg").addEventListener("click", e => { if (e.target === $("wordsDlg")) $("wordsDlg").close(); }); // backdrop
    $("wordsList").addEventListener("change", e => {
      const row = e.target.closest(".wordrow"), f = e.target.dataset.f;
      if (!row || !f) return;
      const w = words[+row.dataset.i], v = e.target.value.trim();
      if (!v) { e.target.value = w[f]; toast("Không để trống nhãn hoặc nội dung"); return; }
      w[f] = v;
      renderChips();
      write();
    });
    $("wordsList").addEventListener("click", e => {
      const i = e.target.closest("[data-del]")?.dataset.del;
      if (i === undefined) return;
      words.splice(+i, 1);
      renderChips();
      renderList();
      write();
    });
    $("wordsAdd").onclick = () => {
      const label = $("wordsNewLabel").value.trim(), text = $("wordsNewText").value.trim();
      if (!label || !text) { toast("Nhập cả nhãn và nội dung"); return; }
      const m = C.mergeWords(words, [{ label, text }]);
      if (!m.added) { toast(`Nhãn "${label}" đã có`); return; }
      words = m.words;
      $("wordsNewLabel").value = $("wordsNewText").value = "";
      renderChips();
      renderList();
      write();
      $("wordsNewLabel").focus();
    };
    $("wordsNewText").addEventListener("keydown", e => { if (e.key === "Enter") $("wordsAdd").click(); });
    $("wordsLink").onclick = async () => {
      let h;
      try { h = await FS.pickFile({ types: JSON_TYPES }); } catch (e) { return; } // cancelled
      if (await FS.ensurePermission(h)) link(h);
    };
    $("wordsCreate").onclick = async () => {
      let h;
      try { h = await FS.createFile({ suggestedName: "caption_words.json", types: JSON_TYPES }); } catch (e) { return; }
      try { await FS.writeFile(h, C.wordsJson(words)); }
      catch (e) { log("err", `Không tạo được ${h.name}: ${e.message}`); return; }
      link(h);
    };
    $("wordsImport").onclick = async () => {
      let h;
      try { h = await FS.pickFile({ types: JSON_TYPES }); } catch (e) { return; }
      try {
        const m = C.mergeWords(words, C.parseWords(await FS.readText(h)));
        words = m.words;
        renderChips();
        renderList();
        await write();
        log("ok", `Import: +${m.added}, bỏ qua ${m.skipped}`);
      } catch (e) { log("err", `${h.name}: ${e.message}`); }
    };

    // ---- startup: reopen the remembered file ----
    renderChips();
    (async () => {
      const old = await FS.recall("wordsFile").catch(() => null);
      if (!old) { note("Chưa liên kết file JSON · đang dùng bộ từ mặc định"); return; }
      if (old.queryPermission && (await old.queryPermission({ mode: "readwrite" })) !== "granted") {
        note(`<button class="btn sm" id="capWordsAllow">Cho phép đọc ${esc(old.name)}</button>`);
        $("capWordsAllow").onclick = async () => { if (await FS.ensurePermission(old)) load(old); };
        return;
      }
      load(old);
    })();
  }

  window.CaptionWords = { init };
})();
```

- [ ] **Step 3: Wire it into Tab 1.** In `tab-caption.js`, replace:

```js
    $("capSave").onclick = save;
```

with:

```js
    $("capSave").onclick = save;
    window.CaptionWords.init({ editor: $("capEd"), log });
```

- [ ] **Step 4: Add the script tag.** In `index.html`, change `<script src="tab-caption.js"></script>` to:

```html
<script src="words.js"></script>
<script src="tab-caption.js"></script>
```

- [ ] **Step 5: Check in the browser.** Seed, then run `await tabs.caption.open(seedRoot)`.
  - Chips `Ivan`, `Close-up`, `Soft light`, `Gym` show, with the note "Chưa liên kết file JSON · đang dùng bộ từ mặc định".
  - Click `A.png`, put the caret right after `man`, and click `Gym`: the text reads `young man in a gym` (one space added). Ctrl+Z removes the insert. Put the caret at the very start and click `Close-up`: the text starts with `close-up shot Ivan_Ryo` (space after).
  - Open ⚙. The inputs and the Thêm/Import buttons are disabled, and the dialog says it is not linked.
  - Link a JSON file without the picker: run `const R=await navigator.storage.getDirectory(); const f=await R.getFileHandle("caption_words.json",{create:true}); const w=await f.createWritable(); await w.write(JSON.stringify({version:1,words:[{label:"Rain",text:"in the rain"}]})); await w.close(); await CaptionFS.remember("wordsFile", f);` then reload the page. The chips now show only `Rain`, and the logger shows `✓ Đọc caption_words.json: 1 từ`.
  - In ⚙, add label `Night`, text `at night`, and click Thêm. A `Night` chip appears. `JSON.parse(await (await f.getFile()).text()).words.length === 2` (re-acquire `f` from OPFS after the reload). Adding `night` again shows the toast `Nhãn "night" đã có`.
  - Edit a label to empty and blur: it reverts, and a toast says "Không để trống nhãn hoặc nội dung". Click × on `Rain`: it is removed from the chips and the file.
  - Make the file invalid (`{"x":1}`) and reload: the logger shows `✕ caption_words.json: File thiếu mảng "words"`, and the chips fall back to the defaults.

- [ ] **Step 6: Commit**

```bash
git add prompt/CaptionPrompt/dist/words.js prompt/CaptionPrompt/dist/caption_words.json prompt/CaptionPrompt/dist/index.html prompt/CaptionPrompt/dist/tab-caption.js
git commit -m "Add snippet chips and a word-list dialog backed by a linked JSON file

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: README, and a final check with the user on real copies

**Files:**
- Modify: `README.md` (one line in the `prompt/` tree)

- [ ] **Step 1: Update README.** In `README.md`, replace:

```
├── prompt/ — Xử lý và chuẩn hoá prompt.
│   ├── prompt_Collector/ — Web UI gom prompt: double-click dist/index.html, lọc câu thừa, export TXT (Text_Splitter) / JSON.
```

with:

```
├── prompt/ — Xử lý và chuẩn hoá prompt.
│   ├── CaptionPrompt/ — Web UI 3 tab: mở dist/index.html bằng Chrome/Edge; sửa caption + crop ảnh, sửa prompt MiniMax H3, lọc folder theo số ảnh.
│   ├── prompt_Collector/ — Web UI gom prompt: double-click dist/index.html, lọc câu thừa, export TXT (Text_Splitter) / JSON.
```

- [ ] **Step 2: Run the core tests once more**: `cd prompt/CaptionPrompt && node test_core.mjs` → `core tests passed`.

- [ ] **Step 3: Make copies of the real sample folders** (never touch the originals):

```bash
mkdir -p "H:/004_Learn/_caption_check" && cp -r "H:/004_Learn/PostIG/day_52_1" "H:/004_Learn/PostIG/day_53_1" "H:/004_Learn/PostIG/day_56_1" "H:/004_Learn/_caption_check/"
```

Record the original metadata keys for later:

```bash
python -I -c "from PIL import Image; import sys; print(sorted(Image.open(sys.argv[1]).info))" "H:/004_Learn/_caption_check/day_52_1/Ryo/ZImage_2026_06_06_111928_60_00001.png"
```

Expected: `['parameters', 'prompt', 'workflow']`.

- [ ] **Step 4: Ask the user** to open `D:\001_PersonalProject\PersonalTools\prompt\CaptionPrompt\dist\index.html` in Chrome and, using **Chọn thư mục** on `H:\004_Learn\_caption_check`:
  1. **Captioned:** crop `day_52_1/Ryo/ZImage_..._00001.png` (Áp dụng → Ghi đè), then type a caption and save.
  2. **MiniMax H3:** change one word in section 2 of each of the three layouts (`day_52_1`, `day_53_1` sfw, `day_56_1`), and save each.
  3. **Filt and Find:** pick `H:\004_Learn\PostIG`, then try Filt with N = 1, 2, 5.
  4. Reload the page and confirm **Mở lại** brings back each tab's folder.

- [ ] **Step 5: Verify the user's edits on disk.**
  - Metadata kept after crop (same keys as step 3, with a new size):

    ```bash
    python -I -c "from PIL import Image; import sys; im=Image.open(sys.argv[1]); print(im.size, sorted(im.info))" "H:/004_Learn/_caption_check/day_52_1/Ryo/ZImage_2026_06_06_111928_60_00001.png"
    ```

  - Only the edited body changed in each H3 file:

    ```bash
    git diff --no-index --stat "H:/004_Learn/PostIG/day_52_1/Ryo/ZImage_2026_06_06_111928_60_00001_H3_sfw.txt" "H:/004_Learn/_caption_check/day_52_1/Ryo/ZImage_2026_06_06_111928_60_00001_H3_sfw.txt"
    git diff --no-index "H:/004_Learn/PostIG/day_53_1/Ryo/ZImage_2026_06_06_101818_60_00001_H3_sfw.txt" "H:/004_Learn/_caption_check/day_53_1/Ryo/ZImage_2026_06_06_101818_60_00001_H3_sfw.txt"
    git diff --no-index "H:/004_Learn/PostIG/day_56_1/Rennoir2/ZImage_2026_06_06_224612_63_00001_H3_sfw.txt" "H:/004_Learn/_caption_check/day_56_1/Rennoir2/ZImage_2026_06_06_224612_63_00001_H3_sfw.txt"
    ```

    Expected: each diff shows only the changed word's line; headings, `---` and blank lines are untouched. `file` on each copy still reports `CRLF line terminators`.
  - Report the results to the user, and ask whether to delete `H:\004_Learn\_caption_check`.

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "List CaptionPrompt in the README tree

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
