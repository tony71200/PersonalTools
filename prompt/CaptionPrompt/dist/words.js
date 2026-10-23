/* Snippet chips under the caption editor, and the word-list dialog backed by a linked JSON file. window.CaptionWords */
(function () {
  "use strict";
  const C = window.CaptionCore, FS = window.CaptionFS, UI = window.CaptionUI;
  const { $, esc, toast } = UI;
  const JSON_TYPES = [{ description: "JSON", accept: { "application/json": [".json"] } }];

  function init({ editor, log }) {
    let words = C.DEFAULT_WORDS.map(w => ({ ...w }));
    let handle = null; // linked JSON file, set only after it was read

    // ---- chips ----
    function renderChips() {
      $("capChips").innerHTML = words.map((w, i) => `<button class="chip" data-i="${i}" title="${esc(w.text)}">${esc(w.label)}</button>`).join("");
    }
    $("capChips").addEventListener("mousedown", e => { if (e.target.closest(".chip")) e.preventDefault(); }); // keep the caret in the editor
    $("capChips").addEventListener("click", e => {
      const b = e.target.closest(".chip");
      if (!b || editor.disabled) return;
      editor.focus();
      const s = editor.selectionStart, end = editor.selectionEnd;
      // execCommand keeps the insert on the editor's undo stack (Ctrl+Z) and fires "input".
      document.execCommand("insertText", false, C.padSnippet(editor.value.slice(0, s), editor.value.slice(end), words[+b.dataset.i].text));
    });

    // ---- JSON file ----
    function note(html) { $("capWordsNote").innerHTML = html; $("capWordsNote").hidden = !html; }
    async function load(h) {
      try {
        words = C.parseWords(await FS.readText(h));
        handle = h;
        note("");
        log("ok", `Đọc ${h.name}: ${words.length} từ`);
      } catch (e) { log("err", `${h.name}: ${e.message}`); }
      renderChips();
      renderList();
    }
    async function write() {
      if (!handle) return;
      try { await FS.writeFile(handle, C.wordsJson(words)); log("ok", `Đã ghi ${handle.name}`); }
      catch (e) { log("err", `Không ghi được ${handle.name}: ${e.message}`); }
    }
    async function link(h) {
      FS.remember("wordsFile", h).catch(() => {});
      await load(h);
    }

    // ---- dialog ----
    function renderList() {
      const off = handle ? "" : " disabled";
      $("wordsFileInfo").textContent = handle
        ? `Đã liên kết: ${handle.name}. Thay đổi được ghi vào file ngay.`
        : "Chưa liên kết file JSON. Liên kết hoặc tạo file mới để sửa danh sách.";
      $("wordsList").innerHTML = words.map((w, i) =>
        `<div class="wordrow" data-i="${i}"><input data-f="label" value="${esc(w.label)}" aria-label="Nhãn"${off}>` +
        `<input data-f="text" value="${esc(w.text)}" aria-label="Nội dung"${off}>` +
        `<button class="btn icon danger" data-del="${i}" aria-label="Xoá ${esc(w.label)}"${off}>&times;</button></div>`).join("");
      for (const id of ["wordsNewLabel", "wordsNewText", "wordsAdd", "wordsImport"]) $(id).disabled = !handle;
    }
    $("capWordsOpen").onclick = () => { renderList(); $("wordsDlg").showModal(); };
    $("wordsClose").onclick = () => $("wordsDlg").close();
    $("wordsDlg").addEventListener("click", e => { if (e.target === $("wordsDlg")) $("wordsDlg").close(); }); // backdrop
    $("wordsList").addEventListener("change", e => {
      const row = e.target.closest(".wordrow"), f = e.target.dataset.f;
      if (!row || !f) return;
      const w = words[+row.dataset.i], v = e.target.value.trim();
      if (!v) { e.target.value = w[f]; toast("Không để trống nhãn hoặc nội dung"); return; }
      w[f] = v;
      renderChips();
      write();
    });
    $("wordsList").addEventListener("click", e => {
      const i = e.target.closest("[data-del]")?.dataset.del;
      if (i === undefined) return;
      words.splice(+i, 1);
      renderChips();
      renderList();
      write();
    });
    $("wordsAdd").onclick = () => {
      const label = $("wordsNewLabel").value.trim(), text = $("wordsNewText").value.trim();
      if (!label || !text) { toast("Nhập cả nhãn và nội dung"); return; }
      const m = C.mergeWords(words, [{ label, text }]);
      if (!m.added) { toast(`Nhãn "${label}" đã có`); return; }
      words = m.words;
      $("wordsNewLabel").value = $("wordsNewText").value = "";
      renderChips();
      renderList();
      write();
      $("wordsNewLabel").focus();
    };
    $("wordsNewText").addEventListener("keydown", e => { if (e.key === "Enter") $("wordsAdd").click(); });
    $("wordsLink").onclick = async () => {
      let h;
      try { h = await FS.pickFile({ types: JSON_TYPES }); } catch (e) { return; } // cancelled
      if (await FS.ensurePermission(h)) link(h);
    };
    $("wordsCreate").onclick = async () => {
      let h;
      try { h = await FS.createFile({ suggestedName: "caption_words.json", types: JSON_TYPES }); } catch (e) { return; }
      try { await FS.writeFile(h, C.wordsJson(words)); }
      catch (e) { log("err", `Không tạo được ${h.name}: ${e.message}`); return; }
      link(h);
    };
    $("wordsImport").onclick = async () => {
      let h;
      try { h = await FS.pickFile({ types: JSON_TYPES }); } catch (e) { return; }
      try {
        const m = C.mergeWords(words, C.parseWords(await FS.readText(h)));
        words = m.words;
        renderChips();
        renderList();
        await write();
        log("ok", `Import: +${m.added}, bỏ qua ${m.skipped}`);
      } catch (e) { log("err", `${h.name}: ${e.message}`); }
    };

    // ---- startup: reopen the remembered file ----
    renderChips();
    (async () => {
      const old = await FS.recall("wordsFile").catch(() => null);
      if (!old) { note("Chưa liên kết file JSON · đang dùng bộ từ mặc định"); return; }
      if (old.queryPermission && (await old.queryPermission({ mode: "readwrite" })) !== "granted") {
        note(`<button class="btn sm" id="capWordsAllow">Cho phép đọc ${esc(old.name)}</button>`);
        $("capWordsAllow").onclick = async () => { if (await FS.ensurePermission(old)) load(old); };
        return;
      }
      load(old);
    })();
  }

  window.CaptionWords = { init };
})();
