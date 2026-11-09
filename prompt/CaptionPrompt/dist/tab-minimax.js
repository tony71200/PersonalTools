/* Tab 2: MiniMax H3. Image + its _H3_ prompt split into two editable sections. window.MiniMaxTab */
(function () {
  "use strict";
  const C = window.CaptionCore, FS = window.CaptionFS, UI = window.CaptionUI;
  const { $, esc, toast } = UI;

  const tag = (text, nsfw) => `<span class="tag${nsfw ? " nsfw" : ""}">${esc(text)}</span>`;
  const tagOf = list => list.length === 1
    ? tag(list[0].rating, list[0].rating === "nsfw")
    : tag(`${list.length} bản`, list.some(h => h.rating === "nsfw"));

  function init(el) {
    const side = el.querySelector(".side");
    const pairs = new Map(); // folder node -> pairFolder() result
    const pairsOf = n => { if (!pairs.has(n)) pairs.set(n, C.pairFolder(n.files.map(f => f.name))); return pairs.get(n); };
    const fileOf = (n, name) => n.files.find(f => f.name === name).handle;
    let root = null;
    let cur = null;          // { node, entry, v, handle, split, url }
    let saved = ["", ""];    // editor texts as last loaded or saved

    const isDirty = () => !!(cur && cur.split) && ($("mmEd1").value !== saved[0] || $("mmEd2").value !== saved[1]);

    const tr = UI.tree($("mmTree"), {
      folder: n => ({ hidden: !C.anyImage(n) }),
      leaves: n => pairsOf(n).map(e => ({
        key: (n.path ? n.path + "/" : "") + e.image, label: e.image, entry: e,
        cls: e.h3.length ? "hl" : "muted", aside: e.h3.length ? tagOf(e.h3) : "",
      })),
      canLeave: () => UI.confirmLeave(isDirty, save),
      onSelect: r => show(r.node, r.leaf.entry),
    });

    function refresh() {
      $("mmDirty").hidden = !isDirty();
      $("mmCount1").textContent = $("mmEd1").value.length + " ký tự";
      $("mmCount2").textContent = $("mmEd2").value.length + " ký tự";
    }
    function resetRight(msg) {
      if (cur && cur.url) URL.revokeObjectURL(cur.url);
      cur = null;
      saved = ["", ""];
      $("mmImg").removeAttribute("src");
      $("mmVarWrap").hidden = true;
      $("mmTag").innerHTML = "";
      $("mmName").textContent = "";
      $("mmSave").disabled = true;
      $("mmWarn").hidden = true;
      $("mmBody").hidden = true;
      $("mmEmpty").textContent = msg;
      $("mmEmpty").hidden = false;
      refresh();
    }

    async function show(node, entry) {
      resetRight("Ảnh này chưa có file H3");
      $("mmName").textContent = entry.image;
      if (!entry.h3.length) return;
      const my = cur = { node, entry, v: 0, handle: null, split: null, url: null };
      $("mmVar").innerHTML = entry.h3.map((h, i) => `<option value="${i}">${esc(h.name)}</option>`).join("");
      $("mmVarWrap").hidden = entry.h3.length < 2;
      $("mmEmpty").hidden = true;
      $("mmBody").hidden = false;
      $("mmSave").disabled = false;
      try {
        const file = await fileOf(node, entry.image).getFile();
        if (cur !== my) return;
        my.url = URL.createObjectURL(file);
        $("mmImg").src = my.url;
      } catch (e) { toast(`Không đọc được ${entry.image}: ${e.message}`); }
      await loadVariant(0);
    }

    async function loadVariant(i) {
      const my = cur, h = my.entry.h3[i];
      let text;
      try { text = await FS.readText(fileOf(my.node, h.name)); }
      catch (e) { toast(`Không đọc được ${h.name}: ${e.message}`); return; }
      if (cur !== my) return;
      my.v = i;
      my.handle = fileOf(my.node, h.name);
      my.split = C.splitH3(text);
      saved = C.h3Bodies(my.split);
      $("mmEd1").value = saved[0];
      $("mmEd2").value = saved[1];
      $("mmEd2").disabled = !my.split.recognized;
      $("mmWarn").hidden = my.split.recognized;
      $("mmVar").value = String(i);
      $("mmTag").innerHTML = tagOf([h]);
      refresh();
    }

    async function save() {
      if (!cur || !cur.split) return false;
      if (!isDirty()) return true;
      const name = cur.entry.h3[cur.v].name;
      const text = C.setH3Bodies(cur.split, $("mmEd1").value, $("mmEd2").value);
      try { await FS.writeFile(cur.handle, text); }
      catch (e) { toast(`Không lưu được ${name}: ${e.message}`); return false; }
      cur.split = C.splitH3(text);
      saved = [$("mmEd1").value, $("mmEd2").value];
      refresh();
      toast(`Đã lưu ${name}`);
      return true;
    }

    async function copy(ed, btn) {
      try { await navigator.clipboard.writeText(ed.value); }
      catch (e) { ed.select(); document.execCommand("copy"); }
      btn.textContent = "Đã copy";
      setTimeout(() => { btn.textContent = "Copy"; }, 1500);
      toast("Đã copy");
    }

    $("mmVar").addEventListener("change", async e => {
      const i = +e.target.value;
      if (!(await UI.confirmLeave(isDirty, save))) { e.target.value = String(cur.v); return; }
      loadVariant(i);
    });
    $("mmEd1").addEventListener("input", refresh);
    $("mmEd2").addEventListener("input", refresh);
    $("mmCopy1").onclick = () => copy($("mmEd1"), $("mmCopy1"));
    $("mmCopy2").onclick = () => copy($("mmEd2"), $("mmCopy2"));
    $("mmSave").onclick = save;

    function summary() {
      let imgs = 0, files = 0;
      (function walk(n) {
        for (const e of pairsOf(n)) if (e.h3.length) { imgs++; files += e.h3.length; }
        n.dirs.forEach(walk);
      })(root);
      $("mmSummary").textContent = `${imgs} ảnh có H3 · ${files} file txt`;
    }
    async function open(h) {
      if (!(await UI.confirmLeave(isDirty, save))) return;
      side.querySelector(".dirname").value = h.name;
      resetRight("Chọn một ảnh ở cây bên trái");
      $("mmSummary").textContent = "Đang quét…";
      root = await FS.scanDir(h, (p, e) => toast(`Bỏ qua ${p}: ${e.message}`));
      pairs.clear();
      tr.setRoot(root);
      summary();
    }

    UI.folderRow(side, "dir.minimax", open);
    return { open, isDirty, save };
  }

  window.MiniMaxTab = { init };
})();
