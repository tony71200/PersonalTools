# Prompt Collector — Design

Date: 2026-10-08
Location: `prompt/prompt_Collector/`
Mockup: [2026-10-08-prompt-collector-mockup.html](2026-10-08-prompt-collector-mockup.html) (sample data, no persistence)

## Goal

A local web UI opened by double-clicking `dist/index.html` (Chrome/Edge, `file://`). The user pastes image prompts one at a time; each is cleaned, added to a list, can be reviewed/edited, and the list is exported as TXT files for the ComfyUI `Text_Splitter` node (`D:\Comfy\ComfyUI\custom_nodes\Load_IO_Tony`) or as JSON. Work in progress survives closing the window.

## Constraints

- No build step, no Node needed to run. No external network requests (fonts are system fonts).
- UI text in English.
- Output must match `Text_Splitter`: it splits the file on the exact string `\n\n` and treats `###` as the positive/negative separator. Therefore no prompt may contain `\n\n` internally on export. `###` in a prompt is preserved untouched.
- Only positive prompts; no negative-prompt field.

## Files

```
prompt/prompt_Collector/
  dist/index.html   HTML + CSS + UI script (DOM, events, storage, downloads)
  dist/core.js      Pure logic, no DOM: clean, dedupe key, chunking, filenames, export payloads
  test_core.mjs     node test_core.mjs — assert-based checks of core.js
```

`core.js` is a classic script (`<script src="core.js">`) that defines a global `PromptCore` and also sets `module.exports` when `module` exists, so Node can load it. This keeps double-click working (`type="module"` is blocked on `file://`).

## Data model

```js
state = {
  version: 1,
  items: [{
    id: "k3f9a2",            // random, stable across reorder
    raw: "…",                // text exactly as pasted
    text: "…",               // cleaned or hand-edited text (what is exported)
    removed: ["…"],          // sentences stripped from raw by keywords
    edited: false,           // true once the user edits `text` by hand
    addedAt: "2026-10-08T13:41:12+07:00"
  }],
  keywords: ["uploaded photo", "facial structure", "exact body proportions", "reference image"],
  perFile: 50,               // natural number >= 1
  selected: 0                // index of the item shown in the editor
}
```

## Cleaning pipeline (`PromptCore.clean(raw, keywords) -> {text, removed}`)

1. Normalize line endings: `\r\n` and `\r` become `\n`.
2. For each line, split into sentences after `.`, `!` or `?` followed by whitespace (`/(?<=[.!?])\s+/`).
3. Drop every sentence whose lowercase form contains any keyword (keywords stored lowercase, compared with `includes`). Dropped sentences go to `removed`.
4. Rejoin sentences with a single space, lines with `\n`.
5. Collapse blank runs: `/\n\s*\n+/g` becomes `\n`. Trim trailing spaces per line, then trim the whole text.

Rules around it:

- **Empty result:** the prompt is not added. Composer shows "Everything was stripped. Check strip keywords." and keeps the pasted text in the box.
- **Keyword list changes** (add/remove) re-run `clean` on every item with `edited === false`. Items with `edited === true` keep their text and show an `edited` marker on their slip.
- **Export-time guard:** `text` is passed through step 5 again when exporting, so a blank line typed during hand-editing can never split a prompt in `Text_Splitter`.

## Duplicate check

Dedupe key = cleaned `text` after step 5, compared exactly. When a paste matches an existing item, the composer shows an inline warning "Same as #N after cleanup." with **Skip** (clears the box) and **Add anyway**. Slips whose text duplicates an earlier one show `= #N`.

## UI (see mockup)

- **Masthead:** title, "Autosaved locally · last change HH:MM", big counts: total prompts, files to export.
- **Toolbar:** `Prompts per file` number input (min 1; invalid or empty falls back to the previous value), filename preview (`prompt_20261008.txt` or `prompt_20261008_01.txt … _NN.txt`), ✂ icon button with keyword count, `Clear list`, `Export JSON`, `Export TXT` (primary).
- **Composer:** labelled textarea. `Enter` adds, `Shift+Enter` inserts a newline. Empty or whitespace-only input does nothing. After adding, a receipt line says how many sentences were removed.
- **Slip list:** grid of numbered slips (number, 3-line preview, marker: `cleaned` / `edited` / `= #N`). Click selects. A dashed divider labelled `file 02` etc. marks each file break according to `perFile`. Reorder by native HTML5 drag and drop; numbering and breaks update after drop.
- **Editor (right column):** `N / Total` position, ←/→ buttons, tabs `Cleaned` (editable textarea; editing sets `edited = true`) and `Original` (raw with removed sentences struck through in accent red). Character and line count. `Delete prompt` removes the item and shows a toast with `Undo` for 5 s. Arrow keys ←/→ also navigate when focus is not in a text field.
- **Strip keywords dialog:** native `<dialog>` opened by the ✂ button; closes with ×, Esc, or a backdrop click. Lists keywords with hit counts (items whose `raw` contains it) and a remove button; input + `Add` (Enter works) adds a lowercased, trimmed keyword, ignoring duplicates and empties.
- **Clear list:** `confirm("Clear all N prompts? Export first if you need them.")`. Keywords and `perFile` are kept.
- **Empty state:** slip area shows "Paste a prompt above and press Enter."; editor shows `0 / 0` and is disabled; export buttons are disabled.

Visual direction: editorial desk. Cool paper `#F3F3EF`, ink `#16171A`, one accent `#C8361D` used only for destructive actions, duplicates and struck text. Serif (Sitka/Cambria) for title and numerals, Segoe UI for interface, Cascadia Mono/Consolas for prompt text. Consistent 3px radius, hairline rules, no drop shadows, no nested cards. Motion: 150–200 ms rise on new slips and dialog, scale on button press, all disabled under `prefers-reduced-motion`.

## Persistence

- Key `promptCollector.v1` in `localStorage`.
- Save the whole `state` 300 ms after any change, and immediately on `pagehide`.
- On load: missing means defaults. If JSON parsing fails or `version` is unknown, copy the raw string to `promptCollector.v1.corrupt`, start with defaults, and show a toast "Saved data could not be read. A backup was kept in localStorage." Never silently overwrite unreadable data without that backup.
- If `setItem` throws (quota), show a persistent toast "Autosave failed: storage is full. Export now." and keep working in memory.
- If another tab saves, this tab adopts the newly saved state (storage event) so a stale tab never overwrites newer data.

## Export

Shared:

- Items with empty `text` are skipped; the toast reports how many were skipped.
- Items are chunked in list order into groups of `perFile`.
- Date stamp `YYYYMMDD` from local time at export. One chunk: `prompt_YYYYMMDD.ext`. Several: `prompt_YYYYMMDD_01.ext`, `_02`, … (two digits, three if more than 99 files).
- Each file is downloaded via `Blob` + `<a download>`, 150 ms apart. Files go to the browser's download folder. Chrome/Edge asks once to allow multiple downloads.
- Nothing is removed from the list after export.

TXT: the prompts of the chunk joined with `\n\n`, followed by a single trailing `\n`, UTF-8 without BOM.

JSON, one file per chunk, UTF-8, 2-space indent:

```json
{
  "app": "prompt-collector",
  "version": 1,
  "exported_at": "2026-10-08T14:02:00+07:00",
  "part": 1,
  "parts": 3,
  "total": 120,
  "strip_keywords": ["uploaded photo", "facial structure"],
  "prompts": [
    {
      "index": 1,
      "text": "A weathered fisherman...\nShot on 35mm...",
      "original": "raw text as pasted",
      "removed": ["Use face image of the uploaded photo ..."],
      "edited": false,
      "added_at": "2026-10-08T13:41:12+07:00"
    }
  ]
}
```

`index` is the 1-based position among all exported (non-empty) prompts across every part, not the position within the chunk. `total` counts exported prompts.

## Out of scope

Import JSON, negative prompts, IndexedDB, ZIP export, choosing a save folder, dark theme, Firefox support.

## Testing

`node test_core.mjs` (no framework, `node:assert`), covering:

- `clean`: CRLF input; `\n\n\n` and whitespace-only lines collapse to one `\n`; keyword match is case-insensitive and removes the whole sentence only; several sentences on one line where only one is removed; every sentence removed gives empty text; `###` preserved.
- Chunking and filenames: 0, 1, exactly `perFile`, `perFile + 1`, and 120 items at 50 per file give 3 files `_01` to `_03`.
- TXT payload: blocks split back by `\n\n` equal the item count and their texts, even when an item text contains a hand-typed blank line.
- JSON payload: fields, `part`/`parts`/`total`, global `index`.

Manual check in Chrome by double-clicking `dist/index.html`: add, edit, reorder, delete with undo, reload keeps everything, close and reopen keeps everything, multi-file TXT export opens correctly in `Text_Splitter`, keyword dialog changes re-clean only non-edited items.
