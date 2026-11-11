"""Bottom sheets, confirm dialogs and toasts."""
from __future__ import annotations

from collections.abc import Callable

import pyray as rl

from openpilot.system.ui.lib.application import MousePos
from openpilot.system.ui.widgets import DialogResult, Widget
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Bindable, Component, resolve, size_of
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, Glyph, Tone
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, place, row
from openpilot.selfdrive.ui.tandem.i18n import N_
from openpilot.system.ui.lib.application import MouseEvent


def _ease_out(t: float) -> float:
  t = min(1.0, max(0.0, t))
  return 1 - (1 - t) ** 3


class Sheet(Component):
  """Slides up from the bottom over a scrim: handle, title and subtitle, actions on the right, then the body.

  A sheet with on_dismiss also closes by dragging its handle or header down: past DRAG_CLOSE of its height, or with a
  downward flick, it closes; short of that it springs back."""
  grow_touch_target = False
  DRAG_CLOSE = 0.25       # share of the sheet's height
  FLICK = T.px(600)       # px/s downward, over the last FLICK_S, that closes even a short drag
  FLICK_S = 0.1
  SNAP_S = 0.18

  def __init__(self, title: Bindable[str], body: Widget, subtitle: Bindable[str] | None = None,
               actions: list[Button] | None = None, height: float | None = None, on_dismiss: Callable[[], None] | None = None,
               header: Widget | None = None):
    """Makes a sheet.

    Args:
      title: The sheet's title, or a getter for it.
      body: What the sheet shows.
      subtitle: A line under the title.
      actions: Buttons on the right of the header.
      height: A fixed height; None fits the body.
      on_dismiss: Runs when the scrim above the sheet is tapped.
      header: A widget left of the actions (e.g. tabs).
    """
    super().__init__()
    self._header = self._child(header) if header is not None else None
    self._on_dismiss = on_dismiss
    self._sheet_rect = rl.Rectangle(0, 0, 0, 0)
    self._title = title
    self._subtitle = subtitle
    self._body = self._child(body)
    self._actions = [self._child(a) for a in actions or []]
    # The mocks' header buttons: one main action (Done) is 60 tall; a pair (Cancel, Save) is 56.
    for a in self._actions:
      if len(self._actions) == 1:
        a.restyle(T.PRIMARY_BUTTON_HEIGHT, T.font_px(18), T.px(30), T.px(16))
      else:
        a.restyle(T.px(56), T.font_px(17), T.px(28) if a is self._actions[-1] else T.px(22), T.px(16))
    self._height = height
    self._shown_at: float | None = None
    self._grab_rects: list[rl.Rectangle] = []
    self._grab: list[tuple[float, float]] | None = None   # (y, t) drag samples, while dragging
    self._grab_y = 0.0
    self._drag = 0.0
    self._dragged = False
    self._snap: tuple[float, float] | None = None   # (offset, start time) while springing back

  def show_event(self) -> None:
    super().show_event()
    self._shown_at = rl.get_time()

  def _sheet_height(self, rect: rl.Rectangle) -> float:
    if self._height is not None:
      return self._height
    width = rect.width - T.px(52)
    return min(rect.height - T.px(90), T.px(110) + size_of(self._body, width)[1] + T.px(24))

  def _render(self, rect: rl.Rectangle) -> None:
    t = 1.0 if self._shown_at is None else _ease_out((rl.get_time() - self._shown_at) * 1000 / T.SHEET_MS)
    height = self._sheet_height(rect)
    offset = self._offset()
    draw.fill(rect, draw.alpha(T.SCRIM, 0.85 * t * (1 - min(1.0, offset / max(height, 1)))))
    sheet = rl.Rectangle(rect.x, rect.y + rect.height - height * t + offset, rect.width, height)
    self._sheet_rect = sheet
    draw.fill(sheet, T.SURFACE_2, T.RADIUS_SHEET)
    draw.fill(rl.Rectangle(sheet.x, sheet.y + T.RADIUS_SHEET, sheet.width, sheet.height - T.RADIUS_SHEET), T.SURFACE_2)
    draw.fill(place(rl.Rectangle(sheet.x, sheet.y + T.px(14), sheet.width, T.px(6)), T.px(64), T.px(6)), T.KEY_MOD, T.px(3))

    body = inset(sheet, left=T.px(26), right=T.px(26), top=T.px(34), bottom=T.px(22))
    header, content = column(body, [T.px(64), FILL], T.px(14))
    x_end = header.x + header.width
    for action in reversed(self._actions):
      w, h = size_of(action, header.width / 3)
      x_end -= w
      action.render(rl.Rectangle(x_end, header.y + (header.height - h) / 2, w, h))
      x_end -= T.px(12)
    if self._header is not None:
      w, h = size_of(self._header, header.width / 2)
      x_end -= w
      self._header.render(rl.Rectangle(x_end, header.y + (header.height - h) / 2, w, h))
      x_end -= T.px(16)
    text_rect = rl.Rectangle(header.x, header.y, x_end - header.x, header.height)
    self._grab_rects = [rl.Rectangle(sheet.x, sheet.y, sheet.width, body.y - sheet.y), text_rect]   # the handle strip and the title
    if self._subtitle is not None:
      title_rect, sub_rect = column(place(text_rect, text_rect.width, draw.line_height(T.SIZE_TITLE) + T.px(4) + draw.line_height(T.SIZE_LABEL)),
                                    [draw.line_height(T.SIZE_TITLE), draw.line_height(T.SIZE_LABEL)], T.px(4))
      draw.text(sub_rect, resolve(self._subtitle), T.SIZE_LABEL, T.TEXT_TERTIARY)
    else:
      title_rect = text_rect
    draw.text(title_rect, resolve(self._title), T.SIZE_TITLE, T.TEXT, T.FONT_EXTRABOLD)
    self._body.render(content)


  def _offset(self) -> float:
    if self._snap is not None:
      start, at = self._snap
      progress = (rl.get_time() - at) / self.SNAP_S
      if progress >= 1:
        self._snap = None
        return 0.0
      return start * (1 - _ease_out(progress))
    return self._drag

  def _speed(self, now: float) -> float:
    """Downward speed over the last FLICK_S, so a finger that pauses a frame before lifting still counts as a flick."""
    samples = self._grab or []
    if len(samples) < 2:
      return 0.0
    last = samples[-1]
    start = next(s for s in samples if now - s[1] <= self.FLICK_S or s is last)
    if start is last:
      start = samples[-2]
    return (last[0] - start[0]) / max(last[1] - start[1], 1e-3)

  def _handle_mouse_event(self, mouse_event: MouseEvent) -> None:
    if self._on_dismiss is None:
      return
    pos = mouse_event.pos
    if mouse_event.left_pressed:
      if any(rl.check_collision_point_rec(pos, r) for r in self._grab_rects):
        self._grab, self._grab_y = [(pos.y, mouse_event.t)], pos.y
        self._drag, self._dragged, self._snap = 0.0, False, None
    elif self._grab is not None and mouse_event.left_released:
      closes = self._drag > self._sheet_rect.height * self.DRAG_CLOSE or (self._speed(mouse_event.t) > self.FLICK and self._drag > T.px(20))
      self._grab = None
      if closes:
        self._on_dismiss()
      elif self._drag > 0:
        self._snap = (self._drag, rl.get_time())
      self._drag = 0.0
    elif self._grab is not None and mouse_event.left_down:
      self._grab.append((pos.y, mouse_event.t))
      self._drag = max(0.0, pos.y - self._grab_y)
      self._dragged = self._dragged or self._drag > T.px(8)

  def _handle_mouse_release(self, mouse_pos: MousePos) -> None:
    super()._handle_mouse_release(mouse_pos)
    if self._dragged:        # the end of a drag, not a tap above the sheet
      self._dragged = False
      return
    if self._on_dismiss is not None and mouse_pos.y < self._sheet_rect.y:
      self._on_dismiss()


class Dialog(Component):
  """A centered confirm card. tone=DANGER gives the red destructive button; ACCENT a blue one. cancel_label=None leaves
  only the confirm button (a notice, e.g. the Bluetooth sound test). The message may change while it shows."""
  grow_touch_target = False

  def __init__(self, title: str, message: Bindable[str], confirm_label: str, on_result: Callable[[DialogResult], None] | None = None,
               cancel_label: str | None = N_("Cancel"), tone: Tone = Tone.ACCENT, glyph: Glyph | None = None):
    super().__init__()
    self._title = title
    self._message = message
    self._tone = tone
    self._glyph = glyph
    self._on_result = on_result
    confirm_style = ButtonStyle.DANGER if tone == Tone.DANGER else ButtonStyle.PRIMARY
    self._cancel = self._child(Button(cancel_label or "", lambda: self._finish(DialogResult.CANCEL), height=T.px(64),
                                      font_size=T.font_px(19), radius=T.px(16), weight=T.FONT_BOLD))
    self._cancel.set_visible(cancel_label is not None)
    self._confirm = self._child(Button(confirm_label, lambda: self._finish(DialogResult.CONFIRM), confirm_style, height=T.px(64),
                                       font_size=T.font_px(19), radius=T.px(16), weight=T.FONT_EXTRABOLD))
    self.result: DialogResult = DialogResult.NO_ACTION

  def _finish(self, result: DialogResult) -> None:
    self.result = result
    if self._on_result:
      self._on_result(result)

  def _card_height(self, width: float) -> float:
    inner = width - T.px(56)
    well = T.px(60) + T.px(12) if self._glyph else 0
    return T.px(28) * 2 + well + T.px(6) + draw.line_height(T.font_px(26)) + T.px(8) + \
      draw.paragraph_height(resolve(self._message), T.font_px(17), T.FONT, inner, 1.4) + T.px(24) + T.px(64)

  def _render(self, rect: rl.Rectangle) -> None:
    draw.fill(rect, draw.alpha(T.SCRIM, 0.85))
    width = min(rect.width - T.px(80), T.px(520))
    card = place(rect, width, self._card_height(width))
    draw.fill(card, T.SURFACE_3, T.px(26))
    draw.stroke(card, T.TRACK, T.px(26))
    body = inset(card, T.px(28))
    danger = self._tone == Tone.DANGER
    if self._glyph:
      well_rect, body = column(body, [T.px(60), FILL], T.px(12))
      well = place(well_rect, T.px(60), T.px(60), Align.START)
      draw.fill(well, T.DANGER_SURFACE if danger else T.ACCENT_SURFACE, T.px(18))
      self._glyph(well, T.DANGER_TEXT if danger else T.ACCENT_TEXT, T.px(28))
    title_rect, text_rect, _, buttons = column(body, [draw.line_height(T.font_px(26)), FILL, T.px(16), T.px(64)], T.px(12))
    draw.text(title_rect, self._title, T.font_px(26), T.TEXT, T.FONT_EXTRABOLD)
    draw.paragraph(text_rect, resolve(self._message), T.font_px(17), T.TEXT_SECONDARY, spacing=1.4)
    if not self._cancel.is_visible:
      self._confirm.render(buttons)
      return
    cancel_rect, confirm_rect = row(buttons, [FILL, FILL], T.px(12))
    self._cancel.render(cancel_rect)
    self._confirm.render(confirm_rect)


class Toast(Component):
  """A short confirmation such as "Backup created". Call show(); it fades after TOAST_MS. Not for use while driving."""
  grow_touch_target = False

  def __init__(self) -> None:
    super().__init__()
    self._message = ""
    self._tone = Tone.SUCCESS
    self._shown_at: float | None = None

  def show(self, message: str, tone: Tone = Tone.SUCCESS) -> None:
    self._message, self._tone, self._shown_at = message, tone, rl.get_time()

  @property
  def active(self) -> bool:
    return self._shown_at is not None and (rl.get_time() - self._shown_at) * 1000 < T.TOAST_MS

  def _render(self, rect: rl.Rectangle) -> None:
    if not self.active or self._shown_at is None:
      return
    elapsed = (rl.get_time() - self._shown_at) * 1000
    fade = min(1.0, elapsed / 150, (T.TOAST_MS - elapsed) / 300)
    width = draw.text_width(self._message, T.SIZE_BODY, T.FONT_SEMIBOLD) + T.px(80)
    box = place(rect, width, T.px(64), Align.CENTER, Align.END)
    box.y -= T.px(24)
    draw.fill(box, draw.alpha(T.CONTROL, fade), T.px(18))
    ink = {Tone.SUCCESS: T.SUCCESS_TEXT, Tone.WARNING: T.WARNING, Tone.DANGER: T.DANGER_TEXT}.get(self._tone, T.ACCENT_TEXT)
    mark = rl.Rectangle(box.x + T.px(18), box.y, T.px(24), box.height)
    draw.check(mark, draw.alpha(ink, fade), T.px(24))
    draw.text(inset(box, left=T.px(52), right=T.px(18)), self._message, T.SIZE_BODY, draw.alpha(T.TEXT, fade), T.FONT_SEMIBOLD)
