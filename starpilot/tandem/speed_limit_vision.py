"""Keep the speed-sign model allocations only while vision can use them."""
import ctypes
import time

# Use the manager's module name so it and the subclass share the base class.
from starpilot.system.speed_limit_vision import SpeedLimitVisionDaemon


MODEL_RETRY_SECONDS = 30.0


def trim_heap() -> None:
  try:
    ctypes.CDLL(None).malloc_trim(0)
  except (AttributeError, OSError):
    pass  # The system allocator may not provide malloc_trim.


class TandemSpeedLimitVisionDaemon(SpeedLimitVisionDaemon):
  """Load vision models at drive start and release them during long idle periods."""

  def __init__(self, use_runtime: bool = True) -> None:
    super().__init__(use_runtime=use_runtime, load_models=False)
    self._next_model_attempt = -float("inf")

  def _prepare_models(self, started: bool, now: float) -> bool:
    if not started or self.memory_pressure_state == "critical":
      if self.net is not None:
        self._disconnect_camera()
        self.current_frame_bgr = None
        self.latest_detector_proposal = None
        self._clear_proposal_track()
        self.pending_auto_bookmark = None
        self.pending_training_capture = None
        self.net = self.classifier_net = self.reject_classifier_net = None
        trim_heap()
      self._next_model_attempt = -float("inf")
      # Let the normal idle or memory-pause path publish its status.
      return True

    if self.net is None and now >= self._next_model_attempt:
      self._load_model()
      self._next_model_attempt = time.monotonic() + MODEL_RETRY_SECONDS
      self.last_inference_at = -float("inf")
    return self.net is not None
