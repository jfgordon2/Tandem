"""Track consecutive posted limits and the driver's dismissal in native m/s, independent of display units."""
import math
from dataclasses import dataclass
from openpilot.selfdrive.ui.tandem.i18n import N_

LIVE_SOURCES = {N_("Dashboard"), N_("Map Data"), N_("Vision"), N_("Mapbox")}


@dataclass
class LimitOfferState:
  last_limit: float = 0.0
  ignored_limit: float = 0.0
  pending_limit: float = 0.0
  since: float | None = None

  @staticmethod
  def same(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=0.0, abs_tol=0.1)

  def observe(self, pending: float, current: float, current_source: str, now: float) -> None:
    # A rejected/expired offer can leave the old accepted target in the plan. Only a live source counts as a change.
    observed = pending if pending > 1 else current if current_source in LIVE_SOURCES else 0.0
    if observed > 1:
      if self.last_limit > 1 and not self.same(observed, self.last_limit):
        self.ignored_limit = 0.0
      self.last_limit = observed
    if pending <= 1:
      self.since = None
    elif self.since is None or not self.same(pending, self.pending_limit):
      self.since = now
    self.pending_limit = pending

  @property
  def ignored(self) -> bool:
    return self.pending_limit > 1 and self.same(self.pending_limit, self.ignored_limit)

  def ignore(self) -> None:
    self.ignored_limit = self.pending_limit


@dataclass
class LimitFollower:
  """MAX follows the speed limit (prefs.MAX_FOLLOWS_LIMIT): when StarPilot adopts a new limit, MAX becomes it plus the
  offset. StarPilot otherwise coasts down to a lower limit under an unchanged MAX, which can take a minute or more;
  with MAX at the limit it slows as it does for a lower MAX. A higher limit raises MAX once StarPilot has adopted it
  (after Match when it asks). Only a change moves MAX, so a MAX the driver sets afterwards stays until the next limit.

  Everything here is in m/s; update() returns the MAX to set, or None.
  """
  limit: float = 0.0

  def update(self, limit: float, source: str, offset: float, set_speed: float, engaged: bool) -> float | None:
    if limit <= 1 or source not in LIVE_SOURCES:
      return None                         # no posted limit, or StarPilot's fallback: nothing to follow
    previous, self.limit = self.limit, limit
    if previous <= 1 or LimitOfferState.same(limit, previous) or not engaged or set_speed <= 0:
      return None                         # the first limit seen, the same limit, or no MAX to move
    target = limit + offset
    if limit < previous:
      return target if set_speed > target + 0.3 else None    # only ever lowers for a lower limit
    return target if set_speed < target - 0.3 else None      # only ever raises for a higher one (a higher MAX stays)


@dataclass
class OfferChime:
  """One soft chime as each new-limit card appears: openpilot's pre-alert (pre_alert.wav, the first "Pay Attention"
  chime, at the Driver attention volume). Not again while the same offer stays up, nor for an offer the driver ignored
  (its card isn't shown)."""
  shown: tuple | None = None

  def update(self, offer: tuple | None) -> bool:
    """offer identifies the card on screen (its limit and when it was first offered), or None. True: chime now."""
    chime = offer is not None and offer != self.shown
    self.shown = offer
    return chime
