// Run: node test_core.mjs   (from prompt/CaptionPrompt)
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const C = createRequire(import.meta.url)("./dist/core.js");

// --- names ---
for (const n of ["a.png", "a.PNG", "b.jpg", "c.JPEG", "d.webp"]) assert.equal(C.isImage(n), true, n);
for (const n of ["a.gif", "a.txt", "png", ".png"]) assert.equal(C.isImage(n), false, n);
assert.equal(C.baseName("a.b.png"), "a.b");
assert.equal(C.baseName("noext"), "noext");
assert.deepEqual(["img10.png", "img2.png", "img1.png"].sort(C.naturalCompare), ["img1.png", "img2.png", "img10.png"]);

// --- parseH3Name ---
assert.deepEqual(C.parseH3Name("A_H3_sfw.txt"), { base: "A", rating: "sfw", suffix: "" });
assert.deepEqual(C.parseH3Name("A_H3_NSFW_v2.txt"), { base: "A", rating: "nsfw", suffix: "v2" });
assert.deepEqual(C.parseH3Name("ZImage_2026_06_06_101818_60_00001_H3_nsfw_v2.txt"),
  { base: "ZImage_2026_06_06_101818_60_00001", rating: "nsfw", suffix: "v2" });
for (const n of ["A_H3.txt", "A_H3_safe.txt", "A.txt", "A_H3_sfw.md"]) assert.equal(C.parseH3Name(n), null, n);

// --- pairFolder ---
{
  const p = C.pairFolder(["B.png", "b.txt", "b_H3_nsfw_v2.txt", "B_H3_sfw.txt", "a.jpg", "orphan.txt", "x_H3_sfw.txt", "notes.md"]);
  assert.deepEqual(p.map(e => e.image), ["a.jpg", "B.png"]);
  assert.equal(p[0].caption, null);
  assert.deepEqual(p[0].h3, []);
  assert.equal(p[1].caption, "b.txt");                       // caption matched case-insensitively
  assert.deepEqual(p[1].h3.map(h => h.name), ["b_H3_nsfw_v2.txt", "B_H3_sfw.txt"]);
  assert.deepEqual(p[1].h3[0], { name: "b_H3_nsfw_v2.txt", rating: "nsfw", suffix: "v2" });
}
// the plain variant sorts before its _v2
assert.deepEqual(C.pairFolder(["A.png", "A_H3_nsfw_v2.txt", "A_H3_sfw.txt", "A_H3_nsfw.txt"])[0].h3.map(h => h.name),
  ["A_H3_nsfw.txt", "A_H3_nsfw_v2.txt", "A_H3_sfw.txt"]);
// an H3 file is never taken as a caption
assert.equal(C.pairFolder(["A.png", "A_H3_sfw.txt"])[0].caption, null);

// --- folder tree ---
const T = (name, path, files, dirs = []) => ({ name, path, files: files.map(n => ({ name: n })), dirs });
const tree = T("PostIG", "", ["readme.txt"], [
  T("day_52_1", "day_52_1", [], [T("Ryo", "day_52_1/Ryo", ["a.png", "a_H3_sfw.txt"])]),
  T("day_53_1", "day_53_1", [], [T("Ryo", "day_53_1/Ryo", ["a.png", "b.jpg", "c.webp"])]),
  T("empty", "empty", []),
]);
assert.equal(C.imageCount(tree.dirs[1].dirs[0]), 3);
assert.equal(C.imageCount(tree), 0);
assert.equal(C.anyImage(tree), true);
assert.equal(C.anyImage(tree.dirs[2]), false);
assert.equal(C.countLabel(tree), "0 ảnh · 3 folder");
assert.equal(C.countLabel(tree.dirs[0].dirs[0]), "1 ảnh");
{
  const f = C.filterTree(tree, 2);
  assert.deepEqual([...f.matched], ["day_52_1/Ryo"]);
  assert.deepEqual([...f.visible].sort(), ["", "day_52_1", "day_52_1/Ryo"]);
  assert.equal(f.total, 6);
}
assert.deepEqual([...C.filterTree(tree, 3).matched].sort(), ["day_52_1/Ryo", "day_53_1/Ryo"]); // i === N matches
assert.equal(C.filterTree(tree, 0).matched.size, 0); // 0-image folders never match

console.log("core tests passed");
