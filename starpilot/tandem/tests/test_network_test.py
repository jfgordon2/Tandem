"""The network test must measure what the connection does, within the data and time it's given, and stop when told."""
import pytest

from openpilot.starpilot.tandem import network_test as N

MBPS = 1e6


class FakeLink:
  """A connection with set speeds, on a clock that moves only as bytes do."""

  def __init__(self, clock, down=100 * MBPS, up=20 * MBPS, pings=(0.031, 0.024, 0.040, 0.026, 0.025), on_chunk=lambda: None):
    self.clock, self.down, self.up, self.pings, self.on_chunk = clock, down, up, list(pings), on_chunk
    self.downloads, self.uploads, self.closed = [], [], False

  def _move(self, size, speed, until, moved):
    got, seconds = 0, 0.0
    while got < size:
      if self.clock[0] >= until:
        return got, seconds, False
      count = min(50_000, size - got)
      self.clock[0] += count * 8 / speed
      seconds += count * 8 / speed
      got += count
      self.on_chunk()
      moved(count, seconds)
    return got, seconds, True

  def download(self, size, until, moved):
    step, count = N.download_requests(size)
    self.downloads.append(step * count)
    return N.Sample(*self._move(step * count, self.down, until, moved))

  def upload(self, size, until, moved):
    self.uploads.append(size)
    got, seconds, whole = self._move(size, self.up, until, moved)
    return N.Sample(got, seconds) if whole else N.Sample(0, 0.0, whole=False)

  def ping(self):
    return self.pings.pop(0)

  def close(self):
    self.closed = True


def finished(budget=N.UNMETERED, **link):
  clock = [100.0]
  made = []

  def connect():
    made.append(FakeLink(clock, **link))
    return made[0]

  test = N.NetworkTest(connect, clock=lambda: clock[0], now=lambda: 1_700_000_000.0, spawn=lambda work: work())
  test.start(budget)
  return test, made[0] if made else None


def test_a_fast_connection_is_measured_at_its_speed_within_the_budget():
  test, link = finished(down=400 * MBPS, up=40 * MBPS)
  result = test.result()
  assert result.phase is N.Phase.DONE and result.problem is None and result.finished == 1_700_000_000.0
  assert result.download == pytest.approx(400 * MBPS) and result.upload == pytest.approx(40 * MBPS)
  assert result.ping == 0.024                                        # the quickest of five
  assert sum(link.downloads) <= N.UNMETERED.download and sum(link.uploads) <= N.UNMETERED.upload
  assert result.used == sum(link.downloads) + sum(link.uploads)
  assert link.downloads[-1] * 8 / (400 * MBPS) >= N.ENOUGH_SECONDS   # the answer came from a round long enough to trust
  assert link.closed


def test_a_slow_connection_moves_little_data():
  test, link = finished(down=1 * MBPS, up=0.5 * MBPS)
  result = test.result()
  assert result.phase is N.Phase.DONE
  assert link.downloads == [N.FIRST_DOWNLOAD] and link.uploads == [N.FIRST_UPLOAD]   # the first rounds already ran long enough
  assert result.used == N.FIRST_DOWNLOAD + N.FIRST_UPLOAD
  assert result.download == pytest.approx(1 * MBPS) and result.upload == pytest.approx(0.5 * MBPS)


def test_a_metered_connection_stays_inside_its_smaller_budget():
  test, link = finished(N.METERED, down=300 * MBPS, up=100 * MBPS)
  result = test.result()
  assert result.phase is N.Phase.DONE and result.budget is N.METERED
  assert sum(link.downloads) <= N.METERED.download and sum(link.uploads) <= N.METERED.upload
  assert result.used <= N.METERED.total
  assert result.download == pytest.approx(300 * MBPS) and result.upload == pytest.approx(100 * MBPS)
  assert link.downloads[-1] == max(link.downloads) and link.uploads[-1] == max(link.uploads)   # never ends on a scrap of budget


def test_a_download_too_slow_to_finish_is_cut_and_still_measured():
  test, _ = finished(down=0.1 * MBPS, up=0.5 * MBPS)
  result = test.result()
  assert result.phase is N.Phase.DONE
  assert result.download == pytest.approx(0.1 * MBPS, rel=0.05)
  assert result.used < N.FIRST_DOWNLOAD + N.FIRST_UPLOAD + 1


def test_an_upload_that_never_arrives_fails_and_keeps_the_download():
  test, link = finished(down=5 * MBPS, up=0.01 * MBPS)
  result = test.result()
  assert result.phase is N.Phase.FAILED and result.problem is N.Problem.DROPPED
  assert result.download == pytest.approx(5 * MBPS) and result.upload is None and result.ping is None
  assert link.closed


@pytest.mark.parametrize("error,problem", [
  (OSError("no route"), N.Problem.UNREACHABLE),
  (TimeoutError("stalled"), N.Problem.UNREACHABLE),
  (N.Refused("403"), N.Problem.REFUSED),
])
def test_a_test_that_cannot_start_says_why(error, problem):
  def connect():
    raise error
  test = N.NetworkTest(connect, spawn=lambda work: work())
  test.start(N.UNMETERED)
  result = test.result()
  assert result.phase is N.Phase.FAILED and result.problem is problem and result.used == 0 and not result.running


def test_a_connection_lost_midway_is_dropped_not_unreachable():
  count = [0]

  def on_chunk():
    count[0] += 1
    if count[0] == 20:
      raise ConnectionResetError

  test, link = finished(on_chunk=on_chunk)
  result = test.result()
  assert result.phase is N.Phase.FAILED and result.problem is N.Problem.DROPPED and result.used > 0 and link.closed


def test_stop_ends_the_test_and_keeps_what_it_measured():
  box = {}
  count = [0]

  def on_chunk():
    count[0] += 1
    if box["link"].uploads and "stopped" not in box:
      box["stopped"] = True
      box["test"].stop()

  clock = [0.0]

  def connect():
    box["link"] = FakeLink(clock, on_chunk=on_chunk)
    return box["link"]

  box["test"] = test = N.NetworkTest(connect, clock=lambda: clock[0], spawn=lambda work: work())
  test.start(N.UNMETERED)
  result, chunks = test.result(), count[0]
  assert result.phase is N.Phase.STOPPED and not result.running
  assert result.download == pytest.approx(100 * MBPS) and result.upload is None
  assert box["link"].closed and len(box["link"].uploads) == 1 and count[0] == chunks   # nothing moved after the stop
  test.stop()                                                                          # stopping twice changes nothing
  assert test.result() == result


def test_a_stopped_test_cannot_write_over_the_next_one():
  held = []
  test = N.NetworkTest(lambda: FakeLink([0.0]), spawn=held.append)
  test.start(N.METERED)
  test.start(N.UNMETERED)                 # already running: no second test
  assert len(held) == 1 and test.result().budget is N.METERED
  test.stop()
  test.start(N.UNMETERED)
  held[0]()                               # the stopped test's work runs late
  assert test.result() == N.Result(N.Phase.DOWNLOAD, budget=N.UNMETERED)
  held[1]()
  assert test.result().phase is N.Phase.DONE


def test_the_running_download_speed_shows_before_the_round_ends():
  seen = []
  box = {}
  clock = [0.0]

  def connect():
    box["link"] = FakeLink(clock, down=8 * MBPS, on_chunk=lambda: seen.append(box["test"].result().download))
    return box["link"]

  box["test"] = N.NetworkTest(connect, clock=lambda: clock[0], spawn=lambda work: work())
  box["test"].start(N.UNMETERED)
  first = len(box["link"].downloads) and N.FIRST_DOWNLOAD // 50_000
  assert seen[0] is None and seen[first + 1] is None                    # nothing in a round's first moments
  assert pytest.approx(8 * MBPS) in [s for s in seen if s is not None]  # then the speed so far


@pytest.mark.parametrize("size,expected", [
  (50_000, (100_000, 1)), (200_000, (100_000, 2)), (999_999, (100_000, 9)), (4_700_000, (1_000_000, 4)),
  (15_000_000, (10_000_000, 1)), (24_999_999, (10_000_000, 2)), (37_500_000, (25_000_000, 1)), (209_715_200, (25_000_000, 8)),
])
def test_downloads_ask_only_for_sizes_cloudflare_accepts(size, expected):
  assert N.download_requests(size) == expected


class FakeHttp:
  """http.client's connection, recording what was asked and answering with a status and a body of zeros."""

  def __init__(self, status=200):
    self.status, self.asked, self.sent, self.closed, self.sock = status, [], 0, 0, None
    self.left = 0

  def connect(self):
    self.sock = FakeSocket()

  def request(self, method, path, headers):
    self.asked.append((method, path, dict(headers)))
    self.left = int(path.split("=")[1])

  def putrequest(self, method, path):
    self.asked.append((method, path, {}))

  def putheader(self, name, value):
    self.asked[-1][2][name] = value

  def endheaders(self):
    pass

  def send(self, data):
    self.sent += len(data)

  def getresponse(self):
    return self

  def readinto(self, buffer):
    count = min(len(buffer), self.left)
    self.left -= count
    return count

  def read(self):
    return b""

  def close(self):
    self.closed += 1
    self.sock = None


class FakeSocket:
  family = 2

  def getpeername(self):
    return ("192.0.2.1", 443)


def cloudflare(status=200):
  clock = [0.0]

  def tick():
    clock[0] += 0.001
    return clock[0]

  link = N.Cloudflare(clock=tick)
  link._http = FakeHttp(status)
  return link, link._http


def test_cloudflare_download_asks_for_whole_requests_and_counts_what_arrived():
  link, http = cloudflare()
  moved = []
  sample = link.download(2_500_000, 1e9, lambda count, seconds: moved.append(count))
  assert [(m, p) for m, p, _ in http.asked] == [("GET", "/__down?bytes=1000000")] * 2
  assert http.asked[0][2] == {"User-Agent": "Tandem"}
  assert sample == N.Sample(2_000_000, pytest.approx(sample.seconds)) and sample.whole and sum(moved) == 2_000_000
  assert link._peer == (2, ("192.0.2.1", 443))                          # ping goes to the server the transfers used


def test_cloudflare_download_cut_short_reports_what_arrived_and_drops_the_connection():
  link, http = cloudflare()
  sample = link.download(1_000_000, 0.01, lambda count, seconds: None)
  assert not sample.whole and 0 < sample.size < 1_000_000 and http.closed == 1


def test_cloudflare_upload_sends_the_body_and_waits_for_the_answer():
  link, http = cloudflare()
  sample = link.upload(300_000, 1e9, lambda count, seconds: None)
  assert http.asked == [("POST", "/__up", {"User-Agent": "Tandem", "Content-Type": "application/octet-stream", "Content-Length": "300000"})]
  assert http.sent == 300_000 and sample.size == 300_000 and sample.whole and sample.seconds > 0


def test_cloudflare_upload_cut_short_measures_nothing():
  link, http = cloudflare()
  assert link.upload(5_000_000, 0.05, lambda count, seconds: None) == N.Sample(0, 0.0, whole=False)
  assert http.closed == 1


def test_cloudflare_refusal_is_its_own_error_and_leaves_the_connection_usable():
  link, http = cloudflare(status=403)
  with pytest.raises(N.Refused):
    link.download(1_000_000, 1e9, lambda count, seconds: None)
  assert http.closed == 1
