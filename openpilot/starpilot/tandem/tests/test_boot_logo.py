"""Tandem's boot logo (starpilot/tandem/boot_logo.py): written only when it differs, with the system partition restored."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PIL import Image

from openpilot.starpilot.tandem import boot_logo


class Commands:
  """Records commands; cp copies, so a second run sees the logo in place."""

  def __init__(self) -> None:
    self.calls: list[list[str]] = []

  def __call__(self, command: Sequence[str]) -> str | None:
    self.calls.append(list(command))
    if command[:2] == ["sudo", "cp"]:
      Path(command[3]).write_bytes(Path(command[2]).read_bytes())
    return "ro,relatime\n" if command[0] == "findmnt" else ""


def device(tmp_path: Path) -> tuple[Path, Path, Path]:
  comma = tmp_path / "usr/comma"
  comma.mkdir(parents=True)
  Image.new("RGB", (2160, 1080), "gray").save(comma / "bg.png")
  Image.new("RGB", (1080, 2160), "gray").save(comma / "bg.jpg")
  (comma / "magic.py").write_text('BACKGROUND = "/usr/comma/bg.png"\n')
  return comma / "bg.jpg", comma / "bg.png", comma / "magic.py"


def test_comma_logo_is_replaced_and_the_partition_restored(tmp_path: Path) -> None:
  jpeg, png, magic = device(tmp_path)
  commands = Commands()
  assert boot_logo.apply(boot_logo.LOGO, commands, jpeg, png, magic)
  assert commands.calls[1] == ["sudo", "mount", "-o", "remount,rw", "/"]
  assert commands.calls[-1] == ["sudo", "mount", "-o", "remount,ro,relatime", "/"]
  with Image.open(png) as shown, Image.open(boot_logo.LOGO) as logo:
    assert shown.size == (2160, 1080) and shown.convert("RGB").getpixel((1080, 540)) == logo.convert("RGB").getpixel((1080, 540))


def test_nothing_is_written_when_the_logo_is_already_there(tmp_path: Path) -> None:
  jpeg, png, magic = device(tmp_path)
  boot_logo.apply(boot_logo.LOGO, Commands(), jpeg, png, magic)
  again = Commands()
  assert not boot_logo.apply(boot_logo.LOGO, again, jpeg, png, magic) and again.calls == []


def test_a_failed_remount_copies_nothing(tmp_path: Path) -> None:
  jpeg, png, magic = device(tmp_path)
  before = png.read_bytes()
  calls: list[list[str]] = []

  def refuse(command: Sequence[str]) -> str | None:
    calls.append(list(command))
    return "ro\n" if command[0] == "findmnt" else None
  assert not boot_logo.apply(boot_logo.LOGO, refuse, jpeg, png, magic)
  assert png.read_bytes() == before and not any(c[:2] == ["sudo", "cp"] for c in calls)
