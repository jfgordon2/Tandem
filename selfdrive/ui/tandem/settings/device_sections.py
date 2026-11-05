"""Device tab sections besides This Device: General, Backups, Storage & Data, and Report a Problem (RAM is in ram.py).

File work (settings snapshots, storage sizes, deleting drives) and sending a report go through DeviceData;
UpstreamData does them the way StarPilot's System screen does, with the same paths.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.blocks import SPACER, Columns, Field, Label, Stack, Surface
from openpilot.selfdrive.ui.tandem.fonts import face_for
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, Segmented, Switch, Tone, ValueButton
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, row
from openpilot.selfdrive.ui.tandem.overlays import Dialog, Sheet
from openpilot.selfdrive.ui.tandem.rows import ListPanel, OptionList, Padded, SectionHeader, SettingRow, Text
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.system.ui.widgets import DialogResult, Widget
from openpilot.selfdrive.ui.tandem.prefs import BACKUP_DIR, TEMPERATURE, celsius, restore_prefs, save_prefs
from openpilot.selfdrive.ui.tandem.i18n import N_, t_, tn_


@dataclass(frozen=True)
class Backup:
  name: str
  when: str


class DeviceData(Protocol):
  def languages(self) -> list[tuple[str, str]]: ...      # (name, code)
  def language(self) -> str: ...                        # current code
  def set_language(self, code: str) -> None: ...
  def backups(self) -> list[Backup]: ...
  def create_backup(self) -> None: ...
  def restore_backup(self, name: str) -> None: ...
  def delete_backup(self, name: str) -> None: ...
  def storage(self) -> dict[str, float]: ...             # bytes used by "Drives", "Maps", "Models", plus "Total" and "Free"
  def delete_drives(self) -> None: ...
  def delete_maps(self) -> None: ...
  def maps_blocked(self) -> str: ...                     # why offline maps can't be deleted right now, or ""
  def send_report(self, issue: str, discord: str) -> None: ...


BRIGHTNESS = [(N_("Dimmer"), 40, 30), (N_("Auto"), 101, 101), (N_("Brighter"), 100, 100)]   # name, parked, driving. 101 is Auto.
UPLOADS = [N_("Off"), N_("Parked"), N_("Always")]
REPORT_CATEGORIES = [N_("Acceleration felt harsh or jerky"), N_("Braking was too sudden"), N_("It disengaged when I didn't expect it"),
                     N_("It felt slow to respond"), N_("An alert was unclear"), N_("My steering wheel buttons aren't working"), N_("Something else")]


class General:
  def __init__(self, store: SettingsStore, data: DeviceData, live):
    self._store = store
    self.data = data
    self._live = live

  @property
  def metric(self) -> int:
    return 1 if self._store.get_bool("IsMetric") else 0

  def set_metric(self, index: int) -> None:
    self._store.write({"IsMetric": index == 1})

  @property
  def temperature(self) -> int:
    """0 °F, 1 °C: Tandem's own choice (prefs.TEMPERATURE), following Units until it's picked."""
    return 1 if celsius(bool(self.metric)) else 0

  def set_temperature(self, index: int) -> None:
    TEMPERATURE.set("C" if index == 1 else "F")

  def language_name(self) -> str:
    code = self.data.language()
    return next((name for name, c in self.data.languages() if same_language(c, code)), code)

  @property
  def brightness(self) -> int:
    parked = self._store.get_int("ScreenBrightness")
    return next((i for i, (_, p, _) in enumerate(BRIGHTNESS) if p == parked), 1)

  def set_brightness(self, index: int) -> None:
    _, parked, driving = BRIGHTNESS[index]
    self._store.write({"ScreenManagement": True, "ScreenBrightness": parked, "ScreenBrightnessOnroad": driving})

  @property
  def standby(self) -> bool:
    return self._store.get_bool("StandbyMode")

  def set_standby(self, on: bool) -> None:
    self._store.write({"ScreenManagement": True, "StandbyMode": on})

  @property
  def uploads(self) -> int:
    if self._store.get_bool("NoUploads"):
      return 0
    return 1 if self._store.get_bool("DisableOnroadUploads") else 2

  def set_uploads(self, index: int) -> None:
    self._store.write({"NoUploads": index == 0, "DisableOnroadUploads": index == 1})

  # Storage & Data

  @property
  def record_driver(self) -> bool:
    return self._store.get_bool("RecordFront")

  def set_record_driver(self, on: bool) -> None:
    self._store.write({"RecordFront": on})

  @property
  def record_audio(self) -> bool:
    return self._store.get_bool("RecordAudio")

  def set_record_audio(self, on: bool) -> None:
    self._store.write({"RecordAudio": on})

  def recording_locked(self) -> bool:
    """Recording changes restart openpilot, so they wait until it's disengaged; RecordFrontLock pins the driver camera."""
    return self._live.engaged() or self._store.get_bool("RecordFrontLock")


def confirm(window, title: str, message: str, label: str, action: Callable[[], None], danger: bool = True, icon: str = "trash") -> None:
  """A confirm dialog with a mock icon in its well: trash for deleting, restart for replacing settings."""
  def done(result: DialogResult) -> None:
    window.dismiss()
    if result == DialogResult.CONFIRM:
      action()
  window.present(Dialog(title, message, label, done, tone=Tone.DANGER if danger else Tone.ACCENT,
                        glyph=lambda r, c, s: draw.icon(r, icon, c, s)))


def same_language(a: str, b: str) -> bool:
  """StarPilot's codes are "main_en" in its list and when just chosen, but plain "en" once loaded at startup."""
  return a.removeprefix("main_") == b.removeprefix("main_")


# StarPilot's style languages: English rewritten for fun, not languages a driver reads. Hidden from Tandem's list
# (StarPilot's own list, with TANDEM_SETTINGS=0, still has them); a driver already using one keeps it.
NOVELTY_LANGUAGES = {"caveman", "duck", "frog", "pirate", "shakespearean"}


def picker_languages(languages: list[tuple[str, str]], current: str) -> list[tuple[str, str]]:
  return [(name, code) for name, code in languages
          if code.removeprefix("main_") not in NOVELTY_LANGUAGES or same_language(code, current)]


def open_language(data: DeviceData, window) -> None:
  """The language sheet, opened from General."""
  languages = picker_languages(data.languages(), data.language())

  def pick(index: int):
    data.set_language(languages[index][1])
    window.dismiss()
  window.present(Sheet(N_("Language"), OptionList([name for name, _ in languages],
                                              lambda: next((i for i, (_, c) in enumerate(languages) if same_language(c, data.language())), 0),
                                              pick, weight=lambda name: face_for(name, T.FONT_SEMIBOLD)),   # unifont only where Figtree lacks
                       subtitle=N_("For menus and alerts"), on_dismiss=window.dismiss))


def general_panel(model: General, window) -> ListPanel:
  def language_sheet():
    open_language(model.data, window)

  return ListPanel([
    SettingRow(N_("Units"), N_("Speed and distance everywhere"), Segmented(["mph", "km/h"], lambda: model.metric, model.set_metric)),
    SettingRow(N_("Temperature"), N_("For the weather forecast"), Segmented(["°F", "°C"], lambda: model.temperature, model.set_temperature)),
    SettingRow(N_("Language"), None, ValueButton(model.language_name, language_sheet)),
    SettingRow(N_("Screen Brightness"), N_("Auto follows ambient light, day and night"),
               Segmented([name for name, _, _ in BRIGHTNESS], lambda: model.brightness, model.set_brightness)),
    SettingRow(N_("Standby"), N_("Screen sleeps while driving, wakes for alerts"), Switch(lambda: model.standby, model.set_standby)),
  ], title=N_("General"))


def backups_panel(model: General, window) -> Component:
  from openpilot.selfdrive.ui.tandem.settings.model import Rebuilding

  def row_for(backup: Backup) -> SettingRow:
    restore = Button(N_("Restore"), lambda: confirm(window, N_("Restore this backup?"), t_("Your current settings are replaced with {}.", backup.name),
                                                N_("Restore"), lambda: model.data.restore_backup(backup.name), danger=False,
                                                icon="restart"))
    delete = Button(N_("Delete"), lambda: confirm(window, N_("Delete this backup?"), t_("{} can't be recovered.", backup.name), N_("Delete"),
                                              lambda: model.data.delete_backup(backup.name)), ButtonStyle.DANGER_SOFT)
    return SettingRow(backup.name, backup.when, ButtonPair(delete, restore))

  def build() -> ListPanel:
    backups = model.data.backups()
    return ListPanel([
      SectionHeader(N_("SAVED")),
      *([row_for(b) for b in backups] or [Text(N_("No backups yet."))]),
    ], title=N_("Backups"), subtitle=N_("Snapshots of your settings. Drives aren't included."),
       header_control=Button(N_("Back up now"), model.data.create_backup, ButtonStyle.PRIMARY))

  return Rebuilding(lambda: tuple(b.name for b in model.data.backups()), build)


class ButtonPair(Component):
  grow_touch_target = False

  def __init__(self, first: Button, second: Button):
    super().__init__()
    self._buttons = [self._child(first), self._child(second)]

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    widths = [b.preferred_size(max_width)[0] for b in self._buttons]
    return sum(widths) + T.px(10), T.BUTTON_HEIGHT

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    super().set_parent_rect(parent_rect)
    for b in self._buttons:
      b.set_parent_rect(parent_rect)

  def _render(self, rect: rl.Rectangle):
    widths = [b.preferred_size(rect.width)[0] for b in self._buttons]
    for b, r in zip(self._buttons, row(rect, widths, T.px(10)), strict=True):
      b.render(r)


class StorageBar(Component):
  """Used space split by kind, with a legend. On Storage & Data it heads the panel; in Offline Maps' Storage card it
  takes a heading, with the used space on the right."""
  grow_touch_target = False
  KINDS = [(N_("Drives"), T.ACCENT), (N_("Maps"), T.SUCCESS_BRIGHT), (N_("Models"), T.WARNING)]

  def __init__(self, sizes: Callable[[], dict[str, float]], heading: str | None = None, padding: tuple[float, float] | None = None):
    super().__init__()
    self._sizes = sizes
    self._heading = heading
    self._padding = padding if padding is not None else (T.PANEL_HEADER_INSET, T.px(12))

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    title = draw.line_height(T.font_px(18) if self._heading else T.SIZE_ROW_TITLE)
    lines = len(self._legend(self._sizes(), max_width - self._padding[0] * 2))
    return max_width, self._padding[1] * 2 + title + T.px(14) + T.px(20) + self._legend_height(lines)

  @staticmethod
  def _legend_height(lines: int) -> float:
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

  def _render(self, rect: rl.Rectangle):
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
  return t_("{} GB", f"{size / 1e9:.1f}") if size >= 1e8 else t_("{} MB", f"{size / 1e6:.0f}")


DELETE_DRIVES_MESSAGE = N_("Every recorded drive and its video is removed. This can't be undone.")
BACKUP_NAME = N_("Backup {}")   # a backup folder's name as drawn: "Backup 2026-10-24 0910"
DELETE_MAPS_MESSAGE = N_("Remove offline routes, speed limits and street names from this device. Saved places stay saved. " +
                         "Your regions stay chosen, so a scheduled update downloads them again.")


def delete_maps_row(data: DeviceData, window, height: float | None = None) -> SettingRow:
  """Storage & Data's row for offline maps: Delete, or why it can't be deleted yet."""
  def subtitle() -> str:
    return data.maps_blocked() or N_("Speed limits and curves work without a connection")
  delete = Button(N_("Delete"), lambda: confirm(window, N_("Delete offline maps?"), DELETE_MAPS_MESSAGE, N_("Delete"), data.delete_maps),
                  ButtonStyle.DANGER_SOFT)
  delete.set_enabled(lambda: data.storage().get("Maps", 0.0) > 0 and not data.maps_blocked())
  return SettingRow(N_("Offline Maps"), subtitle, delete, height=height)


def unused_models_row(models, window) -> SettingRow:
  """Storage & Data's row for downloaded models that aren't in use (never the current or recommended one)."""
  def subtitle() -> str:
    count = len(models.unused())
    blocked = models.source.removal_blocked()
    if blocked and count:
      return blocked
    return tn_("{} downloaded model not in use", "{} downloaded models not in use", count) if count else N_("Only the models you use are downloaded")

  def remove() -> None:
    count = len(models.unused())
    confirm(window, N_("Remove unused models?"),
            tn_("{} model you aren't using is removed. You can download it again from the model catalog.",
                "{} models you aren't using are removed. You can download them again from the model catalog.", count), N_("Remove"),
            lambda: (models.remove_unused(), STORAGE.forget()))
  button = Button(N_("Remove"), remove, ButtonStyle.DANGER_SOFT)
  button.set_enabled(lambda: bool(models.unused()) and not models.source.removal_blocked())
  return SettingRow(N_("Unused Models"), subtitle, button)


def storage_panel(model: General, window, models) -> ListPanel:
  driver = SettingRow(N_("Record Driver Camera"), N_("Saved and uploaded with your drives. Restarts openpilot if the car is on."),
                      Switch(lambda: model.record_driver, model.set_record_driver))
  audio = SettingRow(N_("Record Microphone"), N_("Cabin audio in your drive recordings. Restarts openpilot if the car is on."),
                     Switch(lambda: model.record_audio, model.set_record_audio))
  for r in (driver, audio):
    r.set_enabled(lambda: not model.recording_locked())
  return ListPanel([
    StorageBar(model.data.storage),
    SettingRow(N_("Recorded Drives"), N_("Oldest drives are removed when space runs low"),
               Button(N_("Delete all"), lambda: confirm(window, N_("Delete all drives?"), DELETE_DRIVES_MESSAGE, N_("Delete"), model.data.delete_drives),
                      ButtonStyle.DANGER_SOFT)),
    delete_maps_row(model.data, window),
    unused_models_row(models, window),
    SectionHeader(N_("RECORDING & UPLOADS")),
    driver,
    audio,
    SettingRow(N_("Uploads"), N_("Drive logs and video for debugging"), Segmented(UPLOADS, lambda: model.uploads, model.set_uploads)),
  ], title=N_("Storage & Data"), header_divider=False, end_divider=True,   # the usage bar belongs to the header, as in the mock
     footnote=N_("High-quality recording, logging and error logs are in Tuner Mode."))


class Report:
  def __init__(self, data: DeviceData, store: SettingsStore, ram=None):
    self.data = data
    self._store = store
    self._ram = ram   # ram.RamLog: the last drives that ran low go with the report
    self.category = -1
    self.details = ""
    self.discord = store.get_str("DiscordUsername")
    self.sent = False

  def ready(self) -> bool:
    return self.category >= 0

  def send(self) -> None:
    if not self.ready():
      return
    issue = REPORT_CATEGORIES[self.category] + (f": {self.details}" if self.details else "")
    if self._ram is not None and (low := self._ram.snapshots()):
      from openpilot.selfdrive.ui.tandem.ram import report_text
      issue += "\n" + report_text(low)
    self.data.send_report(issue, self.discord)
    if self.discord:
      self._store.write({"DiscordUsername": self.discord})
    self.sent = True


def report_panel(report: Report) -> Widget:
  def edit(title: str, get: Callable[[], str], set_: Callable[[str], None]) -> Callable[[], None]:
    def open_keyboard():
      from openpilot.system.ui.lib.application import gui_app
      from openpilot.selfdrive.ui.tandem.keyboard import EssentialsKeyboard
      keyboard = EssentialsKeyboard(min_text_size=0, action=N_("Save"))
      keyboard.set_title(title, N_("Optional"))
      keyboard.set_text(get())
      keyboard.set_callback(lambda result: set_(keyboard.text.strip()) if result == DialogResult.CONFIRM else None)
      gui_app.push_widget(keyboard)
    return open_keyboard

  def pick(index: int) -> None:
    report.category = index
    report.sent = False

  send = Button(lambda: N_("Sent. Thank you!") if report.sent else N_("Send report"), report.send, ButtonStyle.PRIMARY, height=T.px(56),
                weight=T.FONT_EXTRABOLD)
  send.set_enabled(lambda: report.ready() and not report.sent)
  happened = Stack([
    Padded(Label(N_("What happened?"), T.font_px(22)), x=T.px(10), y=T.px(4)),
    OptionList(REPORT_CATEGORIES, lambda: report.category, pick, row_height=T.px(52), outlined=True, font_size=T.font_px(15)),
  ], gap=T.px(4))
  details = Stack([
    Field(N_("Details (optional)"), lambda: report.details, N_("Where and when it happened"),
          edit(N_("Details"), lambda: report.details, lambda v: setattr(report, "details", v)), height=T.px(72)),
    Field(N_("Discord name (optional)"), lambda: report.discord, N_("So we can follow up"),
          edit(N_("Discord name"), lambda: report.discord, lambda v: setattr(report, "discord", v))),
    SPACER,
    send,
  ], gap=T.px(14))
  return Surface(Columns([Padded(happened, x=T.px(10), y=T.px(12)), Padded(details, x=T.px(18), y=T.px(16))], [1.25, 1], gap=0),
                 T.SURFACE_2, T.RADIUS_PANEL)


class StorageSizes:
  """Device data sizes and disk capacity, measured on a background thread and shared by every page that shows it (Storage &
  Data, Offline Maps, the model catalog). Until a measurement finishes it returns the last one (zeros at first);
  forget() re-measures right away after something is deleted."""
  REFRESH = 30.0

  def __init__(self):
    self._sizes: dict[str, float] = {}
    self._measuring = False
    self._generation = 0   # bumped by forget(), so a measurement that started before a delete is thrown away
    self._measured_at = 0.0

  def sizes(self) -> dict[str, float]:
    """Re-measured every REFRESH seconds while something shows it, so model and map downloads show up too."""
    import time
    if not self._measuring and (not self._sizes or time.monotonic() - self._measured_at > self.REFRESH):
      import threading
      self._measuring = True
      threading.Thread(target=self._measure, args=(self._generation,), daemon=True).start()
    return self._sizes

  def forget(self) -> None:
    self._generation += 1
    self._sizes = {}

  def _measure(self, generation: int) -> None:
    import shutil
    import time
    from pathlib import Path
    from openpilot.system.hardware import PC

    def size(*paths: str) -> float:
      total = 0
      for p in paths:
        path = Path(p)
        if path.exists():
          total += sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
      return float(total)

    try:
      usage = shutil.disk_usage(Path.home() if PC else "/data")
      from openpilot.starpilot.tandem.routing.config import root as routing_root
      sizes = {"Drives": size("/data/media/0/realdata", "/data/media/0/realdata_HD", "/data/media/0/realdata_konik"),
                     "Maps": size("/data/media/0/osm/offline", str(routing_root() / "bundles"), str(routing_root() / "downloads")),
                     "Models": size("/data/models"),
                     "Total": float(usage.total), "Free": float(usage.free)}
      if generation == self._generation:
        self._sizes = sizes
        self._measured_at = time.monotonic()
    finally:
      self._measuring = False


STORAGE = StorageSizes()


class UpstreamData:
  """DeviceData the way StarPilot's System screen does it: same folders, same params, same report message."""

  def __init__(self):
    from pathlib import Path
    self._Path = Path
    self._backups = Path("/data/toggle_backups")
    self._params_dir = Path("/data/params/d")

  def languages(self) -> list[tuple[str, str]]:
    from openpilot.system.ui.lib.multilang import multilang
    return list(multilang.languages.items())

  def language(self) -> str:
    from openpilot.system.ui.lib.multilang import multilang
    return multilang.language

  def set_language(self, code: str) -> None:
    from openpilot.system.ui.lib.multilang import multilang
    multilang.change_language(code)

  def backups(self) -> list[Backup]:
    import datetime
    if not self._backups.exists():
      return []
    entries = sorted((d for d in self._backups.iterdir() if d.is_dir() and "in_progress" not in d.name),
                     key=lambda d: d.stat().st_mtime, reverse=True)
    return [Backup(d.name.replace("_", " "), datetime.datetime.fromtimestamp(d.stat().st_mtime).strftime("%b %-d, %Y %-I:%M %p"))
            for d in entries]

  def _dir(self, name: str):
    return self._backups / name.replace(" ", "_")

  def create_backup(self) -> None:
    import datetime
    import shutil
    target = self._dir(datetime.datetime.now().strftime("Backup %Y-%m-%d %H%M"))   # drawn as N_("Backup {}") (BACKUP_NAME)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(self._params_dir), str(target), dirs_exist_ok=True)
    save_prefs(target)   # Tandem's own settings live beside the params folder (prefs.py)

  def restore_backup(self, name: str) -> None:
    import shutil
    from openpilot.starpilot.common.starpilot_variables import LEGACY_STARPILOT_PARAM_RENAMES, update_starpilot_toggles
    src, params_dir = self._dir(name), self._params_dir
    for old_key, new_key in LEGACY_STARPILOT_PARAM_RENAMES.items():
      if (src / old_key).exists():
        (params_dir / new_key).unlink(missing_ok=True)
    shutil.copytree(str(src), str(params_dir), dirs_exist_ok=True, ignore=shutil.ignore_patterns(BACKUP_DIR))
    restore_prefs(src)   # Tandem's own settings, beside the params folder
    for old_key, new_key in LEGACY_STARPILOT_PARAM_RENAMES.items():
      if (params_dir / old_key).exists():
        (params_dir / old_key).replace(params_dir / new_key)
    update_starpilot_toggles()

  def delete_backup(self, name: str) -> None:
    import shutil
    shutil.rmtree(self._dir(name), ignore_errors=True)

  def storage(self) -> dict[str, float]:
    return STORAGE.sizes()

  def delete_maps(self) -> None:
    from openpilot.selfdrive.ui.tandem.settings.maps import remove_offline_maps
    remove_offline_maps()

  def maps_blocked(self) -> str:
    from openpilot.selfdrive.ui.tandem.settings.maps import removal_blocked
    return removal_blocked()

  def delete_drives(self) -> None:
    import shutil
    import threading

    def task():
      for path in ("/data/media/0/realdata/", "/data/media/0/realdata_HD/", "/data/media/0/realdata_konik/"):
        p = self._Path(path)
        if p.exists():
          for entry in p.iterdir():
            if entry.is_dir():
              shutil.rmtree(entry, ignore_errors=True)
      STORAGE.forget()
    threading.Thread(target=task, daemon=True).start()

  def send_report(self, issue: str, discord: str) -> None:
    from openpilot.common.params import Params
    Params(memory=True).put("IssueReported", {"DiscordUser": discord, "Issue": issue})
