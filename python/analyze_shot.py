"""Analyze: set EzAtmosScatter up for depth hazing the shot in its inputs.

build_gizmo.py embeds this file in the gizmo's "analyze" button, so Nuke needs no Python
module at run time. It runs once when pressed and sets plain knob values:

- passes: Depth Haze;
- camera height: the camera's height above 'ground height', in metres;
- haze distance: the distance to the HDRI's own horizon line (from how far below level it
  sits), or else to the horizon seen from the camera height;
- self-lit with no HDRI; with one, the sun from the HDRI when it has a clear sun.

It then shows what it set, with warnings for a sun beside or behind the camera, a high
sun, or a skydome without a camera.

Kept to top-level code with plain loops: Nuke runs button scripts with separate locals,
which functions and comprehensions can't see.
"""
import math
import nuke

g = nuke.thisNode()
done = []
warn = []

# The camera, through any Dots or NoOps in between.
cam = g.input(3)
while cam is not None and not cam.knob("world_matrix"):
    cam = cam.input(0) if cam.inputs() else None
scale = g["scene_scale"].value()
# Nothing in the scene says what its units are, so ask once per node (when it is still at 1),
# showing the camera height each choice would give.
if nuke.GUI and abs(scale - 1.0) < 1e-9 and not g["units_confirmed"].value():
    units = [("Metres", 1.0), ("Decimetres", 0.1), ("Centimetres", 0.01), ("Millimetres", 0.001),
             ("Feet", 0.3048), ("Inches", 0.0254)]
    raw = cam["world_matrix"].getValue(7) - g["ground_height"].value() if cam is not None else None
    options = []
    for label, m in units:
        options.append(label if raw is None else "%s: camera %.4g m up" % (label, raw * m))
    try:
        pick = nuke.choice("EzAtmosScatter analyze", "What units is the scene in?", options, 0)
    except Exception:
        pick = None
    if pick is not None and pick >= 0:
        scale = units[pick][1]
        g["scene_scale"].setValue(scale)
        g["units_confirmed"].setValue(True)
        done.append("Units to metres %g: the scene is in %s (you picked it)." % (scale, units[pick][0].lower()))
fwd = None
if cam is not None:
    wm = cam["world_matrix"]
    height = max((wm.getValue(7) - g["ground_height"].value()) * scale, 1.0)
    g["camera_height"].setValue(round(height, 1))
    done.append("Camera height %.0f m (camera %s, units to metres %g)." % (height, cam.name(), scale))
    fwd = [-wm.getValue(2), -wm.getValue(6), -wm.getValue(10)]
else:
    height = g["camera_height"].value()
    warn.append("No camera connected: kept camera height %.0f m. Connect the shot camera to 'camera'." % height)

radius = g["planet_radius"].value()
horizon = math.sqrt((radius + height / 1000.0) ** 2 - radius ** 2)

# The HDRI's own horizon line: the row edge below 0 deg (down to 10 deg) where the image drops most
# from sky to ground (over 3 rows, by at least 1.5x), from the median brightness of 64 columns.
# Its dip below 0 deg gives the distance to that horizon, so the depth haze reaches exactly the
# line the HDRI shows.
hdri = g.input(0)
dip = None
if hdri is not None:
    w, h = hdri.width(), hdri.height()
    rows = []
    for r in range(0, max(int(h * 10.0 / 180.0), 4) + 2):
        y = h * 0.5 - r - 0.5 + 1.0
        vals = []
        for i in range(64):
            x = (i + 0.5) * w / 64.0
            vals.append(0.2126 * hdri.sample("red", x, y) + 0.7152 * hdri.sample("green", x, y) +
                        0.0722 * hdri.sample("blue", x, y))
        vals.sort()
        rows.append(vals[32])
    best, best_r = 1.0, None
    for r in range(len(rows) - 1):
        drop = (rows[r] + 1e-4) / (rows[r + 1] + 1e-4)
        span = (rows[max(r - 1, 0)] + 1e-4) / (rows[min(r + 2, len(rows) - 1)] + 1e-4)
        if drop > best and span > 1.5:
            best, best_r = drop, r
    if best_r is not None:
        dip = best_r * 180.0 / h
if dip is not None and dip > 0.0:
    horizon = radius * math.tan(math.radians(dip))
    g["haze_distance"].setValue(round(horizon, 1))
    done.append("Haze distance %.1f km: the HDRI's horizon line, %.2f deg below level." % (horizon, dip))
else:
    g["haze_distance"].setValue(round(horizon, 1))
    done.append("Haze distance %.1f km: the horizon seen from %.0f m%s." % (
        horizon, height, "" if hdri is None else " (no clear horizon line in the HDRI)"))
g["passes"].setValue("Depth Haze")
done.append("Passes: Depth Haze.")

sun = None
if g.input(0) is None:
    g["self_lit"].setValue(True)
    if g["sun_from"].value() == "Auto (HDRI)":
        g["sun_from"].setValue("Manual")
    done.append("No HDRI: self-lit on, sun from Manual.")
else:
    g["self_lit"].setValue(False)
    with g:
        light = nuke.toNode("Light")
        found = []
        for c in ("red", "green", "blue"):
            found.append(light.sample(c, 0.5, 0.5))
        peak = light.sample("alpha", 0.5, 0.5)
        sky = 0.2126 * light.sample("red", 2.5, 0.5) + 0.7152 * light.sample("green", 2.5, 0.5) + \
            0.0722 * light.sample("blue", 2.5, 0.5)
        clipped = light.sample("alpha", 1.5, 0.5) > 0.5
    ratio = peak / max(sky, 1e-6)
    # A clipped sun (LDR or a capped HDRI) stands out less, but its direction is still good.
    if any(found) and (ratio > 4.0 or (clipped and ratio > 1.5)):
        g["sun_from"].setValue("Auto (HDRI)")
        g["light_from_hdri"].setValue(True)
        sun = found
        if clipped:
            done.append("Clipped sun found in the HDRI: sun from Auto; its brightness is rebuilt, tune 'sun boost'.")
        else:
            done.append("Sun found in the HDRI (%.0fx the sky): sun from Auto, light from HDRI." % ratio)
    else:
        warn.append("No clear sun in the HDRI (overcast?): set 'sun from' to Manual or Axis yourself.")

if g.input(2) is not None:
    if cam is None:
        warn.append("A skydome is connected but no camera: the dome is seen from its centre.")
    else:
        done.append("Skydome connected: the HDRI is re-mapped as the camera sees the dome.")

if sun is None and g["sun_from"].value() == "Manual":
    sun = list(g["sun_direction"].value())
if sun is not None:
    ln = math.sqrt(sun[0] ** 2 + sun[1] ** 2 + sun[2] ** 2) or 1.0
    elev = math.degrees(math.asin(max(-1.0, min(1.0, sun[1] / ln))))
    if fwd is not None:
        az = math.degrees(math.atan2(sun[0], -sun[2]) - math.atan2(fwd[0], -fwd[2]))
        az = (az + 180.0) % 360.0 - 180.0
        done.append("Sun %.0f deg up, %.0f deg %s of where the camera looks." % (elev, abs(az), "right" if az > 0 else "left"))
        if abs(az) > 60.0:
            warn.append("The sun is beside or behind the camera: backlit haze and shafts need it in front.")
    if elev > 20.0:
        warn.append("The sun is high (%.0f deg): sunrise and golden hour looks need it under 10 deg." % elev)

summary = "\n".join(done + ([""] + ["Note: " + w for w in warn] if warn else []))
if nuke.GUI:
    nuke.message("EzAtmosScatter analyze\n\n" + summary)
else:
    print(summary)
