"""Rebuild Coverity_Final_Slide_Updated.pptx so it looks exactly like
Coverity_Final_Slide.png while keeping every text field editable.

How it works
------------
1. Every editable text line's TRUE ink bbox is measured directly from the
   native 1376x768 PNG (white / orange pixel masks inside a rough search
   window) - no hand-scaled coordinates.
2. The PNG is cleaned with OpenCV inpainting: each measured text rect is
   replaced by pixels diffusing in from its border (the title keeps its
   orange glow - only the white glyph cores are masked there).  Icons,
   tables, arrows, glows and bullets stay baked into the background.
3. Every line is re-created as an editable Arial text box placed on the
   measured bbox (size fitted per line from one Spire reference render so
   the rendered ink width equals the PNG ink width).
4. A headless Spire render of a tall "watermark-safe" variant auto-calibrates
   box offsets so the rendered ink lands on the PNG geometry.

Usage:  python3 rebuild_final_slide.py
"""
import subprocess
import sys
import numpy as np
import cv2
from PIL import Image, ImageFont

from pptx import Presentation
from pptx.util import Emu, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

from slide_specs import LINES

SRC = 'Coverity_Final_Slide.png'
W, H = 1376, 768                   # slide_specs coords are in this native space
SW_IN, SH_IN = 13.333, 7.5
XI = SW_IN / W                     # px -> inches (horizontal)
YI = SH_IN / H                     # px -> inches (vertical)
PT = 72.0 * YI                     # px (vertical) -> points
BG = '/tmp/slide_bg.png'
OUT_PPTX = 'Coverity_Final_Slide_Updated.pptx'
OUT_PREVIEW = 'Coverity_Final_Slide_Updated_preview.png'
OFF = 2.0                          # extra top margin of the calibration variant
FONT_DIR = '/usr/share/fonts/truetype/dejavu'

COLORS = {'W': (249, 251, 252), 'O': (238, 110, 30), 'L': (246, 150, 45)}


# --------------------------------------------------------------------------
# measurement
# --------------------------------------------------------------------------
def masks(img):
    a = np.asarray(img).astype(int)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    white = (R > 200) & (G > 200) & (B > 200)
    orange = (R > 225) & (G > 80) & (G < 190) & (B < 110)
    return white, orange


def line_mask(white, orange, runs):
    cks = {r[3] for r in runs}
    return white if cks == {'W'} else (white | orange)


def measure_targets(img):
    """True ink bbox (native px) of every editable line in the PNG.
    The y window grows around the previous result so glyphs that extend
    past the hand-written spec window are still captured (x stays bounded
    by the spec so icons/arrows are never swallowed)."""
    white, orange = masks(img)
    targets = []
    for x0, y0, x1, y1, align, runs in LINES:
        m = line_mask(white, orange, runs)
        wx0, wx1 = max(0, x0 - 4), min(W, x1 + 6)
        wy0, wy1 = max(0, y0 - 4), min(H, y1 + 6)
        sub = m[wy0:wy1, wx0:wx1].copy()
        rowsum = sub.sum(1)          # drop full-width separator lines
        sub[rowsum > 0.7 * sub.shape[1], :] = False
        ys, xs = np.where(sub)
        if len(xs) == 0:
            raise SystemExit(f'no ink measured for line {runs[0][0]!r}')
        targets.append((wx0 + xs.min(), wy0 + ys.min(),
                        wx0 + xs.max() + 1, wy0 + ys.max() + 1))
    return targets


# --------------------------------------------------------------------------
# background inpainting
# --------------------------------------------------------------------------
def plane_bg(arr, x0, y0, x1, y1, ring=8):
    """Fit per-channel colour plane a+b*x+c*y from a ring outside the rect."""
    rx0, ry0 = max(0, x0 - ring), max(0, y0 - ring)
    rx1, ry1 = min(W, x1 + ring), min(H, y1 + ring)
    gy, gx = np.mgrid[ry0:ry1, rx0:rx1]
    ringm = ~((gx >= x0) & (gx < x1) & (gy >= y0) & (gy < y1))
    ys, xs = gy[ringm], gx[ringm]
    P = np.stack([np.ones_like(xs), xs, ys], 1).astype(float)
    gy, gx = np.mgrid[y0:y1, x0:x1]
    G = np.stack([np.ones_like(gx), gx, gy], 2).astype(float)
    out = np.empty((y1 - y0, x1 - x0, 3))
    for c in range(3):
        Pc, vc = P, arr[ys, xs, c].astype(float)
        for _ in range(3):                       # robust refit
            coef, *_ = np.linalg.lstsq(Pc, vc, rcond=None)
            res = vc - Pc @ coef
            keep = np.abs(res) < max(30.0, 2.5 * np.std(res) + 5)
            if keep.mean() > 0.5:
                Pc, vc = Pc[keep], vc[keep]
        coef, *_ = np.linalg.lstsq(Pc, vc, rcond=None)
        out[:, :, c] = G @ coef
    return out


def median_bg(arr, x0, y0, x1, y1):
    """Local median (kernel bigger than the text block) + gaussian: erases
    glyphs and their shadows while keeping wide glows/gradients."""
    h = y1 - y0
    k = int(2 * h + 21) | 1
    pad = k // 2 + 8
    cy0, cx0 = max(0, y0 - pad), max(0, x0 - pad)
    cy1, cx1 = min(H, y1 + pad), min(W, x1 + pad)
    crop = arr[cy0:cy1, cx0:cx1]
    med = cv2.GaussianBlur(cv2.medianBlur(crop, k), (21, 21), 0)
    return med[y0 - cy0:y1 - cy0, x0 - cx0:x1 - cx0].astype(float)


def rowmedian_bg(arr, x0, y0, x1, y1):
    """Per-row horizontal median over a wide column window: exact for colour
    bands that are uniform horizontally (text cols < half the window)."""
    band = arr[y0:y1, 0:W].astype(np.float32)
    med = np.median(band, axis=1)              # (h, 3); text < half the row
    return np.repeat(med[:, None, :], x1 - x0, axis=1)


def best_bg(arr, x0, y0, x1, y1):
    """Pick whichever estimator reconstructs the text-free frame around the
    rect better (plane for linear gradients, 2-D median for glows, column
    median for horizontal colour bands/banners)."""
    py0, px0 = max(0, y0 - 10), max(0, x0 - 10)
    py1, px1 = min(H, y1 + 10), min(W, x1 + 10)
    cands = [plane_bg(arr, px0, py0, px1, py1),
             median_bg(arr, px0, py0, px1, py1),
             rowmedian_bg(arr, px0, py0, px1, py1)]
    yy, xx = np.mgrid[py0:py1, px0:px1]
    frame = ~((yy >= y0 - 4) & (yy < y1 + 4) & (xx >= x0 - 4) & (xx < x1 + 4))
    truth = arr[py0:py1, px0:px1].astype(float)
    best = min(cands, key=lambda e: np.abs(e - truth)[frame].mean())
    return best[y0 - py0:y1 - py0, x0 - px0:x1 - px0]


def inpaint_rect(arr, rect, mode='dist'):
    x0, y0, x1, y1 = rect[:4]
    sub = arr[y0:y1, x0:x1]
    if mode == 'lum':
        # title: erase glyphs and rebuild the orange halo synthetically -
        # a gaussian halo of the core mask tinted with the glow colour over
        # the local dark background plane
        R, G, B = (sub[:, :, c].astype(int) for c in range(3))
        core = ((B > R * 0.6) & (R > 110)).astype(np.uint8)
        core = cv2.dilate(core, np.ones((3, 3), np.uint8))
        halo = np.clip(cv2.GaussianBlur(core.astype(np.float32), (0, 0), 6)
                       * 1.2, 0, 1)
        plane = np.clip(plane_bg(arr, x0, y0, x1, y1, ring=14), 0, 255)
        new = plane * (1 - halo[:, :, None]) + \
            np.array([238, 118, 34], float) * halo[:, :, None]
        hh, ww = halo.shape
        dy, dx = np.mgrid[0:hh, 0:ww]
        d = np.minimum(np.minimum(dy, hh - 1 - dy),
                       np.minimum(dx, ww - 1 - dx))
        alpha = np.clip(d / 4.0, 0, 1)[:, :, None]
        arr[y0:y1, x0:x1] = (sub * (1 - alpha) + new * alpha).astype(np.uint8)
        return
    bg = best_bg(arr, x0, y0, x1, y1)
    hh, ww = bg.shape[:2]
    dy, dx = np.mgrid[0:hh, 0:ww]
    d = np.minimum(np.minimum(dy, hh - 1 - dy), np.minimum(dx, ww - 1 - dx))
    alpha = np.clip(d / 3.0, 0, 1)[:, :, None]
    arr[y0:y1, x0:x1] = (sub * (1 - alpha) + bg * alpha).astype(np.uint8)


def build_background(img, targets, out=BG):
    arr = np.array(img)
    for i, (bx0, by0, bx1, by1) in enumerate(targets):
        if LINES[i][5][0][0].startswith('COVERITY'):
            # title: cover the whole halo so the synthetic glow replaces it
            rect = (max(0, bx0 - 22), max(0, by0 - 22),
                    min(W, bx1 + 22), min(H, by1 + 24))
            mode = 'lum'
        else:
            # asymmetric pad: drop shadows fall to the bottom-right of ink
            rx1 = min(W, bx1 + 11)
            if 262 < by0 < 480 and bx0 < 880:      # stay inside table columns
                rx1 = min(rx1, 637 if bx0 < 640 else 877)
            rect = (max(0, bx0 - 4), max(0, by0 - 5), rx1, min(H, by1 + 11))
            mode = 'dist'
        inpaint_rect(arr, rect, mode)
    Image.fromarray(arr).save(out)
    print('wrote background', out)


# --------------------------------------------------------------------------
# pptx build
# --------------------------------------------------------------------------
REF_PT = 20.0


def fit_sizes(targets):
    """Per-line font size (Arial) whose rendered ink width matches the PNG.
    One Spire render of all lines at REF_PT gives width-per-pt per line."""
    prs = Presentation()
    prs.slide_width = Emu(int(SW_IN * 914400))
    prs.slide_height = Emu(int((len(LINES) * 0.6 + 1) * 914400))
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    for i, line in enumerate(LINES):
        box = slide.shapes.add_textbox(Emu(int(40 * XI * 914400)),
                                       Emu(int((20 + i * 55) * 914400 / 96)),
                                       Emu(int(1200 * XI * 914400)),
                                       Emu(int(50 * 914400 / 96)))
        tf = box.text_frame
        tf.word_wrap = False
        tf.margin_left = tf.margin_right = 0
        p = tf.paragraphs[0]
        for text, emr, bold, ck in line[5]:
            r = p.add_run()
            r.text = text
            r.font.size = Pt(REF_PT)
            r.font.bold = bold
            r.font.name = 'Arial'
            r.font.color.rgb = RGBColor(0, 0, 0)
    prs.save('/tmp/fit.pptx')
    slide_h = len(LINES) * 0.6 + 1
    code = f"""
from spire.presentation import Presentation
prs = Presentation()
prs.LoadFromFile('/tmp/fit.pptx')
img = prs.Slides[0].SaveAsImageByWH(1376, round(1376 * {slide_h} / {SW_IN}))
img.Save('/tmp/fit.png')
prs.Dispose()
"""
    subprocess.run([sys.executable, '-c', code], check=True,
                   capture_output=True)
    img = np.array(Image.open('/tmp/fit.png').convert('RGB'))
    sizes = []
    for i, (t, line) in enumerate(zip(targets, LINES)):
        top_px = (20 + i * 55) / 96.0 * img.shape[0] / slide_h
        y0 = max(0, int(top_px) - 12)
        y1 = min(img.shape[0], int(top_px) + 42)
        band = img[y0:y1].sum(2) < 300          # black ink on white slide
        ys, xs = np.where(band)
        if len(xs) == 0:
            sizes.append(18.0)
            continue
        w = xs.max() + 1 - xs.min()
        tw = t[2] - t[0]
        sizes.append(max(8.0, min(60.0, REF_PT * tw / max(w, 1))))
    return sizes


ADJ = None


def build(path, targets, sizes, offset=0.0, height=SH_IN):
    prs = Presentation()
    prs.slide_width = Emu(int(SW_IN * 914400))
    prs.slide_height = Emu(int(height * 914400))
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_picture(BG, 0, Emu(int(offset * 914400)),
                             Emu(int(SW_IN * 914400)), Emu(int(SH_IN * 914400)))
    for i, line in enumerate(LINES):
        bx0, by0, bx1, by1 = targets[i]
        align = line[4]
        a = ADJ[i]
        em = sizes[i] * a['sc']          # points
        if align == 'c':
            w = max((bx1 - bx0) * 1.5, 260)
            cx = (bx0 + bx1) / 2.0 + a['dx']
            left = (cx - w / 2.0) * XI
        else:
            w = (bx1 - bx0) + 90
            left = (bx0 + a['dx']) * XI
        top = (by0 + a['dy']) * YI + offset
        box = slide.shapes.add_textbox(Emu(int(left * 914400)),
                                       Emu(int(top * 914400)),
                                       Emu(int(w * XI * 914400)),
                                       Emu(int(em * 2.4 / 72.0 * 914400)))
        tf = box.text_frame
        tf.word_wrap = False
        tf.vertical_anchor = MSO_ANCHOR.TOP
        tf.margin_left = tf.margin_right = 0
        tf.margin_top = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER if align == 'c' else PP_ALIGN.LEFT
        p.space_before = p.space_after = 0
        p.line_spacing = 1.0
        for text, emr, bold, ck in line[5]:
            r = p.add_run()
            r.text = text
            r.font.size = Pt(em)
            r.font.bold = bold
            r.font.name = 'Arial'
            r.font.color.rgb = RGBColor(*COLORS[ck])
    prs.save(path)


def render(path, out_png, height, out_w=W):
    """Render slide 1 with Spire; crop the content area for tall variants."""
    code = f"""
from spire.presentation import Presentation
prs = Presentation()
prs.LoadFromFile({path!r})
hpx = round({out_w} * {height} / {SW_IN})
img = prs.Slides[0].SaveAsImageByWH({out_w}, hpx)
img.Save({out_png!r})
prs.Dispose()
"""
    subprocess.run([sys.executable, '-c', code], check=True,
                   capture_output=True)
    full = Image.open(out_png).convert('RGB')
    if height != SH_IN:
        y0 = round(full.height * OFF / height)
        y1 = round(full.height * (OFF + SH_IN) / height)
        full = full.crop((0, y0, full.width, y1)).resize((W, H))
        full.save(out_png)
    return full


def measure_render(img, targets):
    """Ink bbox of every text box in a clean render (background has no text)."""
    white, orange = masks(img)
    res = []
    for (bx0, by0, bx1, by1), line in zip(targets, LINES):
        m = line_mask(white, orange, line[5])
        wx0, wy0 = max(0, bx0 - 6), max(0, by0 - 3)
        wx1, wy1 = min(W, bx1 + 6), min(H, by1 + 12)
        sub = m[wy0:wy1, wx0:wx1]
        ys, xs = np.where(sub)
        if len(xs) == 0:
            res.append(None)
            continue
        res.append((wx0 + xs.min(), wy0 + ys.min(),
                    wx0 + xs.max() + 1, wy0 + ys.max() + 1))
    return res


def calibrate(targets, rnd):
    global ADJ
    build('/tmp/cal.pptx', targets, SIZES, offset=OFF, height=SH_IN + OFF)
    img = render('/tmp/cal.pptx', '/tmp/cal.png', SH_IN + OFF)
    res = measure_render(img, targets)
    maxd = 0.0
    for i, (t, r) in enumerate(zip(targets, res)):
        if r is None:
            continue
        bx0, by0, bx1, by1 = t
        a = ADJ[i]
        dy = by0 - r[1]
        a['dy'] += dy
        maxd = max(maxd, abs(dy))
        if LINES[i][4] == 'c':
            a['dx'] += (bx0 + bx1) / 2.0 - (r[0] + r[2]) / 2.0
    print(f'cal round {rnd}: max |dy| {maxd:.1f}px')


SIZES = None


def main():
    global ADJ, SIZES
    img = Image.open(SRC).convert('RGB')
    targets = measure_targets(img)
    for t, line in zip(targets, LINES):
        print(f'target {t}  {line[5][0][0][:28]!r}')
    build_background(img.copy(), targets)
    SIZES = fit_sizes(targets)
    ADJ = [{'dx': 0.0, 'dy': 0.0, 'sc': 1.0} for _ in LINES]
    for rnd in range(3):
        calibrate(targets, rnd)
    build(OUT_PPTX, targets, SIZES)
    build('/tmp/preview_variant.pptx', targets, SIZES,
          offset=OFF, height=SH_IN + OFF)
    render('/tmp/preview_variant.pptx', OUT_PREVIEW, SH_IN + OFF)
    print('wrote', OUT_PPTX, 'and', OUT_PREVIEW)


if __name__ == '__main__':
    main()
