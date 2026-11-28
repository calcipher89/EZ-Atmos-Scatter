"""Easy sliders: a few artist-language sliders over the Atmosphere and Sun knobs.

build_gizmo.py stores this file base64-encoded in the hidden tool_code knob; knobChanged runs
it from there, so the node needs no Python module at the studio. Other tools (EzMatch) run it
the same way and call apply_easy / rebase, so they only ever move these sliders.

The sliders are relative to a base kept in the hidden easy_base knob (JSON): the knob values
the sliders started from. Every slider change rewrites the knobs from the base, so the knobs
always show exactly what the sliders did. Editing one of those knobs by hand makes the new
values the base and centres the sliders (exposure stays where it is).
"""
import json

import nuke

# (knob, neutral value)
SLIDERS = [("easy_exposure", 0.0), ("easy_sky", 1.0), ("easy_haze", 1.0), ("easy_warmth", 0.0),
           ("easy_glow", 1.0), ("easy_halo", 0.0)]
EASY_KNOBS = [name for name, _ in SLIDERS]
# The knobs the sliders write.
LOOK_KNOBS = ["sun_strength", "sky_light", "sky_amount", "haze_amount", "sun_color", "haze_glow_size", "aureole"]
# Brightness knobs: the base holds them without the exposure slider.
EXPOSED = ("sun_strength", "sky_light")


class _Busy(object):
    """While the sliders set knobs, knobChanged leaves them alone (the flag lives on the nuke
    module, the one thing that outlasts each knobChanged run)."""

    def __enter__(self):
        self.was = getattr(nuke, "_ezatmos_busy", False)
        nuke._ezatmos_busy = True

    def __exit__(self, *args):
        nuke._ezatmos_busy = self.was


def busy():
    return getattr(nuke, "_ezatmos_busy", False)


def _value(n, name):
    v = n[name].value()
    if isinstance(v, (list, tuple)):
        return list(v)
    if name == "sun_color":
        # A Color_Knob reads back as one number while its channels are equal.
        return [v, v, v]
    return v


def _store(n, exposure_in_knobs=True):
    e = 2.0 ** n["easy_exposure"].value() if exposure_in_knobs else 1.0
    base = dict((k, _value(n, k)) for k in LOOK_KNOBS)
    for k in EXPOSED:
        base[k] = base[k] / e
    with _Busy():
        n["easy_base"].setValue(json.dumps(base))
    return base


def rebase(n, centre=True):
    """Make the knobs' current values the base, and centre the sliders (exposure stays)."""
    _store(n)
    if centre:
        with _Busy():
            for name, neutral in SLIDERS:
                if name != "easy_exposure":
                    n[name].setValue(neutral)


def _base(n):
    try:
        b = json.loads(n["easy_base"].value() or "{}")
    except ValueError:
        b = {}
    if not all(k in b for k in LOOK_KNOBS):
        # Never set up: the knobs still hold the look the slider just moved away from.
        b = _store(n, exposure_in_knobs=False)
    return b


def apply_easy(n):
    """Rewrite the knobs from the base and the sliders."""
    b = _base(n)
    e = dict((name, n[name].value()) for name, _ in SLIDERS)
    gain = 2.0 ** e["easy_exposure"]
    w = max(-1.0, min(1.0, e["easy_warmth"]))
    with _Busy():
        # Exposure: the sun and the sky light together, in stops.
        n["sun_strength"].setValue(b["sun_strength"] * gain)
        n["sky_light"].setValue(b["sky_light"] * gain)
        # Sky: the air (bluer, brighter sky). Haze: the Mie haze (whiter, thicker air).
        n["sky_amount"].setValue(max(b["sky_amount"] * e["easy_sky"], 0.0))
        n["haze_amount"].setValue(max(b["haze_amount"] * e["easy_haze"], 0.0))
        # Warmth: an orange or blue tint on the sun.
        tint = (1.0 + 0.4 * w, 1.0 + 0.05 * w, 1.0 - 0.4 * w)
        n["sun_color"].setValue([c * t for c, t in zip(b["sun_color"], tint)])
        # Glow: the size of the haze glow round the sun. Halo: spreads a share of it wide.
        n["haze_glow_size"].setValue(min(max(b["haze_glow_size"] * e["easy_glow"], 0.0), 4.0))
        n["aureole"].setValue(min(max(b["aureole"] + e["easy_halo"], 0.0), 1.0))


# Starting looks: knob values a look sets before the Easy sliders (and EzMatch) take over.
# Aerial Sunset: from high above toward a low sun (the Rocky sunset r27 sky): a thicker, taller
# haze layer, so a camera km over the land still looks through haze, and a bigger glow.
# Each look has a row per role, which the node works out from its own wiring (look_role): "sky"
# draws the sky (or lights EzCloudGen), "haze" feeds EzDepthHaze's atmos input (a thinner haze light
# and a smaller glow), "light" is a Lat-long node lighting the terrain.
LOOKS = {
    "Aerial Sunset": {"sky": {"haze_amount": 4.0, "haze_height": 2.0, "haze_glow_size": 1.5},
                      "haze": {"haze_amount": 2.0, "haze_height": 2.0, "haze_glow_size": 0.5},
                      "light": {"haze_amount": 2.0, "haze_height": 2.0, "haze_glow_size": 1.5}},
    # Aerial Day: a fair-weather day from high above. A little more, taller haze than the
    # defaults, so the far land still sits in air from a camera km up (planner r19 GUESS, to be
    # tuned once on our demo fair-weather render).
    "Aerial Day": {"sky": {"haze_amount": 1.5, "haze_height": 1.5, "haze_glow_size": 1.0},
                   "haze": {"haze_amount": 1.0, "haze_height": 1.5, "haze_glow_size": 0.5},
                   "light": {"haze_amount": 1.0, "haze_height": 1.5, "haze_glow_size": 1.0}},
}
LOOK_NAMES = sorted(LOOKS)
ROLE_NAMES = {"sky": "sky", "haze": "haze light", "light": "lighting lat-long"}
PASS_THROUGH = ("Dot", "NoOp")
ROLE_HOPS = 6


def _feeds_depth_haze(n, hops):
    if hops <= 0:
        return False
    for d in n.dependent(nuke.INPUTS | nuke.HIDDEN_INPUTS, forceEvaluate=False):
        if d.knob("easy_haze") is not None and d.knob("easy_fog") is not None:
            return True
        if d.Class() in PASS_THROUGH and _feeds_depth_haze(d, hops - 1):
            return True
    return False


def look_role(n):
    """'light' for a Lat-long node, 'haze' when it feeds an EzDepthHaze (through Dots), else 'sky'."""
    try:
        if n.knob("output_mapping") is not None and n["output_mapping"].value() == "Lat-long":
            return "light"
        return "haze" if _feeds_depth_haze(n, ROLE_HOPS) else "sky"
    except Exception:
        return "sky"


def apply_look(n, name=None):
    """Set the picked starting look's knobs for this node's role, then make them the Easy
    sliders' base (centred). Returns 'look (role)', or None for an unknown look."""
    name = name or (n["easy_look"].value() if n.knob("easy_look") is not None else None)
    if name not in LOOKS:
        return None
    role = look_role(n)
    with _Busy():
        for k, v in LOOKS[name][role].items():
            n[k].setValue(v)
    rebase(n)
    return "%s (%s)" % (name, ROLE_NAMES[role])


def on_knob(n, k):
    """knobChanged, for a knob the sliders look after."""
    if busy():
        return
    if k in EASY_KNOBS:
        apply_easy(n)
    elif k in LOOK_KNOBS:
        # Tuned by hand: that becomes the sliders' starting point.
        rebase(n)
