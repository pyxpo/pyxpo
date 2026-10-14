"""Regenerate anim_golden.json from the Python reference engine. Native ports (Kotlin/Swift) check against it."""
import json
import os

from pyxpo.animated import easing, engine

E = [{"e": n} for n in ("linear", "ease", "quad", "cubic", "sin", "exp", "circle", "bounce")]
E += [{"e": "poly", "n": 4}, {"e": "back", "s": 1.70158}, {"e": "elastic", "b": 1.0},
      {"e": "bezier", "p": [0.25, 0.1, 0.25, 1.0]}, {"e": "out", "f": {"e": "cubic"}},
      {"e": "in_out", "f": {"e": "bounce"}}, {"e": "in", "f": {"e": "back", "s": 1.70158}}]
TS = [0, 0.1, 0.25, 0.5, 0.75, 0.9, 1]
out = {"easing": [{"spec": s, "t": TS, "v": [easing.fn(s)(t) for t in TS]} for s in E]}
out["interp"] = [
    {"x": x, "in": [0, 1, 2], "out": [0, 10, 40], "ex": ["extend", "clamp"],
     "v": engine.interpolate(x, [0, 1, 2], [0, 10, 40], "extend", "clamp", None, False)}
    for x in (-1, 0, 0.5, 1.5, 3)]
out["interp_color"] = [
    {"x": x, "in": [0, 1], "out": [0xFFFF0000, 0xFF0000FF],
     "v": engine.interpolate(x, [0, 1], [0xFFFF0000, 0xFF0000FF], "clamp", "clamp", None, True)}
    for x in (0, 0.3, 1)]
DT = [0, 16, 100, 250, 500, 1000, 2000]
out["spring"] = [
    {"k": k, "c": c, "m": m, "x0": 0, "v0": v0, "dt": DT,
     "v": [engine.spring_at(t / 1000.0, 0.0, v0, k, c, m) for t in DT]}
    for k, c, m, v0 in ((100, 10, 1, 0), (100, 20, 1, 0), (100, 40, 1, 0), (200, 5, 2, 50))]
json.dump(out, open(os.path.join(os.path.dirname(__file__), "anim_golden.json"), "w"), indent=1)
