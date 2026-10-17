// pyxpo web boot: loads Pyodide, unpacks the app bundle into its file system, wires the page bridge for app.js
// and runs the app. window.PYXPO_CONFIG comes from index.html (written by `pyxpo build web`).
(async () => {
  "use strict";
  const cfg = window.PYXPO_CONFIG;
  const BASE = cfg.base || "";
  const status = document.getElementById("lost");
  const show = (text) => { status.textContent = text; status.classList.add("show"); };

  function script(src) {
    return new Promise((ok, fail) => {
      const s = document.createElement("script");
      s.src = src;
      s.onload = ok;
      s.onerror = () => fail(new Error("could not load " + src));
      document.head.appendChild(s);
    });
  }
  async function fetchBytes(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(url + ": HTTP " + r.status);
    return r.arrayBuffer();
  }

  // Documents (pyxpo-file-system, pyxpo-sqlite) and pyxpo-storage outlive a reload: IndexedDB holds the folders,
  // copied in before the app starts and written back a moment after files change and when the page is hidden.
  // The cache folder stays in memory. Tabs of one site share the data; the last one to write wins.
  async function keepData(py, dirs) {
    const FS = py.FS;
    const sync = (load) => new Promise((ok) => FS.syncfs(load, (err) => {
      if (err) console.warn("pyxpo: could not " + (load ? "load" : "save") + " app data", err);
      ok();
    }));
    try {
      for (const d of dirs) { FS.mkdirTree(d); FS.mount(FS.filesystems.IDBFS, {}, d); }
    } catch (e) {
      console.warn("pyxpo: app data is kept only until the page closes", e);
      return () => Promise.resolve();
    }
    await sync(true);
    let busy = null, again = false;
    const save = () => {
      if (busy) { again = true; return busy; }
      busy = sync(false).then(() => { busy = null; if (again) { again = false; return save(); } });
      return busy;
    };
    setInterval(save, 2000);   // syncfs only writes the files whose mtime changed
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") save(); });
    window.addEventListener("pagehide", save);
    return save;
  }

  const MIME = { png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", gif: "image/gif", webp: "image/webp",
                 svg: "image/svg+xml", bmp: "image/bmp", ico: "image/x-icon", heic: "image/heic" };

  try {
    show("Loading…");
    const bundle = fetchBytes(BASE + "/" + cfg.bundle);  // in parallel with the runtime download
    await script(cfg.pyodide + "pyodide.js");
    const py = await loadPyodide({ indexURL: cfg.pyodide });
    if (cfg.packages && cfg.packages.length) {
      await py.loadPackage("micropip");
      await py.pyimport("micropip").install(cfg.packages);
    }
    py.unpackArchive(await bundle, "zip", { extractDir: "/app" });
    const persist = await keepData(py, ["/app/.pyxpo-data/documents", "/app/.pyxpo-data/storage"]);

    // Images the app writes or bundles live in Pyodide's in-memory file system: hand them to <img> as blob URLs,
    // made again when the file changes.
    const blobs = new Map();
    window.PYXPO_WEB = {
      base: BASE,
      persist,   // writes app data to IndexedDB now (a Promise)
      send(body) { if (window.pyxpoPy) window.pyxpoPy(body); },
      fileUrl(path) {
        let st;
        try { st = py.FS.stat(path); } catch (e) { return ""; }
        const stamp = +st.mtime + ":" + st.size;
        const hit = blobs.get(path);
        if (hit && hit.stamp === stamp) return hit.url;
        if (hit) URL.revokeObjectURL(hit.url);
        const ext = (path.split(".").pop() || "").toLowerCase();
        const url = URL.createObjectURL(new Blob([py.FS.readFile(path)], { type: MIME[ext] || "application/octet-stream" }));
        blobs.set(path, { stamp, url });
        return url;
      },
    };
    await script(BASE + "/app.js?v=" + cfg.version);
    for (const src of cfg.scripts || []) await script(BASE + "/" + src + "?v=" + cfg.version);  // module web.js

    let path = location.pathname;
    if (BASE && path.startsWith(BASE)) path = path.slice(BASE.length) || "/";
    const env = {
      os: "web",
      window: { width: window.innerWidth, height: window.innerHeight },
      screen: { width: screen.width, height: screen.height },
      scale: window.devicePixelRatio || 1,
      font_scale: 1,
      color_scheme: window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light",
      insets: { top: 0, right: 0, bottom: 0, left: 0 },
      initial_url: location.origin + path + location.search,
    };
    if (window.PYXPO_DEVICE) Object.assign(env, window.PYXPO_DEVICE());  // dev tools: emulated device
    py.FS.chdir("/app");
    py.globals.set("PYXPO_BOOT_ENV", JSON.stringify(env));
    await py.runPythonAsync(
      "import sys\nsys.path.insert(0, '/app')\nfrom pyxpo.renderers.web.browser import boot\nboot(PYXPO_BOOT_ENV)\n");
    status.classList.remove("show");
    window.pyxpoPyodide = py;
  } catch (e) {
    console.error(e);
    show("Could not start the app: " + (e && e.message ? e.message.split("\n").filter(Boolean).pop() : e));
  }
})();
