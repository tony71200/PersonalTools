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
