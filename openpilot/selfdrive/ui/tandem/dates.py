"""Dates and clock times in the driver's language: "Nov 24" and "3:05 PM" in English, "24. Nov." and "15:05" in German.

strftime's %b and %p are the C locale's English on the device, so Tandem's screens build them from marked text instead:
translated month names, a date template each language orders as it writes dates (numbered holes, i18n.py), and a
12- or 24-hour clock that each catalog chooses.
"""
from __future__ import annotations

import datetime

from openpilot.selfdrive.ui.tandem.i18n import N_, t_, translate

MONTHS = [N_("Jan", context="month"), N_("Feb", context="month"), N_("Mar", context="month"), N_("Apr", context="month"),
          N_("May", context="month"), N_("Jun", context="month"), N_("Jul", context="month"), N_("Aug", context="month"),
          N_("Sep", context="month"), N_("Oct", context="month"), N_("Nov", context="month"), N_("Dec", context="month")]
# A language's catalog translates this as exactly "24-hour" when it writes times on a 24-hour clock.
CLOCK = N_("12-hour", context="clock: 24-hour for a 24-hour clock")
AM, PM = N_("AM", context="clock"), N_("PM", context="clock")


def short_date(at: datetime.datetime) -> str:
  """A month and day: "Nov 24".

  Args:
    at: The date.
  """
  return t_("{} {}", translate(MONTHS[at.month - 1]), at.day, context="date: month, day")


def long_date(at: datetime.datetime) -> str:
  """A month, day and year: "Nov 24, 2026".

  Args:
    at: The date.
  """
  return t_("{} {}, {}", translate(MONTHS[at.month - 1]), at.day, at.year, context="date: month, day, year")


def clock(at: datetime.datetime) -> str:
  """A time of day: "3:05 PM", or "15:05" in a language that uses a 24-hour clock.

  Args:
    at: The time.
  """
  if translate(CLOCK) == "24-hour":
    return f"{at.hour}:{at.minute:02d}"
  hour = at.hour % 12 or 12
  return f"{hour}:{at.minute:02d} {translate(AM if at.hour < 12 else PM)}"
