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

  // ---- exports ----
  const api = {
    isImage, baseName, naturalCompare, parseH3Name, pairFolder, imageCount, anyImage, countLabel, filterTree,
    detectEol, toEol, splitH3, joinH3, h3Bodies, setH3Bodies,
    padSnippet, DEFAULT_WORDS, parseWords, mergeWords, wordsJson, copyPngText,
  };
  root.CaptionCore = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
