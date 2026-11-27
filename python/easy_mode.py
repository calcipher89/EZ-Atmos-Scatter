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
LOOK_KNOBS = ["sun_strength", "sky_light", "sky_amount", "haze_amount", "haze_height", "sun_color", "haze_glow_size",
              "aureole"]
# The haze slider also raises or lowers the haze layer: haze height = base x haze ^ this power
# (the haze clamped to 0.25-4, so 0.5x to 2x the base height). At a high camera the layer's height
# matters more than its amount (planner r14: 1.2 -> 2 km is about 4x the haze at a 4.1 km camera).
# 0 turns it off.
HAZE_HEIGHT_POWER = 0.5
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
    if b and "haze_height" not in b and all(k in b for k in LOOK_KNOBS if k != "haze_height"):
        # A base stored before the haze slider moved the haze height: the knob still holds its base.
        b["haze_height"] = _value(n, "haze_height")
        with _Busy():
            n["easy_base"].setValue(json.dumps(b))
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
        # ... and a taller (or lower) haze layer with it.
        hz = max(0.25, min(4.0, e["easy_haze"]))
        n["haze_height"].setValue(min(max(b["haze_height"] * hz ** HAZE_HEIGHT_POWER, 0.1), 10.0))
        # Warmth: an orange or blue tint on the sun.
        tint = (1.0 + 0.4 * w, 1.0 + 0.05 * w, 1.0 - 0.4 * w)
        n["sun_color"].setValue([c * t for c, t in zip(b["sun_color"], tint)])
        # Glow: the size of the haze glow round the sun. Halo: spreads a share of it wide.
        n["haze_glow_size"].setValue(min(max(b["haze_glow_size"] * e["easy_glow"], 0.0), 4.0))
        n["aureole"].setValue(min(max(b["aureole"] + e["easy_halo"], 0.0), 1.0))


def on_knob(n, k):
    """knobChanged, for a knob the sliders look after."""
    if busy():
        return
    if k in EASY_KNOBS:
        apply_easy(n)
    elif k in LOOK_KNOBS:
        # Tuned by hand: that becomes the sliders' starting point.
        rebase(n)
