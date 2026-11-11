# Turn-signal animations

Essentials uses its built-in chevrons and offers Frog, Pouncing Cat, Bouncing Ball and Unicorn Rider under Driving > Display > Whimsy. The full bundled catalog is also available through Galaxy's `SignalAnimation` endpoint. The upstream large and small screen settings retain StarPilot's original controls.

`starpilot/tandem/signals.py` owns the nine-pack catalog, selection validation, effective selection and Galaxy settings catalog entry. Selecting a non-stock pack enables Custom Themes and disables Random Themes, preserving the other saved theme choices. Holiday themes can override the selection. Simple Mode disables custom animations.

| Pack | Frames | Timing | Style |
| --- | ---: | ---: | --- |
| Frog | 6 | 125 ms | Travelling |
| Pouncing Cat | 6 | 125 ms | Travelling |
| Shooting Star | 6 | 125 ms | Travelling |
| Bouncing Ball | 40 | 75 ms | Travelling |
| Unicorn Rider | 20 | 60 ms | Travelling |
| Sequential | 6 | 125 ms | Static |
| Flow, Open Flow, Glide | 12 each | 62 ms | Static |

The owned renderer is `selfdrive/ui/tandem/onroad/turn_signals.py`. It reads the blinkers and blind-spot state without requiring engagement or openpilot longitudinal control. Right turns mirror the frames; hazards draw both directions. Full-screen alerts suppress animations; smaller alerts reserve space below them.

Frog stays in StarPilot's `starpilot/assets/holiday_themes/world_frog_day/signals/`. The other eight asset directories live in `selfdrive/ui/tandem/assets/signal_packs/`. The theme manager calls the owned installer at boot to copy them into normal theme packs. The renderer can use bundled frames immediately while theme activation catches up, then prefers the installed copy. Installed PNG packs use numbered frames, an optional `turn_signal_blindspot.png` and `traditional_<milliseconds>` or `static_<milliseconds>` timing markers. GIF-only packs are unsupported.

To add a bundled pack, add its signals directory and metadata in `starpilot/tandem/signals.py`. The renderer and Galaxy derive their catalogs from that module. Update the owned settings picker if it should also appear in Whimsy, its search entry and its mock first.

The asset generators live in `selfdrive/ui/tandem/tools/`: `make_pouncing_cat_signals.py`, `make_shooting_star_signals.py`, `make_sequential_signals.py`, `make_motion_signals.py`, `make_bouncing_ball_signals.py` and `make_unicorn_rider_signals.py`. Running a generator needs CairoSVG; the runtime renderer does not. Indicator asset geometry is covered by `tests/test_turn_signals.py`.

## Previewing the assets

`tools/render_onroad_preview.py` renders the Essentials driving view with sample data and a controlled animation clock. Its preview subclass permits the full catalog, including packs outside the Whimsy picker.

```sh
python selfdrive/ui/tandem/tools/render_onroad_preview.py --pack sequential --out /tmp/preview
python selfdrive/ui/tandem/tools/render_onroad_preview.py --pack bouncing_ball --right --gif /tmp/ball.gif
python selfdrive/ui/tandem/tools/render_onroad_preview.py --pack flow --hazards --blindspot --frames 1
```

The default captures one animation cycle. On Linux without a display, use `xvfb-run -a`; on macOS a window may flash briefly. GIF export needs Pillow. `--speed-at-bottom` affects only this preview; there is no device param for it. `--alert small|mid` supplies a sample alert. Native bindings and a suitable display context are needed for the driving-view preview; use `tools/render/scene_signals.py` with the normal screenshot harness for isolated asset captures.

Run the renderer, catalog and Galaxy regressions with the other owned tests:

```sh
pytest selfdrive/ui/tandem/tests/test_turn_signals.py selfdrive/ui/tandem/tests/test_galaxy_signals.py
```

Before a device release, check left, right and hazard signals while parked, with ACC disengaged and engaged.
