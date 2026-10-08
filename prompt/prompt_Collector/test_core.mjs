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
