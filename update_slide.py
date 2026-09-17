import subprocess
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def build_slide():
    # 1. Load pristine base image from commit f41bb9358b5775fb68762bc2110851f7a281e1b3
    proc = subprocess.run(
        ['git', 'show', 'f41bb9358b5775fb68762bc2110851f7a281e1b3:Coverity_latest_slide.png'],
        stdout=subprocess.PIPE, check=True
    )
    orig_bgr = cv2.imdecode(np.frombuffer(proc.stdout, np.uint8), cv2.IMREAD_COLOR)

    # 2. Extract crops
    # CORE FEATURES: y: 168 to 522, x: 40 to 375
    core_crop = orig_bgr[168:522, 40:375].copy()

    # WORK DETAILS: y: 168 to 586, x: 388 to 738
    work_crop = orig_bgr[168:586, 388:738].copy()
    # Clean the bottom-left of work_crop where stray ROGRAM was
    bg_color = np.array([47, 23, 4], dtype=np.uint8)
    work_crop[365:, :160] = bg_color

    # Money bag icon: y: 554 to 585, x: 50 to 78
    money_bag_crop = orig_bgr[554:585, 50:78].copy()

    # Scale factor: 0.81
    scale = 0.81
    core_scaled = cv2.resize(core_crop, (0,0), fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)
    work_scaled = cv2.resize(work_crop, (0,0), fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)
    money_bag_scaled = cv2.resize(money_bag_crop, (0,0), fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)

    # 3. Clean left area: y: 160 to 768, x: 30 to 745
    clean_bgr = orig_bgr.copy()
    mask = np.zeros(orig_bgr.shape[:2], dtype=np.uint8)
    sub_area = orig_bgr[160:768, 30:745]
    diff = np.linalg.norm(sub_area.astype(float) - bg_color.astype(float), axis=2)
    mask[160:768, 30:745] = (diff > 8).astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.dilate(mask, k)
    clean_bgr = cv2.inpaint(clean_bgr, mask, 7, cv2.INPAINT_TELEA)

    # 4. Paste scaled CORE FEATURES and WORK DETAILS
    # Place CORE FEATURES at x=42, y=168
    clean_bgr[168:168+core_scaled.shape[0], 42:42+core_scaled.shape[1]] = core_scaled

    # Place WORK DETAILS at x=415, y=168
    work_x = 415
    clean_bgr[168:168+work_scaled.shape[0], work_x:work_x+work_scaled.shape[1]] = work_scaled

    # Place money bag at y=517, x=42
    mb_h, mb_w, _ = money_bag_scaled.shape
    clean_bgr[517:517+mb_h, 42:42+mb_w] = money_bag_scaled

    # 5. Convert to PIL for text rendering
    canvas = Image.fromarray(cv2.cvtColor(clean_bgr, cv2.COLOR_BGR2RGB))

    # Fonts
    bold_p = '/usr/local/lib/python3.11/dist-packages/font_source_sans_pro/files/SourceSansPro-Bold.ttf'
    semi_p = '/usr/local/lib/python3.11/dist-packages/font_source_sans_pro/files/SourceSansPro-Semibold.ttf'
    reg_p = '/usr/local/lib/python3.11/dist-packages/font_source_sans_pro/files/SourceSansPro-Regular.ttf'
    dejavu_bold = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

    # Font sizes:
    # Header: 25px (EXACT match to scaled CORE FEATURES & WORK DETAILS headers)
    f_header = ImageFont.truetype(bold_p, 25)
    f_body_bold = ImageFont.truetype(bold_p, 17.5)
    f_body_semi = ImageFont.truetype(semi_p, 17.5)
    f_body_reg = ImageFont.truetype(reg_p, 17)
    
    # Highlighted enlarged badge fonts for $7k and $30k
    f_badge_star = ImageFont.truetype(dejavu_bold, 20)
    f_badge_text = ImageFont.truetype(bold_p, 22)

    # Colors
    C_ORANGE_HDR = (250, 112, 36)
    C_WHITE = (255, 255, 255)
    C_WHITE_DIM = (215, 222, 235)
    C_ORANGE = (255, 120, 20)
    C_CYAN = (0, 230, 255)
    C_GREEN = (50, 255, 130)
    C_GOLD = (255, 225, 20)
    C_BULLET = (255, 120, 20)

    text_layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    t_draw = ImageDraw.Draw(text_layer)

    def draw_shadowed(draw, xy, text, font, fill, shadow_color=(0, 0, 0, 220), offset=(2, 2)):
        x, y = xy
        draw.text((x + offset[0], y + offset[1]), text, font=font, fill=shadow_color)
        draw.text((x, y), text, font=font, fill=fill)

    # Header: COST SAVINGS PER PROGRAM
    hdr_x = 42 + mb_w + 10
    hdr_y = 517
    draw_shadowed(t_draw, (hdr_x, hdr_y), "COST SAVINGS PER PROGRAM", f_header, C_ORANGE_HDR)

    # Line 1: RL1 (1,000 defects): 250 hrs → 33 hrs = 217 hrs SAVED  ★ ($7k) ★
    y1 = 554
    x = 42
    t1 = "RL1 (1,000 defects): 250 hrs → 33 hrs = "
    draw_shadowed(t_draw, (x, y1), t1, f_body_semi, C_WHITE)
    x += int(t_draw.textlength(t1, font=f_body_semi))

    t2 = "217 hrs SAVED"
    draw_shadowed(t_draw, (x, y1), t2, f_body_bold, C_ORANGE)
    x += int(t_draw.textlength(t2, font=f_body_bold)) + 12

    badge_txt1 = "★ ($7k) ★"
    bw1 = int(t_draw.textlength(badge_txt1, font=f_badge_star))
    t_draw.rounded_rectangle([x, y1 - 5, x + bw1 + 14, y1 + 27], radius=6, fill=(35, 28, 5, 240), outline=(255, 215, 0, 255), width=2)
    t_draw.text((x + 7, y1 - 2), badge_txt1, fill=C_GOLD, font=f_badge_star)

    # Line 2: Program (4,000 defects): 1000 hrs → 133 hrs = 867 hrs SAVED  ★ ($30k) ★
    y2 = 588
    x = 42
    t1 = "Program (4,000 defects): 1000 hrs → 133 hrs = "
    draw_shadowed(t_draw, (x, y2), t1, f_body_semi, C_WHITE)
    x += int(t_draw.textlength(t1, font=f_body_semi))

    t2 = "867 hrs SAVED"
    draw_shadowed(t_draw, (x, y2), t2, f_body_bold, C_ORANGE)
    x += int(t_draw.textlength(t2, font=f_body_bold)) + 12

    badge_txt2 = "★ ($30k) ★"
    bw2 = int(t_draw.textlength(badge_txt2, font=f_badge_star))
    t_draw.rounded_rectangle([x, y2 - 5, x + bw2 + 14, y2 + 27], radius=6, fill=(35, 28, 5, 240), outline=(255, 215, 0, 255), width=2)
    t_draw.text((x + 7, y2 - 2), badge_txt2, fill=C_GOLD, font=f_badge_star)

    # Line 3: Real Saving — NG-FMS ATS Core EPP
    y3 = 622
    draw_shadowed(t_draw, (42, y3), "Real Saving — NG-FMS ATS Core EPP", f_body_bold, C_CYAN)

    # Line 4: • 143 defects analysed + pushed in the EPP
    y4 = 652
    x = 42
    draw_shadowed(t_draw, (x, y4), "•", f_body_bold, C_BULLET)
    x += int(t_draw.textlength("•  ", font=f_body_bold))
    draw_shadowed(t_draw, (x, y4), "143 defects", f_body_bold, C_WHITE)
    x += int(t_draw.textlength("143 defects ", font=f_body_bold))
    draw_shadowed(t_draw, (x, y4), "analysed + pushed in the EPP", f_body_semi, C_WHITE_DIM)

    # Line 5: • Manual push: 143 min (≈1 min per defect)   →   Tool push: ~3 min (one batch)
    y5 = 680
    x = 42
    draw_shadowed(t_draw, (x, y5), "•", f_body_bold, C_BULLET)
    x += int(t_draw.textlength("•  ", font=f_body_bold))
    draw_shadowed(t_draw, (x, y5), "Manual push: ", f_body_semi, C_WHITE_DIM)
    x += int(t_draw.textlength("Manual push: ", font=f_body_semi))
    draw_shadowed(t_draw, (x, y5), "143 min", f_body_bold, C_WHITE)
    x += int(t_draw.textlength("143 min ", font=f_body_bold))
    draw_shadowed(t_draw, (x, y5), "(≈1 min per defect)   →   ", f_body_reg, C_WHITE_DIM)
    x += int(t_draw.textlength("(≈1 min per defect)   →   ", font=f_body_reg))
    draw_shadowed(t_draw, (x, y5), "Tool push: ", f_body_semi, C_WHITE_DIM)
    x += int(t_draw.textlength("Tool push: ", font=f_body_semi))
    draw_shadowed(t_draw, (x, y5), "~3 min", f_body_bold, C_GREEN)
    x += int(t_draw.textlength("~3 min ", font=f_body_bold))
    draw_shadowed(t_draw, (x, y5), "(one batch)", f_body_reg, C_WHITE_DIM)

    # Line 6: • Saved on push: ~140 min ($84) (≈99% faster, 2.4 hrs)
    y6 = 708
    x = 42
    draw_shadowed(t_draw, (x, y6), "•", f_body_bold, C_BULLET)
    x += int(t_draw.textlength("•  ", font=f_body_bold))
    draw_shadowed(t_draw, (x, y6), "Saved on push: ", f_body_semi, C_WHITE_DIM)
    x += int(t_draw.textlength("Saved on push: ", font=f_body_semi))
    draw_shadowed(t_draw, (x, y6), "~140 min ($84)", f_body_bold, C_GREEN)
    x += int(t_draw.textlength("~140 min ($84) ", font=f_body_bold))
    draw_shadowed(t_draw, (x, y6), "(≈99% faster, 2.4 hrs)", f_body_bold, C_GREEN)

    # Line 7: Future Targeted programs are  Datalink(787,AIMS,EPIC), TXD along all CNS products and all other HonAero Departments....
    y7 = 736
    x = 42
    draw_shadowed(t_draw, (x, y7), "Future Targeted programs are  ", f_body_bold, C_CYAN)
    x += int(t_draw.textlength("Future Targeted programs are  ", font=f_body_bold))
    draw_shadowed(t_draw, (x, y7), "Datalink(787,AIMS,EPIC), TXD along all CNS products and all other HonAero Departments....", f_body_semi, C_WHITE_DIM)

    # Composite text layer onto canvas
    final_img = Image.alpha_composite(canvas.convert('RGBA'), text_layer).convert('RGB')
    final_img.save('Coverity_latest_slide.png')
    print('✅ Saved Coverity_latest_slide.png')

build_slide()
