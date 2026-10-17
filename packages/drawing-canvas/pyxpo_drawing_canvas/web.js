// pyxpo-drawing-canvas in the browser and the desktop window: an HTML canvas driven by pointer events.
// The page loads this file after app.js (see pyxpoPage in app.js).
(function () {
  "use strict";

  function css(argb) {
    const a = ((argb >>> 24) & 255) / 255;
    return "rgba(" + ((argb >>> 16) & 255) + "," + ((argb >>> 8) & 255) + "," + (argb & 255) + "," + a + ")";
  }

  // Same curve on every platform: quadratic segments through the midpoints, a dot for a single point.
  function trace(ctx, s, k) {
    const p = s.points, n = p.length / 2;
    ctx.globalCompositeOperation = s.tool === "eraser" ? "destination-out" : "source-over";
    ctx.strokeStyle = ctx.fillStyle = css(s.color);
    ctx.lineWidth = s.width * k;
    ctx.lineCap = ctx.lineJoin = "round";
    ctx.beginPath();
    if (n === 1) {
      ctx.arc(p[0] * k, p[1] * k, s.width * k / 2, 0, Math.PI * 2);
      ctx.fill();
      return;
    }
    ctx.moveTo(p[0] * k, p[1] * k);
    for (let i = 1; i < n - 1; i++) {
      ctx.quadraticCurveTo(p[2 * i] * k, p[2 * i + 1] * k, (p[2 * i] + p[2 * i + 2]) / 2 * k, (p[2 * i + 1] + p[2 * i + 3]) / 2 * k);
    }
    ctx.lineTo(p[2 * n - 2] * k, p[2 * n - 1] * k);
    ctx.stroke();
  }

  function inkBounds(c) {
    const w = c.width, h = c.height;
    if (!w || !h) return null;
    const d = c.getContext("2d").getImageData(0, 0, w, h).data;
    let x0 = w, y0 = h, x1 = -1, y1 = -1;
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        if (d[(y * w + x) * 4 + 3]) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
      }
    }
    return x1 < 0 ? null : { x: x0, y: y0, w: x1 - x0 + 1, h: y1 - y0 + 1 };
  }

  // The dev tools show the app in a device body scaled with a CSS transform. getBoundingClientRect is in screen px
  // there, but layout (and what the app draws in) is in CSS px, so size and pointer math use the unscaled size.
  function layoutRect(el) {
    const r = el.getBoundingClientRect();
    let sx = el.offsetWidth ? r.width / el.offsetWidth : 1, sy = el.offsetHeight ? r.height / el.offsetHeight : 1;
    if (Math.abs(sx - 1) < 0.01) sx = 1;   // keep fractional sizes when nothing is scaled
    if (Math.abs(sy - 1) < 0.01) sy = 1;
    return { left: r.left, top: r.top, width: r.width / sx, height: r.height / sy, sx, sy };
  }

  function makeCanvas(el, emit) {
    const canvas = document.createElement("canvas");
    canvas.style.cssText = "position:absolute;left:0;top:0;width:100%;height:100%;touch-action:none;display:block";
    el.style.overflow = "hidden";
    el.appendChild(canvas);
    const ctx = canvas.getContext("2d");
    const done = document.createElement("canvas");  // committed strokes at screen resolution
    const props = { stroke_color: 0xff000000, stroke_width: 4, tool: "pen", background_color: 0xffffffff, enabled: true };
    let strokes = [], history = [], future = [], live = null, pointer = null, frame = 0, dpr = 1, w = 0, h = 0;

    function state() {
      emit("change", { stroke_count: strokes.length, can_undo: history.length > 0, can_redo: future.length > 0 });
    }
    function rebuild() {
      const c = done.getContext("2d");
      c.setTransform(1, 0, 0, 1, 0, 0);
      c.clearRect(0, 0, done.width, done.height);
      for (const s of strokes) trace(c, s, dpr);
      paint();
    }
    function paint() {
      frame = 0;
      ctx.globalCompositeOperation = "source-over";
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(done, 0, 0);
      if (live) trace(ctx, live, dpr);
    }
    function schedule() { if (!frame) frame = requestAnimationFrame(paint); }
    function resize() {
      const r = layoutRect(el);
      dpr = window.devicePixelRatio || 1;
      w = r.width; h = r.height;
      canvas.width = done.width = Math.max(1, Math.round(w * dpr));
      canvas.height = done.height = Math.max(1, Math.round(h * dpr));
      rebuild();
    }
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    function point(e) {
      const r = layoutRect(canvas);
      return [Math.round((e.clientX - r.left) / r.sx * 10) / 10, Math.round((e.clientY - r.top) / r.sy * 10) / 10];
    }
    function add(e) {
      const evs = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
      for (const ev of evs.length ? evs : [e]) {
        const [x, y] = point(ev), p = live.points, n = p.length;
        if (n && Math.abs(p[n - 2] - x) < 0.5 && Math.abs(p[n - 1] - y) < 0.5) continue;
        p.push(x, y);
      }
      schedule();
    }
    canvas.addEventListener("pointerdown", (e) => {
      if (!props.enabled || pointer !== null || (e.pointerType === "mouse" && e.button !== 0)) return;
      pointer = e.pointerId;
      canvas.setPointerCapture(e.pointerId);
      live = { tool: props.tool, color: props.stroke_color, width: props.stroke_width, points: [] };
      add(e);
      e.preventDefault();
    });
    canvas.addEventListener("pointermove", (e) => { if (e.pointerId === pointer) add(e); });
    function end(e, keep) {
      if (e.pointerId !== pointer) return;
      pointer = null;
      const s = live;
      live = null;
      if (keep && s.points.length) {
        strokes.push(s);
        history.push({ kind: "stroke", stroke: s });
        future = [];
        trace(done.getContext("2d"), s, dpr);
        state();
      }
      paint();
    }
    canvas.addEventListener("pointerup", (e) => end(e, true));
    canvas.addEventListener("pointercancel", (e) => end(e, false));

    return {
      update(p) {
        Object.assign(props, p);
        if ("background_color" in p) el.style.backgroundColor = css(props.background_color);
      },
      dispose() { ro.disconnect(); if (frame) cancelAnimationFrame(frame); },
      undo() {
        const op = history.pop();
        if (!op) return;
        if (op.kind === "stroke") strokes.pop(); else strokes = op.strokes;
        future.push(op);
        rebuild(); state();
      },
      redo() {
        const op = future.pop();
        if (!op) return;
        if (op.kind === "stroke") strokes.push(op.stroke); else strokes = [];
        history.push(op);
        rebuild(); state();
      },
      clear() {
        if (!strokes.length) return;
        history.push({ kind: "clear", strokes });
        future = [];
        strokes = [];
        rebuild(); state();
      },
      getStrokes() { return strokes.map((s) => ({ tool: s.tool, color: s.color, width: s.width, points: s.points.slice() })); },
      setStrokes(list) {
        strokes = list.map((s) => ({ tool: s.tool, color: s.color, width: s.width, points: s.points.slice() }));
        history = []; future = [];
        rebuild(); state();
      },
      toImage(o) {
        const k = o.scale || dpr;
        const ink = document.createElement("canvas");
        ink.width = Math.max(1, Math.round(w * k));
        ink.height = Math.max(1, Math.round(h * k));
        const ic = ink.getContext("2d", { willReadFrequently: true });
        for (const s of strokes) trace(ic, s, k);
        let r = { x: 0, y: 0, w: ink.width, h: ink.height };
        if (o.trim) {
          r = inkBounds(ink);
          if (!r) return null;
          const pad = Math.round((o.padding || 0) * k);
          r = { x: r.x - pad, y: r.y - pad, w: r.w + 2 * pad, h: r.h + 2 * pad };
        }
        const out = document.createElement("canvas");
        out.width = r.w; out.height = r.h;
        const oc = out.getContext("2d");
        const jpg = o.format === "jpg";
        if (jpg) { oc.fillStyle = "#ffffff"; oc.fillRect(0, 0, r.w, r.h); }  // no alpha in a jpg
        if (o.background) { oc.fillStyle = css(props.background_color); oc.fillRect(0, 0, r.w, r.h); }
        oc.drawImage(ink, -r.x, -r.y);
        const url = out.toDataURL(jpg ? "image/jpeg" : "image/png", jpg ? o.quality : undefined);
        return { base64: url.slice(url.indexOf(",") + 1), width: r.w, height: r.h, x: r.x / k, y: r.y / k };
      },
    };
  }

  pyxpoPage.defineView("PxDrawingCanvas", makeCanvas);
  pyxpoPage.defineModule("DrawingCanvas", (method, args, page) => {
    const v = page.view(args[0]);
    if (!v) throw new Error("The DrawingCanvas is not mounted");
    switch (method) {
      case "undo": return v.undo();
      case "redo": return v.redo();
      case "clear": return v.clear();
      case "getStrokes": return v.getStrokes();
      case "setStrokes": return v.setStrokes(args[1] || []);
      case "toImage": return v.toImage(args[1] || {});
      default: throw new Error("DrawingCanvas has no method " + method);
    }
  });
})();
