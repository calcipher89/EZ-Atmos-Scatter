"""Easy sliders without Nuke: runs python/easy_mode.py against a stand-in node.

    python3 tests/test_easy_mode.py
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))


class Knob(object):
    def __init__(self, v):
        self.v = v

    def value(self):
        return self.v

    def setValue(self, v):
        self.v = v


class Node(dict):
    def __getitem__(self, k):
        return dict.__getitem__(self, k)

    def vals(self, *ks):
        return [round(v, 4) if not isinstance(v, list) else [round(c, 4) for c in v]
                for v in (self[k].v for k in ks)]


def main():
    sys.modules["nuke"] = types.ModuleType("nuke")
    ns = {}
    with open(os.path.join(HERE, "..", "python", "easy_mode.py")) as f:
        exec(f.read(), ns)
    n = Node()
    for k, v in (("sun_strength", 1.0), ("sky_light", 1.0), ("sky_amount", 1.0), ("haze_amount", 2.0),
                 ("haze_height", 1.2), ("sun_color", 1.0), ("haze_glow_size", 1.0), ("aureole", 0.0), ("easy_base", "")):
        n[k] = Knob(v)
    for k, v in ns["SLIDERS"]:
        n[k] = Knob(v)
    ok = True

    def check(what, got, want):
        good = got == want
        print("%-40s %s %s" % (what, got, "ok" if good else "WANT %s" % (want,)))
        return good

    # First move with no base: exposure must not be divided out of knobs that never had it.
    n["easy_exposure"].v = 1.0
    ns["on_knob"](n, "easy_exposure")
    ok &= check("exposure +1", n.vals("sun_strength", "sky_light"), [2.0, 2.0])
    n["easy_haze"].v = 1.5
    n["easy_warmth"].v = 0.5
    n["easy_halo"].v = 0.4
    for k in ("easy_haze", "easy_warmth", "easy_halo"):
        ns["on_knob"](n, k)
    ok &= check("haze 1.5, warmth .5, halo .4", n.vals("haze_amount", "sun_color", "aureole"),
                [3.0, [1.2, 1.025, 0.8], 0.4])
    ok &= check("haze 1.5 raises the haze height", n.vals("haze_height"), [round(1.2 * 1.5 ** 0.5, 4)])
    n["easy_haze"].v = 1.0
    ns["on_knob"](n, "easy_haze")
    ok &= check("haze back to neutral: base height exactly", n.vals("haze_amount", "haze_height"), [2.0, 1.2])
    n["easy_haze"].v = 8.0
    ns["on_knob"](n, "easy_haze")
    ok &= check("haze 8: height capped at 2x", n.vals("haze_height"), [2.4])
    n["easy_haze"].v = 1.5
    ns["on_knob"](n, "easy_haze")
    # Hand edit: becomes the base, sliders centre, exposure kept.
    n["haze_amount"].v = 5.0
    ns["on_knob"](n, "haze_amount")
    ok &= check("hand edit centres sliders", n.vals("easy_haze", "easy_warmth", "easy_halo", "easy_exposure"),
                [1.0, 0.0, 0.0, 1.0])
    n["easy_exposure"].v = 0.0
    ns["on_knob"](n, "easy_exposure")
    ok &= check("exposure back to 0", n.vals("sun_strength", "haze_amount", "aureole"), [1.0, 5.0, 0.4])
    n["easy_glow"].v = 10.0
    ns["on_knob"](n, "easy_glow")
    ok &= check("glow clamps to the knob range", n.vals("haze_glow_size"), [4.0])
    # A base stored before 1.3.0 (no haze height) with the haze slider off neutral: the knob's
    # height is its base, nothing else moves.
    import json as _json
    old = _json.loads(n["easy_base"].v)
    old.pop("haze_height")
    n["easy_base"].v = _json.dumps(old)
    n["haze_height"].v = 1.5
    n["easy_haze"].v = 2.0
    ns["on_knob"](n, "easy_haze")
    ok &= check("old base: height from the knob, amount from the base",
                n.vals("haze_height", "haze_amount"), [round(1.5 * 2.0 ** 0.5, 4), round(old["haze_amount"] * 2.0, 4)])
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
