"""The release Device › Storage & Data panel."""
from __future__ import annotations

from collections.abc import Callable

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, Segmented, Switch
from openpilot.selfdrive.ui.tandem.i18n import N_, t_, tn_
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SectionHeader, SettingRow
from openpilot.selfdrive.ui.tandem.settings.storage_owner import StorageOwner
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, confirm
from openpilot.starpilot.ui.raylib import rl


class StorageBar(Component):
  """Used space split by kind, with a legend. On Storage & Data it heads the panel; in Offline Maps' Storage card it
  takes a heading, with the used space on the right."""
  grow_touch_target = False
  KINDS = [(N_("Drives"), T.ACCENT), (N_("Maps"), T.SUCCESS_BRIGHT), (N_("Models"), T.WARNING)]

  def __init__(self, sizes: Callable[[], dict[str, float]], heading: str | None = None, padding: tuple[float, float] | None = None):
    super().__init__()
    """Use the same category order and sizes as the release bar."""
    self._sizes = sizes
    self._heading = heading
    self._padding = padding if padding is not None else (T.PANEL_HEADER_INSET, T.px(12))

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    """Fit the drive, map and model legend below the bar."""
    title = draw.line_height(T.font_px(18) if self._heading else T.SIZE_ROW_TITLE)
    lines = len(self._legend(self._sizes(), max_width - self._padding[0] * 2))
    return max_width, self._padding[1] * 2 + title + T.px(14) + T.px(20) + self._legend_height(lines)

  @staticmethod
  def _legend_height(lines: int) -> float:
    """Reserve text height and spacing for each legend line."""
    return lines * draw.line_height(T.SIZE_SUBTITLE) + (lines - 1) * T.px(4)

  def _legend(self, sizes: dict[str, float], width: float) -> list[list[tuple[str, rl.Color, float]]]:
    """Legend entries (label, color, width) in lines, wrapping where a narrow card can't fit them on one."""
    lines: list[list[tuple[str, rl.Color, float]]] = [[]]
    x = 0.0
    for kind, color in self.KINDS:
      label = f"{kind} {_gb(sizes.get(kind, 0.0))}"
      w = T.px(18) + draw.text_width(label, T.SIZE_SUBTITLE)
      if lines[-1] and x + w > width:
        lines.append([])
        x = 0.0
      lines[-1].append((label, color, w))
      x += w + T.px(24)
    return lines

  def _render(self, rect: rl.Rectangle) -> None:
    """Draw release's bar, accounting for any of the three empty categories."""
    sizes = self._sizes()
    total = sizes.get("Total") or 1.0
    used = total - sizes.get("Free", 0.0)
    body = inset(rect, x=self._padding[0], y=self._padding[1])
    title_size = T.font_px(18) if self._heading else T.SIZE_ROW_TITLE
    title, bar, legend = column(body, [draw.line_height(title_size), T.px(14), FILL], T.px(10))
    if self._heading:
      draw.text(title, self._heading, title_size, T.TEXT, T.FONT_BOLD)
      draw.text(title, t_("{} of {}", _gb(used), _gb(total)), T.font_px(15), T.TEXT_TERTIARY, T.FONT, Align.END)
    else:
      draw.text(title, t_("{} of {} used", _gb(used), _gb(total)), title_size, T.TEXT, T.FONT_SEMIBOLD)
    draw.fill(bar, T.TRACK, T.px(7))
    # Flat segments, as in the mock's clipped track: only the bar's own ends are round.
    x, radius = bar.x, T.px(7)
    for kind, color in self.KINDS:
      w = min(bar.width * sizes.get(kind, 0.0) / total, bar.x + bar.width - x)
      if w <= 0:
        continue
      w = max(w, T.px(4))
      segment = rl.Rectangle(x, bar.y, w, bar.height)
      at_start, at_end = x <= bar.x + 0.5, x + w >= bar.x + bar.width - 0.5
      if at_start or at_end:
        draw.fill(segment, color, radius)   # round, then square off the side that joins another color
        if not at_start:
          draw.fill(rl.Rectangle(x, bar.y, min(radius, w), bar.height), color)
        if not at_end:
          draw.fill(rl.Rectangle(x + max(0.0, w - radius), bar.y, min(radius, w), bar.height), color)
      else:
        draw.fill(segment, color)
      x += w
    lines = self._legend(sizes, legend.width)
    line_h = draw.line_height(T.SIZE_SUBTITLE)
    y = legend.y + (legend.height - self._legend_height(len(lines))) / 2
    for entries in lines:
      lx = legend.x
      for label, color, w in entries:
        draw.fill(rl.Rectangle(lx, y + line_h / 2 - T.px(5), T.px(10), T.px(10)), color, T.px(5))
        draw.text(rl.Rectangle(lx + T.px(18), y, w, line_h), label, T.SIZE_SUBTITLE, T.TEXT_TERTIARY)
        lx += w + T.px(24)
      y += line_h + T.px(4)


def _gb(size: float) -> str:
  """Format stored bytes in the displayed decimal units."""
  return t_("{} GB", f"{size / 1e9:.1f}") if size >= 1e8 else t_("{} MB", f"{size / 1e6:.0f}")


class StoragePanel(ListPanel):
  """Storage usage and release controls backed by verified native operations."""

  def __init__(self, owner: StorageOwner, window: SettingsWindow) -> None:
    self._owner, self._window = owner, window

    def delete_drives() -> None:
      """Ask for confirmation before deleting the local recordings."""
      confirm(window, N_("Delete all drives?"), N_("Every recorded drive and its video is removed. This can't be undone."),
              N_("Delete"), owner.delete_drives, icon="trash")

    def models_subtitle() -> str:
      """Show the model count from the native owner."""
      count = len(owner.sample.unused)
      return tn_("{} downloaded model not in use", "{} downloaded models not in use", count) if count else N_("Only the models you use are downloaded")

    def delete_models() -> None:
      """Capture the exact set before opening the release confirmation."""
      selected = owner.sample.unused
      confirm(window, N_("Remove unused models?"),
              tn_("{} model you aren't using is removed. You can download it again from the model catalog.",
                  "{} models you aren't using are removed. You can download them again from the model catalog.", len(selected)),
              N_("Remove"), lambda: owner.delete_models(selected))

    def record(key: str, title: str, subtitle: str) -> SettingRow:
      """Build either recording switch using the native toggle gates."""
      item = SettingRow(title, subtitle, Switch(lambda: owner.record(key), lambda value: owner.set_record(key, value)))
      item.set_enabled(lambda: owner.record_allowed(key))
      return item

    drives = Button(N_("Delete all"), delete_drives, ButtonStyle.DANGER_SOFT)
    drives.set_enabled(lambda: owner.allowed() and not owner.busy and owner.sample.usage.get("Drives", 0) > 0)
    models = Button(N_("Remove"), delete_models, ButtonStyle.DANGER_SOFT)
    models.set_enabled(lambda: owner.allowed() and not owner.busy and bool(owner.sample.unused) and not owner.sample.model_busy)
    def delete_maps() -> None:
      """Bind the confirmation to the currently displayed managed selection."""
      generation = owner.sample.map_generation
      if generation is not None:
        confirm(window, N_("Delete offline maps?"), N_("Remove all downloaded maps from this device. Your regions stay chosen."),
                N_("Delete"), lambda: owner.delete_maps(generation))

    maps = Button(N_("Delete"), delete_maps, ButtonStyle.DANGER_SOFT)
    maps.set_enabled(lambda: owner.allowed() and not owner.busy and owner.sample.map_generation is not None)
    uploads = Segmented([N_("Off"), N_("Parked"), N_("Always")], lambda: owner.uploads, owner.set_uploads)
    uploads.set_enabled(owner.uploads_allowed)
    super().__init__([
      StorageBar(lambda: owner.sample.usage),
      SettingRow(N_("Recorded Drives"), N_("Oldest drives are removed when space runs low"), drives),
      SettingRow(N_("Offline Maps"), N_("Speed limits and curves work without a connection"), maps),
      SettingRow(N_("Unused Models"), models_subtitle, models),
      SectionHeader(N_("RECORDING & UPLOADS")),
      record("RecordFront", N_("Record Driver Camera"), N_("Saved and uploaded with your drives. Restarts openpilot if the car is on.")),
      record("RecordAudio", N_("Record Microphone"), N_("Cabin audio in your drive recordings. Restarts openpilot if the car is on.")),
      SettingRow(N_("Uploads"), N_("Drive logs and video for debugging"), uploads),
    ], title=N_("Storage & Data"), header_divider=False, end_divider=True,
       footnote=N_("High-quality recording, logging and error logs are in Tuner Mode."))

  def show_event(self) -> None:
    """Start a fresh scan on opening the release panel."""
    super().show_event()
    self._poll(refresh=True)

  def _poll(self, *, refresh: bool = False) -> None:
    """Surface errors through the existing notice dialog."""
    error = self._owner.poll(refresh=refresh)
    if error is not None:
      message = t_("Storage operation could not finish. {}", error) if error else N_("Some files could not be removed.")
      self._window.notice(N_("Storage & Data"), message)

  def _update_state(self) -> None:
    """Keep the usage and available actions current while visible."""
    self._poll()
    super()._update_state()
