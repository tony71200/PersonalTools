# Prompt Collector v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add trigger-word presets applied at export, show the list newest-first without scroll jumps, and restyle the page with switchable Sunny/Sky themes with rounded, deeper controls.

**Architecture:** Same two runtime files as v1. Pure trigger logic, state defaults and export changes go in `dist/core.js` and are tested by `test_core.mjs`. `dist/index.html` gets a new `<style>` and markup block (Task 3), then focused script edits for triggers (Task 4) and list order (Task 5). Triggers are never written into a prompt's `text`; they are applied when building export files and previews.

**Tech Stack:** Plain HTML/CSS/ES2020, classic scripts, Chrome/Edge on `file://`. Node 22 only for `node test_core.mjs`.

**Spec:** `docs/superpowers/specs/2026-10-08-prompt-collector-v2-design.md` (builds on `docs/superpowers/specs/2026-10-08-prompt-collector-design.md`; mockup: `docs/superpowers/specs/2026-10-08-prompt-collector-v2-mockup.html`)

## Global Constraints

- Still double-click `prompt/prompt_Collector/dist/index.html` in Chrome/Edge (`file://`): no build, no npm, no network requests, system fonts only, classic `<script src>` only.
- UI text in English.
- Text_Splitter contract unchanged: TXT blocks joined by exactly `\n\n`, one trailing `\n`, no `\n\n` inside any exported prompt, `###` untouched.
- `state.version` stays `1`; localStorage key `promptCollector.v1` unchanged. New fields `triggers`, `activeTrigger`, `theme` come from defaults when missing.
- The trigger is never written into `item.text`, `item.raw` or `item.removed`.
- Default trigger preset: `{ id: "ivan", token: "Ivan_Ryo", description: "A 25yo Asian young man.", already: ["asian young man", "young asian man", "asian man"] }`; default `activeTrigger` is `""` (None); default `theme` is `"sunny"`.
- Sunny tokens: background `#FFF6E9`, card `#FFFFFF`, ink `#2A2140`, muted `#8C8299`, line `#F1DFC6`, primary `#FF6A3D` → `#FF9A3D`, accent `#12B3A3`, danger `#E5384F`.
- Sky tokens: background `#EEF6FF`, card `#FFFFFF`, ink `#13233F`, muted `#7486A3`, line `#D5E4F7`, primary `#2E6BFF` → `#22B8FF`, accent `#FFB020`, danger `#E5384F`.
- Radii: 16px panels, 12px controls and slips, 9px small inputs, fully round pills/toast/theme switch, 20px dialogs. Three tinted shadow levels plus an inset shadow on text fields.
- Danger red only for destructive buttons, the duplicate warning, and struck text. `prefers-reduced-motion` disables animation. Single column below 900px.
- Out of scope: Berry palette, dark theme, per-prompt trigger override, multiple active triggers, triggers in the body, JSON import.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Branch `ver004`.

## File Structure

```
prompt/prompt_Collector/
  dist/core.js      + DEFAULT_TRIGGERS, triggerPrefix, applyTrigger, parseAlready, findTrigger; state v2 fields; buildFiles trigger (Tasks 1-2)
  test_core.mjs     + trigger, state and export tests (Tasks 1-2)
  dist/index.html   new style + markup + theme (Task 3), trigger UI (Task 4), newest-first list (Task 5)
```

Commands run from the repo root `D:\001_PersonalProject\PersonalTools` unless stated. Run tests with `cd prompt/prompt_Collector && node test_core.mjs`.

**How to check UI tasks (3-5):** an agent serves the folder in the background, `python -m http.server 8765 -d prompt/prompt_Collector/dist`, and drives `http://localhost:8765/` in the built-in browser with `javascript_tool`. Add prompts by setting `#in`'s value and dispatching `new KeyboardEvent("keydown", {key: "Enter", bubbles: true})` on it. Start from `localStorage.clear()` and a reload done in its own call (a reloading script is cut off). Finish with a clean reload and `read_console_messages` (errors only). Stop the server afterwards. A human repeats the key checks by double-clicking the file.

---

### Task 1: Core trigger logic and v2 state fields

**Files:**
- Modify: `prompt/prompt_Collector/dist/core.js`
- Test: `prompt/prompt_Collector/test_core.mjs`

**Interfaces:**
- Consumes: existing `defaultState`, `parseState`.
- Produces (`PromptCore.*`):
  - `DEFAULT_TRIGGERS: Trigger[]` where `Trigger = { id: string, token: string, description: string, already: string[] }`
  - `triggerPrefix(text: string, trigger: Trigger|null) -> string` (`""`, `"Token."` or `"Token. Description."`)
  - `applyTrigger(text: string, trigger: Trigger|null) -> string`
  - `parseAlready(str: string) -> string[]` (comma split, trimmed, lowercased, empties dropped)
  - `findTrigger(triggers: Trigger[], id: string) -> Trigger|null`
  - `defaultState()` / `parseState()` now also return `triggers`, `activeTrigger`, `theme`.

- [ ] **Step 1: Update the two existing parseState assertions that compare whole state objects**

In `prompt/prompt_Collector/test_core.mjs`, replace

```js
assert.deepEqual(C.parseState(null).state, { version: 1, items: [], keywords: C.DEFAULT_KEYWORDS, perFile: 50, selected: 0 });
```

with

```js
assert.deepEqual(C.parseState(null).state, {
  version: 1, items: [], keywords: C.DEFAULT_KEYWORDS, perFile: 50, selected: 0,
  triggers: C.DEFAULT_TRIGGERS, activeTrigger: "", theme: "sunny",
});
```

and replace

```js
  assert.deepEqual(C.parseState(JSON.stringify(s)), { state: s, corrupt: false });
```

with

```js
  assert.deepEqual(C.parseState(JSON.stringify(s)), {
    state: { ...s, triggers: C.DEFAULT_TRIGGERS, activeTrigger: "", theme: "sunny" }, corrupt: false,
  });
```

- [ ] **Step 2: Add the trigger tests**

Insert this block immediately before the line `// --- chunk / move ---`:

```js
// --- triggers ---
assert.deepEqual(C.DEFAULT_TRIGGERS, [{ id: "ivan", token: "Ivan_Ryo", description: "A 25yo Asian young man.", already: ["asian young man", "young asian man", "asian man"] }]);
assert.notEqual(C.defaultState().triggers[0], C.DEFAULT_TRIGGERS[0]); // defaults are copied, not shared
const IVAN = { id: "ivan", token: "Ivan_Ryo", description: "A 25yo Asian young man.", already: ["asian young man", "young asian man"] };
assert.equal(C.triggerPrefix("anything", null), "");
assert.equal(C.triggerPrefix("anything", { ...IVAN, token: "  " }), "");
assert.equal(C.triggerPrefix("IVAN_RYO walks in rain.", IVAN), "");                       // token already there
assert.equal(C.triggerPrefix("Night market, an Asian Young Man in denim.", IVAN), "Ivan_Ryo."); // already described
assert.equal(C.triggerPrefix("Close-up portrait, rim light.", IVAN), "Ivan_Ryo. A 25yo Asian young man.");
assert.equal(C.triggerPrefix("Portrait.", { ...IVAN, description: "A 25yo Asian young man" }), "Ivan_Ryo. A 25yo Asian young man.");
assert.equal(C.triggerPrefix("Portrait.", { ...IVAN, token: "Ivan_Ryo." }), "Ivan_Ryo. A 25yo Asian young man.");
assert.equal(C.triggerPrefix("Portrait.", { ...IVAN, description: "  " }), "Ivan_Ryo.");
assert.equal(C.triggerPrefix("Portrait of an ASIAN MAN.", { ...IVAN, already: ["Asian Man"] }), "Ivan_Ryo.");
assert.equal(C.applyTrigger("Portrait.", IVAN), "Ivan_Ryo. A 25yo Asian young man. Portrait.");
assert.equal(C.applyTrigger("Portrait.", null), "Portrait.");
assert.deepEqual(C.parseAlready(" Asian Man, ,young ASIAN man ,"), ["asian man", "young asian man"]);
assert.equal(C.findTrigger([IVAN], "ivan"), IVAN);
assert.equal(C.findTrigger([IVAN], "nope"), null);
assert.equal(C.findTrigger([IVAN], ""), null);
// parseState fills and validates the v2 fields
{
  const v1 = { version: 1, items: [], keywords: ["k"], perFile: 7, selected: 0 };
  const s = C.parseState(JSON.stringify(v1)).state;
  assert.deepEqual(s.triggers, C.DEFAULT_TRIGGERS);
  assert.equal(s.activeTrigger, "");
  assert.equal(s.theme, "sunny");
  const bad = C.parseState(JSON.stringify({ ...v1, triggers: "x", activeTrigger: "ghost", theme: "neon" })).state;
  assert.deepEqual(bad.triggers, C.DEFAULT_TRIGGERS);
  assert.equal(bad.activeTrigger, "");
  assert.equal(bad.theme, "sunny");
  const ok = C.parseState(JSON.stringify({ ...v1, triggers: [IVAN], activeTrigger: "ivan", theme: "sky" })).state;
  assert.equal(ok.activeTrigger, "ivan");
  assert.equal(ok.theme, "sky");
}

```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd prompt/prompt_Collector && node test_core.mjs`
Expected: FAIL with an `AssertionError` on the updated `parseState(null).state` deepEqual (the actual object has no `triggers`).

- [ ] **Step 4: Implement**

In `prompt/prompt_Collector/dist/core.js`:

(a) Replace

```js
  const SENTENCE_SPLIT = /(?<=[.!?])\s+/;
```

with

```js
  const SENTENCE_SPLIT = /(?<=[.!?])\s+/;
  const DEFAULT_TRIGGERS = [{
    id: "ivan", token: "Ivan_Ryo", description: "A 25yo Asian young man.",
    already: ["asian young man", "young asian man", "asian man"],
  }];
  const THEMES = ["sunny", "sky"];
```

(b) Replace

```js
  function defaultState() {
    return { version: 1, items: [], keywords: DEFAULT_KEYWORDS.slice(), perFile: DEFAULT_PER_FILE, selected: 0 };
  }
```

with

```js
  // Trigger presets are applied at export time only; prompts never store them.
  const cleanToken = token => String(token || "").trim().replace(/\.+$/, "");

  function triggerPrefix(text, trigger) {
    const token = trigger ? cleanToken(trigger.token) : "";
    if (!token) return "";
    const lower = String(text).toLowerCase();
    if (lower.includes(token.toLowerCase())) return "";
    const head = token + ".";
    let desc = String(trigger.description || "").trim();
    if (!desc || (trigger.already || []).some(p => p && lower.includes(String(p).toLowerCase()))) return head;
    if (!/[.!?]$/.test(desc)) desc += ".";
    return head + " " + desc;
  }

  function applyTrigger(text, trigger) {
    const prefix = triggerPrefix(text, trigger);
    return prefix ? prefix + " " + text : text;
  }

  function parseAlready(str) {
    return String(str).split(",").map(p => p.trim().toLowerCase()).filter(Boolean);
  }

  function findTrigger(triggers, id) {
    return (id && triggers.find(t => t.id === id)) || null;
  }

  function defaultState() {
    return {
      version: 1, items: [], keywords: DEFAULT_KEYWORDS.slice(), perFile: DEFAULT_PER_FILE, selected: 0,
      triggers: DEFAULT_TRIGGERS.map(t => ({ ...t, already: t.already.slice() })), activeTrigger: "", theme: "sunny",
    };
  }
```

(c) Replace

```js
    if (!Number.isInteger(state.perFile) || state.perFile < 1) state.perFile = DEFAULT_PER_FILE;
    return { state, corrupt: false };
```

with

```js
    if (!Number.isInteger(state.perFile) || state.perFile < 1) state.perFile = DEFAULT_PER_FILE;
    if (!Array.isArray(state.triggers)) state.triggers = defaultState().triggers;
    if (!findTrigger(state.triggers, state.activeTrigger)) state.activeTrigger = "";
    if (!THEMES.includes(state.theme)) state.theme = "sunny";
    return { state, corrupt: false };
```

(d) Replace

```js
    DEFAULT_KEYWORDS, DEFAULT_PER_FILE, collapseBlank, clean, findDuplicate, reclean, defaultState, parseState,
```

with

```js
    DEFAULT_KEYWORDS, DEFAULT_PER_FILE, DEFAULT_TRIGGERS, collapseBlank, clean, findDuplicate, reclean,
    triggerPrefix, applyTrigger, parseAlready, findTrigger, defaultState, parseState,
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd prompt/prompt_Collector && node test_core.mjs`
Expected: `core: all checks passed`

- [ ] **Step 6: Commit**

```bash
git add prompt/prompt_Collector/dist/core.js prompt/prompt_Collector/test_core.mjs
git commit -m "Add trigger presets and v2 state fields to Prompt Collector core

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Export with the active trigger

**Files:**
- Modify: `prompt/prompt_Collector/dist/core.js` (`buildFiles`)
- Test: `prompt/prompt_Collector/test_core.mjs`

**Interfaces:**
- Consumes: `applyTrigger`, `collapseBlank` (Task 1 / v1).
- Produces: `buildFiles(kind, items, { perFile, keywords, trigger = null, now })`. TXT blocks become `applyTrigger(body, trigger)`. JSON gains a file-level `trigger` (`{ token, description, already }` or `null`), and each prompt gets `body` (the text without the trigger) next to `text` (the final text).

- [ ] **Step 1: Write the failing tests**

In `prompt/prompt_Collector/test_core.mjs`, replace

```js
  assert.deepEqual(p2.prompts, [{ index: 3, text: "c", original: "raw 2", removed: [], edited: false, added_at: "t" }]);
```

with

```js
  assert.equal(p2.trigger, null);
  assert.deepEqual(p2.prompts, [{ index: 3, text: "c", body: "c", original: "raw 2", removed: [], edited: false, added_at: "t" }]);
```

Then insert this block immediately before the line `console.log("core: all checks passed");`:

```js
// --- buildFiles with a trigger ---
{
  const IV = { id: "ivan", token: "Ivan_Ryo", description: "A 25yo Asian young man.", already: ["asian young man"] };
  const items = [mk("Close-up portrait.", 0), mk("   ", 1), mk("An Asian young man\n\n\nin rain.", 2)];
  const txt = C.buildFiles("txt", items, { perFile: 50, keywords: [], trigger: IV, now: day });
  assert.equal(txt.skipped, 1); // an empty body is never exported as a lone trigger
  assert.equal(txt.files[0].content, "Ivan_Ryo. A 25yo Asian young man. Close-up portrait.\n\nIvan_Ryo. An Asian young man\nin rain.\n");
  assert.equal(txt.files[0].content.split("\n\n").filter(b => b.trim()).length, 2); // Text_Splitter view
  const json = JSON.parse(C.buildFiles("json", items, { perFile: 50, keywords: [], trigger: IV, now: day }).files[0].content);
  assert.deepEqual(json.trigger, { token: "Ivan_Ryo", description: "A 25yo Asian young man.", already: ["asian young man"] });
  assert.equal(json.prompts[0].text, "Ivan_Ryo. A 25yo Asian young man. Close-up portrait.");
  assert.equal(json.prompts[0].body, "Close-up portrait.");
  assert.equal(json.prompts[1].index, 2);
  assert.equal(json.prompts[1].body, "An Asian young man\nin rain.");
}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd prompt/prompt_Collector && node test_core.mjs`
Expected: FAIL with an `AssertionError`: `p2.trigger` is `undefined`, expected `null`.

- [ ] **Step 3: Implement**

In `prompt/prompt_Collector/dist/core.js`, replace

```js
  // kind: "txt" | "json". Text is collapsed again (hand edits may contain blank lines); empty prompts are skipped.
  function buildFiles(kind, items, { perFile, keywords, now = new Date() }) {
    const prompts = [];
    for (const it of items) {
      const text = collapseBlank(it.text);
      if (text) prompts.push({ ...it, text });
    }
```

with

```js
  // kind: "txt" | "json". Text is collapsed again (hand edits may contain blank lines); empty prompts are skipped.
  // The active trigger is prepended here, never stored in the item.
  function buildFiles(kind, items, { perFile, keywords, trigger = null, now = new Date() }) {
    const prompts = [];
    for (const it of items) {
      const body = collapseBlank(it.text);
      if (body) prompts.push({ ...it, body, text: applyTrigger(body, trigger) });
    }
```

then replace

```js
            strip_keywords: keywords,
            prompts: group.map((p, j) => ({
              index: part * perFile + j + 1,
              text: p.text,
```

with

```js
            strip_keywords: keywords,
            trigger: trigger ? { token: trigger.token, description: trigger.description, already: trigger.already } : null,
            prompts: group.map((p, j) => ({
              index: part * perFile + j + 1,
              text: p.text,
              body: p.body,
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd prompt/prompt_Collector && node test_core.mjs`
Expected: `core: all checks passed`

- [ ] **Step 5: Commit**

```bash
git add prompt/prompt_Collector/dist/core.js prompt/prompt_Collector/test_core.mjs
git commit -m "Apply the active trigger when building export files

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: New visual design and Sunny/Sky theme switch

**Files:**
- Modify: `prompt/prompt_Collector/dist/index.html`

**Interfaces:**
- Consumes: `state.theme` from Task 1's `parseState`.
- Produces for Tasks 4-5:
  - Markup ids, hidden until Task 4: `#trigCtl` (wrapper, `hidden`), `#trig` (select), `#trigOpen`, `#tabFinal` (third tab, `data-t="final"`, `hidden`), `#trigline` (`hidden`).
  - Dialog markup: `#trigDlg`, `#trigClose`, `#trigList`, `#trigAdd`.
  - CSS classes: `.pill`, `.pill.trig`, `.preset`, `.preset .row`.
  - Script: `applyTheme()`, called at the start of `render()`.
  - Every existing id and class the script uses is kept.

- [ ] **Step 1: Replace the head and markup**

In `prompt/prompt_Collector/dist/index.html`, replace everything from the first line `<!doctype html>` through the line `<script src="core.js"></script>` (inclusive) with:

```html
<!doctype html>
<html lang="en" data-theme="sunny">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prompt Collector</title>
<script>/* apply the saved theme before first paint */ try { if (JSON.parse(localStorage.getItem("promptCollector.v1")).theme === "sky") document.documentElement.dataset.theme = "sky"; } catch (e) {}</script>
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
  --ring:0 0 0 4px color-mix(in srgb,var(--primary) 20%,transparent);
}
*{box-sizing:border-box}
[hidden]{display:none!important}
html,body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 var(--sans)}
button,input,textarea,select{font:inherit;color:inherit}
button:disabled{opacity:.45;cursor:default;pointer-events:none}

.mast{display:flex;align-items:center;gap:16px;padding:22px 32px}
.logo{width:42px;height:42px;border-radius:13px;display:grid;place-items:center;color:var(--on-primary);font:700 20px var(--serif);background:linear-gradient(135deg,var(--primary),var(--primary-2));box-shadow:var(--sh-2)}
.mast h1{font:700 28px/1 var(--serif);margin:0;letter-spacing:-.01em}
.mast .sub{color:var(--muted);font-size:12.5px;margin-top:4px}
.spacer{flex:1}
.themes{display:inline-flex;gap:4px;padding:4px;border-radius:999px;background:var(--card);box-shadow:var(--sh-1)}
.themes button{border:0;border-radius:999px;padding:6px 14px;font-size:12px;font-weight:650;cursor:pointer;background:transparent;color:var(--ink-2);transition:background .15s,color .15s}
.themes button[aria-pressed=true]{background:linear-gradient(135deg,var(--primary),var(--primary-2));color:var(--on-primary);box-shadow:var(--sh-1)}
.stat{background:var(--card);border-radius:var(--r);padding:10px 16px;box-shadow:var(--sh-1);text-align:right;min-width:104px}
.stat b{display:block;font:700 26px/1 var(--serif);font-variant-numeric:tabular-nums}
.stat span{font-size:11px;color:var(--muted);letter-spacing:.04em;text-transform:uppercase}
.stat.hot b{color:var(--primary)}

.bar{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:0 32px;padding:10px 12px;background:var(--card);border-radius:var(--r-lg);box-shadow:var(--sh-2)}
.trigctl{display:flex;align-items:center;gap:6px}
.field{display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--ink-2);padding:0 6px}
.field input,.field select{height:36px;padding:0 10px;border:1px solid var(--line);border-radius:var(--r-sm);background:var(--bg);box-shadow:var(--inset);outline:none;transition:border-color .15s,box-shadow .15s}
.field input{width:70px;font-family:var(--mono)}
.field select{min-width:160px;font-weight:600;cursor:pointer}
.field input:focus,.field select:focus{border-color:var(--primary);box-shadow:var(--inset),var(--ring)}
.hint{font:12px var(--mono);color:var(--muted)}
.sep{width:1px;align-self:stretch;background:var(--line);margin:4px 2px}

.btn{height:38px;border:0;border-radius:var(--r);padding:0 16px;font-weight:650;font-size:13px;cursor:pointer;display:inline-flex;align-items:center;gap:7px;background:var(--card);color:var(--ink);box-shadow:var(--sh-1),inset 0 0 0 1px var(--line);transition:transform .14s,box-shadow .14s,background .14s}
.btn:hover{transform:translateY(-1px);box-shadow:var(--sh-2),inset 0 0 0 1px var(--line)}
.btn:active{transform:translateY(1px) scale(.98);box-shadow:var(--sh-1)}
.btn:focus-visible{outline:none;box-shadow:var(--sh-1),var(--ring)}
.btn.primary{color:var(--on-primary);background:linear-gradient(135deg,var(--primary),var(--primary-2));box-shadow:var(--sh-2),inset 0 1px 0 rgb(255 255 255/.35)}
.btn.primary:hover{box-shadow:var(--sh-3),inset 0 1px 0 rgb(255 255 255/.35)}
.btn.danger{color:var(--danger);background:transparent;box-shadow:none}
.btn.danger:hover{background:var(--danger-wash)}
.btn.icon{width:38px;padding:0;justify-content:center}
.btn.icon.count{width:auto;padding:0 12px;font:650 12px var(--mono)}

.desk{display:grid;grid-template-columns:minmax(0,1fr) 440px;gap:20px;padding:20px 32px 40px}
.panel{background:var(--card);border-radius:var(--r-lg);box-shadow:var(--sh-2);padding:18px}
.right{position:sticky;top:16px;align-self:start;max-height:calc(100vh - 32px);overflow:auto}

.label{display:flex;justify-content:space-between;align-items:baseline;font-size:12px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--ink-2);margin-bottom:8px}
.label em{font-style:normal;text-transform:none;letter-spacing:0;font-weight:400;color:var(--muted)}
kbd{font:11px var(--mono);border-radius:6px;padding:1px 6px;background:var(--bg);border:1px solid var(--line);box-shadow:inset 0 -2px 0 var(--line)}
textarea{width:100%;resize:vertical;padding:14px 16px;border:1px solid var(--line);border-radius:var(--r);background:var(--bg);box-shadow:var(--inset);font:13px/1.6 var(--mono);outline:none;transition:border-color .15s,box-shadow .15s,background .15s}
textarea:focus{background:var(--card);border-color:var(--primary);box-shadow:var(--inset),var(--ring)}
textarea:disabled{opacity:.6}
textarea[readonly]{background:var(--bg);color:var(--ink-2)}
#in{min-height:92px}
.receipt{font-size:12px;color:var(--muted);margin-top:8px;min-height:22px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.receipt b{color:var(--ink-2);font-weight:600}
.pill{display:inline-flex;align-items:center;font-size:11.5px;font-weight:650;padding:3px 10px;border-radius:999px;background:var(--accent-wash);color:color-mix(in srgb,var(--accent) 65%,var(--ink))}
.pill.trig{background:color-mix(in srgb,var(--primary) 14%,var(--card));color:color-mix(in srgb,var(--primary) 75%,var(--ink))}
.dupe{display:none;margin-top:10px;padding:10px 12px;border-radius:var(--r);background:var(--danger-wash);color:var(--danger);font-size:13px;align-items:center;gap:10px}
.dupe.show{display:flex;animation:pop .22s cubic-bezier(.2,.9,.3,1.3)}

.listhead{display:flex;align-items:baseline;justify-content:space-between;margin:22px 2px 12px}
.listhead h2{font:700 18px/1.2 var(--serif);margin:0}
.listhead span{font-size:12px;color:var(--muted)}
.slips{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px}
.slip{position:relative;text-align:left;border:0;background:var(--card);border-radius:var(--r);padding:12px 13px;cursor:pointer;min-height:104px;display:flex;flex-direction:column;gap:6px;box-shadow:var(--sh-1),inset 0 0 0 1px var(--line);transition:transform .16s,box-shadow .16s}
.slip:hover{transform:translateY(-2px);box-shadow:var(--sh-2),inset 0 0 0 1px var(--line)}
.slip:focus-visible{outline:none;box-shadow:var(--sh-1),var(--ring)}
.slip.new{animation:pop .3s cubic-bezier(.2,.9,.3,1.3) both}
.slip .no{font:700 22px/1 var(--serif);font-variant-numeric:tabular-nums}
.slip .pv{font:11px/1.45 var(--mono);color:var(--ink-2);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;word-break:break-word}
.slip .meta{position:absolute;top:11px;right:11px;font-size:10.5px;font-weight:650;padding:1px 7px;border-radius:999px;background:var(--bg);color:var(--muted)}
.slip .meta:empty{display:none}
.slip.dup .meta{background:var(--danger-wash);color:var(--danger)}
.slip.on{color:var(--on-primary);background:linear-gradient(140deg,var(--primary),var(--primary-2));box-shadow:var(--sh-3)}
.slip.on .pv{color:rgb(255 255 255/.88)}
.slip.on .meta{background:rgb(255 255 255/.22);color:#fff}
.slip.dragging{opacity:.4}
.slip.drop{outline:3px solid var(--primary);outline-offset:3px}
.cut{grid-column:1/-1;display:flex;align-items:center;gap:10px;font-size:11px;font-weight:700;color:var(--muted);letter-spacing:.06em;text-transform:uppercase;margin:2px 0}
.cut::before,.cut::after{content:"";flex:1;border-top:2px dashed var(--line)}
.empty{color:var(--muted);font-size:13px;margin:16px 2px}

.edhead{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}
.pos{font:700 30px/1 var(--serif);font-variant-numeric:tabular-nums}
.pos small{font-size:16px;color:var(--muted);font-weight:400}
.nav{display:flex;gap:6px}
.tabs{display:inline-flex;gap:4px;padding:4px;border-radius:var(--r);background:var(--bg);box-shadow:var(--inset);margin-bottom:12px}
.tabs button{border:0;background:none;padding:6px 14px;border-radius:var(--r-sm);cursor:pointer;color:var(--muted);font-size:13px;font-weight:650;transition:background .15s,color .15s}
.tabs button.on{background:var(--card);color:var(--ink);box-shadow:var(--sh-1)}
.trigline{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px;font-size:12px;color:var(--muted)}
.trigline code{font:12px var(--mono);padding:4px 10px;border-radius:var(--r-sm);background:color-mix(in srgb,var(--primary) 12%,var(--card));color:color-mix(in srgb,var(--primary) 80%,var(--ink))}
#ed{min-height:340px}
.orig{min-height:200px;padding:14px 16px;border-radius:var(--r);background:var(--bg);box-shadow:var(--inset);font:13px/1.6 var(--mono);white-space:pre-wrap;word-break:break-word;color:var(--ink-2)}
.orig del{color:var(--danger);background:var(--danger-wash);border-radius:4px;text-decoration-thickness:1px}
.edfoot{display:flex;justify-content:space-between;align-items:center;margin-top:10px;font-size:12px;color:var(--muted)}

dialog{width:520px;max-width:calc(100vw - 32px);padding:0;border:0;border-radius:20px;background:var(--card);color:var(--ink);box-shadow:var(--sh-3)}
dialog[open]{animation:pop .24s cubic-bezier(.2,.9,.3,1.2)}
dialog::backdrop{background:rgb(var(--shadow)/.28);backdrop-filter:blur(3px)}
.dlg{padding:20px 22px 22px}
.dlghead{display:flex;justify-content:space-between;align-items:center}
.dlghead h3{font:700 18px/1.2 var(--serif);margin:0}
.dlg p{margin:6px 0 14px;font-size:12.5px;color:var(--muted)}
.kw{display:flex;align-items:center;padding:8px 4px;border-bottom:1px solid var(--line);font:12.5px var(--mono)}
.kw .hits{font-family:var(--sans);font-size:11px;color:var(--muted);margin-left:auto;margin-right:12px}
.kw button{border:0;background:none;color:var(--muted);cursor:pointer;font-size:16px;line-height:1;border-radius:6px;padding:2px 6px}
.kw button:hover{color:var(--danger);background:var(--danger-wash)}
.addkw{display:flex;gap:8px;margin-top:12px}
.addkw input,.preset input{height:36px;padding:0 10px;border:1px solid var(--line);border-radius:var(--r-sm);background:var(--bg);box-shadow:var(--inset);font:12.5px var(--mono);outline:none;color:var(--ink)}
.addkw input{flex:1}
.addkw input:focus,.preset input:focus{border-color:var(--primary);box-shadow:var(--inset),var(--ring)}
.preset{border-radius:var(--r);padding:12px;background:var(--bg);box-shadow:var(--inset);margin-bottom:10px;display:grid;gap:8px}
.preset .row{display:grid;grid-template-columns:1fr 2fr;gap:8px}
.preset label{display:grid;gap:4px;font-size:11.5px;font-weight:700;color:var(--ink-2);text-transform:uppercase;letter-spacing:.04em}
.preset input{background:var(--card);text-transform:none;letter-spacing:0;font-weight:400}
.preset .btn.danger{justify-self:end;height:32px}

.toast{position:fixed;left:50%;bottom:24px;transform:translate(-50%,90px);opacity:0;pointer-events:none;display:flex;gap:14px;align-items:center;max-width:calc(100vw - 32px);background:var(--ink);color:var(--card);padding:10px 18px;border-radius:999px;font-size:13px;box-shadow:var(--sh-3);transition:transform .25s cubic-bezier(.2,.9,.3,1.2),opacity .2s}
.toast.show{transform:translate(-50%,0);opacity:1;pointer-events:auto}
.toast button{background:none;border:0;color:var(--primary-2);font-weight:700;cursor:pointer}

@keyframes pop{from{opacity:0;transform:translateY(8px) scale(.97)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
@media (max-width:900px){
  .mast{flex-wrap:wrap;padding:16px}
  .bar{margin:0 16px}
  .desk{grid-template-columns:1fr;padding:16px}
  .right{position:static;max-height:none}
  .preset .row{grid-template-columns:1fr}
}
</style>
</head>
<body>

<header class="mast">
  <div class="logo" aria-hidden="true">P</div>
  <div>
    <h1>Prompt Collector</h1>
    <div class="sub" id="saved">Autosaved locally</div>
  </div>
  <div class="spacer"></div>
  <div class="themes" role="group" aria-label="Theme">
    <button data-theme-set="sunny" aria-pressed="true">Sunny</button><button data-theme-set="sky" aria-pressed="false">Sky</button>
  </div>
  <div class="stat hot"><b id="total">0</b><span>prompts</span></div>
  <div class="stat"><b id="files">0</b><span>files to export</span></div>
</header>

<div class="bar">
  <div class="trigctl" id="trigCtl" hidden>
    <label class="field">Trigger <select id="trig"></select></label>
    <button class="btn icon" id="trigOpen" aria-label="Edit trigger presets" title="Edit trigger presets">&#9998;</button>
    <span class="sep"></span>
  </div>
  <label class="field">Prompts per file <input type="number" id="per" min="1" step="1"></label>
  <span class="hint" id="namehint"></span>
  <div class="spacer"></div>
  <button class="btn icon count" id="kwOpen" aria-label="Strip keywords" title="Strip keywords"><svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M8.6 7.6 20 18M8.6 16.4 20 6"/></svg><span id="kwCount">0</span></button>
  <button class="btn danger" id="clear">Clear list</button>
  <button class="btn" id="exportJson">Export JSON</button>
  <button class="btn primary" id="exportTxt">Export TXT</button>
</div>

<main class="desk">
  <section>
    <div class="panel">
      <label class="label" for="in"><span>Paste prompt</span><em><kbd>Enter</kbd> add · <kbd>Shift</kbd>+<kbd>Enter</kbd> new line</em></label>
      <textarea id="in" placeholder="Paste a prompt and press Enter"></textarea>
      <div class="receipt" id="receipt"></div>
      <div class="dupe" id="dupe" role="alert">Same as <b id="dupeNo"></b> after cleanup.<span class="spacer"></span>
        <button class="btn" id="skip">Skip</button><button class="btn primary" id="addAnyway">Add anyway</button></div>
    </div>
    <div class="listhead"><h2>Collected</h2><span>Drag to reorder · dashed line marks a file break</span></div>
    <div class="slips" id="slips"></div>
    <p class="empty" id="empty">Paste a prompt above and press Enter.</p>
  </section>

  <aside class="panel right">
    <div class="edhead">
      <div class="pos" id="pos"></div>
      <div class="nav"><button class="btn icon" id="prev" aria-label="Previous prompt">&larr;</button><button class="btn icon" id="next" aria-label="Next prompt">&rarr;</button></div>
    </div>
    <div class="tabs"><button class="on" data-t="clean">Cleaned</button><button data-t="orig">Original</button><button data-t="final" id="tabFinal" hidden>Export preview</button></div>
    <div class="trigline" id="trigline" hidden></div>
    <div class="editor">
      <textarea id="ed" aria-label="Edit prompt"></textarea>
      <div class="orig" id="orig" hidden></div>
    </div>
    <div class="edfoot"><span id="chars"></span><button class="btn danger" id="del">Delete prompt</button></div>
  </aside>
</main>

<dialog id="kwDlg" aria-label="Strip keywords">
  <div class="dlg">
    <div class="dlghead"><h3>Strip keywords</h3><button class="btn icon" id="kwClose" aria-label="Close">&times;</button></div>
    <p>Any sentence containing one of these is removed on add. Case is ignored. Prompts you edited by hand are left alone.</p>
    <div id="kws"></div>
    <div class="addkw"><input id="kwIn" aria-label="New keyword" placeholder="e.g. reference image"><button class="btn" id="kwAdd">Add</button></div>
  </div>
</dialog>

<dialog id="trigDlg" aria-label="Trigger presets">
  <div class="dlg">
    <div class="dlghead"><h3>Trigger presets</h3><button class="btn icon" id="trigClose" aria-label="Close">&times;</button></div>
    <p>The active trigger is put at the start of every exported prompt. If the prompt already contains one of the "already described" phrases, only the token is added.</p>
    <div id="trigList"></div>
    <button class="btn" id="trigAdd">+ Add preset</button>
  </div>
</dialog>

<div class="toast" id="toast" role="status"><span id="toastMsg"></span><button id="toastAct" hidden></button></div>

<script src="core.js"></script>
```

- [ ] **Step 2: Add the theme code**

In the script, replace

```js
function render() {
  const items = state.items, n = items.length, per = state.perFile;
```

with

```js
function render() {
  applyTheme();
  const items = state.items, n = items.length, per = state.perFile;
```

and insert this block immediately before the line `function boot() {`:

```js
// ---- theme ----
function applyTheme() {
  document.documentElement.dataset.theme = state.theme;
  document.querySelectorAll("[data-theme-set]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.themeSet === state.theme)));
}
document.querySelector(".themes").addEventListener("click", e => {
  const b = e.target.closest("[data-theme-set]");
  if (b) { state.theme = b.dataset.themeSet; changed(); }
});

```

- [ ] **Step 3: Check it in the browser**

Serve and open the page (see "How to check UI tasks" above), then check:

1. **First load:** Sunny colors, the rounded cards with shadows, and the gradient "P" logo are visible. The theme switch shows Sunny pressed. No trigger controls, no Export preview tab and no trigger line are visible yet.
2. **Theme switch:** clicking Sky switches every color at once and sets `document.documentElement.dataset.theme === "sky"`. Reload: the attribute is `"sky"` and the switch shows Sky pressed. The inline `<head>` script sets the attribute before the body is parsed, so there is no Sunny flash. Switching back to Sunny persists too.
3. **Regression run:**
   - Add prompts. Check the duplicate warning, the Original tab, and per-file dividers.
   - Delete one prompt and Undo it.
   - Open the strip keywords dialog: confirm the backdrop click closes it, and clicking inside it does not.
   - Click Clear list and Cancel.
   - Export TXT with downloads captured in-page, so nothing is really downloaded:

     ```js
     window.__dl = [];
     HTMLAnchorElement.prototype.click = function () { if (this.download) window.__dl.push(this.download); };
     ```

     Then confirm the expected file names.
4. **Narrow width:** below 900px (`resize_window` 800x900) the layout is one column with no horizontal scroll. Reset with preset `desktop` afterwards.
5. **Console:** no errors.

- [ ] **Step 4: Commit**

```bash
git add prompt/prompt_Collector/dist/index.html
git commit -m "Restyle Prompt Collector with Sunny/Sky themes and deeper controls

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Trigger UI

**Files:**
- Modify: `prompt/prompt_Collector/dist/index.html`

**Interfaces:**
- Consumes: `PromptCore.triggerPrefix`, `applyTrigger`, `parseAlready`, `findTrigger`, `collapseBlank`, and `buildFiles({ ..., trigger })` (Tasks 1-2). Markup ids from Task 3: `#trigCtl`, `#trig`, `#trigOpen`, `#tabFinal`, `#trigline`, `#trigDlg`, `#trigClose`, `#trigList`, `#trigAdd`. Script globals: `state`, `$`, `esc`, `newId`, `changed()`, `render()`, `toast()`.
- Produces: `activeTrigger()` and editor view `"final"`.

- [ ] **Step 1: Unhide the trigger markup**

Replace `<div class="trigctl" id="trigCtl" hidden>` with `<div class="trigctl" id="trigCtl">`.
Replace `<button data-t="final" id="tabFinal" hidden>Export preview</button>` with `<button data-t="final" id="tabFinal">Export preview</button>`.
Replace `<div class="trigline" id="trigline" hidden></div>` with `<div class="trigline" id="trigline"></div>`.

- [ ] **Step 2: Add the active-trigger helper**

Replace

```js
const newId = () => Math.random().toString(36).slice(2, 8) + Date.now().toString(36).slice(-4);
```

with

```js
const newId = () => Math.random().toString(36).slice(2, 8) + Date.now().toString(36).slice(-4);
const activeTrigger = () => C.findTrigger(state.triggers, state.activeTrigger);
```

and replace

```js
let view = "clean";      // editor tab: "clean" | "orig"
```

with

```js
let view = "clean";      // editor tab: "clean" | "orig" | "final"
```

- [ ] **Step 3: Render the trigger select, the editor trigger line, the preview and the export character count**

Replace

```js
  if ($("ed").value !== text) $("ed").value = text;
  $("chars").textContent = it ? `${text.length} chars · ${text ? text.split("\n").length : 0} lines` : "";
  $("orig").innerHTML = it ? markRemoved(it) : "";
  $("ed").hidden = view !== "clean";
  $("orig").hidden = view !== "orig";
  document.querySelectorAll(".tabs button").forEach(b => b.classList.toggle("on", b.dataset.t === view));
  renderKeywords();
}
```

with

```js
  const trig = activeTrigger();
  const body = it ? C.collapseBlank(text) : "";
  const prefix = body ? C.triggerPrefix(body, trig) : "";
  const final = body ? C.applyTrigger(body, trig) : "";
  const shown = view === "final" ? final : text;
  if ($("ed").value !== shown) $("ed").value = shown;
  $("ed").readOnly = view === "final";
  $("chars").textContent = it ? `${final.length} chars on export` : "";
  $("trigline").innerHTML = !trig ? "No trigger selected"
    : !body ? "Empty prompt, skipped on export"
    : prefix ? `Adds on export: <code>${esc(prefix)}</code>` : "Token already in prompt, nothing added";
  $("orig").innerHTML = it ? markRemoved(it) : "";
  $("ed").hidden = view === "orig";
  $("orig").hidden = view !== "orig";
  document.querySelectorAll(".tabs button").forEach(b => b.classList.toggle("on", b.dataset.t === view));
  renderKeywords();
  renderTriggerSelect();
}

function renderTriggerSelect() {
  const sel = $("trig");
  if (document.activeElement === sel) return; // don't rebuild an open dropdown
  sel.innerHTML = `<option value="">None</option>` +
    state.triggers.map(t => `<option value="${esc(t.id)}">${esc(t.token.trim() || "(untitled)")}</option>`).join("");
  sel.value = state.activeTrigger;
}
```

- [ ] **Step 4: Show the trigger in the add receipt**

Replace

```js
  $("receipt").innerHTML = `Last add: <b>${r ? `removed ${r} sentence${r > 1 ? "s" : ""}` : "nothing removed"}</b>`;
```

with

```js
  const prefix = C.triggerPrefix(text, activeTrigger());
  $("receipt").innerHTML = `<span class="pill">${r ? `removed ${r} sentence${r > 1 ? "s" : ""}` : "nothing removed"}</span>` +
    (prefix ? `<span class="pill trig">+ ${esc(prefix)}</span>` : "");
```

- [ ] **Step 5: Keep arrow keys inside the select**

Replace

```js
  if (e.target.closest("textarea, input, dialog") || e.altKey || e.ctrlKey || e.metaKey) return;
```

with

```js
  if (e.target.closest("textarea, input, select, dialog") || e.altKey || e.ctrlKey || e.metaKey) return;
```

- [ ] **Step 6: Pass the trigger to export**

Replace

```js
  const { files, skipped } = C.buildFiles(kind, state.items, { perFile: state.perFile, keywords: state.keywords });
```

with

```js
  const { files, skipped } = C.buildFiles(kind, state.items, { perFile: state.perFile, keywords: state.keywords, trigger: activeTrigger() });
```

- [ ] **Step 7: Add the select and preset dialog handlers**

Insert this block immediately before the final line `boot();`:

```js
// ---- trigger presets ----
$("trig").addEventListener("change", e => {
  state.activeTrigger = e.target.value;
  changed();
  const t = activeTrigger();
  toast(t ? `Trigger ${t.token.trim() || "(untitled)"} applies to all ${state.items.length} prompts on export` : "Trigger off");
});
function renderTriggerRows() {
  $("trigList").innerHTML = state.triggers.map(t => `<div class="preset" data-id="${esc(t.id)}">
    <div class="row"><label>Token<input data-f="token" value="${esc(t.token)}"></label>
    <label>Description<input data-f="description" value="${esc(t.description)}"></label></div>
    <label>Already described if prompt contains (comma separated)<input data-f="already" value="${esc(t.already.join(", "))}"></label>
    <button class="btn danger" data-del="${esc(t.id)}">Delete preset</button></div>`).join("") || `<p>No presets yet.</p>`;
}
$("trigOpen").onclick = () => { renderTriggerRows(); $("trigDlg").showModal(); };
$("trigClose").onclick = () => $("trigDlg").close();
$("trigDlg").addEventListener("click", e => { if (e.target === $("trigDlg")) $("trigDlg").close(); }); // backdrop
// Edits update state without rebuilding the rows, so the caret stays put while typing.
$("trigList").addEventListener("input", e => {
  const field = e.target.dataset.f, row = e.target.closest(".preset");
  if (!field || !row) return;
  const t = state.triggers.find(x => x.id === row.dataset.id);
  if (!t) return;
  t[field] = field === "already" ? C.parseAlready(e.target.value) : e.target.value;
  changed();
});
$("trigList").addEventListener("click", e => {
  const id = e.target.dataset.del;
  if (id === undefined) return;
  state.triggers = state.triggers.filter(t => t.id !== id);
  if (state.activeTrigger === id) state.activeTrigger = "";
  renderTriggerRows();
  changed();
});
$("trigAdd").onclick = () => {
  const t = { id: newId(), token: "", description: "", already: [] };
  state.triggers.push(t);
  renderTriggerRows();
  changed();
  $("trigList").querySelector(`[data-id="${t.id}"] input`).focus();
};

```

- [ ] **Step 8: Check it in the browser**

Serve and open the page, then check:

1. **Select contents:** the Trigger select shows `None` and `Ivan_Ryo`, with None selected. The editor line reads `No trigger selected`.
2. **Activating and adding:** select `Ivan_Ryo` and the toast reads `Trigger Ivan_Ryo applies to all N prompts on export`. Then:
   - Add `Close-up portrait, rim light.`. The receipt shows a `nothing removed` pill and a `+ Ivan_Ryo. A 25yo Asian young man.` pill.
   - The editor line reads `Adds on export: Ivan_Ryo. A 25yo Asian young man.`.
   - Export preview shows `Ivan_Ryo. A 25yo Asian young man. Close-up portrait, rim light.` read-only, and typing there changes nothing.
   - The Cleaned tab still shows the body only, and `state.items[...].text` has no trigger.
3. **Already described:** add `Night market, an Asian young man in denim.`. The editor line reads `Adds on export: Ivan_Ryo.`.
4. **Token already present:** add `ivan_ryo standing in rain.`. The line reads `Token already in prompt, nothing added`.
5. **Hand-edited prompt:** edit the first prompt by hand (Cleaned tab). Export preview still starts with the trigger.
6. **Preset dialog:**
   - Open ✎. Change the description to `A 30yo Asian man`; the caret stays in the field while typing, and Export preview updates to `… A 30yo Asian man. …`.
   - Change the already phrases to `asian man, Denim`; they are stored as `["asian man","denim"]`.
   - `+ Add preset` adds an empty row with focus in its Token field, and the select lists `(untitled)`.
   - Delete the active preset: the select falls back to None.
   - ×, Esc and a backdrop click all close the dialog.
7. **Export:** capture downloads in-page (Task 3 Step 3 item 3) and export TXT. Each block in the captured content starts with the expected prefix, and `content.split("\n\n")` gives one block per prompt. JSON has `trigger` and per-prompt `body`.
8. **Persistence:** reload. The active trigger, presets and theme persist.
9. **Console:** no errors.

- [ ] **Step 9: Commit**

```bash
git add prompt/prompt_Collector/dist/index.html
git commit -m "Add trigger preset picker, editor, export preview and export wiring

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Newest-first list without scroll jumps

**Files:**
- Modify: `prompt/prompt_Collector/dist/index.html`

**Interfaces:**
- Consumes: `render()` slip rendering, `addPrompt()` from v1/Task 4. Slip `data-i` remains the real index into `state.items`, so drag, select and delete handlers are unchanged.
- Produces: nothing new.

- [ ] **Step 1: Render slips newest first**

Replace

```js
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
```

with

```js
  const firstSeen = new Map();
  items.forEach((it, i) => { if (!firstSeen.has(it.text)) firstSeen.set(it.text, i + 1); });
  const width = files > 99 ? 3 : 2;
  const num = k => String(k).padStart(width, "0");
  let html = "";
  for (let i = n - 1; i >= 0; i--) { // newest first; the number stays the export position
    const it = items[i];
    const dupOf = firstSeen.get(it.text) !== i + 1 ? firstSeen.get(it.text) : 0;
    const mark = dupOf ? `= #${dupOf}` : it.edited ? "edited" : it.removed.length ? "cleaned" : "";
    const cls = "slip" + (i === state.selected ? " on" : "") + (dupOf ? " dup" : "") + (it.id === lastAdded ? " new" : "");
    html += `<button class="${cls}" data-i="${i}" draggable="true">` +
      `<span class="no">${i + 1}</span><span class="meta">${mark}</span><span class="pv">${esc(it.text)}</span></button>`;
    if (i && i % per === 0) html += `<div class="cut">&#9650; file ${num(i / per + 1)} · file ${num(i / per)} &#9660;</div>`;
  }
  $("slips").innerHTML = html;
```

- [ ] **Step 2: Stop scrolling after adding a prompt**

In `addPrompt`, replace (the receipt line from Task 4 is included so the match is unique; `select()` ends with the same two lines and must keep them)

```js
    (prefix ? `<span class="pill trig">+ ${esc(prefix)}</span>` : "");
  changed();
  $("slips").querySelector(".on")?.scrollIntoView({ block: "nearest" });
}
```

with

```js
    (prefix ? `<span class="pill trig">+ ${esc(prefix)}</span>` : "");
  changed(); // no scrollIntoView: the new slip renders first, right under the composer, and focus stays in it
}
```

(`select()` keeps its own `scrollIntoView` for clicks and arrow keys.)

- [ ] **Step 3: Update the list heading**

Replace

```html
    <div class="listhead"><h2>Collected</h2><span>Drag to reorder · dashed line marks a file break</span></div>
```

with

```html
    <div class="listhead"><h2>Collected</h2><span>Newest first · export runs #1 → #n</span></div>
```

- [ ] **Step 4: Check it in the browser**

Serve and open the page. Set prompts per file to `2`, then add 5 short prompts `p1.`, `p2.`, `p3.`, `p4.` and `p5.` in that order. Check:

1. **Order and numbering:** the slips read `5, 4, 3, 2, 1` from the top and are numbered `5` to `1`. Two dividers appear: between slips 3 and 2 it reads `▲ file 02 · file 01 ▼`, and between slips 5 and 4 it reads `▲ file 03 · file 02 ▼`.
2. **No scroll on add:** before adding a 6th prompt, scroll the window to the top (`scrollTo(0,0)`). After pressing Enter, `window.scrollY` is still `0`, `document.activeElement.id === "in"`, and the first slip in `#slips` is `#6`.
3. **Navigation:** ← moves to #5, and → from #5 moves to #6. Clicking a slip selects it.
4. **Export order:** export TXT (captured in-page). The blocks run `p1.` … `p6.`, oldest first, split across files `_01` to `_03`.
5. **Duplicates:** add `p2.` again with Add anyway. The newest slip shows `= #2`.
6. **Console:** no errors.

- [ ] **Step 5: Final checks**

1. Run `cd prompt/prompt_Collector && node test_core.mjs`. Expected: `core: all checks passed`.
2. **Human check:**
   - Double-click `prompt\prompt_Collector\dist\index.html`, switch to Sky, close the tab and reopen it: Sky shows with no flash.
   - Select the Ivan_Ryo trigger, add a few prompts, and export TXT.
   - Load the TXT into ComfyUI Text_Splitter: `count` matches, and each prompt starts with the trigger.
   - Drag one slip with the real mouse.

- [ ] **Step 6: Commit**

```bash
git add prompt/prompt_Collector/dist/index.html
git commit -m "Show newest prompts first and keep focus in the composer after adding

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
