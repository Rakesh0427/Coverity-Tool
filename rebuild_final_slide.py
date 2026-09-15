"""Rebuild Coverity_Final_Slide_Updated.pptx so it looks exactly like
Coverity_Final_Slide.png while keeping every text field editable.

How: the PNG is inpainted (text glyphs removed, see make_slide_background.py)
and embedded as the slide background; every text line is re-created as an
editable text box positioned to match the PNG.  A headless render
(Spire.Presentation) of a tall "watermark-safe" variant is used to
auto-calibrate box positions/font sizes against the measured PNG geometry.

Usage:  python3 rebuild_final_slide.py
"""
import subprocess
import sys
import numpy as np
from PIL import Image

from pptx import Presentation
from pptx.util import Emu, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

from slide_specs import LINES, XI, YI, PT, WHITE, ORANGE_HDR, ORANGE_LT

COLORS = {'W': WHITE, 'O': ORANGE_HDR, 'L': ORANGE_LT}
BG = '/tmp/slide_bg.png'
OUT_PPTX = 'Coverity_Final_Slide_Updated.pptx'
OUT_PREVIEW = 'Coverity_Final_Slide_Updated_preview.png'
SW, SH = 13.333, 7.5
OFF = 2.0          # extra top margin in the calibration variant (hides the
                   # Spire evaluation watermark above the content)

ADJ = [{'dx': 0.0, 'dy': 0.0, 'sc': 1.0} for _ in LINES]
FONT_DIR = '/usr/share/fonts/truetype/dejavu'


def fit_sizes():
    """Pick per-line DejaVu Sans size whose ink width matches the PNG bbox."""
    from PIL import ImageFont
    sizes = []
    for x0, y0, x1, y1, align, runs in LINES:
        tw = x1 - x0
        best = (1e9, runs[0][1])
        for size in range(9, 60):
            wsum = 0
            for text, emr, bold, ck in runs:
                f = ImageFont.truetype(
                    f'{FONT_DIR}/{"DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"}', size)
                l, t, r, b = f.getbbox(text)
                wsum += r - l
            score = abs(wsum - tw)
            if score < best[0]:
                best = (score, size)
        sizes.append(best[1])
    return sizes


SIZES = fit_sizes()
OVERRIDES = {1: 20, 26: 30, 14: 18, 15: 18, 16: 16, 17: 16, 18: 16, 19: 16,
             20: 16, 21: 16, 22: 16, 23: 16, 24: 16, 25: 16,
             27: 16, 28: 16, 34: 20, 35: 20}
for k, v in OVERRIDES.items():
    SIZES[k] = v


def build(path, offset=0.0, height=SH):
    prs = Presentation()
    prs.slide_width = Emu(int(SW * 914400))
    prs.slide_height = Emu(int(height * 914400))
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_picture(BG, 0, Emu(int(offset * 914400)),
                             Emu(int(SW * 914400)), Emu(int(SH * 914400)))
    for i, line in enumerate(LINES):
        x0, y0, x1, y1, align, runs = line
        a = ADJ[i]
        em = SIZES[i] * a['sc']
        if align == 'c':
            w = max((x1 - x0) * 1.35, 240)
            cx = (x0 + x1) / 2.0 + a['dx']
            left = (cx - w / 2.0) * XI
        else:
            w = (x1 - x0) + 80
            left = (x0 + a['dx']) * XI
        top = (y0 + a['dy']) * YI + offset
        box = slide.shapes.add_textbox(Emu(int(left * 914400)),
                                       Emu(int(top * 914400)),
                                       Emu(int(w * XI * 914400)),
                                       Emu(int(em * 2.2 * YI * 914400)))
        tf = box.text_frame
        tf.word_wrap = False
        tf.vertical_anchor = MSO_ANCHOR.TOP
        tf.margin_left = tf.margin_right = 0
        tf.margin_top = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER if align == 'c' else PP_ALIGN.LEFT
        p.space_before = p.space_after = 0
        for text, emr, bold, ck in runs:
            r = p.add_run()
            r.text = text
            r.font.size = Pt(SIZES[i] * a['sc'] * PT)
            r.font.bold = bold
            r.font.name = 'DejaVu Sans'
            r.font.color.rgb = RGBColor(*COLORS[ck])
    prs.save(path)


def render(path, out_png, height):
    """Render slide 1 to out_png at 1280px width via Spire; returns crop box
    (content area) when height != SH."""
    code = f"""
from spire.presentation import Presentation
prs = Presentation()
prs.LoadFromFile({path!r})
hpx = round(1280 * {height} / 13.333)
img = prs.Slides[0].SaveAsImageByWH(1280, hpx)
img.Save({out_png!r})
prs.Dispose()
"""
    subprocess.run([sys.executable, '-c', code], check=True,
                   capture_output=True)
    full = Image.open(out_png).convert('RGB')
    if height != SH:
        y0 = round(full.height * OFF / height)
        y1 = round(full.height * (OFF + SH) / height)
        full = full.crop((0, y0, 1280, y1)).resize((1280, 768))
        full.save(out_png)
    return full


def measure(img):
    a = np.asarray(img).astype(int)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    lum = a.sum(2)
    white = (R > 200) & (G > 200) & (B > 200)
    orange = (R > 225) & (G > 80) & (G < 190) & (B < 110)
    results = []
    for i, line in enumerate(LINES):
        x0, y0, x1, y1, align, runs = line
        cks = {r[3] for r in runs}
        mask = white if cks == {'W'} else (white | orange)
        pad_l = 10 if align == 'c' else 2
        rx0, ry0 = max(0, x0 - pad_l), max(0, y0 - 3)
        rx1, ry1 = min(1280, x1 + 8), min(768, y1 + 5)
        sub = mask[ry0:ry1, rx0:rx1]
        rowsum = sub.sum(1)                     # drop full-width separator
        sub[rowsum > 0.7 * sub.shape[1], :] = False   # line highlights
        ys, xs = np.where(sub)
        if len(xs) == 0:
            results.append(None)
            continue
        results.append((rx0 + xs.min(), ry0 + ys.min(),
                        rx0 + xs.max() + 1, ry0 + ys.max() + 1))
    return results


def calibrate(round_idx):
    build('/tmp/cal.pptx', offset=OFF, height=SH + OFF)
    img = render('/tmp/cal.pptx', '/tmp/cal.png', SH + OFF)
    res = measure(img)
    maxdy = 0
    for i, (line, r) in enumerate(zip(LINES, res)):
        if r is None:
            continue
        x0, y0, x1, y1, align, runs = line
        a = ADJ[i]
        dy = y0 - r[1]
        a['dy'] += dy
        maxdy = max(maxdy, abs(dy))
        if align == 'c':
            a['dx'] += (x0 + x1) / 2.0 - (r[0] + r[2]) / 2.0
    print(f'cal round {round_idx}: max |dy| {maxdy:.1f}px')


def main():
    subprocess.run([sys.executable, 'make_slide_background.py', BG], check=True)
    for rnd in range(2):
        calibrate(rnd)
    build(OUT_PPTX)                                   # deliverable, true 16:9
    build('/tmp/preview_variant.pptx', offset=OFF, height=SH + OFF)
    render('/tmp/preview_variant.pptx', OUT_PREVIEW, SH + OFF)
    print('wrote', OUT_PPTX, 'and', OUT_PREVIEW)


if __name__ == '__main__':
    main()
