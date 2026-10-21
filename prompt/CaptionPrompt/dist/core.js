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

  // ---- exports ----
  const api = {
    isImage, baseName, naturalCompare, parseH3Name, pairFolder, imageCount, anyImage, countLabel, filterTree,
    detectEol, toEol, splitH3, joinH3, h3Bodies, setH3Bodies,
  };
  root.CaptionCore = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
