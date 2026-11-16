#!/usr/bin/env python3
"""Builds a side-by-side page of each mock and the built screen (design/compare.json lists them, with notes).

  python3 tools/compare.py <renders dir> <out dir>

<renders dir> holds the built screens from tools/render (scene_compare.py). Each entry's mock screenshot comes from
design/screenshots/<mock>.png; its render is <built>.png (default: the mock's name), or several stacked when "built" is a
list. Writes <out dir>/index.html and <out dir>/img/, a self-contained folder to open in a browser or publish.
"""
import html
import json
import sys
from pathlib import Path

from PIL import Image

DESIGN = Path(__file__).resolve().parents[1] / "design"
WIDTH = 1125   # the mocks' width; renders (2160 wide) are scaled to it


def scaled(image: Image.Image) -> Image.Image:
  return image.convert("RGB").resize((WIDTH, round(image.height * WIDTH / image.width)), Image.LANCZOS)


def built_image(renders: Path, built) -> Image.Image | None:
  names = built if isinstance(built, list) else [built]
  paths = [renders / f"{n}.png" for n in names]
  if not all(p.exists() for p in paths):
    return None
  parts = [scaled(Image.open(p)) for p in paths]
  out = Image.new("RGB", (WIDTH, sum(p.height for p in parts) + 16 * (len(parts) - 1)), (11, 13, 16))
  y = 0
  for part in parts:
    out.paste(part, (0, y))
    y += part.height + 16
  return out


def main(renders: Path, out: Path, prefix: str = "") -> None:
  entries = json.loads((DESIGN / "compare.json").read_text())["entries"]
  entries = [e for e in entries if e["mock"].startswith(prefix)]
  (out / "img").mkdir(parents=True, exist_ok=True)
  articles, missing = [], []
  for e in entries:
    key = e["mock"]
    shots = []
    mock = DESIGN / "screenshots" / f"{key}.png"
    if mock.exists():
      scaled(Image.open(mock)).save(out / "img" / f"mock-{key}.webp", "WEBP", quality=84)
      shots.append(("Mock", f"img/mock-{key}.webp"))
    built = built_image(renders, e.get("built", key))
    if built is not None:
      built.save(out / "img" / f"built-{key}.webp", "WEBP", quality=84)
      shots.append(("Built", f"img/built-{key}.webp"))
    else:
      missing.append(key)
    title = html.escape(e["title"])
    figures = "".join(f'<figure><a href="{src}"><img src="{src}" alt="{label}: {title}" loading="lazy"></a>'
                      + f'<figcaption>{label}</figcaption></figure>' for label, src in shots)
    note_class = "note match" if e.get("match") else "note"
    articles.append(f'<article><h3>{title}</h3><p class="{note_class}">{html.escape(e["note"])}</p>'
                    + f'<div class="shots">{figures}</div></article>')
  page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mocks and built screens</title>
<style>
:root {{ --bg: #000000; --card: #16191D; --text: #F2F5F9; --muted: #AEB6C2; --match: #6FD8A0; --diff: #F0B35A; }}
body {{ margin: 0; background: var(--bg); color: var(--text); font: 16px/1.5 system-ui, sans-serif; }}
main {{ max-width: 1500px; margin: 0 auto; padding: 24px 16px 48px; }}
article {{ background: var(--card); border-radius: 16px; padding: 16px; margin: 0 0 16px; }}
h3 {{ margin: 0 0 4px; }}
.note {{ margin: 0 0 12px; color: var(--diff); }}
.note.match {{ color: var(--match); }}
.shots {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px; }}
figure {{ margin: 0; }} img {{ width: 100%; height: auto; border-radius: 8px; display: block; }}
figcaption {{ color: var(--muted); font-size: 14px; margin-top: 4px; }}
</style></head><body><main>
<h1>Mocks beside the built screens</h1>
<p style="color: var(--muted)">Each built screen is a headless render of the current code at 2160×1080 with sample data, scaled to the
mock's size. Green notes match; amber notes say what still differs and why.</p>
{"".join(articles)}
</main></body></html>
"""
  (out / "index.html").write_text(page)
  print(f"{out / 'index.html'}: {len(entries)} screens" + (f"; no render for {', '.join(missing)}" if missing else ""))


if __name__ == "__main__":
  if len(sys.argv) not in (3, 4):
    sys.exit(__doc__)
  main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] if len(sys.argv) == 4 else "")
