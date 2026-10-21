# EZ Atmos Scatter

Physically based atmospheric scattering for The Foundry Nuke, built in BlinkScript.

EZ Atmos Scatter takes a lat-long HDRI and a sun direction (found in the HDRI, or driven by
an Axis node) and generates atmospheric scattering passes as AOV layers that can be
composited on top of the source HDRI.

Target: Nuke 15.1.

## Status

Step 2 of 4: the EzAtmosScatter gizmo, lit by the HDRI (automatic sun detection, sun colour
and brightness from the image, sky light). Depth-aware haze and multiple scattering come next.

## Contents

| Path | What it is |
| --- | --- |
| `gizmos/EzAtmosScatter.gizmo` | The node artists use. Built from the kernels by `python/build_gizmo.py` |
| `blink/AtmosScatter.blink` | BlinkScript kernel: Rayleigh + Mie single scattering per lat-long pixel |
| `blink/EzAtmosLight.blink` | BlinkScript kernel: measures the sun and sky light in the HDRI |
| `blink/EzAtmosTransmittanceLUT.blink` | BlinkScript kernel: precomputes the optical depth towards the sun as a 256x64 table |
| `python/build_gizmo.py` | Rebuilds the gizmo after a kernel change |
| `python/ezatmosscatter.py` | Helpers for the gizmo's buttons |
| `init.py`, `menu.py` | Plugin path and the Nodes menu entry |
| `reference/atmos_reference.py` | NumPy port of the scattering core for checking the math outside Nuke |
| `docs/previews/contact_sheet.png` | Reference renders: inscatter, Mie and transmittance at 45°, 10°, 2° and -2° sun elevation |

![Reference renders](docs/previews/contact_sheet.png)

## Installing

Clone the repo into `~/.nuke/plugins/EzAtmosScatter` and add this line to `~/.nuke/init.py`:

```python
nuke.pluginAddPath('./plugins/EzAtmosScatter')
```

The node then shows up under **Nodes > EzAtmosScatter**.

## Using it

1. Read in a lat-long HDRI and connect it to the `hdri` input.
2. Leave **sun from** on *Auto (HDRI)*, or plug an Axis into the `sun` input and set it to
   *Axis* (the sun is in the direction of the Axis's world position), or type a direction
   in *Manual*.
3. Pick what the main rgba shows with **view output**. Every pass is also written to its
   own layer, whatever the view output is:

| Layer | Contents |
| --- | --- |
| `atmos_inscatter` | Light scattered towards the camera (sky + haze + sky light) |
| `atmos_rayleigh` | Sky only (blue sky) |
| `atmos_mie` | Haze only (haze and glow around the sun) |
| `atmos_ambient` | Sky light: the whole HDRI sky scattered into the haze |
| `atmos_transmittance` | How much of the background survives along each view ray |
| `atmos_haze_color` | Depth haze colour: what infinitely deep haze looks like in each direction (see Depth haze below) |
| `atmos_haze_sun` | The sunlit part of `atmos_haze_color`: what shadowed haze loses |
| `atmos_haze_sky` | The sky-lit part of `atmos_haze_color`: what shadowed haze keeps |

The Scatter Preview Comp is `hdri * atmos_transmittance + atmos_inscatter`.

### Knobs

| Knob | Default | What it does |
| --- | --- | --- |
| view output | Scatter Preview Comp | What the main rgba shows |
| passes | Atmosphere | *Atmosphere*: rays run through the whole sky down to the ground. *Depth Haze*: every pass describes the haze around the camera out to *haze distance*, with no ground and no horizon line |
| sun from | Auto (HDRI) | Where the sun direction comes from: the HDRI, the Axis input or the manual knob |
| sun direction | (0, 0.5, -1) | Manual sun direction, +Y up |
| copy detected sun to manual | | Writes the sun found in the HDRI into *sun direction* |
| hdri rotation | 0 | Rotates the lat-long mapping, in degrees |
| self-lit (no HDRI) | off | For setups without an HDRI: sky light comes from this atmosphere's own sky, and the sun from *sun color* and *sun strength*. Replaces a second EzAtmosScatter used only as a sky |
| light from HDRI | on | Sun colour and brightness come from the HDRI. Off: *sun color* and *sun strength* set them |
| sun color | white | Tint on the HDRI's sun, or the sun colour when *light from HDRI* is off |
| sun strength | 1 | Multiplies the sun's brightness |
| sun boost | 1 | Only for clipped suns (JPEGs, LDR captures); scales the brightness estimated from the sky |
| sky light | 1 | How much of the HDRI sky lights the haze |
| sky amount | 1 | Air density (Rayleigh) |
| haze amount | 1 | Haze density (Mie) |
| haze glow size | 1 | Size of the glow around the sun |
| camera height (m) | 1 | Camera height above sea level |
| max distance (km) | 0 (off) | How far the haze reaches. Use it to add haze up to a set distance instead of a full sky |
| haze height (km) | 1.2 | How quickly the haze thins with altitude (its scale height). Low keeps it near the ground |
| haze density (1/m) | read only | Extinction per metre at camera height, for depth hazing in a comp |
| haze distance (km) | 5 | How far the depth haze reaches, for the *Haze Preview* view and the *Depth Haze* passes |
| quality | Normal | Samples per ray (Draft is about 4x faster than High) |
| viewer resolution | Half | Resolution the haze is computed at in the Nuke GUI (Full / Half / Quarter) |
| render resolution | Full | Resolution the haze is computed at in terminal and farm renders |

The **Advanced** section holds the physical constants (scattering coefficients, scale
heights, planet size) and the sun detection settings.

### Depth haze

The *Haze Color* view (and the `atmos_haze_color` layer) is the colour fog settles to when it is
infinitely deep, for every direction around the camera. It combines sunlight scattered
by the air and haze at camera height, strongest near the sun because haze scatters
mostly forwards, with the HDRI sky light scattered evenly. It has no ground and no
horizon line, so it can haze a plate with any metric depth pass:

```
T      = exp(-haze_density * depth_in_metres)
result = plate * T + hazeColor * (1 - T)
```

In a comp, an Expression node can read *haze density* from the gizmo
(`EzAtmosScatter1.haze_density.r` and so on), and `hazeColor` comes from a lat-long lookup
of `atmos_haze_color` along each pixel's view direction.

*Haze Preview* shows the result on the preview comp as if everything were *haze
distance* away. Setting **passes** to *Depth Haze* gives every layer (Scatter, Sky, Haze,
Sky Light, Transmittance) in that form, so they composite the same way as the atmosphere
passes: `plate * atmos_transmittance + atmos_inscatter`. There the haze also thins with height: along a ray at elevation
cos = dir.y each part of the atmosphere adds `beta(h0) * H * (1 - exp(-d * cos / H)) / cos`
of optical depth (scale height H), so looking up clears faster than looking sideways.
A low *haze height* with a high *haze amount* gives a fog bank sitting on the ground.

### How the HDRI lights it

`EzAtmosLight.blink` looks at a 512x256 copy of the HDRI. It finds the brightest spot above
the horizon, treats everything within 6° of it as the sun, and averages the rest of the
upper hemisphere as the sky.

- **Unclipped sun** (a real HDR capture): the sun's irradiance is measured from the image
  and divided by the atmosphere's transmittance towards the sun, so the scattering uses
  the light arriving at the top of the atmosphere.
- **Clipped sun** (its peak is under 20x the average sky): the energy is gone, so the sun
  is sized from the sky brightness instead, using the ratio this model has on a clear day.
  *sun boost* scales that estimate.

Lat-long convention: the centre column looks down -Z, the top row is straight up.

### Skydome

When the HDRI is shown on a skydome in the comp (a Sphere, often under TransformGeos,
rendered with ScanlineRender), plug the dome geometry into the **dome** input and the shot
camera into **camera**. The node follows the chain from the dome input up to the Sphere,
TransformGeos with their axis inputs included, and combines every transform at the frame
being rendered. It then rebuilds the HDRI as seen from the camera: for each direction, where
the ray from the camera hits the moved, rotated or squashed dome, using the Sphere's own
UV mapping. The light, sun and haze then line up with the dome in the comp, and follow it
when it is animated. Without a camera the dome's centre is used. *hdri rotation* still
adds on top, so leave it at 0. Moving the dome marks a bake out of date.

Checked against a ScanlineRender of a dome rotated, moved and scaled in Y twice (Sphere
and TransformGeo) and seen from an offset camera: the HDRI lands within one pixel at 2K.

### Speed

The haze is smooth, so it is computed at a reduced size and scaled back up, with the sky
and ground halves scaled separately so the horizon stays sharp. *viewer resolution* is
used while Nuke's GUI is open and *render resolution* when rendering from a terminal
(`$gui` decides which). Half and Quarter stay within about 2% of Full.

Measured on a 3044x1522 HDRI in Nuke 15.1 (RTX 3070, warm):

| | CPU | GPU |
| --- | --- | --- |
| Full | 3.1 s | 0.2 s |
| Half | 0.95 s | 0.2 s |
| Quarter | 0.36 s | 0.2 s |

On the farm:

- Terminal Nuke only uses the GPU when started with `--gpu`
  (`Nuke15.1.exe --gpu -x script.nk`). Without it BlinkScript runs on the CPU.
- Each new Nuke process compiles the kernels once before the first frame (about 7 s on
  the GPU, 30 s on the CPU), so render several frames per task.

### Baking

The node's whole output (every layer) can be baked to EXRs and read back instead of being
computed, which skips the kernels and their compile time on the farm.

- **bake now** renders the bake here and now. **bake range** picks the current frame
  (held for the whole shot, for a sun that doesn't move) or the script range.
- **make farm bake Write** adds a top-level Write with the same path instead, to render as
  a farm job that the comp renders depend on.
- **use baked** reads the bake, but only while the file exists and the settings still match
  the ones it was baked with. Otherwise the node computes live and its label reads
  *bake out of date: live*; it reads *baked* while the bake is used.

The bake goes next to the script by default:

```
<script dir>/ezatmos_cache/<script>/<node>/<script>_<node>.####.exr
/shows/abc/seq010/comp/ezatmos_cache/sh010_comp_v003/EzAtmosScatter1/sh010_comp_v003_EzAtmosScatter1.0001.exr
```

Set `EZATMOS_CACHE_DIR` to put it somewhere else (it replaces `<script dir>/ezatmos_cache`),
or type a path in *bake file* to override it for one node. Versioning the script up starts
a new cache folder, so bake again (or keep the old path in *bake file*).

## Rebuilding the gizmo

After changing a kernel, run

```
Nuke15.1.exe --nukex -i -t python/build_gizmo.py
```

It loads the kernels from `blink/`, embeds them in the group and writes
`gizmos/EzAtmosScatter.gizmo`.

## Reference renders

`python3 reference/atmos_reference.py --out docs/previews` regenerates the previews.
The NumPy port mirrors the scattering core of the kernel (a fixed sun, no HDRI lighting
or sky light), so it is the place to try changes to the model before porting them to
BlinkScript.

## References

- Sean O'Neil, *Accurate Atmospheric Scattering*, GPU Gems 2, ch. 16
- Eric Bruneton and Fabrice Neyret, *Precomputed Atmospheric Scattering* (2008)
- Leo Cao, [Atmospheric_Scattering](https://github.com/Zhongrui-Cao/Atmospheric_Scattering) (volumetric path-traced reference)
