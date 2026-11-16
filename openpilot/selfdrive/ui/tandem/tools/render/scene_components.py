"""The component library on its own: a settings page built from every common control, and a dialog over it.

Checks drawing on StarPilot 7's raylib before any screen is ported (PORTING.md, stage 1).
"""
from openpilot.starpilot.ui.raylib import rl
from openpilot.selfdrive.ui.tandem import (BottomNav, Button, ButtonStyle, Dialog, ListPanel, Segmented, SettingRow, SettingsPage, Sidebar,
                                           SidebarItem, Slider, Stepper, Switch, Text, Tone)


def main(frame, save, out, tap, gui_app):
  state = {"style": 1, "smart": True, "volume": 70, "gap": 3}
  content = ListPanel([
    SettingRow("Driving Style", "Sets following gap, acceleration and braking together",
               Segmented(["Relaxed", "Standard", "Sport"], selected=lambda: state["style"], on_change=lambda i: state.update(style=i))),
    SettingRow("Smart Slowdowns", "Slows for curves and stop lights", Switch(lambda: state["smart"], lambda v: state.update(smart=v))),
    SettingRow("Volume", "How loud alerts are", Slider(lambda: state["volume"], lambda v: state.update(volume=v), 0, 100, step=10)),
    SettingRow("Following gap", "Seconds behind the car ahead", Stepper(lambda: state["gap"], lambda v: state.update(gap=v), 1, 4)),
    SettingRow("Languages", "Tiếng Việt · 日本語 · 한국어 · ไทย · العربية · Українська", Button("Check", style=ButtonStyle.SECONDARY)),
    Text("Figtree draws Latin text; the Noto fallback draws the rest."),
  ], title="Everyday")
  page = SettingsPage(content,
                      nav=BottomNav(["Driving", "Device", "Connections", "Software"], selected=0, on_select=lambda i: None),
                      sidebar=Sidebar("DRIVING", [SidebarItem("Everyday"), SidebarItem("Weather", value="Auto")], selected=0))
  rect = rl.Rectangle(0, 0, 2160, 1080)
  for _ in range(6):
    frame(lambda: page.render(rect))
  save(f"{out}/components.png")
  dialog = Dialog("Reset settings?", "Driving settings go back to their defaults. Saved places stay.", "Reset", tone=Tone.DANGER)
  for _ in range(6):
    frame(lambda: (page.render(rect), dialog.render(rect)))
  save(f"{out}/components_dialog.png")
