// pyxpo-video in the browser and the desktop window: a <video> element.
// The page loads this file after app.js (see pyxpoPage in app.js).
(function () {
  "use strict";

  const FIT = { contain: "contain", cover: "cover", stretch: "fill" };

  function url(src) {
    if (/^(https?:|data:|blob:)/.test(src)) return src;
    return window.pyxpoPage.fileUrl(src) || "";
  }

  function makeView(el, emit) {
    const v = document.createElement("video");
    v.playsInline = true;
    v.preload = "metadata";
    v.style.cssText = "width:100%;height:100%;display:block;object-fit:contain;background:#000";
    el.style.overflow = "hidden";
    el.appendChild(v);
    let source = null, playing = true;

    const play = () => { const p = v.play(); if (p && p.catch) p.catch(() => {}); };
    v.addEventListener("loadedmetadata", () => emit("load", {
      duration: isFinite(v.duration) ? v.duration : 0, width: v.videoWidth, height: v.videoHeight,
    }));
    v.addEventListener("ended", () => emit("end", null));
    v.addEventListener("error", () => {
      if (source) emit("error", { message: (v.error && v.error.message) || "cannot play the video" });
    });

    return {
      update(props) {
        if ("loop" in props) v.loop = !!props.loop;
        if ("muted" in props) v.muted = !!props.muted;
        if ("controls" in props) v.controls = !!props.controls;
        if ("resize_mode" in props) v.style.objectFit = FIT[props.resize_mode] || "contain";
        const src = "source" in props ? props.source || null : source;
        if (src !== source) {
          source = src;
          if (source) v.src = url(source); else v.removeAttribute("src");
          v.load();
        }
        if ("playing" in props) playing = !!props.playing;
        if ("playing" in props || "source" in props) { if (playing && source) play(); else v.pause(); }
      },
      play() { if (source) play(); },
      pause() { v.pause(); },
      seek(seconds) { v.currentTime = seconds; },
      dispose() { v.pause(); v.removeAttribute("src"); v.load(); v.remove(); },
    };
  }

  pyxpoPage.defineView("PxVideoView", makeView);
  pyxpoPage.defineModule("Video", (method, args, page) => {
    const v = page.view(args[0]);
    if (!v) throw new Error("The VideoView is not mounted");
    switch (method) {
      case "play": return v.play();
      case "pause": return v.pause();
      case "seek": return v.seek(args[1] || 0);
      default: throw new Error("Video has no method " + method);
    }
  });
})();
