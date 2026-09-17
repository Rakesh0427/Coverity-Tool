"""
Update Coverity_latest_slide.png with requested updates:
  1. Under COST SAVINGS PER PROGRAM:
     - Line 1: RL1 (1,000 defects): 250 hrs → 33 hrs = 217 hrs SAVED *($7k)*
     - Line 2: Program (4,000 defects): 1,000 hrs → 133 hrs = 867 hrs SAVED *($30k)*
     - Remove Cost: line fully
  2. Add Real Saving — NG-FMS ATS Core EPP case study:
     - 143 defects analysed + pushed in the EPP
     - Manual push: 143 min (≈1 min per defect) → Tool push: ~3 min (one batch)
     - Saved on push: ~140 min ($84) (≈99% faster, 2.4 hrs)
  3. Add Future Targeted programs are Datalink(787,AIMS,EPIC), TXD along all CNS products and all other HonAero Departments....
  4. Ensure font size matches the rest of the slide (size 20-21px, cap height matching existing headers and table text).
  5. Keep the rest of the image 100% untouched.
"""

import os
import subprocess
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def get_base_image():
    """Retrieve pristine base image from commit f41bb9358b5775fb68762bc2110851f7a281e1b3 if available."""
    try:
        proc = subprocess.run(
            ['git', 'show', 'f41bb9358b5775fb68762bc2110851f7a281e1b3:Coverity_latest_slide.png'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
        )
        img_arr = np.frombuffer(proc.stdout, dtype=np.uint8)
        img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
        if img is not None:
            return img
    except Exception as e:
        print(f"Warning: git show failed ({e}), falling back to disk image")

    if os.path.exists('orig_slide.png'):
        return cv2.imread('orig_slide.png')
    return cv2.imread('Coverity_latest_slide.png')

def generate_updated_slide(output_path='Coverity_latest_slide.png'):
    img_cv = get_base_image()
    assert img_cv is not None, "Failed to load base image"
    h, w, _ = img_cv.shape

    # Clean the modified text region (y in [593, 725], x in [45, 800])
    # The background is a dark navy-black gradient
    sub = img_cv[593:725, 45:800]
    bg_color = np.array([47, 23, 4], dtype=float)
    diff = np.linalg.norm(sub.astype(float) - bg_color, axis=2)
    text_mask = diff > 15
    mask = np.zeros(img_cv.shape[:2], dtype=np.uint8)
    mask[593:725, 45:800] = text_mask.astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.dilate(mask, k)
    clean_bgr = cv2.inpaint(img_cv, mask, 5, cv2.INPAINT_TELEA)

    clean_pil = Image.fromarray(cv2.cvtColor(clean_bgr, cv2.COLOR_BGR2RGB))
    W, H = clean_pil.size

    # Font definitions (Source Sans Pro matching modern corporate presentation standards)
    bold_p = '/usr/local/lib/python3.11/dist-packages/font_source_sans_pro/files/SourceSansPro-Bold.ttf'
    reg_p = '/usr/local/lib/python3.11/dist-packages/font_source_sans_pro/files/SourceSansPro-Regular.ttf'
    semi_p = '/usr/local/lib/python3.11/dist-packages/font_source_sans_pro/files/SourceSansPro-Semibold.ttf'

    # Font instances scaled to match the rest of the slide (cap height 16-18px)
    f_b21 = ImageFont.truetype(bold_p, 21)
    f_r21 = ImageFont.truetype(reg_p, 21)
    f_b20 = ImageFont.truetype(bold_p, 20)
    f_r20 = ImageFont.truetype(reg_p, 20)
    f_s20 = ImageFont.truetype(semi_p, 20)

    # Color palette
    C_WHITE = (255, 255, 255)
    C_WHITE_DIM = (215, 222, 235)
    C_ORANGE = (255, 120, 20)      # Vivid aerospace orange
    C_YELLOW = (255, 215, 0)       # Gold yellow for dollar savings
    C_GREEN = (50, 255, 130)       # Vibrant green for tool speedup & savings
    C_CYAN = (0, 230, 255)         # Cyan glow for Real Saving header
    C_BULLET = (255, 120, 20)      # Orange accent bullets

    x = 52
    runs = []

    # ── Line 1: RL1 program savings with *($7k)* ──
    y1 = 596
    runs.append((x, y1, 'RL1', f_b21, C_WHITE))
    w = x + f_b21.getlength('RL1')
    runs.append((w, y1, ' (1,000 defects): 250 hrs \u2192 33 hrs = ', f_r21, C_WHITE))
    w += f_r21.getlength(' (1,000 defects): 250 hrs \u2192 33 hrs = ')
    runs.append((w, y1, '217 hrs SAVED ', f_b21, C_ORANGE))
    w += f_b21.getlength('217 hrs SAVED ')
    runs.append((w, y1, '*($7k)*', f_b21, C_YELLOW))

    # ── Line 2: Program savings with *($30k)* ──
    y2 = 621
    runs.append((x, y2, 'Program', f_b21, C_WHITE))
    w = x + f_b21.getlength('Program')
    runs.append((w, y2, ' (4,000 defects): 1,000 hrs \u2192 133 hrs = ', f_r21, C_WHITE))
    w += f_r21.getlength(' (4,000 defects): 1,000 hrs \u2192 133 hrs = ')
    runs.append((w, y2, '867 hrs SAVED ', f_b21, C_ORANGE))
    w += f_b21.getlength('867 hrs SAVED ')
    runs.append((w, y2, '*($30k)*', f_b21, C_YELLOW))

    # ── Line 3: Real Saving Header ──
    y3 = 647
    runs.append((x, y3, 'Real Saving \u2014 NG-FMS ATS Core EPP', f_b21, C_CYAN))

    # ── Line 4: 143 defects analysed + pushed in the EPP ──
    y4 = 671
    runs.append((x, y4, '\u2022 ', f_b20, C_BULLET))
    w = x + f_b20.getlength('\u2022 ')
    runs.append((w, y4, '143', f_b20, C_WHITE))
    w += f_b20.getlength('143')
    runs.append((w, y4, ' defects analysed + pushed in the EPP', f_s20, C_WHITE))

    # ── Line 5: Manual push vs Tool push ──
    y5 = 695
    runs.append((x, y4 := y5, '\u2022 ', f_b20, C_BULLET))
    w = x + f_b20.getlength('\u2022 ')
    runs.append((w, y5, 'Manual push: ', f_r20, C_WHITE_DIM))
    w += f_r20.getlength('Manual push: ')
    runs.append((w, y5, '143 min ', f_b20, C_WHITE))
    w += f_b20.getlength('143 min ')
    runs.append((w, y5, '(\u22481 min per defect)   ', f_r20, C_WHITE_DIM))
    w += f_r20.getlength('(\u22481 min per defect)   ')
    runs.append((w, y5, '\u2192   ', f_b20, C_ORANGE))
    w += f_b20.getlength('\u2192   ')
    runs.append((w, y5, 'Tool push: ', f_r20, C_WHITE_DIM))
    w += f_r20.getlength('Tool push: ')
    runs.append((w, y5, '~3 min ', f_b20, C_GREEN))
    w += f_b20.getlength('~3 min ')
    runs.append((w, y5, '(one batch)', f_r20, C_WHITE_DIM))

    # ── Line 6: Saved on push ──
    y6 = 719
    runs.append((x, y6, '\u2022 ', f_b20, C_BULLET))
    w = x + f_b20.getlength('\u2022 ')
    runs.append((w, y6, 'Saved on push: ', f_r20, C_WHITE_DIM))
    w += f_r20.getlength('Saved on push: ')
    runs.append((w, y6, '~140 min ($84) ', f_b20, C_GREEN))
    w += f_b20.getlength('~140 min ($84) ')
    runs.append((w, y6, '(\u224899% faster, 2.4 hrs)', f_s20, C_WHITE))

    # ── Line 7: Future Targeted programs ──
    y7 = 744
    runs.append((x, y7, 'Future Targeted programs are  ', f_b20, C_ORANGE))
    w = x + f_b20.getlength('Future Targeted programs are  ')
    runs.append((w, y7, 'Datalink(787,AIMS,EPIC), TXD along all CNS products and all other HonAero Departments....', f_r20, C_WHITE))

    # Layered rendering: background -> soft shadow -> sharp text
    canvas = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    canvas.paste(clean_pil.convert('RGBA'), (0, 0))

    # Shadow layer
    shadow_layer = Image.new('L', (W, H), 0)
    d_sh = ImageDraw.Draw(shadow_layer)
    for rx, ry, text, font, _ in runs:
        d_sh.text((rx, ry), text, font=font, fill=255)
    shadow_blurred = shadow_layer.filter(ImageFilter.GaussianBlur(1.5))

    blk = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    blk.putalpha(shadow_blurred.point(lambda v: int(v * 0.75)))
    sh_shifted = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    sh_shifted.paste(blk, (0, 2))
    canvas = Image.alpha_composite(canvas, sh_shifted)

    # Crisp text layer
    txt_layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d_txt = ImageDraw.Draw(txt_layer)
    for rx, ry, text, font, color in runs:
        d_txt.text((rx, ry), text, font=font, fill=(*color, 255))
    canvas = Image.alpha_composite(canvas, txt_layer)

    final_img = canvas.convert('RGB')
    final_img.save(output_path, 'PNG')
    print(f"Successfully generated updated slide at {output_path}")

if __name__ == '__main__':
    generate_updated_slide('Coverity_latest_slide.png')
