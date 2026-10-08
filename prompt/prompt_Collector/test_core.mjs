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
assert.equal(C.findDuplicate([{ text: "a\n\nb" }], "a\nb"), 0);

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
assert.deepEqual(C.parseState(null).state, {
  version: 1, items: [], keywords: C.DEFAULT_KEYWORDS, perFile: 50, selected: 0,
  triggers: C.DEFAULT_TRIGGERS, activeTrigger: "", theme: "sunny",
});
assert.equal(C.parseState("{not json").corrupt, true);
assert.equal(C.parseState(JSON.stringify({ version: 2, items: [], keywords: [] })).corrupt, true);
assert.equal(C.parseState(JSON.stringify({ version: 1, items: [], keywords: [], perFile: 0 })).state.perFile, 50);
{
  const s = { version: 1, items: [{ id: "a", raw: "r", text: "t", removed: [], edited: false, addedAt: "x" }], keywords: ["k"], perFile: 7, selected: 0 };
  assert.deepEqual(C.parseState(JSON.stringify(s)), {
    state: { ...s, triggers: C.DEFAULT_TRIGGERS, activeTrigger: "", theme: "sunny" }, corrupt: false,
  });
}

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

console.log("core: all checks passed");
