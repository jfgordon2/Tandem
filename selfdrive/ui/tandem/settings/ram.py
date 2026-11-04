"""Device › RAM (design/systemram.html): what was using RAM at the peak of each of the last drives that ran low.

ram.RamLog records the snapshots from the drive screen; this panel only shows them. The section is hidden until the first
drive runs low; opening it clears the sidebar's dot.
"""
from __future__ import annotations

import datetime
from collections.abc import Callable

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.blocks import Label
from openpilot.selfdrive.ui.tandem.controls import Segmented
from openpilot.selfdrive.ui.tandem.i18n import N_, t_, translate
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, inset, row
from openpilot.selfdrive.ui.tandem.ram import DESCRIPTIONS, RamLog, Snapshot
from openpilot.selfdrive.ui.tandem.rows import ListPanel, Padded, Text
from openpilot.system.ui.widgets import Widget

ROW_HEIGHT = T.px(41)
NAME_WIDTH, WHAT_WIDTH, SIZE_WIDTH = T.px(120), T.px(190), T.px(70)


def size_text(size: float) -> str:
  """1.3 GB from a gigabyte up, else 620 MB."""
  return t_("{} GB", f"{size / 2**30:.1f}") if size >= 2**30 else t_("{} MB", f"{size / 2**20:.0f}")


def when_text(when: float, now: datetime.datetime | None = None) -> str:
  """Today 4:12 PM, Yesterday 8:40 AM, or Oct 30 for older drives."""
  at = datetime.datetime.fromtimestamp(when)
  today = (now or datetime.datetime.now()).date()
  clock = at.strftime("%-I:%M %p")
  if at.date() == today:
    return t_("Today {}", clock)
  if at.date() == today - datetime.timedelta(days=1):
    return t_("Yesterday {}", clock)
  return at.strftime("%b %-d")


def drive_label(snap: Snapshot, now: datetime.datetime | None = None) -> str:
  return t_("{} · {}%", when_text(snap.when, now), snap.percent)


class ProcessRow(Component):
  """A process's name, what it does, a bar against the largest, and its size; or "Everything else" (bar=None)."""
  grow_touch_target = False

  def __init__(self, snap: Callable[[], Snapshot], index: int):
    super().__init__()
    self._snap = snap
    self._index = index   # into snap.top; len(top) is "Everything else"

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, ROW_HEIGHT

  def _render(self, rect: rl.Rectangle):
    snap = self._snap()
    if self._index > len(snap.top):
      return
    body = inset(rect, x=T.PANEL_HEADER_INSET)
    if self._index == len(snap.top):
      draw.text(body, N_("Everything else"), T.font_px(15), T.TEXT_TERTIARY)
      draw.text(body, size_text(snap.rest), T.font_px(16), T.TEXT_TERTIARY, T.FONT_BOLD, Align.END)
      return
    name, size = snap.top[self._index]
    largest = snap.top[0][1] or 1
    name_r, what_r, bar_r, size_r = row(body, [NAME_WIDTH, WHAT_WIDTH, FILL, SIZE_WIDTH], T.px(16))
    draw.text(name_r, draw.fit(name, T.font_px(15), T.FONT_MONO, name_r.width), T.font_px(15), T.TEXT, T.FONT_MONO)
    what = DESCRIPTIONS.get(name)
    if what:
      draw.text(what_r, draw.fit(translate(what), T.SIZE_SUBTITLE, T.FONT, what_r.width), T.SIZE_SUBTITLE, T.TEXT_TERTIARY)
    track = rl.Rectangle(bar_r.x, bar_r.y + (bar_r.height - T.px(8)) / 2, bar_r.width, T.px(8))
    draw.fill(track, T.TRACK, T.px(4))
    draw.fill(rl.Rectangle(track.x, track.y, max(T.px(8), track.width * size / largest), track.height), T.DANGER, T.px(4))
    draw.text(size_r, size_text(size), T.font_px(16), T.TEXT, T.FONT_BOLD, Align.END)


def ram_panel(log: RamLog, now_percent: Callable[[], int]) -> Widget:
  """The picker of drives, then the chosen drive's processes. Opening it clears the sidebar's dot."""
  from openpilot.selfdrive.ui.tandem.settings.model import Rebuilding
  chosen = [0]

  def build() -> ListPanel:
    snaps = log.snapshots()
    chosen[0] = min(chosen[0], max(0, len(snaps) - 1))
    header = Label(lambda: t_("Now {}% used", now_percent()), T.font_px(15), T.TEXT_TERTIARY, T.FONT, h=Align.END, fit=True)
    if snaps:   # the section is hidden until the first; the text covers the moment before it hides
      picker = Segmented([drive_label(s) for s in snaps], lambda: chosen[0], lambda i: chosen.__setitem__(0, i), equal=True,
                         font_size=T.font_px(15))
      items: list[Widget] = [Padded(picker, y=T.px(10)),
                             *[ProcessRow(lambda: snaps[chosen[0]], i) for i in range(len(snaps[0].top) + 1)]]
    else:
      items = [Text(N_("No drive has run low on RAM yet."))]
    return ListPanel(items, title=N_("RAM"),
                     subtitle=N_("What was using it at the peak of each drive that ran low. The last three drives are kept."),
                     header_control=header, footnote=N_("Added to Report a Problem. A reboot clears RAM."))

  return Rebuilding(lambda: tuple((s.when, s.percent) for s in log.snapshots()), build, on_show=log.mark_seen)
