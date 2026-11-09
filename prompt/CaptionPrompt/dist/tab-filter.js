/* Tab 3: Filt and Find. Folder tree with image counts, filter by count, lazy thumbnail grid. window.FilterTab */
(function () {
  "use strict";
  const C = window.CaptionCore, FS = window.CaptionFS, UI = window.CaptionUI;
  const { $, esc, toast } = UI;

  function init(el) {
    const side = el.querySelector(".side");
    let root = null, total = 0;
    let filt = null;            // { matched, visible, total, max } while a filter is on
    let urls = [], io = null;   // thumbnail object URLs and their observer

    const tr = UI.tree($("fltTree"), {
      selectable: "folder",
      folder(n) {
        const label = esc(C.countLabel(n));
        if (!filt) return { aside: `<span class="tag cnt">${label}</span>` };
        if (filt.matched.has(n.path)) return { aside: `<span class="tag">${label}</span>` };
        return { hidden: !filt.visible.has(n.path), cls: "muted", aside: `<span class="tag cnt">${label}</span>` };
      },
      onSelect: r => showFolder(r.node),
    });

    function clearGrid() {
      if (io) io.disconnect();
      io = null;
      urls.forEach(u => URL.revokeObjectURL(u));
      urls = [];
      $("fltGrid").innerHTML = "";
    }
    function resetRight() {
      clearGrid();
      $("fltPath").textContent = "";
      $("fltCount").textContent = "";
      $("fltEmpty").textContent = "Chọn một folder ở cây bên trái";
      $("fltEmpty").hidden = false;
    }
    function showFolder(n) {
      clearGrid();
      const imgs = n.files.filter(f => C.isImage(f.name));
      $("fltPath").textContent = [root.name, n.path].filter(Boolean).join(" / ");
      $("fltCount").textContent = imgs.length + " ảnh";
      $("fltEmpty").textContent = "Folder này không có ảnh";
      $("fltEmpty").hidden = imgs.length > 0;
      $("fltGrid").innerHTML = imgs.map((f, i) =>
        `<figure class="thumb" data-i="${i}"><div class="ph"><img alt=""></div><figcaption title="${esc(f.name)}">${esc(f.name)}</figcaption></figure>`).join("");
      const mine = io = new IntersectionObserver(entries => {
        for (const en of entries) {
          if (!en.isIntersecting) continue;
          mine.unobserve(en.target);
          imgs[+en.target.dataset.i].handle.getFile().then(file => {
            if (io !== mine) return; // folder changed while loading
            const u = URL.createObjectURL(file);
            urls.push(u);
            en.target.querySelector("img").src = u;
          }).catch(() => en.target.classList.add("bad"));
        }
      }, { root: el.querySelector(".main"), rootMargin: "300px" });
      $("fltGrid").querySelectorAll(".thumb").forEach(t => mine.observe(t));
    }

    function updateSummary() {
      $("fltSummary").textContent = !root ? "" : filt ? `Khớp ${filt.matched.size} / ${filt.total} folder` : `${total} folder`;
      $("fltNone").hidden = !filt || filt.matched.size > 0;
      $("fltNone").textContent = filt ? `Không có folder nào có 1 đến ${filt.max} ảnh` : "";
    }
    function runFilter() {
      const n = Number($("fltN").value);
      if (!Number.isInteger(n) || n < 1) { toast("Nhập một số nguyên từ 1 trở lên"); $("fltN").focus(); return; }
      if (!root) { toast("Chọn thư mục trước"); return; }
      filt = { ...C.filterTree(root, n), max: n };
      updateSummary();
      tr.render();
    }
    $("fltGo").onclick = runFilter;
    $("fltN").addEventListener("keydown", e => { if (e.key === "Enter") runFilter(); });
    $("fltClear").onclick = () => { filt = null; updateSummary(); tr.render(); };

    async function open(h) {
      side.querySelector(".dirname").value = h.name;
      resetRight();
      $("fltSummary").textContent = "Đang quét…";
      root = await FS.scanDir(h, (p, e) => toast(`Bỏ qua ${p}: ${e.message}`));
      total = C.filterTree(root, 0).total; // filterTree counts every folder it walks
      filt = null;
      tr.setRoot(root);
      updateSummary();
    }

    UI.folderRow(side, "dir.filter", open);
    return { open };
  }

  window.FilterTab = { init };
})();
