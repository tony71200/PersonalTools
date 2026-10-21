/* CaptionPrompt shared UI: toast, ask dialog, unsaved-changes guard, folder row, tree. window.CaptionUI */
(function () {
  "use strict";
  const FS = window.CaptionFS;
  const $ = id => document.getElementById(id);
  const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  let toastTimer = null;
  function toast(msg) {
    $("toastMsg").textContent = msg;
    $("toast").classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => $("toast").classList.remove("show"), 4000);
  }

  // Resolves with the clicked button's id, or "cancel" on Esc.
  // Button clicks resolve at once: the dialog's "close" event can lag while the page is hidden.
  function ask(msg, buttons) {
    return new Promise(res => {
      const d = $("askDlg");
      let done = false;
      const finish = v => { if (!done) { done = true; res(v); } };
      $("askMsg").textContent = msg;
      $("askBtns").innerHTML = buttons.map(b => `<button class="btn ${b.kind || ""}" value="${esc(b.id)}">${esc(b.label)}</button>`).join("");
      $("askBtns").onclick = e => { const b = e.target.closest("button"); if (b) finish(b.value); };
      d.returnValue = "";
      d.onclose = () => finish(d.returnValue || "cancel");
      d.showModal();
    });
  }

  // true = go ahead (saved or discarded), false = stay.
  async function confirmLeave(isDirty, save) {
    if (!isDirty()) return true;
    const r = await ask("Có thay đổi chưa lưu.", [
      { id: "save", label: "Lưu", kind: "primary" }, { id: "discard", label: "Bỏ thay đổi" }, { id: "cancel", label: "Huỷ" }]);
    if (r === "save") return save();
    return r === "discard";
  }

  // Wires the folder picker and the "Mở lại" button inside one tab's side panel.
  async function folderRow(side, key, onRoot) {
    const reopen = side.querySelector(".reopen");
    side.querySelector(".pick").onclick = async () => {
      let h;
      try { h = await FS.pickDir(); }
      catch (e) { if (e.name !== "AbortError") toast("Không mở được thư mục: " + e.message); return; }
      FS.remember(key, h).catch(() => {});
      reopen.hidden = true;
      onRoot(h);
    };
    const old = await FS.recall(key).catch(() => null);
    if (!old) return;
    reopen.textContent = `Mở lại "${old.name}"`;
    reopen.hidden = false;
    reopen.onclick = async () => {
      if (!(await FS.ensurePermission(old))) { toast("Chưa được cấp quyền đọc thư mục."); return; }
      reopen.hidden = true;
      onRoot(old);
    };
  }

  // Folder tree. Rows are rebuilt on every render; selection is kept by key.
  function tree(el, o) {
    const want = o.selectable || "leaf";
    const closed = new Set();
    let root = null, sel = null, rows = [];

    function build() {
      rows = [];
      if (!root) return;
      (function walk(n, depth) {
        const f = o.folder ? o.folder(n) : {};
        if (depth > 0 && f.hidden) return;
        rows.push({ key: "d:" + n.path, node: n, depth, folder: true, label: n.name, cls: f.cls || "", aside: f.aside || "" });
        if (closed.has(n.path)) return;
        n.dirs.forEach(c => walk(c, depth + 1));
        for (const l of o.leaves ? o.leaves(n) : []) {
          rows.push({ key: "f:" + l.key, node: n, depth: depth + 1, folder: false, leaf: l,
            label: l.label, cls: l.cls || "", aside: l.aside || "", icon: l.icon || "" });
        }
      })(root, 0);
    }
    function render() {
      build();
      el.innerHTML = rows.map((r, i) =>
        `<div class="trow ${r.folder ? "folder" : "leaf"} ${r.cls}${r.key === sel ? " sel" : ""}" data-i="${i}" style="--d:${r.depth}" role="treeitem"` +
        (r.folder ? ` aria-expanded="${!closed.has(r.node.path)}">` : ">") +
        (r.folder ? `<span class="tw">${closed.has(r.node.path) ? "▸" : "▾"}</span>` : r.icon) +
        `<span class="nm" title="${esc(r.label)}">${esc(r.label)}</span>` +
        (r.aside ? `<span class="aside">${r.aside}</span>` : "") + `</div>`).join("");
      el.querySelector(".sel")?.scrollIntoView({ block: "nearest" });
    }
    const pickable = r => (want === "folder" ? r.folder : !r.folder);
    async function choose(r) {
      if (r.key === sel) return;
      if (o.canLeave && !(await o.canLeave())) return;
      sel = r.key;
      render();
      o.onSelect(r);
    }
    function toggle(path, open = closed.has(path)) {
      if (open) closed.delete(path); else closed.add(path);
      render();
    }
    el.addEventListener("click", e => {
      const row = e.target.closest(".trow");
      if (!row) return;
      const r = rows[+row.dataset.i];
      if (r.folder && (want !== "folder" || e.target.closest(".tw"))) { toggle(r.node.path); return; }
      if (pickable(r)) choose(r);
    });
    el.addEventListener("keydown", e => {
      const list = rows.filter(pickable);
      const i = list.findIndex(r => r.key === sel);
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const next = list[e.key === "ArrowDown" ? Math.min(list.length - 1, i + 1) : Math.max(0, i - 1)];
        if (next) choose(next);
      } else if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && i >= 0 && list[i].folder) {
        e.preventDefault();
        toggle(list[i].node.path, e.key === "ArrowRight");
      }
    });
    return {
      setRoot(r) { root = r; sel = null; closed.clear(); render(); },
      render,
      clear() { sel = null; render(); },
    };
  }

  window.CaptionUI = { $, esc, toast, ask, confirmLeave, folderRow, tree };
})();
