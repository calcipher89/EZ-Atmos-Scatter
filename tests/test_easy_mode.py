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

    def knob(self, k):
        return self.get(k)

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
                 ("sun_color", 1.0), ("haze_glow_size", 1.0), ("aureole", 0.0), ("easy_base", "")):
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
    # Starting look: its knobs set, sliders centred on them.
    n["easy_haze"].v = 2.0
    for k in ("haze_height",):
        n[k] = Knob(1.2)
    n["easy_look"] = Knob("Aerial Sunset")
    ns["apply_look"](n)
    ok &= check("Aerial Sunset: haze 4, height 2, glow 1.5, sliders centred",
                n.vals("haze_amount", "haze_height", "haze_glow_size", "easy_haze"), [4.0, 2.0, 1.5, 1.0])
    n["easy_haze"].v = 1.5
    ns["on_knob"](n, "easy_haze")
    ok &= check("then haze 1.5 multiplies the look's haze", n.vals("haze_amount"), [6.0])
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
