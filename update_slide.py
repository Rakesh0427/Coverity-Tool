"""
Generate Coverity_latest_slide.png respecting:
  1. "keep the image same dont touch":
     - The base image from commit f41bb9358b5775fb68762bc2110851f7a281e1b3 is preserved 100%.
     - Line 1 ("RL1 (1,000 defects): 250 hrs → 33 hrs = 217 hrs SAVED") is UNTOUCHED in place.
     - Line 2 ("Program (4,000 defects): 1000 hrs → 133 hrs = 867 hrs SAVED") is UNTOUCHED in place.
     - Only append "*($7k)*" after 217 hrs SAVED, and "*($30k)*" after 867 hrs SAVED.
     - Only erase the "Cost: $7,595 - $30,345 per release (at $30/hr)" line.
  2. "remaining font adjust accordingly":
     - The remaining text (Real Saving and Future Targeted) is scaled and formatted harmoniously
       (size 16-17.5px with natural line spacing), matching the visual hierarchy of the deck.
"""

import subprocess
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def update_slide(output_path='Coverity_latest_slide.png'):
    # Load pristine base image from commit f41bb9358b5775fb68762bc2110851f7a281e1b3
    proc = subprocess.run(
        ['git', 'show', 'f41bb9358b5775fb68762bc2110851f7a281e1b3:Coverity_latest_slide.png'],
        stdout=subprocess.PIPE, check=True
    )
    base_cv = cv2.imdecode(np.frombuffer(proc.stdout, np.uint8), cv2.IMREAD_COLOR)

    # Erase ONLY the "Cost: $7,595 - $30,345..." line (y: 682..715, x: 45..560)
    cost_mask = np.zeros(base_cv.shape[:2], dtype=np.uint8)
    sub_cost = base_cv[682:715, 45:560]
    bg_color = np.array([47, 23, 4], dtype=float)
    diff = np.linalg.norm(sub_cost.astype(float) - bg_color, axis=2)
    cost_mask[682:715, 45:560] = (diff > 18).astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    cost_mask = cv2.dilate(cost_mask, k)
    clean_bgr = cv2.inpaint(base_cv, cost_mask, 5, cv2.INPAINT_TELEA)

    # Fonts
    bold_p = '/usr/local/lib/python3.11/dist-packages/font_source_sans_pro/files/SourceSansPro-Bold.ttf'
    reg_p = '/usr/local/lib/python3.11/dist-packages/font_source_sans_pro/files/SourceSansPro-Regular.ttf'
    semi_p = '/usr/local/lib/python3.11/dist-packages/font_source_sans_pro/files/SourceSansPro-Semibold.ttf'

    # Font sizes adjusted to fit proportionally without looking odd
    f_badge = ImageFont.truetype(bold_p, 20)       # Matching RL1/Program SAVED text size
    f_hdr = ImageFont.truetype(bold_p, 17.5)       # Real Saving header
    f_b = ImageFont.truetype(bold_p, 16.5)         # Bold metrics
    f_r = ImageFont.truetype(reg_p, 16.5)         # Regular labels
    f_s = ImageFont.truetype(semi_p, 16.5)        # Semibold body text

    # Colors
    C_WHITE = (255, 255, 255)
    C_WHITE_DIM = (215, 222, 235)
    C_ORANGE = (255, 120, 20)
    C_YELLOW = (255, 215, 0)
    C_GREEN = (50, 255, 130)
    C_CYAN = (0, 230, 255)
    C_BULLET = (255, 120, 20)

    runs = []

    # ── Append *($7k)* after 217 hrs SAVED (Line 1 pristine, ends at x=660) ──
    runs.append((672, 608, '*($7k)*', f_badge, C_YELLOW))

    # ── Append *($30k)* after 867 hrs SAVED (Line 2 pristine, ends at x=739) ──
    runs.append((751, 648, '*($30k)*', f_badge, C_YELLOW))

    x = 52

    # ── Line 3: Real Saving Header ──
    y3 = 675
    runs.append((x, y3, 'Real Saving \u2014 NG-FMS ATS Core EPP', f_hdr, C_CYAN))

    # ── Line 4: 143 defects analysed + pushed in the EPP ──
    y4 = 694
    runs.append((x, y4, '\u2022 ', f_b, C_BULLET))
    w = x + f_b.getlength('\u2022 ')
    runs.append((w, y4, '143', f_b, C_WHITE))
    w += f_b.getlength('143')
    runs.append((w, y4, ' defects analysed + pushed in the EPP', f_s, C_WHITE))

    # ── Line 5: Manual push vs Tool push ──
    y5 = 712
    runs.append((x, y5, '\u2022 ', f_b, C_BULLET))
    w = x + f_b.getlength('\u2022 ')
    runs.append((w, y5, 'Manual push: ', f_r, C_WHITE_DIM))
    w += f_r.getlength('Manual push: ')
    runs.append((w, y5, '143 min ', f_b, C_WHITE))
    w += f_b.getlength('143 min ')
    runs.append((w, y5, '(\u22481 min per defect)   ', f_r, C_WHITE_DIM))
    w += f_r.getlength('(\u22481 min per defect)   ')
    runs.append((w, y5, '\u2192   ', f_b, C_ORANGE))
    w += f_b.getlength('\u2192   ')
    runs.append((w, y5, 'Tool push: ', f_r, C_WHITE_DIM))
    w += f_r.getlength('Tool push: ')
    runs.append((w, y5, '~3 min ', f_b, C_GREEN))
    w += f_b.getlength('~3 min ')
    runs.append((w, y5, '(one batch)', f_r, C_WHITE_DIM))

    # ── Line 6: Saved on push ──
    y6 = 730
    runs.append((x, y6, '\u2022 ', f_b, C_BULLET))
    w = x + f_b.getlength('\u2022 ')
    runs.append((w, y6, 'Saved on push: ', f_r, C_WHITE_DIM))
    w += f_r.getlength('Saved on push: ')
    runs.append((w, y6, '~140 min ($84) ', f_b, C_GREEN))
    w += f_b.getlength('~140 min ($84) ')
    runs.append((w, y6, '(\u224899% faster, 2.4 hrs)', f_s, C_WHITE))

    # ── Line 7: Future Targeted programs ──
    y7 = 748
    runs.append((x, y7, 'Future Targeted programs are  ', f_b, C_ORANGE))
    w = x + f_b.getlength('Future Targeted programs are  ')
    runs.append((w, y7, 'Datalink(787,AIMS,EPIC), TXD along all CNS products and all other HonAero Departments....', f_r, C_WHITE))

    # Composite layers
    pil_img = Image.fromarray(cv2.cvtColor(clean_bgr, cv2.COLOR_BGR2RGB))
    W, H = pil_img.size

    shadow = Image.new('L', (W, H), 0)
    d_sh = ImageDraw.Draw(shadow)
    for rx, ry, text, font, _ in runs:
        d_sh.text((rx, ry), text, font=font, fill=255)
    shadow_b = shadow.filter(ImageFilter.GaussianBlur(1.2))

    canvas = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    canvas.paste(pil_img.convert('RGBA'), (0, 0))

    blk = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    blk.putalpha(shadow_b.point(lambda v: int(v * 0.7)))
    sh_shifted = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    sh_shifted.paste(blk, (0, 1))
    canvas = Image.alpha_composite(canvas, sh_shifted)

    txt = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d_txt = ImageDraw.Draw(txt)
    for rx, ry, text, font, color in runs:
        d_txt.text((rx, ry), text, font=font, fill=(*color, 255))
    canvas = Image.alpha_composite(canvas, txt)

    final = canvas.convert('RGB')
    final.save(output_path, 'PNG')
    print(f"✅ Generated updated slide at {output_path}")

if __name__ == '__main__':
    update_slide('Coverity_latest_slide.png')
