"""Benchmark the local broker with public coordinate pairs; never writes navigation Params."""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import platform
import statistics
import hashlib
import shutil
import subprocess
import sys
import time

from openpilot.starpilot.tandem.routing import client, config as C
from openpilot.starpilot.tandem.routing.bundles import active
from openpilot.starpilot.tandem.routing.normalize import normalize

SAMPLES = {
  "liechtenstein": [(47.13975, 9.52188, 47.16650, 9.51030), (47.13975, 9.52188, 47.0712, 9.5070)],
  "iowa": [(41.5868, -93.6250, 41.6016, -93.6091), (41.5868, -93.6250, 41.7318, -93.6001),
           (41.7318, -93.6001, 42.0308, -93.6319), (41.5868, -93.6250, 41.9779, -91.6656),
           (41.7400, -93.5900, 42.0308, -93.6319)],
}


def environment():
  result = {"free_bytes": shutil.disk_usage(C.root()).free}
  try:
    result["memory"] = {line.split(":")[0]: line.split(":")[1].strip() for line in Path("/proc/meminfo").read_text().splitlines()
                        if line.startswith(("MemTotal:", "MemAvailable:", "Cached:", "SwapFree:"))}
  except (OSError, ValueError):
    pass
  temperatures = {}
  for path in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
    try:
      temperatures[path.parent.name] = int(path.read_text())
    except (OSError, ValueError):
      continue
  result["thermal_millicelsius"] = temperatures
  return result


def benchmark(region: str, repeats: int) -> dict:
  before = environment()
  results = []
  for index, (lat, lon, end_lat, end_lon) in enumerate(SAMPLES[region]):
    for repetition in range(repeats):
      started = time.monotonic()
      response = client.request("route", caller="benchmark", bundle=active().id, generation=active().generation, start=[lat, lon, None],
                                destination={"name": "Public benchmark", "latitude": end_lat, "longitude": end_lon}, language="en")
      elapsed = time.monotonic() - started
      item = {"sample": index, "repetition": repetition, "seconds": elapsed, "status": response["status"],
              "network_isolation": response.get("network_isolation")}
      item["worker_peak_rss_kib"] = response.get("worker_peak_rss_kib")
      item["worker_cpu_seconds"] = response.get("worker_cpu_seconds")
      item["broker_peak_rss_kib"] = response.get("broker_peak_rss_kib")
      for owner in ("worker", "broker"):
        for kind in ("rss_kib", "pss_kib"):
          item[f"{owner}_{kind}"] = response.get(f"{owner}_{kind}")
      if response["status"] == "ok":
        route = normalize(response["route"])
        item.update(meters=route["totalDistance"], duration=route["totalDuration"], steps=len(route["steps"]),
                    speed_slots=len(route["maxspeed"]), lanes=sum(len((b.get("sub") or {}).get("components", []))
                      for step in route["steps"] for b in step["bannerInstructions"]))
        if not results:
          C.atomic_json(C.root() / "benchmarks" / f"{region}-sample-route.json", response["route"])
      results.append(item)
      print(json.dumps(item), flush=True)
  warm = sorted(r["seconds"] for r in results if r["status"] == "ok" and r["repetition"] > 0)
  lat, lon, end_lat, end_lon = SAMPLES[region][0]
  probes = []
  for label, start, end, expected in (
      ("outside_coverage", [lat, lon, None], [0, 0], "outside_coverage"),
      ("invalid_coordinate", [91, lon, None], [end_lat, end_lon], "invalid_request"),
      ("recovery", [lat, lon, None], [end_lat, end_lon], "ok")):
    started = time.monotonic()
    response = client.request("route", caller="benchmark", bundle=active().id, generation=active().generation, start=start,
                              destination={"latitude": end[0], "longitude": end[1]}, language="en")
    probes.append({"case": label, "expected": expected, "status": response["status"], "seconds": time.monotonic() - started})
  return {"schema": 1, "region": region, "time": datetime.datetime.now(datetime.UTC).isoformat(),
          "platform": platform.platform(), "version": C.VERSION, "generation": active().generation,
          "environment_before": before, "environment_after": environment(),
          "source_sha256": {str(p.relative_to(Path(__file__).parents[1])): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted(Path(__file__).parents[1].rglob("*.py"))},
          "cache_note": "First request includes native process startup; filesystem cache was not flushed.",
          "results": results, "probes": probes, "warm_median": statistics.median(warm) if warm else None,
          "warm_p95": warm[min(len(warm) - 1, int(len(warm) * .95))] if warm else None}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--region", choices=SAMPLES, required=True)
  parser.add_argument("--repeats", type=int, default=10)
  parser.add_argument("--out", type=Path, required=True)
  parser.add_argument("--standalone", action="store_true", help="supervise a broker for this trial and stop it afterward")
  args = parser.parse_args()
  C.require_parked()
  process = None
  try:
    if args.standalone:
      if C.socket_path().exists():
        raise C.RoutingError("busy")
      process = subprocess.Popen([sys.executable, "-m", "openpilot.starpilot.tandem.routing.routingd"])
      for _ in range(100):
        if C.socket_path().exists():
          break
        if process.poll() is not None:
          raise C.RoutingError("worker_failed")
        time.sleep(.05)
    result = benchmark(args.region, args.repeats)
  finally:
    if process is not None:
      process.terminate()
      try:
        process.wait(timeout=C.DEADLINE + 3)
      except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
  C.atomic_json(args.out, result)
  if any(item["status"] != "ok" for item in result["results"]) or any(p["status"] != p["expected"] for p in result["probes"]):
    raise SystemExit(1)


if __name__ == "__main__":
  main()
