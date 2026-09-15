"""Create the slide background: Coverity_Final_Slide.png with all text glyphs
inpainted away (icons, tables, arrows, glows kept), so the rebuilt PPTX can
overlay editable text boxes while looking identical to the PNG."""
import sys
import numpy as np
from PIL import Image, ImageFilter

from slide_specs import INPAINT_RECTS

SRC = 'Coverity_Final_Slide.png'
OUT = sys.argv[1] if len(sys.argv) > 1 else '/tmp/slide_bg.png'


def plane_bg(img, x0, y0, x1, y1):
    """Robustly fit per-channel colour plane a+b*x+c*y from a ring of pixels
    just outside the rect (ring avoids the text but follows the gradient)."""
    H, W, _ = img.shape
    rx0, ry0 = max(0, x0 - 7), max(0, y0 - 7)
    rx1, ry1 = min(W, x1 + 7), min(H, y1 + 7)
    gy, gx = np.mgrid[ry0:ry1, rx0:rx1]
    ring = ~((gx >= x0 - 1) & (gx <= x1) & (gy >= y0 - 1) & (gy <= y1))
    ys, xs = gy[ring], gx[ring]
    P = np.stack([np.ones_like(xs), xs, ys], 1).astype(float)
    out = np.empty((y1 - y0, x1 - x0, 3))
    gy, gx = np.mgrid[y0:y1, x0:x1]
    G = np.stack([np.ones_like(gx), gx, gy], 2).astype(float)
    for c in range(3):
        Pc, vc = P, img[ys, xs, c].astype(float)
        for _ in range(3):                      # robust refit
            coef, *_ = np.linalg.lstsq(Pc, vc, rcond=None)
            res = vc - Pc @ coef
            keep = np.abs(res) < max(30.0, 2.5 * np.std(res) + 5)
            if keep.mean() > 0.5:
                Pc, vc = Pc[keep], vc[keep]
        coef, *_ = np.linalg.lstsq(Pc, vc, rcond=None)
        out[:, :, c] = G @ coef
    return out


def inpaint_rect(img, rect):
    """img: HxWx3 uint8 ndarray, modified in place for `rect`."""
    mode = 'lum' if len(rect) == 5 else 'dist'
    x0, y0, x1, y1 = rect[:4]
    sub = img[y0:y1, x0:x1].astype(np.int32)
    if mode == 'lum':
        for _ in range(4):                       # passes shrink white cores
            pil = Image.fromarray(sub.astype(np.uint8)).filter(ImageFilter.MedianFilter(31))
            bg = np.asarray(pil).astype(np.int32)
            mask = sub.sum(2) > 470              # white title glyphs only
            m = mask.copy()
            m[1:, :] |= mask[:-1, :]
            m[:-1, :] |= mask[1:, :]
            m[:, 1:] |= mask[:, :-1]
            m[:, :-1] |= mask[:, 1:]
            sub[m] = bg[m]
            if not m.any():
                break
    else:
        bg = plane_bg(img, x0, y0, x1, y1)
        for thr in (60, 40, 26):
            diff = sub.sum(2) - bg.sum(2)        # text is lighter than bg
            mask = diff > thr
            m = mask.copy()
            m[1:, :] |= mask[:-1, :]
            m[:-1, :] |= mask[1:, :]
            m[:, 1:] |= mask[:, :-1]
            m[:, :-1] |= mask[:, 1:]
            sub[m] = np.clip(bg, 0, 255)[m].astype(np.int32)
    img[y0:y1, x0:x1] = sub.astype(np.uint8)


def main():
    img = np.asarray(Image.open(SRC).convert('RGB')).copy()
    for r in INPAINT_RECTS:
        inpaint_rect(img, r)
    Image.fromarray(img).save(OUT)
    print('wrote', OUT)


if __name__ == '__main__':
    main()
