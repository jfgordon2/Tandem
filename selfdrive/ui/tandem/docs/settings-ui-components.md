# Settings components

Essentials settings use the owned component library in `selfdrive/ui/tandem/`:
`tokens.py`, `layout.py`, `draw.py`, `controls.py`, `rows.py`, `blocks.py`,
`chrome.py` and `overlays.py`. Upstream's Aether widgets keep StarPilot's own
screens and controller views. New Tandem screens do not extend those widgets.

Use `T.px()` and `T.font_px()` for dimensions from an approved HTML mock. Build
pages from `SettingsPage`, `TitledPage`, `ListPanel`, `Card`, `Columns` and `Stack`;
rows use `SettingRow` and shared controls. `draw.py` owns text translation,
font selection and scoped shaping. `scroll.py` specializes gesture rejection
for Tandem without changing upstream's scroll panel.

Controllers retain StarPilot's rules and saved params. Adapters live in
`settings/`; explicit notification and named-confirmation hooks keep upstream
checks while letting Tandem present its own dialogs. See `controllers.py`.

Render every sample scene, or save selected PNG names:

```sh
PYTHONPATH=. BIG=1 python selfdrive/ui/tandem/tools/render_settings_preview.py --out /tmp/settings-preview
PYTHONPATH=. BIG=1 python selfdrive/ui/tandem/tools/render_settings_preview.py --page hub --page display --out /tmp/settings-preview
```

On Linux without a display, prefix the command with `xvfb-run -a`. The full mock
comparison workflow is in `AGENTS.md`; `tools/render/scene_compare.py` names the
scenes and `design/compare.json` associates them with approved mock screenshots.
