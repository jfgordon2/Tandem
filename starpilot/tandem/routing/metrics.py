"""Small process measurements for the isolated routing trial."""
import resource
import sys
from pathlib import Path


def memory() -> dict:
  result = {"peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 if sys.platform == "darwin" else 1)}
  if sys.platform == "linux":
    try:
      try:
        data = Path("/proc/self/smaps_rollup").read_text()
      except OSError:
        data = Path("/proc/self/smaps").read_text()
      names = {"Rss": "rss_kib", "Pss": "pss_kib", "Anonymous": "anonymous_kib", "Private_Dirty": "private_dirty_kib"}
      for line in data.splitlines():
        key = names.get(line.split(":", 1)[0])
        if key:
          result[key] = result.get(key, 0) + int(line.split()[1])
    except OSError:
      try:
        for line in Path("/proc/self/status").read_text().splitlines():
          if line.startswith("VmRSS:"):
            result["rss_kib"] = int(line.split()[1])
      except OSError:
        pass
  return result
