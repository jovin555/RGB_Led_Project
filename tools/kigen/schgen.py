"""Generate KiCad 9 schematic sheets from a compact part/net description.

Every pin gets a 2.54 mm wire stub ending in a power symbol, a net label,
a global label, or (for unused pins) a no-connect flag sits on the pin.
"""
import copy
import math
import uuid as _uuid

from sexp import Str, dumps, find, find_all, lib_symbol, symbol_pins, transform

PROJECT = "esp32_led_controller"
STUB = 2.54

# net name -> power symbol lib_id. Nets listed here are drawn as power symbols;
# the symbol's Value sets the net name (KiCad 7+), so custom rails reuse power:+5V.
POWER_NETS = {
    "GND": "power:GND",
    "+3V3": "power:+3V3",
    "VBUS": "power:VBUS",
    "+5V_IN": "power:+5V",
    "+5V_LED": "power:+5V",
    "+5V_LOGIC": "power:+5V",
}
GLOBAL_NETS = set()  # filled by the design file

_counters = {"#PWR": 0, "#FLG": 0}


def uid():
    return Str(str(_uuid.uuid4()))


def _font(size=1.27, bold=False):
    f = ["font", ["size", size, size]]
    if bold:
        f.append(["bold", "yes"])
    return f


def _effects(justify=None, hide=False, size=1.27, bold=False):
    e = ["effects", _font(size, bold)]
    if justify:
        e.append(["justify"] + justify.split())
    if hide:
        e.append(["hide", "yes"])
    return e


def _r(v):
    return round(v, 4)


class Sheet:
    def __init__(self, filename, title, file_uuid, inst_path, date="2026-10-28", rev="0.2"):
        self.filename = filename
        self.title = title
        self.file_uuid = file_uuid
        self.inst_path = inst_path  # "/<root uuid>/<sheet uuid>"
        self.date = date
        self.rev = rev
        self.lib_ids = []
        self.items = []
        self.refs = []

    # ------------------------------------------------------------ primitives
    def _use_lib(self, lib_id):
        if lib_id not in self.lib_ids:
            self.lib_ids.append(lib_id)

    def wire(self, a, b):
        self.items.append(["wire", ["pts", ["xy", _r(a[0]), _r(a[1])], ["xy", _r(b[0]), _r(b[1])]],
                           ["stroke", ["width", 0], ["type", "default"]], ["uuid", uid()]])

    def no_connect(self, p):
        self.items.append(["no_connect", ["at", _r(p[0]), _r(p[1])], ["uuid", uid()]])

    def label(self, name, p, left=False, glob=False, shape="bidirectional"):
        angle = 180 if left else 0
        just = "right" if left else "left"
        if glob:
            item = ["global_label", Str(name), ["shape", shape], ["at", _r(p[0]), _r(p[1]), angle],
                    ["fields_autoplaced", "yes"], _effects(just), ["uuid", uid()],
                    ["property", Str("Intersheetrefs"), Str("${INTERSHEET_REFS}"),
                     ["at", _r(p[0]), _r(p[1]), 0], _effects(just, hide=True)]]
        else:
            item = ["label", Str(name), ["at", _r(p[0]), _r(p[1]), angle],
                    _effects(just + " bottom"), ["uuid", uid()]]
        self.items.append(item)

    def text(self, s, x, y, size=1.524, bold=False):
        self.items.append(["text", Str(s), ["exclude_from_sim", "no"], ["at", x, y, 0],
                           _effects("left bottom", size=size, bold=bold), ["uuid", uid()]])

    # ------------------------------------------------------------ symbols
    def _place(self, lib_id, ref, value, footprint, x, y, rot, unit, fields=None, field_pos=None,
               extra_props=None, bom=True):
        self._use_lib(lib_id)
        sym = lib_symbol(lib_id)
        props = {p[1]: p for p in find_all(sym, "property")}
        pins = symbol_pins(lib_id)
        unit_pins = [p for p in pins if p["unit"] in (0, unit)]
        is_power = lib_id.startswith("power:")
        node = ["symbol", ["lib_id", Str(lib_id)], ["at", _r(x), _r(y), rot], ["unit", unit],
                ["exclude_from_sim", "no"], ["in_bom", "no" if is_power or not bom else "yes"],
                ["on_board", "no" if is_power else "yes"], ["dnp", "no"], ["uuid", uid()]]
        values = {"Reference": ref, "Value": value, "Footprint": footprint or "",
                  "Datasheet": str(props["Datasheet"][2]) if "Datasheet" in props else "~",
                  "Description": str(props["Description"][2]) if "Description" in props else ""}
        if extra_props:
            values.update(extra_props)
        for name, val in values.items():
            lp = props.get(name)
            hidden = name not in ("Reference", "Value")
            just = None
            if lp is not None:
                at = find(lp, "at")
                eff = find(lp, "effects")
                if eff is not None and (["hide", "yes"] in eff or "hide" in eff):
                    hidden = True
                j = find(eff, "justify") if eff is not None else None
                just = " ".join(j[1:]) if j else None
                fx, fy = transform(float(at[1]), float(at[2]), x, y, rot)
            else:
                fx, fy = x, y
            fang = float(find(lp, "at")[3]) if lp is not None and len(find(lp, "at")) > 3 else 0
            two_pin = len([p for p in unit_pins if not p["hidden"]]) == 2 and not is_power
            if name in ("Reference", "Value") and (two_pin or (field_pos and name in field_pos)):
                # field angles are stored relative to the symbol; rot % 180 keeps text horizontal
                fang, just = rot % 180, None
                if field_pos and name in field_pos:
                    fx, fy = field_pos[name][:2]
                else:
                    pts = [transform(p["x"], p["y"], x, y, rot) for p in unit_pins if not p["hidden"]]
                    w = 1.05 * len(val)
                    if abs(pts[0][0] - pts[1][0]) < 0.01:  # vertical part: fields to the right
                        fx, fy = x + 2.0 + w / 2, (y - 1.27 if name == "Reference" else y + 1.27)
                    else:  # horizontal part: fields above
                        fx, fy = x, (y - 5.08 if name == "Reference" else y - 2.54)
            node.append(["property", Str(name), Str(val), ["at", _r(fx), _r(fy), fang],
                         _effects(just, hide=hidden)])
        for p in unit_pins:
            node.append(["pin", Str(p["number"]), ["uuid", uid()]])
        node.append(["instances", ["project", Str(PROJECT),
                                   ["path", Str(self.inst_path), ["reference", Str(ref)], ["unit", unit]]]])
        self.items.append(node)
        return unit_pins

    def _power_symbol(self, net, p, d_sch):
        """Place a power symbol whose pin sits at p, body pointing along d_sch."""
        lib_id = POWER_NETS[net]
        _counters["#PWR"] += 1
        ref = "#PWR%03d" % _counters["#PWR"]
        down = d_sch[1] > 0
        # GND body points down, rails point up; flip when the stub runs the other way
        rot = 0 if (net == "GND") == down else 180
        self._place(lib_id, ref, net, "", p[0], p[1], rot, 1)

    def _connect(self, pin_pt, d, net):
        end = (pin_pt[0] + d[0] * STUB, pin_pt[1] + d[1] * STUB)
        self.wire(pin_pt, end)
        if net in POWER_NETS and d[1] != 0:
            self._power_symbol(net, end, d)
        elif net in POWER_NETS:
            self.label(net, end, left=d[0] < -0.5, glob=True, shape="passive")
        else:
            self.label(net.lstrip("/"), end, left=d[0] < -0.5, glob=net in GLOBAL_NETS)

    def part(self, lib_id, ref, value, footprint, at, rot=0, unit=1, conns=None, nc_rest=False,
             field_pos=None, props=None, bom=True):
        conns = dict(conns or {})
        x, y = at
        unit_pins = self._place(lib_id, ref, value, footprint, x, y, rot, unit, field_pos=field_pos,
                                extra_props=props, bom=bom)
        self.refs.append(ref)
        seen = set()
        for p in unit_pins:
            num = p["number"]
            pt = transform(p["x"], p["y"], x, y, rot)
            if p["hidden"]:
                continue  # stacked under a visible pin of the same name
            a = math.radians(p["angle"] + 180 + rot)
            d = (round(math.cos(a)), -round(math.sin(a)))
            if num in conns:
                net = conns.pop(num)
                if net is None:  # wired explicitly by the caller
                    continue
            elif nc_rest or p["type"] == "no_connect" or p["type"] == "free":
                net = "NC"
            else:
                raise ValueError("%s pin %s (%s) unconnected" % (ref, num, p["name"]))
            if (pt, net) in seen:
                continue
            seen.add((pt, net))
            if net == "NC":
                self.no_connect(pt)
            else:
                self._connect(pt, d, net)
        if conns:
            raise ValueError("%s: unknown pins %s" % (ref, list(conns)))

    def pin_pos(self, lib_id, num, at, rot=0):
        p = next(p for p in symbol_pins(lib_id) if p["number"] == num)
        return transform(p["x"], p["y"], at[0], at[1], rot)

    def wire_label(self, name, a, b):
        """Wire a-b with a net label just past a (for readable net names)."""
        self.wire(a, b)
        mid = (round((a[0] + 3.81) / 1.27) * 1.27, a[1])
        self.label(name, mid)

    def pwr_flag(self, net, at):
        """PWR_FLAG + power symbol sharing one point."""
        _counters["#FLG"] += 1
        ref = "#FLG%02d" % _counters["#FLG"]
        x, y = at
        if net == "GND":
            self._place("power:PWR_FLAG", ref, "PWR_FLAG", "", x, y, 0, 1)
            self._power_symbol(net, (x, y), (0, 1))
        else:
            self._place("power:PWR_FLAG", ref, "PWR_FLAG", "", x, y, 180, 1,
                        field_pos={"Value": (x, y + 6.35, None)})
            self._power_symbol(net, (x, y), (0, -1))

    # ------------------------------------------------------------ output
    def build(self):
        libs = ["lib_symbols"] + [lib_symbol(l) for l in self.lib_ids]
        doc = ["kicad_sch", ["version", 20250114], ["generator", Str("eeschema")],
               ["generator_version", Str("9.0")], ["uuid", Str(self.file_uuid)], ["paper", Str("A4")],
               ["title_block", ["title", Str(self.title)], ["date", Str(self.date)], ["rev", Str(self.rev)],
                ["company", Str("RGB LED Project")], ["comment", 1, Str("See docs/PCB_DESIGN_PLAN.md")]],
               libs]
        doc += self.items
        doc.append(["embedded_fonts", "no"])
        return dumps(doc) + "\n"

    def write(self, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.build())
