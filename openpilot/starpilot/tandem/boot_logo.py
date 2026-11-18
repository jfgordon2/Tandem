"""Tandem's logo on the comma's boot screen, put back after every AGNOS update.

AGNOS shows /usr/comma/bg.png while the device starts (its magic.py; older AGNOS used bg.jpg), on the read-only system
partition, and each AGNOS update rewrites it with comma's. StarPilot 6 replaced it on every start; StarPilot 7 doesn't, so
Tandem does, the same way: when the UI starts, compare the images with Tandem's logo and, only if they differ, remount
the system partition read-write, copy them in, and restore its mount options. Nothing is written when they match.
"""
from __future__ import annotations

import subprocess
import tempfile
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

LOGO = Path(__file__).resolve().parents[2] / "selfdrive/ui/tandem/assets/boot_logo.jpg"
JPEG = Path("/usr/comma/bg.jpg")
PNG = Path("/usr/comma/bg.png")
MAGIC = Path("/usr/comma/magic.py")

Run = Callable[[Sequence[str]], str | None]


def run(command: Sequence[str]) -> str | None:
  """A command's output, or None when it fails."""
  try:
    return subprocess.run(list(command), check=True, capture_output=True, text=True, timeout=30).stdout
  except (OSError, subprocess.SubprocessError):
    return None


def staged(logo: Path, folder: Path, jpeg: Path = JPEG, png: Path = PNG, magic: Path = MAGIC) -> list[tuple[Path, Path]]:
  """The boot images made from logo in folder, paired with where they go, for the ones that differ from what's there.

  As StarPilot 6: the PNG is landscape; the JPEG is landscape when AGNOS's boot script reads it, otherwise turned for the
  display compositor. The PNG is only written where AGNOS has one.
  """
  from PIL import Image
  with Image.open(logo) as image:
    picture = image.convert("RGB")
  landscape = picture if picture.width >= picture.height else picture.transpose(Image.Transpose.ROTATE_90)
  portrait = landscape.transpose(Image.Transpose.ROTATE_270)
  try:
    jpeg_read = jpeg.as_posix() in magic.read_text()
  except OSError:
    jpeg_read = False
  staged_jpeg, staged_png = folder / "bg.jpg", folder / "bg.png"
  (landscape if jpeg_read else portrait).save(staged_jpeg, format="JPEG", quality=95)
  landscape.save(staged_png, format="PNG")
  pairs = [(staged_jpeg, jpeg)] + ([(staged_png, png)] if png.is_file() else [])
  return [(source, target) for source, target in pairs if not target.is_file() or target.read_bytes() != source.read_bytes()]


def apply(logo: Path = LOGO, command: Run = run, jpeg: Path = JPEG, png: Path = PNG, magic: Path = MAGIC) -> bool:
  """Put logo on the boot screen if it isn't there; True when the images were replaced."""
  if not logo.is_file():
    return False
  with tempfile.TemporaryDirectory(prefix="tandem_boot_logo_") as folder:
    pending = staged(logo, Path(folder), jpeg, png, magic)
    if not pending:
      return False
    options = command(["findmnt", "-n", "-o", "OPTIONS", "/"])
    if options is None or command(["sudo", "mount", "-o", "remount,rw", "/"]) is None:
      return False
    try:
      return all(command(["sudo", "cp", str(source), str(target)]) is not None for source, target in pending)
    finally:
      command(["sudo", "mount", "-o", f"remount,{options.strip()}", "/"])


def apply_in_background() -> None:
  """apply() off the UI thread, on the comma only; a failure leaves comma's logo."""
  from openpilot.common.hardware import HARDWARE
  if HARDWARE.get_device_type() == "pc":
    return

  def work() -> None:
    try:
      apply()
    except Exception:
      from openpilot.common.swaglog import cloudlog
      cloudlog.exception("Tandem: boot logo not applied")
  threading.Thread(target=work, name="tandem-boot-logo", daemon=True).start()
