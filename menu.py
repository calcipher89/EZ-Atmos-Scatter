import nuke

toolbar = nuke.menu("Nodes")
menu = toolbar.addMenu("EzAtmosScatter")
menu.addCommand("EzAtmosScatter", "nuke.createNode('EzAtmosScatter')")
