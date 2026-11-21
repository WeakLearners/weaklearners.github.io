#!/usr/bin/env python3
"""Build og.png (1200x630), the link-preview image, in the home page's own look.

Usage: python3 tools/make_og.py        (needs Pillow; fonts are in tools/fonts/)

Reads the match and win counts from the STAT block in index.html, so the dot field
keeps the same proportion as the hero after tools/update_stats.py runs.
Gold dots are wins, slate dots are losses, one dot for each match, in a phyllotaxis bloom.
"""
import math, random, re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
m = re.search(r"const STAT = \{matches: (\d+), wins: (\d+)", (ROOT / "index.html").read_text())
N, WINS = int(m.group(1)), int(m.group(2))

W, H, SS = 1200, 630, 3          # SS = supersampling, for smooth dots
BG, FG, DIM = "#07080b", "#eceae4", "#7d8392"
WIN, LOSS = (242, 196, 107), (125, 151, 182)
SERIF = ROOT / "tools/fonts/InstrumentSerif-Regular.ttf"
MONO = ROOT / "tools/fonts/SpaceMono-Regular.ttf"

img = Image.new("RGB", (W * SS, H * SS), BG)
d = ImageDraw.Draw(img, "RGBA")

# dot bloom, same method as the hero: golden-angle spiral, results shuffled with a fixed seed
cx, cy, R = 940, 315, 228
GA = math.pi * (3 - math.sqrt(5))
res = [i < WINS for i in range(N)]
random.Random(48).shuffle(res)
rnd = random.Random(7)
spacing = R / math.sqrt(N)
for i, win in enumerate(res):
    a, r = i * GA, spacing * math.sqrt(i)
    x, y = cx + math.cos(a) * r, cy + math.sin(a) * r
    col = WIN if win else LOSS
    alpha = int(255 * (0.55 + 0.45 * rnd.random()))
    rad = 1.4
    d.ellipse([(x - rad) * SS, (y - rad) * SS, (x + rad) * SS, (y + rad) * SS], fill=col + (alpha,))

def font(path, size):
    return ImageFont.truetype(str(path), size * SS)

d.text((64 * SS, 262 * SS), "Sean Kim", font=font(SERIF, 148), fill=FG, anchor="ls")
d.text((68 * SS, 340 * SS), "AI and LLM application engineering · 2027 internship", font=font(MONO, 19), fill=FG, anchor="ls")
d.text((68 * SS, 560 * SS), "weaklearners.com", font=font(MONO, 22), fill=WIN, anchor="ls")
d.text((68 * SS, 592 * SS), f"{N:,} competitive matches, one dot each", font=font(MONO, 15), fill=DIM, anchor="ls")

img = img.resize((W, H), Image.LANCZOS)
out = ROOT / "og.png"
img.save(out, optimize=True)
print(f"wrote {out} ({out.stat().st_size // 1024} KB), {N} dots, {WINS} wins")
