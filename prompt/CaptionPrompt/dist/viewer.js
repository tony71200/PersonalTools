/* Image viewer: wheel zoom around the cursor, drag to pan, crop rectangle with 8 handles. window.CaptionViewer */
(function () {
  "use strict";
  const MIN = 0.1, MAX = 8;
  const norm = (a, b, c, d) => ({ x: Math.min(a, c), y: Math.min(b, d), w: Math.abs(c - a), h: Math.abs(d - b) });

  function create(box, img, rectEl, sizeEl, onChange) {
    let W = 0, H = 0;          // image size in pixels
    let s = 1, tx = 0, ty = 0; // screen = t + image * s
    let crop = null;           // { x, y, w, h } in image pixels while crop mode is on
    let cropOn = false, drag = null;

    function rect() {
      if (!crop) return null;
      const x = Math.round(crop.x), y = Math.round(crop.y);
      const w = Math.min(W - x, Math.round(crop.w)), h = Math.min(H - y, Math.round(crop.h));
      return w >= 1 && h >= 1 ? { x, y, w, h } : null;
    }
    function apply() {
      img.style.transform = `translate(${tx}px, ${ty}px) scale(${s})`;
      rectEl.hidden = !(cropOn && crop);
      if (cropOn && crop) {
        Object.assign(rectEl.style, { left: tx + crop.x * s + "px", top: ty + crop.y * s + "px", width: crop.w * s + "px", height: crop.h * s + "px" });
        const r = rect();
        sizeEl.textContent = r ? `${r.w}×${r.h}` : "0×0";
      }
      if (onChange) onChange({ zoom: s });
    }
    function fit() {
      if (!W) return;
      const bw = box.clientWidth, bh = box.clientHeight;
      s = Math.min(bw / W, bh / H);
      tx = (bw - W * s) / 2;
      ty = (bh - H * s) / 2;
      apply();
    }
    function zoomAt(f, mx, my) {
      const ns = Math.min(MAX, Math.max(MIN, s * f));
      tx = mx - (mx - tx) * (ns / s);
      ty = my - (my - ty) * (ns / s);
      s = ns;
      apply();
    }
    const zoomBy = f => { if (W) zoomAt(f, box.clientWidth / 2, box.clientHeight / 2); };
    function toImg(e) {
      const b = box.getBoundingClientRect();
      return { x: Math.min(W, Math.max(0, (e.clientX - b.left - tx) / s)), y: Math.min(H, Math.max(0, (e.clientY - b.top - ty) / s)) };
    }

    box.addEventListener("wheel", e => {
      if (!W) return;
      e.preventDefault();
      const b = box.getBoundingClientRect();
      zoomAt(e.deltaY < 0 ? 1.1 : 1 / 1.1, e.clientX - b.left, e.clientY - b.top);
    }, { passive: false });

    box.addEventListener("pointerdown", e => {
      if (!W || e.target.closest(".cropbar")) return;
      if (!cropOn || e.button === 1) drag = { kind: "pan", x: e.clientX, y: e.clientY, tx, ty };
      else if (e.button !== 0) return;
      else if (e.target.dataset.h) drag = { kind: "resize", h: e.target.dataset.h, start: { ...crop } };
      else if (rectEl.contains(e.target)) drag = { kind: "move", p: toImg(e), start: { ...crop } };
      else { const p = toImg(e); drag = { kind: "new", p }; crop = { x: p.x, y: p.y, w: 0, h: 0 }; }
      box.setPointerCapture(e.pointerId);
      box.classList.toggle("panning", drag.kind === "pan");
      e.preventDefault();
    });
    box.addEventListener("pointermove", e => {
      if (!drag) return;
      if (drag.kind === "pan") {
        tx = drag.tx + e.clientX - drag.x;
        ty = drag.ty + e.clientY - drag.y;
      } else {
        const p = toImg(e), c = drag.start;
        if (drag.kind === "new") crop = norm(drag.p.x, drag.p.y, p.x, p.y);
        else if (drag.kind === "move") {
          crop = { ...c, x: Math.min(W - c.w, Math.max(0, c.x + p.x - drag.p.x)), y: Math.min(H - c.h, Math.max(0, c.y + p.y - drag.p.y)) };
        } else {
          let l = c.x, t = c.y, r = c.x + c.w, b = c.y + c.h;
          if (drag.h.includes("w")) l = p.x;
          if (drag.h.includes("e")) r = p.x;
          if (drag.h.includes("n")) t = p.y;
          if (drag.h.includes("s")) b = p.y;
          crop = norm(l, t, r, b);
        }
      }
      apply();
    });
    const end = () => { drag = null; box.classList.remove("panning"); };
    box.addEventListener("pointerup", end);
    box.addEventListener("pointercancel", end);

    function load(url) {
      return new Promise((res, rej) => {
        img.onload = () => { W = img.naturalWidth; H = img.naturalHeight; fit(); res({ w: W, h: H }); };
        img.onerror = () => rej(new Error("không giải mã được ảnh"));
        img.src = url;
      });
    }
    function clear() { W = H = 0; crop = null; img.removeAttribute("src"); apply(); }
    function setCrop(on) {
      cropOn = on && W > 0;
      crop = cropOn ? { x: W * 0.1, y: H * 0.1, w: W * 0.8, h: H * 0.8 } : null; // start with a centered 80% box
      box.classList.toggle("cropping", cropOn);
      apply();
    }
    return { load, clear, fit, zoomBy, setCrop, rect };
  }

  window.CaptionViewer = { create };
})();
