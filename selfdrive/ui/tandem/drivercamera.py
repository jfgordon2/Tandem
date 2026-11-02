"""Driver Camera preview (design/drivercamera.html): upstream's driver camera with our overlay.

EssentialsDriverCamera subclasses upstream's DriverCameraDialog, keeping its camera stream, driver view param, timeout
and tap-anywhere-to-close. Only the overlay is ours: back, a status pill, the face box, the driver monitor tile and a
hint. draw_overlay is the drawing alone, so it renders without a camera.
"""
from __future__ import annotations

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.controls import back_glyph
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, inset, place, row
from openpilot.selfdrive.ui.tandem.onroad.layers import dm_tile, draw_driver_monitor
from openpilot.selfdrive.ui.tandem.i18n import N_

FACE_FOUND = 0.7            # upstream's face probability for drawing the box
HINT = N_("Sit as you do to drive. The box should follow your face.")


def face_box(face_x: float, face_y: float, rect: rl.Rectangle) -> rl.Rectangle:
  """Upstream's approximate mapping from the model's face position to the full-screen view (2160 x 1080)."""
  sx, sy = rect.width / 2160, rect.height / 1080
  x = 1080.0 - 1714.0 * face_x
  y = -135.0 + (504.0 + abs(face_x) * 112.0) + (1205.0 - abs(face_x) * 724.0) * face_y
  size = 220
  return rl.Rectangle(rect.x + (x - size / 2) * sx, rect.y + (y - size / 2) * sy, size * sx, size * sy)


def draw_overlay(rect: rl.Rectangle, starting: bool, face: rl.Rectangle | None, face_alpha: float, watching: bool, attentive: float) -> None:
  if starting:
    draw.fill(rect, T.BG)
    draw.text(rect, N_("Starting the camera…"), T.font_px(24), T.TEXT_SECONDARY, T.FONT_SEMIBOLD, Align.CENTER)
  elif face is not None:
    draw.stroke(face, draw.alpha(T.SUCCESS_BRIGHT, face_alpha), T.px(34), T.px(4))

  back = rl.Rectangle(rect.x + T.px(18), rect.y + T.px(18), T.NAV_BUTTON, T.NAV_BUTTON)
  draw.fill(back, draw.alpha(T.CONTROL_NAV, 0.8), T.RADIUS_CARD)
  back_glyph(back, T.TEXT, T.px(28))

  found = face is not None and not starting
  text = N_("Face found · driver monitoring can see you") if found else N_("Looking for your face")
  width = T.px(20) * 2 + T.px(22) + draw.text_width(text, T.font_px(18), T.FONT_SEMIBOLD)
  pill = rl.Rectangle(rect.x + (rect.width - width) / 2, rect.y + T.px(18), width, T.px(52))
  draw.fill(pill, draw.alpha(T.SUCCESS_SURFACE if found else T.WARNING_SURFACE, 0.9), T.px(16))
  dot, words = row(inset(pill, x=T.px(20)), [T.px(12), FILL], T.px(10))
  draw.fill(place(dot, T.px(12), T.px(12)), T.SUCCESS_BRIGHT if found else T.WARNING, T.px(6))
  draw.text(words, text, T.font_px(18), T.SUCCESS_CHIP_TEXT if found else T.WARNING_CHIP_TEXT, T.FONT_SEMIBOLD)

  draw_driver_monitor(dm_tile(rect), 1.0 if watching else 0.35, attentive, watching)

  hint_w = T.px(22) * 2 + draw.text_width(HINT, T.font_px(17))
  hint = rl.Rectangle(rect.x + (rect.width - hint_w) / 2, rect.y + rect.height - T.px(20) - T.px(50), hint_w, T.px(50))
  draw.fill(hint, draw.alpha(T._hex("0B0D10"), 0.9), T.px(16))
  draw.text(hint, HINT, T.font_px(17), T.TEXT_SECONDARY, T.FONT, Align.CENTER)


def driver_camera():
  """Upstream's driver camera with our overlay. Made on demand: its camera stream needs the device's libraries."""
  from openpilot.selfdrive.ui.onroad.driver_camera_dialog import DriverCameraDialog
  from openpilot.selfdrive.ui.ui_state import ui_state

  class EssentialsDriverCamera(DriverCameraDialog):
    def _render(self, rect):
      super(DriverCameraDialog, self)._render(rect)   # the camera itself (CameraView)
      dm = self.driver_state_renderer
      dm._update_state()
      attentive = dm._color_fade_filter.update(0.0 if dm._awareness_unfull else 1.0)
      face, alpha = None, 0.0
      if self.frame:
        state = ui_state.sm["driverStateV2"]
        data = state.rightDriverData if state.wheelOnRightProb > 0.5 else state.leftDriverData
        if data.faceProb > FACE_FOUND:
          spread = max(data.faceOrientationStd[0], data.faceOrientationStd[1])
          alpha = 1.0 if spread <= 0.15 else max(1.0 - (spread - 0.15) * 5.0, 0.0)
          face = face_box(data.facePosition[0], data.facePosition[1], rect)
      draw_overlay(rect, not self.frame, face, alpha, dm.is_active, attentive)
      return -1

  return EssentialsDriverCamera()
