# Prompt Collector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A double-clickable local web page (`prompt/prompt_Collector/dist/index.html`) that collects pasted image prompts, strips unwanted sentences, lets the user review/edit/reorder them, autosaves to localStorage, and exports TXT (for ComfyUI `Text_Splitter`) and JSON files split by a per-file threshold.

**Architecture:** Two runtime files, no build step. `dist/core.js` holds all pure logic (cleaning, dedupe, chunking, file naming, export payloads, state parsing) and exposes `window.PromptCore`, plus `module.exports` for Node. `dist/index.html` holds markup, CSS and the UI script (DOM, events, localStorage, downloads) and loads `core.js` with a classic `<script src>`, because `type="module"` is blocked on `file://`. `test_core.mjs` checks `core.js` with `node:assert`.

**Tech Stack:** Plain HTML/CSS/ES2020 JavaScript, Chrome/Edge. Node 22 (already installed) only for running `test_core.mjs`.

**Spec:** `docs/superpowers/specs/2026-10-08-prompt-collector-design.md` (mockup: `docs/superpowers/specs/2026-10-08-prompt-collector-mockup.html`)

## Global Constraints

- Runs by double-clicking `dist/index.html` in Chrome/Edge (`file://`). No build step, no npm packages, no network requests, system fonts only.
- UI text in English.
- No exported prompt may contain `\n\n`; files join prompts with exactly `\n\n`. `###` inside a prompt is preserved untouched.
- localStorage key `promptCollector.v1`; corrupt backup key `promptCollector.v1.corrupt`.
- Default strip keywords: `uploaded photo`, `facial structure`, `exact body proportions`, `reference image`. Default prompts per file: `50`.
- File names: `prompt_YYYYMMDD.txt` for one file, `prompt_YYYYMMDD_01.txt`, `_02`… for several (3 digits when more than 99). Same pattern for `.json`.
- Colors: paper `#F3F3EF`, ink `#16171A`, single accent `#C8361D` (destructive actions, duplicates, struck text only). 3px radius everywhere, no drop shadows, no nested cards.
- Out of scope: Import JSON, negative prompts, IndexedDB, ZIP, save-folder picker, dark theme, Firefox.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Work on branch `ver004`.

## File Structure

```
prompt/prompt_Collector/
  dist/core.js      pure logic, no DOM (Tasks 1-2)
  dist/index.html   markup + CSS + UI script (Tasks 3-5)
  test_core.mjs     node test_core.mjs (Tasks 1-2)
README.md           add the new folder to the tree (Task 5)
```

All commands below run from the repo root `D:\001_PersonalProject\PersonalTools` unless stated otherwise.

**How to check UI tasks (3-5):** a human double-clicks `prompt\prompt_Collector\dist\index.html`. An agent cannot drive `file://` pages in the browser pane, so instead it serves the folder and opens `http://localhost:8765/` in the built-in browser:

```bash
python -m http.server 8765 -d prompt/prompt_Collector/dist
```

(run it in the background; localStorage on `localhost` is separate from the `file://` data, so testing there touches nothing real). Stop the server when the task is done.

---

### Task 1: Core cleaning, dedupe and state parsing

**Files:**
- Create: `prompt/prompt_Collector/dist/core.js`
- Test: `prompt/prompt_Collector/test_core.mjs`

**Interfaces:**
- Consumes: nothing.
- Produces (`PromptCore.*`, also `require("./dist/core.js")`):
  - `DEFAULT_KEYWORDS: string[]`, `DEFAULT_PER_FILE: 50`
  - `collapseBlank(text: string) -> string`
  - `clean(raw: string, keywords: string[]) -> { text: string, removed: string[] }`
  - `findDuplicate(items: {text}[], text: string) -> number` (index or -1)
  - `reclean(items: Item[], keywords: string[]) -> Item[]` (new array, unedited items re-cleaned)
  - `defaultState() -> State`, `parseState(str: string|null) -> { state: State, corrupt: boolean }`
  - `Item = { id, raw, text, removed: string[], edited: boolean, addedAt }`, `State = { version: 1, items: Item[], keywords: string[], perFile: number, selected: number }`

- [ ] **Step 1: Write the failing test**

Create `prompt/prompt_Collector/test_core.mjs`:

```js
// Run: node test_core.mjs   (from prompt/prompt_Collector)
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const C = createRequire(import.meta.url)("./dist/core.js");
const KW = ["uploaded photo", "facial structure"];

// --- clean / collapseBlank ---
// CRLF, blank runs and whitespace-only lines collapse to a single "\n"
assert.equal(C.clean("A.\r\n\r\n\r\nB.\n   \n\t\nC.", KW).text, "A.\nB.\nC.");
// keyword sentence removed (case-insensitive), rest of the line kept
{
  const r = C.clean("Man at dawn. Use the UPLOADED PHOTO face. Shot on 35mm.", KW);
  assert.equal(r.text, "Man at dawn. Shot on 35mm.");
  assert.deepEqual(r.removed, ["Use the UPLOADED PHOTO face."]);
}
// a removed line leaves no blank gap
assert.equal(C.clean("Top.\n\nKeep the facial structure.\n\nBottom.", KW).text, "Top.\nBottom.");
// everything stripped -> empty text
assert.equal(C.clean("Same facial structure as the uploaded photo.", KW).text, "");
// "###" and single newlines preserved, trailing spaces trimmed
assert.equal(C.clean("pos one  \npos two###neg", KW).text, "pos one\npos two###neg");
// blank keywords never strip anything
assert.equal(C.clean("Hello.", ["", "  "]).text, "Hello.");
// leading indentation kept, blank lines collapsed
assert.equal(C.collapseBlank("a\n\n  b  \n"), "a\n  b");

// --- findDuplicate ---
assert.equal(C.findDuplicate([{ text: "x" }, { text: "y" }], "y"), 1);
assert.equal(C.findDuplicate([], "y"), -1);

// --- reclean: only items not edited by hand, input not mutated ---
{
  const items = [
    { raw: "Keep. Drop me.", text: "Keep. Drop me.", removed: [], edited: false },
    { raw: "Keep. Drop me.", text: "hand edit", removed: [], edited: true },
  ];
  const out = C.reclean(items, ["drop me"]);
  assert.equal(out[0].text, "Keep.");
  assert.deepEqual(out[0].removed, ["Drop me."]);
  assert.equal(out[1].text, "hand edit");
  assert.equal(items[0].text, "Keep. Drop me.");
}

// --- defaults and parseState ---
assert.deepEqual(C.DEFAULT_KEYWORDS, ["uploaded photo", "facial structure", "exact body proportions", "reference image"]);
assert.equal(C.parseState(null).corrupt, false);
assert.deepEqual(C.parseState(null).state, { version: 1, items: [], keywords: C.DEFAULT_KEYWORDS, perFile: 50, selected: 0 });
assert.equal(C.parseState("{not json").corrupt, true);
assert.equal(C.parseState(JSON.stringify({ version: 2, items: [], keywords: [] })).corrupt, true);
assert.equal(C.parseState(JSON.stringify({ version: 1, items: [], keywords: [], perFile: 0 })).state.perFile, 50);
{
  const s = { version: 1, items: [{ id: "a", raw: "r", text: "t", removed: [], edited: false, addedAt: "x" }], keywords: ["k"], perFile: 7, selected: 0 };
  assert.deepEqual(C.parseState(JSON.stringify(s)), { state: s, corrupt: false });
}

console.log("core: all checks passed");
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd prompt/prompt_Collector && node test_core.mjs`
Expected: FAIL with `Cannot find module './dist/core.js'`

- [ ] **Step 3: Write minimal implementation**

Create `prompt/prompt_Collector/dist/core.js`:

```js
/* Prompt Collector core: pure logic, no DOM.
   Loaded by dist/index.html as a classic script (window.PromptCore) and by test_core.mjs via require. */
(function (root) {
  "use strict";

  const DEFAULT_KEYWORDS = ["uploaded photo", "facial structure", "exact body proportions", "reference image"];
  const DEFAULT_PER_FILE = 50;
  const SENTENCE_SPLIT = /(?<=[.!?])\s+/;

  // CRLF -> LF, strip trailing spaces per line, collapse any run of blank lines into one "\n", trim.
  // ComfyUI Text_Splitter cuts files on the exact string "\n\n", so no prompt may keep one inside.
  function collapseBlank(text) {
    return String(text).replace(/\r\n?/g, "\n")
      .split("\n").map(line => line.replace(/\s+$/, "")).join("\n")
      .replace(/\n\s*\n+/g, "\n")
      .trim();
  }

  // Drop every sentence that contains a keyword (case-insensitive), then collapse blank lines.
  function clean(raw, keywords) {
    const kws = keywords.map(k => k.trim().toLowerCase()).filter(Boolean);
    const removed = [];
    const lines = String(raw).replace(/\r\n?/g, "\n").split("\n").map(line =>
      line.split(SENTENCE_SPLIT).filter(sentence => {
        const lower = sentence.toLowerCase();
        const hit = kws.some(k => lower.includes(k));
        if (hit) removed.push(sentence.trim());
        return !hit;
      }).join(" "));
    return { text: collapseBlank(lines.join("\n")), removed };
  }

  function findDuplicate(items, text) {
    return items.findIndex(it => it.text === text);
  }

  // Re-run clean on items the user has not edited by hand. Returns new objects; input untouched.
  function reclean(items, keywords) {
    return items.map(it => it.edited ? it : { ...it, ...clean(it.raw, keywords) });
  }

  function defaultState() {
    return { version: 1, items: [], keywords: DEFAULT_KEYWORDS.slice(), perFile: DEFAULT_PER_FILE, selected: 0 };
  }

  // str: the localStorage value or null. corrupt=true means str existed but is unusable (caller backs it up).
  function parseState(str) {
    if (str == null) return { state: defaultState(), corrupt: false };
    let s;
    try { s = JSON.parse(str); } catch (e) { return { state: defaultState(), corrupt: true }; }
    if (!s || s.version !== 1 || !Array.isArray(s.items) || !Array.isArray(s.keywords)) {
      return { state: defaultState(), corrupt: true };
    }
    const state = { ...defaultState(), ...s };
    if (!Number.isInteger(state.perFile) || state.perFile < 1) state.perFile = DEFAULT_PER_FILE;
    return { state, corrupt: false };
  }

  const api = { DEFAULT_KEYWORDS, DEFAULT_PER_FILE, collapseBlank, clean, findDuplicate, reclean, defaultState, parseState };
  root.PromptCore = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd prompt/prompt_Collector && node test_core.mjs`
Expected: `core: all checks passed`

- [ ] **Step 5: Commit**

```bash
git add prompt/prompt_Collector/dist/core.js prompt/prompt_Collector/test_core.mjs
git commit -m "Add Prompt Collector core cleaning and state parsing

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Core chunking, file names and export payloads

**Files:**
- Modify: `prompt/prompt_Collector/dist/core.js` (add functions before `const api = …`, extend `api`)
- Test: `prompt/prompt_Collector/test_core.mjs` (insert before the final `console.log`)

**Interfaces:**
- Consumes: `collapseBlank` from Task 1.
- Produces (`PromptCore.*`):
  - `chunk(list: T[], size: number) -> T[][]`
  - `move(list: T[], from: number, to: number) -> T[]` (new array)
  - `stamp(d: Date) -> "YYYYMMDD"` (local time)
  - `isoLocal(d: Date) -> "YYYY-MM-DDTHH:MM:SS+07:00"` (local time with offset)
  - `fileNames(d: Date, count: number, ext: "txt"|"json") -> string[]`
  - `buildFiles(kind: "txt"|"json", items: Item[], { perFile: number, keywords: string[], now?: Date }) -> { files: {name, content}[], skipped: number }`

- [ ] **Step 1: Write the failing test**

In `prompt/prompt_Collector/test_core.mjs`, insert this block immediately before the line `console.log("core: all checks passed");`:

```js
// --- chunk / move ---
assert.deepEqual(C.chunk([], 3), []);
assert.deepEqual(C.chunk([1, 2, 3], 3), [[1, 2, 3]]);
assert.deepEqual(C.chunk([1, 2, 3, 4], 3), [[1, 2, 3], [4]]);
assert.deepEqual(C.move(["a", "b", "c", "d"], 0, 2), ["b", "c", "a", "d"]);
assert.deepEqual(C.move(["a", "b", "c", "d"], 3, 0), ["d", "a", "b", "c"]);

// --- stamp / isoLocal / fileNames ---
const day = new Date(2026, 9, 8, 14, 2, 0);
assert.equal(C.stamp(day), "20261008");
assert.match(C.isoLocal(day), /^2026-10-08T14:02:00[+-]\d\d:\d\d$/);
assert.deepEqual(C.fileNames(day, 0, "txt"), []);
assert.deepEqual(C.fileNames(day, 1, "txt"), ["prompt_20261008.txt"]);
assert.deepEqual(C.fileNames(day, 3, "json"), ["prompt_20261008_01.json", "prompt_20261008_02.json", "prompt_20261008_03.json"]);
assert.equal(C.fileNames(day, 120, "txt")[0], "prompt_20261008_001.txt");
assert.equal(C.fileNames(day, 120, "txt")[119], "prompt_20261008_120.txt");

// --- buildFiles ---
const mk = (text, i) => ({ id: "i" + i, raw: "raw " + i, text, removed: [], edited: false, addedAt: "t" });
assert.deepEqual(C.buildFiles("txt", [], { perFile: 5, keywords: [] }).files, []);
// 120 prompts at 50 per file: 3 files, Text_Splitter sees every prompt exactly once
{
  const items = Array.from({ length: 120 }, (_, i) => mk(`prompt ${i + 1}`, i));
  const { files, skipped } = C.buildFiles("txt", items, { perFile: 50, keywords: [], now: day });
  assert.equal(skipped, 0);
  assert.deepEqual(files.map(f => f.name), ["prompt_20261008_01.txt", "prompt_20261008_02.txt", "prompt_20261008_03.txt"]);
  const blocks = files.flatMap(f => f.content.split("\n\n").map(b => b.trim()).filter(Boolean)); // Text_Splitter logic
  assert.equal(blocks.length, 120);
  assert.equal(blocks[50], "prompt 51");
  assert.ok(files[2].content.endsWith("prompt 120\n"));
}
// hand-typed blank lines are collapsed, empty prompts skipped, "###" kept
{
  const items = [mk("line one\n\n\nline two", 0), mk("   ", 1), mk("solo###neg", 2)];
  const { files, skipped } = C.buildFiles("txt", items, { perFile: 50, keywords: [], now: day });
  assert.equal(skipped, 1);
  assert.deepEqual(files, [{ name: "prompt_20261008.txt", content: "line one\nline two\n\nsolo###neg\n" }]);
}
// JSON parts, global index, field mapping
{
  const items = [mk("a", 0), mk("b", 1), mk("c", 2)];
  items[1].removed = ["Use the uploaded photo."];
  const { files } = C.buildFiles("json", items, { perFile: 2, keywords: ["uploaded photo"], now: day });
  assert.deepEqual(files.map(f => f.name), ["prompt_20261008_01.json", "prompt_20261008_02.json"]);
  const p2 = JSON.parse(files[1].content);
  assert.equal(p2.app, "prompt-collector");
  assert.equal(p2.version, 1);
  assert.equal(p2.part, 2);
  assert.equal(p2.parts, 2);
  assert.equal(p2.total, 3);
  assert.deepEqual(p2.strip_keywords, ["uploaded photo"]);
  assert.match(p2.exported_at, /^2026-10-08T14:02:00/);
  assert.deepEqual(p2.prompts, [{ index: 3, text: "c", original: "raw 2", removed: [], edited: false, added_at: "t" }]);
  assert.deepEqual(JSON.parse(files[0].content).prompts[1].removed, ["Use the uploaded photo."]);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd prompt/prompt_Collector && node test_core.mjs`
Expected: FAIL with `TypeError: C.chunk is not a function`

- [ ] **Step 3: Write minimal implementation**

In `prompt/prompt_Collector/dist/core.js`, replace the line

```js
  const api = { DEFAULT_KEYWORDS, DEFAULT_PER_FILE, collapseBlank, clean, findDuplicate, reclean, defaultState, parseState };
```

with:

```js
  function chunk(list, size) {
    const out = [];
    for (let i = 0; i < list.length; i += size) out.push(list.slice(i, i + size));
    return out;
  }

  function move(list, from, to) {
    const out = list.slice();
    out.splice(to, 0, out.splice(from, 1)[0]);
    return out;
  }

  const pad = (n, width = 2) => String(n).padStart(width, "0");

  function stamp(d) {
    return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}`;
  }

  function isoLocal(d) {
    const off = -d.getTimezoneOffset(), abs = Math.abs(off);
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
      `T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}` +
      `${off >= 0 ? "+" : "-"}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
  }

  function fileNames(d, count, ext) {
    const base = `prompt_${stamp(d)}`;
    if (count === 1) return [`${base}.${ext}`];
    const width = count > 99 ? 3 : 2;
    return Array.from({ length: count }, (_, i) => `${base}_${pad(i + 1, width)}.${ext}`);
  }

  // kind: "txt" | "json". Text is collapsed again (hand edits may contain blank lines); empty prompts are skipped.
  function buildFiles(kind, items, { perFile, keywords, now = new Date() }) {
    const prompts = [];
    for (const it of items) {
      const text = collapseBlank(it.text);
      if (text) prompts.push({ ...it, text });
    }
    const chunks = chunk(prompts, perFile);
    const names = fileNames(now, chunks.length, kind);
    const files = chunks.map((group, part) => ({
      name: names[part],
      content: kind === "txt"
        ? group.map(p => p.text).join("\n\n") + "\n"
        : JSON.stringify({
            app: "prompt-collector",
            version: 1,
            exported_at: isoLocal(now),
            part: part + 1,
            parts: chunks.length,
            total: prompts.length,
            strip_keywords: keywords,
            prompts: group.map((p, j) => ({
              index: part * perFile + j + 1,
              text: p.text,
              original: p.raw,
              removed: p.removed,
              edited: p.edited,
              added_at: p.addedAt,
            })),
          }, null, 2) + "\n",
    }));
    return { files, skipped: items.length - prompts.length };
  }

  const api = {
    DEFAULT_KEYWORDS, DEFAULT_PER_FILE, collapseBlank, clean, findDuplicate, reclean, defaultState, parseState,
    chunk, move, stamp, isoLocal, fileNames, buildFiles,
  };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd prompt/prompt_Collector && node test_core.mjs`
Expected: `core: all checks passed`

- [ ] **Step 5: Commit**

```bash
git add prompt/prompt_Collector/dist/core.js prompt/prompt_Collector/test_core.mjs
git commit -m "Add Prompt Collector chunking, file naming and export payloads

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Page shell, autosave, composer, list and editor

**Files:**
- Create: `prompt/prompt_Collector/dist/index.html`

**Interfaces:**
- Consumes: `PromptCore.clean`, `findDuplicate`, `parseState`, `fileNames`, `isoLocal` (Tasks 1-2).
- Produces (globals inside the page script, used by Tasks 4-5): `state`, `$(id)`, `esc(s)`, `changed()` (re-render + debounced save), `render()`, `renderKeywords()`, `toast(msg, action?, sticky?)` where `action = { label, run }`. The script ends with the line `boot();`; later tasks insert code immediately before it. Buttons `#del`, `#clear`, `#kwOpen`, `#exportTxt`, `#exportJson` and the `#kwDlg` dialog exist in the markup but do nothing until Tasks 4-5.

- [ ] **Step 1: Create the page**

Create `prompt/prompt_Collector/dist/index.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prompt Collector</title>
<style>
:root{
  --paper:#F3F3EF; --sheet:#FBFBF8; --ink:#16171A; --ink-2:#45464B; --muted:#76777C;
  --rule:#D8D8D1; --rule-2:#E6E6E0; --accent:#C8361D; --accent-wash:#F6E3DE;
  --serif:"Sitka Heading","Sitka Text",Cambria,Georgia,serif;
  --sans:"Segoe UI Variable Text","Segoe UI",system-ui,sans-serif;
  --mono:"Cascadia Mono","Cascadia Code",Consolas,monospace;
  --r:3px;
}
*{box-sizing:border-box}
[hidden]{display:none!important}
html,body{margin:0;background:var(--paper);color:var(--ink);font:14px/1.5 var(--sans)}
button,input,textarea{font:inherit;color:inherit}
button:disabled{opacity:.4;cursor:default;pointer-events:none}

.mast{display:grid;grid-template-columns:1fr auto;align-items:end;gap:24px;padding:28px 40px 18px;border-bottom:2px solid var(--ink)}
.mast h1{font:600 34px/1 var(--serif);letter-spacing:-.01em;margin:0}
.mast .sub{color:var(--muted);font-size:12.5px;margin-top:8px}
.tally{display:flex;align-items:end;gap:28px}
.stat{text-align:right}
.stat b{display:block;font:600 40px/1 var(--serif);font-variant-numeric:lining-nums tabular-nums}
.stat span{font-size:11.5px;color:var(--muted);letter-spacing:.04em;text-transform:uppercase}

.bar{display:flex;align-items:center;gap:10px;padding:12px 40px;border-bottom:1px solid var(--rule);background:var(--sheet)}
.bar label{font-size:12.5px;color:var(--ink-2);display:flex;align-items:center;gap:8px}
.bar input[type=number]{width:64px;padding:5px 8px;border:1px solid var(--rule);border-radius:var(--r);background:#fff;font-family:var(--mono);font-size:13px}
.bar .hint{font-size:12px;color:var(--muted);font-family:var(--mono)}
.spacer{flex:1}
.btn{border:1px solid var(--ink);background:transparent;border-radius:var(--r);padding:7px 14px;font-weight:600;font-size:13px;cursor:pointer;transition:background .15s,color .15s,transform .16s}
.btn:active{transform:scale(.97)}
.btn:hover{background:var(--ink);color:var(--paper)}
.btn.primary{background:var(--ink);color:var(--paper)}
.btn.primary:hover{background:#000}
.btn.ghost{border-color:transparent;color:var(--accent)}
.btn.ghost:hover{background:var(--accent-wash);color:var(--accent)}
.icon{display:flex;align-items:center;gap:6px;height:32px;padding:0 10px;border:1px solid var(--rule);background:#fff;border-radius:var(--r);cursor:pointer;color:var(--ink-2);font:600 12px var(--mono);transition:border-color .15s,color .15s}
.icon:hover{border-color:var(--ink);color:var(--ink)}

.desk{display:grid;grid-template-columns:minmax(0,1fr) 460px;min-height:calc(100vh - 150px)}
.left{padding:24px 40px 40px;border-right:1px solid var(--rule)}
.right{padding:24px 32px 40px;background:var(--sheet);position:sticky;top:0;align-self:start;max-height:100vh;overflow:auto}

.fieldlabel{display:flex;justify-content:space-between;font-size:12px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--ink-2);margin-bottom:6px}
.fieldlabel em{font-style:normal;text-transform:none;letter-spacing:0;font-weight:400;color:var(--muted)}
kbd{font:11px var(--mono);border:1px solid var(--rule);border-bottom-width:2px;border-radius:3px;padding:0 4px;background:#fff}
.composer textarea{width:100%;min-height:96px;resize:vertical;padding:12px 14px;border:1px solid var(--ink);border-radius:var(--r);background:#fff;font:13px/1.55 var(--mono);outline:none}
.composer textarea:focus{box-shadow:0 0 0 3px rgba(22,23,26,.12)}
.receipt{font-size:12px;color:var(--muted);margin-top:6px;min-height:18px}
.receipt b{color:var(--ink-2);font-weight:600}
.dupe{display:none;margin-top:8px;padding:10px 12px;border:1px solid var(--accent);background:var(--accent-wash);border-radius:var(--r);font-size:13px;align-items:center;gap:10px}
.dupe.show{display:flex;animation:rise .18s ease-out}

.listhead{display:flex;align-items:baseline;justify-content:space-between;margin:28px 0 10px;border-bottom:1px solid var(--rule);padding-bottom:6px}
.listhead h2{font:600 18px/1.2 var(--serif);margin:0}
.listhead span{font-size:12px;color:var(--muted)}
.slips{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.slip{position:relative;text-align:left;border:1px solid var(--rule);background:var(--sheet);border-radius:var(--r);padding:10px 11px 11px;cursor:pointer;min-height:96px;display:flex;flex-direction:column;gap:6px;transition:border-color .15s,transform .15s,background .12s,color .12s}
.slip:hover{border-color:var(--ink);transform:translateY(-1px)}
.slip.new{animation:rise .2s ease-out both}
.slip .no{font:600 22px/1 var(--serif);font-variant-numeric:tabular-nums}
.slip .pv{font:11px/1.45 var(--mono);color:var(--ink-2);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;word-break:break-word}
.slip .meta{position:absolute;top:10px;right:10px;font-size:10.5px;color:var(--muted);font-family:var(--mono)}
.slip.on{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.slip.on .pv,.slip.on .meta{color:#B9BAB5}
.slip.dup .meta{color:var(--accent)}
.slip.dragging{opacity:.4}
.slip.drop{outline:2px solid var(--ink);outline-offset:2px}
.cut{grid-column:1/-1;display:flex;align-items:center;gap:10px;font-size:11px;color:var(--muted);letter-spacing:.06em;text-transform:uppercase;margin:4px 0}
.cut::before,.cut::after{content:"";flex:1;border-top:1px dashed var(--rule)}
.empty{color:var(--muted);font-size:13px;margin:16px 0}

.edhead{display:flex;align-items:baseline;justify-content:space-between;border-bottom:2px solid var(--ink);padding-bottom:10px;margin-bottom:14px}
.pos{font:600 30px/1 var(--serif);font-variant-numeric:tabular-nums}
.pos small{font-size:16px;color:var(--muted);font-weight:400}
.nav{display:flex;gap:6px}
.nav button{width:32px;height:32px;border:1px solid var(--rule);background:#fff;border-radius:var(--r);cursor:pointer}
.nav button:hover{border-color:var(--ink)}
.tabs{display:flex;gap:18px;font-size:13px;margin-bottom:10px}
.tabs button{border:0;background:none;padding:0 0 4px;cursor:pointer;color:var(--muted);border-bottom:2px solid transparent}
.tabs button.on{color:var(--ink);border-bottom-color:var(--ink);font-weight:600}
.editor textarea{width:100%;min-height:420px;resize:vertical;padding:12px 14px;border:1px solid var(--rule);border-radius:var(--r);background:#fff;font:13px/1.6 var(--mono);outline:none}
.editor textarea:focus{border-color:var(--ink)}
.editor textarea:disabled{background:var(--rule-2)}
.orig{min-height:120px;padding:12px 14px;border:1px dashed var(--rule);border-radius:var(--r);font:13px/1.6 var(--mono);white-space:pre-wrap;word-break:break-word;color:var(--ink-2);background:#fff}
.orig del{color:var(--accent);text-decoration-thickness:1px;background:var(--accent-wash)}
.edfoot{display:flex;justify-content:space-between;align-items:center;margin-top:8px;font-size:12px;color:var(--muted)}

.strip{width:420px;max-width:calc(100vw - 32px);margin:84px 40px auto auto;padding:0;border:1px solid var(--ink);border-radius:var(--r);background:var(--sheet);color:var(--ink)}
.strip[open]{animation:rise .16s ease-out}
.strip::backdrop{background:rgba(22,23,26,.18)}
.dlgbody{padding:18px 20px 20px}
.dlghead{display:flex;justify-content:space-between;align-items:center}
.dlghead h3{font:600 16px/1.2 var(--serif);margin:0}
.dlghead button{border:0;background:none;font-size:20px;cursor:pointer;color:var(--muted)}
.dlghead button:hover{color:var(--ink)}
.dlgbody p{margin:4px 0 12px;font-size:12.5px;color:var(--muted)}
.kw{display:flex;align-items:center;padding:7px 0;border-bottom:1px solid var(--rule-2);font:12.5px var(--mono)}
.kw .hits{font-family:var(--sans);font-size:11px;color:var(--muted);margin-left:auto;margin-right:12px}
.kw button{border:0;background:none;color:var(--muted);cursor:pointer;font-size:15px;line-height:1}
.kw button:hover{color:var(--accent)}
.addkw{display:flex;gap:8px;margin-top:10px}
.addkw input{flex:1;padding:7px 10px;border:1px solid var(--rule);border-radius:var(--r);background:#fff;font:12.5px var(--mono)}

.toast{position:fixed;left:40px;bottom:24px;max-width:calc(100vw - 80px);background:var(--ink);color:var(--paper);padding:10px 14px;border-radius:var(--r);font-size:13px;display:flex;gap:14px;align-items:center;transform:translateY(80px);opacity:0;pointer-events:none;transition:transform .2s,opacity .2s}
.toast.show{transform:none;opacity:1;pointer-events:auto}
.toast button{background:none;border:0;color:#FFB4A6;font-weight:600;cursor:pointer}

@keyframes rise{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
@media (max-width:900px){
  .desk{grid-template-columns:1fr}
  .left{border-right:0;padding:20px 16px}
  .right{position:static;max-height:none;padding:20px 16px}
  .mast,.bar{padding-left:16px;padding-right:16px}
  .bar{flex-wrap:wrap}
  .toast{left:16px;max-width:calc(100vw - 32px)}
}
</style>
</head>
<body>

<header class="mast">
  <div>
    <h1>Prompt Collector</h1>
    <div class="sub" id="saved">Autosaved locally</div>
  </div>
  <div class="tally">
    <div class="stat"><b id="total">0</b><span>prompts</span></div>
    <div class="stat"><b id="files">0</b><span>files to export</span></div>
  </div>
</header>

<div class="bar">
  <label>Prompts per file <input type="number" id="per" min="1" step="1"></label>
  <span class="hint" id="namehint"></span>
  <div class="spacer"></div>
  <button class="icon" id="kwOpen" aria-label="Strip keywords" title="Strip keywords"><svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M8.6 7.6 20 18M8.6 16.4 20 6"/></svg><span id="kwCount">0</span></button>
  <button class="btn ghost" id="clear">Clear list</button>
  <button class="btn" id="exportJson">Export JSON</button>
  <button class="btn primary" id="exportTxt">Export TXT</button>
</div>

<main class="desk">
  <section class="left">
    <div class="composer">
      <label class="fieldlabel" for="in"><span>Paste prompt</span><em><kbd>Enter</kbd> add · <kbd>Shift</kbd>+<kbd>Enter</kbd> new line</em></label>
      <textarea id="in" placeholder="Paste a prompt and press Enter"></textarea>
      <div class="receipt" id="receipt"></div>
      <div class="dupe" id="dupe" role="alert">Same as <b id="dupeNo"></b> after cleanup.<span class="spacer"></span>
        <button class="btn" id="skip">Skip</button><button class="btn primary" id="addAnyway">Add anyway</button></div>
    </div>
    <div class="listhead"><h2>Collected</h2><span>Drag to reorder · dashed line marks a file break</span></div>
    <div class="slips" id="slips"></div>
    <p class="empty" id="empty">Paste a prompt above and press Enter.</p>
  </section>

  <aside class="right">
    <div class="edhead">
      <div class="pos" id="pos"></div>
      <div class="nav"><button id="prev" aria-label="Previous prompt">&larr;</button><button id="next" aria-label="Next prompt">&rarr;</button></div>
    </div>
    <div class="tabs"><button class="on" data-t="clean">Cleaned</button><button data-t="orig">Original</button></div>
    <div class="editor">
      <textarea id="ed" aria-label="Edit prompt"></textarea>
      <div class="orig" id="orig" hidden></div>
    </div>
    <div class="edfoot"><span id="chars"></span><button class="btn ghost" id="del">Delete prompt</button></div>
  </aside>
</main>

<dialog class="strip" id="kwDlg" aria-label="Strip keywords">
  <div class="dlgbody">
    <div class="dlghead"><h3>Strip keywords</h3><button id="kwClose" aria-label="Close">&times;</button></div>
    <p>Any sentence containing one of these is removed on add. Case is ignored. Prompts you edited by hand are left alone.</p>
    <div id="kws"></div>
    <div class="addkw"><input id="kwIn" aria-label="New keyword" placeholder="e.g. reference image"><button class="btn" id="kwAdd">Add</button></div>
  </div>
</dialog>

<div class="toast" id="toast" role="status"><span id="toastMsg"></span><button id="toastAct" hidden></button></div>

<script src="core.js"></script>
<script>
"use strict";
const C = window.PromptCore;
const KEY = "promptCollector.v1";
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const newId = () => Math.random().toString(36).slice(2, 8) + Date.now().toString(36).slice(-4);

let state;
let view = "clean";      // editor tab: "clean" | "orig"
let pending = null;      // raw text waiting on the duplicate warning
let lastAdded = null;    // id of the slip to animate once
let saveTimer = null;
let toastTimer = null;

// ---- toast ----
function toast(msg, action, sticky) {
  $("toastMsg").textContent = msg;
  const b = $("toastAct");
  b.hidden = !action;
  if (action) { b.textContent = action.label; b.onclick = () => { hideToast(); action.run(); }; }
  $("toast").classList.add("show");
  clearTimeout(toastTimer);
  if (!sticky) toastTimer = setTimeout(hideToast, 5000);
}
function hideToast() { $("toast").classList.remove("show"); }
$("toast").addEventListener("click", e => { if (e.target !== $("toastAct")) hideToast(); });

// ---- persistence ----
function load() {
  let raw = null;
  try { raw = localStorage.getItem(KEY); } catch (e) { /* storage blocked: start fresh */ }
  const parsed = C.parseState(raw);
  state = parsed.state;
  if (parsed.corrupt) {
    try { localStorage.setItem(KEY + ".corrupt", raw); } catch (e) { /* nothing more we can do */ }
    toast("Saved data could not be read. A backup was kept in localStorage.", null, true);
  }
}
function saveNow() {
  clearTimeout(saveTimer);
  saveTimer = null;
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
    $("saved").textContent = "Autosaved locally · last change " + new Date().toTimeString().slice(0, 5);
  } catch (e) {
    toast("Autosave failed: storage is full. Export now.", null, true);
  }
}
function changed() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveNow, 300);
  render();
}
addEventListener("pagehide", () => { if (saveTimer) saveNow(); });

// ---- render ----
function markRemoved(it) {
  let html = "", rest = it.raw.replace(/\r\n?/g, "\n");
  for (const s of it.removed) {
    const k = rest.indexOf(s);
    if (k < 0) continue;
    html += esc(rest.slice(0, k)) + `<del>${esc(s)}</del>`;
    rest = rest.slice(k + s.length);
  }
  return html + esc(rest);
}

function renderKeywords() {
  $("kwCount").textContent = state.keywords.length;
  $("kws").innerHTML = state.keywords.map((k, i) => {
    const hits = state.items.filter(x => x.raw.toLowerCase().includes(k)).length;
    return `<div class="kw"><span>${esc(k)}</span><span class="hits">${hits} hit${hits === 1 ? "" : "s"}</span>` +
      `<button data-k="${i}" aria-label="Remove ${esc(k)}">&times;</button></div>`;
  }).join("") || `<p>No keywords. Nothing is stripped.</p>`;
}

function render() {
  const items = state.items, n = items.length, per = state.perFile;
  if (state.selected > n - 1) state.selected = Math.max(0, n - 1);
  const files = Math.ceil(n / per);
  const names = C.fileNames(new Date(), files, "txt");

  $("total").textContent = n;
  $("files").textContent = files;
  $("namehint").textContent = files > 1 ? `${names[0]} … ${names[files - 1]}` : (names[0] || "");
  if (document.activeElement !== $("per")) $("per").value = per;

  const firstSeen = new Map();
  const width = files > 99 ? 3 : 2;
  $("slips").innerHTML = items.map((it, i) => {
    const dupOf = firstSeen.get(it.text) || 0;
    if (!dupOf) firstSeen.set(it.text, i + 1);
    const mark = dupOf ? `= #${dupOf}` : it.edited ? "edited" : it.removed.length ? "cleaned" : "";
    const cut = i && i % per === 0 ? `<div class="cut">file ${String(i / per + 1).padStart(width, "0")}</div>` : "";
    const cls = "slip" + (i === state.selected ? " on" : "") + (dupOf ? " dup" : "") + (it.id === lastAdded ? " new" : "");
    return cut + `<button class="${cls}" data-i="${i}" draggable="true">` +
      `<span class="no">${i + 1}</span><span class="meta">${mark}</span><span class="pv">${esc(it.text)}</span></button>`;
  }).join("");
  lastAdded = null;
  $("empty").hidden = n > 0;

  const it = items[state.selected];
  const text = it ? it.text : "";
  $("pos").innerHTML = `${n ? state.selected + 1 : 0} <small>/ ${n}</small>`;
  $("ed").disabled = $("del").disabled = !it;
  $("prev").disabled = !it || state.selected === 0;
  $("next").disabled = !it || state.selected === n - 1;
  $("exportTxt").disabled = $("exportJson").disabled = $("clear").disabled = !n;
  if ($("ed").value !== text) $("ed").value = text;
  $("chars").textContent = it ? `${text.length} chars · ${text ? text.split("\n").length : 0} lines` : "";
  $("orig").innerHTML = it ? markRemoved(it) : "";
  $("ed").hidden = view !== "clean";
  $("orig").hidden = view !== "orig";
  document.querySelectorAll(".tabs button").forEach(b => b.classList.toggle("on", b.dataset.t === view));
  renderKeywords();
}

// ---- composer ----
function hideDupe() { pending = null; $("dupe").classList.remove("show"); }

function addPrompt(raw) {
  const { text, removed } = C.clean(raw, state.keywords);
  if (!text) { $("receipt").textContent = "Everything was stripped. Check strip keywords."; return; }
  const it = { id: newId(), raw, text, removed, edited: false, addedAt: C.isoLocal(new Date()) };
  state.items.push(it);
  state.selected = state.items.length - 1;
  lastAdded = it.id;
  $("in").value = "";
  hideDupe();
  const r = removed.length;
  $("receipt").innerHTML = `Last add: <b>${r ? `removed ${r} sentence${r > 1 ? "s" : ""}` : "nothing removed"}</b>`;
  changed();
  $("slips").querySelector(".on")?.scrollIntoView({ block: "nearest" });
}

$("in").addEventListener("keydown", e => {
  if (e.key !== "Enter" || e.shiftKey || e.isComposing) return;
  e.preventDefault();
  const raw = $("in").value;
  if (!raw.trim()) return;
  const { text } = C.clean(raw, state.keywords);
  const d = text ? C.findDuplicate(state.items, text) : -1;
  if (d >= 0) {
    pending = raw;
    $("dupeNo").textContent = "#" + (d + 1);
    $("dupe").classList.add("show");
    return;
  }
  addPrompt(raw);
});
$("in").addEventListener("input", hideDupe);
$("addAnyway").onclick = () => {
  if (pending === null) return;
  const raw = pending;
  hideDupe();
  addPrompt(raw);
  $("in").focus();
};
$("skip").onclick = () => { hideDupe(); $("in").value = ""; $("in").focus(); };

// ---- selection, editor, tabs ----
function select(i) {
  if (!state.items.length) return;
  state.selected = Math.max(0, Math.min(state.items.length - 1, i));
  changed();
  $("slips").querySelector(".on")?.scrollIntoView({ block: "nearest" });
}
$("slips").addEventListener("click", e => { const b = e.target.closest(".slip"); if (b) select(+b.dataset.i); });
$("prev").onclick = () => select(state.selected - 1);
$("next").onclick = () => select(state.selected + 1);
document.addEventListener("keydown", e => {
  if (e.target.closest("textarea, input, dialog") || e.altKey || e.ctrlKey || e.metaKey) return;
  if (e.key === "ArrowLeft") select(state.selected - 1);
  if (e.key === "ArrowRight") select(state.selected + 1);
});
$("ed").addEventListener("input", e => {
  const it = state.items[state.selected];
  it.text = e.target.value;
  it.edited = true;
  changed();
});
document.querySelector(".tabs").addEventListener("click", e => {
  const t = e.target.dataset.t;
  if (t) { view = t; render(); }
});

// ---- prompts per file ----
$("per").addEventListener("input", e => {
  const v = Number(e.target.value);
  if (Number.isInteger(v) && v >= 1) { state.perFile = v; changed(); }
});
$("per").addEventListener("change", e => { e.target.value = state.perFile; });

function boot() {
  load();
  render();
  $("in").focus();
}
boot();
</script>
</body>
</html>
```

- [ ] **Step 2: Check it in the browser**

Serve and open (see "How to check UI tasks" above). Verify each item and fix anything that fails before committing:

1. First open shows `0` prompts, `0` files, the empty-list hint, `0 / 0`, and the editor, Delete, Clear list and both export buttons disabled. The ✂ button shows `4`.
2. Paste `A man at dawn.\n\n\nUse face image of the uploaded photo with the exact body proportions, facial proportions, hairstyle and facial structure.\n\nShot on 35mm.` (with real blank lines) and press Enter: slip `1` appears with the `cleaned` marker, the receipt says `removed 1 sentence`, and the editor shows `A man at dawn.` and `Shot on 35mm.` on two lines.
3. Shift+Enter inserts a newline without adding. Enter on an empty or whitespace-only box does nothing.
4. Paste `Keep the facial structure.` and press Enter: nothing is added, the receipt says `Everything was stripped. Check strip keywords.`, and the text stays in the box.
5. Paste the step 2 prompt again: the red warning `Same as #1 after cleanup.` appears. `Skip` clears the box. Doing it again and choosing `Add anyway` adds slip `2` marked `= #1`.
6. Typing in the editor updates the slip preview live and the marker becomes `edited`. The Original tab shows the raw text with the removed sentence struck through in red.
7. ←/→ buttons and the arrow keys (focus outside text fields) move the selection and `N / Total`.
8. Set prompts per file to `1`: the files count becomes `2`, the hint shows `prompt_YYYYMMDD_01.txt … prompt_YYYYMMDD_02.txt`, and a dashed `file 02` divider appears. Clearing the field and leaving it restores the last valid value.
9. Reload the page: everything comes back, including the selection and the per-file value.
10. In devtools run `localStorage.setItem("promptCollector.v1", "{oops")` and reload: the sticky toast about unreadable data appears, the list is empty, and `localStorage.getItem("promptCollector.v1.corrupt")` returns `"{oops"`.

- [ ] **Step 3: Commit**

```bash
git add prompt/prompt_Collector/dist/index.html
git commit -m "Add Prompt Collector page with autosave, composer, list and editor

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Delete with undo, drag reorder, keyword dialog, clear list

**Files:**
- Modify: `prompt/prompt_Collector/dist/index.html` (insert a block immediately before the line `boot();` near the end of the script)

**Interfaces:**
- Consumes: from Task 3 `state`, `$`, `changed()`, `render()`, `renderKeywords()`, `toast(msg, {label, run})`. From core: `PromptCore.move`, `PromptCore.reclean`.
- Produces: nothing new for later tasks.

- [ ] **Step 1: Add the handlers**

In `prompt/prompt_Collector/dist/index.html`, insert this block immediately before the line `boot();`:

```js
// ---- delete with undo ----
$("del").onclick = () => {
  const i = state.selected, it = state.items[i];
  if (!it) return;
  state.items.splice(i, 1);
  changed();
  toast(`Deleted #${i + 1}`, { label: "Undo", run: () => { state.items.splice(i, 0, it); state.selected = i; changed(); } });
};

// ---- drag to reorder ----
let dragFrom = null;
$("slips").addEventListener("dragstart", e => {
  const b = e.target.closest(".slip");
  if (!b) return;
  dragFrom = +b.dataset.i;
  e.dataTransfer.effectAllowed = "move";
  e.dataTransfer.setData("text/plain", "");
  b.classList.add("dragging");
});
$("slips").addEventListener("dragover", e => {
  const b = e.target.closest(".slip");
  if (dragFrom === null || !b) return;
  e.preventDefault();
  document.querySelectorAll(".slip.drop").forEach(x => { if (x !== b) x.classList.remove("drop"); });
  b.classList.add("drop");
});
$("slips").addEventListener("drop", e => {
  const b = e.target.closest(".slip");
  if (dragFrom === null || !b) return;
  e.preventDefault();
  const selectedItem = state.items[state.selected];
  state.items = C.move(state.items, dragFrom, +b.dataset.i);
  state.selected = state.items.indexOf(selectedItem);
  dragFrom = null;
  changed();
});
$("slips").addEventListener("dragend", () => { dragFrom = null; render(); });

// ---- strip keywords dialog ----
function setKeywords(list) {
  state.keywords = list;
  state.items = C.reclean(state.items, list);
  changed();
}
$("kwOpen").onclick = () => { renderKeywords(); $("kwDlg").showModal(); $("kwIn").focus(); };
$("kwClose").onclick = () => $("kwDlg").close();
$("kwDlg").addEventListener("click", e => { if (e.target === $("kwDlg")) $("kwDlg").close(); }); // backdrop
$("kws").addEventListener("click", e => {
  const k = e.target.dataset.k;
  if (k !== undefined) setKeywords(state.keywords.filter((_, i) => i !== +k));
});
$("kwAdd").onclick = () => {
  const v = $("kwIn").value.trim().toLowerCase();
  $("kwIn").value = "";
  if (v && !state.keywords.includes(v)) setKeywords([...state.keywords, v]);
  $("kwIn").focus();
};
$("kwIn").addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); $("kwAdd").click(); } });

// ---- clear list ----
$("clear").onclick = () => {
  const n = state.items.length;
  if (!n || !confirm(`Clear all ${n} prompts? Export first if you need them.`)) return;
  state.items = [];
  state.selected = 0;
  changed();
};

```

- [ ] **Step 2: Check it in the browser**

Serve and open. Add 4 short prompts first (e.g. `one.`, `two.`, `three.`, `four.`), then verify:

1. Select `#2` and click Delete prompt: it disappears and a toast `Deleted #2` with `Undo` shows. Undo puts it back at position 2 and selects it. Without Undo, the toast hides after about 5 s.
2. Drag slip `4` onto slip `1`: the order becomes four, one, two, three, numbering updates, and the previously selected prompt stays selected. Reload keeps the new order.
3. The ✂ button opens the dialog with the 4 default keywords and hit counts. ×, Esc and a click on the dimmed backdrop all close it. A click inside the dialog's empty area does not close it.
4. Add the keyword `four` (press Enter in the field): the count on ✂ becomes 5 and the `four.` prompt now has empty text (empty preview). Remove `four`: the prompt text comes back.
5. Edit one prompt by hand so it contains `two`, add the keyword `two`: the hand-edited prompt keeps its text, the unedited `two.` prompt becomes empty. Remove the keyword again.
6. Adding an existing keyword or blank input changes nothing.
7. Clear list → Cancel keeps everything. Clear list → OK empties the list and keeps the keywords and the per-file value. Reload confirms both.

- [ ] **Step 3: Commit**

```bash
git add prompt/prompt_Collector/dist/index.html
git commit -m "Add delete/undo, drag reorder, keyword dialog and clear list

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Export TXT and JSON, README entry

**Files:**
- Modify: `prompt/prompt_Collector/dist/index.html` (insert before the line `boot();`)
- Modify: `README.md` (add the folder to the `prompt/` tree)

**Interfaces:**
- Consumes: `state`, `$`, `toast` from Task 3. `PromptCore.buildFiles(kind, items, { perFile, keywords })` from Task 2.
- Produces: nothing.

- [ ] **Step 1: Add export handlers**

In `prompt/prompt_Collector/dist/index.html`, insert this block immediately before the line `boot();`:

```js
// ---- export ----
// One <a download> per file, 150 ms apart; Chrome/Edge asks once to allow multiple downloads.
function download(files) {
  files.forEach((f, n) => setTimeout(() => {
    const type = f.name.endsWith(".json") ? "application/json" : "text/plain;charset=utf-8";
    const url = URL.createObjectURL(new Blob([f.content], { type }));
    const a = Object.assign(document.createElement("a"), { href: url, download: f.name });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }, n * 150));
}
function exportAs(kind) {
  const { files, skipped } = C.buildFiles(kind, state.items, { perFile: state.perFile, keywords: state.keywords });
  if (!files.length) { toast("Nothing to export: every prompt is empty."); return; }
  download(files);
  toast(`Exported ${files.length} ${kind.toUpperCase()} file${files.length > 1 ? "s" : ""}` +
    (skipped ? ` · skipped ${skipped} empty prompt${skipped > 1 ? "s" : ""}` : ""));
}
$("exportTxt").onclick = () => exportAs("txt");
$("exportJson").onclick = () => exportAs("json");

```

- [ ] **Step 2: Update README**

In `README.md`, replace

```
├── prompt/ — Xử lý và chuẩn hoá prompt.
│   ├── groupPrompt_v2.py — Gom nhóm prompt theo độ tương đồng và tóm tắt từ khóa.
```

with

```
├── prompt/ — Xử lý và chuẩn hoá prompt.
│   ├── prompt_Collector/ — Web UI gom prompt: double-click dist/index.html, lọc câu thừa, export TXT (Text_Splitter) / JSON.
│   ├── groupPrompt_v2.py — Gom nhóm prompt theo độ tương đồng và tóm tắt từ khóa.
```

- [ ] **Step 3: Check it in the browser**

Serve and open. Add 5 prompts, one of them with an internal blank line typed by hand in the editor, and one edited to be empty. Set prompts per file to `2`. Verify:

1. Export TXT downloads `prompt_YYYYMMDD_01.txt` and `_02.txt` (4 non-empty prompts over 2 files; allow multiple downloads if asked). The toast says `Exported 2 TXT files · skipped 1 empty prompt`.
2. Each TXT has prompts separated by exactly one blank line, no blank line inside a prompt, and ends with one newline. Check with:

```bash
python -c "import sys,pathlib; t=pathlib.Path(sys.argv[1]).read_text(encoding='utf-8-sig'); print([b.strip() for b in t.split('\n\n') if b.strip()])" "%USERPROFILE%/Downloads/prompt_YYYYMMDD_01.txt"
```

   (replace the date; this is the same split `Text_Splitter` does). It should print exactly the 2 prompts of that file.
3. Export JSON downloads `_01.json` and `_02.json`. Each has `app`, `version`, `exported_at`, `part`, `parts: 2`, `total: 4`, `strip_keywords`, and `prompts[]` with `index` running 1–4 across both files.
4. Set prompts per file to `50`: Export TXT downloads one `prompt_YYYYMMDD.txt` with no suffix.
5. Export does not change the list.

- [ ] **Step 4: Final checks on the real file**

1. Run `cd prompt/prompt_Collector && node test_core.mjs`. Expected: `core: all checks passed`.
2. Human check: double-click `prompt\prompt_Collector\dist\index.html` in Explorer. It opens in Chrome/Edge with no console errors. Add two prompts, close the tab, reopen the file: both prompts are still there.
3. Load one exported TXT into ComfyUI `Text_Splitter` (`paragraph_sep` `\n\n`, `negative_sep` `###`): `count` equals the number of prompts in that file.

- [ ] **Step 5: Commit**

```bash
git add prompt/prompt_Collector/dist/index.html README.md
git commit -m "Add TXT/JSON export to Prompt Collector and list it in README

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
