# Project screenshots

These PNGs illustrate the current Tandem UI in the repository's root README. They are renders
of the implemented screens with sample data, rather than screenshots of the HTML design mocks.
The driving screen uses a schematic road instead of a camera recording.

| Published image | Render output | Scene in `../../tools/render/` |
| --- | --- | --- |
| `onroad.png` | `onroad_nav.png` | `scene_onroad.py` |
| `home.png` | `sidebar_home.png` | `scene_sidebar.py` |
| `settings.png` | `hub.png` | `scene_compare.py` |
| `everyday.png` | `driving.png` | `scene_compare.py` |
| `destinations.png` | `destinations.png` | `scene_destinations.py` |

To refresh them, use the built-screen rendering instructions in the root
[AGENTS.md](../../../../../AGENTS.md), then copy the selected render outputs here with the
published names above. Normalize any Retina captures to 2160 by 1080 pixels and save as optimized
RGB PNGs. Inspect each image before committing it, and keep the root README's captions in sync.

The full render output and comparison pages belong in `tools/out/`, which stays out of Git.
