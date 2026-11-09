"""Developer View onroad (design/onroaddev.html).

- A panel on the right: LEAD (distance, gap, relative speed, radar or vision), DEVICE (CPU and temperature, GPU, RAM with
  bars, FPS) and CONTROLS (curve speed, limit source, lane widths). It replaces StarPilot's developer sidebar, which
  still decides when the panel shows (its DeveloperSidebar setting).
- A strip above the bar: up to five metrics the driver picks (STRIP_METRICS, kept in prefs.DEVELOPER_STRIP), spread
  evenly across it. The mock's five are the default; picking none hides the strip.
- A tag above the lead car: distance, gap and relative speed.

Each Device and Controls row follows StarPilot's own switch for it (ShowCPU, ShowGPU, NumericalTemp, ShowMemoryUsage,
FPSCounter, AdjacentPathMetrics, SpeedLimitSources), so Bundle Overrides decides what shows.

read() gathers every value from openpilot's and StarPilot's messages; the draw functions only draw, so they render
without a car.
"""
from __future__ import annotations

from dataclasses import dataclass

import pyray as rl

from openpilot.selfdrive.ui.tandem.onroad import size as Z
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, row
from openpilot.selfdrive.ui.tandem.i18n import N_, t_, translate
from openpilot.selfdrive.ui.tandem.prefs import DEVELOPER_STRIP

PANEL_W = T.px(256)                 # the mock's sidebar
WIDTH = PANEL_W + T.px(10)          # with its gap from the road view


def strip_h() -> int:
  """As onroaddev.html (was 30); larger with Text Size."""
  return Z.px(40)


def strip_gap() -> int:
  """Between the strip and the bar, and the lowest lead tag and whatever it rests on."""
  return Z.px(6)


def strip_text() -> int:
  """As onroaddev.html (13 was too small to read while driving)."""
  return Z.font_px(18)

TILE_FILL = T._hex("1E2227")
LABEL = T._hex("9FAABA")
BAR_INK = T.ACCENT_TEXT
STRIP_FILL = rl.Color(0x0B, 0x0D, 0x10, 0x99)
TAG_FILL = rl.Color(0x0B, 0x0D, 0x10, 0xE6)
MONO, BOLD = T.FONT_MONO, T.FONT_MONO_BOLD   # the mock sets the panel, strip and tag in JetBrains Mono


# The strip's choices: key, its label on the strip, and what it is (for the picker), in the order they're drawn.
STRIP_METRICS: dict[str, tuple[str, str]] = {
  "accel": (N_("accel"), N_("Acceleration now")),
  "want": (N_("want"), N_("Acceleration openpilot asks for")),
  "jerk": (N_("jerk"), N_("Planned jerk")),
  "lat": (N_("lat"), N_("Lateral acceleration")),
  "delay": (N_("delay"), N_("Steering delay")),
  "steer": (N_("steer"), N_("Steering wheel angle")),
  "torque": (N_("torque"), N_("Steering torque used")),
  "danger": (N_("danger"), N_("Following danger factor")),
  "ratio": (N_("ratio"), N_("Steer ratio")),
}
STRIP_PARAM = "DeveloperStripMetrics"
STRIP_DEFAULT = ("accel", "want", "jerk", "lat", "delay")
STRIP_MAX = 5


def strip_keys(raw: str | bytes | None) -> list[str]:
  """The picked metrics from the param, known ones only, at most STRIP_MAX, in STRIP_METRICS order."""
  text = raw.decode() if isinstance(raw, bytes) else str(raw or "")
  if not text:
    return list(STRIP_DEFAULT)      # unset (an empty pick is saved as "none")
  picked = {k.strip() for k in text.split(",")}
  return [k for k in STRIP_METRICS if k in picked][:STRIP_MAX]


@dataclass
class Lead:
  distance: str    # "38 m"
  gap: str         # "1.4 s"
  rel_speed: str   # "−2 mph"
  closing: bool    # the lead is slower: rel speed shows amber
  source: str      # "radar" or "vision"


@dataclass
class DevData:
  lead: Lead | None = None
  cpu: float = 0.0          # 0..1
  cpu_temp: str = ""        # "61°C"
  gpu: float = 0.0
  ram: float = 0.0
  ram_text: str = ""        # "3.1 GB"
  fps: str = ""
  curve: str = N_("idle")
  limit_source: str = N_("none")
  lanes: str = "—"
  accel: str = "+0.00"
  want: str = "+0.00"
  jerk: str = "0.0"
  lat: str = N_("0.0 m/s²")
  delay: str = N_("0.00 s")
  steer: str = "0°"
  torque: str = "0%"
  danger: str = "0%"
  ratio: str = "—"
  strip: tuple[str, ...] = STRIP_DEFAULT      # which metrics the strip shows
  # StarPilot's switches for each row
  show_cpu: bool = True
  show_temp: bool = True
  show_gpu: bool = True
  show_ram: bool = True
  show_fps: bool = True
  show_lanes: bool = True
  show_source: bool = True

  def strip_values(self) -> list[tuple[str, str]]:
    return [(STRIP_METRICS[k][0], getattr(self, k)) for k in self.strip]


# ── Drawing ──

def _caption() -> int:
  return round(T.SIZE_CAPTION * Z.zoom())


def _section(rect: rl.Rectangle, y: float, title: str) -> float:
  h = draw.line_height(_caption())
  draw.caption(rl.Rectangle(rect.x, y, rect.width, h), title, T.ACCENT_TEXT, size=_caption())
  return y + h + T.px(8)


def _pair(rect: rl.Rectangle, y: float, label: str, value: str) -> float:
  h = draw.line_height(Z.font_px(14))
  line = rl.Rectangle(rect.x, y, rect.width, h)
  draw.text(line, label, Z.font_px(14), LABEL, MONO)
  draw.text(line, value, Z.font_px(14), T.TEXT, MONO, Align.END)
  return y + h + T.px(7)


def _meter(rect: rl.Rectangle, y: float, share: float) -> float:
  track = rl.Rectangle(rect.x, y, rect.width, T.px(5))
  draw.fill(track, T.TRACK, T.px(3))
  if share > 0:
    draw.fill(rl.Rectangle(track.x, y, max(track.height, track.width * min(1.0, share)), track.height), BAR_INK, T.px(3))
  return y + track.height + T.px(7)


def draw_panel(rect: rl.Rectangle, data: DevData) -> None:
  """The right-hand panel: rect is the strip beside the road view (WIDTH wide)."""
  draw.fill(rect, T.BG)
  panel = rl.Rectangle(rect.x, rect.y + T.px(10), PANEL_W, rect.height - T.px(20))
  draw.fill(panel, T._hex("13161A"), T.px(18))
  body = inset(panel, T.px(14))
  y = _section(body, body.y, N_("Lead"))
  tile_h = Z.pick(52, 64)   # taller for the larger text, at the same width
  lead = data.lead
  tiles = [(N_("distance"), lead.distance if lead else "—", None), (N_("gap"), lead.gap if lead else "—", None),
           (N_("rel speed"), lead.rel_speed if lead else "—", T.WARNING if lead and lead.closing else None),
           (N_("source"), lead.source if lead else N_("none"), None)]
  for i in range(0, 4, 2):
    for (label, value, ink), cell in zip(tiles[i:i + 2], row(rl.Rectangle(body.x, y, body.width, tile_h), [FILL, FILL], T.px(6)), strict=True):
      draw.fill(cell, TILE_FILL, T.px(10))
      inner = inset(cell, x=T.px(10), y=T.px(7))
      top, bottom = column(inner, [draw.line_height(Z.font_px(11)), FILL], T.px(3))
      draw.text(top, label, Z.font_px(11), LABEL, MONO)
      draw.text(bottom, draw.fit(value, Z.font_px(18), BOLD, bottom.width), Z.font_px(18), ink or T.TEXT, BOLD)
    y += tile_h + T.px(6)
  if data.show_cpu or data.show_temp or data.show_gpu or data.show_ram or data.show_fps:
    y = _section(body, y + T.px(6), N_("Device"))
    if data.show_cpu or data.show_temp:
      load = f"{round(data.cpu * 100)}%" if data.show_cpu else ""
      temp = data.cpu_temp if data.show_temp else ""
      y = _pair(body, y, N_("CPU") if data.show_cpu else N_("Temp"), " · ".join(v for v in (load, temp) if v))
      if data.show_cpu:
        y = _meter(body, y, data.cpu)
    if data.show_gpu:
      y = _meter(body, _pair(body, y, N_("GPU"), f"{round(data.gpu * 100)}%"), data.gpu)
    if data.show_ram:
      y = _meter(body, _pair(body, y, N_("RAM"), data.ram_text), data.ram)
    if data.show_fps:
      y = _pair(body, y, N_("FPS"), data.fps)
  y = _section(body, y + T.px(6), N_("Controls"))
  y = _pair(body, y, N_("curve spd"), data.curve)
  if data.show_source:
    y = _pair(body, y, N_("limit src"), data.limit_source)
  if data.show_lanes:
    _pair(body, y, N_("lanes L/R"), data.lanes)


def draw_strip(rect: rl.Rectangle, data: DevData) -> None:
  """The picked metrics in one dark band: each gets an equal share of the width, centered in it, so fewer spread wider."""
  parts = data.strip_values()
  if not parts:
    return
  draw.fill(rect, STRIP_FILL)
  for (label, value), cell in zip(parts, row(inset(rect, x=Z.px(20)), [FILL] * len(parts), Z.px(12)), strict=True):
    label = translate(label)
    gap = draw.text_width(" ", strip_text(), MONO)   # a layout gap stays between the label and value in right-to-left scripts too
    vw = draw.text_width(value, strip_text(), BOLD)
    label = draw.fit(label, strip_text(), MONO, max(0, cell.width - gap - vw))
    lw = draw.text_width(label, strip_text(), MONO)
    gap = gap if label else 0
    x = cell.x + (cell.width - lw - gap - vw) / 2
    draw.text(rl.Rectangle(x, cell.y, lw, cell.height), label, strip_text(), T.TEXT_SECONDARY, MONO)
    draw.text(rl.Rectangle(x + lw + gap, cell.y, vw, cell.height), value, strip_text(), T.TEXT, BOLD)


def lead_tag_motion(progress: float) -> tuple[float, float, float]:
  """The anchor appears first, then its connector, then the tag; progress uses LeadSettle's ease-out."""
  p = max(0.0, min(1.0, progress))
  return min(1.0, p / 0.25), max(0.0, min(1.0, (p - 0.15) / 0.55)), max(0.0, min(1.0, (p - 0.45) / 0.55))


def draw_lead_tag(center_x: float, top_y: float, lead: Lead, *, compact: bool = False, value: str | None = None,
                  anchored: bool = False, braking: bool = False, opacity: float = 1.0, progress: float = 1.0,
                  bounds: rl.Rectangle | None = None, floor: float | None = None) -> rl.Rectangle | None:
  """One shared tag style: a gap in normal view, or the original distance/gap/relative-speed tag in developer views.

  floor is the lowest the tag may reach (the top of the metrics strip, or of the bar): a car close to it keeps its tag
  just above, without the anchor or connector, which would sit under the strip or bar."""
  ink = T.WARNING if braking else T.TEXT
  parts = [(value if value is not None else lead.gap, ink, BOLD)] if compact else [
    (lead.distance, T.TEXT, BOLD), (lead.gap, LABEL, BOLD), (lead.rel_speed, T.WARNING if lead.closing else T.TEXT_SECONDARY, BOLD)]
  size, gap, pad = strip_text(), Z.px(14), Z.px(14)   # the metrics strip's size (design/gaptag.html)
  widths = [draw.text_width(text, size, weight) for text, _, weight in parts]
  w = max(Z.px(78) if compact else 0.0, sum(widths) + gap * (len(parts) - 1) + pad * 2)
  h = Z.px(36)
  box = rl.Rectangle(center_x - w / 2, top_y - h - Z.px(14), w, h)
  anchor_alpha, connector, tag_alpha = lead_tag_motion(progress) if anchored else (0.0, 0.0, 1.0)
  if bounds is not None:
    margin = Z.px(8)
    if not (bounds.x + margin <= center_x <= bounds.x + bounds.width - margin
            and bounds.y + margin <= top_y <= bounds.y + bounds.height - margin):
      return None
    box.x = min(max(box.x, bounds.x + margin), bounds.x + bounds.width - margin - w)
  if floor is not None and box.y + h > floor:
    box.y = floor - h
    anchored = False      # the car is at or under the strip or bar: the tag alone, resting on it
  if anchored and anchor_alpha * opacity > 0.01:
    point = rl.Vector2(center_x, top_y)
    draw.disc(point, Z.px(4.2), draw.alpha(TAG_FILL, opacity * anchor_alpha))
    draw.disc(point, Z.px(2.7), draw.alpha(ink, opacity * anchor_alpha))
  if bounds is not None and (box.y < bounds.y + Z.px(8) or w > bounds.width - Z.px(16)):
    return None       # keep the anchor when there is no space for a readable tag above it
  if anchored and connector > 0:
    length = Z.px(10) * connector
    for width, color in ((Z.px(4.5), TAG_FILL), (Z.px(1.5), ink)):
      draw.fill(rl.Rectangle(center_x - width / 2, top_y - Z.px(3) - length, width, length),
                draw.alpha(color, opacity * anchor_alpha), width / 2)
    box.y += Z.px(4) * (1.0 - tag_alpha)
  alpha = opacity * tag_alpha
  if alpha <= 0.01:
    return box
  draw.fill(box, draw.alpha(TAG_FILL, alpha), Z.px(11))
  draw.stroke(box, draw.alpha(T.TRACK, alpha), Z.px(11), Z.px(1))
  x = box.x + (w - sum(widths)) / 2 if compact else box.x + pad
  for (text, ink, weight), width in zip(parts, widths, strict=True):
    draw.text(rl.Rectangle(x, box.y, width, box.height), text, size, draw.alpha(ink, alpha), weight)
    x += width + gap
  return box


# ── Reading ──

def _signed(value: float, digits: int = 2) -> str:
  return f"{value:+.{digits}f}".replace("-", "−")


def lead_of(lead, v_ego: float, metric: bool) -> Lead | None:
  """radarState's lead, in the driver's units."""
  if lead is None or not lead.status:
    return None
  from openpilot.common.constants import CV
  distance = t_("{} m", round(lead.dRel)) if metric else t_("{} ft", round(lead.dRel * CV.METER_TO_FOOT))
  rel = lead.vRel * (CV.MS_TO_KPH if metric else CV.MS_TO_MPH)
  return Lead(distance, t_("{} s", f"{lead.dRel / max(v_ego, 1.0):.1f}"), f"{round(rel):+d} {'km/h' if metric else 'mph'}".replace("-", "−"),
              rel < -0.5, N_("radar") if getattr(lead, "radar", False) else N_("vision"))


def read(ui_state, params=None) -> DevData:
  """Every value the Developer View shows, from the messages the UI already receives, and which parts StarPilot's switches
  turn on. params is the UI's per-frame param cache (ui_state.ui_params by default)."""
  from openpilot.common.constants import CV
  params = params if params is not None else ui_state.ui_params
  toggles = ui_state.starpilot_toggles or {}
  shown = lambda toggle, key: bool(toggles[toggle]) if toggle in toggles else bool(params.get_bool(key))  # noqa: E731
  sm = ui_state.sm
  get = lambda name: sm[name] if sm.valid.get(name, False) else None  # noqa: E731
  car, control, plan, device, delay = get("carState"), get("carControl"), get("starpilotPlan"), get("deviceState"), get("liveDelay")
  controls, radar = get("controlsState"), get("radarState")
  metric = bool(ui_state.is_metric)
  v_ego = car.vEgo if car else 0.0
  data = DevData(strip=tuple(strip_keys(DEVELOPER_STRIP.get())),
                 show_cpu=shown("cpu_metrics", "ShowCPU"), show_temp=shown("numerical_temp", "NumericalTemp"),
                 show_gpu=shown("gpu_metrics", "ShowGPU"), show_ram=shown("memory_metrics", "ShowMemoryUsage"),
                 show_fps=shown("show_fps", "FPSCounter"), show_lanes=shown("adjacent_path_metrics", "AdjacentPathMetrics"),
                 show_source=shown("speed_limit_sources", "SpeedLimitSources"))
  data.lead = lead_of(radar.leadOne if radar else None, v_ego, metric)
  if device:
    cpus = list(device.cpuUsagePercent)
    data.cpu = (sum(cpus) / len(cpus) / 100.0) if cpus else 0.0
    data.cpu_temp = f"{round(device.maxTempC)}°C"
    data.gpu = device.gpuUsagePercent / 100.0
    data.ram = device.memoryUsagePercent / 100.0
    data.ram_text = t_("{} GB", f"{8.0 * data.ram:.1f}")     # as StarPilot reckons it
  data.fps = f"{round(rl.get_fps())}"
  if plan:
    speed = plan.cscSpeed * (CV.MS_TO_KPH if metric else CV.MS_TO_MPH)
    data.curve = t_("active · {} {}", round(speed), 'km/h' if metric else 'mph') if plan.cscControllingSpeed else N_("idle")
    data.limit_source = (plan.slcPresentedSpeedLimitSource or plan.slcSpeedLimitSource or "none").lower()
    unit, scale = ("m", 1.0) if metric else ("ft", CV.METER_TO_FOOT)
    data.lanes = f"{plan.laneWidthLeft * scale:.1f} / {plan.laneWidthRight * scale:.1f} {unit}"
    data.jerk = f"{plan.accelerationJerk:.1f}"
  if car:
    data.accel = _signed(car.aEgo)
  if control:
    data.want = _signed(control.actuators.accel)
    data.torque = f"{round(abs(control.actuators.torque) * 100)}%"
  if car:
    data.steer = f"{round(car.steeringAngleDeg)}°".replace("-", "−")
  if plan:
    data.danger = f"{round(plan.dangerFactor * 100)}%"
  live = get("liveParameters")
  if live:
    data.ratio = f"{live.steerRatio:.2f}"
  if controls and car:
    data.lat = t_("{} m/s²", f"{abs(car.vEgo ** 2 * controls.curvature):.1f}")
  if delay:
    data.delay = t_("{} s", f"{delay.lateralDelay:.2f}")
  return data


def developer_ui_on(ui_state, params) -> bool:
  """StarPilot's Developer UI switch (the Developer View bundle turns it on)."""
  return bool(ui_state.starpilot_toggles.get("developer_ui", params.get_bool("DeveloperUI")))


def developer_view_on(ui_state, params) -> bool:
  """The Developer View switch: its bundle is keyed on StarPilot's DeveloperSidebar. Developer UI alone isn't enough,
  since Lead Insights keeps it on after Developer View is turned off."""
  toggles = ui_state.starpilot_toggles or {}
  sidebar = toggles["developer_sidebar"] if "developer_sidebar" in toggles else params.get_bool("DeveloperSidebar")
  return developer_ui_on(ui_state, params) and bool(sidebar)


def developer_sidebar():
  """The right panel, shown when StarPilot's developer sidebar would be. Made on the device only."""
  from openpilot.selfdrive.ui.onroad.starpilot.developer_sidebar import DeveloperSidebar
  from openpilot.selfdrive.ui.ui_state import ui_state

  class EssentialsDeveloperSidebar(DeveloperSidebar):
    def update(self):
      super().update()   # StarPilot decides whether the sidebar shows
      self._data = read(ui_state) if self._visible else None

    def render(self, sidebar_rect: rl.Rectangle):
      if self._visible and getattr(self, "_data", None) is not None:
        draw_panel(sidebar_rect, self._data)

  return EssentialsDeveloperSidebar()
