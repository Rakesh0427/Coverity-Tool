"""
Generate Coverity Findings Analyzer slide as an editable PowerPoint.
Updates applied:
  1. Removed Honeywell Aerospace and CNS AI Day 2026 at the top
  2. Removed "for Aerospace" from subtitle
  3. Removed Processing Stage 3 fully and adjusted flow: Rule Engine -> Smart Dispositions
  4. Removed footer with Rakesh Boya and other metadata
"""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
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
ORANGE       = RGBColor(0xFF, 0x6B, 0x00)   # accent orange
ORANGE_LIGHT = RGBColor(0xFF, 0x99, 0x33)
GREEN        = RGBColor(0x00, 0xCC, 0x66)   # accent green
GREEN_LIGHT  = RGBColor(0x33, 0xFF, 0x88)
WHITE        = RGBColor(0xFF, 0xFF, 0xFF)
WHITE_DIM    = RGBColor(0xCC, 0xCC, 0xDD)
GRAY         = RGBColor(0x88, 0x88, 0xAA)
RED_BG       = RGBColor(0x3A, 0x15, 0x15)   # red-tinted cell
GREEN_BG     = RGBColor(0x0F, 0x2E, 0x1A)   # green-tinted cell
RED_TEXT     = RGBColor(0xFF, 0x44, 0x44)
CYAN_GLOW    = RGBColor(0x00, 0xCC, 0xFF)
YELLOW       = RGBColor(0xFF, 0xCC, 0x00)

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

# Robot emoji placeholder - use a circle shape as icon
icon = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(2.6), Inches(0.12),
                              Inches(0.45), Inches(0.45))
icon.fill.solid()
icon.fill.fore_color.rgb = ORANGE
icon.line.fill.background()

# Main title (centered horizontally)
add_text(3.1, 0.05, 7.5, 0.5, "COVERITY FINDINGS ANALYZER",
         font_size=26, color=ORANGE, bold=True,
         alignment=PP_ALIGN.LEFT, font_name='Calibri')

# Subtitle (without "for Aerospace", centered)
add_text(2.0, 0.55, 9.333, 0.4,
         "AI-Developed, Rule-Based Static Analysis",
         font_size=14, color=WHITE_DIM,
         alignment=PP_ALIGN.CENTER, font_name='Calibri')

# ── Horizontal divider ──
divider = add_rect_straight(0.3, 0.95, 12.7, 0.02, ORANGE)

# ══════════════════════════════════════════════
# LEFT COLUMN: CORE FEATURES
# ══════════════════════════════════════════════

# Section header
hdr = add_text(0.4, 1.15, 4.0, 0.35, "  CORE FEATURES",
               font_size=16, color=ORANGE, bold=True, font_name='Calibri')

features = [
    ("Aerospace Compliance", "DO-178C, MISRA, CERT"),
    ("100% Secure & Offline", "Source never leaves machine"),
    ("No AI Tokens Required", "Runs 100% offline"),
    ("Reduces SME Dependency", "80% reduction"),
]

y = 1.55
for title, desc in features:
    add_text(0.5, y, 3.8, 0.22, title, font_size=11, color=WHITE, bold=True)
    add_text(0.5, y + 0.2, 3.8, 0.22, f"  {desc}", font_size=10, color=WHITE_DIM)
    y += 0.6

# ══════════════════════════════════════════════
# MIDDLE COLUMN: WORK DETAILS TABLE
# ══════════════════════════════════════════════

hdr2 = add_text(4.6, 1.15, 3.5, 0.35, "⚖  WORK DETAILS",
                font_size=16, color=ORANGE, bold=True)

table_top = 1.55
col_w = 2.3
row_h = 0.42
tbl_left = 4.6

# Table header row
manual_hdr = add_rect(tbl_left, table_top, col_w, row_h, RED_BG, ORANGE, 1)
manual_hdr.text_frame.text = "MANUAL"
manual_hdr.text_frame.paragraphs[0].font.size = Pt(11)
manual_hdr.text_frame.paragraphs[0].font.color.rgb = RED_TEXT
manual_hdr.text_frame.paragraphs[0].font.bold = True
manual_hdr.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

tool_hdr = add_rect(tbl_left + col_w + 0.05, table_top, col_w, row_h, GREEN_BG, ORANGE, 1)
tool_hdr.text_frame.text = "WITH TOOL"
tool_hdr.text_frame.paragraphs[0].font.size = Pt(11)
tool_hdr.text_frame.paragraphs[0].font.color.rgb = GREEN
tool_hdr.text_frame.paragraphs[0].font.bold = True
tool_hdr.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

# Table rows
rows = [
    ("⏱ 10-15 min / defect",    "⚡ 1-2 min / defect"),
    ("🔍 Source Code Investigation Required", "🤖 Automated Analysis"),
    ("🧠 Context Analysis Required",         "✅ One Controlled Flow"),
    ("📝 Disposition & Documentation Required", "📊 Higher Quality"),
]

y = table_top + row_h + 0.04
for manual, tool in rows:
    r1 = add_rect(tbl_left, y, col_w, row_h, RED_BG)
    r1.text_frame.text = manual
    r1.text_frame.paragraphs[0].font.size = Pt(9)
    r1.text_frame.paragraphs[0].font.color.rgb = WHITE_DIM
    r1.text_frame.word_wrap = True

    r2 = add_rect(tbl_left + col_w + 0.05, y, col_w, row_h, GREEN_BG)
    r2.text_frame.text = tool
    r2.text_frame.paragraphs[0].font.size = Pt(9)
    r2.text_frame.paragraphs[0].font.color.rgb = WHITE
    r2.text_frame.word_wrap = True
    y += row_h + 0.04

# ~90% Time Reduction callout
callout_y = y + 0.08
add_text(tbl_left + 0.3, callout_y, 2.5, 0.5, "~90%",
         font_size=28, color=ORANGE, bold=True, font_name='Calibri')
add_text(tbl_left + 0.3, callout_y + 0.38, 2.5, 0.3, "Time Reduction",
         font_size=11, color=WHITE_DIM)

# ══════════════════════════════════════════════
# BOTTOM LEFT: COST SAVINGS
# ══════════════════════════════════════════════

cost_top = 4.85
add_text(0.4, cost_top, 4.5, 0.35, "💰  COST SAVINGS PER PROGRAM",
         font_size=14, color=ORANGE, bold=True)

cost_items = [
    ("RL1 (1,000 defects): 250 hrs → 33 hrs = ", "217 hrs SAVED ", "*($7k)*"),
    ("Program (4,000 defects): 1,000 hrs → 133 hrs = ", "867 hrs SAVED ", "*($30k)*"),
]
y = cost_top + 0.32
for prefix, saved, cost in cost_items:
    add_text(0.5, y, 4.8, 0.25, prefix, font_size=11, color=WHITE)
    add_text(4.4, y, 1.8, 0.25, saved, font_size=11, color=ORANGE, bold=True)
    add_text(5.6, y, 1.5, 0.25, cost, font_size=11, color=YELLOW, bold=True)
    y += 0.25

# Real Saving — NG-FMS ATS Core EPP
add_text(0.5, y + 0.05, 6.5, 0.25, "Real Saving — NG-FMS ATS Core EPP",
         font_size=12, color=CYAN_GLOW, bold=True)
y += 0.30

add_text(0.5, y, 6.5, 0.22, "• 143 defects analysed + pushed in the EPP",
         font_size=10, color=WHITE)
y += 0.22

add_text(0.5, y, 6.5, 0.22, "• Manual push: 143 min (≈1 min per defect)   →   Tool push: ~3 min (one batch)",
         font_size=10, color=WHITE_DIM)
y += 0.22

add_text(0.5, y, 6.5, 0.22, "• Saved on push: ~140 min ($84) (≈99% faster, 2.4 hrs)",
         font_size=10, color=GREEN_LIGHT, bold=True)
y += 0.28

# Future Targeted programs
add_text(0.5, y, 12.0, 0.25,
         "Future Targeted programs are  Datalink(787,AIMS,EPIC), TXD along all CNS products and all other HonAero Departments....",
         font_size=10, color=ORANGE_LIGHT, bold=True)

# ══════════════════════════════════════════════
# RIGHT SIDE: FLOW DIAGRAM (Adjusted: Stage 1 -> Stage 2 -> Smart Dispositions)
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

# Curved arrow: Source Parser → Rule Engine (down-right)
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

# Adjusted flow: Rule Engine → Smart Dispositions (direct curve/down-right into Output)
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
