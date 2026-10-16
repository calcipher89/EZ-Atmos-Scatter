"""NumPy port of blink/AtmosScatter.blink, used to check the math outside Nuke.

Renders the kernel's passes for a few sun elevations to lat-long PNG
previews (gamma 2.2 and a clamp, no tone mapping), plus a contact sheet.

    python3 reference/atmos_reference.py --out docs/previews
"""

import argparse
import os

import numpy as np
from PIL import Image

DEFAULTS = dict(
    sun_color=(1.0, 1.0, 1.0),
    sun_intensity=20.0,
    camera_altitude_km=0.001,
    max_distance_km=0.0,
    longitude_offset_deg=0.0,
    rayleigh_density=1.0,
    mie_density=1.0,
    rayleigh_coefficients=(0.0052, 0.0121, 0.0296),
    mie_coefficient=0.021,
    rayleigh_scale_height_km=8.5,
    mie_scale_height_km=1.2,
    mie_g=0.76,
    planet_radius_km=6360.0,
    atmosphere_thickness_km=60.0,
    view_samples=16,
    light_samples=8,
)


def _exit_distance(b, c):
    return -b + np.sqrt(np.maximum(b * b - c, 0.0))


def _ground_distance(b, c):
    disc = b * b - c
    t = -b - np.sqrt(np.maximum(disc, 0.0))
    return np.where((b > 0.0) | (disc < 0.0), -1.0, t)


def render(width, height, sun_direction, **overrides):
    """Return dict of passes (H x W x 3 float32), row 0 = top of the image."""
    p = dict(DEFAULTS, **overrides)
    f = np.float32
    Re = f(p["planet_radius_km"])
    Ra = Re + f(p["atmosphere_thickness_km"])
    Hr = f(p["rayleigh_scale_height_km"])
    Hm = f(p["mie_scale_height_km"])
    beta_r = np.array(p["rayleigh_coefficients"], f) * f(p["rayleigh_density"])
    beta_m = f(p["mie_coefficient"] * p["mie_density"])
    beta_m_ext = beta_m / f(0.9)
    sun_dir = np.array(sun_direction, f)
    sun_dir /= np.linalg.norm(sun_dir)

    # Nuke pixel rows count up from the bottom; build in that order, flip at the end.
    xs = (np.arange(width, dtype=f) + 0.5) / width
    ys = (np.arange(height, dtype=f) + 0.5) / height
    u, v = np.meshgrid(xs, ys)
    lon = (u - 0.5) * 2 * np.pi + np.radians(p["longitude_offset_deg"])
    lat = (v - 0.5) * np.pi
    d = np.stack([np.sin(lon) * np.cos(lat), np.sin(lat), -np.cos(lon) * np.cos(lat)], -1).astype(f)

    h0 = f(max(p["camera_altitude_km"], 0.0))
    r0 = Re + h0
    origin = np.array([0.0, r0, 0.0], f)
    b = d @ origin
    t_max = _exit_distance(b, (r0 - Ra) * (r0 + Ra))
    t_ground = _ground_distance(b, h0 * (r0 + Re))
    t_max = np.where(t_ground > 0.0, t_ground, t_max)
    if p["max_distance_km"] > 0.0:
        t_max = np.minimum(t_max, f(p["max_distance_km"]))

    n_view, n_light = p["view_samples"], p["light_samples"]
    seg = t_max / n_view
    od_r = np.zeros_like(seg)
    od_m = np.zeros_like(seg)
    sum_r = np.zeros(seg.shape + (3,), f)
    sum_m = np.zeros(seg.shape + (3,), f)
    for i in range(n_view):
        pt = origin + d * (seg * (i + 0.5))[..., None]
        h = np.linalg.norm(pt, axis=-1) - Re
        dens_r = np.exp(-h / Hr) * seg
        dens_m = np.exp(-h / Hm) * seg
        od_r += dens_r
        od_m += dens_m

        # Light ray towards the sun.
        r = h + Re
        bs = pt @ sun_dir
        lit = _ground_distance(bs, h * (r + Re)) <= 0.0
        lseg = _exit_distance(bs, (r - Ra) * (r + Ra)) / n_light
        sod_r = np.zeros_like(lseg)
        sod_m = np.zeros_like(lseg)
        for j in range(n_light):
            q = pt + sun_dir * (lseg * (j + 0.5))[..., None]
            hq = np.linalg.norm(q, axis=-1) - Re
            sod_r += np.exp(-hq / Hr) * lseg
            sod_m += np.exp(-hq / Hm) * lseg
        tau = beta_r * (od_r + sod_r)[..., None] + beta_m_ext * (od_m + sod_m)[..., None]
        att = np.exp(-tau) * lit[..., None]
        sum_r += att * dens_r[..., None]
        sum_m += att * dens_m[..., None]

    mu = d @ sun_dir
    g = f(p["mie_g"])
    phase_r = 3.0 / (16.0 * np.pi) * (1.0 + mu * mu)
    phase_m = (3.0 / (8.0 * np.pi) * ((1 - g * g) * (1 + mu * mu))
               / ((2 + g * g) * np.maximum(1 + g * g - 2 * g * mu, 1e-6) ** 1.5))
    sun = np.array(p["sun_color"], f) * f(p["sun_intensity"])
    rayleigh = sun * sum_r * beta_r * phase_r[..., None]
    mie = sun * sum_m * beta_m * phase_m[..., None]
    trans = np.exp(-(beta_r * od_r[..., None] + beta_m_ext * od_m[..., None]))
    passes = dict(inscatter=rayleigh + mie, rayleigh=rayleigh, mie=mie, transmittance=trans)
    return {k: np.flipud(v).astype(f) for k, v in passes.items()}


def to_png(img, path, exposure=1.0):
    rgb = np.clip(img * exposure, 0.0, 1.0) ** (1 / 2.2)
    Image.fromarray((rgb * 255 + 0.5).astype(np.uint8)).save(path)


def sun_from_angles(elevation_deg, azimuth_deg=0.0):
    """Azimuth 0 faces -Z (centre of the lat-long), positive turns towards +X."""
    el, az = np.radians(elevation_deg), np.radians(azimuth_deg)
    return (np.sin(az) * np.cos(el), np.sin(el), -np.cos(az) * np.cos(el))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="docs/previews")
    ap.add_argument("--width", type=int, default=512)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    sheet_rows = []
    for elevation in (45, 10, 2, -2):
        passes = render(args.width, args.width // 2, sun_from_angles(elevation))
        for name, img in passes.items():
            to_png(img, os.path.join(args.out, f"sun{elevation:+03d}_{name}.png"))
        sheet_rows.append(np.concatenate([passes[k] for k in ("inscatter", "mie", "transmittance")], 1))
        hi = passes["inscatter"][: args.width // 4]
        print(f"sun {elevation:+3d} deg  upper-hemisphere inscatter mean {hi.mean(axis=(0, 1)).round(4)}"
              f"  max {hi.max():.3f}")
    # One row per sun elevation: inscatter | mie | transmittance.
    to_png(np.concatenate(sheet_rows, 0), os.path.join(args.out, "contact_sheet.png"))


if __name__ == "__main__":
    main()
