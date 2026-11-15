"""Two-part 3D-printable enclosure for the ESP32 WS2812B controller (110 x 85 mm PCB).

Run with CadQuery 2.x:  python enclosure.py [output_dir]
Writes base/lid/plunger as STEP and STL.

Coordinates: origin at the PCB's bottom-left corner (KiCad x=87, y=143), +y toward
the USB-C / antenna edge, z=0 at the underside of the enclosure floor.
"""
import os
import sys

import cadquery as cq

# ---- Board data (from kicad/esp32_led_controller.kicad_pcb) -----------------
PCB_W, PCB_H, PCB_T = 110.0, 85.0, 1.6
HOLES = [(4.0, 81.0), (106.0, 81.0), (4.0, 4.0), (105.5, 18.0)]  # H1, H2, H3, H4
USB_X = 30.0                         # J6 centre; receptacle face at y = 86.05
USB_Z_OFF = 1.63                     # plug centre above PCB top (3.26 mm shell)
BARREL_Y = (40.5, 49.5)              # J2 body; face at x = -0.1
BARREL_TOP = 10.7                    # J2 height above PCB top
J1_PINS_Y = (17.92, 23.0)            # power-in screw terminal, wire entry at -x
OUT_PIN1_X = [42.0, 59.5, 77.0, 94.5]  # J4, J5, J7, J8 pin 1; 5.08 mm pitch, entry at -y
OUT_SPAN_X = (38.2, 107.7)           # J4 left edge .. J8 right edge
TERM_TOP = 13.8                      # terminal block height above PCB top (tallest part)
SCREW_IN = 4.45                      # terminal screw axis, distance in from the board edge
FUSE_XY = (28.96, 7.8)               # F1 holder centre
SW = {"RST": (58.83, 76.02), "BOOT": (94.10, 61.10)}  # SW1, SW2 (TL3342)
SW_TOP = 3.1 - PCB_T + 0.04          # switch top above PCB top (~1.5 mm)
LED_XY = (45.94, 38.39)              # D4 power LED
ANT_X = (69.0, 87.0)                 # ESP32 module, overhangs to y = 91

# ---- Enclosure parameters -----------------------------------------------------
WALL = 2.4        # wall thickness
GAP = 1.5         # PCB edge to inner wall
FLOOR = 2.0       # floor thickness
STANDOFF = 5.0    # floor top to PCB underside (THT leads stick out ~2.3 mm)
HEADROOM = 16.0   # PCB top to lid ceiling (2.2 mm over the terminal blocks)
LID_T = 2.0       # lid top thickness
TONGUE_H = 2.0    # alignment tongue on the base rim
TONGUE_W = 1.2
FIT = 0.2         # clearance between mating printed parts
BAY_Y = 93.0      # antenna bay inner wall (module tip at y = 91)
BAY_X = (ANT_X[0] - 3, ANT_X[1] + 3)
EARS = True       # wall-mount ears on the base

# Fasteners: one M3x12 socket screw per corner, from under the floor, through the
# base boss and the PCB hole, into a heat-set insert in the lid post. It clamps the
# PCB between boss and post.
BOSS_D, POST_D = 10.0, 7.5        # boss 10 mm: 1.75 mm wall around the screw-head counterbore
SCREW_CLR = 3.4
HEAD_D, HEAD_H = 6.5, 3.0          # counterbore for M3 socket head (5.5 mm)
INSERT_D, INSERT_DEPTH = 4.0, 7.0  # M3 x 5.7 heat-set insert (check your insert's spec)

Z_PCB = FLOOR + STANDOFF            # PCB underside
Z_SPLIT = Z_PCB + PCB_T             # PCB top = base/lid split plane
Z_CEIL = Z_SPLIT + HEADROOM
Z_TOP = Z_CEIL + LID_T

INNER = [(-GAP, -GAP), (PCB_W + GAP, -GAP), (PCB_W + GAP, PCB_H + GAP),
         (BAY_X[1], PCB_H + GAP), (BAY_X[1], BAY_Y), (BAY_X[0], BAY_Y),
         (BAY_X[0], PCB_H + GAP), (-GAP, PCB_H + GAP)]


def prism(offset, z0, z1):
    """Inner outline grown by `offset`, extruded from z0 to z1."""
    wp = cq.Workplane("XY").workplane(offset=z0).polyline(INNER).close()
    if offset:
        wp = wp.offset2D(offset, "arc")
    return wp.extrude(z1 - z0)


def box(x0, x1, y0, y1, z0, z1):
    return (cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False)
            .translate((x0, y0, z0)))


def cyl(x, y, d, z0, z1):
    return cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(d / 2).extrude(z1 - z0)


def slot(x, y, length, width, z0, z1, along="y"):
    wp = cq.Workplane("XY").workplane(offset=z0).center(x, y)
    w, h = (width, length) if along == "y" else (length, width)
    return wp.slot2D(max(w, h), min(w, h), 90 if along == "y" else 0).extrude(z1 - z0)


# Labels: >= 0.8 mm stroke width and depth (JLC3DP minimum for resin/nylon).
# Bold text at size >= 6.5 mm gives strokes of about 0.9 mm.
LABEL_SIZE, LABEL_DEPTH = 7.0, 0.8
LETTER_GAP = 1.2  # plastic left between engraved letters (also >= 0.8 mm)


def engrave(part, text, x, y, size=LABEL_SIZE, depth=LABEL_DEPTH, rot=0):
    """Engrave text one letter at a time, so neighbouring letters keep LETTER_GAP between
    them (the font's own spacing leaves slivers under 0.8 mm at this size)."""
    try:
        glyphs, cursor = [], 0.0
        for ch in text:
            if ch == " ":
                cursor += size * 0.35
                continue
            g = cq.Workplane("XY").text(ch, size, depth + 0.1, halign="left",
                                        valign="center", kind="bold")
            bb = g.val().BoundingBox()
            glyphs.append(g.translate((cursor - bb.xmin, 0, 0)))
            cursor += bb.xlen + LETTER_GAP
        width = cursor - LETTER_GAP
        for g in glyphs:
            g = (g.translate((-width / 2, 0, 0)).rotate((0, 0, 0), (0, 0, 1), rot)
                 .translate((x, y, Z_TOP - depth)))
            part = part.cut(g)
        return part
    except Exception as e:  # missing font etc. -- labels are cosmetic
        print("label skipped:", text, e)
        return part


# Openings shared by base and lid (cut from both).
def connector_cuts():
    out = []
    usb_z = Z_SPLIT + USB_Z_OFF
    out.append(box(USB_X - 6.5, USB_X + 6.5, PCB_H, PCB_H + 20, usb_z - 3.5, usb_z + 3.5))
    out.append(box(-20, 0, BARREL_Y[0] - 0.6, BARREL_Y[1] + 0.6, Z_SPLIT - 0.01,
                   Z_SPLIT + BARREL_TOP + 0.8))
    out.append(box(-20, 0, J1_PINS_Y[0] - 3.0, J1_PINS_Y[1] + 3.8, Z_SPLIT - 0.01, Z_SPLIT + 11))
    out.append(box(OUT_SPAN_X[0], OUT_SPAN_X[1], -20, 0, Z_SPLIT - 0.01, Z_SPLIT + 11))
    return out


def make_base():
    base = prism(WALL, 0, Z_SPLIT).cut(prism(0, FLOOR, Z_SPLIT + 1))
    tongue = prism(WALL, Z_SPLIT, Z_SPLIT + TONGUE_H).cut(
        prism(WALL - TONGUE_W, Z_SPLIT - 1, Z_SPLIT + TONGUE_H + 1))
    base = base.union(tongue)
    for x, y in HOLES:
        base = base.union(cyl(x, y, BOSS_D, FLOOR - 0.01, Z_PCB))
    if EARS:
        for x, y in [(-GAP - WALL, 6), (-GAP - WALL, 72), (PCB_W + GAP + WALL, 30),
                     (PCB_W + GAP + WALL, 72)]:
            dx = -1 if x < 0 else 1
            ear = (cq.Workplane("XY").center(x + dx * 5, y).rect(10 + 0.02, 14)
                   .extrude(3.0).edges("|Z").fillet(2.5))
            ear = ear.cut(slot(x + dx * 5.5, y, 8, 4.5, -1, 5, along="y"))
            base = base.union(ear)
    for x, y in HOLES:
        base = base.cut(cyl(x, y, SCREW_CLR, -1, Z_PCB + 1))
        base = base.cut(cyl(x, y, HEAD_D, -1, HEAD_H))
    for c in connector_cuts():
        base = base.cut(c)
    # four shallow recesses for 8 mm stick-on rubber feet
    for x, y in [(8, 8), (PCB_W - 8, 8), (8, PCB_H - 8), (PCB_W - 8, PCB_H - 8)]:
        if all((x - hx) ** 2 + (y - hy) ** 2 > 36 for hx, hy in HOLES):
            base = base.cut(cyl(x, y, 9, -1, 0.6))
    return base


def make_lid():
    lid = prism(WALL, Z_SPLIT + TONGUE_H, Z_TOP).union(
        prism(WALL - TONGUE_W - FIT, Z_SPLIT, Z_SPLIT + TONGUE_H + 0.01))
    lid = lid.cut(prism(0, Z_SPLIT - 1, Z_CEIL))
    try:
        lid = lid.faces(">Z").edges().fillet(1.2)
    except Exception as e:
        print("lid fillet skipped:", e)

    for x, y in HOLES:  # posts that press the PCB down; heat-set insert at the bottom
        lid = lid.union(cyl(x, y, POST_D, Z_SPLIT, Z_CEIL + 0.01))
    for name, (x, y) in SW.items():  # plunger guide tubes
        lid = lid.union(cyl(x, y, 6.4, Z_SPLIT + SW_TOP + 3.4, Z_CEIL + 0.01))
    lid = lid.union(cyl(*LED_XY, 5.2, Z_SPLIT + 3.0, Z_CEIL + 0.01))  # light-pipe sleeve

    for x, y in HOLES:
        lid = lid.cut(cyl(x, y, INSERT_D, Z_SPLIT - 1, Z_SPLIT + INSERT_DEPTH))
    for x, y in SW.values():
        lid = lid.cut(cyl(x, y, 3.5, Z_SPLIT, Z_TOP + 1))
    lid = lid.cut(cyl(*LED_XY, 3.2, Z_SPLIT, Z_TOP + 1))

    # fuse access window (the mini blade fuse stands taller than the lid allows)
    fx, fy = FUSE_XY
    lid = lid.cut(cq.Workplane("XY").workplane(offset=Z_CEIL - 1).center(fx, fy)
                  .rect(18, 9).extrude(LID_T + 2).edges("|Z").fillet(2))
    # screwdriver slots over every terminal screw
    for x1 in OUT_PIN1_X:
        for i in range(3):
            lid = lid.cut(slot(x1 + i * 5.08, SCREW_IN, 6.0, 3.8, Z_CEIL - 1, Z_TOP + 1))
    for y in J1_PINS_Y:
        lid = lid.cut(slot(SCREW_IN, y, 6.0, 3.8, Z_CEIL - 1, Z_TOP + 1, along="x"))
    # vent slots over the open middle of the board
    for i in range(8):
        lid = lid.cut(slot(60 + i * 4.5, 37, 22, 2.0, Z_CEIL - 1, Z_TOP + 1))

    for c in connector_cuts():
        lid = lid.cut(c)

    labels = [("5V IN", 10.5, 33.0, LABEL_SIZE, 0),
              ("PWR", LED_XY[0], LED_XY[1] - 6.5, LABEL_SIZE, 0),
              ("RST", SW["RST"][0], SW["RST"][1] - 7.0, LABEL_SIZE, 0),
              ("BOOT", SW["BOOT"][0], SW["BOOT"][1] - 7.0, LABEL_SIZE, 0),
              ("FUSE", FUSE_XY[0], FUSE_XY[1] + 9.0, LABEL_SIZE, 0)]
    for n, x1 in enumerate(OUT_PIN1_X, 1):
        labels.append((str(n), x1 + 5.08, 13.0, LABEL_SIZE, 0))  # output number above each group
    for text, x, y, s, r in labels:
        lid = engrave(lid, text, x, y, s, rot=r)
    return lid


def make_plunger():
    """Button plunger: shaft through the lid tube, collar below the tube keeps it captive.
    Print upright, two copies. Insert from inside before fitting the lid."""
    bottom = Z_SPLIT + SW_TOP + 0.3
    collar_top = bottom + 1.5
    shaft = cyl(0, 0, 3.0, collar_top - 0.01, Z_TOP + 1.0)
    collar = cyl(0, 0, 5.6, bottom, collar_top)
    p = collar.union(shaft).translate((0, 0, -bottom))
    try:
        p = p.faces(">Z").edges().fillet(0.8)
    except Exception:
        pass
    return p


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
    os.makedirs(out, exist_ok=True)
    parts = {"enclosure_base": make_base(), "enclosure_lid": make_lid(),
             "button_plunger": make_plunger()}
    for name, part in parts.items():
        cq.exporters.export(part, os.path.join(out, name + ".step"))
        cq.exporters.export(part, os.path.join(out, name + ".stl"), tolerance=0.02,
                            angularTolerance=0.1)
        bb = part.val().BoundingBox()
        print(f"{name}: {bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f} mm")
