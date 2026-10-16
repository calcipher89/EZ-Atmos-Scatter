# EZ Atmos Scatter

Physically based atmospheric scattering for The Foundry Nuke, built in BlinkScript.

EZ Atmos Scatter takes a lat-long HDRI and a sun direction (driven by an Axis node) and
generates atmospheric scattering passes as AOV layers that can be composited on top of the
source HDRI.

Target: Nuke 15.1.

## Status

Step 1 of 4: the core single-scattering kernel. The Axis-driven gizmo, HDRI-driven sun
colour and ambient, automatic sun detection and multiple scattering come next.

## Contents

| Path | What it is |
| --- | --- |
| `blink/AtmosScatter.blink` | BlinkScript kernel: Rayleigh + Mie single scattering per lat-long pixel |
| `python/build_test_setup.py` | Builds a test node graph in Nuke around a selected HDRI Read node |
| `reference/atmos_reference.py` | NumPy port of the kernel for checking the math outside Nuke |
| `docs/previews/contact_sheet.png` | Reference renders: inscatter, Mie and transmittance at 45°, 10°, 2° and -2° sun elevation |

![Reference renders](docs/previews/contact_sheet.png)

## Trying it in Nuke

1. Read in a lat-long HDRI and select the Read node.
2. In the Script Editor run
   `exec(open('/path/to/ez-atmos-scatter/python/build_test_setup.py').read())`
   and point it at `blink/AtmosScatter.blink` if asked.
3. Adjust the knobs on `AtmosScatter_master`. The other BlinkScript nodes follow it.

The setup writes four RGB layers on top of the HDRI:

| Layer | Contents |
| --- | --- |
| `atmos_inscatter` | Light scattered towards the camera (Rayleigh + Mie) |
| `atmos_rayleigh` | Rayleigh part only (blue sky) |
| `atmos_mie` | Mie part only (haze and glow around the sun) |
| `atmos_transmittance` | How much of the background survives along each view ray |

A physically consistent comp is `hdri * atmos_transmittance + atmos_inscatter`; the
`AtmosScatter_preview_comp` node shows exactly that.

### Kernel knobs

| Knob | Default | Notes |
| --- | --- | --- |
| `sun_direction` | (0, 0.5, -1) | World direction towards the sun, +Y up. Normalised internally |
| `sun_color`, `sun_intensity` | (1, 1, 1), 20 | Will come from the HDRI in step 2 |
| `camera_altitude_km` | 0.001 | Viewer height above sea level |
| `max_distance_km` | 0 (off) | Limits how far each ray marches. Use it to add haze up to a set distance instead of a full sky |
| `longitude_offset_deg` | 0 | Rotates the lat-long mapping to line up with your HDRI |
| `rayleigh_density`, `mie_density` | 1, 1 | Artist multipliers; raise `mie_density` for hazier air |
| `rayleigh_coefficients` | (0.0052, 0.0121, 0.0296) /km | Sea-level Rayleigh scattering at 680, 550, 440 nm |
| `mie_coefficient` | 0.021 /km | Sea-level Mie scattering; extinction is this / 0.9 |
| `rayleigh_scale_height_km`, `mie_scale_height_km` | 8.5, 1.2 | Exponential density falloff |
| `mie_g` | 0.76 | Cornette-Shanks asymmetry; higher is a tighter sun glow |
| `planet_radius_km`, `atmosphere_thickness_km` | 6360, 60 | |
| `view_samples`, `light_samples` | 16, 8 | Quality vs speed |
| `output` | 0 | 0 inscatter, 1 Rayleigh, 2 Mie, 3 transmittance, 4 preview comp |

Lat-long convention: the centre column looks down -Z, the top row is straight up.
If your sun lands in the wrong place horizontally, use `longitude_offset_deg`.

## Reference renders

`python3 reference/atmos_reference.py --out docs/previews` regenerates the previews.
The NumPy port mirrors the kernel line for line, so it is also the place to try changes
to the model before porting them to BlinkScript.

## References

- Sean O'Neil, *Accurate Atmospheric Scattering*, GPU Gems 2, ch. 16
- Eric Bruneton and Fabrice Neyret, *Precomputed Atmospheric Scattering* (2008)
- Leo Cao, [Atmospheric_Scattering](https://github.com/Zhongrui-Cao/Atmospheric_Scattering) (volumetric path-traced reference)
