"""Build the PCB from the schematic netlist: outline, placement, holes, power pours, stitching.

Run:  python3 -I tools/kigen/pcbgen.py      (from the project root; KiCad must not have the board open)
Signal routing is left to KiCad's interactive router.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew  # noqa: E402
from sexp import find, find_all, parse  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
KDIR = os.path.normpath(os.path.join(HERE, "..", "..", "kicad"))
PRO = os.path.join(KDIR, "esp32_led_controller.kicad_pro")
SCH = os.path.join(KDIR, "esp32_led_controller.kicad_sch")
PCB = os.path.join(KDIR, "esp32_led_controller.kicad_pcb")
TEMPLATE = os.path.join(HERE, "board_template.kicad_pcb")  # empty board: stackup, title block, rules
FPLIB = "/usr/share/kicad/footprints"

# Board: 110 x 85 mm, top-left corner at (100, 100)
X0, Y0, W, H = 100.0, 100.0, 110.0, 85.0
X1, Y1 = X0 + W, Y0 + H

# ref: (x, y, rotation_deg). Rotation is counter-clockwise as seen from the top.
PLACE = {
    # MCU: antenna overhangs the top edge; module keep-out (6.75 mm above centre) lands off-board
    "U1": (178.0, Y0 + 6.75, 0),
    "C7": (163.5, 103.0, 0), "C6": (163.5, 106.0, 0),
    "R1": (163.5, 109.5, 0), "C8": (163.5, 112.0, 0),
    "SW1": (156.0, 120.0, 0),
    "R2": (192.5, 122.0, 0), "SW2": (197.0, 128.0, 0),
    "J3": (196.0, 106.0, 0),
    # USB-C on the top edge, ESD array and CC resistors right behind it
    "J6": (130.0, Y0 + 3.1, 180),
    "U4": (130.3375, 110.2275, -90),  # moved by hand while routing USB
    "R3": (133.0, 112.0, -90), "R4": (129.1, 113.3, -90),
    "D2": (123.2, 113.6, 90),
    # input: barrel jack and screw terminal on the left edge, protection next to them
    "J2": (X0 + 13.7, 140.0, 0),
    "J1": (X0 + 4.65, 162.0, 270),
    "C1": (118.0, 157.0, 0),
    "D3": (117.0, 169.5, 0),
    "F1": (124.0, 175.5, 0),
    # hook-clip test loops in the free strip between H3 and F1
    "TP1": (112.0, 178.5, 0), "TP2": (118.0, 178.5, 0),
    # SMD probe pads next to the parts on each net
    "TP3": (136.0, 183.0, 0),   # +5V_LED, inside its pour beside F1
    "TP4": (129.0, 131.0, 0),   # +5V_LOGIC, by C2/C3
    "TP5": (157.0, 134.0, 0),   # +3V3, by C4/C5
    "TP6": (117.5, 120.0, 0),   # VBUS, by D2
    "TP7": (149.0, 120.0, 0),   # EN, by SW1
    "TP8": (188.0, 127.0, 0),   # BOOT, by SW2
    # logic branch and 3.3 V regulator
    "F2": (126.0, 147.0, 0),
    "D1": (134.0, 147.0, 0),
    "C2": (133.0, 134.0, 90), "C3": (136.0, 134.0, 90),
    "U2": (143.0, 136.0, 0),
    "C4": (150.0, 134.0, 90), "C5": (153.0, 134.0, 90),
    "R9": (157.0, 140.0, 90), "D4": (157.0, 145.0, 90),
    # level shifter, series resistors and LED outputs along the bottom edge
    "U3": (172.0, 152.0, 0), "C9": (172.0, 145.0, 0),
    "J4": (142.0, Y1 - 4.65, 0), "J5": (159.5, Y1 - 4.65, 0),
    "J7": (177.0, Y1 - 4.65, 0), "J8": (194.5, Y1 - 4.65, 0),
}
# series resistors sit right above each output's DATA pin (pin 2 = origin + 5.08)
for _ref, _j in (("R5", "J4"), ("R6", "J5"), ("R7", "J7"), ("R8", "J8")):
    PLACE[_ref] = (PLACE[_j][0] + 5.08, 165.0, 90)

# The board was moved in KiCad after generation; every item is shifted by this much at the end
OFFSET = (-13.0, -42.0)

HOLES = [(X0 + 4.0, Y0 + 4.0), (X1 - 4.0, Y0 + 4.0), (X0 + 4.0, Y1 - 4.0), (X1 - 4.5, 167.0)]

# copper pours: (net, layer, priority, polygon or None for the whole board)
POURS = [
    ("GND", pcbnew.B_Cu, 0, None),
    ("GND", pcbnew.F_Cu, 0, None),
    # +5V_IN: input connectors -> TVS, bulk cap, F1 pad 1, F2
    ("+5V_IN", pcbnew.F_Cu, 1, [(X0 + 0.5, 134.0), (129.5, 134.0), (129.5, Y1 - 0.5), (X0 + 0.5, Y1 - 0.5)]),
    # +5V_LED: F1 pad 2 -> all output terminals
    ("+5V_LED", pcbnew.F_Cu, 1, [(132.0, 171.0), (X1 - 0.5, 171.0), (X1 - 0.5, Y1 - 0.5), (132.0, Y1 - 0.5)]),
]


_IO = pcbnew.PCB_IO_MGR.PluginFind(pcbnew.PCB_IO_MGR.KICAD_SEXP)  # keep one plugin alive


def load_fp(lib, name):
    """Footprint copy owned by Python (FootprintLoad results can be freed with their plugin)."""
    return pcbnew.FOOTPRINT(_IO.FootprintLoad("%s/%s.pretty" % (FPLIB, lib), name))


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def netlist():
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "n.net")
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr", "-o", out, SCH],
                       check=True, capture_output=True)
        return parse(open(out, encoding="utf-8").read())


def project_settings():
    """The real project file with this board's net-class and rule changes applied."""
    d = json.load(open(PRO))
    pats = [p for p in d["net_settings"]["netclass_patterns"] if p["pattern"] not in ("GND", "+5V_IN")]
    pats += [{"netclass": "LED_Power", "pattern": "+5V_IN"}, {"netclass": "Power", "pattern": "GND"}]
    d["net_settings"]["netclass_patterns"] = pats
    # the ESP32-S3-WROOM-1 library footprint has 0.2 mm thermal vias in its ground pad
    d["board"]["design_settings"]["rules"]["min_through_hole_diameter"] = 0.2
    return d


def add_shape_rect(board, x0, y0, x1, y1, layer, width=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_RECT)
    s.SetStart(pt(x0, y0))
    s.SetEnd(pt(x1, y1))
    s.SetLayer(layer)
    s.SetWidth(mm(width))
    board.Add(s)


def add_text(board, text, x, y, size=1.0, layer=pcbnew.F_SilkS, bold=False):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetPosition(pt(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(max(0.15, size * (0.2 if bold else 0.15))))
    board.Add(t)


def add_zone(board, netinfo, layer, priority, poly):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(netinfo)
    z.SetAssignedPriority(priority)
    z.SetLocalClearance(mm(0.3))
    z.SetMinThickness(mm(0.25))
    z.SetThermalReliefGap(mm(0.5))
    z.SetThermalReliefSpokeWidth(mm(1.0 if netinfo.GetNetname() == "GND" else 1.5))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    if poly is None:
        poly = [(X0 + 0.3, Y0 + 0.3), (X1 - 0.3, Y0 + 0.3), (X1 - 0.3, Y1 - 0.3), (X0 + 0.3, Y1 - 0.3)]
    outline = z.Outline()
    outline.NewOutline()
    for x, y in poly:
        outline.Append(mm(x), mm(y))
    board.Add(z)
    return z


def main():
    settings = project_settings()
    n = netlist()
    comps = find_all(find(n, "components"), "comp")
    loaded = {}
    for comp in comps:
        lib, name = str(find(comp, "footprint")[1]).split(":", 1)
        loaded[str(find(comp, "ref")[1])] = load_fp(lib, name)
    holes = [load_fp("MountingHole", "MountingHole_3.2mm_M3") for _ in HOLES]
    # Start from the empty template (removing items from a loaded board corrupts pcbnew's Python
    # bindings). Load it next to a copy of the real project file: SaveBoard rewrites the .kicad_pro
    # from the loaded project, so this keeps the net classes and design rules.
    tmp = tempfile.mkdtemp()
    base = os.path.join(tmp, os.path.basename(PCB))
    shutil.copy(TEMPLATE, base)
    with open(base[:-len("kicad_pcb")] + "kicad_pro", "w") as f:
        json.dump(settings, f, indent=2)
    board = pcbnew.LoadBoard(base)

    # nets
    pad_net = {}
    nets = {}
    for net in find_all(find(n, "nets"), "net"):
        name = str(find(net, "name")[1])
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        nets[name] = ni
        for node in find_all(net, "node"):
            pad_net[(str(find(node, "ref")[1]), str(find(node, "pin")[1]))] = ni

    # footprints
    for comp in comps:
        ref = str(find(comp, "ref")[1])
        lib, name = str(find(comp, "footprint")[1]).split(":", 1)
        fp = loaded[ref]
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetReference(ref)
        fp.SetValue(str(find(comp, "value")[1]))
        sheet = find(comp, "sheetpath")
        tstamps = find(comp, "tstamps")
        fp.SetPath(pcbnew.KIID_PATH(str(find(sheet, "tstamps")[1]) + str(tstamps[1])))
        fp.SetSheetname(str(find(sheet, "names")[1]))
        if ref == "U4":
            fp.SetLocalClearance(mm(0.125))  # UDFN-10 0.5 mm pitch: the footprint's own pad gap is 0.15 mm
        x, y, rot = PLACE[ref]
        fp.SetPosition(pt(x, y))
        fp.SetOrientationDegrees(rot)
        for pad in fp.Pads():
            ni = pad_net.get((ref, pad.GetNumber()))
            if ni is not None:
                pad.SetNet(ni)
            if ref == "U4" and pad.GetNumber() in ("3", "8"):
                pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)  # too small for 2 spokes
        board.Add(fp)

    # mounting holes (board-only, so "Update PCB from Schematic" leaves them alone)
    for i, (x, y) in enumerate(HOLES, 1):
        fp = holes[i - 1]
        fp.SetFPID(pcbnew.LIB_ID("MountingHole", "MountingHole_3.2mm_M3"))
        fp.SetReference("H%d" % i)
        fp.SetValue("M3")
        fp.SetBoardOnly(True)
        fp.Reference().SetVisible(False)
        fp.SetPosition(pt(x, y))
        board.Add(fp)

    # outline
    add_shape_rect(board, X0, Y0, X1, Y1, pcbnew.Edge_Cuts, 0.1)

    # pours
    for net, layer, prio, poly in POURS:
        add_zone(board, nets[net], layer, prio, poly)

    # GND stitching vias around the perimeter, away from parts and the 5 V pours
    keep = []
    for fp in board.GetFootprints():
        bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox() if fp.GetCourtyard(pcbnew.F_CrtYd).OutlineCount() \
            else fp.GetBoundingBox(False)
        keep.append((pcbnew.ToMM(bb.GetLeft()) - 0.8, pcbnew.ToMM(bb.GetTop()) - 0.8,
                     pcbnew.ToMM(bb.GetRight()) + 0.8, pcbnew.ToMM(bb.GetBottom()) + 0.8))
    for _net, _layer, _prio, poly in POURS:
        if poly and _net != "GND":
            xs, ys = [p[0] for p in poly], [p[1] for p in poly]
            keep.append((min(xs) - 1, min(ys) - 1, max(xs) + 1, max(ys) + 1))
    u1x = PLACE["U1"][0]
    keep.append((u1x - 10.5, Y0, u1x + 10.5, Y0 + 20.5))  # under the module

    def free(x, y):
        return not any(a <= x <= c and b <= y <= d for a, b, c, d in keep)

    spots = []
    step = 5.0
    inset = 2.0
    x = X0 + inset
    while x <= X1 - inset + 1e-6:
        spots += [(x, Y0 + inset), (x, Y1 - inset)]
        x += step
    y = Y0 + inset + step
    while y <= Y1 - inset - step + 1e-6:
        spots += [(X0 + inset, y), (X1 - inset, y)]
        y += step
    nvias = 0
    for x, y in spots:
        if free(x, y):
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pt(x, y))
            v.SetWidth(pcbnew.F_Cu, mm(0.6))
            v.SetDrill(mm(0.3))
            v.SetNet(nets["GND"])
            board.Add(v)
            nvias += 1

    # D3's GND pad is an SMD pad inside the +5V_IN pour: drop it to the B.Cu GND plane
    d3 = next(f for f in board.GetFootprints() if f.GetReference() == "D3")
    pad = d3.FindPadByNumber("2")
    px, py = pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)
    vx = px + pcbnew.ToMM(pad.GetSize().x) / 2 + 1.0
    for vy in (py - 0.9, py + 0.9):
        tr = pcbnew.PCB_TRACK(board)
        tr.SetStart(pt(px, vy))
        tr.SetEnd(pt(vx, vy))
        tr.SetWidth(mm(0.8))
        tr.SetLayer(pcbnew.F_Cu)
        tr.SetNet(nets["GND"])
        board.Add(tr)
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pt(vx, vy))
        v.SetWidth(pcbnew.F_Cu, mm(0.8))
        v.SetDrill(mm(0.4))
        v.SetNet(nets["GND"])
        board.Add(v)

    # silkscreen: polarity and pin order
    add_text(board, "ESP32-S3 WS2812B CONTROLLER  rev 0.2", 150.0, 128.5, 1.2, bold=True)
    j1x, j1y = PLACE["J1"][:2]
    add_text(board, "+5V", j1x + 7.5, j1y)
    add_text(board, "GND", j1x + 7.5, j1y + 5.08)
    add_text(board, "5V IN", j1x + 7.5, j1y - 4.0)
    for k, j in enumerate(("J4", "J5", "J7", "J8"), 1):
        jx, jy = PLACE[j][:2]
        add_text(board, "5V", jx, jy - 7.2, 0.9)
        add_text(board, "DAT", jx + 5.08, jy - 7.2, 0.9)
        add_text(board, "GND", jx + 10.16, jy - 7.2, 0.9)
        add_text(board, "%s  OUT%d" % (j, k), jx + 5.08, jy - 8.9, 0.9)
    for ref, lbl in (("TP1", "+5V"), ("TP2", "GND")):
        add_text(board, lbl, PLACE[ref][0], PLACE[ref][1] + 3.6, 0.9)
    add_text(board, "J6 USB-C", PLACE["J6"][0], PLACE["J6"][1] + 5.5, 0.9)

    # references: folded into the labels above for the edge connectors, moved clear of pads elsewhere
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    for ref in ("J4", "J5", "J7", "J8", "J6"):
        fps[ref].Reference().SetVisible(False)
    for ref, (dx, dy) in {"U4": (-3.0, 0.0), "C8": (-3.5, 0.0), "C7": (-3.5, 0.0), "C6": (-3.5, 0.0),
                          "R1": (-3.5, 0.0)}.items():
        x, y = PLACE[ref][:2]
        fps[ref].Reference().SetPosition(pt(x + dx, y + dy))
        fps[ref].Reference().SetTextAngleDegrees(0)

    shift = pt(*OFFSET)
    for item in list(board.GetFootprints()) + list(board.GetDrawings()) + list(board.GetTracks()) \
            + list(board.Zones()):
        item.Move(shift)

    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(PCB, board)
    print("footprints:", len(board.GetFootprints()), "nets:", board.GetNetCount(), "stitching vias:", nvias)


if __name__ == "__main__":
    main()
