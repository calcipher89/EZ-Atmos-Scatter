# EZ Atmos Scatter

Physically based atmospheric scattering for The Foundry Nuke, built in BlinkScript.

EZ Atmos Scatter takes a lat-long HDRI and a sun direction (driven by an Axis node) and
generates atmospheric scattering passes as AOV layers that can be composited on top of the
source HDRI.

Target: Nuke 15.1.

## References

- Sean O'Neil, *Accurate Atmospheric Scattering*, GPU Gems 2, ch. 16
- Eric Bruneton and Fabrice Neyret, *Precomputed Atmospheric Scattering* (2008)
- Leo Cao, [Atmospheric_Scattering](https://github.com/Zhongrui-Cao/Atmospheric_Scattering) (volumetric path-traced reference)
