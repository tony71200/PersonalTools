/* CaptionPrompt file access: File System Access API, plus handles remembered in IndexedDB. window.CaptionFS */
(function () {
  "use strict";
  const C = window.CaptionCore;
  const DB = "captionPrompt", STORE = "handles";

  function openDb() {
    return new Promise((res, rej) => {
      const r = indexedDB.open(DB, 1);
      r.onupgradeneeded = () => r.result.createObjectStore(STORE);
      r.onsuccess = () => res(r.result);
      r.onerror = () => rej(r.error);
    });
  }
  async function idb(mode, fn) {
    const db = await openDb();
    try {
      return await new Promise((res, rej) => {
        const req = fn(db.transaction(STORE, mode).objectStore(STORE));
        req.onsuccess = () => res(req.result);
        req.onerror = () => rej(req.error);
      });
    } finally { db.close(); }
  }
  const remember = (key, handle) => idb("readwrite", s => s.put(handle, key));
  const recall = key => idb("readonly", s => s.get(key));

  const pickDir = () => window.showDirectoryPicker({ mode: "readwrite" });
  const pickFile = async opts => (await window.showOpenFilePicker(opts))[0];
  const createFile = opts => window.showSaveFilePicker(opts);

  async function ensurePermission(handle, mode = "readwrite") {
    if (!handle.queryPermission) return true; // OPFS handles (used in checks) need no permission
    if ((await handle.queryPermission({ mode })) === "granted") return true;
    return (await handle.requestPermission({ mode })) === "granted";
  }

  async function scanDir(handle, onError, path = "") {
    const node = { name: handle.name, path, handle, dirs: [], files: [] };
    try {
      for await (const [name, h] of handle.entries()) {
        if (h.kind === "directory") {
          if (!name.startsWith(".")) node.dirs.push(await scanDir(h, onError, path ? path + "/" + name : name));
        } else node.files.push({ name, handle: h });
      }
    } catch (e) { if (onError) onError(path || handle.name, e); }
    node.dirs.sort((a, b) => C.naturalCompare(a.name, b.name));
    node.files.sort((a, b) => C.naturalCompare(a.name, b.name));
    return node;
  }

  async function readText(fileHandle) { return (await fileHandle.getFile()).text(); } // UTF-8, BOM dropped
  async function writeFile(fileHandle, data) {
    const w = await fileHandle.createWritable();
    try { await w.write(data); await w.close(); }
    catch (e) { await w.abort().catch(() => {}); throw e; }
  }
  async function writeText(dirHandle, name, text) {
    const fh = await dirHandle.getFileHandle(name, { create: true });
    await writeFile(fh, text);
    return fh;
  }

  window.CaptionFS = { remember, recall, pickDir, pickFile, createFile, ensurePermission, scanDir, readText, writeFile, writeText };
})();
