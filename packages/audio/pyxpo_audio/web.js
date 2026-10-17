// pyxpo-audio in the browser and the desktop window: one HTML audio element per player id Python gives.
// The page loads this file after app.js (see pyxpoPage in app.js).
(function () {
  "use strict";

  const players = new Map();   // id -> {el, wants}

  function url(src, page) {
    if (/^(https?|blob|data):/.test(src)) return src;
    if (src.startsWith("file://")) src = decodeURIComponent(src.slice(7));
    return page.fileUrl(src);
  }

  function start(p) {
    const r = p.el.play();
    // Browsers refuse sound before the first tap on the page; the next play() works.
    if (r && r.catch) r.catch((e) => console.warn("pyxpo-audio:", e.message));
  }

  // A hidden tab pauses the sound and plays it on when it shows again, as the native apps do.
  document.addEventListener("visibilitychange", () => {
    for (const p of players.values()) {
      if (!p.wants) continue;
      if (document.hidden) p.el.pause(); else start(p);
    }
  });

  pyxpoPage.defineModule("Audio", (method, args, page) => {
    const id = args[0];
    const p = players.get(id);
    switch (method) {
      case "create": {
        if (p) p.el.pause();
        const el = new Audio(url(args[1], page));
        el.preload = "auto";
        el.loop = !!args[2];
        el.volume = args[3] == null ? 1 : args[3];
        players.set(id, { el, wants: false });
        return null;
      }
      case "play":
        if (p) {
          p.wants = true;
          if (p.el.ended) p.el.currentTime = 0;
          start(p);
        }
        return null;
      case "pause":
        if (p) { p.wants = false; p.el.pause(); }
        return null;
      case "seek":
        if (p) p.el.currentTime = args[1];
        return null;
      case "set": {
        const o = args[1] || {};
        if (p && "loop" in o) p.el.loop = !!o.loop;
        if (p && "volume" in o) p.el.volume = o.volume;
        return null;
      }
      case "release":
        if (p) {
          p.el.pause();
          p.el.removeAttribute("src");
          p.el.load();
          players.delete(id);
        }
        return null;
    }
    throw new Error("unknown native call Audio." + method);
  });
})();
