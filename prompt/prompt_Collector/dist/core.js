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
  root.PromptCore = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
