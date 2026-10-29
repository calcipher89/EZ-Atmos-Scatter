"""How node_layout.py arranges the inside of EzAtmosScatter: its modules and their Backdrops,
the side chains that go left of the trunk, and labels on the Switches."""

MODULES = [
    # (Backdrop label, tile_color, node names it holds as a regex)
    ("Inputs", 0x4a5a6aff, r"hdri|sun|dome|camera|BlankHDRI|HDRIInput|InputDownscale|HDRISource"),
    ("Skydome", 0x4a5a6aff, r"DomeRemap|UseDome"),
    ("Sun light + transmittance LUT", 0x7a6a3aff,
     r"LUTRef|TransmittanceLUT|LightDome.*|UseDomeLight|LightProxy|LightRef|Light"),
    ("Self-lit sky", 0x7a6a3aff, r"SelfSky.*|SelfLight|SkyLightSource"),
    ("Scatter passes", 0x3a5a4aff, r"ScatterResolution|Scatter_.*|\w+_(sky|ground)_(cut|up|trim)|\w+_full|\w+_resolution"),
    ("Preview comp", 0x5a4a6aff, r"AddMie|AddSkyLight|Attenuate|PreviewComp|HazePreview.*|ViewOutput"),
    ("AOV layers", 0x6a4a4aff, r"MainRGB|Layer_.*"),
    ("Bake", 0x444444ff, r"Bake.*|UseBake"),
    ("Back to HDRI size", 0x6a4a4aff, r"OutputUpscale|OutputResolution"),
    ("Remap to dome / camera", 0x6a4a4aff,
     r"Roll.*|Rolled|To(Dome|Camera).*|DomeUV|CameraFormat|CameraUV|OutputAs|Output\d*"),
]

LEFT = [r"BlankHDRI", r"InputDownscale"]

LABELS = {
    "HDRIInput": "blank if no hdri",
    "HDRISource": "downscale on",
    "UseDome": "dome input",
    "UseDomeLight": "dome input",
    "SkyLightSource": "self lit",
    "ViewOutput": "view output",
    "UseBake": "use bake",
    "OutputResolution": "back to hdri size",
    "OutputAs": "output as",
}

HINTS = {"modules": MODULES, "left": LEFT, "labels": LABELS}
