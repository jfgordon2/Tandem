"""National source ranges are resumable and never published without their checksum."""
import hashlib
import io

import pytest

from openpilot.starpilot.tandem.routing import config as C
from openpilot.starpilot.tandem.routing.tools import sources


@pytest.fixture
def origin(monkeypatch):
  raw = b"OSM source range fixture" * 100
  calls = []
  class Response(io.BytesIO):
    status = 206
    headers = {}
  def open_(request, **_):
    url = request if isinstance(request, str) else request.full_url
    if url.endswith(".md5"):
      return Response((hashlib.md5(raw, usedforsecurity=False).hexdigest() + " source.pbf").encode())
    if request.get_method() == "HEAD":
      response = Response(b"")
      response.headers = {"Content-Length": str(len(raw))}
      return response
    start, end = map(int, request.get_header("Range")[6:].split("-"))
    calls.append((start, end))
    response = Response(raw[start:end + 1])
    response.headers = {"Content-Range": f"bytes {start}-{end}/{len(raw)}"}
    return response
  monkeypatch.setattr(sources.urllib.request, "urlopen", open_)
  return raw, calls


def test_source_download_preserves_completed_prefix_and_verifies_all_ranges(origin, tmp_path):
  raw, calls = origin
  target = tmp_path / "source.pbf"
  target.with_name(target.name + ".part").write_bytes(raw[:113])
  receipt = sources.fetch("https://example.test/source.pbf", target)
  assert target.read_bytes() == raw and min(start for start, _ in calls) == 113
  assert receipt["sha256"] == hashlib.sha256(raw).hexdigest()
  assert not list(tmp_path.glob("*.range-*"))
  calls.clear()
  assert sources.fetch("https://example.test/source.pbf", target) == receipt and not calls


def test_source_bad_checksum_never_publishes_final_file(origin, tmp_path):
  raw, _ = origin
  target = tmp_path / "source.pbf"
  target.with_name(target.name + ".part").write_bytes(b"x" * 113)
  with pytest.raises(C.RoutingError, match="data_incompatible"):
    sources.fetch("https://example.test/source.pbf", target)
  assert not target.exists()


def test_completed_source_is_not_trusted_after_modification(origin, tmp_path):
  target = tmp_path / "source.pbf"
  sources.fetch("https://example.test/source.pbf", target)
  target.write_bytes(b"corrupt")
  with pytest.raises(C.RoutingError, match="data_incompatible"):
    sources.fetch("https://example.test/source.pbf", target)


def test_checked_dated_source_can_resume_build_when_the_source_host_is_offline(origin, tmp_path, monkeypatch):
  target = tmp_path / "source.pbf"
  expected = sources.fetch("https://example.test/source.pbf", target)
  monkeypatch.setattr(sources.urllib.request, "urlopen", lambda *_a, **_k: pytest.fail("checked source contacted its host"))
  assert sources.fetch("https://example.test/source.pbf", target) == expected
