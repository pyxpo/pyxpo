// pyxpo-whiteboard in the browser and the desktop window: an HTML canvas driven by pointer events.
// The page loads this file after app.js (see pyxpoPage in app.js).
(function () {
  "use strict";

  const SHAPES = ["line", "arrow", "rect", "ellipse", "triangle", "star", "diamond", "hexagon", "heart"];
  const SPACING = 24;   // page pattern spacing in CSS px

  // Dashes: 1.5 x width on, 2.5 x width off, before the round caps grow each dash by a width.
  function dash(ctx, e, k) { ctx.setLineDash(e.dash ? [1.5 * e.width * k, 2.5 * e.width * k] : []); }

  function css(argb) {
    const a = ((argb >>> 24) & 255) / 255;
    return "rgba(" + ((argb >>> 16) & 255) + "," + ((argb >>> 8) & 255) + "," + (argb & 255) + "," + a + ")";
  }

  // Same curve on every platform: quadratic segments through the midpoints, a dot for a single point.
  function stroke(ctx, s, k) {
    const p = s.points, n = p.length / 2;
    ctx.globalCompositeOperation = s.tool === "eraser" ? "destination-out" : "source-over";
    ctx.strokeStyle = ctx.fillStyle = css(s.tool === "eraser" ? 0xff000000 : s.color);
    ctx.lineWidth = s.width * k;
    ctx.lineCap = ctx.lineJoin = "round";
    ctx.beginPath();
    if (n === 1) {
      ctx.arc(p[0] * k, p[1] * k, s.width * k / 2, 0, Math.PI * 2);
      ctx.fill();
      return;
    }
    if (s.tool !== "eraser") dash(ctx, s, k);
    ctx.moveTo(p[0] * k, p[1] * k);
    for (let i = 1; i < n - 1; i++) {
      ctx.quadraticCurveTo(p[2 * i] * k, p[2 * i + 1] * k, (p[2 * i] + p[2 * i + 2]) / 2 * k, (p[2 * i + 1] + p[2 * i + 3]) / 2 * k);
    }
    ctx.lineTo(p[2 * n - 2] * k, p[2 * n - 1] * k);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  function polygon(ctx, pts, k) {
    for (let j = 0; j < pts.length; j += 2) {
      if (j) ctx.lineTo(pts[j] * k, pts[j + 1] * k); else ctx.moveTo(pts[j] * k, pts[j + 1] * k);
    }
    ctx.closePath();
  }

  // The heart curve x = 16 sin^3 t, y = 13 cos t - 5 cos 2t - 2 cos 3t - cos 4t, fitted to the box.
  function heart(lx, ly, hx, hy) {
    const cx = (lx + hx) / 2, w = (hx - lx) / 2, h = hy - ly, pts = [];
    for (let j = 0; j < 48; j++) {
      const t = 2 * Math.PI * j / 48;
      const x = 16 * Math.pow(Math.sin(t), 3);
      const y = -(13 * Math.cos(t) - 5 * Math.cos(2 * t) - 2 * Math.cos(3 * t) - Math.cos(4 * t));
      pts.push(cx + w * x / 16, ly + h * (y + 12) / 29);
    }
    return pts;
  }

  // Arrow head lines: 28 degrees off the shaft, max(12, 3.5 x width) long, at most half the shaft.
  function arrowHead(e, side) {
    const dx = e.x1 - e.x0, dy = e.y1 - e.y0, n = Math.hypot(dx, dy) || 1;
    const size = Math.min(Math.max(12, e.width * 3.5), n * 0.5);
    const a = Math.atan2(dy, dx) + Math.PI + side * 28 * Math.PI / 180;
    return [e.x1 + size * Math.cos(a), e.y1 + size * Math.sin(a)];
  }

  function shapePath(ctx, e, k) {
    const lx = Math.min(e.x0, e.x1), ly = Math.min(e.y0, e.y1), hx = Math.max(e.x0, e.x1), hy = Math.max(e.y0, e.y1);
    const cx = (lx + hx) / 2, cy = (ly + hy) / 2, rx = (hx - lx) / 2, ry = (hy - ly) / 2;
    ctx.beginPath();
    switch (e.shape) {
      case "line":
      case "arrow":
        ctx.moveTo(e.x0 * k, e.y0 * k);
        ctx.lineTo(e.x1 * k, e.y1 * k);
        if (e.shape === "arrow") {
          for (const side of [-1, 1]) {
            const h = arrowHead(e, side);
            ctx.moveTo(e.x1 * k, e.y1 * k);
            ctx.lineTo(h[0] * k, h[1] * k);
          }
        }
        return false;
      case "rect":
        ctx.rect(lx * k, ly * k, (hx - lx) * k, (hy - ly) * k);
        return true;
      case "ellipse":
        ctx.ellipse(cx * k, cy * k, rx * k, ry * k, 0, 0, Math.PI * 2);
        return true;
      case "triangle":
        ctx.moveTo(cx * k, ly * k);
        ctx.lineTo(hx * k, hy * k);
        ctx.lineTo(lx * k, hy * k);
        ctx.closePath();
        return true;
      case "star":
        for (let j = 0; j < 10; j++) {
          const a = -Math.PI / 2 + Math.PI * j / 5, r = j % 2 ? 0.45 : 1;
          const x = (cx + rx * r * Math.cos(a)) * k, y = (cy + ry * r * Math.sin(a)) * k;
          if (j) ctx.lineTo(x, y); else ctx.moveTo(x, y);
        }
        ctx.closePath();
        return true;
      case "diamond":
        polygon(ctx, [cx, ly, hx, cy, cx, hy, lx, cy], k);
        return true;
      case "hexagon": {
        const pts = [];
        for (let j = 0; j < 6; j++) {
          const a = -Math.PI / 2 + Math.PI * j / 3;
          pts.push(cx + rx * Math.cos(a), cy + ry * Math.sin(a));
        }
        polygon(ctx, pts, k);
        return true;
      }
      case "heart":
        polygon(ctx, heart(lx, ly, hx, hy), k);
        return true;
    }
    return false;
  }

  // Fill inside first, then the outline on top.
  function shape(ctx, e, k) {
    ctx.globalCompositeOperation = "source-over";
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    const closed = shapePath(ctx, e, k);
    if (closed && e.fill >>> 24) { ctx.fillStyle = css(e.fill); ctx.fill(); }
    if (e.width > 0) {
      ctx.strokeStyle = css(e.color); ctx.lineWidth = e.width * k;
      dash(ctx, e, k);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }

  // The page under the ink (screen only): grid lines, dots or ruled lines every SPACING px.
  function pattern(ctx, kind, color, k, cw, ch) {
    if (!kind || kind === "none") return;
    const step = SPACING * k;
    ctx.save();
    ctx.globalCompositeOperation = "source-over";
    ctx.setLineDash([]);
    ctx.strokeStyle = ctx.fillStyle = css(color);
    ctx.lineWidth = Math.max(1, k);
    ctx.beginPath();
    if (kind === "dots") {
      const r = 1.3 * k;
      for (let y = step; y < ch; y += step) {
        for (let x = step; x < cw; x += step) { ctx.moveTo(x + r, y); ctx.arc(x, y, r, 0, Math.PI * 2); }
      }
      ctx.fill();
    } else {
      for (let y = step; y < ch; y += step) { ctx.moveTo(0, Math.round(y) + 0.5); ctx.lineTo(cw, Math.round(y) + 0.5); }
      if (kind === "grid") {
        for (let x = step; x < cw; x += step) { ctx.moveTo(Math.round(x) + 0.5, 0); ctx.lineTo(Math.round(x) + 0.5, ch); }
      }
      ctx.stroke();
    }
    ctx.restore();
  }

  // Bucket fill on the canvas pixels: the 4-connected region of pixels within `tol` of the tapped one (in
  // premultiplied color) gets the fill color, and a 1px ring around it gets the fill under its own color, so the
  // fill meets anti-aliased lines without a gap. Returns false when nothing would change.
  function flood(c, e, k, tol) {
    const w = c.width, h = c.height;
    const sx = Math.floor(e.x * k), sy = Math.floor(e.y * k);
    if (sx < 0 || sy < 0 || sx >= w || sy >= h) return false;
    const g = c.getContext("2d", { willReadFrequently: true });
    g.setTransform(1, 0, 0, 1, 0, 0);
    const img = g.getImageData(0, 0, w, h), d = img.data;
    const pm = new Int32Array(w * h * 4);   // premultiplied copy for matching
    for (let i = 0; i < w * h; i++) {
      const a = d[4 * i + 3];
      pm[4 * i] = d[4 * i] * a / 255; pm[4 * i + 1] = d[4 * i + 1] * a / 255; pm[4 * i + 2] = d[4 * i + 2] * a / 255; pm[4 * i + 3] = a;
    }
    const fa = (e.color >>> 24) & 255, fr = (e.color >>> 16) & 255, fg = (e.color >>> 8) & 255, fb = e.color & 255;
    const s = 4 * (sy * w + sx);
    const s0 = pm[s], s1 = pm[s + 1], s2 = pm[s + 2], s3 = pm[s + 3];
    if (Math.abs(fr * fa / 255 - s0) <= 2 && Math.abs(fg * fa / 255 - s1) <= 2 && Math.abs(fb * fa / 255 - s2) <= 2 && Math.abs(fa - s3) <= 2) return false;
    const match = (i) => Math.abs(pm[4 * i] - s0) <= tol && Math.abs(pm[4 * i + 1] - s1) <= tol &&
      Math.abs(pm[4 * i + 2] - s2) <= tol && Math.abs(pm[4 * i + 3] - s3) <= tol;
    const mask = new Uint8Array(w * h);   // 1 region, 2 ring
    const stack = [sx, sy];
    while (stack.length) {
      const y = stack.pop(), x0 = stack.pop();
      let x = x0;
      const row = y * w;
      if (mask[row + x] === 1 || !match(row + x)) continue;
      while (x > 0 && mask[row + x - 1] !== 1 && match(row + x - 1)) x--;
      let up = false, down = false;
      for (; x < w && mask[row + x] !== 1 && match(row + x); x++) {
        mask[row + x] = 1;
        if (y > 0) {
          const m = mask[row - w + x] !== 1 && match(row - w + x);
          if (m && !up) stack.push(x, y - 1);
          up = m;
        }
        if (y < h - 1) {
          const m = mask[row + w + x] !== 1 && match(row + w + x);
          if (m && !down) stack.push(x, y + 1);
          down = m;
        }
      }
    }
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const i = y * w + x;
        if (mask[i] === 1) continue;
        if ((x > 0 && mask[i - 1] === 1) || (x < w - 1 && mask[i + 1] === 1) ||
            (y > 0 && mask[i - w] === 1) || (y < h - 1 && mask[i + w] === 1)) mask[i] = 2;
      }
    }
    for (let i = 0; i < w * h; i++) {
      const m = mask[i];
      if (!m) continue;
      if (m === 1) { d[4 * i] = fr; d[4 * i + 1] = fg; d[4 * i + 2] = fb; d[4 * i + 3] = fa; continue; }
      // ring: existing over fill, premultiplied
      const ea = pm[4 * i + 3] / 255, out = ea + fa / 255 * (1 - ea);
      if (out <= 0) continue;
      const mix = (pe, f) => Math.round((pe + f * fa / 255 * (1 - ea)) / out);
      d[4 * i] = mix(pm[4 * i], fr); d[4 * i + 1] = mix(pm[4 * i + 1], fg); d[4 * i + 2] = mix(pm[4 * i + 2], fb);
      d[4 * i + 3] = Math.round(out * 255);
    }
    g.putImageData(img, 0, 0);
    return true;
  }

  function draw(c, e, k, tol) {
    if (e.type === "fill") return flood(c, e, k, tol);
    const ctx = c.getContext("2d", { willReadFrequently: true });
    if (e.type === "shape") shape(ctx, e, k); else stroke(ctx, e, k);
    ctx.globalCompositeOperation = "source-over";
    return true;
  }

  function copy(e) {
    const t = e.type || "stroke";
    let out = null;
    if (t === "stroke") out = { type: "stroke", tool: e.tool || "pen", color: e.color >>> 0, width: e.width, points: e.points.slice() };
    if (t === "shape") out = { type: "shape", shape: e.shape, color: e.color >>> 0, width: e.width, fill: (e.fill || 0) >>> 0, x0: e.x0, y0: e.y0, x1: e.x1, y1: e.y1 };
    if (out) {
      if (e.dash && out.tool !== "eraser") out.dash = true;
      return out;
    }
    return { type: "fill", x: e.x, y: e.y, color: e.color >>> 0 };
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
    if (Math.abs(sx - 1) < 0.01) sx = 1;
    if (Math.abs(sy - 1) < 0.01) sy = 1;
    return { left: r.left, top: r.top, width: r.width / sx, height: r.height / sy, sx, sy };
  }

  function makeBoard(el, emit) {
    const canvas = document.createElement("canvas");
    canvas.style.cssText = "position:absolute;left:0;top:0;width:100%;height:100%;touch-action:none;display:block";
    el.style.overflow = "hidden";
    el.appendChild(canvas);
    const ctx = canvas.getContext("2d");
    const done = document.createElement("canvas");  // committed elements at screen resolution, transparent background
    const layer = document.createElement("canvas");  // done plus a live eraser stroke, over a page pattern
    const props = { tool: "pen", color: 0xff000000, width: 4, fill_color: 0, background_color: 0xffffffff, enabled: true,
      fill_tolerance: 32, dash: false, pattern: "none", pattern_color: 0x33808080 };
    let elements = [], history = [], future = [], live = null, pointer = null, frame = 0, dpr = 1, w = 0, h = 0;

    function state() {
      emit("change", { element_count: elements.length, can_undo: history.length > 0, can_redo: future.length > 0 });
    }
    function rebuild() {
      const c = done.getContext("2d", { willReadFrequently: true });
      c.setTransform(1, 0, 0, 1, 0, 0);
      c.globalCompositeOperation = "source-over";
      c.clearRect(0, 0, done.width, done.height);
      for (const e of elements) draw(done, e, dpr, props.fill_tolerance);
      paint();
    }
    function paint() {
      frame = 0;
      ctx.globalCompositeOperation = "source-over";
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      pattern(ctx, props.pattern, props.pattern_color, dpr, canvas.width, canvas.height);
      if (live && live.tool === "eraser" && props.pattern !== "none") {
        // the live eraser must cut the ink only, not the page under it
        layer.width = canvas.width; layer.height = canvas.height;
        const lc = layer.getContext("2d");
        lc.drawImage(done, 0, 0);
        stroke(lc, live, dpr);
        ctx.drawImage(layer, 0, 0);
      } else {
        ctx.drawImage(done, 0, 0);
        if (live) { if (live.type === "shape") shape(ctx, live, dpr); else stroke(ctx, live, dpr); }
      }
      ctx.globalCompositeOperation = "source-over";
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

    function commit(e) {
      if (!draw(done, e, dpr, props.fill_tolerance)) return false;
      elements.push(e);
      history.push({ kind: "add", element: e });
      future = [];
      return true;
    }
    function point(e) {
      const r = layoutRect(canvas);
      return [Math.round((e.clientX - r.left) / r.sx * 10) / 10, Math.round((e.clientY - r.top) / r.sy * 10) / 10];
    }
    // The color under a point: the ink pixel over the background color, opaque.
    function pick(pt) {
      const bg = props.background_color >>> 0;
      const x = Math.min(done.width - 1, Math.max(0, Math.floor(pt[0] * dpr)));
      const y = Math.min(done.height - 1, Math.max(0, Math.floor(pt[1] * dpr)));
      const d = done.getContext("2d", { willReadFrequently: true }).getImageData(x, y, 1, 1).data;
      const a = d[3] / 255;
      const mix = (c, b) => Math.round(c * a + b * (1 - a));
      return ((0xff << 24) | (mix(d[0], (bg >>> 16) & 255) << 16) | (mix(d[1], (bg >>> 8) & 255) << 8) | mix(d[2], bg & 255)) >>> 0;
    }
    function add(e) {
      if (live.type === "shape") {
        const [x, y] = point(e);
        live.x1 = x; live.y1 = y;
      } else {
        const evs = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
        for (const ev of evs.length ? evs : [e]) {
          const [x, y] = point(ev), p = live.points, n = p.length;
          if (n && Math.abs(p[n - 2] - x) < 0.5 && Math.abs(p[n - 1] - y) < 0.5) continue;
          p.push(x, y);
        }
      }
      schedule();
    }
    canvas.addEventListener("pointerdown", (e) => {
      if (!props.enabled || pointer !== null || (e.pointerType === "mouse" && e.button !== 0)) return;
      e.preventDefault();
      const tool = props.tool;
      if (tool === "picker") {
        emit("pick", { color: pick(point(e)) });
        return;
      }
      emit("draw_start", { tool });
      if (tool === "fill") {
        const [x, y] = point(e);
        commit({ type: "fill", x, y, color: props.color >>> 0 });
        paint();
        state();
        return;
      }
      pointer = e.pointerId;
      canvas.setPointerCapture(e.pointerId);
      if (SHAPES.includes(tool)) {
        const [x, y] = point(e);
        live = { type: "shape", shape: tool, color: props.color >>> 0, width: props.width, fill: props.fill_color >>> 0, x0: x, y0: y, x1: x, y1: y };
      } else {
        live = { type: "stroke", tool, color: props.color >>> 0, width: props.width, points: [] };
      }
      if (props.dash && tool !== "eraser") live.dash = true;
      add(e);
    });
    canvas.addEventListener("pointermove", (e) => { if (e.pointerId === pointer) add(e); });
    function end(e, keep) {
      if (e.pointerId !== pointer) return;
      pointer = null;
      const s = live;
      live = null;
      if (keep && s) {
        const big = s.type !== "shape" || Math.abs(s.x1 - s.x0) >= 2 || Math.abs(s.y1 - s.y0) >= 2;
        if (big && (s.type === "shape" || s.points.length)) commit(s);
      }
      paint();
      state();
    }
    canvas.addEventListener("pointerup", (e) => end(e, true));
    canvas.addEventListener("pointercancel", (e) => end(e, false));

    return {
      update(p) {
        const tol = props.fill_tolerance;
        Object.assign(props, p);
        if ("background_color" in p) el.style.backgroundColor = css(props.background_color);
        if (props.fill_tolerance !== tol && elements.some((e) => e.type === "fill")) rebuild();
        else if ("pattern" in p || "pattern_color" in p) paint();
      },
      dispose() { ro.disconnect(); if (frame) cancelAnimationFrame(frame); },
      undo() {
        const op = history.pop();
        if (!op) return;
        if (op.kind === "add") elements.pop(); else elements = op.elements;
        future.push(op);
        rebuild(); state();
      },
      redo() {
        const op = future.pop();
        if (!op) return;
        if (op.kind === "add") elements.push(op.element); else elements = [];
        history.push(op);
        rebuild(); state();
      },
      clear() {
        if (!elements.length) return;
        history.push({ kind: "clear", elements });
        future = [];
        elements = [];
        rebuild(); state();
      },
      getElements() { return elements.map(copy); },
      setElements(list) {
        elements = list.map(copy);
        history = []; future = [];
        rebuild(); state();
      },
      toImage(o) {
        const k = o.scale || dpr;
        const ink = document.createElement("canvas");
        ink.width = Math.max(1, Math.round(w * k));
        ink.height = Math.max(1, Math.round(h * k));
        for (const e of elements) draw(ink, e, k, props.fill_tolerance);
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

  pyxpoPage.defineView("PxWhiteboard", makeBoard);
  pyxpoPage.defineModule("Whiteboard", (method, args, page) => {
    const v = page.view(args[0]);
    if (!v) throw new Error("The Whiteboard is not mounted");
    switch (method) {
      case "undo": return v.undo();
      case "redo": return v.redo();
      case "clear": return v.clear();
      case "getElements": return v.getElements();
      case "setElements": return v.setElements(args[1] || []);
      case "toImage": return v.toImage(args[1] || {});
      default: throw new Error("Whiteboard has no method " + method);
    }
  });
})();
