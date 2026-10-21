/* Tab 1: Captioned. Image tree, viewer with crop, same-name caption txt, logger. window.CaptionTab */
(function () {
  "use strict";
  const C = window.CaptionCore, FS = window.CaptionFS, UI = window.CaptionUI;
  const { $ } = UI;
  const MIME = { png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", webp: "image/webp" };

  function init(el) {
    const side = el.querySelector(".side");
    const pairs = new Map(); // folder node -> pairFolder() result (entries are updated in place)
    const pairsOf = n => { if (!pairs.has(n)) pairs.set(n, C.pairFolder(n.files.map(f => f.name))); return pairs.get(n); };
    const fileOf = (n, name) => n.files.find(f => f.name === name).handle;
    let root = null;
    let cur = null; // { node, entry, eol, saved, url }

    // ---- logger ----
    function log(level, msg) {
      const box = $("capLog"), line = document.createElement("div");
      line.className = "ll " + level;
      line.textContent = `${new Date().toTimeString().slice(0, 8)} ${level === "ok" ? "✓" : level === "err" ? "✕" : "·"} ${msg}`;
      box.append(line);
      while (box.childElementCount > 200) box.firstElementChild.remove();
      box.scrollTop = box.scrollHeight;
    }
    $("capLogClear").onclick = () => { $("capLog").innerHTML = ""; };

    // ---- tree ----
    const isDirty = () => !!cur && !$("capEd").disabled && $("capEd").value !== cur.saved;
    const tr = UI.tree($("capTree"), {
      folder: n => ({ hidden: !C.anyImage(n) }),
      leaves: n => pairsOf(n).map(e => ({
        key: (n.path ? n.path + "/" : "") + e.image, label: e.image, entry: e,
        cls: e.caption ? "" : "muted", icon: `<span class="dot${e.caption ? "" : " no"}"></span>`,
      })),
      canLeave: () => UI.confirmLeave(isDirty, save),
      onSelect: r => show(r.node, r.leaf.entry),
    });
    function summary() {
      let imgs = 0, txt = 0;
      (function walk(n) { for (const e of pairsOf(n)) { imgs++; if (e.caption) txt++; } n.dirs.forEach(walk); })(root);
      $("capSummary").textContent = `${imgs} ảnh · ${txt} có txt`;
      return { imgs, txt };
    }

    // ---- viewer and crop ----
    const view = window.CaptionViewer.create($("capViewer"), $("capImg"), $("capRect"), $("capSize"),
      st => { $("capZoom").textContent = Math.round(st.zoom * 100) + "%"; });
    let cropOn = false;
    function setCrop(on) {
      cropOn = on && !!cur;
      view.setCrop(cropOn);
      $("capCrop").setAttribute("aria-pressed", String(cropOn));
      $("capCropBar").hidden = !cropOn;
    }
    $("capZoomIn").onclick = () => view.zoomBy(1.25);
    $("capZoomOut").onclick = () => view.zoomBy(1 / 1.25);
    $("capFit").onclick = () => view.fit();
    $("capCrop").onclick = () => setCrop(!cropOn);
    $("capCropCancel").onclick = () => setCrop(false);
    $("capCropApply").onclick = applyCrop;
    document.addEventListener("keydown", e => {
      if (e.key === "Escape" && cropOn && !el.hidden && !document.querySelector("dialog[open]")) setCrop(false);
    });

    async function applyCrop() {
      const r = view.rect();
      if (!cur || !r) { log("err", "Khung crop trống"); return; }
      const name = cur.entry.image;
      const ok = await UI.ask(`Ghi đè ${name}? Không hoàn tác được.`, [{ id: "ok", label: "Ghi đè", kind: "primary" }, { id: "cancel", label: "Huỷ" }]);
      if (ok !== "ok") return;
      const fh = fileOf(cur.node, name);
      const type = MIME[name.split(".").pop().toLowerCase()];
      try {
        const file = await fh.getFile();
        const bmp = await createImageBitmap(file);
        const cv = document.createElement("canvas");
        cv.width = r.w;
        cv.height = r.h;
        cv.getContext("2d").drawImage(bmp, r.x, r.y, r.w, r.h, 0, 0, r.w, r.h);
        bmp.close();
        const blob = await new Promise((res, rej) => cv.toBlob(b => (b ? res(b) : rej(new Error("không mã hoá được ảnh"))), type, 0.95));
        let bytes = new Uint8Array(await blob.arrayBuffer());
        if (type === "image/png") bytes = C.copyPngText(new Uint8Array(await file.arrayBuffer()), bytes);
        await FS.writeFile(fh, bytes);
        log("ok", `Crop ${r.w}×${r.h} ${name}` + (type === "image/png" ? ", giữ metadata PNG" : ""));
        setCrop(false);
        await showImage();
      } catch (e) { log("err", `Không crop được ${name}: ${e.message}`); }
    }

    async function showImage() {
      const my = cur;
      try {
        const file = await fileOf(my.node, my.entry.image).getFile();
        if (cur !== my) return;
        if (my.url) URL.revokeObjectURL(my.url);
        my.url = URL.createObjectURL(file);
        const { w, h } = await view.load(my.url);
        if (cur !== my) return;
        $("capImgName").textContent = `${my.entry.image} · ${w}×${h}`;
        $("capHint").hidden = true;
      } catch (e) { log("err", `Không đọc được ${my.entry.image}: ${e.message}`); }
    }

    // ---- caption editor ----
    const txtName = entry => entry.caption || C.baseName(entry.image) + ".txt";
    function refreshDirty() { $("capDirty").hidden = !isDirty(); }
    $("capEd").addEventListener("input", refreshDirty);

    async function show(node, entry) {
      setCrop(false);
      if (cur && cur.url) URL.revokeObjectURL(cur.url);
      const my = cur = { node, entry, eol: "\n", saved: "", url: null };
      const ed = $("capEd");
      ed.disabled = true;
      ed.value = "";
      $("capTxtName").textContent = txtName(entry);
      refreshDirty();
      showImage();
      if (entry.caption) {
        try {
          const t = await FS.readText(fileOf(node, entry.caption));
          if (cur !== my) return;
          my.eol = C.detectEol(t);
          my.saved = C.toEol(t, "\n");
        } catch (e) {
          log("err", `Không đọc được ${entry.caption}: ${e.message}`);
          return; // editor stays disabled so an unread file is never overwritten
        }
      }
      if (cur !== my) return;
      ed.value = my.saved;
      ed.disabled = false;
      refreshDirty();
    }

    async function save() {
      if (!cur || $("capEd").disabled) return false;
      if (!isDirty()) return true;
      const text = $("capEd").value, name = txtName(cur.entry), isNew = !cur.entry.caption;
      let fh;
      try { fh = await FS.writeText(cur.node.handle, name, C.toEol(text, cur.eol)); }
      catch (e) { log("err", `Không lưu được ${name}: ${e.message}`); return false; }
      cur.saved = text;
      refreshDirty();
      if (isNew) {
        cur.node.files.push({ name, handle: fh });
        cur.entry.caption = name;
        tr.render();
        summary();
        log("ok", `Đã tạo ${name}`);
      } else log("ok", `Đã lưu ${name}`);
      return true;
    }
    $("capSave").onclick = save;

    // ---- folder ----
    async function open(h) {
      if (!(await UI.confirmLeave(isDirty, save))) return;
      side.querySelector(".dirname").value = h.name;
      setCrop(false);
      if (cur && cur.url) URL.revokeObjectURL(cur.url);
      cur = null;
      view.clear();
      $("capHint").hidden = false;
      $("capImgName").textContent = "";
      $("capTxtName").textContent = "";
      $("capEd").value = "";
      $("capEd").disabled = true;
      refreshDirty();
      $("capSummary").textContent = "Đang quét…";
      root = await FS.scanDir(h, (p, e) => log("err", `Bỏ qua ${p}: ${e.message}`));
      pairs.clear();
      tr.setRoot(root);
      const s = summary();
      log("info", `Nạp ${h.name}: ${s.imgs} ảnh, ${s.txt} txt`);
    }

    UI.folderRow(side, "dir.caption", open);
    return { open, isDirty, save, log };
  }

  window.CaptionTab = { init };
})();
