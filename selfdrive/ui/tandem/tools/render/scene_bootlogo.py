"""Compare the shipped boot JPEG with its HTML mock; the boot loader displays this asset directly."""
from pathlib import Path

from PIL import Image


def main(out, **_):
  source = Path(__file__).resolve().parents[2] / "assets" / "boot_logo.jpg"
  with Image.open(source) as logo:
    logo.convert("RGB").save(Path(out) / "bootlogo.png")
