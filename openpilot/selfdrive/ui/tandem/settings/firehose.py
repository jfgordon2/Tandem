"""Device › Firehose (design/firehose.html, firehose-inactive.html): whether comma can pull training data now, what
Firehose is, how to get the most from it, and StarPilot's questions in Essentials' words.

StarPilot decides what's true: Firehose is active while the device is connected to a network without a data limit, the
rule its own Firehose screen uses (selfdrive/ui/mici/layouts/settings/firehose.py). Its count of segments in the training
set stays out, as StarPilot leaves it out until it's reliable.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.i18n import N_
from openpilot.selfdrive.ui.tandem.layout import inset
from openpilot.selfdrive.ui.tandem.rows import ListPanel, Padded, SectionHeader, Text
from openpilot.starpilot.ui.raylib import rl

QUESTIONS = [
  # StarPilot has no Firehose switch: comma's servers ask athenad for drives, which it sends on any unmetered network, or on
  # metered ones with StarPilot's AlwaysAllowUploads (Uploads on Cellular); Save Data marks a network metered. Storage & Data
  # › Uploads governs only openpilot's automatic uploader (starpilot/tandem/uploads.py), not these.
  (N_("Can I turn it off?"), N_("Not with a switch: comma asks for drives over Wi-Fi on its own, separately from Storage & " +
                                "Data › Uploads. Save Data pauses it on a network, and cellular sends nothing unless Uploads on " +
                                "Cellular is on.")),
  (N_("Does it matter how or where I drive?"), N_("No, just drive as you normally would.")),
  (N_("Are all of my drives uploaded?"), N_("No, comma pulls a selection of them.")),
  (N_("What's a good USB-C charger?"), N_("Any fast phone or laptop charger is fine.")),
  (N_("Does it matter which software I run?"), N_("Yes. Only openpilot and some forks can be used for training.")),
]
ACTIVE_LINE = N_("On Wi-Fi without a data limit, so comma can pull your drives")
INACTIVE_LINE = N_("Connect to Wi-Fi or another network without a data limit")
ACTIVE_SURFACE = T._hex("10261A")
INACTIVE_SURFACE = T._hex("2A1A1C")
INACTIVE_INK = T._hex("E5646F")


def active(network_type: int, metered: bool) -> bool:
  """StarPilot's rule: connected (any network type but none) and not metered.

  Args:
    network_type: deviceState.networkType as a number; 0 is no connection.
    metered: deviceState.networkMetered.
  """
  return network_type != 0 and not metered


def state_active(state: Any) -> bool:
  """Whether a deviceState message says Firehose is active.

  Args:
    state: openpilot's deviceState. Its networkType is a capnp enum, which int() can't take: its number is .raw.
  """
  network = state.networkType
  return active(int(getattr(network, "raw", network)), bool(state.networkMetered))


def device_active() -> bool:
  """Whether Firehose is active now, from openpilot's deviceState; inactive while it's unknown."""
  from openpilot.selfdrive.ui.ui_state import ui_state
  sm = ui_state.sm
  if not sm.valid.get("deviceState", False):
    return False
  return state_active(sm["deviceState"])


class FirehoseStatus(Component):
  """The status card: a dot, Active or Inactive, and what that means for the driver."""
  grow_touch_target = False

  def __init__(self, is_active: Callable[[], bool]):
    super().__init__()
    self._active = is_active

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(72)

  def _render(self, rect: rl.Rectangle) -> None:
    on = self._active()
    ink = T.SUCCESS_BRIGHT if on else INACTIVE_INK
    draw.fill(rect, ACTIVE_SURFACE if on else INACTIVE_SURFACE, T.px(16))
    body = inset(rect, x=T.px(16), y=T.px(14))
    dot = T.px(12)
    draw.fill(rl.Rectangle(body.x, body.y + (body.height - dot) / 2, dot, dot), ink, dot / 2)
    lines = inset(body, left=dot + T.px(14))
    title_h = draw.line_height(T.SIZE_BODY)
    draw.text(rl.Rectangle(lines.x, lines.y, lines.width, title_h), N_("Active") if on else N_("Inactive"), T.SIZE_BODY, ink,
              T.FONT_BOLD)
    draw.text(rl.Rectangle(lines.x, lines.y + title_h + T.px(2), lines.width, draw.line_height(T.SIZE_LABEL)),
              ACTIVE_LINE if on else INACTIVE_LINE, T.SIZE_LABEL, T.TEXT_SECONDARY)


class Answer(Component):
  """One question and its answer, with a divider under it unless it's the last."""
  grow_touch_target = False

  def __init__(self, question: str, answer: str, last: bool = False):
    super().__init__()
    self._question, self._answer, self._last = question, answer, last

  def _body_width(self, width: float) -> float:
    return width - T.PANEL_HEADER_INSET * 2

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    width = self._body_width(max_width)
    return max_width, (T.px(7) * 2 + draw.paragraph_height(self._question, T.font_px(16), T.FONT_SEMIBOLD, width) + T.px(3)
                       + draw.paragraph_height(self._answer, T.SIZE_LABEL, T.FONT, width))

  def _render(self, rect: rl.Rectangle) -> None:
    body = inset(rect, x=T.PANEL_HEADER_INSET, y=T.px(7))
    question_h = draw.paragraph_height(self._question, T.font_px(16), T.FONT_SEMIBOLD, body.width)
    draw.paragraph(rl.Rectangle(body.x, body.y, body.width, question_h), self._question, T.font_px(16), T.TEXT, T.FONT_SEMIBOLD)
    draw.paragraph(rl.Rectangle(body.x, body.y + question_h + T.px(3), body.width, body.height - question_h - T.px(3)),
                   self._answer, T.SIZE_LABEL, T.TEXT_TERTIARY)
    if not self._last:
      draw.fill(rl.Rectangle(body.x, rect.y + rect.height - 1, body.width, 1), T.CONTROL)


def firehose_panel(is_active: Callable[[], bool] = device_active) -> ListPanel:
  """The Firehose page.

  Args:
    is_active: Whether Firehose is active now; StarPilot's rule on openpilot's deviceState by default.
  """
  intro = N_("openpilot learns to drive by watching people drive. Firehose uploads more of your drives so comma can train " +
             "bigger, better driving models.")
  items = [
    Padded(FirehoseStatus(is_active), y=T.px(14)),
    Text(intro, size=T.font_px(16), color=T.TEXT_SECONDARY, padding=(T.PANEL_HEADER_INSET, T.px(2))),
    SectionHeader(N_("GET THE MOST FROM IT")),
    Text(N_("• Once a week, bring the device inside on a fast USB-C charger and Wi-Fi."), size=T.SIZE_LABEL,
         color=T.TEXT_SECONDARY, padding=(T.PANEL_HEADER_INSET, T.px(3))),
    Text(N_("• It also works while driving on a hotspot or an unlimited SIM."), size=T.SIZE_LABEL, color=T.TEXT_SECONDARY,
         padding=(T.PANEL_HEADER_INSET, T.px(3))),
    SectionHeader(N_("QUESTIONS")),
    *(Answer(question, answer, last=i == len(QUESTIONS) - 1) for i, (question, answer) in enumerate(QUESTIONS)),
  ]
  return ListPanel(items, title=N_("Firehose"), subtitle=N_("Training data for openpilot's driving models"), dividers=False)

