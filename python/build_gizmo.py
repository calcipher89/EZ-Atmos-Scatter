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
    quality = nuke.Enumeration_Knob("quality", "quality", ["Draft", "Normal", "High"])
    quality.setTooltip("Number of samples along each ray. Draft is about 4x faster than High.")
    k.append(quality)

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
        "rayleigh_coefficients": [0.0052, 0.0121, 0.0296], "mie_coefficient": 0.021,
        "rayleigh_scale_height": 8.5, "mie_scale_height": 1.2, "planet_radius": 6360.0,
        "atmosphere_thickness": 60.0, "manual_sun_brightness": 20.0, "clear_sky_ratio": 55.0,
        "sun_search_cone": 6.0, "clip_ratio": 20.0,
    }
    for name, value in defaults.items():
        group[name].setValue(value)


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
    _link(node, "light_samples", "parent.quality==0 ? 4 : parent.quality==1 ? 8 : 12")


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

    passes = {}
    for index, (name, output, _) in enumerate(PASSES):
        node = nuke.nodes.BlinkScript(name="Scatter_" + name, xpos=-300 + 150 * index, ypos=-100)
        node.setInput(0, hdri)
        node.setInput(1, light)
        _load_kernel(node, "AtmosScatter.blink")
        _link_scatter(node, output)
        passes[name] = node

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

    sources = {"comp": comp, "inscatter": inscatter}
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
    layer_sources.update({layer: passes[name] for name, _, layer in PASSES})
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
