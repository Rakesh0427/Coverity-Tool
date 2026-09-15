"""Create the slide background: Coverity_Final_Slide.png with all editable
text glyphs inpainted away (icons, tables, arrows, glows, bullets kept), so
the rebuilt PPTX can overlay editable text boxes while looking identical to
the PNG.  Text rects are measured from the PNG itself and inpainted with
OpenCV; see rebuild_final_slide.py for the shared logic.

Usage:  python3 make_slide_background.py [out.png]
"""
import sys
from PIL import Image

from rebuild_final_slide import build_background, measure_targets

SRC = 'Coverity_Final_Slide.png'
OUT = sys.argv[1] if len(sys.argv) > 1 else '/tmp/slide_bg.png'


def main():
    img = Image.open(SRC).convert('RGB')
    build_background(img, measure_targets(img), OUT)
    print('wrote', OUT)


if __name__ == '__main__':
    main()
