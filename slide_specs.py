"""Shared specs for rebuilding Coverity_Final_Slide_Updated.pptx to match
Coverity_Final_Slide.png exactly.

Coordinate system: pixels of the 1280x768 source PNG.
Slide is 13.333in x 7.5in  ->  x_in = px/96.0 ; y_in = px/102.4
Font sizes: vertical px -> pt via 72/102.4.
"""

XI = 1.0 / 96.0     # px -> inches (horizontal)
YI = 1.0 / 102.4    # px -> inches (vertical)
PT = 72.0 / 102.4   # px (em height, vertical) -> points

ORANGE_HDR = (238, 110, 30)     # section headers / CNS AI Day
ORANGE_LT = (246, 150, 45)      # banner + "hrs SAVED"
WHITE = (249, 251, 252)

# Rectangles (x0, y0, x1, y1) whose TEXT GLYPHS must be inpainted out of the
# PNG so they can be re-drawn as editable text boxes.  Icons / tables /
# arrows / glows stay baked into the background.
INPAINT_RECTS = [
    (38, 18, 368, 56),        # Honeywell Aerospace
    (1120, 20, 1280, 54),     # CNS AI Day 2026 (clipped at right edge)
    (280, 84, 1182, 142, 'lum'),  # title glyphs only (keep glow)
    (288, 150, 1088, 190),    # subtitle
    (84, 220, 335, 252),      # CORE FEATURES
    (74, 266, 340, 322),      # feat 1 + sub
    (74, 334, 380, 390),      # feat 2 + sub
    (74, 400, 340, 456),      # feat 3 + sub
    (74, 466, 380, 520),      # feat 4 + sub
    (450, 220, 825, 252),     # MANUAL vs AUTOMATED
    (430, 270, 600, 295),     # MANUAL PROCESS header text
    (672, 270, 874, 295),     # AUTOMATED PROCESS header text
    (425, 308, 628, 335),     # man row1
    (425, 341, 628, 395),     # man row2 (2 lines)
    (425, 396, 628, 425),     # man row3
    (425, 431, 628, 486),     # man row4 (2 lines)
    (678, 308, 866, 336),     # auto row1
    (678, 348, 866, 378),     # auto row2
    (678, 394, 866, 424),     # auto row3
    (678, 434, 866, 464),     # auto row4
    (445, 494, 818, 531),     # ~90% Time Reduction banner text
    (1150, 218, 1280, 268),   # top-right note (clipped)
    (908, 383, 1020, 433),    # HTML/Excel Reports
    (1035, 494, 1192, 572),   # Rules Engine block
    (1150, 596, 1280, 660),   # Smart Dispositions (clipped)
    (990, 624, 1185, 676),    # bottom note
    (88, 568, 555, 600),      # COST SAVINGS PER PROGRAM
    (78, 612, 742, 646),      # cost line 1
    (78, 648, 828, 682),      # cost line 2
    (78, 684, 615, 718),      # cost line 3
    (310, 740, 1062, 766),    # footer
]

# Editable text lines: (x0, y0, x1, y1, align, runs...)
# run = (text, em_px, bold, colorkey)  colorkey: W white, O orange, L light orange
LINES = [
    (42, 23, 368, 52, 'l', [("Honeywell ", 27, True, 'W'), ("Aerospace", 27, False, 'W')]),
    (1125, 25, 1292, 50, 'l', [("CNS AI Day 2026", 24, True, 'O')]),
    (286, 90, 1177, 132, 'c', [("COVERITY FINDINGS ANALYZER", 56, True, 'W')]),
    (293, 154, 1082, 186, 'c', [("AI-Developed, Rule-Based Static Analysis for Aerospace", 26, False, 'W')]),
    (88, 225, 330, 248, 'l', [("CORE FEATURES", 27, True, 'O')]),
    (78, 270, 334, 294, 'l', [("Aerospace Compliance", 21, True, 'W')]),
    (79, 296, 333, 320, 'l', [("- DO-178C, MISRA, CERT", 19, False, 'W')]),
    (80, 338, 324, 360, 'l', [("100% Secure & Offline", 21, True, 'W')]),
    (79, 367, 375, 388, 'l', [("- Source never leaves machine", 19, False, 'W')]),
    (80, 405, 329, 428, 'l', [("No AI Tokens Required", 21, True, 'W')]),
    (79, 434, 270, 452, 'l', [("- Runs 100% offline", 19, False, 'W')]),
    (80, 473, 375, 495, 'l', [("Reduces SME Dependency", 21, True, 'W')]),
    (79, 498, 272, 520, 'l', [("- 80% reduction", 19, False, 'W')]),
    (455, 225, 821, 248, 'l', [("MANUAL vs AUTOMATED", 27, True, 'O')]),
    (433, 275, 593, 290, 'l', [("MANUAL PROCESS", 19, True, 'W')]),
    (677, 275, 871, 290, 'l', [("AUTOMATED PROCESS", 19, True, 'W')]),
    (429, 313, 620, 331, 'l', [("10-15 minutes per defect", 17, False, 'W')]),
    (428, 346, 528, 361, 'l', [("Source Code", 17, False, 'W')]),
    (429, 368, 599, 386, 'l', [("Investigation Required", 17, False, 'W')]),
    (429, 400, 625, 422, 'l', [("Context Analysis Required", 17, False, 'W')]),
    (428, 435, 545, 455, 'l', [("Disposition &", 16, False, 'W')]),
    (428, 460, 618, 478, 'l', [("Documentation Required", 17, False, 'W')]),
    (683, 314, 857, 332, 'l', [("1-2 minutes per defect", 17, False, 'W')]),
    (681, 356, 835, 374, 'l', [("Automated Analysis", 17, False, 'W')]),
    (682, 397, 841, 412, 'l', [("One Controlled Flow", 17, False, 'W')]),
    (682, 439, 792, 457, 'l', [("Higher Quality", 17, False, 'W')]),
    (450, 498, 815, 527, 'c', [("~90% Time Reduction", 30, True, 'L')]),
    (1156, 223, 1280, 236, 'l', [("* AI used to DEVELOP,", 16, False, 'W')]),
    (1156, 242, 1280, 259, 'l', [("analysis is RULE-BASED", 16, False, 'W')]),
    (913, 387, 1014, 402, 'c', [("HTML/Excel", 20, True, 'W')]),
    (930, 410, 997, 429, 'c', [("Reports", 20, True, 'W')]),
    (1054, 500, 1180, 522, 'c', [("Rules Engine", 20, True, 'W')]),
    (1059, 523, 1173, 544, 'c', [("AI Developed", 20, True, 'W')]),
    (1044, 548, 1189, 562, 'c', [("20+ Checker Rules", 17, False, 'W')]),
    (1164, 600, 1277, 622, 'l', [("Smart", 20, True, 'W')]),
    (1178, 626, 1280, 652, 'l', [("Dispositions", 20, True, 'W')]),
    (995, 628, 1175, 648, 'l', [("AI used to DEVELOP,", 16, False, 'W')]),
    (993, 652, 1180, 672, 'l', [("analysis is RULE-BASED", 16, False, 'W')]),
    (93, 573, 550, 596, 'l', [("COST SAVINGS PER PROGRAM", 27, True, 'O')]),
    (83, 616, 737, 642, 'l', [("RL1 (1,000 defects): 250 hrs \u2192 33 hrs = ", 21, False, 'W'),
                              ("217 hrs SAVED", 21, True, 'L')]),
    (83, 652, 820, 678, 'l', [("Program (4,000 defects): 1000 hrs \u2192 133 hrs = ", 21, False, 'W'),
                              ("867 hrs SAVED", 21, True, 'L')]),
    (83, 687, 610, 714, 'l', [("Cost: $7,595 - $30,345 per release (at $30/hr)", 21, False, 'W')]),
    (315, 743, 1056, 761, 'c', [("Rakesh Boya | Tool Owner & Developer | Honeywell Aerospace | CNS AI Day 2026 | Confidential", 17, False, 'W')]),
]
