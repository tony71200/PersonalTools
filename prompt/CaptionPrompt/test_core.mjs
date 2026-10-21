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

// --- H3 split / join ---
// Layout 1: plain headings (like day_52_1)
const H3_PLAIN =
  "CHARACTER & SCENE DEFINITION\r\n\r\n" +
  "<Subject 1> A man.\r\n\r\n[reference generation] He smiles.\r\n" +
  "\r\nSHOT STRUCTURE — MINIMAX H3\r\n\r\n" +
  "[SHOT 01 | DURATION: 10s | PRIMARY CAMERA SETUP: close-up]\r\nHe waves.\r\n\r\n" +
  "[SHOT 02 | DURATION: 10s | PRIMARY CAMERA SETUP: wide]\r\nHe leaves.\r\n";
// Layout 2: markdown headings with --- (like day_53_1 sfw / nsfw_v2)
const H3_MD =
  "# CHARACTER & SCENE DEFINITION\r\n\r\n" +
  "**summary:**\r\n\r\nA man dances.\r\n" +
  "\r\n---\r\n\r\n# SHOT STRUCTURE — MINIMAX H3\r\n\r\n" +
  "[SHOT 01 | DURATION: 8s | PRIMARY CAMERA SETUP: dolly]\r\n\r\nStep one.\r\n\r\n---\r\n\r\n" +
  "[SHOT 02 | DURATION: 7s | PRIMARY CAMERA SETUP: medium]\r\n\r\nStep two.\r\n";
// Layout 3: no headings (like day_56_1/Rennoir2)
const H3_BARE =
  "subject_definitions:\r\n\r\nA swimmer.\r\n\r\nnon_diegetic_music:\r\n\r\nNONE\r\n" +
  "\r\n" +
  "[SHOT 01 | DURATION: 12s | PRIMARY CAMERA SETUP: mirror]\r\n\r\nsubject_definitions:\r\n\r\nSame swimmer.\r\n\r\nnon_diegetic_music:\r\n" +
  "\r\n";

assert.equal(C.detectEol(H3_PLAIN), "\r\n");
assert.equal(C.detectEol("a\nb"), "\n");
assert.equal(C.toEol("a\r\nb\nc\rd", "\r\n"), "a\r\nb\r\nc\r\nd");
assert.equal(C.toEol("a\r\nb", "\n"), "a\nb");

{
  const s = C.splitH3(H3_PLAIN);
  assert.equal(s.recognized, true);
  assert.equal(s.eol, "\r\n");
  assert.deepEqual(s.parts, [
    "CHARACTER & SCENE DEFINITION\r\n\r\n",
    "<Subject 1> A man.\r\n\r\n[reference generation] He smiles.\r\n",
    "\r\nSHOT STRUCTURE — MINIMAX H3\r\n\r\n",
    "[SHOT 01 | DURATION: 10s | PRIMARY CAMERA SETUP: close-up]\r\nHe waves.\r\n\r\n[SHOT 02 | DURATION: 10s | PRIMARY CAMERA SETUP: wide]\r\nHe leaves.\r\n",
    "",
  ]);
  assert.deepEqual(C.h3Bodies(s), [
    "<Subject 1> A man.\n\n[reference generation] He smiles.",
    "[SHOT 01 | DURATION: 10s | PRIMARY CAMERA SETUP: close-up]\nHe waves.\n\n[SHOT 02 | DURATION: 10s | PRIMARY CAMERA SETUP: wide]\nHe leaves.",
  ]);
}
{
  const s = C.splitH3(H3_MD);
  assert.deepEqual(s.parts.slice(0, 3), [
    "# CHARACTER & SCENE DEFINITION\r\n\r\n",
    "**summary:**\r\n\r\nA man dances.\r\n",
    "\r\n---\r\n\r\n# SHOT STRUCTURE — MINIMAX H3\r\n\r\n",
  ]);
  assert.ok(s.parts[3].includes("\r\n---\r\n"), "--- between shots stays in body 2");
}
{
  const s = C.splitH3(H3_BARE);
  assert.equal(s.recognized, true);
  assert.equal(s.parts[0], "");
  assert.equal(s.parts[1], "subject_definitions:\r\n\r\nA swimmer.\r\n\r\nnon_diegetic_music:\r\n\r\nNONE\r\n");
  assert.equal(s.parts[2], "\r\n");
  assert.ok(s.parts[3].startsWith("[SHOT 01"));
  assert.equal(s.parts[4], "\r\n");
}
// round trip, byte for byte, for every layout
for (const t of [H3_PLAIN, H3_MD, H3_BARE]) {
  const s = C.splitH3(t);
  assert.equal(C.joinH3(s.parts), t);
  const [b1, b2] = C.h3Bodies(s);
  assert.equal(C.setH3Bodies(s, b1, b2), t);
}
// editing one body changes only that body
{
  const s = C.splitH3(H3_PLAIN);
  const out = C.setH3Bodies(s, "<Subject 1> A woman.\n\n[reference generation] She smiles.", C.h3Bodies(s)[1]);
  assert.equal(out, H3_PLAIN.replace("A man.", "A woman.").replace("He smiles.", "She smiles."));
}
{
  const s = C.splitH3(H3_MD);
  const out = C.setH3Bodies(s, C.h3Bodies(s)[0], C.h3Bodies(s)[1].replace("Step two.", "Step 2."));
  assert.equal(out, H3_MD.replace("Step two.", "Step 2."));
}
// a file with no final newline stays without one
{
  const t = "CHARACTER & SCENE DEFINITION\nA\nSHOT STRUCTURE\n[SHOT 01]\nB";
  const s = C.splitH3(t);
  assert.equal(C.setH3Bodies(s, ...C.h3Bodies(s)), t);
  assert.equal(C.setH3Bodies(s, "A", "[SHOT 01]\nC"), "CHARACTER & SCENE DEFINITION\nA\nSHOT STRUCTURE\n[SHOT 01]\nC");
}
// unrecognized text: everything in body 1, still round-trips
{
  const t = "Just a note.\r\nSecond line.\r\n\r\n";
  const s = C.splitH3(t);
  assert.equal(s.recognized, false);
  assert.deepEqual(s.parts, ["", "Just a note.\r\nSecond line.\r\n", "", "", "\r\n"]);
  assert.equal(C.setH3Bodies(s, ...C.h3Bodies(s)), t);
  assert.equal(C.joinH3(C.splitH3("").parts), "");
}
console.log("core tests passed");
