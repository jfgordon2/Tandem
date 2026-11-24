"""Dates and clock times in the driver's language (dates.py): month names, date order and a 12- or 24-hour clock."""
from __future__ import annotations

import datetime

import pytest

from openpilot.selfdrive.ui.tandem import i18n
from openpilot.selfdrive.ui.tandem.dates import clock, long_date, short_date
from openpilot.selfdrive.ui.tandem.settings.auto_learn import last_change

AFTERNOON = datetime.datetime(2026, 11, 24, 15, 5)
MORNING = datetime.datetime(2026, 5, 3, 9, 30)


@pytest.mark.parametrize("language,day,with_year,afternoon,morning", [
  ("en", "Nov 24", "Nov 24, 2026", "3:05 PM", "9:30 AM"),
  ("de", "24. Nov.", "24. Nov. 2026", "15:05", "9:30"),
  ("es", "24 nov", "24 nov 2026", "15:05", "9:30"),
  ("ja", "11月24日", "2026年11月24日", "15:05", "9:30"),
  ("ko", "11월 24일", "2026년 11월 24일", "15:05", "9:30"),
  ("ar", "24 نوفمبر", "24 نوفمبر 2026", "3:05 م", "9:30 ص"),
])
def test_each_language_writes_dates_and_times_its_own_way(monkeypatch: pytest.MonkeyPatch, language: str, day: str, with_year: str,
                                                          afternoon: str, morning: str) -> None:
  monkeypatch.setattr(i18n, "_language", lambda: f"main_{language}")
  assert short_date(AFTERNOON) == day and long_date(AFTERNOON) == with_year
  assert clock(AFTERNOON) == afternoon and clock(MORNING) == morning


def test_every_month_has_a_name_and_noon_and_midnight_read_right(monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setattr(i18n, "_language", lambda: "main_en")
  assert [short_date(datetime.datetime(2026, m, 1)) for m in (1, 5, 12)] == ["Jan 1", "May 1", "Dec 1"]
  assert clock(datetime.datetime(2026, 1, 1, 0, 0)) == "12:00 AM" and clock(datetime.datetime(2026, 1, 1, 12, 0)) == "12:00 PM"


def test_auto_learns_last_change_is_in_the_drivers_language(monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setattr(i18n, "_language", lambda: "main_de")
  saved = {"savedHistory": {"profiles": [{"completedAt": int(AFTERNOON.timestamp() * 1000), "state": "ready_for_next_drive"}]}}
  assert last_change(saved) == "Letzte Änderung 24. Nov."
