"""Driving Model: the active model, Use recommended, and a catalog to download and switch models.

The catalog, downloads and switching are StarPilot's: UpstreamModels drives its model screen's controller,
which keeps its checks (no downloads while driving, one at a time, eGPU-only models) and its download thread.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.blocks import SPACER, Card, Columns, Inline, Label, Stack, Surface
from openpilot.selfdrive.ui.tandem.controls import Badge, Button, ButtonStyle, Segmented, Switch
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, place, row
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SectionHeader, SettingRow, Text
from openpilot.selfdrive.ui.tandem.settings.device_sections import STORAGE, StorageBar
from openpilot.selfdrive.ui.tandem.settings.pages import TitledPage
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.i18n import N_, t_


@dataclass(frozen=True)
class ModelInfo:
  key: str
  name: str
  installed: bool
  community_pick: bool = False
  needs_egpu: bool = False
  removable: bool = True


class ModelSource(Protocol):
  def refresh(self) -> None: ...
  def tick(self) -> None: ...
  def models(self) -> list[ModelInfo]: ...
  def current_key(self) -> str: ...
  def recommended_key(self) -> str: ...
  def downloading_key(self) -> str | None: ...
  def progress(self) -> str: ...
  def egpu_available(self) -> bool: ...
  def use(self, key: str) -> None: ...
  def download(self, key: str) -> None: ...
  def cancel(self) -> None: ...
  def remove(self, key: str) -> None: ...
  def removal_blocked(self) -> str: ...   # why models can't be removed right now, or ""


class Models:
  def __init__(self, store: SettingsStore, source: ModelSource):
    self._store = store
    self.source = source

  def find(self, key: str) -> ModelInfo | None:
    return next((m for m in self.source.models() if m.key == key), None)

  def current_name(self) -> str:
    model = self.find(self.source.current_key())
    return model.name if model else N_("Default model")

  @property
  def use_recommended(self) -> bool:
    return self._store.get_bool("AutomaticallyDownloadModels") and self.source.current_key() == self.source.recommended_key()

  def set_use_recommended(self, on: bool) -> None:
    self._store.write({"AutomaticallyDownloadModels": on})
    if on:
      self.source.use(self.source.recommended_key())

  def status(self, model: ModelInfo) -> str:
    """One state per model: active, downloading, on device, not available, or downloadable."""
    if model.key == self.source.current_key():
      return "active"
    if model.key == self.source.downloading_key():
      return "downloading"
    if model.installed:
      return "on_device"
    if model.needs_egpu and not self.source.egpu_available():
      return "unavailable"
    return "download"

  def tab(self, index: int) -> list[ModelInfo]:
    models = self.source.models()
    if index == 1:
      return [m for m in models if m.community_pick]
    if index == 2:
      return [m for m in models if m.installed]
    return models

  def unused(self) -> list[ModelInfo]:
    return [m for m in self.source.models() if m.installed and m.removable and m.key not in (self.source.current_key(),
                                                                                          self.source.recommended_key())]

  def remove_unused(self) -> None:
    for model in self.unused():
      self.source.remove(model.key)

  def summary(self) -> str:
    return N_("Recommended") if self.use_recommended else self.current_name()

  def update_summary(self) -> str:
    if self.source.downloading_key():
      return N_("Downloading")
    return N_("Updates automatically") if self.use_recommended else N_("Chosen by you")


def model_row(models: Models, model: ModelInfo) -> Widget:
  return ModelRow(models, model)


class ModelRow(Component):
  """A model with its state and action, as in the mock: the active one lit up with a filled ACTIVE badge, a download with
  its progress bar, Use in the accent when it can be used, and a model that can't run here dimmed."""
  grow_touch_target = False
  INK = {"downloading": T.ACCENT_TEXT, "on_device": T.SUCCESS_TEXT}

  def __init__(self, models: Models, model: ModelInfo):
    super().__init__()
    self._models, self._model = models, model
    status = lambda: models.status(model)  # noqa: E731
    self._badge = self._child(Badge(N_("ACTIVE"), solid=True))
    self._use = self._child(Button(N_("Use"), lambda: models.source.use(model.key), ButtonStyle.PRIMARY, height=T.px(42),
                                   font_size=T.font_px(15)))
    self._use.set_visible(lambda: status() == "on_device" and not models.use_recommended)
    label = {"downloading": N_("Cancel"), "on_device": N_("Use"), "download": N_("Download"), "unavailable": N_("Not available")}
    self._action = self._child(Button(lambda: label.get(status(), ""), self._act, height=T.px(42), font_size=T.font_px(15)))
    self._action.set_visible(lambda: status() != "active" and not self._use.is_visible)
    self._action.set_enabled(lambda: status() in ("downloading", "download"))

  def _act(self) -> None:
    status = self._models.status(self._model)
    if status == "downloading":
      self._models.source.cancel()
    elif status == "download":
      self._models.source.download(self._model.key)

  def subtitle(self) -> str:
    status, source = self._models.status(self._model), self._models.source
    return {
      "active": N_("Recommended · On device") if self._model.key == source.recommended_key() else N_("On device"),
      "downloading": t_("Downloading · {}", source.progress() or 'starting'),
      "on_device": N_("On device"),
      "unavailable": N_("Needs an eGPU"),
      "download": N_("Community pick") if self._model.community_pick else N_("Available to download"),
    }[status]

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    status = self._models.status(self._model)
    return max_width, {"active": T.px(72), "downloading": T.px(82)}.get(status, T.px(68))

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    super().set_parent_rect(parent_rect)
    for w in (self._badge, self._use, self._action):
      w.set_parent_rect(parent_rect)

  def set_touch_valid_callback(self, touch_callback) -> None:
    super().set_touch_valid_callback(touch_callback)
    for w in (self._badge, self._use, self._action):
      w.set_touch_valid_callback(touch_callback)

  def _render(self, rect: rl.Rectangle):
    status = self._models.status(self._model)
    if status == "active":
      draw.fill(rect, T.ACCENT_SELECTED)
    body = inset(rect, left=T.px(20), right=T.px(16))
    top = rl.Rectangle(body.x, body.y, body.width, T.px(68) if status != "active" else body.height)
    trailing = self._badge if status == "active" else (self._use if self._use.is_visible else self._action)
    w, h = trailing.preferred_size(body.width / 2)
    trailing.render(place(top, w, h, Align.END))
    text = inset(top, right=w + T.px(14))
    lines = [draw.line_height(T.font_px(18)), draw.line_height(T.SIZE_SUBTITLE)]
    title, line = column(place(text, text.width, sum(lines) + T.px(3)), lines, T.px(3))
    dim = status == "unavailable"
    draw.text(title, self._model.name, T.font_px(18), T.TEXT_MUTED if dim else T.TEXT,
              T.FONT_BOLD if status in ("active", "downloading") else T.FONT_SEMIBOLD)
    usable = status == "on_device" and not self._models.use_recommended
    ink = self.INK.get(status) if status != "on_device" or usable else None
    draw.text(line, self.subtitle(), T.SIZE_SUBTITLE, T.TEXT_MUTED if dim else (ink or T.TEXT_TERTIARY))
    if status == "downloading":
      bar = rl.Rectangle(body.x, rect.y + rect.height - T.px(16), body.width, T.px(6))
      draw.fill(bar, T.TRACK, T.px(3))
      fraction = download_fraction(self._models.source.progress())
      if fraction > 0:
        draw.fill(rl.Rectangle(bar.x, bar.y, max(bar.height, bar.width * fraction), bar.height), T.ACCENT, T.px(3))


def download_fraction(progress: str) -> float:
  """0.45 from "45% · about 3 min left"; 0 before the first percent arrives."""
  match = re.match(r"\s*(\d+(?:\.\d+)?)%", progress or "")
  return min(1.0, float(match.group(1)) / 100) if match else 0.0


class Pair(Component):
  """Whichever of two controls is visible (e.g. the ACTIVE badge or an action button)."""
  grow_touch_target = False

  def __init__(self, first: Component, second: Component):
    super().__init__()
    self._items = [self._child(first), self._child(second)]

  def _visible(self) -> Component:
    return next((w for w in self._items if w.is_visible), self._items[-1])

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return self._visible().preferred_size(max_width)

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    super().set_parent_rect(parent_rect)
    for w in self._items:
      w.set_parent_rect(parent_rect)

  def _render(self, rect: rl.Rectangle):
    self._visible().render(rect)


class Rebuilding(Component):
  """Rebuilds its content when key() changes, e.g. a list of models after a download finishes."""
  grow_touch_target = False

  def __init__(self, key: Callable[[], object], build: Callable[[], Widget], tick: Callable[[], None] | None = None,
               on_show: Callable[[], None] | None = None):
    super().__init__()
    self._on_show = on_show
    self._key_fn = key
    self._build = build
    self._tick = tick
    self._key: object = None
    self._content: Widget | None = None
    self._shown = False

  def show_event(self):
    super().show_event()
    self._shown = True
    if self._on_show is not None:
      self._on_show()
    if self._content is not None:
      self._content.show_event()

  def hide_event(self):
    super().hide_event()
    self._shown = False
    if self._content is not None:
      self._content.hide_event()

  def _update_state(self):
    if self._tick is not None:
      self._tick()
    key = self._key_fn()
    if self._content is None or key != self._key:
      if self._content is not None and self._shown:
        self._content.hide_event()
      self._key, self._content = key, self._build()
      if self._shown:
        self._content.show_event()

  def _render(self, rect: rl.Rectangle):
    if self._content is not None:
      self._content.render(rect)


def model_page(models: Models, open_catalog: Callable[[], None]) -> Widget:
  """The active model on an accent card at the left; other models on the device at the right."""
  def build() -> Widget:
    current = models.source.current_key()
    # Models on the device first, then community picks to download.
    others = sorted((m for m in models.source.models() if m.key != current and (m.installed or m.community_pick)),
                    key=lambda m: not m.installed)[:3]
    active = Card([
      Inline(Badge(N_("ACTIVE"), solid=True)),
      Label(models.current_name, T.font_px(26), weight=T.FONT_EXTRABOLD),
      Text(lambda: N_("Chosen for your car. Swaps to newer recommended models automatically.") if models.use_recommended
           else N_("Picked by you"), T.font_px(16), T.TEXT_TERTIARY, padding=(0, 0)),
      SPACER,
      Surface(SettingRow(N_("Use recommended"), N_("Turn off to pick your own"), Switch(lambda: models.use_recommended,
                                                                              models.set_use_recommended)),
              T.ACCENT_INSET, T.px(16)),
    ], padding=(T.px(22), T.px(22)), tone="accent")
    browse = Button(N_("Browse all"), open_catalog, ButtonStyle.GHOST, height=T.px(32))
    other = ListPanel([
      SectionHeader(N_("OTHER MODELS"), trailing=browse),
      *[model_row(models, m) for m in others],
      Text(N_("Available when Use recommended is off. Model randomizer and blacklist are in Tuner Mode."), T.SIZE_SUBTITLE),
    ])
    return Columns([active, other], [1, 1.2])

  return TitledPage(N_("Driving Model"), N_("The neural network that steers and judges speed"),
                    Rebuilding(lambda: (models.source.current_key(), tuple((m.key, m.installed) for m in models.source.models())), build,
                               models.source.tick, on_show=models.source.refresh))


class CatalogPage(Component):
  """The title and tabs above; the models on the left; storage and notes on two cards at the right."""
  grow_touch_target = False
  TABS = [N_("All models"), N_("Community picks"), N_("On device")]   # the mock's "For your car": StarPilot lists every model for every car

  def __init__(self, models: Models, sizes: Callable[[], dict[str, float]]):
    super().__init__()
    self._models = models
    self._tab = 0
    self._tabs = self._child(Segmented(self.TABS, lambda: self._tab, self._select, height=T.px(52), font_size=T.font_px(16)))
    self._list = self._child(Rebuilding(
      lambda: (self._tab, tuple((m.key, m.installed) for m in models.tab(self._tab))),
      lambda: ListPanel([model_row(models, m) for m in models.tab(self._tab)] or [Text(N_("No models here yet."))]),
      models.source.tick))
    remove = Button(lambda: t_("Remove unused models ({})", len(models.unused())) if models.unused() else N_("Remove unused models"),
                    lambda: (models.remove_unused(), STORAGE.forget()), height=T.px(46), font_size=T.font_px(15))
    remove.set_enabled(lambda: bool(models.unused()) and not models.source.removal_blocked())
    note = lambda text: Text(text, T.SIZE_SUBTITLE, T.TEXT_SECONDARY, padding=(0, 0))  # noqa: E731
    self._side = self._child(Stack([
      Card([
        StorageBar(sizes, heading=N_("Storage"), padding=(0, 0)),
        remove,
      ], gap=T.px(10), padding=(T.px(18), T.px(16)), background=T.SURFACE_2),
      Card([
        Label(N_("GOOD TO KNOW"), caption=True),
        note(N_("One download at a time, paused while driving.")),
        note(N_("A new model applies on your next drive.")),
        SPACER,
      ], gap=T.px(10), padding=(T.px(18), T.px(16)), background=T.SURFACE_2),
    ], gap=T.px(14), grow=1))

  def _select(self, index: int) -> None:
    self._tab = index

  def _render(self, rect: rl.Rectangle):
    from openpilot.selfdrive.ui.tandem.settings.pages import body_rect
    body = inset(body_rect(rect), top=T.px(2))
    header, content = column(body, [T.px(56), FILL], T.px(14))
    w, h = self._tabs.preferred_size(header.width / 2)
    self._tabs.render(place(header, w, h, Align.END))
    draw.text(inset(header, left=T.px(6), right=w + T.px(14)), N_("Driving models"), T.font_px(26), T.TEXT, T.FONT_EXTRABOLD)
    left, right = row(content, [FILL, T.px(280)], T.px(14))
    self._list.render(left)
    self._side.render(right)


class UpstreamModels:
  """ModelSource backed by StarPilot's driving model screen controller."""

  def __init__(self, notify: Callable[[str], None] | None = None):
    """notify shows a message StarPilot would have shown in its own alert box (e.g. "Cannot download models while
    driving"); without it the message is dropped."""
    from openpilot.selfdrive.ui.layouts.settings.starpilot import driving_model as dm
    self._dm = dm
    from openpilot.selfdrive.ui.tandem.settings.controllers import notice_controller
    self._layout = notice_controller(dm.StarPilotDrivingModelLayout, notify or (lambda message: None))()

  def _run(self, action: Callable[[], None]) -> None:
    action()

  def refresh(self) -> None:
    self._layout.show_event()   # fetches the manifest in the background

  def tick(self) -> None:
    self._layout._update_state()   # starts and tracks the download thread

  def models(self) -> list[ModelInfo]:
    entries = {e.key: e for e in self._layout.installed_entries() + self._layout.available_entries()}
    return [ModelInfo(e.key, self._dm._clean_model_name(e.name), e.installed, e.community_favorite, e.requires_external_gpu,
                      self._layout.is_model_removable(e.key)) for e in entries.values()]

  def current_key(self) -> str:
    entry = self._layout.current_entry()
    return entry.key if entry else ""

  def recommended_key(self) -> str:
    return self._dm.canonical_model_key(self._layout._default_model_key())

  def downloading_key(self) -> str | None:
    if not self._layout._is_download_active():
      return None
    active = self._layout._params_memory.get(self._dm.MODEL_DOWNLOAD_PARAM, encoding="utf-8") or ""
    return self._dm.canonical_model_key(active) or None

  def progress(self) -> str:
    return self._layout.download_progress_text()

  def egpu_available(self) -> bool:
    return bool(self._dm.external_gpu_available())

  def use(self, key: str) -> None:
    self._run(lambda: self._layout.select_model(key))

  def download(self, key: str) -> None:
    self._run(lambda: self._layout.start_download(key))

  def cancel(self) -> None:
    self._layout.cancel_active_download()

  def remove(self, key: str) -> None:
    self._run(lambda: self._layout.delete_model(key))

  def removal_blocked(self) -> str:
    """StarPilot's rules for deleting model files: not while driving, not during a download."""
    from openpilot.selfdrive.ui.ui_state import ui_state
    if ui_state.started:
      return N_("Park to remove models")
    if self._layout._is_download_active():
      return N_("Wait for the download to finish")
    return ""
