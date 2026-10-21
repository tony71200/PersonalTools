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

  // ---- exports ----
  const api = { isImage, baseName, naturalCompare, parseH3Name, pairFolder, imageCount, anyImage, countLabel, filterTree };
  root.CaptionCore = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
