"""Helpers used by the EzAtmosScatter gizmo's buttons."""

import nuke


def copy_detected_sun(group):
    """Copy the sun direction measured from the HDRI into the gizmo's manual knob."""
    with group:
        light = nuke.toNode("Light")
        values = [light.sample(channel, 0.5, 0.5) for channel in ("red", "green", "blue")]
    if not any(values):
        nuke.message("No sun found: is an HDRI connected?")
        return
    group["sun_direction"].setValue(values)
    group["sun_from"].setValue("Manual")
