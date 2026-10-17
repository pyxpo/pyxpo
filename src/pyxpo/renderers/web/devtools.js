// pyxpo dev tools: served by `pyxpo run web` only, never part of `pyxpo build web`.
// A round button at the bottom right opens a panel that shows the app in a phone or tablet body (or any size), turns
// it, zooms, switches light/dark and the platform behaviour, and shows the active breakpoint. In a device the page
// behaves like a touch screen: no hover, a round touch cursor, drag to scroll with momentum, hidden scroll bars, the
// device's safe area insets and status bar. app.js and boot.js read the emulated environment from
// window.PYXPO_DEVICE() and re-send it on the `pyxpo-env` event.
(() => {
  "use strict";
  const KEY = "pyxpo.devtools.v1";

  // Sizes in CSS px. ins = safe area insets [top, right, bottom, left] portrait / landscape. sb = status bar height.
  const DEVICES = [
    { id: "iphone-15-pro", name: "iPhone 15 Pro", kind: "phone", os: "ios", w: 393, h: 852, dpr: 3, look: "island",
      ins: [[59, 0, 34, 0], [0, 59, 21, 59]], sb: [54, 0], radius: 55, bezel: 12 },
    { id: "iphone-15-pro-max", name: "iPhone 15 Pro Max", kind: "phone", os: "ios", w: 430, h: 932, dpr: 3,
      look: "island", ins: [[59, 0, 34, 0], [0, 59, 21, 59]], sb: [54, 0], radius: 55, bezel: 12 },
    { id: "iphone-se", name: "iPhone SE", kind: "phone", os: "ios", w: 375, h: 667, dpr: 2, look: "home",
      ins: [[20, 0, 0, 0], [0, 0, 0, 0]], sb: [20, 0], radius: 0, bezel: 14 },
    { id: "pixel-8", name: "Pixel 8", kind: "phone", os: "android", w: 412, h: 915, dpr: 2.625, look: "punch",
      ins: [[32, 0, 24, 0], [24, 0, 24, 32]], sb: [32, 24], radius: 38, bezel: 10 },
    { id: "galaxy-s24", name: "Galaxy S24", kind: "phone", os: "android", w: 360, h: 780, dpr: 3, look: "punch",
      ins: [[32, 0, 24, 0], [24, 0, 24, 32]], sb: [32, 24], radius: 32, bezel: 8 },
    { id: "ipad-mini", name: "iPad mini", kind: "tablet", os: "ios", w: 744, h: 1133, dpr: 2, look: "tablet",
      ins: [[24, 0, 20, 0], [24, 0, 20, 0]], sb: [24, 24], radius: 22, bezel: 20 },
    { id: "ipad-air-11", name: "iPad Air 11\"", kind: "tablet", os: "ios", w: 820, h: 1180, dpr: 2, look: "tablet",
      ins: [[24, 0, 20, 0], [24, 0, 20, 0]], sb: [24, 24], radius: 18, bezel: 20 },
    { id: "ipad-pro-13", name: "iPad Pro 13\"", kind: "tablet", os: "ios", w: 1032, h: 1376, dpr: 2, look: "tablet",
      ins: [[24, 0, 20, 0], [24, 0, 20, 0]], sb: [24, 24], radius: 18, bezel: 18 },
    { id: "galaxy-tab-s9", name: "Galaxy Tab S9", kind: "tablet", os: "android", w: 800, h: 1280, dpr: 2,
      look: "tablet", ins: [[24, 0, 24, 0], [24, 0, 24, 0]], sb: [24, 24], radius: 16, bezel: 18 },
  ];
  const DEFAULT_BP = { xs: 0, sm: 576, md: 768, lg: 992, xl: 1200, xxl: 1400 };
  const ZMIN = 0.2, ZMAX = 3;
  const ZSTEPS = [0.25, 0.33, 0.5, 0.67, 0.75, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3];
  const TOOLS_W = 72;   // side toolbar and its gap
  const PANEL_W = 346;  // panel and its gap: the device moves left of an open panel when the window is wide enough

  const svg = (p, w) => '<svg viewBox="0 0 24 24" width="' + (w || 18) + '" height="' + (w || 18) + '" fill="none" ' +
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + p + "</svg>";
  const I = {
    rotate: svg('<path d="M21 2v6h-6"/><path d="M21 13a9 9 0 1 1-3-7.7L21 8"/>'),
    zin: svg('<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3M11 8v6M8 11h6"/>'),
    zout: svg('<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3M8 11h6"/>'),
    fit: svg('<path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3"/>'),
    sun: svg('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2' +
      'M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'),
    moon: svg('<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>'),
    system: svg('<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/>'),
    back: svg('<path d="M19 12H5M12 19l-7-7 7-7"/>'),
    reload: svg('<path d="M23 4v6h-6"/><path d="M20.5 15a9 9 0 1 1-2.1-9.4L23 10"/>'),
    sliders: svg('<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>'),
    close: svg('<path d="M18 6L6 18M6 6l12 12"/>'),
    minus: svg('<path d="M5 12h14"/>'),
    plus: svg('<path d="M12 5v14M5 12h14"/>'),
    swap: svg('<path d="M17 3l4 4-4 4M21 7H8M7 21l-4-4 4-4M3 17h13"/>'),
    portrait: svg('<rect x="6" y="2" width="12" height="20" rx="2.5"/><path d="M11 18h2"/>'),
    landscape: svg('<rect x="2" y="6" width="20" height="12" rx="2.5"/><path d="M18 11v2"/>'),
    grip: svg('<path d="M21 11L11 21M21 17l-4 4"/>', 16),
  };

  const defaults = {
    mode: "desktop",          // desktop | phone | tablet | custom
    phone: "iphone-15-pro", tablet: "ipad-air-11",
    cw: 390, ch: 844,         // custom size
    landscape: false, zoom: "fit", scheme: "system", platform: "web", frame: true, open: false,
  };
  let st = Object.assign({}, defaults);
  try { Object.assign(st, JSON.parse(localStorage.getItem(KEY) || "{}")); } catch (e) { /* private window */ }
  if (!["desktop", "phone", "tablet", "custom"].includes(st.mode)) st.mode = "desktop";
  function save() { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) { /* ignore */ } }

  const darkMq = window.matchMedia("(prefers-color-scheme: dark)");
  const statusBar = { style: null, hidden: false, background: null };

  function device() {
    if (st.mode === "phone") return DEVICES.find((d) => d.id === st.phone) || DEVICES[0];
    if (st.mode === "tablet") return DEVICES.find((d) => d.id === st.tablet) || DEVICES.find((d) => d.kind === "tablet");
    return null;
  }
  // The emulated screen: {w, h, dpr, ins:[t,r,b,l], sb, dev} or null on desktop.
  function screenInfo() {
    if (st.mode === "desktop") return null;
    const d = device();
    if (!d) {
      const w = clamp(st.cw, 200, 3840), h = clamp(st.ch, 200, 3840);
      return { w, h, dpr: window.devicePixelRatio || 1, ins: [0, 0, 0, 0], sb: 0, dev: null };
    }
    const l = st.landscape ? 1 : 0;
    return { w: l ? d.h : d.w, h: l ? d.w : d.h, dpr: d.dpr, ins: d.ins[l], sb: d.sb[l], dev: d };
  }
  const clamp = (v, a, b) => Math.max(a, Math.min(b, Number(v) || a));
  function scheme() { return st.scheme === "system" ? (darkMq.matches ? "dark" : "light") : st.scheme; }

  // Read by boot.js (first env) and app.js (every env event).
  window.PYXPO_DEVICE = () => {
    const out = { color_scheme: scheme() };
    if (st.platform !== "web") out.os = st.platform;
    const s = screenInfo();
    if (s) {
      out.window = { width: s.w, height: s.h };
      out.screen = { width: s.w, height: s.h };
      out.scale = s.dpr;
      out.insets = s.dev && st.frame ? { top: s.ins[0], right: s.ins[1], bottom: s.ins[2], left: s.ins[3] }
        : { top: 0, right: 0, bottom: 0, left: 0 };
    }
    return out;
  };
  const sendEnv = () => window.dispatchEvent(new Event("pyxpo-env"));

  // -- page styles (the frame lives in the page: #root moves into it) ----------------------------------------------
  const TOUCH_CURSOR = "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='28' height='28'%3E" +
    "%3Ccircle cx='14' cy='14' r='11' fill='rgba(120,120,128,.35)' stroke='rgba(255,255,255,.9)' stroke-width='2'/%3E" +
    "%3C/svg%3E\") 14 14, pointer";
  const css = document.createElement("style");
  css.textContent = `
  #pxd-stage { position: fixed; inset: 0; z-index: 0; display: none; overflow: auto; background: var(--pxd-bg);
    background-image: radial-gradient(var(--pxd-dot) 1px, transparent 1px); background-size: 18px 18px; }
  html.pxd-on #pxd-stage { display: block; }
  html.pxd-on, html.pxd-on body { --pxd-bg: #e9e9ee; --pxd-dot: #d3d3da; }
  @media (prefers-color-scheme: dark) { html.pxd-on, html.pxd-on body { --pxd-bg: #121214; --pxd-dot: #26262b; } }
  #pxd-center { min-width: 100%; min-height: 100%; box-sizing: border-box; padding: 28px 24px 56px;
    display: flex; flex-direction: column; align-items: center; justify-content: center; }
  #pxd-box { position: relative; flex-shrink: 0; }
  #pxd-frame { position: absolute; left: 0; top: 0; transform-origin: 0 0; box-sizing: content-box; }
  #pxd-frame.body { background: #1d1d20; box-shadow: 0 0 0 2px #3a3a3f, 0 0 0 4px #121214, 0 30px 80px rgba(0,0,0,.35); }
  #pxd-frame.body::before, #pxd-frame.body::after { content: ""; position: absolute; background: #2a2a2e; border-radius: 3px; }
  #pxd-frame.phone.body::before { left: -6px; top: 22%; width: 4px; height: 64px; box-shadow: 0 84px 0 #2a2a2e; }
  #pxd-frame.phone.body::after { right: -6px; top: 28%; width: 4px; height: 96px; }
  #pxd-frame.phone.land.body::before { left: 22%; top: -6px; width: 64px; height: 4px; box-shadow: 84px 0 0 #2a2a2e; }
  #pxd-frame.phone.land.body::after { right: auto; top: auto; left: 28%; bottom: -6px; width: 96px; height: 4px; }
  #pxd-frame.tablet.body::before { right: 12%; top: -5px; width: 56px; height: 3px; }
  #pxd-frame.tablet.body::after { right: -5px; top: 10%; width: 3px; height: 48px; }
  #pxd-frame.tablet.land.body::before { right: -5px; top: 12%; width: 3px; height: 56px; }
  #pxd-frame.tablet.land.body::after { right: auto; left: 10%; top: -5px; width: 48px; height: 3px; }
  #pxd-frame.bare { box-shadow: 0 0 0 1px rgba(0,0,0,.15), 0 12px 40px rgba(0,0,0,.18); }
  #pxd-screen { position: relative; overflow: hidden; background: #fff; transform: translateZ(0); isolation: isolate; }
  #pxd-screen > #root { position: absolute; inset: 0; }
  #pxd-screen.dark { background: #000; }
  #pxd-screen.touch, #pxd-screen.touch * { cursor: ${TOUCH_CURSOR} !important; }
  #pxd-screen.touch input, #pxd-screen.touch textarea { cursor: text !important; }
  #pxd-screen.touch .press::after { display: none; }
  #pxd-screen.touch .t { user-select: none; -webkit-user-select: none; }
  #pxd-screen.touch .sv { scrollbar-width: none; }
  #pxd-screen.touch .sv::-webkit-scrollbar { display: none; }
  #pxd-screen #alert, #pxd-screen #lost { position: absolute; }
  .pxd-deco { position: absolute; pointer-events: none; z-index: 99998; }
  .pxd-island { left: 50%; top: 11px; width: 124px; height: 36px; margin-left: -62px; border-radius: 20px; background: #000; }
  .land .pxd-island { left: 11px; top: 50%; width: 36px; height: 124px; margin: -62px 0 0; }
  .pxd-punch { left: 50%; top: 10px; width: 14px; height: 14px; margin-left: -7px; border-radius: 50%; background: #000;
    box-shadow: inset 0 0 0 3px #1a1a1e; }
  .land .pxd-punch { left: 10px; top: 50%; margin: -7px 0 0; }
  .pxd-cam { width: 8px; height: 8px; border-radius: 50%; background: #0c0c10; box-shadow: inset 0 0 0 2px #2b2b33; }
  .pxd-home-btn { width: 48px; height: 48px; border-radius: 50%; box-shadow: inset 0 0 0 2px #3a3a40; }
  .pxd-speaker { width: 56px; height: 6px; border-radius: 3px; background: #0c0c10; }
  .pxd-bar { left: 50%; bottom: 8px; width: 134px; height: 5px; margin-left: -67px; border-radius: 3px; }
  .pxd-bar.android { width: 108px; margin-left: -54px; height: 4px; bottom: 9px; }
  .pxd-bar.tablet { width: 200px; margin-left: -100px; }
  #pxd-status { position: absolute; left: 0; right: 0; top: 0; z-index: 99999; pointer-events: none; display: flex;
    align-items: center; justify-content: space-between; box-sizing: border-box; font: 600 15px/1 -apple-system,
    BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; letter-spacing: -.2px; }
  #pxd-status svg { display: block; }
  #pxd-status .ic { display: flex; gap: 6px; align-items: center; }
  #pxd-status.android { font: 500 13px/1 Roboto, "Segoe UI", sans-serif; }
  .pxd-handle { position: absolute; z-index: 2; background: transparent; }
  .pxd-handle::after { content: ""; position: absolute; border-radius: 3px; background: rgba(128,128,140,.6); }
  .pxd-handle.r { top: 0; bottom: 0; right: -18px; width: 14px; cursor: ew-resize; }
  .pxd-handle.r::after { left: 5px; top: 50%; width: 4px; height: 40px; margin-top: -20px; }
  .pxd-handle.b { left: 0; right: 0; bottom: -18px; height: 14px; cursor: ns-resize; }
  .pxd-handle.b::after { top: 5px; left: 50%; height: 4px; width: 40px; margin-left: -20px; }
  .pxd-handle.rb { right: -18px; bottom: -18px; width: 16px; height: 16px; cursor: nwse-resize; }
  .pxd-handle.rb::after { inset: 4px; border-radius: 50%; }
  #pxd-label { margin-top: 18px; padding-right: ${TOOLS_W}px; font: 500 12px/1.4 -apple-system, BlinkMacSystemFont,
    "Segoe UI", Roboto, sans-serif; color: #6e6e78; text-align: center; white-space: nowrap; user-select: none; }
  #pxd-label b { color: #3b82f6; font-weight: 600; }
  #pxd-unit { display: flex; align-items: flex-start; }
  .pxd-grip { position: absolute; right: -28px; bottom: -28px; width: 24px; height: 24px; border-radius: 7px; z-index: 2;
    display: flex; align-items: center; justify-content: center; color: #8a8a96; cursor: nwse-resize; touch-action: none; }
  .pxd-grip:hover, .pxd-grip.on { background: rgba(59,130,246,.12); color: #3b82f6; }
  #pxd-tools { position: sticky; top: 16px; margin-left: 24px; width: 48px; flex-shrink: 0; box-sizing: border-box;
    display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 6px; border-radius: 14px;
    background: rgba(255,255,255,.94); box-shadow: 0 10px 30px rgba(0,0,0,.14), 0 0 0 1px rgba(0,0,0,.06);
    -webkit-backdrop-filter: blur(12px); backdrop-filter: blur(12px); user-select: none;
    font: 600 11px/1 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  #pxd-tools button { all: unset; position: relative; box-sizing: border-box; width: 36px; height: 36px;
    border-radius: 9px; display: flex; align-items: center; justify-content: center; color: #3f3f46; cursor: pointer;
    transition: background .12s, color .12s; }
  #pxd-tools button:hover { background: #f0f0f4; color: #111; }
  #pxd-tools button:active { transform: scale(.94); }
  #pxd-tools button.on { color: #2563eb; background: #eaf1ff; }
  #pxd-tools button:focus-visible { outline: 2px solid #3b82f6; outline-offset: 1px; }
  #pxd-tools button svg { display: block; }
  #pxd-tools .zv { height: 24px; font-size: 11px; color: #6b7280; font-variant-numeric: tabular-nums; }
  #pxd-tools .one { font-size: 11px; letter-spacing: -.2px; }
  #pxd-tools hr { all: unset; display: block; width: 22px; height: 1px; background: #e4e4ea; margin: 4px 0; }
  #pxd-tools button[data-tip]:hover::after { content: attr(data-tip); position: absolute; left: calc(100% + 12px);
    top: 50%; transform: translateY(-50%); white-space: nowrap; padding: 6px 9px; border-radius: 7px; z-index: 5;
    background: #18181b; color: #fff; font: 500 12px/1 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    box-shadow: 0 4px 14px rgba(0,0,0,.2); pointer-events: none; }
  @media (prefers-color-scheme: dark) {
    #pxd-tools { background: rgba(34,34,38,.94); box-shadow: 0 10px 30px rgba(0,0,0,.5), 0 0 0 1px rgba(255,255,255,.07); }
    #pxd-tools button { color: #d4d4d8; }
    #pxd-tools button:hover { background: #303036; color: #fff; }
    #pxd-tools button.on { color: #93c5fd; background: rgba(59,130,246,.2); }
    #pxd-tools .zv { color: #a1a1aa; }
    #pxd-tools hr { background: #3a3a40; }
    #pxd-tools button[data-tip]:hover::after { background: #f4f4f5; color: #18181b; }
  }
  `;
  document.head.appendChild(css);

  // -- stage and frame ----------------------------------------------------------------------------------------------
  const stage = el("div", { id: "pxd-stage" });
  const center = el("div", { id: "pxd-center" });
  const box = el("div", { id: "pxd-box" });
  const frame = el("div", { id: "pxd-frame" });
  const screenEl = el("div", { id: "pxd-screen" });
  const status = el("div", { id: "pxd-status" });
  const label = el("div", { id: "pxd-label" });
  const unit = el("div", { id: "pxd-unit" });
  const tools = el("div", { id: "pxd-tools", role: "toolbar", "aria-label": "Device controls" });
  const grip = el("div", { class: "pxd-grip", title: "Drag to zoom" }, I.grip);
  frame.appendChild(screenEl);
  box.append(frame, grip);
  unit.append(box, tools);
  center.append(unit, label);
  stage.appendChild(center);

  function el(tag, attrs, html) {
    const e = document.createElement(tag);
    for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
    if (html != null) e.innerHTML = html;
    return e;
  }

  const pageNodes = () => ["root", "alert", "lost"].map((id) => document.getElementById(id)).filter(Boolean);
  let inFrame = false;
  function place(on) {
    if (on === inFrame) return;
    const ns = pageNodes();
    if (on) {
      if (!stage.parentNode) document.body.prepend(stage);
      screenEl.prepend(...ns);
      screenEl.appendChild(status);
    } else {
      document.body.prepend(...ns);  // back in their original order, before the scripts
    }
    inFrame = on;
  }

  // Room kept on the right for the open panel (none when the window is too narrow: the panel then floats over it).
  const reserve = () => (st.open && window.innerWidth - PANEL_W >= 560 ? PANEL_W : 0);
  function zoomFor(fw, fh) {
    if (st.zoom !== "fit") return clamp(st.zoom, ZMIN, ZMAX);
    const aw = window.innerWidth - 48 - TOOLS_W - reserve() - (st.mode === "custom" ? 24 : 0);
    const ah = window.innerHeight - 110;
    return Math.max(ZMIN, Math.min(1, aw / fw, ah / fh));
  }

  // quick: only the scale changed (zoom slider, pinch, grip): the panel and toolbar are not rebuilt.
  function layout(quick) {
    const s = screenInfo();
    document.documentElement.classList.toggle("pxd-on", !!s);
    place(!!s);
    if (!s) { renderPanel(); return; }
    center.style.paddingRight = 24 + reserve() + "px";
    const d = s.dev, body = !!(d && st.frame);
    const kind = d ? d.kind : "custom";
    frame.className = [kind, st.landscape ? "land" : "", body ? "body" : "bare", d ? d.look : ""].join(" ");
    let pad = [0, 0, 0, 0];
    if (body) {
      const b = d.bezel;
      pad = d.look === "home" ? (st.landscape ? [b, 72, b, 72] : [72, b, 72, b]) : [b, b, b, b];
    }
    frame.style.padding = pad.map((p) => p + "px").join(" ");
    const rad = body ? d.radius : 0;
    frame.style.borderRadius = body ? (d.look === "home" ? "48px" : (rad + d.bezel) + "px") : "0";
    screenEl.style.width = s.w + "px";
    screenEl.style.height = s.h + "px";
    screenEl.style.borderRadius = rad + "px";
    screenEl.classList.toggle("touch", !!d || st.platform !== "web");
    screenEl.classList.toggle("dark", scheme() === "dark");
    decorate(d, body, pad);
    statusBarRender(s, body);
    const fw = s.w + pad[1] + pad[3], fh = s.h + pad[0] + pad[2];
    const z = zoomFor(fw, fh);
    frame.style.transform = z === 1 ? "" : "scale(" + z + ")";
    box.style.width = fw * z + "px";
    box.style.height = fh * z + "px";
    handles(!d);
    grip.style.display = d ? "" : "none";
    const bp = bpFor(s.w);
    label.innerHTML = (d ? esc(d.name) + " · " : "") + s.w + " × " + s.h + " · <b>" + bp + "</b> · " +
      Math.round(z * 100) + "%" + (st.platform !== "web" ? " · " + st.platform : "");
    zoomNow = z;
    if (quick) { syncZoomUI(); return; }
    renderTools();
    renderPanel();
  }
  let zoomNow = 1;

  // anchor {x, y}: the page point that stays under the pointer (wheel / pinch zoom).
  function setZoom(z, anchor) {
    const before = anchor && box.getBoundingClientRect();
    st.zoom = Math.round(clamp(z, ZMIN, ZMAX) * 100) / 100;
    layout(true);
    if (before && before.width) {
      const after = box.getBoundingClientRect();
      stage.scrollLeft += after.left + (anchor.x - before.left) * (after.width / before.width) - anchor.x;
      stage.scrollTop += after.top + (anchor.y - before.top) * (after.height / before.height) - anchor.y;
    }
    saveSoon();
  }
  function stepZoom(dir) {
    const cur = zoomNow;
    const next = dir > 0 ? ZSTEPS.find((v) => v > cur + 0.005) : ZSTEPS.slice().reverse().find((v) => v < cur - 0.005);
    if (next) setZoom(next);
  }
  function fitZoom() { st.zoom = "fit"; layout(true); saveSoon(); }
  let saveTimer = null;
  function saveSoon() { clearTimeout(saveTimer); saveTimer = setTimeout(save, 200); }

  function syncZoomUI() {
    const pct = Math.round(zoomNow * 100), fit = st.zoom === "fit";
    const zv = tools.querySelector(".zv");
    if (zv) zv.textContent = pct + "%";
    tools.querySelectorAll("[data-a=fit]").forEach((b) => b.classList.toggle("on", fit && !b.classList.contains("zv")));
    const one = tools.querySelector(".one");
    if (one) one.classList.toggle("on", pct === 100 && !fit);
    const r = panel.querySelector("[data-k=zrange]");
    if (r && Number(r.value) !== pct) r.value = pct;
    const v = panel.querySelector(".zval");
    if (v) v.textContent = pct + "%";
    panel.querySelectorAll(".chip").forEach((c) => c.classList.toggle("on",
      c.dataset.a === "fit" ? fit : !fit && Math.round(Number(c.dataset.z) * 100) === pct));
  }

  // -- side toolbar (like an emulator's) ----------------------------------------------------------------------------
  function renderTools() {
    const b = (a, tip, icon, cls) => '<button type="button" data-a="' + a + '" data-tip="' + esc(tip) + '" aria-label="' +
      esc(tip) + '"' + (cls ? ' class="' + cls + '"' : "") + ">" + icon + "</button>";
    const dark = scheme() === "dark", custom = st.mode === "custom";
    tools.innerHTML =
      b("rotate", custom ? "Swap width and height" : st.landscape ? "Rotate to portrait" : "Rotate to landscape",
        custom ? I.swap : I.rotate) + "<hr>" +
      b("zin", "Zoom in (Ctrl/⌘ + scroll)", I.zin) +
      '<button type="button" class="zv" data-a="fit" aria-label="Zoom level, click to fit">' +
        Math.round(zoomNow * 100) + "%</button>" +
      b("zout", "Zoom out", I.zout) +
      b("fit", "Fit to window", I.fit) +
      b("one", "Actual size (100%)", "1:1", "one") + "<hr>" +
      b("theme", dark ? "Light mode" : "Dark mode", dark ? I.sun : I.moon) +
      b("back", st.platform === "android" ? "Back (Esc)" : "Back", I.back) +
      b("reload", "Reload app", I.reload) + "<hr>" +
      b("panel", "Dev tools panel", I.sliders, st.open ? "on" : "") +
      b("exit", "Exit device view (⌘/Ctrl ⇧ M)", I.system);
    syncZoomUI();
  }
  tools.addEventListener("click", (e) => {
    const t = e.target.closest("[data-a]");
    if (t) act(t.dataset.a);
  });

  // Ctrl/Cmd + wheel and trackpad pinch (Chrome sends it as ctrl + wheel) zoom the device around the pointer.
  window.addEventListener("wheel", (e) => {
    if (!inFrame || !(e.ctrlKey || e.metaKey)) return;
    e.preventDefault();
    const d = Math.max(-50, Math.min(50, e.deltaY));
    setZoom(zoomNow * Math.exp(-d * 0.006), { x: e.clientX, y: e.clientY });
  }, { passive: false });

  // Corner grip: drag out to zoom in, in to zoom out (the device keeps its size in dp).
  grip.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    e.stopPropagation();
    grip.setPointerCapture(e.pointerId);
    grip.classList.add("on");
    const sx = e.clientX, sy = e.clientY, z0 = zoomNow, bw = box.offsetWidth, bh = box.offsetHeight;
    const move = (m) => setZoom(z0 * Math.max(0.05, (bw + bh + (m.clientX - sx) + (m.clientY - sy)) / (bw + bh)));
    const up = () => {
      grip.removeEventListener("pointermove", move);
      grip.removeEventListener("pointerup", up);
      grip.classList.remove("on");
      save();
    };
    grip.addEventListener("pointermove", move);
    grip.addEventListener("pointerup", up);
  });

  const decos = [];
  function decorate(d, body, pad) {
    decos.splice(0).forEach((n) => n.remove());
    if (!d || !body) return;
    const add = (cls, parent, style) => {
      const n = el("div", { class: "pxd-deco " + cls });
      Object.assign(n.style, style || {});
      (parent || screenEl).appendChild(n);
      decos.push(n);
      return n;
    };
    if (d.look === "island") add("pxd-island");
    if (d.look === "punch") add("pxd-punch");
    if (d.look === "home") {  // bezels hold the speaker and the home button
      const b = 72;
      if (st.landscape) {
        add("pxd-speaker", frame, { left: (b / 2 - 3) + "px", top: "50%", width: "6px", height: "56px", marginTop: "-28px" });
        add("pxd-home-btn", frame, { right: (b / 2 - 24) + "px", top: "50%", marginTop: "-24px" });
      } else {
        add("pxd-speaker", frame, { top: (b / 2 - 3) + "px", left: "50%", marginLeft: "-28px" });
        add("pxd-home-btn", frame, { bottom: (b / 2 - 24) + "px", left: "50%", marginLeft: "-24px" });
      }
    }
    if (d.look === "tablet") {
      const p = pad[0];
      add("pxd-cam", frame, st.landscape ? { left: (p / 2 - 4) + "px", top: "50%", marginTop: "-4px" }
        : { top: (p / 2 - 4) + "px", left: "50%", marginLeft: "-4px" });
    }
    if (d.look !== "home") {
      const bar = add("pxd-bar" + (d.os === "android" ? " android" : "") + (d.kind === "tablet" ? " tablet" : ""));
      bar.style.background = scheme() === "dark" ? "rgba(255,255,255,.85)" : "rgba(0,0,0,.85)";
      if (st.landscape && d.kind === "phone") bar.style.bottom = "6px";
    }
  }

  const ICONS = {
    signal: '<svg width="18" height="11" viewBox="0 0 18 11"><rect x="0" y="7" width="3" height="4" rx="1"/>' +
      '<rect x="5" y="5" width="3" height="6" rx="1"/><rect x="10" y="2.5" width="3" height="8.5" rx="1"/>' +
      '<rect x="15" y="0" width="3" height="11" rx="1"/></svg>',
    wifi: '<svg width="16" height="11" viewBox="0 0 16 11"><path d="M8 2.2c2.3 0 4.4.9 6 2.4l1.3-1.3A10.3 10.3 0 0 0 ' +
      '8 .3 10.3 10.3 0 0 0 .7 3.3L2 4.6a8.5 8.5 0 0 1 6-2.4Zm0 3.6c1.3 0 2.5.5 3.4 1.3l1.3-1.3A6.6 6.6 0 0 0 8 4a6.6 ' +
      '6.6 0 0 0-4.7 1.8l1.3 1.3c.9-.8 2.1-1.3 3.4-1.3Zm0 3.6c.4 0 .8.2 1.1.4L8 11 6.9 9.8c.3-.2.7-.4 1.1-.4Z"/></svg>',
    battery: '<svg width="27" height="12" viewBox="0 0 27 12"><rect x=".5" y=".5" width="23" height="11" rx="3" ' +
      'fill="none" stroke="currentColor" opacity=".4"/><rect x="2" y="2" width="20" height="8" rx="1.8"/>' +
      '<path d="M25 4v4a2 2 0 0 0 0-4Z" opacity=".5"/></svg>',
    abattery: '<svg width="10" height="15" viewBox="0 0 10 15"><path d="M3 0h4v1.5h2a1 1 0 0 1 1 1V14a1 1 0 0 1-1 1H1' +
      'a1 1 0 0 1-1-1V2.5a1 1 0 0 1 1-1h2Z"/></svg>',
  };
  function statusBarRender(s, body) {
    const d = s.dev;
    if (!d || !body || !s.sb || statusBar.hidden) { status.style.display = "none"; return; }
    status.style.display = "flex";
    status.style.height = s.sb + "px";
    const android = d.os === "android";
    const glyph = statusBar.style || (scheme() === "dark" ? "light" : "dark");
    status.style.color = glyph === "light" ? "#fff" : "#000";
    status.style.fill = "currentColor";
    status.style.background = android && statusBar.background != null ? statusBar.background : "transparent";
    status.className = android ? "android" : "";
    const island = d.look === "island";
    status.style.padding = island ? "0 30px 0 50px" : android ? "0 18px" : "0 8px";
    if (island) status.style.paddingTop = "6px";
    const time = android ? "9:41" : "9:41";
    status.innerHTML = '<span style="width:' + (island ? 54 : 40) + 'px;text-align:' + (island ? "center" : "left") +
      '">' + time + "</span>" + '<span class="ic">' +
      (android ? ICONS.wifi + ICONS.signal + ICONS.abattery : ICONS.signal + ICONS.wifi + ICONS.battery) + "</span>";
    status.querySelectorAll("svg").forEach((v) => v.setAttribute("fill", "currentColor"));
  }
  window.addEventListener("pyxpo-statusbar", (e) => {
    const { method, value } = e.detail || {};
    if (method === "set_style") statusBar.style = value === "light" ? "light" : value === "dark" ? "dark" : null;
    else if (method === "set_hidden") statusBar.hidden = !!value;
    else if (method === "set_background") statusBar.background = typeof value === "number"
      ? "rgba(" + ((value >>> 16) & 255) + "," + ((value >>> 8) & 255) + "," + (value & 255) + "," +
        (((value >>> 24) & 255) / 255) + ")" : value;
    const s = screenInfo();
    if (s) statusBarRender(s, !!(s.dev && st.frame));
  });

  // -- custom size: drag handles ------------------------------------------------------------------------------------
  const hs = ["r", "b", "rb"].map((k) => {
    const h = el("div", { class: "pxd-handle " + k, title: "Drag to resize" });
    h.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      e.stopPropagation();
      h.setPointerCapture(e.pointerId);
      const sx = e.clientX, sy = e.clientY, w0 = st.cw, h0 = st.ch, z = zoomNow;
      const move = (m) => {
        if (k !== "b") st.cw = Math.round(clamp(w0 + (m.clientX - sx) / z, 200, 3840));
        if (k !== "r") st.ch = Math.round(clamp(h0 + (m.clientY - sy) / z, 200, 3840));
        if (st.zoom === "fit") st.zoom = Math.round(z * 100) / 100;  // keep the scale still while dragging
        layout(true);
        envSoon();
      };
      const up = () => {
        h.removeEventListener("pointermove", move);
        h.removeEventListener("pointerup", up);
        save();
        layout();
      };
      h.addEventListener("pointermove", move);
      h.addEventListener("pointerup", up);
    });
    return h;
  });
  function handles(on) {
    hs.forEach((h) => { if (on && !h.parentNode) box.appendChild(h); if (!on && h.parentNode) h.remove(); });
  }
  let envTimer = null;
  function envSoon() { clearTimeout(envTimer); envTimer = setTimeout(sendEnv, 40); }

  // -- touch screen: drag to scroll with momentum -------------------------------------------------------------------
  let drag = null, glide = 0, eatClick = false;
  function scroller(n, axis) {
    for (; n && n !== screenEl; n = n.parentNode) {
      if (n.nodeType !== 1) continue;
      const cs = getComputedStyle(n);
      if (axis === "y" && /(auto|scroll)/.test(cs.overflowY) && n.scrollHeight > n.clientHeight + 1) return n;
      if (axis === "x" && /(auto|scroll)/.test(cs.overflowX) && n.scrollWidth > n.clientWidth + 1) return n;
    }
    return null;
  }
  screenEl.addEventListener("pointerdown", (e) => {
    cancelAnimationFrame(glide);
    if (!screenEl.classList.contains("touch") || e.pointerType !== "mouse" || e.button !== 0) return;
    if (e.target.closest("input, textarea, select, .sl, .sw, #alert")) return;
    drag = { x: e.clientX, y: e.clientY, lx: e.clientX, ly: e.clientY, t: performance.now(), vx: 0, vy: 0,
             target: e.target, sc: null, moved: false };
  }, true);
  document.addEventListener("pointermove", (e) => {
    if (!drag) return;
    if (!drag.moved) {
      const ax = e.clientX - drag.x, ay = e.clientY - drag.y;
      if (Math.hypot(ax, ay) < 6) return;
      drag.moved = true;
      const main = Math.abs(ax) > Math.abs(ay) ? "x" : "y";
      drag.sc = scroller(drag.target, main) || scroller(drag.target, main === "x" ? "y" : "x");
      const sel = window.getSelection && window.getSelection();
      if (sel) sel.removeAllRanges();
    }
    const now = performance.now(), dt = Math.max(1, now - drag.t);
    const dx = (e.clientX - drag.lx) / zoomNow, dy = (e.clientY - drag.ly) / zoomNow;
    if (drag.sc) { drag.sc.scrollLeft -= dx; drag.sc.scrollTop -= dy; }
    drag.vx = 0.8 * (dx / dt) + 0.2 * drag.vx;
    drag.vy = 0.8 * (dy / dt) + 0.2 * drag.vy;
    drag.lx = e.clientX; drag.ly = e.clientY; drag.t = now;
  }, true);
  function endDrag() {
    if (!drag) return;
    const d = drag;
    drag = null;
    if (!d.moved) return;
    eatClick = true;
    setTimeout(() => { eatClick = false; }, 0);
    if (!d.sc || performance.now() - d.t > 80) return;
    let vx = d.vx, vy = d.vy, last = performance.now();
    const step = (now) => {
      const dt = now - last;
      last = now;
      d.sc.scrollLeft -= vx * dt;
      d.sc.scrollTop -= vy * dt;
      const k = Math.pow(0.995, dt);
      vx *= k; vy *= k;
      if (Math.abs(vx) + Math.abs(vy) > 0.02) glide = requestAnimationFrame(step);
    };
    glide = requestAnimationFrame(step);
  }
  document.addEventListener("pointerup", endDrag, true);
  document.addEventListener("pointercancel", () => { drag = null; }, true);
  window.addEventListener("click", (e) => { if (eatClick) { e.stopPropagation(); e.preventDefault(); eatClick = false; } }, true);
  screenEl.addEventListener("dragstart", (e) => { if (screenEl.classList.contains("touch")) e.preventDefault(); });

  // -- panel (shadow DOM keeps the app's CSS out) -------------------------------------------------------------------
  const host = el("div", { id: "pxd-host" });
  host.style.cssText = "position:fixed;z-index:2147483000;right:0;bottom:0;width:0;height:0";
  const root = host.attachShadow({ mode: "open" });
  root.innerHTML = `<style>
    :host { all: initial; }
    * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    button { font: inherit; }
    .fab { position: fixed; right: 18px; bottom: 18px; width: 48px; height: 48px; border-radius: 50%; border: 0;
      background: #18181b; color: #fff; display: flex; align-items: center; justify-content: center; cursor: pointer;
      box-shadow: 0 8px 24px rgba(0,0,0,.28), 0 0 0 1px rgba(255,255,255,.08) inset; transition: transform .15s, background .15s; }
    .fab:hover { transform: scale(1.06); }
    .fab.open { background: #2563eb; }
    .fab:focus-visible { outline: 2px solid #3b82f6; outline-offset: 3px; }
    .fab .dot { position: absolute; top: 2px; right: 2px; width: 11px; height: 11px; border-radius: 50%;
      background: #22c55e; box-shadow: 0 0 0 2px #18181b; display: none; }
    .fab.dev .dot { display: block; }
    .panel { position: fixed; right: 18px; bottom: 78px; width: 328px; max-height: calc(100vh - 96px); overflow: auto;
      border-radius: 16px; background: #fff; color: #18181b; font-size: 12px; overscroll-behavior: contain;
      box-shadow: 0 24px 60px rgba(0,0,0,.22), 0 0 0 1px rgba(0,0,0,.06); display: none; }
    .panel.show { display: block; animation: pop .16s ease-out; }
    @keyframes pop { from { opacity: 0; transform: translateY(6px) scale(.98); } }
    header { position: sticky; top: 0; z-index: 1; display: flex; align-items: center; gap: 10px;
      padding: 12px 10px 12px 14px; background: inherit; border-bottom: 1px solid #f0f0f3; }
    .logo { width: 30px; height: 30px; border-radius: 9px; flex-shrink: 0; color: #fff; display: flex;
      align-items: center; justify-content: center; background: linear-gradient(135deg, #3b82f6, #6366f1); }
    .ttl { flex: 1; line-height: 1.3; min-width: 0; }
    .ttl b { display: block; font-size: 13px; }
    .ttl small { color: #71717a; font-size: 11px; }
    .x { border: 0; background: none; width: 30px; height: 30px; border-radius: 8px; color: #71717a; cursor: pointer;
      display: flex; align-items: center; justify-content: center; }
    .x:hover { background: #f4f4f5; color: #18181b; }
    section { padding: 12px 14px; }
    section + section { border-top: 1px solid #f0f0f3; }
    h4 { margin: 0 0 8px; font-size: 10.5px; font-weight: 700; color: #a1a1aa; text-transform: uppercase;
      letter-spacing: .6px; display: flex; justify-content: space-between; align-items: center; }
    h4 em { font-style: normal; text-transform: none; letter-spacing: 0; font-weight: 600; color: #3b82f6; font-size: 11px; }
    .seg { display: flex; background: #f4f4f5; border-radius: 10px; padding: 3px; gap: 2px; }
    .seg button { flex: 1; border: 0; background: none; padding: 7px 4px; border-radius: 8px; font-size: 11.5px;
      color: #52525b; cursor: pointer; display: flex; flex-direction: column; align-items: center; gap: 4px;
      transition: background .12s, color .12s; }
    .seg button:hover { color: #18181b; }
    .seg.inline button { flex-direction: row; justify-content: center; gap: 6px; }
    .seg.inline svg { width: 15px; height: 15px; }
    .seg button.on { background: #fff; color: #2563eb; font-weight: 600;
      box-shadow: 0 1px 3px rgba(0,0,0,.1), 0 0 0 1px rgba(0,0,0,.03); }
    .row { display: flex; gap: 8px; align-items: center; margin-top: 8px; }
    select, input[type=number] { height: 32px; font-size: 12px; padding: 0 8px; border: 1px solid #e4e4e7;
      border-radius: 8px; background: #fff; color: inherit; min-width: 0; outline: none; }
    select:focus, input[type=number]:focus { border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,.15); }
    select { flex: 1; cursor: pointer; }
    input[type=number] { width: 0; flex: 1; font-variant-numeric: tabular-nums; }
    .times { color: #a1a1aa; }
    .ib { width: 32px; height: 32px; flex-shrink: 0; border: 1px solid #e4e4e7; background: #fff; border-radius: 8px;
      color: #3f3f46; cursor: pointer; display: flex; align-items: center; justify-content: center; padding: 0; }
    .ib:hover { background: #f4f4f5; }
    .ib svg { width: 16px; height: 16px; }
    label.tg { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 12px;
      cursor: pointer; }
    .tg small { display: block; color: #a1a1aa; font-size: 11px; margin-top: 2px; }
    .tg input { position: absolute; opacity: 0; pointer-events: none; }
    .tg i { position: relative; width: 34px; height: 20px; flex-shrink: 0; border-radius: 10px; background: #d4d4d8;
      transition: background .15s; }
    .tg i::after { content: ""; position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%;
      background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,.25); transition: transform .15s; }
    .tg input:checked + i { background: #3b82f6; }
    .tg input:checked + i::after { transform: translateX(14px); }
    .tg input:focus-visible + i { outline: 2px solid #3b82f6; outline-offset: 2px; }
    .zoom { display: flex; align-items: center; gap: 8px; }
    input[type=range] { flex: 1; min-width: 0; accent-color: #3b82f6; margin: 0; cursor: pointer; }
    .zval { width: 40px; text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; }
    .chips { display: flex; gap: 4px; margin-top: 10px; }
    .chip { flex: 1; height: 26px; border: 1px solid #e4e4e7; background: #fff; border-radius: 7px; font-size: 11px;
      color: #52525b; cursor: pointer; padding: 0; }
    .chip:hover { background: #f4f4f5; }
    .chip.on { border-color: #3b82f6; background: #eff6ff; color: #1d4ed8; font-weight: 600; }
    .bps { display: flex; gap: 3px; }
    .bp { flex: 1; border: 1px solid #e4e4e7; border-radius: 8px; padding: 5px 0; text-align: center; cursor: pointer;
      background: #fff; color: #3f3f46; line-height: 1.2; font-weight: 600; }
    .bp:hover { border-color: #93c5fd; }
    .bp small { display: block; color: #a1a1aa; font-size: 10px; font-weight: 400; }
    .bp.on { background: #3b82f6; border-color: #3b82f6; color: #fff; }
    .bp.on small { color: #dbeafe; }
    .meter { position: relative; height: 6px; border-radius: 3px; background: #f4f4f5; margin-top: 10px; overflow: hidden; }
    .meter i { position: absolute; top: 0; bottom: 0; left: 0; border-radius: 3px;
      background: linear-gradient(90deg, #93c5fd, #3b82f6); transition: width .2s; }
    .info { color: #71717a; margin-top: 8px; display: flex; justify-content: space-between; }
    .info b { color: #18181b; font-variant-numeric: tabular-nums; }
    .hint { color: #a1a1aa; font-size: 11px; margin-top: 8px; line-height: 1.45; }
    footer { display: flex; gap: 8px; padding: 12px 14px 14px; border-top: 1px solid #f0f0f3; }
    .btn { flex: 1; height: 32px; border: 1px solid #e4e4e7; background: #fff; border-radius: 8px; font-size: 12px;
      cursor: pointer; color: inherit; display: inline-flex; align-items: center; justify-content: center; gap: 6px; }
    .btn svg { width: 14px; height: 14px; }
    .btn:hover { background: #f4f4f5; }
    @media (prefers-color-scheme: dark) {
      .panel { background: #1c1c20; color: #f4f4f5; box-shadow: 0 24px 60px rgba(0,0,0,.6), 0 0 0 1px rgba(255,255,255,.08); }
      header, section + section, footer { border-color: #2a2a30; }
      .x:hover { background: #2a2a30; color: #fff; }
      .seg { background: #27272a; }
      .seg button { color: #a1a1aa; }
      .seg button:hover { color: #fff; }
      .seg button.on { background: #3f3f46; color: #93c5fd; box-shadow: none; }
      select, input[type=number], .ib, .chip, .btn, .bp { background: #232327; border-color: #3a3a42; color: #e4e4e7; }
      .ib:hover, .chip:hover, .btn:hover { background: #2e2e35; }
      .chip.on { background: rgba(59,130,246,.2); color: #bfdbfe; border-color: #3b82f6; }
      .bp.on { background: #3b82f6; border-color: #3b82f6; color: #fff; }
      .tg i { background: #52525b; }
      .meter { background: #27272a; }
      .info b { color: #f4f4f5; }
      .fab { background: #f4f4f5; color: #18181b; }
      .fab.open { background: #3b82f6; color: #fff; }
      .fab .dot { box-shadow: 0 0 0 2px #f4f4f5; }
    }
  </style>
  <button class="fab" title="pyxpo dev tools (Ctrl/Cmd+Shift+M: device on/off)" aria-label="pyxpo dev tools">
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
      stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="2" width="12" height="20" rx="2.5"/>
      <path d="M11 18h2"/></svg><span class="dot"></span></button>
  <div class="panel" role="dialog" aria-label="pyxpo dev tools"></div>`;
  const fab = root.querySelector(".fab");
  const panel = root.querySelector(".panel");
  fab.addEventListener("click", () => act("panel"));

  const MODE_ICONS = {
    desktop: I.system,
    phone: I.portrait,
    tablet: svg('<rect x="4" y="2" width="16" height="20" rx="2.5"/><path d="M11 18h2"/>'),
    custom: svg('<path d="M4 9V4h5M20 15v5h-5M4 4l7 7M20 20l-7-7"/>'),
  };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  function bpTable() {
    const t = (window.PYXPO_CONFIG && window.PYXPO_CONFIG.breakpoints) || DEFAULT_BP;
    return Object.entries(t).sort((a, b) => a[1] - b[1]).map(([n, w], i) => [n, i === 0 ? 0 : w]);
  }
  function bpFor(w) {
    let name = bpTable()[0][0];
    for (const [n, m] of bpTable()) if (w >= m) name = n;
    return name;
  }
  function currentWidth() { const s = screenInfo(); return s ? s.w : window.innerWidth; }

  // items: [value, text, icon]
  const seg = (key, items, cur, cls) => '<div class="seg' + (cls ? " " + cls : "") + '">' + items.map(([v, text, icon]) =>
    '<button type="button" data-' + key + '="' + v + '"' + (cur === v ? ' class="on"' : "") + ">" + (icon || "") +
    "<span>" + text + "</span></button>").join("") + "</div>";

  function renderPanel() {
    fab.classList.toggle("dev", st.mode !== "desktop");
    fab.classList.toggle("open", !!st.open);
    panel.classList.toggle("show", !!st.open);
    if (!st.open) return;
    const s = screenInfo(), w = currentWidth(), h = s ? s.h : window.innerHeight;
    const bps = bpTable(), bp = bpFor(w), last = bps[bps.length - 1][1] || 1;
    const d = s && s.dev;
    let dev = "";
    if (st.mode === "phone" || st.mode === "tablet") {
      dev = '<div class="row"><select data-k="dev" aria-label="Device">' + DEVICES.filter((x) => x.kind === st.mode)
        .map((x) => '<option value="' + x.id + '"' + (x.id === st[st.mode] ? " selected" : "") + ">" + esc(x.name) +
          "  ·  " + x.w + "×" + x.h + "</option>").join("") + "</select></div>" +
        '<div class="row">' + seg("orient", [["port", "Portrait", I.portrait], ["land", "Landscape", I.landscape]],
          st.landscape ? "land" : "port", "inline").replace('<div class="seg', '<div style="flex:1" class="seg') + "</div>" +
        '<label class="tg"><span>Device frame<small>Body, status bar and safe area insets</small></span>' +
        '<input type="checkbox" data-k="frame"' + (st.frame ? " checked" : "") + "><i></i></label>";
    } else if (st.mode === "custom") {
      dev = '<div class="row"><input type="number" min="200" max="3840" data-k="cw" aria-label="Width" value="' + st.cw +
        '"><span class="times">×</span><input type="number" min="200" max="3840" data-k="ch" aria-label="Height" value="' +
        st.ch + '"><button type="button" class="ib" data-a="swap" title="Swap width and height">' + I.swap + "</button></div>" +
        '<div class="hint">Drag the handles on the right and bottom edges of the screen to resize.</div>';
    }
    const pct = Math.round(zoomNow * 100);
    const zoom = s ? "<section><h4>Zoom <em class=\"zval\">" + pct + "%</em></h4>" +
      '<div class="zoom"><button type="button" class="ib" data-a="zout" title="Zoom out">' + I.minus + "</button>" +
      '<input type="range" min="' + ZMIN * 100 + '" max="' + ZMAX * 100 + '" step="1" data-k="zrange" aria-label="Zoom" ' +
      'value="' + pct + '"><button type="button" class="ib" data-a="zin" title="Zoom in">' + I.plus + "</button></div>" +
      '<div class="chips"><button type="button" class="chip" data-a="fit">Fit</button>' +
      [0.5, 0.75, 1, 1.5, 2].map((z) => '<button type="button" class="chip" data-z="' + z + '">' + z * 100 + "%</button>")
        .join("") + "</div>" +
      '<div class="hint">Ctrl/⌘ + scroll or pinch over the device to zoom' + (d ? ", or drag its corner grip." : ".") +
      "</div></section>" : "";
    panel.innerHTML =
      '<header><div class="logo">' + svg('<rect x="6" y="2" width="12" height="20" rx="2.5"/><path d="M11 18h2"/>', 16) +
      '</div><div class="ttl"><b>pyxpo dev tools</b><small>⌘/Ctrl ⇧ M turns the device on and off</small></div>' +
      '<button type="button" class="x" data-a="close" aria-label="Close">' + I.close + "</button></header>" +
      "<section><h4>View" + (d ? "<em>" + esc(d.name) + "</em>" : "") + "</h4>" +
      seg("mode", ["desktop", "phone", "tablet", "custom"].map((m) => [m,
        { desktop: "Desktop", phone: "Mobile", tablet: "Tablet", custom: "Custom" }[m], MODE_ICONS[m]]), st.mode) +
      dev + "</section>" + zoom +
      "<section><h4>Breakpoint <em>" + esc(bp) + "</em></h4><div class=\"bps\">" + bps.map(([n, m]) =>
        '<div class="bp' + (n === bp ? " on" : "") + '" data-bp="' + esc(n) + '" title="Show the app at ' + Math.max(m, 360) +
        ' px">' + esc(n) + "<small>" + (m ? m + "+" : "0") + "</small></div>").join("") + "</div>" +
      '<div class="meter"><i style="width:' + Math.min(100, (w / (last * 1.15)) * 100) + '%"></i></div>' +
      '<div class="info"><span>Window <b>' + w + " × " + h + "</b></span><span>" +
      (s ? "Scale <b>@" + s.dpr + "x</b>" : "") + "</span></div></section>" +
      "<section><h4>Appearance</h4>" + seg("scheme", [["system", "System", I.system], ["light", "Light", I.sun],
        ["dark", "Dark", I.moon]], st.scheme, "inline") + "</section>" +
      "<section><h4>Behaviour</h4>" + seg("platform", [["web", "Web"], ["ios", "iOS"], ["android", "Android"]],
        st.platform, "inline") +
      '<div class="hint">' + (st.platform === "web" ? "Navigation acts like a web site (browser history, no slide)."
        : "Platform.OS is \"" + st.platform + "\": stacks slide and swipe like the phone app." +
          (st.platform === "android" ? " Esc is the hardware back button." : "")) + " Changing it reloads the app.</div>" +
      "</section>" +
      '<footer><button type="button" class="btn" data-a="reload">' + I.reload + "Reload app</button>" +
      '<button type="button" class="btn" data-a="reset">Reset all</button></footer>';
    syncZoomUI();
  }

  function act(a) {
    if (a === "rotate" && st.mode === "custom") a = "swap";
    if (a === "rotate") { st.landscape = !st.landscape; st.zoom = "fit"; apply(); }
    else if (a === "swap") { [st.cw, st.ch] = [st.ch, st.cw]; apply(); }
    else if (a === "zin") stepZoom(1);
    else if (a === "zout") stepZoom(-1);
    else if (a === "fit") fitZoom();
    else if (a === "one") setZoom(1);
    else if (a === "theme") { st.scheme = scheme() === "dark" ? "light" : "dark"; apply(); }
    else if (a === "back") {
      if (st.platform === "android" && window.pyxpoPage && window.pyxpoPage.emit) window.pyxpoPage.emit("hardware_back", 0);
      else history.back();
    } else if (a === "reload") location.reload();
    else if (a === "panel" || a === "close") { st.open = a === "panel" ? !st.open : false; save(); layout(); }
    else if (a === "exit") { lastDevice = st.mode; setMode("desktop"); }
    else if (a === "reset") {
      const reload = st.platform !== "web";
      st = Object.assign({}, defaults, { open: true });
      if (reload) { save(); location.reload(); return; }
      apply();
    }
  }

  panel.addEventListener("click", (e) => {
    const t = e.target.closest("[data-mode],[data-scheme],[data-platform],[data-orient],[data-a],[data-bp],[data-z]");
    if (!t) return;
    if (t.dataset.mode) setMode(t.dataset.mode);
    else if (t.dataset.scheme) { st.scheme = t.dataset.scheme; apply(); }
    else if (t.dataset.orient) { st.landscape = t.dataset.orient === "land"; st.zoom = "fit"; apply(); }
    else if (t.dataset.platform) {
      if (t.dataset.platform !== st.platform) { st.platform = t.dataset.platform; save(); location.reload(); }
    } else if (t.dataset.z) setZoom(Number(t.dataset.z));
    else if (t.dataset.bp) {
      const m = Object.fromEntries(bpTable())[t.dataset.bp];
      st.mode = "custom";
      st.cw = Math.max(m, 360);
      st.zoom = "fit";
      apply();
    } else if (t.dataset.a) act(t.dataset.a);
  });
  panel.addEventListener("input", (e) => {
    if (e.target.dataset.k === "zrange") setZoom(Number(e.target.value) / 100);
  });
  panel.addEventListener("change", (e) => {
    const k = e.target.dataset.k;
    if (!k || k === "zrange") return;
    if (k === "dev") { st[st.mode] = e.target.value; st.zoom = "fit"; }
    else if (k === "frame") st.frame = e.target.checked;
    else if (k === "cw" || k === "ch") st[k] = Math.round(clamp(e.target.value, 200, 3840));
    apply();
  });

  function setMode(m) {
    st.mode = m;
    st.zoom = "fit";  // a new device starts fitted to the window
    apply();
  }
  function apply() { save(); layout(); sendEnv(); }

  // -- keys, window -------------------------------------------------------------------------------------------------
  let lastDevice = st.mode !== "desktop" ? st.mode : "phone";
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.shiftKey && (e.key === "m" || e.key === "M")) {
      e.preventDefault();
      if (st.mode === "desktop") setMode(lastDevice);
      else { lastDevice = st.mode; setMode("desktop"); }
      return;
    }
    if (e.key === "Escape" && st.platform === "android" && !e.defaultPrevented &&
        !(document.getElementById("alert") || { classList: { contains: () => false } }).classList.contains("show")) {
      if (window.pyxpoPage && window.pyxpoPage.emit) window.pyxpoPage.emit("hardware_back", 0);
    }
  });
  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (st.mode !== "desktop") layout(); else renderPanel(); }, 60);
  });
  darkMq.addEventListener("change", () => { if (st.scheme === "system") layout(); });

  function start() {
    document.body.appendChild(host);
    layout();
  }
  if (document.body && document.getElementById("root")) start();
  else document.addEventListener("DOMContentLoaded", start);
})();
