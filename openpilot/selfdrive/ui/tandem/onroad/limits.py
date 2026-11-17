"""MAX follows limits (prefs.MAX_FOLLOWS_LIMIT): when the posted limit changes, StarPilot sets MAX from it.

StarPilot otherwise coasts down to a lower limit under an unchanged MAX, which can take a minute or more. With this on,
each new limit is adopted once through StarPilot's own ADOPT action (the one its "Match the speed limit" wheel button
sends), so StarPilot sets MAX to the limit plus the driver's offset and slows as it does for a lower MAX. A higher limit
that StarPilot asks about is adopted only after the driver accepts it, as ADOPT is refused while a limit is pending. Only
a change adopts, so a MAX the driver sets afterwards stays until the next limit. It applies only where StarPilot sets
MAX (not the car's own cruise), while engaged.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


def same(a: float, b: float) -> bool:
  return math.isclose(a, b, rel_tol=0.0, abs_tol=0.1)


@dataclass
class LimitFollower:
  """Which posted limit MAX last followed (m/s), so each change is adopted once."""
  limit: float = 0.0

  def update(self, limit: float | None, valid: bool, pending: bool, engaged: bool) -> bool:
    """Whether to adopt the posted limit now.

    Args:
      limit: StarPilot's posted limit in m/s, if any.
      valid: StarPilot has a live limit from a real source (not its fallback).
      pending: StarPilot is asking the driver about a new limit, or adopting one itself.
      engaged: openpilot is engaged.

    Returns:
      True once when the limit has changed and can be adopted.
    """
    if not valid or limit is None or limit <= 1:
      return False
    if self.limit <= 1:
      self.limit = limit                  # the first limit seen: follow from here on
      return False
    if same(limit, self.limit) or pending:
      return False                        # unchanged, or wait until the driver answers
    self.limit = limit
    return engaged
