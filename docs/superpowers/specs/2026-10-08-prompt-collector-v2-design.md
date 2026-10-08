# Prompt Collector v2: Design

Date: 2026-10-08
Builds on: [2026-10-08-prompt-collector-design.md](2026-10-08-prompt-collector-design.md). Everything there still holds unless this document replaces it.
Mockup: [2026-10-08-prompt-collector-v2-mockup.html](2026-10-08-prompt-collector-v2-mockup.html). It has sample data and no persistence. Its third "Berry" palette was for comparison only and is not built.

## Goals

1. **Trigger word presets.** A LoRA trigger (e.g. `Ivan_Ryo`) is added to the start of every exported prompt. A description (e.g. `A 25yo Asian young man.`) is added only when the prompt does not already describe the subject.
2. **Newest-first list.** After pressing Enter the page must not jump. The newest prompt appears right under the composer and focus stays in the composer.
3. **Brighter look.** Two switchable themes, Sunny and Sky. Controls are rounded and have depth.

## Data model changes

`state` keeps `version: 1`. New fields are filled from defaults by `parseState`, so data saved by v1 loads unchanged.

```js
state = {
  // ...v1 fields: version, items, keywords, perFile, selected
  triggers: [{
    id: "ivan",                                   // random id for new presets
    token: "Ivan_Ryo",
    description: "A 25yo Asian young man.",
    already: ["asian young man", "young asian man", "asian man"]  // lowercase phrases
  }],
  activeTrigger: "",                              // a preset id, or "" for None
  theme: "sunny"                                  // "sunny" | "sky"
}
```

- **Defaults:** `triggers` holds the single `Ivan_Ryo` preset shown above, `activeTrigger` is `""` (None), and `theme` is `"sunny"`.
- **Validation in `parseState`:** if `triggers` is not an array, use the defaults. If `activeTrigger` does not match a preset id, reset it to `""`. If `theme` is not `"sunny"` or `"sky"`, use `"sunny"`.
- **Items are unchanged.** `item.text` holds the body only. The trigger is never written into `text`, `raw`, or `removed`.

## Trigger logic (core.js)

`triggerPrefix(text, trigger) -> string`:

1. If `trigger` is null, or its token (trimmed, trailing `.` removed) is empty, return `""`.
2. Lowercase `text`. If it contains the lowercase token, return `""`, so the token is never added twice.
3. Let `head = token + "."`.
4. If the description (trimmed) is empty, or the lowercase text contains any non-empty `already` phrase, return `head`.
5. Otherwise return `head + " " + description`. Add a trailing `.` to the description if it does not already end in `.`, `!` or `?`.

`applyTrigger(text, trigger) -> string` returns `prefix + " " + text` when the prefix is non-empty, and `text` otherwise.

Phrases are matched by substring after lowercasing, the same way strip keywords are matched. `already` entries are stored trimmed and lowercased, with empty entries dropped.

Examples with the default preset active:

| Body | Exported text |
|---|---|
| `Night market, an Asian young man in denim.` | `Ivan_Ryo. Night market, an Asian young man in denim.` |
| `Close-up portrait, rim light.` | `Ivan_Ryo. A 25yo Asian young man. Close-up portrait, rim light.` |
| `ivan_ryo standing in rain.` | `ivan_ryo standing in rain.` |

## Export changes

`buildFiles(kind, items, { perFile, keywords, trigger = null, now })`:

- **Which prompts:** empty-body detection, chunking and file names are unchanged. A prompt whose body is empty is skipped; it is never exported as a trigger on its own.
- **TXT:** each block is `applyTrigger(collapseBlank(body), trigger)`. Blocks are still joined with `\n\n`, with one trailing `\n`. The trigger has no newlines, so the Text_Splitter contract still holds.
- **JSON:** add a file-level `"trigger"` field, either `{ "token", "description", "already" }` or `null`. Each prompt's `"text"` is the final exported text, and a new `"body"` field holds the text without the trigger. All other fields are unchanged.
- **Duplicates:** the duplicate check and `= #N` markers still compare bodies.

## Trigger UI

- **Toolbar:** a labelled `Trigger` `<select>` lists `None` and every preset by token. Changing it sets `activeTrigger`, saves, and shows the toast `Trigger <token> applies to all N prompts on export` (or `Trigger off`).
- **✎ button:** sits next to the select (`aria-label="Edit trigger presets"`) and opens a native `<dialog>`. The dialog closes the same ways as the strip-keywords dialog: ×, Esc, or a backdrop click.
- **Preset rows in the dialog:** each preset is one row with three inputs: Token, Description, and "Already described if prompt contains (comma separated)". It also has a Delete button. Edits apply on `input`: `already` is split on commas, trimmed, lowercased, and empties are dropped. After every edit the app saves and re-renders. Deleting the active preset sets `activeTrigger` to `""`.
- **`+ Add preset`:** appends an empty preset and focuses its Token input. A preset with an empty token is listed in the select as `(untitled)` and adds nothing on export (rule 1).
- **Editor:** a line above the textarea shows one of three states:
  - `Adds on export: <prefix>` when the prefix is non-empty.
  - `Token already in prompt, nothing added`.
  - `No trigger selected`.
- **Export preview tab:** a third editor tab, next to `Cleaned` and `Original`. It shows `applyTrigger(text, trigger)` in the read-only textarea. Typing is only possible in `Cleaned`.
- **Receipt:** after adding a prompt, the receipt shows a pill for the removed-sentence count and, when the prefix is non-empty, a second pill `+ <prefix>`.
- **Character count:** the count under the editor shows the length of the exported text, e.g. `412 chars on export`.

## List order and focus

- **Order:** slips render newest first, i.e. in reverse of `state.items`. The number on each slip stays its 1-based position in `state.items`, which is the export order. `#1` is the oldest prompt and appears at the bottom.
- **File breaks:** a divider is placed between export positions `k*perFile` and `k*perFile + 1`. It reads `▲ file NN · file MM ▼`, where NN is the later file (above) and MM the earlier one (below). The digit width follows the file-name rule.
- **After adding:** a prompt added with Enter, or with "Add anyway", selects the new item but does not call `scrollIntoView` or move focus. The composer keeps focus. Clicking a slip or using ←/→ still scrolls the selected slip into view with `block: "nearest"`.
- **Navigation:** ←/→ and the prev/next buttons still move by export position: ← goes to #N−1, → to #N+1.
- **Drag reorder:** still works on real indices (`data-i`). Dropping slip A on slip B moves A to B's export position.
- **Header text:** the list heading reads `Newest first · export runs #1 → #n`.

## Visual design (replaces the v1 visual direction)

- **Theme switch:** a segmented switch in the masthead with the options `Sunny` and `Sky`. It sets `data-theme` on `<html>` and is saved in `state.theme`. The theme is applied before the first render so the page does not flash.
- **Theme tokens:**
  - Sunny: background `#FFF6E9`, card `#FFFFFF`, ink `#2A2140`, muted `#8C8299`, line `#F1DFC6`, primary `#FF6A3D` → `#FF9A3D` gradient, accent `#12B3A3`, danger `#E5384F`.
  - Sky: background `#EEF6FF`, card `#FFFFFF`, ink `#13233F`, muted `#7486A3`, line `#D5E4F7`, primary `#2E6BFF` → `#22B8FF` gradient, accent `#FFB020`, danger `#E5384F`.
  - All values are defined as CSS custom properties on `[data-theme=…]`.
- **Shape and depth:**
  - Radius is 16px for panels, 12px for controls and slips, 9px for small inputs, and fully round for pills, the toast and the theme switch.
  - Shadows come in three tinted levels (`--sh-1`, `--sh-2`, `--sh-3`), and text fields get an inset shadow.
  - Buttons rise 1px on hover and press down on `:active`. The primary button uses the gradient with an inner highlight.
  - The selected slip is filled with the primary gradient.
  - Dialogs are rounded to 20px and sit over a blurred, tinted backdrop.
  - Focus rings are a 3–4px primary-tinted halo.
- **Layout:** the masthead has a gradient "P" logo and two stat cards. The toolbar is a single rounded card. The composer, the slip grid, and the editor each sit in their own card. Everything else follows the mockup.
- **Kept from v1:**
  - Danger red is used only for destructive buttons, the duplicate warning, and struck text.
  - Under `prefers-reduced-motion`, all animation is turned off.
  - System fonts only, no network requests.
  - The layout stacks into one column below 900px.

## Out of scope

The third Berry palette, a dark theme, a per-prompt trigger override, multiple active triggers, triggers written into the prompt body, and import of JSON.

## Testing

Extend `test_core.mjs` (`node:assert`):

- **`triggerPrefix`:**
  - Null trigger returns `""`.
  - Empty token returns `""`.
  - Token already present (case-insensitive) returns `""`.
  - An `already` phrase matches, case-insensitively, and returns the token only.
  - No match returns the token and description.
  - A description with no final `.` gets one.
  - A token typed as `Ivan_Ryo.` gives `Ivan_Ryo.`, not `Ivan_Ryo..`.
  - An empty description returns the token only.
- **`applyTrigger`:** check the joining space, and the no-prefix case.
- **`parseState`:**
  - v1 data with no new fields gets the default triggers, `activeTrigger: ""` and `theme: "sunny"`.
  - An unknown `activeTrigger` resets to `""`.
  - A bad `theme` resets to `"sunny"`.
- **`buildFiles` with a trigger:**
  - TXT blocks carry the prefix and the Text_Splitter split still returns one block per prompt.
  - Empty-body items are skipped, with no lone trigger.
  - JSON has the file-level `trigger`, and each prompt has `text` (final) and `body`.
  - Without a trigger, the output equals v1 output plus `"trigger": null` and `"body"`.

Browser checklist, run on localhost by the agent and on `file://` by the human:

1. Adding with Enter does not scroll the page, focus stays in the composer, and the new slip is first in the list.
2. Slip numbers follow export order: the newest has the highest number, and dividers sit at the right positions.
3. The trigger select, the preset dialog (add, edit, delete), the editor trigger line, the Export preview tab, and the receipt pill all behave as specified.
4. A hand-edited prompt also gets the trigger in Export preview and in the exported TXT.
5. Choosing a theme survives a reload, with no theme flash on load.
6. No console errors.
