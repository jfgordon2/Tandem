import datetime
import json

from openpilot.selfdrive.ui.tandem.ram import RamLog, Snapshot, process_name, report_text
from openpilot.selfdrive.ui.tandem.onroad.status import RamWatch, Snapshot as Status, chips_for

MB = 2**20
PROCS = [("modeld", 1300 * MB), ("ui", 620 * MB), ("selfdrived", 410 * MB), ("mapd", 290 * MB), ("locationd", 240 * MB), ("camerad", 90 * MB)]


def _log(tmp_path, clock=None):
  reads = []

  def read():
    reads.append(1)
    return PROCS, 7300 * MB
  times = iter(range(1000, 2000)) if clock is None else clock
  return RamLog(tmp_path / ".tandem_ram.json", read, lambda: float(next(times)), background=False), reads


def test_low_ram_chip_holds_until_85_percent():
  watch = RamWatch()
  assert watch.update(True, 91)                  # StarPilot raises Low Memory above 90%
  assert watch.update(False, 89)                 # its alert drops while RAM hovers: the chip stays
  assert watch.update(False, 86)
  assert not watch.update(False, 85)             # down to 85%: gone
  assert not watch.update(False, 88)             # and doesn't come back until StarPilot raises it again
  assert [c.key for c in chips_for(Status(low_ram=True, memory_percent=88))] == ["low_memory"]


def test_one_snapshot_per_drive_at_its_peak(tmp_path):
  log, reads = _log(tmp_path)
  log.note(drive=1, percent=91)
  for _ in range(50):                            # the chip shows every frame: no new capture at the same reading
    log.note(drive=1, percent=91)
  log.note(drive=1, percent=90)
  assert len(reads) == 1
  log.note(drive=1, percent=93)                  # a new peak replaces the drive's snapshot
  assert len(reads) == 2
  assert [(s.percent, s.drive) for s in log.snapshots()] == [(93, 1)]
  top = log.snapshots()[0]
  assert [n for n, _ in top.top] == ["modeld", "ui", "selfdrived", "mapd", "locationd"]
  assert top.rest == 7300 * MB - sum(b for _, b in PROCS[:5])


def test_keeps_the_last_three_drives_newest_first_and_survives_a_restart(tmp_path):
  log, _ = _log(tmp_path)
  for drive, percent in [(1, 91), (2, 92), (3, 93), (4, 94)]:
    log.note(drive, percent)
  assert [s.drive for s in log.snapshots()] == [4, 3, 2]
  again = RamLog(tmp_path / ".tandem_ram.json")
  assert [s.percent for s in again.snapshots()] == [94, 93, 92]


def test_new_snapshot_is_unseen_until_the_panel_opens(tmp_path):
  log, _ = _log(tmp_path)
  assert not log.unseen()
  log.note(1, 91)
  assert log.unseen()
  log.mark_seen()
  assert not log.unseen() and not json.loads((tmp_path / ".tandem_ram.json").read_text())["unseen"]


def test_a_failed_read_records_nothing(tmp_path):
  def read():
    raise OSError("no /proc")
  log = RamLog(tmp_path / ".tandem_ram.json", read, background=False)
  log.note(1, 91)
  assert log.snapshots() == [] and not log.unseen()


def test_process_names_as_a_device_shows_them():
  # Command lines read from a comma device running Tandem
  assert process_name("selfdrive.pandad.pandad", ["selfdrive.pandad.pandad"]) == "pandad"           # titled by manager
  assert process_name("system.timed", ["system.timed", ""]) == "timed"
  assert process_name("starpilot.system.bluetooth.daemon", ["starpilot.system.bluetooth.daemon"]) == "bluetooth.daemon"
  assert process_name("/usr/local/venv", ["/usr/local/venv/bin/python3", "-m", "openpilot.selfdrive.ui.ui"]) == "ui"
  assert process_name("python", ["python", "-m", "system.athena.manage_athenad"]) == "manage_athenad"
  assert process_name("python3", ["python3", "./manager.py"]) == "manager"
  assert process_name("python", ["/usr/local/venv/bin/python", "-u", "/usr/comma/magic.py"]) == "magic"
  assert process_name("python", ["/usr/local/venv/bin/python", "-"]) == "python"                    # a script on stdin
  assert process_name("kworker", []) == "kworker"


def test_report_lists_each_drive_for_the_developers():
  snap = Snapshot(datetime.datetime(2026, 11, 3, 16, 12).timestamp(), 92, [("modeld", 1300 * MB), ("ui", 620 * MB)], 4500 * MB, 1)
  assert report_text([snap]) == "Low on RAM 2026-11-03 16:12 92%: modeld 1300 MB, ui 620 MB, rest 4500 MB"


def test_report_sends_the_ram_snapshots(tmp_path):
  from openpilot.selfdrive.ui.tandem.settings.device_sections import REPORT_CATEGORIES, Report
  from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeData
  from openpilot.selfdrive.ui.tandem.tests.test_settings import FakeCache
  log, _ = _log(tmp_path)
  data = FakeData()
  report = Report(data, SettingsStore(FakeCache(), lambda: None), log)
  report.category = 0
  report.send()
  assert data.reports[-1][0] == REPORT_CATEGORIES[0]          # nothing to add yet
  log.note(1, 91)
  report.send()
  assert data.reports[-1][0].startswith(REPORT_CATEGORIES[0] + "\nLow on RAM ") and "modeld 1300 MB" in data.reports[-1][0]


def test_drive_labels_say_today_yesterday_or_the_date():
  from openpilot.selfdrive.ui.tandem.settings.ram import drive_label, size_text
  now = datetime.datetime(2026, 11, 3, 18, 0)
  at = lambda *a: Snapshot(datetime.datetime(*a).timestamp(), 92)  # noqa: E731
  assert drive_label(at(2026, 11, 3, 16, 12), now) == "Today 4:12 PM · 92%"
  assert drive_label(at(2026, 11, 2, 8, 40), now) == "Yesterday 8:40 AM · 92%"
  assert drive_label(at(2026, 10, 30, 9, 0), now) == "Oct 30 · 92%"
  assert (size_text(1300 * MB), size_text(620 * MB)) == ("1.3 GB", "620 MB")


def test_device_tab_has_ram_with_a_dot_until_opened(tmp_path):
  from openpilot.selfdrive.ui.tandem.tests.test_settings import _search_window
  from openpilot.selfdrive.ui.tandem.settings.window import Tab
  log, _ = _log(tmp_path)
  log.note(1, 92)
  window = _search_window()
  window.ram_log, window.ram_now = (lambda: log), (lambda: 54)
  window.show_event()
  window.select_tab(Tab.DEVICE)
  page = window.top
  ram = [i for i, s in enumerate(page._sections) if s.label == "RAM"][0]
  assert [s.label for s in page._sections][ram - 1:ram + 2] == ["Storage & Data", "RAM", "Report a Problem"]
  assert page._sidebar._items[ram].dot()
  page.select(ram)
  assert not page._sidebar._items[ram].dot()


def test_ram_is_hidden_until_a_drive_runs_low(tmp_path):
  from openpilot.selfdrive.ui.tandem.tests.test_settings import _search_window
  from openpilot.selfdrive.ui.tandem.base import resolve
  from openpilot.selfdrive.ui.tandem.settings.window import Tab
  log, _ = _log(tmp_path)
  window = _search_window()
  window.ram_log = lambda: log
  window.show_event()
  window.select_tab(Tab.DEVICE)
  ram = [s for s in window.top._sections if s.label == "RAM"][0]
  assert not resolve(ram.visible)
  log.note(1, 91)
  assert resolve(ram.visible)


def test_search_finds_ram_only_once_it_shows_and_report_without_tuner_mode():
  from openpilot.selfdrive.ui.tandem.settings.search import search
  assert "RAM" not in [e.name for e in search("ram", tuner=True)]
  assert search("ram", tuner=False, ram=True)[0].name == "RAM"
  assert search("report a problem", tuner=False)[0].name == "Report a Problem"   # not a Tuner Mode screen
  assert "SSH" not in [e.name for e in search("ssh", tuner=False)]               # Developer is
  assert "SSH" in [e.name for e in search("ssh", tuner=True)]


def test_growth_is_measured_from_a_baseline_a_minute_into_the_drive(tmp_path):
  sizes = {"starpilot_process": 100 * MB, "modeld": 300 * MB}

  def read():
    return sorted(sizes.items(), key=lambda kv: -kv[1]), 3000 * MB
  log = RamLog(tmp_path / ".tandem_ram.json", read, lambda: 1000.0, background=False)
  log.drive(7, now=10.0)
  log.drive(7, now=69.0)                        # not a minute yet
  sizes["starpilot_process"] = 120 * MB         # still settling in: not counted as growth
  log.drive(7, now=70.0)                        # baseline taken here
  sizes["starpilot_process"] = 390 * MB         # then it leaks
  log.note(7, 95)
  snap = log.snapshots()[0]
  assert snap.grew == {"starpilot_process": 270 * MB, "modeld": 0}
  assert "starpilot_process 390 MB (+270)" in report_text([snap])


def test_a_new_drive_waits_for_its_own_baseline(tmp_path):
  log, _ = _log(tmp_path)
  log.drive(1, now=0.0)
  log.drive(1, now=61.0)
  log.drive(2, now=100.0)                       # the next drive starts: the old baseline doesn't apply
  log.note(2, 91)
  assert log.snapshots()[0].grew == {}


def test_snapshots_saved_before_growth_still_load(tmp_path):
  path = tmp_path / ".tandem_ram.json"
  path.write_text(json.dumps({"drives": [{"when": 1.0, "percent": 92, "top": [["modeld", 300 * MB]], "rest": 0, "drive": 1}]}))
  assert RamLog(path).snapshots()[0].grew == {}


def test_pss_sums_a_processes_share_of_each_mapping():
  from openpilot.selfdrive.ui.tandem.ram import pss_of
  smaps = (b"7f00-7f10 r-xp 00000000 08:01 1 /lib/libc.so\nRss:   400 kB\nPss:   100 kB\nShared_Clean: 300 kB\n" +
           b"7f20-7f30 rw-p 00000000 00:00 0\nRss:   50 kB\nPss:   50 kB\n")
  assert pss_of(smaps) == 150 * 1024


def test_growth_reads_as_a_signed_size():
  from openpilot.selfdrive.ui.tandem.settings.ram import growth_text
  assert (growth_text(270 * MB), growth_text(-3 * MB), growth_text(0)) == ("+270 MB", "-3 MB", "+0 MB")
