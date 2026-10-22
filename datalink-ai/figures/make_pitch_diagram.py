"""Generate the one-slide 'how it works' block diagram for the DATALINK pitch."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

NAVY  = "#1F3864"
TEAL  = "#0E7C7B"
AMBER = "#C55A11"
GREY  = "#5A6474"
LIGHT = "#F4F7FB"
CARD  = "#EAF1F8"

fig, ax = plt.subplots(figsize=(13.6, 7.65), dpi=160)
ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")
fig.patch.set_facecolor("white")


def box(x, y, w, h, fc, ec, lw=1.4, r=1.1, z=2):
    p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                       fc=fc, ec=ec, lw=lw, zorder=z)
    ax.add_patch(p)
    return p


def txt(x, y, s, size=9, color="#1b1b1b", weight="normal", ha="left", va="center", style="normal"):
    ax.text(x, y, s, fontsize=size, color=color, weight=weight, ha=ha, va=va,
            style=style, zorder=5)


# ---------------- title ----------------
txt(50, 96.4, "HOW IT WORKS — four steps, one mechanism", 19, NAVY, "bold", "center")
txt(50, 91.6, "Ground-based. Reads what the aircraft already sends. No new avionics, no change to certified software.",
    10.5, GREY, "normal", "center", style="italic")

# ---------------- panel 1: inputs ----------------
box(1.5, 20.5, 27, 62, LIGHT, "#C9D6E6", 1.4)
txt(15, 79.6, "WHAT WE READ", 10.5, NAVY, "bold", "center")
txt(15, 75.4, "(data that already exists)", 8, GREY, "normal", "center", style="italic")

inputs = [
    ("CMU / ATSU message timestamps", "every uplink & downlink, per hop"),
    ("Network & radio logs", "CSP, SATCOM / VHF, handover points"),
    ("Aircraft configuration", "AOC database revision, software load"),
    ("Crew response times", "when the pilot actually answered"),
]
y = 66.5
for head, sub in inputs:
    box(3.5, y - 4.2, 23, 9.2, "white", "#C9D6E6", 1.0, 0.7)
    txt(5, y + 1.7, head, 8.6, NAVY, "bold")
    txt(5, y - 1.9, sub, 7.6, GREY)
    y -= 12.3

# ---------------- panel 2: engine ----------------
box(31.5, 20.5, 37, 62, "#E7F1F7", NAVY, 2.0)
txt(50, 79.6, "THE VERDICT ENGINE", 12, NAVY, "bold", "center")
txt(50, 75.4, "deterministic — it decides; AI only explains", 8.2, GREY, "normal", "center", style="italic")

steps = [
    ("1", "CHECK", "pass/fail per transaction  +  the margin:\n“conforming — 62% of the 240 s already used”", TEAL),
    ("2", "ATTRIBUTE", "split the elapsed time: network · radio ·\nthe aircraft’s own computer · crew", AMBER),
    ("3", "PREDICT", "watch the margin decay — warn while still\nlegal, with a projected breach date", "#7B3FA0"),
    ("4", "PROVE", "hash-chained, replayable evidence pack\nper flight, per tail", NAVY),
]
y = 73.4
for num, head, body, col in steps:
    box(33.5, y - 11.2, 33, 11.2, "white", col, 1.5, 0.9)
    ax.add_patch(plt.Circle((36.4, y - 2.4), 1.5, fc=col, ec="none", zorder=4))
    txt(36.4, y - 2.45, num, 8.5, "white", "bold", "center")
    txt(38.7, y - 2.4, head, 10.2, col, "bold")
    txt(35.2, y - 7.1, body, 8.0, "#242424", va="center")
    y -= 12.7

# ---------------- panel 3: outputs ----------------
box(71, 20.5, 27.5, 62, LIGHT, "#C9D6E6", 1.4)
txt(84.75, 79.6, "WHAT YOU GET", 10.5, NAVY, "bold", "center")
txt(84.75, 75.4, "(on a screen, in minutes)", 8, GREY, "normal", "center", style="italic")

outputs = [
    ("Live verdict per flight", "not a monthly spreadsheet"),
    ("A named cause", "not “datalink problem”"),
    ("Warning before the complaint", "weeks, not quarters"),
    ("Proof you can hand over", "airline, OEM, regulator"),
]
y = 66.5
for head, sub in outputs:
    box(73, y - 4.2, 23.5, 9.2, "white", "#C9D6E6", 1.0, 0.7)
    txt(74.5, y + 1.7, head, 8.6, NAVY, "bold")
    txt(74.5, y - 1.9, sub, 7.6, GREY)
    y -= 12.3

# ---------------- arrows ----------------
for yy in (62.0, 47.0, 32.0):
    ax.add_patch(FancyArrowPatch((28.8, yy), (31.2, yy), arrowstyle="-|>", mutation_scale=13,
                                 lw=1.6, color=NAVY, zorder=3))
    ax.add_patch(FancyArrowPatch((68.8, yy), (70.8, yy), arrowstyle="-|>", mutation_scale=13,
                                 lw=1.6, color=NAVY, zorder=3))

# ---------------- benefit band ----------------
box(1.5, 2.5, 97, 14.5, "white", NAVY, 1.5)
txt(3.6, 13.2, "WHO BENEFITS", 9.2, NAVY, "bold")

ben = [
    ("AIRLINE", "fewer false removals · fewer AOGs ·\nPBCS proved per flight", TEAL),
    ("OEM  (Honeywell)", "defects known before the customer calls ·\ntargeted fleet actions, not blanket ones", AMBER),
    ("ANSP / CSP / REGULATOR", "cause lands on the right party ·\nno more multi-month problem-report loop", NAVY),
]
x = 3.6
for head, body, col in ben:
    txt(x, 9.4, head, 9.0, col, "bold")
    txt(x, 5.6, body, 7.8, "#242424")
    x += 32.0

fig.savefig("figures/fig_pitch_flow.png", bbox_inches="tight", pad_inches=0.16, facecolor="white")
fig.savefig("figures/fig_pitch_flow.svg", bbox_inches="tight", pad_inches=0.16, facecolor="white")
print("ok")
