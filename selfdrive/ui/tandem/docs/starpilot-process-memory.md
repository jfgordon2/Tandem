# starpilot_process memory growth: findings and test plan

November 4, 2026, comma 3X (3.6 GB RAM, no swap), branch `valhalla` at `b334e9f6` on the device.

## What the logs show

Read from the drive logs' `procLog` (every 30 s in qlogs, every 2 s in rlogs) for the day's ten drives, with
`tools/ram_report.py`:

| Drive | Minutes | RAM used, start → peak | starpilot_process, start → end | Growth |
| --- | --- | --- | --- | --- |
| `0000054c` | 7 | 52 → 86% | 107 → 144 MB | |
| `0000054d` | 20 | 68 → 88% | 150 → 218 MB | |
| `0000054e` | 18 | 72 → 92% | 223 → 253 MB | |
| `0000054f` | 12 | 74 → 92% | 285 → 323 MB | +3.2 MB/min |
| `00000550` | 18 | 82 → 95% | 326 → 382 MB | +3.2 MB/min |
| *(process restarted)* | | | | |
| `00000551` | 7 | 49 → 85% | 104 → 140 MB | |
| `00000552` | 12 | 49 → 82% | 96 → 149 MB | |
| `00000553` | 7 | 69 → 84% | 155 → 177 MB | +3.0 MB/min |
| `00000555` | 22 | 68 → 87% | 184 → 258 MB | +3.4 MB/min |

- `starpilot_process` grows about **3 MB per minute of driving** and keeps it between drives: its start time stays the
  same and it barely changes while parked (218 → 223 MB across one stop). Only a restart frees it.
- That carried-over growth is the difference between drives peaking at 82–87% after a restart and staying above 90% for
  minutes before it (the Low Memory event was active for 2 to 5+ minutes on `0000054e`, `0000054f` and `00000550`).
- Above 90%, openpilot refuses to engage and would disengage ("Low Memory: Reboot Your Device"). On these drives every
  Low Memory alert came while it wasn't engaged.
- The other large processes hold steady once started: `modeld` ~294 MB, `dmonitoringmodeld` ~230 MB, `mapd` ~145 MB,
  `loggerd` ~140 MB, `speed_limit_vision` 150–204 MB, `adj_spot_monitor_vision` ~115 MB. Offline routing's `routingd`
  stays at ~65 MB on every drive, and `navigationd` plus Valhalla's worker added ~120 MB on the drive that routed.

`starpilot_process` runs StarPilot's planner and its helpers. Tandem's onroad hook runs inside it too
(`starpilot/controls/starpilot_planner.py` selects the owned cruise subclass that observes navigation turns), so the
leak could be either StarPilot's or Tandem's.

## Test plan

Each step is one drive of at least 20 minutes (growth is clear after 10), parked restart before it, and
`tools/ram_report.py` afterwards. Record the MB/min for `starpilot_process`.

1. **Baseline.** Restart, drive as usual. Expect about +3 MB/min. This also checks the rate doesn't depend on the drive.
2. **Upstream behavior.** Add `export TANDEM_ONROAD=0` to `/data/continue.sh` (device-local, not in the repository),
   reboot, drive, then remove the line and reboot. This turns off Tandem's onroad hooks, including the planner's cruise
   subclass, so `starpilot_process` runs as StarPilot ships it (the drive screen is StarPilot's for that drive).
   - **Still growing:** the leak is StarPilot's. Continue with step 3 on StarPilot's side and report it upstream with
     the numbers.
   - **Flat:** the leak is in Tandem's planner hook. Continue with step 3 on Tandem's side.
3. **Narrow it down.** Two records point at the cause:
   - **Which kind of memory grew:** any drive above 90% saves a Device › RAM snapshot that splits each top process into
     heap, files, shared and device memory, with each kind's growth since a minute into the drive. Report a Problem shows
     it as `starpilot_process 390 MB (+270; heap +265)`. Heap growth is Python objects or a native library's buffers;
     file growth would point at a model or map file being mapped again and again.
   - **Which code allocated it:** switch the device to the `debug` branch, which is `release` plus a memory trace that's
     always on there (it's kept off `release`, since it's a diagnostic). Drive once, then switch back.
     `starpilot/tandem/memory_trace.py` starts Python's
     tracemalloc inside the planner's process, from the Tandem module the planner already imports, and also under
     `TANDEM_ONROAD=0`. Each drive gets a report in `/data/tandem/diagnostics/memory/` (the last ten kept): a line a
     minute with RssAnon, RssFile, RssShmem and the memory Python traced, then the 25 lines whose allocations grew most
     between a minute into the drive and parking, by file and line. If RssAnon grows but the traced lines don't, the leak
     is in a native library (a C extension), not Python. Tracing slows allocation a little and its two snapshots pause the
     process briefly (one at a minute in, one parked), so use it for diagnostic drives only.
   - If step 2 pointed at StarPilot, also try one drive each with its optional planner features off that are on today
     (weather presets, speed limit controller, curve speed control, Smart Slowdowns), to find which one grows.
4. **Fix and confirm.** After a fix, repeat step 1: the rate should be near 0 MB/min, and RAM should peak in the 80s.

Until it's fixed, restarting openpilot between long driving sessions clears it.

## Measuring

On the device, parked, from `/data/openpilot`:

```sh
PYTHONPATH=/data/openpilot:/data nice -n 19 /usr/local/venv/bin/python selfdrive/ui/tandem/tools/ram_report.py \
  --drives 6 starpilot_process speed_limit_vision
```

Sizes there are RSS, so compare a process with itself over time. Device › RAM (after a drive above 90%) ranks processes by
PSS and shows each one's growth since a minute into the drive, so a leaking process stands out there too.

On the `debug` branch, the memory trace's reports are plain text:

```sh
ls -t /data/tandem/diagnostics/memory/ | head -3
cat "/data/tandem/diagnostics/memory/$(ls -t /data/tandem/diagnostics/memory/ | head -1)"
```
