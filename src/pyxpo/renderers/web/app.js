// pyxpo desktop page: applies native ops from Python to the DOM and posts events back.
// Same op and event contract as the iOS and Android shells (see OpApplier.swift).
(() => {
  "use strict";
  const TOKEN = window.PYXPO_TOKEN;
  const rootEl = document.getElementById("root");
  const nodes = new Map();        // id -> {id, type, el, props, children, parent}
  const aval = {};                // animated node id -> current value
  const bindings = new Map();     // animated node id -> Set(view id)
  const fonts = new Set();

  const extraCss = document.createElement("style");
  extraCss.textContent = ".in::placeholder { color: var(--ph, #a0a0a8); }";
  document.head.appendChild(extraCss);

  // -- events to Python -------------------------------------------------------------------------
  let outbox = [];
  let flushing = false;
  function emit(event, id, payload) {
    outbox.push({ event, id, payload: payload || {} });
    if (!flushing) { flushing = true; queueMicrotask(flush); }
  }
  function flush() {
    flushing = false;
    if (!outbox.length) return;
    const body = JSON.stringify(outbox);
    outbox = [];
    fetch("/event", { method: "POST", body, headers: { "content-type": "application/json", "x-pyxpo-token": TOKEN } })
      .catch(() => {});
  }

  // -- values -----------------------------------------------------------------------------------
  function color(v) {
    if (v == null) return "";
    if (typeof v === "string") return v;
    const n = v >>> 0;
    const a = (n >>> 24) & 255, r = (n >>> 16) & 255, g = (n >>> 8) & 255, b = n & 255;
    return `rgba(${r},${g},${b},${+(a / 255).toFixed(3)})`;
  }
  function px(v) { return typeof v === "number" ? v + "px" : String(v); }
  function kebab(v) { return typeof v === "string" ? v.replace(/_/g, "-") : v; }
  function resolve(v, id) {
    if (v && typeof v === "object" && "$a" in v) {
      const nid = String(v["$a"]);
      if (!bindings.has(nid)) bindings.set(nid, new Set());
      bindings.get(nid).add(id);
      const r = aval[nid];
      return r == null ? 0 : r;
    }
    return v;
  }
  function fileUrl(p) { return "/file?t=" + encodeURIComponent(TOKEN) + "&p=" + encodeURIComponent(p); }
  function srcUrl(uri) {
    if (!uri) return "";
    if (/^(https?:|data:|blob:)/.test(uri)) return uri;
    if (uri.startsWith("file://")) uri = decodeURIComponent(uri.slice(7));
    return fileUrl(uri);
  }

  // -- style ------------------------------------------------------------------------------------
  const EDGE = { top: "top", right: "right", bottom: "bottom", left: "left", start: "left", end: "right",
                 horizontal: null, vertical: null };
  const TEXT_KEYS = new Set(["color", "font_size", "font_weight", "font_style", "font_family", "font_file", "line_height",
    "letter_spacing", "text_align", "text_decoration", "text_decoration_line", "text_transform", "background_color",
    "text_shadow_color", "text_shadow_offset_x", "text_shadow_offset_y", "text_shadow_radius", "opacity"]);

  function loadFont(family, file) {
    const key = family + "|" + file;
    if (fonts.has(key)) return;
    fonts.add(key);
    try {
      const f = new FontFace(family, `url("${fileUrl(file)}")`);
      f.load().then((ff) => document.fonts.add(ff)).catch(() => {});
    } catch (e) { /* bad font: fall back to system */ }
  }

  // CSS for a style dict. `text` limits it to text keys (spans).
  function css(st, id, n, text) {
    const o = {};
    const tr = { tx: 0, ty: 0, rot: 0, sx: 1, sy: 1, any: false };
    const sh = {};
    const tsh = {};
    for (const k0 in st) {
      if (text && !TEXT_KEYS.has(k0)) continue;
      const v = resolve(st[k0], id);
      if (v == null) continue;
      const k = k0;
      let m;
      if (k === "display") o.display = v === "none" ? "none" : (n && n.type === "Text" ? "" : "flex");
      else if (k === "position") o.position = v;
      else if ((m = /^(top|right|bottom|left|start|end)$/.exec(k))) o[EDGE[m[1]]] = px(v);
      else if (k === "z_index") o.zIndex = String(Math.round(v));
      else if (k === "overflow") o.overflow = v === "scroll" ? "auto" : v;
      else if ((m = /^(min_|max_)?(width|height)$/.exec(k))) {
        o[(m[1] ? m[1].replace("_", "") : "") + (m[1] ? m[2][0].toUpperCase() + m[2].slice(1) : m[2])] = px(v);
      }
      else if (k === "aspect_ratio") o.aspectRatio = String(v);
      else if (k === "flex_grow") o.flexGrow = String(v);
      else if (k === "flex_shrink") o.flexShrink = String(v);
      else if (k === "flex_basis") o.flexBasis = px(v);
      else if (k === "flex_direction") o.flexDirection = kebab(v);
      else if (k === "flex_wrap") o.flexWrap = kebab(v);
      else if (k === "justify_content") o.justifyContent = kebab(v);
      else if (k === "align_items") o.alignItems = kebab(v);
      else if (k === "align_self") o.alignSelf = kebab(v);
      else if (k === "align_content") o.alignContent = kebab(v);
      else if (k === "row_gap") o.rowGap = px(v);
      else if (k === "column_gap") o.columnGap = px(v);
      else if ((m = /^(margin|padding)_(top|right|bottom|left|start|end)$/.exec(k))) {
        o[m[1] + EDGE[m[2]][0].toUpperCase() + EDGE[m[2]].slice(1)] = px(v);
      }
      else if ((m = /^border_(top|right|bottom|left|start|end)_width$/.exec(k)) || k === "border_width") {
        const sides = m ? [EDGE[m[1]]] : ["top", "right", "bottom", "left"];
        for (const s of sides) {
          const S = s[0].toUpperCase() + s.slice(1);
          o["border" + S + "Width"] = px(v);
          o["border" + S + "Style"] = (st.border_style || "solid");
        }
      }
      else if ((m = /^border_(top|right|bottom|left|start|end)_color$/.exec(k)) || k === "border_color") {
        const sides = m ? [EDGE[m[1]]] : ["top", "right", "bottom", "left"];
        for (const s of sides) o["border" + s[0].toUpperCase() + s.slice(1) + "Color"] = color(v);
      }
      else if ((m = /^border_(top|bottom)_(left|right|start|end)_radius$/.exec(k))) {
        const h = EDGE[m[2]];
        o["border" + m[1][0].toUpperCase() + m[1].slice(1) + h[0].toUpperCase() + h.slice(1) + "Radius"] = px(v);
      }
      else if (k === "border_radius") o.borderRadius = px(v);
      else if (k === "border_style") { /* used with widths */ }
      else if (k === "background_color") o.backgroundColor = color(v);
      else if (k === "linear_gradient") {
        const cs = v.colors || [], ss = v.stops;
        const parts = cs.map((c, i) => color(c) + (ss && ss[i] != null ? " " + (ss[i] * 100) + "%" : ""));
        o.backgroundImage = parts.length ? `linear-gradient(${v.angle == null ? 180 : v.angle}deg, ${parts.join(", ")})` : "";
      }
      else if (k === "opacity") o.opacity = String(v);
      else if ((m = /^shadow_(color|offset_x|offset_y|radius|opacity)$/.exec(k))) sh[m[1]] = v;
      else if (k === "elevation") sh.elevation = v;
      else if (k === "rotate") { tr.rot = typeof v === "number" ? v : parseFloat(v) || 0; tr.any = true; }
      else if (k === "scale") { tr.sx = tr.sy = v; tr.any = true; }
      else if (k === "scale_x") { tr.sx = v; tr.any = true; }
      else if (k === "scale_y") { tr.sy = v; tr.any = true; }
      else if (k === "translate_x") { tr.tx = v; tr.any = true; }
      else if (k === "translate_y") { tr.ty = v; tr.any = true; }
      else if (k === "color") o.color = color(v);
      else if (k === "font_size") o.fontSize = px(v);
      else if (k === "font_weight") o.fontWeight = v === "normal" ? "400" : v === "bold" ? "700" : String(v);
      else if (k === "font_style") o.fontStyle = v;
      else if (k === "font_family") {
        if (st.font_file) loadFont(v, st.font_file);
        o.fontFamily = v === "System" ? "" : `"${v}", -apple-system, BlinkMacSystemFont, sans-serif`;
      }
      else if (k === "line_height") o.lineHeight = px(v);
      else if (k === "letter_spacing") o.letterSpacing = px(v);
      else if (k === "text_align") o.textAlign = v === "auto" ? "" : v;
      else if (k === "text_decoration" || k === "text_decoration_line") o.textDecoration = v === "none" ? "none" : kebab(v);
      else if (k === "text_transform") o.textTransform = v;
      else if ((m = /^text_shadow_(color|offset_x|offset_y|radius)$/.exec(k))) tsh[m[1]] = v;
      else if (k === "number_of_lines" && n) n.lines = v;
    }
    if (sh.color != null || sh.radius != null || sh.offset_x != null || sh.offset_y != null) {
      const c = sh.color != null ? sh.color >>> 0 : 0xff000000;
      const op = sh.opacity != null ? sh.opacity : 1;
      const a = (((c >>> 24) & 255) / 255) * op;
      if (a > 0) {
        o.boxShadow = `${px(sh.offset_x || 0)} ${px(sh.offset_y || 0)} ${px(sh.radius || 0)} ` +
          `rgba(${(c >>> 16) & 255},${(c >>> 8) & 255},${c & 255},${+a.toFixed(3)})`;
      } else o.boxShadow = "none";
    } else if (sh.elevation) {
      const e = sh.elevation;
      o.boxShadow = `0 ${px(Math.round(e * 0.6))} ${px(Math.round(e * 1.4))} rgba(0,0,0,0.22)`;
    }
    if (tsh.color != null || tsh.radius != null) {
      o.textShadow = `${px(tsh.offset_x || 0)} ${px(tsh.offset_y || 0)} ${px(tsh.radius || 0)} ${color(tsh.color != null ? tsh.color : 0xff000000)}`;
    }
    if (tr.any) {
      const t = [];
      if (tr.tx || tr.ty) t.push(`translate(${tr.tx}px, ${tr.ty}px)`);
      if (tr.rot) t.push(`rotate(${tr.rot}deg)`);
      if (tr.sx !== 1 || tr.sy !== 1) t.push(`scale(${tr.sx}, ${tr.sy})`);
      o.transform = t.join(" ");
    }
    return o;
  }

  function applyStyle(n) {
    const el = n.el;
    const base = n.baseCss || "";
    el.style.cssText = base;
    n.lines = n.props.number_of_lines;
    const o = css(n.props.style || {}, n.id, n, false);
    Object.assign(el.style, o);
    if (n.type === "Text") {
      const lines = n.lines | 0;
      el.classList.toggle("clamp", lines > 0);
      el.style.webkitLineClamp = lines > 0 ? String(lines) : "";
    }
    if (n.type === "Modal") el.style.zIndex = el.style.zIndex || "1000";
  }

  // -- node creation ----------------------------------------------------------------------------
  const CLASS = { View: "v", Text: "t", Image: "img", ScrollView: "sv", NavStack: "ns", Button: "btn", Path: "path",
                  NativeSwitch: "sw", NativeSlider: "sl", NativeSpinner: "sp", Modal: "v" };

  function make(id, type) {
    let el;
    const n = { id, type, el: null, props: {}, children: [], parent: null };
    if (type === "Button") {
      el = document.createElement("button");
      el.addEventListener("click", () => emit("press", id));
    } else if (type === "TextInput") {
      el = document.createElement("div");  // replaced by input/textarea on first props
    } else {
      el = document.createElement("div");
    }
    el.className = CLASS[type] || "v";
    if (type === "ScrollView") {
      n.content = null;
      let last = 0, pending = null;
      el.addEventListener("scroll", () => {
        if (!n.props.on_scroll) return;
        const thr = Math.max(16, n.props.scroll_event_throttle || 16);
        const send = () => {
          last = performance.now(); pending = null;
          emit("scroll", id, { value: { x: el.scrollLeft, y: el.scrollTop, width: el.clientWidth, height: el.clientHeight,
                                        content_width: el.scrollWidth, content_height: el.scrollHeight } });
        };
        const dt = performance.now() - last;
        if (dt >= thr) send();
        else if (!pending) pending = setTimeout(send, thr - dt);
      }, { passive: true });
    } else if (type === "Image") {
      const img = document.createElement("img");
      img.draggable = false;
      img.addEventListener("load", () => emit("load", id, { value: { width: img.naturalWidth, height: img.naturalHeight } }));
      img.addEventListener("error", () => { if (img.getAttribute("src")) emit("error", id, { value: { message: "cannot load image" } }); });
      el.appendChild(img);
      n.img = img;
    } else if (type === "NativeSwitch") {
      el.addEventListener("click", () => {
        if (n.props.disabled) return;
        emit("value_change", id, { value: !n.props.value });
      });
    } else if (type === "NativeSlider") {
      const r = document.createElement("input");
      r.type = "range";
      r.addEventListener("input", () => emit("value_change", id, { value: parseFloat(r.value) }));
      r.addEventListener("change", () => emit("sliding_complete", id, { value: parseFloat(r.value) }));
      el.appendChild(r);
      n.range = r;
    } else if (type === "Path") {
      el.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet"><path/></svg>';
    }
    el._px = n;
    n.el = el;
    nodes.set(id, n);
    return n;
  }

  function makeInput(n) {
    const multi = !!n.props.multiline;
    if (n.input && n.multi === multi) return;
    const inp = document.createElement(multi ? "textarea" : "input");
    inp.className = "in";
    inp._px = n;
    const id = n.id;
    inp.addEventListener("input", () => emit("change_text", id, { value: inp.value }));
    inp.addEventListener("focus", () => {
      emit("focus", id);
      if (n.props.select_on_focus) setTimeout(() => inp.select(), 0);
    });
    inp.addEventListener("blur", () => emit("blur", id));
    inp.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !multi) { e.preventDefault(); emit("submit", id, { value: inp.value }); }
    });
    if (n.el && n.el.parentNode) n.el.parentNode.replaceChild(inp, n.el);
    n.el = inp; n.input = inp; n.multi = multi;
  }

  const KEYBOARD = { numeric: "numeric", "number-pad": "numeric", number_pad: "numeric", "decimal-pad": "decimal",
                     decimal_pad: "decimal", "email-address": "email", email_address: "email", email: "email",
                     "phone-pad": "tel", phone_pad: "tel", phone: "tel", url: "url" };

  function applyProps(n, props, removed) {
    for (const k of removed || []) delete n.props[k];
    Object.assign(n.props, props || {});
    const p = n.props;
    const el = n.el;
    switch (n.type) {
      case "Text": {
        if (p.spans) {
          el.textContent = "";
          for (const s of p.spans) {
            const sp = document.createElement("span");
            sp.textContent = s.text == null ? "" : String(s.text);
            Object.assign(sp.style, css(s.style || {}, n.id, null, true));
            el.appendChild(sp);
          }
        } else {
          const t = p.text == null ? "" : String(p.text);
          if (el.textContent !== t || el.children.length) el.textContent = t;
        }
        break;
      }
      case "Button":
        el.textContent = p.text == null ? "" : String(p.text);
        el.disabled = !!p.disabled;
        break;
      case "Image": {
        const s = p.source;
        const uri = typeof s === "string" ? s : s && s.uri;
        const url = srcUrl(uri);
        if (n.img.getAttribute("src") !== url) { if (url) n.img.setAttribute("src", url); else n.img.removeAttribute("src"); }
        const fit = { cover: "cover", contain: "contain", stretch: "fill", center: "scale-down", repeat: "none" };
        n.img.style.objectFit = fit[p.resize_mode] || "cover";
        if (p.tint_color != null && url) {
          n.img.style.visibility = "hidden";
          el.style.setProperty("--tint", color(p.tint_color));
          n.tint = url;
        } else { n.img.style.visibility = ""; n.tint = null; }
        break;
      }
      case "TextInput": {
        makeInput(n);
        const inp = n.input;
        if (p.value != null && inp.value !== String(p.value)) inp.value = String(p.value);
        inp.placeholder = p.placeholder || "";
        if (p.placeholder_color) inp.style.setProperty("--ph", p.placeholder_color);
        if (!n.multi) inp.type = p.secure ? "password" : (KEYBOARD[p.keyboard_type] === "email" ? "email" : "text");
        inp.inputMode = KEYBOARD[p.keyboard_type] || "text";
        inp.autocapitalize = p.auto_capitalize === "none" ? "off" : (p.auto_capitalize || "sentences");
        inp.spellcheck = p.auto_correct !== false;
        inp.setAttribute("autocomplete", p.auto_correct === false || p.secure ? "off" : "on");
        if (p.max_length != null) inp.maxLength = p.max_length; else inp.removeAttribute("maxlength");
        inp.readOnly = p.editable === false;
        if (p.auto_focus && !n.focused) { n.focused = true; setTimeout(() => inp.focus(), 0); }
        break;
      }
      case "NativeSwitch":
        el.classList.toggle("on", !!p.value);
        el.classList.toggle("off", !p.value);
        el.classList.toggle("dis", !!p.disabled);
        el.style.setProperty("--on", p.track_on != null ? color(p.track_on) : "#34c759");
        el.style.setProperty("--off", p.track_off != null ? color(p.track_off) : "#e5e5ea");
        el.style.setProperty("--thumb", color(p.value ? (p.thumb_on != null ? p.thumb_on : p.thumb_color) :
                                                       (p.thumb_off != null ? p.thumb_off : p.thumb_color)) || "#fff");
        break;
      case "NativeSlider": {
        const r = n.range;
        r.min = p.minimum != null ? p.minimum : 0;
        r.max = p.maximum != null ? p.maximum : 1;
        r.step = p.step ? p.step : "any";
        if (p.value != null && document.activeElement !== r) r.value = p.value;
        r.disabled = !!p.disabled;
        if (p.min_track_color != null) r.style.setProperty("--min", color(p.min_track_color));
        break;
      }
      case "NativeSpinner":
        el.style.color = p.color != null ? color(p.color) : "#8e8e93";
        el.classList.toggle("large", p.size === "large");
        el.classList.toggle("stopped", p.animating === false);
        break;
      case "Path": {
        const svg = el.firstChild, path = svg.firstChild;
        const vb = p.viewbox || 24;
        svg.setAttribute("viewBox", `0 0 ${vb} ${vb}`);
        let d = "";
        for (const c of p.path || []) {
          const a = c.slice(1).map((x) => +x);
          d += c[0] === 0 ? `M${a[0]} ${a[1]}` : c[0] === 1 ? `L${a[0]} ${a[1]}` : c[0] === 2 ? `C${a.join(" ")}` : "Z";
        }
        path.setAttribute("d", d);
        path.setAttribute("fill", p.fill != null ? color(p.fill) : "none");
        path.setAttribute("stroke", p.stroke != null ? color(p.stroke) : "none");
        path.setAttribute("stroke-width", p.stroke_width != null ? p.stroke_width : 1);
        path.setAttribute("stroke-linecap", "round");
        path.setAttribute("stroke-linejoin", "round");
        break;
      }
      case "ScrollView":
        el.classList.toggle("h", !!p.horizontal);
        el.classList.toggle("noind", p.shows_scroll_indicator === false);
        el.style.scrollSnapType = p.paging_enabled ? (p.horizontal ? "x mandatory" : "y mandatory") : "";
        break;
    }
    const pressable = !!(p.on_press || p.on_press_in || p.on_press_out || p.on_long_press);
    el.classList.toggle("press", pressable && n.type !== "Button");
    if (p.test_id) el.dataset.testid = p.test_id; else delete el.dataset.testid;
    if (p.accessibility_label) el.setAttribute("aria-label", p.accessibility_label); else el.removeAttribute("aria-label");
    applyStyle(n);
    if (n.type === "ScrollView") {
      const forced = { overflow: "", overflowX: "", overflowY: "" };
      if (p.scroll_enabled === false) forced.overflow = "hidden";
      Object.assign(el.style, forced);
    }
    if (n.type === "Image" && n.tint) {
      el.style.backgroundColor = "var(--tint)";
      el.style.webkitMaskImage = el.style.maskImage = `url("${n.tint}")`;
      el.style.webkitMaskSize = el.style.maskSize = n.img.style.objectFit === "fill" ? "100% 100%" : n.img.style.objectFit;
      el.style.webkitMaskRepeat = el.style.maskRepeat = "no-repeat";
      el.style.webkitMaskPosition = el.style.maskPosition = "center";
    }
    if (p.on_layout) observeLayout(n); else unobserveLayout(n);
    if (n.type === "ScrollView" && n.content) styleScrollContent(n);
  }

  function styleScrollContent(sv) {
    // A ScrollView's content view grows with its children along the scroll axis.
    const c = sv.content;
    if (!c) return;
    if (sv.props.horizontal) { c.el.style.flexShrink = "0"; c.el.style.minWidth = "100%"; c.el.style.alignSelf = "flex-start"; }
    else { c.el.style.flexShrink = "0"; c.el.style.minHeight = c.el.style.minHeight || ""; }
    if (sv.props.paging_enabled) for (const ch of c.children) ch.el.style.scrollSnapAlign = "start";
  }

  // -- layout events ----------------------------------------------------------------------------
  const ro = new ResizeObserver((entries) => { for (const e of entries) sendLayout(e.target._px); });
  function observeLayout(n) { if (!n.observed) { n.observed = true; ro.observe(n.el); requestAnimationFrame(() => sendLayout(n)); } }
  function unobserveLayout(n) { if (n.observed) { n.observed = false; ro.unobserve(n.el); } }
  function sendLayout(n) {
    if (!n || !n.props.on_layout || !n.el.isConnected) return;
    const el = n.el;
    const v = { x: el.offsetLeft, y: el.offsetTop, width: el.offsetWidth, height: el.offsetHeight };
    const k = `${v.x},${v.y},${v.width},${v.height}`;
    if (k === n.lastLayout) return;
    n.lastLayout = k;
    emit("layout", n.id, { value: v });
  }

  // -- tree ops ---------------------------------------------------------------------------------
  function insert(parentId, id, index, animate) {
    const p = parentId === 1 ? root : nodes.get(parentId);
    const c = nodes.get(id);
    if (!p || !c) return;
    if (c.parent) detach(c);
    const kids = p.children;
    index = Math.max(0, Math.min(index == null ? kids.length : index, kids.length));
    const before = kids[index];
    kids.splice(index, 0, c);
    c.parent = p;
    p.el.insertBefore(c.el, before ? before.el : null);
    if (p.type === "ScrollView") { p.content = c; styleScrollContent(p); }
    if (p.type === "NavStack") navChanged(p, animate && index === kids.length - 1 && kids.length > 1 ? c : null);
    if (c.observed) requestAnimationFrame(() => sendLayout(c));
  }

  function detach(c) {
    const p = c.parent;
    if (!p) return;
    const i = p.children.indexOf(c);
    if (i >= 0) p.children.splice(i, 1);
    c.parent = null;
    if (p.type === "ScrollView" && p.content === c) p.content = null;
    if (c.el.parentNode === p.el) p.el.removeChild(c.el);
  }

  function remove(parentId, id, animate) {
    const p = parentId === 1 ? root : nodes.get(parentId);
    const c = nodes.get(id);
    if (!p || !c) return;
    const wasTop = p.type === "NavStack" && p.children[p.children.length - 1] === c;
    if (wasTop && animate && p.props.animated !== false && p.children.length > 1) {
      // Pop: slide the old top out, then drop it.
      const i = p.children.indexOf(c);
      p.children.splice(i, 1);
      c.parent = null;
      navChanged(p, null);
      const el = c.el;
      el.classList.remove("push", "hidden");
      el.classList.add("pop");
      const done = () => { el.classList.remove("pop"); if (el.parentNode === p.el && !c.parent) p.el.removeChild(el); };
      el.addEventListener("animationend", done, { once: true });
      setTimeout(done, 400);
      return;
    }
    detach(c);
    if (p.type === "NavStack") navChanged(p, null);
  }

  function navChanged(ns, pushed) {
    const kids = ns.children;
    const top = kids[kids.length - 1];
    const under = kids[kids.length - 2];
    for (const k of kids) k.el.classList.toggle("hidden", k !== top && !(pushed && k === under));
    if (pushed && ns.props.animated !== false) {
      const el = pushed.el;
      el.classList.remove("push"); void el.offsetWidth; el.classList.add("push");
      el.addEventListener("animationend", () => {
        el.classList.remove("push");
        if (under && ns.children[ns.children.length - 1] !== under) under.el.classList.add("hidden");
      }, { once: true });
    }
  }

  function destroy(id) {
    const n = nodes.get(id);
    if (!n) return;
    unobserveLayout(n);
    if (n.parent) detach(n);
    nodes.delete(id);
  }

  const root = { id: 1, type: "View", el: rootEl, props: {}, children: [], parent: null };
  rootEl._px = root;

  function reset() {
    for (const n of nodes.values()) unobserveLayout(n);
    nodes.clear();
    bindings.clear();
    root.children = [];
    rootEl.textContent = "";
  }

  function applyOps(ops, initial) {
    for (const op of ops) {
      try {
        switch (op.op) {
          case "create": { const n = make(op.id, op.type); applyProps(n, op.props || {}, []); break; }
          case "update": { const n = op.id === 1 ? null : nodes.get(op.id); if (n) applyProps(n, op.props || {}, op.removed); break; }
          case "insert": insert(op.parent, op.id, op.index, !initial); break;
          case "remove": remove(op.parent, op.id, !initial); break;
          case "delete": destroy(op.id); break;
          case "call": jsCall(op); break;
        }
      } catch (e) { console.error("pyxpo op failed", op, e); }
    }
  }

  function applyValues(vals) {
    const dirty = new Set();
    for (const k in vals) {
      if (aval[k] === vals[k]) continue;
      aval[k] = vals[k];
      const s = bindings.get(k);
      if (s) for (const id of s) dirty.add(id);
    }
    for (const id of dirty) {
      const n = nodes.get(id);
      if (!n) continue;
      if (n.type === "Text" && n.props.spans) applyProps(n, {}, []);
      else applyStyle(n);
    }
  }

  // -- calls handled in the page ----------------------------------------------------------------
  function reply(op, value, error) {
    if (!op.reply) return;
    emit("call_result", op.id, error != null ? { error: String(error) } : { value: value === undefined ? null : value });
  }

  function jsCall(op) {
    const a = op.args || [];
    const m = op.module + "." + op.method;
    try {
      if (m === "Scroll.to" || m === "Scroll.scroll_to") {
        const n = nodes.get(a[0]);
        if (n) n.el.scrollTo({ left: a[1] || 0, top: a[2] || 0, behavior: a[3] === false ? "auto" : "smooth" });
        reply(op, null);
      } else if (m === "Scroll.to_end" || m === "Scroll.scroll_to_end") {
        const n = nodes.get(a[0]);
        if (n) n.el.scrollTo({ left: n.props.horizontal ? n.el.scrollWidth : 0, top: n.props.horizontal ? 0 : n.el.scrollHeight,
                               behavior: a[1] === false ? "auto" : "smooth" });
        reply(op, null);
      } else if (m === "Keyboard.dismiss") {
        if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
        reply(op, null);
      } else if (op.module === "Alert") {
        showAlert(a[0], a[1], a[2], (i) => reply(op, i));
      } else {
        reply(op, null);  // StatusBar, SplashScreen, Back, Vibration: nothing to do in a window
      }
    } catch (e) { reply(op, null, e); }
  }

  const alertQueue = [];
  function showAlert(title, message, labels, done) {
    alertQueue.push({ title, message, labels, done });
    if (alertQueue.length === 1) nextAlert();
  }
  function nextAlert() {
    const box = document.getElementById("alert");
    const cur = alertQueue[0];
    if (!cur) { box.classList.remove("show"); return; }
    box.querySelector("h3").textContent = cur.title == null ? "" : String(cur.title);
    const p = box.querySelector("p");
    p.textContent = cur.message == null ? "" : String(cur.message);
    p.style.display = cur.message ? "" : "none";
    const btns = box.querySelector(".btns");
    btns.textContent = "";
    const labels = cur.labels && cur.labels.length ? cur.labels : ["OK"];
    labels.forEach((l, i) => {
      const b = document.createElement("button");
      b.textContent = typeof l === "string" ? l : (l && l.text) || "OK";
      b.addEventListener("click", () => { alertQueue.shift(); cur.done(i); nextAlert(); });
      btns.appendChild(b);
    });
    box.classList.add("show");
  }

  // -- press and touch --------------------------------------------------------------------------
  function owner(el, test) {
    for (; el && el !== document.body; el = el.parentNode) {
      const n = el._px;
      if (n && n.props && test(n.props)) return n;
    }
    return null;
  }
  const isPress = (p) => p.on_press || p.on_press_in || p.on_press_out || p.on_long_press;
  const isTouch = (p) => p.on_touch_start || p.on_touch_move || p.on_touch_end;
  let press = null;
  let touch = null;

  function local(n, e) {
    const r = n.el.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }
  function touchPayload(n, e) {
    const l = local(n, e);
    return { value: { x: l.x, y: l.y, page_x: e.clientX, page_y: e.clientY } };
  }

  document.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    const t = e.target;
    if (t.closest && t.closest("input, textarea, button, #alert, .sw, .sl")) return;
    const tn = owner(t, isTouch);
    if (tn) {
      touch = { n: tn };
      if (tn.props.on_touch_start) emit("touch_start", tn.id, touchPayload(tn, e));
    }
    const n = owner(t, isPress);
    if (!n) return;
    const pos = local(n, e);
    press = { n, x: e.clientX, y: e.clientY, long: false, timer: null };
    if (n.props.on_long_press) {
      const cur = press;
      press.timer = setTimeout(() => { if (press === cur) { cur.long = true; emit("long_press", n.id); } }, 500);
    }
    emit("press_in", n.id, pos);
  });
  document.addEventListener("pointermove", (e) => {
    if (touch && touch.n.props.on_touch_move) emit("touch_move", touch.n.id, touchPayload(touch.n, e));
    if (!press) return;
    if (Math.hypot(e.clientX - press.x, e.clientY - press.y) > 10) {
      clearTimeout(press.timer);
      emit("press_out", press.n.id);
      press = null;
    }
  });
  function endPointer(e, cancel) {
    if (touch) { if (touch.n.props.on_touch_end) emit("touch_end", touch.n.id, touchPayload(touch.n, e)); touch = null; }
    if (!press) return;
    const p = press;
    press = null;
    clearTimeout(p.timer);
    emit("press_out", p.n.id);
    if (!cancel && !p.long && p.n.props.on_press) emit("press", p.n.id);
  }
  document.addEventListener("pointerup", (e) => endPointer(e, false));
  document.addEventListener("pointercancel", (e) => endPointer(e, true));
  // A wheel scroll during a press is a scroll, not a tap.
  document.addEventListener("wheel", () => { if (press) { clearTimeout(press.timer); emit("press_out", press.n.id); press = null; } },
                            { passive: true });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !document.getElementById("alert").classList.contains("show")) emit("hardware_back", 0);
  });

  // -- environment ------------------------------------------------------------------------------
  const dark = window.matchMedia("(prefers-color-scheme: dark)");
  function sendEnv() {
    emit("env", 0, {
      window: { width: window.innerWidth, height: window.innerHeight },
      screen: { width: screen.width, height: screen.height },
      scale: window.devicePixelRatio || 1,
      font_scale: 1,
      color_scheme: dark.matches ? "dark" : "light",
      insets: { top: 0, right: 0, bottom: 0, left: 0 },
    });
  }
  let envTimer = null;
  window.addEventListener("resize", () => { clearTimeout(envTimer); envTimer = setTimeout(sendEnv, 50); });
  dark.addEventListener("change", sendEnv);
  window.addEventListener("focus", sendEnv);  // several windows on one app: the focused one sets the size

  // -- stream from Python -----------------------------------------------------------------------
  const lost = document.getElementById("lost");
  let es = null, fails = 0;
  function connect() {
    es = new EventSource("/stream?t=" + encodeURIComponent(TOKEN));
    es.onopen = () => { fails = 0; lost.classList.remove("show"); };
    es.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.reset) { reset(); if (msg.aval) Object.assign(aval, msg.aval); applyOps(msg.ops || [], true); sendEnv(); return; }
      if (msg.ops) applyOps(msg.ops, false);
      if (msg.aval) applyValues(msg.aval);
    };
    es.onerror = () => {
      fails += 1;
      if (fails > 2) lost.classList.add("show");
    };
  }
  connect();
})();
