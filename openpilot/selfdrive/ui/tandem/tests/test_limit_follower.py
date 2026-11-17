"""MAX follows limits (onroad/limits.py): each new posted limit is adopted once, through StarPilot's ADOPT."""
from __future__ import annotations

from openpilot.selfdrive.ui.tandem.onroad.limits import LimitFollower

MPH = 0.44704


def test_the_first_limit_is_where_following_starts() -> None:
  follower = LimitFollower()
  assert not follower.update(45 * MPH, True, False, True)
  assert not follower.update(45 * MPH, True, False, True)


def test_a_new_limit_is_adopted_once() -> None:
  follower = LimitFollower()
  follower.update(45 * MPH, True, False, True)
  assert follower.update(35 * MPH, True, False, True)
  assert not follower.update(35 * MPH, True, False, True)   # a MAX the driver sets now stays until the next limit
  assert follower.update(55 * MPH, True, False, True)


def test_a_limit_waiting_for_the_driver_is_adopted_after_they_accept_it() -> None:
  follower = LimitFollower()
  follower.update(45 * MPH, True, False, True)
  assert not follower.update(45 * MPH, True, True, True)    # StarPilot asks about 55; its limit is still 45
  assert follower.update(55 * MPH, True, False, True)       # accepted: the limit is now 55


def test_a_rejected_limit_leaves_max_alone() -> None:
  follower = LimitFollower()
  follower.update(45 * MPH, True, False, True)
  follower.update(45 * MPH, True, True, True)
  assert not follower.update(45 * MPH, True, False, True)


def test_changes_while_disengaged_or_without_a_live_limit_move_nothing() -> None:
  follower = LimitFollower()
  follower.update(45 * MPH, True, False, False)
  assert not follower.update(35 * MPH, True, False, False)  # disengaged: the new limit becomes the baseline
  assert not follower.update(35 * MPH, True, False, True)
  assert not follower.update(None, False, False, True) and not follower.update(25 * MPH, False, False, True)
  assert follower.update(25 * MPH, True, False, True)
