"""Build gizmos/EzAtmosScatter.gizmo from the kernels in blink/.

Run from a terminal (NukeX licence, -i so BlinkScript can compile):

    Nuke15.1.exe --nukex -i -t python/build_gizmo.py

or paste into the Script Editor of an empty script. The group it builds has two inputs
(the lat-long HDRI and an optional sun Axis) and a single panel of plain-named knobs that
drive every BlinkScript node inside.
"""

import os

import nuke

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLINK = os.path.join(ROOT, "blink")
GIZMO_PATH = os.path.join(ROOT, "gizmos", "EzAtmosScatter.gizmo")

LAYERS = ["atmos_inscatter", "atmos_rayleigh", "atmos_mie", "atmos_ambient", "atmos_transmittance",
          "atmos_haze_color", "atmos_haze_sun", "atmos_haze_sky"]

VIEW_OUTPUTS = [
    # (menu label, node feeding the main rgba)
    ("Scatter Preview Comp", "comp"),
    ("Scatter", "inscatter"),
    ("Sky (Rayleigh)", "rayleigh"),
    ("Haze (Mie)", "mie"),
    ("Sky Light (Ambient)", "ambient"),
    ("Transmittance", "transmittance"),
    ("Haze Color", "haze_color"),
    ("Haze Preview", "haze_preview"),
]

# Kernel output index for each pass (see AtmosScatter.blink), and the layer it goes to.
PASSES = [("rayleigh", 1, "atmos_rayleigh"),
          ("mie", 2, "atmos_mie"),
          ("transmittance", 3, "atmos_transmittance"),
          ("ambient", 5, "atmos_ambient"),
          ("haze_color", 8, "atmos_haze_color"),
          ("haze_sun", 10, "atmos_haze_sun"),
          ("haze_sky", 11, "atmos_haze_sky"),
          ("haze_transmittance", 9, None)]

# Extinction per metre at camera height, per channel; matches the kernel's local
# coefficients. Used by the read-only 'haze density' knob.
HAZE_DENSITY = ("(rayleigh_coefficients.{c} * sky_amount * exp(-camera_height / 1000 / rayleigh_scale_height)"
                " + mie_coefficient * haze_amount / 0.9 * exp(-camera_height / 1000 / haze_height)) / 1000")

SUN_FROM_AXIS = "parent.input1.world_matrix.%d"


def _load_kernel(node, filename):
    # Setting kernelSource from Python does not rebuild the parameter knobs; loading the
    # file does. Clear the path afterwards so the gizmo carries its own copy of the source.
    node["kernelSourceFile"].setValue(os.path.join(BLINK, filename).replace("\\", "/"))
    node["reloadKernelSourceFile"].execute()
    node["recompile"].execute()
    node["kernelSourceFile"].setValue("")


def _link(node, param, expression, channel=None):
    knob = node["%s_%s" % (node["kernelName"].value(), param)]
    if channel is None:
        knob.setExpression(expression)
    else:
        knob.setExpression(expression, channel)


# Names of the user knobs, filled in by _add_knobs; the bake fingerprint covers them.
_USER_KNOBS = set()


def _add_knobs(group):
    k = []

    k.append(nuke.Tab_Knob("ezatmos", "EzAtmosScatter"))
    view = nuke.Enumeration_Knob("view_output", "view output", [label for label, _ in VIEW_OUTPUTS])
    view.setTooltip("What the main rgba shows. Every pass is also written to its own atmos_* layer.")
    k.append(view)
    passes = nuke.Enumeration_Knob("passes", "passes", ["Atmosphere", "Depth Haze"])
    passes.setTooltip("Atmosphere: every ray runs through the whole sky down to the ground, as seen from the "
                      "camera. Depth Haze: Scatter, Sky, Haze, Sky Light and Transmittance describe the haze "
                      "around the camera out to 'haze distance', with no ground and no horizon line, for hazing "
                      "a plate. Composite either with plate * transmittance + scatter.")
    k.append(passes)

    k.append(nuke.Text_Knob("sun_divider", "Sun"))
    sun_from = nuke.Enumeration_Knob("sun_from", "sun from", ["Auto (HDRI)", "Axis", "Manual"])
    sun_from.setTooltip("Auto finds the sun in the HDRI. Axis points at the Axis node plugged into the "
                        "'sun' input (its world position). Manual uses 'sun direction'.")
    k.append(sun_from)
    sun_dir = nuke.XYZ_Knob("sun_direction", "sun direction")
    sun_dir.setTooltip("Direction towards the sun, +Y up. Used when 'sun from' is Manual.")
    k.append(sun_dir)
    grab = nuke.PyScript_Knob("use_detected_sun", "copy detected sun to manual",
                              "import ezatmosscatter; ezatmosscatter.copy_detected_sun(nuke.thisNode())")
    grab.setTooltip("Writes the sun direction found in the HDRI into 'sun direction'.")
    k.append(grab)
    rotation = nuke.Double_Knob("hdri_rotation", "hdri rotation")
    rotation.setRange(-180, 180)
    rotation.setTooltip("Rotates the lat-long mapping in degrees, if the HDRI's centre column does not look down -Z.")
    k.append(rotation)

    self_lit = nuke.Boolean_Knob("self_lit", "self-lit (no HDRI)")
    self_lit.setTooltip("For setups without an HDRI: the sky light comes from this atmosphere's own sky "
                        "instead of the hdri input, and the sun from 'sun color' and 'sun strength' "
                        "(light from HDRI is ignored). Set 'sun from' to Manual or Axis.")
    self_lit.setFlag(nuke.STARTLINE)
    k.append(self_lit)
    light = nuke.Boolean_Knob("light_from_hdri", "light from HDRI")
    light.setFlag(nuke.STARTLINE)
    light.setTooltip("Take the sun's colour and brightness from the HDRI. Off: 'sun color' and "
                     "'sun strength' set them directly.")
    k.append(light)
    color = nuke.Color_Knob("sun_color", "sun color")
    color.setTooltip("Tint on the HDRI's sun, or the sun colour itself when 'light from HDRI' is off.")
    k.append(color)
    strength = nuke.Double_Knob("sun_strength", "sun strength")
    strength.setRange(0, 4)
    strength.setTooltip("Multiplies the sun's brightness.")
    k.append(strength)
    boost = nuke.Double_Knob("sun_boost", "sun boost")
    boost.setRange(0, 4)
    boost.setTooltip("Only used when the HDRI's sun is clipped (JPEGs, LDR captures). The sun is then "
                     "sized from the sky brightness; this scales it.")
    k.append(boost)
    sky_light = nuke.Double_Knob("sky_light", "sky light")
    sky_light.setRange(0, 2)
    sky_light.setTooltip("Light from the whole HDRI sky scattered into the haze. Fills in what a single "
                         "bounce from the sun misses.")
    k.append(sky_light)

    k.append(nuke.Text_Knob("atmos_divider", "Atmosphere"))
    for name, label, lo, hi, tip in [
            ("sky_amount", "sky amount", 0, 4, "Density of the air (Rayleigh). More gives a bluer, brighter sky."),
            ("haze_amount", "haze amount", 0, 10, "Density of the haze (Mie). More gives whiter, thicker air."),
            ("haze_glow_size", "haze glow size", 0, 4, "Size of the glow around the sun. Bigger spreads it wider."),
            ("haze_height", "haze height (km)", 0.1, 10, "Height over which the haze thins out by about two thirds "
             "(its scale height). Low keeps it near the ground, so looking up clears quickly; high fills the "
             "air evenly around the camera."),
            ("camera_height", "camera height (m)", 0, 5000, "Camera height above sea level, in metres."),
            ("max_distance", "max distance (km)", 0, 200, "How far the haze reaches along each ray. 0 = to the top of the atmosphere.")]:
        knob = nuke.Double_Knob(name, label)
        knob.setRange(lo, hi)
        knob.setTooltip(tip)
        k.append(knob)

    k.append(nuke.Text_Knob("depth_haze_divider", "Depth Haze"))
    density = nuke.Color_Knob("haze_density", "haze density (1/m)")
    density.setFlag(nuke.DISABLED)
    density.setTooltip("Read only. How much the air and haze at camera height dim light per metre. For depth "
                       "hazing a plate: T = exp(-haze_density * depth_in_metres), then "
                       "plate * T + atmos_haze_color * (1 - T).")
    k.append(density)
    preview_distance = nuke.Double_Knob("haze_distance", "haze distance (km)")
    preview_distance.setRange(0, 50)
    preview_distance.setTooltip("How far the depth haze reaches: used by the Haze Preview view and, with passes set to "
                                "Depth Haze, by every pass. The haze thins with height along each ray.")
    k.append(preview_distance)

    quality = nuke.Enumeration_Knob("quality", "quality", ["Draft", "Normal", "High"])
    quality.setTooltip("Number of samples along each ray. Draft is about 4x faster than High.")
    k.append(quality)
    for name, label, tip in [
            ("viewer_resolution", "viewer resolution",
             "Resolution the haze is computed at while you work in the Nuke GUI. It is smooth, so Half "
             "or Quarter look almost the same and are 4x or 16x faster. The horizon stays sharp."),
            ("render_resolution", "render resolution",
             "Resolution the haze is computed at when rendering from a terminal or on the farm.")]:
        knob = nuke.Enumeration_Knob(name, label, ["Full", "Half", "Quarter"])
        knob.setTooltip(tip)
        k.append(knob)
    # Scale the passes are computed at: the viewer setting in the GUI, the render setting
    # in terminal renders ($gui is 0 there).
    scale = nuke.Double_Knob("scatter_scale", "scatter scale")
    scale.setFlag(nuke.INVISIBLE)
    k.append(scale)

    k.append(nuke.Tab_Knob("advanced", "Advanced", nuke.TABBEGINCLOSEDGROUP))
    for name, label, tip in [
            ("rayleigh_coefficients", "rayleigh coefficients", "Sea-level Rayleigh scattering per km at 680, 550, 440 nm."),
    ]:
        knob = nuke.XYZ_Knob(name, label)
        knob.setTooltip(tip)
        k.append(knob)
    for name, label, tip in [
            ("mie_coefficient", "mie coefficient", "Sea-level Mie scattering per km. Extinction is this / 0.9."),
            ("rayleigh_scale_height", "rayleigh scale height (km)", "Height over which air density falls by e."),
            ("planet_radius", "planet radius (km)", ""),
            ("atmosphere_thickness", "atmosphere thickness (km)", ""),
            ("manual_sun_brightness", "manual sun brightness", "Sun brightness when 'light from HDRI' is off, before 'sun strength'."),
            ("clear_sky_ratio", "clear sky ratio", "For clipped suns: sun brightness relative to the average sky."),
            ("sun_search_cone", "sun search cone (deg)", "Radius around the brightest spot counted as the sun."),
            ("clip_ratio", "clip ratio", "The sun counts as clipped when its peak is under this many times the average sky.")]:
        knob = nuke.Double_Knob(name, label)
        if tip:
            knob.setTooltip(tip)
        k.append(knob)
    k.append(nuke.Tab_Knob("advanced_end", None, nuke.TABENDGROUP))

    for knob in k:
        group.addKnob(knob)
    _USER_KNOBS.update(knob.name() for knob in k)

    defaults = {
        "sun_direction": [0.0, 0.5, -1.0], "sun_color": 1.0, "sun_strength": 1.0, "sun_boost": 1.0,
        "sky_light": 1.0, "light_from_hdri": True, "sky_amount": 1.0, "haze_amount": 1.0,
        "haze_glow_size": 1.0, "camera_height": 1.0, "max_distance": 0.0, "quality": 1,
        "viewer_resolution": 1, "render_resolution": 0,
        "rayleigh_coefficients": [0.0052, 0.0121, 0.0296], "mie_coefficient": 0.021,
        "rayleigh_scale_height": 8.5, "haze_height": 1.2, "haze_distance": 5.0, "planet_radius": 6360.0,
        "atmosphere_thickness": 60.0, "manual_sun_brightness": 20.0, "clear_sky_ratio": 55.0,
        "sun_search_cone": 6.0, "clip_ratio": 20.0,
    }
    for name, value in defaults.items():
        group[name].setValue(value)
    res = "(%s==0 ? 1 : %s==1 ? 0.5 : 0.25)"
    group["scatter_scale"].setExpression("$gui ? %s : %s" % (res % ("viewer_resolution", "viewer_resolution"),
                                                              res % ("render_resolution", "render_resolution")))
    for i, c in enumerate("xyz"):
        group["haze_density"].setExpression(HAZE_DENSITY.format(c=c), i)


def _link_scatter(node, output):
    _link(node, "output", str(output))
    _link(node, "depth_haze", "parent.passes")
    _link(node, "sun_from_hdri", "parent.sun_from==0")
    _link(node, "light_from_hdri", "parent.light_from_hdri && !parent.self_lit")
    for i, axis in enumerate("xyz"):
        _link(node, "sun_direction",
              "parent.sun_from==1 && [exists parent.input1] ? (%s) : parent.sun_direction.%s" % (SUN_FROM_AXIS % (3 + 4 * i), axis), i)
    for i, channel in enumerate("rgb"):
        _link(node, "sun_color", "parent.sun_color.%s" % channel, i)
        _link(node, "rayleigh_coefficients", "parent.rayleigh_coefficients.%s" % "xyz"[i], i)
    _link(node, "sun_intensity", "parent.manual_sun_brightness")
    _link(node, "sun_strength", "parent.sun_strength")
    _link(node, "sun_boost", "parent.sun_boost")
    _link(node, "sky_light", "parent.sky_light")
    _link(node, "clear_sky_ratio", "parent.clear_sky_ratio")
    _link(node, "camera_altitude_km", "parent.camera_height / 1000")
    _link(node, "max_distance_km", "parent.max_distance")
    _link(node, "longitude_offset_deg", "parent.hdri_rotation")
    _link(node, "rayleigh_density", "parent.sky_amount")
    _link(node, "mie_density", "parent.haze_amount")
    _link(node, "mie_g", "clamp(1 - 0.24 * parent.haze_glow_size, 0, 0.99)")
    _link(node, "mie_coefficient", "parent.mie_coefficient")
    _link(node, "rayleigh_scale_height_km", "parent.rayleigh_scale_height")
    _link(node, "mie_scale_height_km", "parent.haze_height")
    _link(node, "haze_distance_km", "parent.haze_distance")
    _link(node, "planet_radius_km", "parent.planet_radius")
    _link(node, "atmosphere_thickness_km", "parent.atmosphere_thickness")
    _link(node, "view_samples", "parent.quality==0 ? 8 : parent.quality==1 ? 16 : 32")


def _upscale(node, hdri, name):
    """Scale a pass back to the HDRI size, sky and ground halves apart so the hard
    horizon line does not get filtered across."""
    halves = []
    for half, (lo, hi) in (("sky", ("input.height / 2", "input.height")), ("ground", ("0", "input.height / 2"))):
        x, y = node.xpos(), node.ypos() + 60
        # Crop without black edges: outside the box Nuke repeats the edge pixels.
        cut = nuke.nodes.Crop(name="%s_%s_cut" % (name, half), crop=False)
        cut.setInput(0, node)
        cut["box"].setExpression("0", 0)
        cut["box"].setExpression(lo, 1)
        cut["box"].setExpression("input.width", 2)
        cut["box"].setExpression(hi, 3)
        up = nuke.nodes.Reformat(name="%s_%s_up" % (name, half), type="to box", box_fixed=True,
                                 resize="distort", filter="Cubic")
        up.setInput(0, cut)
        up["box_width"].setExpression("hdri.width")
        up["box_height"].setExpression("hdri.height")
        trim = nuke.nodes.Crop(name="%s_%s_trim" % (name, half))
        trim.setInput(0, up)
        trim["box"].setExpression("0", 0)
        trim["box"].setExpression(lo.replace("input", "hdri"), 1)
        trim["box"].setExpression("hdri.width", 2)
        trim["box"].setExpression(hi.replace("input", "hdri"), 3)
        halves.append(trim)
    joined = nuke.nodes.Merge2(name="%s_full" % name, operation="plus")
    joined.setInput(0, halves[0])
    joined.setInput(1, halves[1])
    # At full resolution skip the round trip altogether.
    pick = nuke.nodes.Switch(name="%s_resolution" % name)
    pick.setInput(0, node)
    pick.setInput(1, joined)
    pick["which"].setExpression("parent.scatter_scale < 1")
    for i, n in enumerate([halves[0].input(0).input(0), halves[0].input(0), halves[0],
                           halves[1].input(0).input(0), halves[1].input(0), halves[1], joined, pick]):
        n.setXYpos(node.xpos() + (i // 3) * 0, node.ypos() + 40 + 30 * i)
    return pick


# ---- Bake ----------------------------------------------------------------------------

# Default cache path, next to the script (or under $EZATMOS_CACHE_DIR):
#   <script dir>/ezatmos_cache/<script>/<node>/<script>_<node>.####.exr
_SCRIPT = "[file rootname [file tail [value root.name]]]"
_CACHE_ROOT = "[python {__import__('os').environ.get('EZATMOS_CACHE_DIR') or ''}]"
BAKE_PATH = ("[if {[value parent.bake_file] != \"\"} {value parent.bake_file} "
             "{set d [if {\"%(root)s\" != \"\"} {set e \"%(root)s\"} "
             "{set e [file dirname [value root.name]]/ezatmos_cache}]/"
             "%(script)s/[value parent.name]/%(script)s_[value parent.name].####.exr}]"
             % {"root": _CACHE_ROOT, "script": _SCRIPT})


def _hash_code(names):
    """Python that sets `h` to a fingerprint of the settings that shape the output."""
    # A plain loop: Nuke runs this with separate locals, which a comprehension can't see.
    return ("import hashlib\n"
            "s = []\n"
            "for n in %r:\n"
            "    if g.knob(n):\n"
            "        s.append((n, g[n].toScript()))\n"
            "# Where the skydome sits shapes the output too.\n"
            "d = g.node('DomeRemap')\n"
            "if d is not None and g.input(2) is not None:\n"
            "    for k in ('dome_row0', 'dome_row1', 'dome_row2', 'eye', 'radius'):\n"
            "        s.append((k, repr(d['EzAtmosDome_' + k].value())))\n"
            "h = hashlib.md5(repr(s).encode()).hexdigest()\n"
            % (list(names),))


def _range_code():
    return ("if g['bake_range'].getValue() == 0:\n"
            "    first = last = nuke.frame()\n"
            "else:\n"
            "    first, last = int(nuke.root()['first_frame'].value()), int(nuke.root()['last_frame'].value())\n")


def _use_baked_expression(names):
    # 1 only when 'use baked' is on, the bake exists and the settings still match it.
    code = ("g = nuke.thisGroup()\n" + _hash_code(names) +
            "import os\n"
            "f = nuke.filename(g.node('BakeRead'), nuke.REPLACE) or ''\n"
            "ret = 1 if g['use_baked'].value() and g['baked_hash'].value() == h and os.path.exists(f) else 0\n")
    return "[python -execlocal {%s}]" % code


def _label_expression(names):
    code = ("g = nuke.thisNode()\n" + _hash_code(names) +
            "import os\n"
            "f = nuke.filename(g.node('BakeRead'), nuke.REPLACE) or ''\n"
            "ok = g['baked_hash'].value() == h and os.path.exists(f)\n"
            "ret = '' if not g['use_baked'].value() or not g['baked_hash'].value() else "
            "('baked' if ok else 'bake out of date: live')\n")
    return "[python -execlocal {%s}]" % code


def _bake_script(names):
    return ("g = nuke.thisNode()\n" + _hash_code(names) + _range_code() +
            "use = g['use_baked'].value()\n"
            "g['use_baked'].setValue(False)\n"
            "try:\n"
            "    with g:\n"
            "        nuke.execute(nuke.toNode('BakeWrite'), first, last)\n"
            "    g['baked_hash'].setValue(h)\n"
            "    g['baked_first'].setValue(first)\n"
            "    g['baked_last'].setValue(last)\n"
            "finally:\n"
            "    g['use_baked'].setValue(use)\n")


def _farm_write_script(names):
    # A top-level Write with the same path, for a farm job the comp renders depend on.
    return ("g = nuke.thisNode()\n" + _hash_code(names) + _range_code() +
            "path = nuke.filename(g.node('BakeRead'))\n"
            "with nuke.root():\n"
            "    w = nuke.nodes.Write(name=g.name() + '_BakeWrite', file=path, file_type='exr', channels='all')\n"
            "    w['create_directories'].setValue(True)\n"
            "    w['use_limit'].setValue(True)\n"
            "    w['first'].setValue(first)\n"
            "    w['last'].setValue(last)\n"
            "    w.setInput(0, g)\n"
            "    w.setXYpos(g.xpos(), g.ypos() + 80)\n"
            "g['baked_hash'].setValue(h)\n"
            "g['baked_first'].setValue(first)\n"
            "g['baked_last'].setValue(last)\n"
            "if nuke.GUI:\n"
            "    nuke.message('Render %s on the farm before the comp. It writes ' % w.name() + path)\n")


def _add_bake_knobs(group, names):
    k = [nuke.Text_Knob("bake_divider", "Bake")]
    f = nuke.File_Knob("bake_file", "bake file")
    f.setTooltip("Leave empty for the default: <script dir>/ezatmos_cache/<script>/<node>/<script>_<node>.####.exr, "
                 "or $EZATMOS_CACHE_DIR/<script>/<node>/... when that is set. Fill in to override.")
    k.append(f)
    rng = nuke.Enumeration_Knob("bake_range", "bake range", ["Current Frame (hold)", "Script Range"])
    rng.setTooltip("Current Frame: one frame, held for the whole shot (a sun that doesn't move). "
                   "Script Range: every frame, for an animated sun or knobs.")
    k.append(rng)
    now = nuke.PyScript_Knob("bake_now", "bake now", _bake_script(names))
    now.setTooltip("Writes all layers to the bake file here and now.")
    k.append(now)
    farm = nuke.PyScript_Knob("bake_farm_write", "make farm bake Write", _farm_write_script(names))
    farm.setTooltip("Adds a Write below this node with the bake path, to render on the farm before the comp.")
    k.append(farm)
    use = nuke.Boolean_Knob("use_baked", "use baked")
    use.setTooltip("Read the bake instead of computing, but only while it exists and these settings still "
                   "match it; otherwise the node computes live and its label says the bake is out of date.")
    use.setFlag(nuke.STARTLINE)
    k.append(use)
    s = nuke.String_Knob("baked_hash", "baked hash")
    s.setFlag(nuke.INVISIBLE)
    k.append(s)
    for name in ("baked_first", "baked_last"):
        n = nuke.Int_Knob(name, name)
        n.setFlag(nuke.INVISIBLE)
        k.append(n)
    for knob in k:
        group.addKnob(knob)
    group["use_baked"].setValue(True)
    group["label"].setValue(_label_expression(names))


def _add_bake_nodes(stream, names):
    """Write the full output to the bake, read it back, and pick between them."""
    write = nuke.nodes.Write(name="BakeWrite", file_type="exr", channels="all", xpos=200, ypos=stream.ypos() + 60)
    write["file"].setValue(BAKE_PATH)
    write["create_directories"].setValue(True)
    write.setInput(0, stream)
    read = nuke.nodes.Read(name="BakeRead", xpos=200, ypos=stream.ypos() + 120)
    read["file"].setValue(BAKE_PATH)
    for knob, expr in (("first", "parent.baked_first"), ("last", "parent.baked_last"),
                       ("origfirst", "parent.baked_first"), ("origlast", "parent.baked_last")):
        read[knob].setExpression(expr)
    read["before"].setValue("hold")
    read["after"].setValue("hold")
    read["on_error"].setValue("black")
    pick = nuke.nodes.Switch(name="UseBake", xpos=0, ypos=stream.ypos() + 120)
    pick.setInput(0, stream)
    pick.setInput(1, read)
    pick["which"].setExpression(_use_baked_expression(names))
    return pick


# ---- Skydome ---------------------------------------------------------------------------

# Python that sets `m` to the skydome's world matrix and `r` to its radius at this frame,
# from the geometry in the dome input: TransformGeos (and their axis input) down to the
# Sphere. A knob's own matrix ignores the frame being rendered, so each transform is built
# from its knobs at nuke.frame(), in its transform and rotation orders.
_DOME_WALK = """\
def local(n, t):
    import math
    M = nuke.math.Matrix4
    def v(k, i):
        return n[k].getValueAt(t, i)
    T = M()
    T.makeIdentity()
    T.translate(v('translate', 0), v('translate', 1), v('translate', 2))
    P = M()
    P.makeIdentity()
    P.translate(v('pivot', 0), v('pivot', 1), v('pivot', 2))
    us = n['uniform_scale'].getValueAt(t)
    S = M()
    S.makeIdentity()
    S.scale(v('scaling', 0) * us, v('scaling', 1) * us, v('scaling', 2) * us)
    R = M()
    R.makeIdentity()
    for axis in reversed(n['rot_order'].value()):
        a = math.radians(v('rotate', 'XYZ'.index(axis)))
        if axis == 'X':
            R.rotateX(a)
        elif axis == 'Y':
            R.rotateY(a)
        else:
            R.rotateZ(a)
    m = M()
    m.makeIdentity()
    for op in n['xform_order'].value():
        if op == 'T':
            m = T * m
        else:
            m = P * (S if op == 'S' else R) * P.inverse() * m
    return m
t = nuke.frame()
g = nuke.thisGroup()
n = g.input(2)
m = nuke.math.Matrix4()
m.makeIdentity()
r = 1.0
while n is not None:
    p = n.input(1) if n.Class() == 'TransformGeo' else None
    if p is not None and p.knob('world_matrix'):
        w = nuke.math.Matrix4()
        for i in range(16):
            w[(i % 4) * 4 + i // 4] = p['world_matrix'].getValueAt(t, i)
        m = m * w
    if n.knob('transform') and n['transform'].Class() == 'Axis_Knob':
        m = m * local(n, t)
    if n.Class() == 'Sphere':
        r = n['radius'].getValueAt(t)
        break
    n = n.input(0)
"""
def _dome_expression(ret):
    return "[python -execlocal {%sret = %s}]" % (_DOME_WALK, ret)


def _add_dome_nodes(hdri):
    """Re-map the HDRI to what the camera sees on the skydome, when one is connected."""
    dome = nuke.nodes.BlinkScript(name="DomeRemap", xpos=150, ypos=-360)
    dome.setInput(0, hdri)
    dome.setInput(1, hdri)
    _load_kernel(dome, "EzAtmosDome.blink")
    for row in range(3):
        for col in range(4):
            _link(dome, "dome_row%d" % row, _dome_expression("m.inverse()[%d]" % (col * 4 + row)), col)
    for k in range(3):
        # The camera's position, or the dome's centre without a camera.
        _link(dome, "eye", _dome_expression(
            "g.input(3)['world_matrix'].getValueAt(t, %d) if g.input(3) is not None and g.input(3).knob('world_matrix') "
            "else m[%d]" % (3 + 4 * k, 12 + k)), k)
    _link(dome, "radius", _dome_expression("r"))
    pick = nuke.nodes.Switch(name="UseDome", xpos=0, ypos=-340)
    pick.setInput(0, hdri)
    pick.setInput(1, dome)
    pick["which"].setExpression("[exists parent.input2]")
    return pick


def build():
    for layer in LAYERS:
        nuke.Layer(layer, ["%s.red" % layer, "%s.green" % layer, "%s.blue" % layer])

    group = nuke.nodes.Group(name="EzAtmosScatter1")
    group["tile_color"].setValue(0x4a7fb5ff)
    _add_knobs(group)

    group.begin()
    hdri = nuke.nodes.Input(name="hdri", xpos=0, ypos=-400)
    axis = nuke.nodes.Input(name="sun", xpos=600, ypos=-400)
    nuke.nodes.Input(name="dome", xpos=150, ypos=-440)
    nuke.nodes.Input(name="camera", xpos=300, ypos=-440)
    # From here on the HDRI is the one seen on the skydome, when there is one.
    hdri = _add_dome_nodes(hdri)

    # Light measured from a small copy of the HDRI.
    proxy = nuke.nodes.Reformat(name="LightProxy", type="to box", box_width=512, box_height=256,
                                box_fixed=True, resize="distort", filter="Mitchell", xpos=300, ypos=-300)
    proxy.setInput(0, hdri)
    ref = nuke.nodes.Reformat(name="LightRef", type="to box", box_width=4, box_height=1,
                              box_fixed=True, resize="distort", xpos=300, ypos=-240)
    ref.setInput(0, proxy)
    light = nuke.nodes.BlinkScript(name="Light", xpos=300, ypos=-180)
    light.setInput(0, ref)
    light.setInput(1, proxy)
    _load_kernel(light, "EzAtmosLight.blink")
    _link(light, "longitude_offset_deg", "parent.hdri_rotation")
    _link(light, "sun_cone_deg", "parent.sun_search_cone")
    _link(light, "clip_ratio", "parent.clip_ratio")

    # Optical depth towards the sun, precomputed once instead of marched at every sample.
    lut_ref = nuke.nodes.Reformat(name="LUTRef", type="to box", box_width=256, box_height=64,
                                  box_fixed=True, resize="distort", xpos=450, ypos=-240)
    lut_ref.setInput(0, hdri)
    lut = nuke.nodes.BlinkScript(name="TransmittanceLUT", xpos=450, ypos=-180)
    lut.setInput(0, lut_ref)
    _load_kernel(lut, "EzAtmosTransmittanceLUT.blink")
    for param, knob in [("planet_radius_km", "planet_radius"), ("atmosphere_thickness_km", "atmosphere_thickness"),
                        ("rayleigh_scale_height_km", "rayleigh_scale_height"),
                        ("mie_scale_height_km", "haze_height")]:
        _link(lut, param, "parent." + knob)

    # The passes are computed at scatter_scale. Even height keeps the horizon on a row edge.
    low = nuke.nodes.Reformat(name="ScatterResolution", type="to box", box_fixed=True, resize="distort",
                              xpos=-300, ypos=-240)
    low.setInput(0, hdri)
    low["box_width"].setExpression("max(floor(hdri.width * parent.scatter_scale + 0.5), 4)")
    low["box_height"].setExpression("max(2 * floor(hdri.height * parent.scatter_scale / 2 + 0.5), 2)")

    # Self-lit: with no HDRI, the sky light comes from this atmosphere's own sky. A small
    # Rayleigh + Mie render (always in Atmosphere mode, no sky light, so no loop) is
    # measured like an HDRI; the passes that use sky light read that measurement.
    self_ref = nuke.nodes.Reformat(name="SelfSkySize", type="to box", box_width=512, box_height=256,
                                   box_fixed=True, resize="distort", xpos=600, ypos=-300)
    self_ref.setInput(0, hdri)
    self_parts = []
    for name, output in (("rayleigh", 1), ("mie", 2)):
        node = nuke.nodes.BlinkScript(name="SelfSky_" + name, xpos=600 + 120 * len(self_parts), ypos=-240)
        node.setInput(0, self_ref)
        node.setInput(1, light)
        node.setInput(2, lut)
        _load_kernel(node, "AtmosScatter.blink")
        _link_scatter(node, output)
        _link(node, "depth_haze", "0")
        _link(node, "view_samples", "8")
        self_parts.append(node)
    self_sky = nuke.nodes.Merge2(name="SelfSky", operation="plus", output="rgb", xpos=600, ypos=-200)
    self_sky.setInput(0, self_parts[0])
    self_sky.setInput(1, self_parts[1])
    self_light = nuke.nodes.BlinkScript(name="SelfLight", xpos=600, ypos=-160)
    self_light.setInput(0, ref)
    self_light.setInput(1, self_sky)
    _load_kernel(self_light, "EzAtmosLight.blink")
    _link(self_light, "longitude_offset_deg", "0")
    _link(self_light, "sun_cone_deg", "parent.sun_search_cone")
    _link(self_light, "clip_ratio", "parent.clip_ratio")
    sky_light_source = nuke.nodes.Switch(name="SkyLightSource", xpos=450, ypos=-120)
    sky_light_source.setInput(0, light)
    sky_light_source.setInput(1, self_light)
    sky_light_source["which"].setExpression("parent.self_lit")

    passes = {}
    for index, (name, output, _) in enumerate(PASSES):
        node = nuke.nodes.BlinkScript(name="Scatter_" + name, xpos=-300 + 150 * index, ypos=-100)
        node.setInput(0, low)
        # Passes that use sky light read it from the HDRI, or from the atmosphere itself.
        node.setInput(1, sky_light_source if name in ("ambient", "haze_color", "haze_sky") else light)
        node.setInput(2, lut)
        _load_kernel(node, "AtmosScatter.blink")
        _link_scatter(node, output)
        passes[name] = _upscale(node, hdri, name)

    sum1 = nuke.nodes.Merge2(name="AddMie", operation="plus", xpos=-300, ypos=0)
    sum1.setInput(0, passes["rayleigh"])
    sum1.setInput(1, passes["mie"])
    inscatter = nuke.nodes.Merge2(name="AddSkyLight", operation="plus", xpos=-300, ypos=60)
    inscatter.setInput(0, sum1)
    inscatter.setInput(1, passes["ambient"])

    attenuated = nuke.nodes.Merge2(name="Attenuate", operation="multiply", output="rgb", xpos=0, ypos=0)
    attenuated.setInput(0, hdri)
    attenuated.setInput(1, passes["transmittance"])
    comp = nuke.nodes.Merge2(name="PreviewComp", operation="plus", output="rgb", xpos=0, ypos=60)
    comp.setInput(0, attenuated)
    comp.setInput(1, inscatter)

    # Haze Preview: the comp hazed as if everything were haze_distance away,
    #   comp * T + hazeColor * (1 - T)
    hazed = nuke.nodes.Merge2(name="HazePreviewAttenuate", operation="multiply", output="rgb", xpos=150, ypos=0)
    hazed.setInput(0, comp)
    hazed.setInput(1, passes["haze_transmittance"])
    clear = nuke.nodes.Invert(name="HazePreviewOpacity", channels="rgb", xpos=300, ypos=0)
    clear.setInput(0, passes["haze_transmittance"])
    veil = nuke.nodes.Merge2(name="HazePreviewVeil", operation="multiply", output="rgb", xpos=300, ypos=60)
    veil.setInput(0, passes["haze_color"])
    veil.setInput(1, clear)
    haze_preview = nuke.nodes.Merge2(name="HazePreview", operation="plus", output="rgb", xpos=150, ypos=60)
    haze_preview.setInput(0, hazed)
    haze_preview.setInput(1, veil)
    # With passes on Depth Haze the comp is already hazed; do not haze it twice.
    preview_pick = nuke.nodes.Switch(name="HazePreviewMode", xpos=150, ypos=100)
    preview_pick.setInput(0, haze_preview)
    preview_pick.setInput(1, comp)
    preview_pick["which"].setExpression("parent.passes")

    sources = {"comp": comp, "inscatter": inscatter, "haze_preview": preview_pick}
    sources.update(passes)
    view = nuke.nodes.Switch(name="ViewOutput", xpos=0, ypos=160)
    for i, (_, key) in enumerate(VIEW_OUTPUTS):
        view.setInput(i, sources[key])
    view["which"].setExpression("parent.view_output")

    # Main rgba from the view switch; every other channel of the HDRI passes through.
    stream = nuke.nodes.Copy(name="MainRGB", channels="rgb", xpos=0, ypos=240)
    stream.setInput(0, hdri)
    stream.setInput(1, view)
    layer_sources = {"atmos_inscatter": inscatter}
    layer_sources.update({layer: passes[name] for name, _, layer in PASSES if layer})
    for i, layer in enumerate(LAYERS):
        copy = nuke.nodes.Copy(name="Layer_" + layer, xpos=0, ypos=300 + 60 * i)
        copy.setInput(0, stream)
        copy.setInput(1, layer_sources[layer])
        for c, channel in enumerate(("red", "green", "blue")):
            copy["from%d" % c].setValue("rgba." + channel)
            copy["to%d" % c].setValue("%s.%s" % (layer, channel))
        stream = copy

    # Every user knob shapes the output, so the bake fingerprint covers them all.
    names = [kn.name() for kn in group.allKnobs() if kn.Class() not in ("Tab_Knob", "Text_Knob", "PyScript_Knob")
             and kn.name() in _USER_KNOBS]
    stream = _add_bake_nodes(stream, names)
    out = nuke.nodes.Output(xpos=0, ypos=stream.ypos() + 80)
    out.setInput(0, stream)
    group.end()
    _add_bake_knobs(group, names)
    return group


def save_gizmo(group, path=GIZMO_PATH):
    """Write the group out as a .gizmo, layers first so the Copy nodes resolve."""
    for node in nuke.allNodes():
        node.setSelected(False)
    group.setSelected(True)
    if not os.path.isdir(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))
    tmp = path + ".tmp"
    nuke.nodeCopy(tmp)
    with open(tmp) as f:
        body = f.read()
    os.remove(tmp)
    body = body.replace("Group {", "Gizmo {", 1)
    header = "version %d.%d v%d\n" % (nuke.NUKE_VERSION_MAJOR, nuke.NUKE_VERSION_MINOR, nuke.NUKE_VERSION_RELEASE)
    for layer in LAYERS:
        header += "add_layer {%s %s.red %s.green %s.blue}\n" % (layer, layer, layer, layer)
    if not os.path.isdir(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))
    with open(path, "w") as f:
        f.write(header + body[body.index("Gizmo {"):])
    return path


if __name__ == "__main__":
    print("wrote", save_gizmo(build()))
