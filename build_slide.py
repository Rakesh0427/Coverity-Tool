"""
Generate Coverity Findings Analyzer slide as an editable PowerPoint.
Updates applied:
  1. Reduced CORE FEATURES and WORK DETAILS sections proportionally.
  2. Section headers (CORE FEATURES, WORK DETAILS, COST SAVINGS PER PROGRAM)
     share the exact same font size (15pt Bold Orange).
  3. Typography under COST SAVINGS PER PROGRAM matches CORE FEATURES.
  4. "Deployed in — NG-FMS ATS Core EPP" replaces "Real Saving".
  5. "143 defects pushed in the EPP" (removed "analysed +").
  6. $7k, $30k, and $84 are prominently highlighted in gold pill badges with star accents.
  7. Last line reviewed and properly formatted:
     "Future Targeted Programs: Datalink (787, AIMS, EPIC), TXD across all CNS products, and all other HonAero Departments..."
"""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
import os

# ── Presentation setup ──
prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)

# ── Color palette (aerospace dark theme) ──
BG_DARK      = RGBColor(0x0A, 0x0E, 0x1A)   # deep navy-black
BG_CARD      = RGBColor(0x11, 0x18, 0x2E)   # slightly lighter card
ORANGE       = RGBColor(0xFA, 0x70, 0x24)   # accent orange
ORANGE_LIGHT = RGBColor(0xFF, 0x99, 0x33)
GREEN        = RGBColor(0x00, 0xCC, 0x66)   # accent green
GREEN_LIGHT  = RGBColor(0x32, 0xFF, 0x82)
WHITE        = RGBColor(0xFF, 0xFF, 0xFF)
WHITE_DIM    = RGBColor(0xD7, 0xDE, 0xEB)
GRAY         = RGBColor(0x88, 0x88, 0xAA)
RED_BG       = RGBColor(0x3A, 0x15, 0x15)   # red-tinted cell
GREEN_BG     = RGBColor(0x0F, 0x2E, 0x1A)   # green-tinted cell
RED_TEXT     = RGBColor(0xFF, 0x55, 0x55)
CYAN_GLOW    = RGBColor(0x00, 0xE5, 0xFF)
GOLD_YELLOW  = RGBColor(0xFF, 0xE1, 0x14)
GOLD_BG      = RGBColor(0x23, 0x1C, 0x05)

slide_layout = prs.slide_layouts[6]  # blank
slide = prs.slides.add_slide(slide_layout)

# ── Background ──
bg = slide.background
fill = bg.fill
fill.solid()
fill.fore_color.rgb = BG_DARK

# ── Helper: add text box ──
def add_text(left, top, width, height, text, font_size=14,
             color=WHITE, bold=False, alignment=PP_ALIGN.LEFT,
             font_name='Calibri', anchor=MSO_ANCHOR.TOP):
    txBox = slide.shapes.add_textbox(Inches(left), Inches(top),
                                     Inches(width), Inches(height))
    tf = txBox.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(font_size)
    p.font.color.rgb = color
    p.font.bold = bold
    p.font.name = font_name
    p.alignment = alignment
    return txBox

# ── Helper: add rectangle with fill ──
def add_rect(left, top, width, height, fill_color, border_color=None, border_width=None):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                   Inches(left), Inches(top),
                                   Inches(width), Inches(height))
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    if border_color:
        shape.line.color.rgb = border_color
        shape.line.width = Pt(border_width or 1)
    else:
        shape.line.fill.background()
    return shape

def add_rect_straight(left, top, width, height, fill_color, border_color=None, border_width=None):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                   Inches(left), Inches(top),
                                   Inches(width), Inches(height))
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    if border_color:
        shape.line.color.rgb = border_color
        shape.line.width = Pt(border_width or 1)
    else:
        shape.line.fill.background()
    return shape

# ══════════════════════════════════════════════
# TITLE AREA
# ══════════════════════════════════════════════

# Robot icon placeholder
icon = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(2.6), Inches(0.12),
                              Inches(0.45), Inches(0.45))
icon.fill.solid()
icon.fill.fore_color.rgb = ORANGE
icon.line.fill.background()

# Main title
add_text(3.1, 0.05, 7.5, 0.5, "COVERITY FINDINGS ANALYZER",
         font_size=26, color=ORANGE, bold=True,
         alignment=PP_ALIGN.LEFT, font_name='Calibri')

# Subtitle
add_text(2.0, 0.55, 9.333, 0.4,
         "AI-Developed, Rule-Based Static Analysis",
         font_size=14, color=WHITE_DIM,
         alignment=PP_ALIGN.CENTER, font_name='Calibri')

# Divider
divider = add_rect_straight(0.3, 0.95, 12.7, 0.02, ORANGE)

# Common section header font size
SECTION_HDR_SIZE = 15

# ══════════════════════════════════════════════
# LEFT COLUMN: CORE FEATURES (Reduced & Compact)
# ══════════════════════════════════════════════

hdr1 = add_text(0.4, 1.15, 3.6, 0.35, "🎯  CORE FEATURES",
                font_size=SECTION_HDR_SIZE, color=ORANGE, bold=True, font_name='Calibri')

features = [
    ("Aerospace Compliance", "DO-178C, MISRA, CERT"),
    ("100% Secure & Offline", "Source never leaves machine"),
    ("No AI Tokens Required", "Runs 100% offline"),
    ("Reduces SME Dependency", "80% reduction"),
]

y = 1.55
for title, desc in features:
    add_text(0.5, y, 3.5, 0.22, title, font_size=10.5, color=WHITE, bold=True)
    add_text(0.5, y + 0.18, 3.5, 0.20, f"- {desc}", font_size=9.5, color=WHITE_DIM)
    y += 0.50

# ══════════════════════════════════════════════
# MIDDLE COLUMN: WORK DETAILS TABLE (Reduced & Compact)
# ══════════════════════════════════════════════

hdr2 = add_text(4.2, 1.15, 3.5, 0.35, "⚖  WORK DETAILS",
                font_size=SECTION_HDR_SIZE, color=ORANGE, bold=True)

table_top = 1.55
col_w = 1.85
row_h = 0.36
tbl_left = 4.2

# Table header row
manual_hdr = add_rect(tbl_left, table_top, col_w, row_h, RED_BG, ORANGE, 1)
manual_hdr.text_frame.text = "MANUAL"
manual_hdr.text_frame.paragraphs[0].font.size = Pt(10)
manual_hdr.text_frame.paragraphs[0].font.color.rgb = RED_TEXT
manual_hdr.text_frame.paragraphs[0].font.bold = True
manual_hdr.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

tool_hdr = add_rect(tbl_left + col_w + 0.05, table_top, col_w, row_h, GREEN_BG, ORANGE, 1)
tool_hdr.text_frame.text = "WITH TOOL"
tool_hdr.text_frame.paragraphs[0].font.size = Pt(10)
tool_hdr.text_frame.paragraphs[0].font.color.rgb = GREEN
tool_hdr.text_frame.paragraphs[0].font.bold = True
tool_hdr.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

# Table rows
rows = [
    ("10-15 minutes\nper defect",               "1-2 minutes\nper defect"),
    ("Source Code Investigation\nRequired",     "Automated\nAnalysis"),
    ("Context Analysis\nRequired",              "One Controlled\nFlow"),
    ("Disposition &\nDocumentation Required",    "Higher\nQuality"),
]

y_row = table_top + row_h + 0.04
for manual, tool in rows:
    r1 = add_rect(tbl_left, y_row, col_w, row_h, RED_BG)
    r1.text_frame.text = manual
    r1.text_frame.paragraphs[0].font.size = Pt(8.5)
    r1.text_frame.paragraphs[0].font.color.rgb = WHITE_DIM
    r1.text_frame.word_wrap = True

    r2 = add_rect(tbl_left + col_w + 0.05, y_row, col_w, row_h, GREEN_BG)
    r2.text_frame.text = tool
    r2.text_frame.paragraphs[0].font.size = Pt(8.5)
    r2.text_frame.paragraphs[0].font.color.rgb = WHITE
    r2.text_frame.word_wrap = True
    y_row += row_h + 0.04

# ~90% Time Reduction callout
callout_y = y_row + 0.04
add_text(tbl_left + 1.2, callout_y, 2.5, 0.4, "~90%",
         font_size=24, color=ORANGE, bold=True, font_name='Calibri')
add_text(tbl_left + 1.2, callout_y + 0.32, 2.5, 0.25, "Time Reduction",
         font_size=10, color=WHITE_DIM)

# ══════════════════════════════════════════════
# BOTTOM LEFT: COST SAVINGS PER PROGRAM
# ══════════════════════════════════════════════

cost_top = 4.80
# EXACT same font size as CORE FEATURES and WORK DETAILS
add_text(0.4, cost_top, 5.5, 0.35, "💰  COST SAVINGS PER PROGRAM",
         font_size=SECTION_HDR_SIZE, color=ORANGE, bold=True)

# Line 1: RL1
y_c = cost_top + 0.36
add_text(0.4, y_c, 3.4, 0.25, "RL1 (1,000 defects): 250 hrs → 33 hrs =",
         font_size=11, color=WHITE)
add_text(3.7, y_c, 1.5, 0.25, "217 hrs SAVED",
         font_size=11, color=ORANGE, bold=True)
# Highlighted enlarged badge for $7k
b1 = add_rect(5.2, y_c - 0.04, 1.2, 0.28, GOLD_BG, GOLD_YELLOW, 1.5)
b1.text_frame.text = "★ ($7k) ★"
b1.text_frame.paragraphs[0].font.size = Pt(12)
b1.text_frame.paragraphs[0].font.color.rgb = GOLD_YELLOW
b1.text_frame.paragraphs[0].font.bold = True
b1.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

# Line 2: Program
y_c += 0.32
add_text(0.4, y_c, 3.7, 0.25, "Program (4,000 defects): 1000 hrs → 133 hrs =",
         font_size=11, color=WHITE)
add_text(4.0, y_c, 1.5, 0.25, "867 hrs SAVED",
         font_size=11, color=ORANGE, bold=True)
# Highlighted enlarged badge for $30k
b2 = add_rect(5.5, y_c - 0.04, 1.3, 0.28, GOLD_BG, GOLD_YELLOW, 1.5)
b2.text_frame.text = "★ ($30k) ★"
b2.text_frame.paragraphs[0].font.size = Pt(12)
b2.text_frame.paragraphs[0].font.color.rgb = GOLD_YELLOW
b2.text_frame.paragraphs[0].font.bold = True
b2.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

# Line 3: Deployed in — NG-FMS ATS Core EPP
y_c += 0.32
add_text(0.4, y_c, 6.5, 0.25, "Deployed in — NG-FMS ATS Core EPP",
         font_size=11.5, color=CYAN_GLOW, bold=True)

# Line 4: • 143 defects pushed in the EPP
y_c += 0.26
add_text(0.4, y_c, 6.5, 0.22, "• 143 defects pushed in the EPP",
         font_size=10.5, color=WHITE)

# Line 5: • Manual push vs Tool push
y_c += 0.24
add_text(0.4, y_c, 7.5, 0.22, "• Manual push: 143 min (≈1 min per defect)   →   Tool push: ~3 min (one batch)",
         font_size=10.5, color=WHITE_DIM)

# Line 6: • Saved on push: ~140 min  ★ ($84) ★  (≈99% faster, 2.4 hrs)
y_c += 0.24
add_text(0.4, y_c, 2.5, 0.22, "• Saved on push: ~140 min",
         font_size=10.5, color=GREEN_LIGHT, bold=True)
# Highlighted dollar number for $84 like above
b3 = add_rect(2.9, y_c - 0.04, 1.1, 0.26, GOLD_BG, GOLD_YELLOW, 1.5)
b3.text_frame.text = "★ ($84) ★"
b3.text_frame.paragraphs[0].font.size = Pt(11)
b3.text_frame.paragraphs[0].font.color.rgb = GOLD_YELLOW
b3.text_frame.paragraphs[0].font.bold = True
b3.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

add_text(4.1, y_c, 3.5, 0.22, "(≈99% faster, 2.4 hrs)",
         font_size=10.5, color=GREEN_LIGHT, bold=True)

# Line 7: Future Targeted programs (Reviewed & properly formatted)
y_c += 0.28
add_text(0.4, y_c, 12.5, 0.25,
         "Future Targeted Programs: Datalink (787, AIMS, EPIC), TXD across all CNS products, and all other HonAero Departments...",
         font_size=10.5, color=CYAN_GLOW, bold=True)

# ══════════════════════════════════════════════
# RIGHT SIDE: FLOW DIAGRAM (Stage 1 -> Stage 2 -> Smart Dispositions)
# ══════════════════════════════════════════════

flow_left = 8.2

# --- Input box: Coverity report ---
input_box = add_rect(flow_left, 1.4, 1.6, 1.2, BG_CARD, CYAN_GLOW, 1.5)
tf = input_box.text_frame
tf.vertical_anchor = MSO_ANCHOR.MIDDLE
p = tf.paragraphs[0]
p.text = "📄"
p.font.size = Pt(22)
p.alignment = PP_ALIGN.CENTER
p2 = tf.add_paragraph()
p2.text = "Coverity"
p2.font.size = Pt(10)
p2.font.color.rgb = WHITE
p2.alignment = PP_ALIGN.CENTER
p3 = tf.add_paragraph()
p3.text = "report"
p3.font.size = Pt(10)
p3.font.color.rgb = WHITE
p3.alignment = PP_ALIGN.CENTER

add_text(flow_left, 1.15, 1.6, 0.25, "Input",
         font_size=9, color=WHITE_DIM, alignment=PP_ALIGN.CENTER)

# Arrow: Input → Source Parser
arrow1 = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW,
                                Inches(flow_left + 1.5), Inches(1.85),
                                Inches(0.7), Inches(0.3))
arrow1.fill.solid()
arrow1.fill.fore_color.rgb = ORANGE
arrow1.line.fill.background()

# --- Stage 1: Source Parser ---
stage1_x = flow_left + 2.1
s1 = add_rect(stage1_x, 1.4, 2.0, 1.2, BG_CARD, CYAN_GLOW, 1.5)
tf = s1.text_frame
tf.vertical_anchor = MSO_ANCHOR.MIDDLE
p = tf.paragraphs[0]
p.text = "🌳"
p.font.size = Pt(20)
p.alignment = PP_ALIGN.CENTER
p2 = tf.add_paragraph()
p2.text = "Tree-sitter"
p2.font.size = Pt(10)
p2.font.color.rgb = CYAN_GLOW
p2.alignment = PP_ALIGN.CENTER

add_text(stage1_x - 0.3, 1.0, 2.6, 0.2, "Processing Stage 1",
         font_size=9, color=WHITE_DIM, alignment=PP_ALIGN.CENTER)
add_text(stage1_x - 0.3, 1.15, 2.6, 0.3, "Source Parser",
         font_size=12, color=WHITE, bold=True, alignment=PP_ALIGN.CENTER)

# Curved arrow: Source Parser → Rule Engine
arrow2 = slide.shapes.add_shape(MSO_SHAPE.DOWN_ARROW,
                                Inches(stage1_x + 0.9), Inches(2.55),
                                Inches(0.3), Inches(0.5))
arrow2.fill.solid()
arrow2.fill.fore_color.rgb = ORANGE
arrow2.line.fill.background()

# --- Stage 2: Rule Engine ---
stage2_x = flow_left + 2.1
s2 = add_rect(stage2_x, 3.0, 2.4, 1.2, BG_CARD, ORANGE, 1.5)
tf = s2.text_frame
tf.vertical_anchor = MSO_ANCHOR.MIDDLE
p = tf.paragraphs[0]
p.text = "⚙️"
p.font.size = Pt(20)
p.alignment = PP_ALIGN.CENTER
p2 = tf.add_paragraph()
p2.text = "Rule Engine"
p2.font.size = Pt(12)
p2.font.color.rgb = ORANGE
p2.font.bold = True
p2.alignment = PP_ALIGN.CENTER
p3 = tf.add_paragraph()
p3.text = "20+ Checker Rules"
p3.font.size = Pt(9)
p3.font.color.rgb = WHITE_DIM
p3.alignment = PP_ALIGN.CENTER

add_text(stage2_x - 0.3, 2.7, 3.0, 0.25, "Processing Stage 2",
         font_size=9, color=WHITE_DIM, alignment=PP_ALIGN.CENTER)

# Flow: Rule Engine → Smart Dispositions
arrow3 = slide.shapes.add_shape(MSO_SHAPE.DOWN_ARROW,
                                Inches(stage2_x + 1.0), Inches(4.2),
                                Inches(0.35), Inches(0.5))
arrow3.fill.solid()
arrow3.fill.fore_color.rgb = ORANGE
arrow3.line.fill.background()

# --- Output: Smart Dispositions ---
out_x = flow_left + 2.3
out_box = add_rect(out_x, 4.8, 2.0, 1.2, BG_CARD, GREEN, 1.5)
tf = out_box.text_frame
tf.vertical_anchor = MSO_ANCHOR.MIDDLE
p = tf.paragraphs[0]
p.text = "✅"
p.font.size = Pt(22)
p.alignment = PP_ALIGN.CENTER
p2 = tf.add_paragraph()
p2.text = "Smart"
p2.font.size = Pt(11)
p2.font.color.rgb = GREEN
p2.font.bold = True
p2.alignment = PP_ALIGN.CENTER
p3 = tf.add_paragraph()
p3.text = "Dispositions"
p3.font.size = Pt(11)
p3.font.color.rgb = GREEN
p3.alignment = PP_ALIGN.CENTER

# ─ Key message below flow ──
add_text(flow_left - 0.5, 6.2, 5.5, 0.3,
         "AI used to DEVELOP, analysis is RULE-BASED",
         font_size=13, color=WHITE_DIM, bold=True,
         alignment=PP_ALIGN.CENTER, font_name='Calibri')

# ══════════════════════════════════════════════
# SAVE
# ══════════════════════════════════════════════

output_path = "/home/user/Coverity-Tool/Coverity_Findings_Analyzer.pptx"
prs.save(output_path)
print(f"✅ Saved: {output_path}")
print(f"   File size: {os.path.getsize(output_path)} bytes")
