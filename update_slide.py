import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def generate_updated_slide(input_path, output_path):
    assert os.path.exists(input_path), f"Input image {input_path} not found"
    img_cv = cv2.imread(input_path)
    h, w, _ = img_cv.shape

    # 1. Clean background in the modified area (y in [593, 725], x in [45, 755])
    # The background is a clean, uniform dark navy gradient
    sub = img_cv[593:725, 45:755]
    bg_color = np.array([47, 23, 4], dtype=float)
    diff = np.linalg.norm(sub.astype(float) - bg_color, axis=2)
    text_mask = diff > 15
    mask = np.zeros(img_cv.shape[:2], dtype=np.uint8)
    mask[593:725, 45:755] = text_mask.astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.dilate(mask, k)
    clean_bgr = cv2.inpaint(img_cv, mask, 5, cv2.INPAINT_TELEA)

    clean_pil = Image.fromarray(cv2.cvtColor(clean_bgr, cv2.COLOR_BGR2RGB))
    W, H = clean_pil.size

    # Font definitions (Source Sans Pro, highly clean and modern, matching Segoe UI metrics)
    bold_p = '/usr/local/lib/python3.11/dist-packages/font_source_sans_pro/files/SourceSansPro-Bold.ttf'
    reg_p = '/usr/local/lib/python3.11/dist-packages/font_source_sans_pro/files/SourceSansPro-Regular.ttf'
    semi_p = '/usr/local/lib/python3.11/dist-packages/font_source_sans_pro/files/SourceSansPro-Semibold.ttf'

    # Color palette matching the rest of the slide
    C_WHITE = (249, 251, 252)
    C_ORANGE = (246, 150, 45)      # Light orange for SAVED and Future Targeted
    C_YELLOW = (255, 204, 0)       # Accent gold/yellow for cost figures
    C_GREEN = (51, 255, 136)       # Vibrant green for tool push and savings
    C_CYAN = (0, 204, 255)         # Cyan glow for Real Saving header
    C_GRAY = (185, 195, 210)       # Muted gray for labels
    C_BULLET = (246, 150, 45)      # Orange for bullets

    # Font instances
    f_prog_b = ImageFont.truetype(bold_p, 20)
    f_prog_r = ImageFont.truetype(reg_p, 20)
    f_prog_y = ImageFont.truetype(bold_p, 20)

    f_rs_hdr = ImageFont.truetype(bold_p, 18)
    f_rs_b = ImageFont.truetype(bold_p, 15)
    f_rs_r = ImageFont.truetype(reg_p, 15)
    f_rs_s = ImageFont.truetype(semi_p, 15)

    f_fut_b = ImageFont.truetype(bold_p, 15)
    f_fut_r = ImageFont.truetype(reg_p, 15)

    runs = []
    x = 52

    # ── Line 1: RL1 program savings with *($7k)* ──
    y1 = 595
    runs.append((x, y1, 'RL1', f_prog_b, C_WHITE))
    w = x + f_prog_b.getlength('RL1')
    runs.append((w, y1, ' (1,000 defects): 250 hrs \u2192 33 hrs = ', f_prog_r, C_WHITE))
    w += f_prog_r.getlength(' (1,000 defects): 250 hrs \u2192 33 hrs = ')
    runs.append((w, y1, '217 hrs SAVED ', f_prog_b, C_ORANGE))
    w += f_prog_b.getlength('217 hrs SAVED ')
    runs.append((w, y1, '*($7k)*', f_prog_y, C_YELLOW))

    # ── Line 2: Program savings with *($30k)* ──
    y2 = 620
    runs.append((x, y2, 'Program', f_prog_b, C_WHITE))
    w = x + f_prog_b.getlength('Program')
    runs.append((w, y2, ' (4,000 defects): 1000 hrs \u2192 133 hrs = ', f_prog_r, C_WHITE))
    w += f_prog_r.getlength(' (4,000 defects): 1000 hrs \u2192 133 hrs = ')
    runs.append((w, y2, '867 hrs SAVED ', f_prog_b, C_ORANGE))
    w += f_prog_b.getlength('867 hrs SAVED ')
    runs.append((w, y2, '*($30k)*', f_prog_y, C_YELLOW))

    # ── Line 3: Real Saving Header ──
    y3 = 648
    runs.append((x, y3, 'Real Saving \u2014 NG-FMS ATS Core EPP', f_rs_hdr, C_CYAN))

    # ── Line 4: 143 defects analysed + pushed in the EPP ──
    y4 = 670
    runs.append((x, y4, '\u2022 ', f_rs_b, C_BULLET))
    w = x + f_rs_b.getlength('\u2022 ')
    runs.append((w, y4, '143 defects analysed + pushed in the EPP', f_rs_s, C_WHITE))

    # ── Line 5: Manual push vs Tool push ──
    y5 = 690
    runs.append((x, y5, '\u2022 ', f_rs_b, C_BULLET))
    w = x + f_rs_b.getlength('\u2022 ')
    runs.append((w, y5, 'Manual push: ', f_rs_r, C_GRAY))
    w += f_rs_r.getlength('Manual push: ')
    runs.append((w, y5, '143 min ', f_rs_b, C_WHITE))
    w += f_rs_b.getlength('143 min ')
    runs.append((w, y5, '(\u22481 min per defect)   \u2192   Tool push: ', f_rs_r, C_GRAY))
    w += f_rs_r.getlength('(\u22481 min per defect)   \u2192   Tool push: ')
    runs.append((w, y5, '~3 min ', f_rs_b, C_GREEN))
    w += f_rs_b.getlength('~3 min ')
    runs.append((w, y5, '(one batch)', f_rs_r, C_GRAY))

    # ── Line 6: Saved on push ──
    y6 = 710
    runs.append((x, y6, '\u2022 ', f_rs_b, C_BULLET))
    w = x + f_rs_b.getlength('\u2022 ')
    runs.append((w, y6, 'Saved on push: ', f_rs_r, C_GRAY))
    w += f_rs_r.getlength('Saved on push: ')
    runs.append((w, y6, '~140 min ($84) ', f_rs_b, C_GREEN))
    w += f_rs_b.getlength('~140 min ($84) ')
    runs.append((w, y6, '(\u224899% faster, 2.4 hrs)', f_rs_r, C_WHITE))

    # ── Line 7: Future Targeted programs ──
    y7 = 738
    runs.append((x, y7, 'Future Targeted programs are  ', f_fut_b, C_ORANGE))
    w = x + f_fut_b.getlength('Future Targeted programs are  ')
    runs.append((w, y7, 'Datalink(787,AIMS,EPIC), TXD along all CNS products and all other HonAero Departments....', f_fut_r, C_WHITE))

    # Composition with soft drop shadow
    canvas = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    canvas.paste(clean_pil.convert('RGBA'), (0, 0))

    # Shadow layer
    shadow_layer = Image.new('L', (W, H), 0)
    d_sh = ImageDraw.Draw(shadow_layer)
    for rx, ry, text, font, _ in runs:
        d_sh.text((rx, ry), text, font=font, fill=255)

    shadow_blurred = shadow_layer.filter(ImageFilter.GaussianBlur(1.5))
    blk = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    blk.putalpha(shadow_blurred.point(lambda v: int(v * 0.55)))

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
    print(f"Successfully saved updated slide to {output_path}")

if __name__ == '__main__':
    generate_updated_slide('Coverity_latest_slide.png', 'Coverity_latest_slide.png')
