<!-- part: Part IX - Visualization, Interface and Operations -->
# 3D Visualization

Two scenes share SAILAB's viewer stylesheet, controls, timeline, probe and export, but each draws its own hazard. The scene files are built from saved arrays (`frames.npz`, `impacts.json.gz`, `rocks.npz`), so the look can change and every run be re-rendered without re-simulating (`rebuild_scene`).

## Debris flow and landslide

SAILAB's water surface (blue, glossy) is gone. Three things replace it:

1. **A rubble body.** A displaced mesh (three.js, standing on Mapbox's own terrain) follows the flow depth, with a per-pixel material in metres: dark wet mud while moving, pale cracked mud at rest, cobbles and boulders from noise thresholds, gravel grain, a warm sheen on the fast front. The mesh normals come from the displaced surface itself, so the lobes read as relief. A first version extruded stacked depth contours and produced stepped pillars; a second used rounded contours and produced smooth blobs; only the displaced surface with a rubble material read as debris.
2. **A scar layer.** Each cell remembers when it failed. It flashes red-orange at that moment and then stays as pale exposed earth with a ragged darker rim (the failed mask is blurred and thresholded with noise, so the outline is not a blocky grid).
3. **A terrain-change mode.** Net bed change from the solver: blue where soil was lost (scar and scour), brown where it was gained (deposit), lit as relief.

Other changes: the flow-speed mode uses a blue-to-dark-red ramp; contact shadows fall beside the flow; buildings change colour with the depth reached so far (damage curve of Ch. {{ch:exposure_damage}}); the loop is 24 s instead of 9 so events can be followed; the camera is placed below the deposit looking up the slope toward the source.

## Earthquake

For earthquake runs the scene adds the epicentre (red marker), the rupture trace along the fault (glowing line), expanding wavefront rings, a **Ground shaking** map of PGA, and a brief damped shake of the camera as the wave passes. Failures begin at the quake time with the same flash and scar. **The wavefront speed is not physical:** the real S wave crosses a 5 km area in about a second, far shorter than any animation window, so the rings run at a time-scaled speed for visibility. The shaking map is the Joyner-Boore field of Ch. {{ch:earthquake_failure}}, without site amplification.

## Checking the renders

Scenes were rendered in headless Chromium through the DevTools protocol (`scripts/shot.py`), which waits for the scene to settle and reports JavaScript errors, and judged by eye at several moments of the event. This found real faults: the animation controls were blank because of a script error that only the page's own error hook revealed. A software GL renderer is used, so real-GPU frame rate is not measured.

## Export

PNG of the current view and an MP4 recorded from the canvas, transcoded on the server (`/export-video`).
