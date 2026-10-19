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

LAYERS = ["atmos_inscatter", "atmos_rayleigh", "atmos_mie", "atmos_ambient", "atmos_transmittance"]

VIEW_OUTPUTS = [
    # (menu label, node feeding the main rgba)
    ("Scatter Preview Comp", "comp"),
    ("Scatter", "inscatter"),
    ("Sky (Rayleigh)", "rayleigh"),
    ("Haze (Mie)", "mie"),
    ("Sky Light (Ambient)", "ambient"),
    ("Transmittance", "transmittance"),
]

# Kernel output index for each pass (see AtmosScatter.blink).
PASSES = [("rayleigh", 1, "atmos_rayleigh"),
          ("mie", 2, "atmos_mie"),
          ("transmittance", 3, "atmos_transmittance"),
          ("ambient", 5, "atmos_ambient")]

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


def _add_knobs(group):
    k = []

    k.append(nuke.Tab_Knob("ezatmos", "EzAtmosScatter"))
    view = nuke.Enumeration_Knob("view_output", "view output", [label for label, _ in VIEW_OUTPUTS])
    view.setTooltip("What the main rgba shows. Every pass is also written to its own atmos_* layer.")
    k.append(view)

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
            ("camera_height", "camera height (m)", 0, 5000, "Camera height above sea level, in metres."),
            ("max_distance", "max distance (km)", 0, 200, "How far the haze reaches along each ray. 0 = to the top of the atmosphere.")]:
        knob = nuke.Double_Knob(name, label)
        knob.setRange(lo, hi)
        knob.setTooltip(tip)
        k.append(knob)
    fill = nuke.Enumeration_Knob("fill_below_horizon", "fill below horizon", ["Off", "Extend Horizon", "Mirror Sky"])
    fill.setTooltip("Fills the empty lower half of the sky passes (Scatter, Sky, Haze, Sky Light) so they "
                    "can be used as a full sky dome. Extend Horizon repeats the row just above the horizon, "
                    "Mirror Sky reflects the sky. The Scatter Preview Comp and Transmittance stay physical.")
    k.append(fill)
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
            ("mie_scale_height", "mie scale height (km)", "Height over which haze density falls by e."),
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

    defaults = {
        "sun_direction": [0.0, 0.5, -1.0], "sun_color": 1.0, "sun_strength": 1.0, "sun_boost": 1.0,
        "sky_light": 1.0, "light_from_hdri": True, "sky_amount": 1.0, "haze_amount": 1.0,
        "haze_glow_size": 1.0, "camera_height": 1.0, "max_distance": 0.0, "quality": 1,
        "viewer_resolution": 1, "render_resolution": 0,
        "rayleigh_coefficients": [0.0052, 0.0121, 0.0296], "mie_coefficient": 0.021,
        "rayleigh_scale_height": 8.5, "mie_scale_height": 1.2, "planet_radius": 6360.0,
        "atmosphere_thickness": 60.0, "manual_sun_brightness": 20.0, "clear_sky_ratio": 55.0,
        "sun_search_cone": 6.0, "clip_ratio": 20.0,
    }
    for name, value in defaults.items():
        group[name].setValue(value)
    res = "(%s==0 ? 1 : %s==1 ? 0.5 : 0.25)"
    group["scatter_scale"].setExpression("$gui ? %s : %s" % (res % ("viewer_resolution", "viewer_resolution"),
                                                              res % ("render_resolution", "render_resolution")))


def _link_scatter(node, output):
    _link(node, "output", str(output))
    _link(node, "sun_from_hdri", "parent.sun_from==0")
    _link(node, "light_from_hdri", "parent.light_from_hdri")
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
    _link(node, "mie_scale_height_km", "parent.mie_scale_height")
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


def _fill_below(node, name):
    """Fill the rows below the horizon from the sky above them, as 'fill below horizon'
    picks: 0 leaves them black, 1 repeats the horizon row, 2 mirrors the sky."""
    x, y = node.xpos() + 120, node.ypos()
    sky = nuke.nodes.Crop(name="%s_sky" % name, crop=False, xpos=x, ypos=y + 30)
    sky.setInput(0, node)
    for i, e in enumerate(("0", "input.height / 2", "input.width", "input.height")):
        sky["box"].setExpression(e, i)
    # AdjBBox bakes the repeated edge row into real pixels; the Crop trims it to the frame.
    grow = nuke.nodes.AdjBBox(name="%s_extend" % name, xpos=x, ypos=y + 60)
    grow["numpixels"].setExpression("hdri.height")
    grow.setInput(0, sky)
    extend = nuke.nodes.Crop(name="%s_extend_trim" % name, xpos=x, ypos=y + 90)
    extend.setInput(0, grow)
    for i, e in enumerate(("0", "0", "hdri.width", "hdri.height")):
        extend["box"].setExpression(e, i)

    upper = nuke.nodes.Crop(name="%s_upper" % name, xpos=x + 110, ypos=y + 30)
    upper.setInput(0, node)
    for i, e in enumerate(("0", "hdri.height / 2", "hdri.width", "hdri.height")):
        upper["box"].setExpression(e, i)
    flipped = nuke.nodes.Mirror2(name="%s_flip" % name, flip=True, xpos=x + 220, ypos=y + 30)
    flipped.setInput(0, upper)
    lower = nuke.nodes.Crop(name="%s_lower" % name, xpos=x + 220, ypos=y + 60)
    lower.setInput(0, flipped)
    for i, e in enumerate(("0", "0", "hdri.width", "hdri.height / 2")):
        lower["box"].setExpression(e, i)
    mirror = nuke.nodes.Merge2(name="%s_mirror" % name, operation="plus", xpos=x + 110, ypos=y + 90)
    mirror.setInput(0, upper)
    mirror.setInput(1, lower)

    pick = nuke.nodes.Switch(name="%s_fill" % name, xpos=x, ypos=y + 130)
    pick.setInput(0, node)
    pick.setInput(1, extend)
    pick.setInput(2, mirror)
    pick["which"].setExpression("parent.fill_below_horizon")
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
                        ("mie_scale_height_km", "mie_scale_height")]:
        _link(lut, param, "parent." + knob)

    # The passes are computed at scatter_scale. Even height keeps the horizon on a row edge.
    low = nuke.nodes.Reformat(name="ScatterResolution", type="to box", box_fixed=True, resize="distort",
                              xpos=-300, ypos=-240)
    low.setInput(0, hdri)
    low["box_width"].setExpression("max(floor(hdri.width * parent.scatter_scale + 0.5), 4)")
    low["box_height"].setExpression("max(2 * floor(hdri.height * parent.scatter_scale / 2 + 0.5), 2)")

    passes = {}
    for index, (name, output, _) in enumerate(PASSES):
        node = nuke.nodes.BlinkScript(name="Scatter_" + name, xpos=-300 + 150 * index, ypos=-100)
        node.setInput(0, low)
        node.setInput(1, light)
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

    # Optional fill of the empty lower half, for the sky passes only: the preview comp keeps
    # the physical (black) haze below the horizon so the HDRI ground is not washed out.
    filled = {"inscatter": _fill_below(inscatter, "inscatter")}
    for name in ("rayleigh", "mie", "ambient"):
        filled[name] = _fill_below(passes[name], name)
    filled["transmittance"] = passes["transmittance"]

    sources = {"comp": comp}
    sources.update(filled)
    view = nuke.nodes.Switch(name="ViewOutput", xpos=0, ypos=160)
    for i, (_, key) in enumerate(VIEW_OUTPUTS):
        view.setInput(i, sources[key])
    view["which"].setExpression("parent.view_output")

    # Main rgba from the view switch; every other channel of the HDRI passes through.
    stream = nuke.nodes.Copy(name="MainRGB", channels="rgb", xpos=0, ypos=240)
    stream.setInput(0, hdri)
    stream.setInput(1, view)
    layer_sources = {"atmos_inscatter": filled["inscatter"]}
    layer_sources.update({layer: filled[name] for name, _, layer in PASSES})
    for i, layer in enumerate(LAYERS):
        copy = nuke.nodes.Copy(name="Layer_" + layer, xpos=0, ypos=300 + 60 * i)
        copy.setInput(0, stream)
        copy.setInput(1, layer_sources[layer])
        for c, channel in enumerate(("red", "green", "blue")):
            copy["from%d" % c].setValue("rgba." + channel)
            copy["to%d" % c].setValue("%s.%s" % (layer, channel))
        stream = copy

    out = nuke.nodes.Output(xpos=0, ypos=300 + 60 * len(LAYERS) + 60)
    out.setInput(0, stream)
    group.end()
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
