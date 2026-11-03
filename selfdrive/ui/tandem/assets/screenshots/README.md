# Project screenshots

These PNGs illustrate the current Tandem UI in the repository's root README. They are renders
of the implemented screens with sample data, rather than screenshots of the HTML design mocks.
The driving screen uses a schematic road instead of a camera recording.

| Published image | Render output | Scene in `../../tools/render/` |
| --- | --- | --- |
| `onroad.png` | `onroad_hero.png` (a new-limit offer, two chips, compass and weather) | `scene_onroad.py` |
| `home.png` | `homeweather.png` (with the forecast strip) | `scene_sidebar.py` |
| `settings.png` | `hub.png` | `scene_compare.py` |
| `everyday.png` | `driving.png` | `scene_compare.py` |
| `destinations.png` | `destinations.png` | `scene_destinations.py` |
| `voice.png` | `voicelistening.png` | `scene_destinations.py` |
| `helpsteer.png` | `onroad_helpsteer.png` | `scene_onroad.py` |
| `navigation.png` | `onroad_nav.png` | `scene_onroad.py` |
| `developer.png` | `onroaddev.png` | `scene_dev.py` |

To refresh them, use the built-screen rendering instructions in the root
[AGENTS.md](../../../../../AGENTS.md), then copy the selected render outputs here with the
published names above. Normalize any Retina captures to 2160 by 1080 pixels and save as optimized
RGB PNGs. Inspect each image before committing it, and keep the root README's captions in sync.

The full render output and comparison pages belong in `tools/out/`, which stays out of Git.

## README animation

`interface-tour.gif` is a looping, 63-second tour of 26 built screens at 1200 × 654 pixels, including
the caption strip. It starts with the driving view, then visits Home, destinations, voice typing,
navigation, driving settings, device settings, connections and software. The CAN recorder screens
and other testing variants are excluded by the generator's explicit screen list.

After refreshing the built-screen renders, regenerate the GIF from the repo root (needs Pillow):

```sh
python3 selfdrive/ui/tandem/tools/make_interface_gif.py --renders selfdrive/ui/tandem/tools/out/renders
```

The generator validates every source image, slide and hold time, and checks that the GIF loops.
Each slide has its own palette so small colored details survive GIF encoding. Cuts hold each screen
for 2–3 seconds; there are no flashing transitions. Change `SLIDES` in the generator to adjust the
sequence or timing, then inspect the decoded frames and update the root README's duration if needed.
