"""Essentials design tokens. See design/tokens.md.

The mocks are drawn on a 1125x563 frame; the comma 3/3X panel is 2160x1080, so one mock
px is SCALE device px. Layout values below are already in device px. Font sizes are the
values to pass to draw calls. The text patch in application.py multiplies them by
FONT_SCALE, which is what turns a draw size into the same em size as CSS (the atlases
are sized by line height), so a mock's CSS font-size converts with SCALE alone.
"""

import pyray as rl

from openpilot.system.ui.lib.application import FontWeight
from openpilot.selfdrive.ui.tandem.fonts import ExtraFont

SCALE = 2160 / 1125


def px(mock_px: float) -> int:
  return round(mock_px * SCALE)


def font_px(mock_px: float) -> int:
  return round(mock_px * SCALE)


def _hex(value: str, alpha: int = 255) -> rl.Color:
  value = value.lstrip("#")
  return rl.Color(int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha)


# ── Surfaces, darkest to lightest ──
BG = _hex("000000")                     # true-black page ground for OLED
SCRIM = _hex("050608")                  # behind sheets and dialogs
NAV_BAR = _hex("0E1013")
NAV_BAR_EDGE = _hex("1F242B")
SURFACE_1 = _hex("13161A")              # grouped strips, sidebar sections, power-user rows
STRIP_EDGE = _hex("252A31")             # outline of the power-user strip
SURFACE_2 = _hex("16191D")              # panels and sheets
SURFACE_3 = _hex("1A1D22")              # hub tiles, cards on BG
SURFACE_4 = _hex("1E2227")              # cards inside a panel
CONTROL = _hex("23272E")                # segmented track, secondary buttons, row dividers
CONTROL_NAV = _hex("1F2328")            # back/close and onroad controls
KEY = _hex("262A31")                    # keyboard keys
KEY_MOD = _hex("353A43")                # shift, backspace, 123
TRACK = _hex("2A2F36")                  # slider and progress tracks, input outlines

# ── Text ──
TEXT = _hex("F2F5F9")
TEXT_SECONDARY = _hex("C9D0DA")         # labels on controls, unselected segments, nav
TEXT_TERTIARY = _hex("AEB6C2")          # row subtitles, data labels
TEXT_MUTED = _hex("8FA0B5")             # section labels, footnotes

# ── Accent (blue) ──
ACCENT = _hex("5AAAF8")                 # selected segment, primary buttons, switch on
ACCENT_INK = _hex("0B1A2B")             # text on ACCENT
ACCENT_TEXT = _hex("7DBBF9")            # links, icons, section headings
ACCENT_SURFACE = _hex("1F2E45")         # icon wells, selected sidebar item, speed chips
ACCENT_SELECTED = _hex("182434")        # selected card fill, with a 2 mock px ACCENT edge
ACCENT_EDGE = _hex("2D4A6E")             # edge of the active card (the current model)
ACCENT_INSET = _hex("13202E")            # boxes inside the active card
ACCENT_CHIP_TEXT = _hex("DCEBFF")

# ── Status ──
SUCCESS = _hex("1F9A55")                # engaged border, engage button
SUCCESS_BRIGHT = _hex("3FD08A")         # turn signal chevrons, status dots
SUCCESS_TEXT = _hex("6FD8A0")
SUCCESS_SURFACE = _hex("13301F")
SUCCESS_CARD = _hex("13221A")           # a card for something that worked (button detected)
SUCCESS_EDGE = _hex("1F5A3A")
SUCCESS_WELL = _hex("1B3A28")
SUCCESS_CHIP_TEXT = _hex("D2F5E1")

WARNING = _hex("F0B35A")                # Tuner Mode, paused or blocked chips, working arc
WARNING_BORDER = _hex("E0A23A")         # warning alert border
WARNING_SURFACE = _hex("3A2E1B")
WARNING_BANNER = _hex("221D14")
WARNING_TITLE = _hex("FFD08A")
WARNING_CHIP_TEXT = _hex("FFE3B8")

DANGER = _hex("D9434F")                 # critical alert border
DANGER_BUTTON = _hex("C8404D")          # destructive confirm
DANGER_TEXT = _hex("F2A7B1")
DANGER_SURFACE = _hex("3A2026")
DANGER_BORDER = _hex("5A3A40")
DANGER_STRIPE = _hex("2A1A1E")          # the darker band of the hatched safety floor; the other is DANGER_SURFACE
CRITICAL_FILL = _hex("2A0E12")

# ── Switch ──
SWITCH_TRACK_ON = ACCENT
SWITCH_KNOB_ON = _hex("0E1520")
SWITCH_TRACK_OFF = _hex("343A44")
SWITCH_KNOB_OFF = TEXT

# ── Onroad ──
ONROAD_BAR_SCRIM_TOP = _hex("0B0D10", 0)        # bar is a vertical gradient between these
ONROAD_BAR_SCRIM_BOTTOM = _hex("0B0D10", 140)
ONROAD_CONTROL = _hex("1F2328", 204)
ONROAD_CARD = _hex("0B0D10", 230)                # speed, status chips, road name
ONROAD_METRICS_STRIP = _hex("0B0D10", 153)
LEAD_MARKER = _hex("E9B44C")
STEER_ARC_TRACK = _hex("FFFFFF", 46)
STEER_ARC_COMFORT = _hex("FFFFFF", 230)          # under 60%
STEER_ARC_WORKING = WARNING                      # 60-85%
STEER_ARC_LIMIT = _hex("FF6A3D")                 # over 85% for STEER_LIMIT_HOLD_MS
STEER_ARC_LANE_TINT = _hex("FF8A4D")

# ── Type ──
FONT = FontWeight.ROMAN                         # Figtree Regular on every UI size
FONT_MEDIUM = FontWeight.MEDIUM
FONT_SEMIBOLD = FontWeight.SEMI_BOLD            # row titles, buttons, nav
FONT_BOLD = FontWeight.BOLD                     # panel titles, selected segments
FONT_EXTRABOLD = ExtraFont.EXTRA_BOLD           # screen titles, speed, big values (loaded on first use)
FONT_MONO = ExtraFont.MONO                      # Developer View (loaded on first use)
FONT_MONO_BOLD = ExtraFont.MONO_BOLD
FONT_UNIFONT = FontWeight.UNIFONT               # names in other scripts, e.g. the language list

SIZE_VALUE = font_px(72)                # value editors
SIZE_SPEED = font_px(62)
SIZE_TITLE = font_px(28)                # screen titles
SIZE_PANEL_TITLE = font_px(24)
SIZE_CARD_TITLE = font_px(22)           # hub tiles, card headings
SIZE_ROW_TITLE = font_px(19)
SIZE_BODY = font_px(18)                 # sidebar items, nav, primary buttons
SIZE_BUTTON = font_px(16)               # segments, secondary buttons
SIZE_LABEL = font_px(15)
SIZE_SUBTITLE = font_px(14)             # row subtitles, footnotes
SIZE_CAPTION = font_px(13)              # section labels, drawn in capitals with CAPTION_TRACKING
SIZE_BADGE = font_px(12)
CAPTION_TRACKING = px(1.6)

# ── Shape ──
RADIUS_PANEL = px(22)                   # panels, hub tiles, sheets (top corners 26)
RADIUS_SHEET = px(26)
RADIUS_CARD = px(18)                    # cards in a panel, nav pills
RADIUS_ITEM = px(14)                    # sidebar items, list rows
RADIUS_SEGMENT_TRACK = px(13)
RADIUS_CONTROL = px(12)                 # buttons, chips
RADIUS_SEGMENT = px(10)
RADIUS_BADGE = px(8)
SELECTED_EDGE = px(2)
DIVIDER = 2

# ── Layout ──
NAV_HEIGHT = px(102)
NAV_BUTTON = px(74)                     # back/close, StarPilot pill, tab height
SIDEBAR_WIDTH = px(300)
SIDEBAR_ITEM_HEIGHT = px(56)
PAGE_INSET = px(20)
PANEL_GAP = px(18)
PANEL_HEADER_INSET = px(22)
ROW_HEIGHT = px(70)                     # a settings row, as on the Theme & Startup mock
SUB_ROW_HEIGHT = px(48)                 # indented rows under a choice, on SURFACE_1
SEGMENT_HEIGHT = px(50)                 # the whole track: 42 px segments inside 4 px of padding, as in the mocks
BUTTON_HEIGHT = px(44)
PRIMARY_BUTTON_HEIGHT = px(60)
SWITCH_WIDTH = px(72)
SWITCH_HEIGHT = px(42)
ICON_WELL = px(62)
ONROAD_BAR_HEIGHT = px(92)
ONROAD_CONTROL_SIZE = px(74)
STATUS_CHIP_HEIGHT = px(44)
MIN_TOUCH = 112                         # mock controls under 58 px grow to this

# ── States ──
PRESSED_OVERLAY = _hex("FFFFFF", 20)    # drawn over any control while touched
DISABLED_ALPHA = 0.5                    # whole row or control, label stays readable

# ── Motion ──
SHEET_MS = 240                          # sheets slide up, dialogs fade and scale from 96%
SWITCH_MS = 150
PRESSED_ROW_MS = 600                    # wheel-button "PRESSED" highlight after a press
STATUS_CHIP_HOLD_MS = 2000              # stays this long after its reason ends
STATUS_CHIP_FADE_MS = 200
TOAST_MS = 4000
STEER_LIMIT_HOLD_MS = 500
SPEED_LIMIT_PROMPT_MS = 8000            # higher-limit confirmation times out to Ignore
