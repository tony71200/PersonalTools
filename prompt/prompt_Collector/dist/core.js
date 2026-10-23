/* Prompt Collector core: pure logic, no DOM.
   Loaded by dist/index.html as a classic script (window.PromptCore) and by test_core.mjs via require. */
(function (root) {
  "use strict";

  const DEFAULT_KEYWORDS = ["uploaded photo", "facial structure", "exact body proportions", "reference image"];
  const DEFAULT_PER_FILE = 50;
  const SENTENCE_SPLIT = /(?<=[.!?])\s+/;
  const DEFAULT_TRIGGERS = [{
    id: "ivan", token: "Ivan_Ryo", description: "A 25yo Asian young man.",
    already: ["asian young man", "young asian man", "asian man"],
  }];
  const THEMES = ["sunny", "sky"];
  const DEFAULT_SUFFIX = "White balance 5500K, 50mm lens, f/1.8 aperture. Slightly blur the background for portrait shots. " +
    "Remove unnecessary details; keep shadows natural and soft.";

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

  // ---- find / replace: whole word, case-insensitive. Letters of any script (Vietnamese too) count as word characters.
  function wordRe(term) {
    const t = String(term || "").trim();
    if (!t) return null;
    const esc = t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return new RegExp(`(?<![\\p{L}\\p{N}_])${esc}(?![\\p{L}\\p{N}_])`, "giu");
  }
  function countWord(text, term) {
    const re = wordRe(term);
    return re ? (String(text).match(re) || []).length : 0;
  }
  // Next match at or after `from`, wrapping to the start; null when there is none.
  function findWord(text, term, from = 0) {
    const re = wordRe(term);
    if (!re) return null;
    const all = [...String(text).matchAll(re)].map(m => ({ start: m.index, end: m.index + m[0].length }));
    return all.find(m => m.start >= from) || all[0] || null;
  }
  function replaceWord(text, find, replace) {
    const re = wordRe(find);
    if (!re) return { text, count: 0 };
    let count = 0;
    const out = String(text).replace(re, () => { count++; return replace; }); // a function keeps "$" literal
    return { text: out, count };
  }
  // Pairs that occur in text, with their position in the list and how often they occur.
  function scanPairs(text, pairs) {
    return pairs.map((p, index) => ({ index, find: p.find, replace: p.replace, count: countWord(text, p.find) }))
      .filter(p => p.count > 0);
  }
  function applyPairs(text, pairs) {
    let count = 0;
    for (const p of pairs) {
      const r = replaceWord(text, p.find, p.replace);
      text = r.text;
      count += r.count;
    }
    return { text, count };
  }
  function cleanPairs(list) {
    return (Array.isArray(list) ? list : [])
      .filter(p => p && typeof p.find === "string" && typeof p.replace === "string")
      .map(p => ({ find: p.find.trim(), replace: p.replace.trim() }))
      .filter(p => p.find);
  }

  // ---- suffix: appended at export only, never stored in a prompt ----
  function applySuffix(text, suffix) {
    const s = suffix && suffix.on ? String(suffix.text || "").replace(/\s+/g, " ").trim() : "";
    const body = String(text).replace(/\s+$/, "");
    if (!s || !body || body.toLowerCase().includes(s.toLowerCase())) return text;
    return body + (/[.!?]$/.test(body) ? " " : ". ") + s;
  }

  function findDuplicate(items, text) {
    return items.findIndex(it => collapseBlank(it.text) === text);
  }

  // Re-run clean on items the user has not edited by hand. Returns new objects; input untouched.
  function reclean(items, keywords) {
    return items.map(it => it.edited ? it : { ...it, ...clean(it.raw, keywords) });
  }

  // Trigger presets are applied at export time only; prompts never store them.
  const cleanToken = token => String(token || "").replace(/\s+/g, " ").trim().replace(/\.+$/, "");

  function triggerPrefix(text, trigger) {
    const token = trigger ? cleanToken(trigger.token) : "";
    if (!token) return "";
    const lower = String(text).toLowerCase();
    if (lower.includes(token.toLowerCase())) return "";
    const head = token + ".";
    let desc = String(trigger.description || "").replace(/\s+/g, " ").trim();
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
      replacements: [], suffix: { text: DEFAULT_SUFFIX, on: false },
    };
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
    if (!Array.isArray(state.triggers)) state.triggers = defaultState().triggers;
    if (!findTrigger(state.triggers, state.activeTrigger)) state.activeTrigger = "";
    if (!THEMES.includes(state.theme)) state.theme = "sunny";
    state.replacements = cleanPairs(state.replacements);
    const sf = state.suffix;
    if (!sf || typeof sf.text !== "string" || typeof sf.on !== "boolean") state.suffix = defaultState().suffix;
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
  // The active trigger is prepended and the suffix appended here; neither is stored in the item.
  function buildFiles(kind, items, { perFile, keywords, trigger = null, suffix = null, now = new Date() }) {
    const prompts = [];
    for (const it of items) {
      const body = collapseBlank(it.text);
      if (body) prompts.push({ ...it, body, text: applySuffix(applyTrigger(body, trigger), suffix) });
    }
    const suffixText = (suffix && suffix.on && String(suffix.text || "").replace(/\s+/g, " ").trim()) || null;
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
            trigger: trigger && triggerPrefix("", trigger) ? { token: cleanToken(trigger.token), description: trigger.description, already: trigger.already } : null,
            suffix: suffixText,
            prompts: group.map((p, j) => ({
              index: part * perFile + j + 1,
              text: p.text,
              body: p.body,
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
    DEFAULT_KEYWORDS, DEFAULT_PER_FILE, DEFAULT_TRIGGERS, collapseBlank, clean, findDuplicate, reclean,
    triggerPrefix, applyTrigger, parseAlready, findTrigger, defaultState, parseState,
    chunk, move, stamp, isoLocal, fileNames, buildFiles,
    DEFAULT_SUFFIX, countWord, findWord, replaceWord, scanPairs, applyPairs, cleanPairs, applySuffix,
  };
  root.PromptCore = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
