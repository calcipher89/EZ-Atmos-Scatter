"""Build a test setup for blink/AtmosScatter.blink in Nuke 15.1.

Select the Read node holding your lat-long HDRI, then run in the Script Editor:

    exec(open('/path/to/ez-atmos-scatter/python/build_test_setup.py').read())

It creates one BlinkScript per pass and copies each into its own layer
(atmos_inscatter, atmos_rayleigh, atmos_mie, atmos_transmittance) on top of the
HDRI. Only the first BlinkScript ("AtmosScatter_master") needs tweaking: the
others follow it through expressions and differ only in their output pass.
"""

import os

import nuke

KERNEL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "blink", "AtmosScatter.blink") if "__file__" in globals() else None

PASSES = [
    # (output index, layer name)
    (0, "atmos_inscatter"),
    (1, "atmos_rayleigh"),
    (2, "atmos_mie"),
    (3, "atmos_transmittance"),
]


def _param_knob(node, param):
    """BlinkScript names parameter knobs '<KernelName>_<param>'."""
    for name, knob in node.knobs().items():
        if name.endswith("_" + param):
            return knob
    raise RuntimeError("BlinkScript knob for parameter '%s' not found on %s" % (param, node.name()))


def _make_blink(kernel_source, upstream, name):
    node = nuke.nodes.BlinkScript(name=name)
    node.setInput(0, upstream)
    node["kernelSource"].setValue(kernel_source)
    node["recompile"].execute()
    return node


def _ensure_layer(layer):
    nuke.Layer(layer, ["%s.red" % layer, "%s.green" % layer, "%s.blue" % layer])


def build(kernel_path=None):
    kernel_path = kernel_path or KERNEL_PATH
    if not kernel_path or not os.path.exists(kernel_path):
        kernel_path = nuke.getFilename("Locate AtmosScatter.blink", "*.blink")
    with open(kernel_path) as f:
        kernel_source = f.read()

    source = nuke.selectedNode()
    master = None
    stream = source
    for index, (output, layer) in enumerate(PASSES):
        blink = _make_blink(kernel_source, source, "AtmosScatter_master" if index == 0 else "AtmosScatter_" + layer)
        if master is None:
            master = blink
        else:
            # Follow every master parameter except the pass selector.
            for name, knob in master.knobs().items():
                if name.startswith("AtmosScatter_") and not name.endswith("_output") and name in blink.knobs():
                    blink[name].setExpression("%s.%s" % (master.name(), name))
        _param_knob(blink, "output").setValue(output)
        blink.setXYpos(source.xpos() + 150 * (index + 1), source.ypos() + 100)

        _ensure_layer(layer)
        copy = nuke.nodes.Copy(name="Copy_" + layer)
        copy.setInput(0, stream)
        copy.setInput(1, blink)
        for i, channel in enumerate(("red", "green", "blue")):
            copy["from%d" % i].setValue("rgba." + channel)
            copy["to%d" % i].setValue("%s.%s" % (layer, channel))
        copy.setXYpos(source.xpos(), source.ypos() + 200 + 60 * index)
        stream = copy

    preview = _make_blink(kernel_source, source, "AtmosScatter_preview_comp")
    for name, knob in master.knobs().items():
        if name.startswith("AtmosScatter_") and not name.endswith("_output") and name in preview.knobs():
            preview[name].setExpression("%s.%s" % (master.name(), name))
    _param_knob(preview, "output").setValue(4)
    preview.setXYpos(source.xpos() + 150 * (len(PASSES) + 1), source.ypos() + 100)

    return stream


build()
