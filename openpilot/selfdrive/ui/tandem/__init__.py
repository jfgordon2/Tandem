"""Tandem: this fork's UI, built on StarPilot. Essentials is its design language; this package is the component library.

Screens are composed from these components instead of drawing with raylib directly:

  page = SettingsPage(
    sidebar=Sidebar("Driving", [SidebarItem("Everyday"), SidebarItem("Weather", value="Auto")], selected=0),
    content=ListPanel([
      SettingRow("Driving Style", "Sets following gap, acceleration and braking together",
                 Segmented(["Relaxed", "Standard", "Sport"], selected=get_style, on_change=set_style)),
      SettingRow("Smart Slowdowns", "Slows for curves and stop lights", Switch(get_smart, set_smart)),
    ], title="Everyday"),
    nav=BottomNav(["Driving", "Device", "Network", "Bluetooth", "Software"], selected=0, on_select=open_tab),
  )

Values can be plain or callables (read every frame), so rows can bind straight to Params.
Tokens and drawing helpers are in `tokens` and `draw`; see design/tokens.md.
"""
from openpilot.selfdrive.ui.tandem import draw, layout, tokens
from openpilot.selfdrive.ui.tandem.base import Bindable, Component, resolve, size_of
from openpilot.selfdrive.ui.tandem.chrome import BottomNav, HubGrid, HubTile, PageHeader, SettingsPage, Sidebar, SidebarItem, close_glyph
from openpilot.selfdrive.ui.tandem.controls import (Badge, Button, ButtonRow, ButtonStyle, ChoiceCards, Chip, ProgressBar, Segmented,
                                                    Slider, Stepper, Switch, ToggleButton, Tone, ValueButton, back_glyph)
from openpilot.selfdrive.ui.tandem.overlays import Dialog, Sheet, Toast
from openpilot.selfdrive.ui.tandem.rows import Banner, ListPanel, OptionList, Padded, SectionHeader, SettingRow, Text

__all__ = [
  "draw", "layout", "tokens",
  "Bindable", "Component", "resolve", "size_of",
  "BottomNav", "HubGrid", "HubTile", "PageHeader", "SettingsPage", "Sidebar", "SidebarItem", "close_glyph",
  "Badge", "Button", "ButtonRow", "ButtonStyle", "ChoiceCards", "Chip", "ProgressBar", "Segmented", "Slider", "Stepper", "Switch",
  "ToggleButton", "Tone", "ValueButton", "back_glyph",
  "Dialog", "Sheet", "Toast",
  "Banner", "ListPanel", "OptionList", "Padded", "SectionHeader", "SettingRow", "Text",
]
