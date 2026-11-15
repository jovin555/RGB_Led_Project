"""Minimal S-expression reader/writer for KiCad files, plus symbol-library helpers."""
import copy
import math
import re

KICAD_SHARE = "/usr/share/kicad"


class Str(str):
    """A quoted string atom (as opposed to a bare symbol/number)."""


_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)


def parse(text):
    stack = [[]]
    pos = 0
    n = len(text)
    while pos < n:
        m = _TOKEN.match(text, pos)
        if not m:
            if text[pos:].strip() == "":
                break
            raise ValueError("parse error at %d: %r" % (pos, text[pos:pos + 40]))
        pos = m.end()
        if m.group(1):
            stack.append([])
        elif m.group(2):
            done = stack.pop()
            stack[-1].append(done)
        elif m.group(3) is not None:
            stack[-1].append(Str(m.group(3).replace('\\"', '"').replace("\\\\", "\\")))
        else:
            stack[-1].append(m.group(4))
    return stack[0][0]


def dumps(node, indent=0):
    if isinstance(node, list):
        if not node:
            return "()"
        simple = all(not isinstance(x, list) for x in node)
        if simple:
            return "(" + " ".join(dumps(x) for x in node) + ")"
        pad = "\t" * (indent + 1)
        parts = [dumps(node[0])]
        out = "(" + parts[0]
        for x in node[1:]:
            if isinstance(x, list):
                out += "\n" + pad + dumps(x, indent + 1)
            else:
                out += " " + dumps(x)
        return out + "\n" + "\t" * indent + ")"
    if isinstance(node, Str):
        return '"' + node.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(node, float):
        s = ("%.4f" % node).rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s
    return str(node)


def find(node, key):
    for x in node:
        if isinstance(x, list) and x and x[0] == key:
            return x
    return None


def find_all(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]


# ---------------------------------------------------------------- libraries
_lib_cache = {}


def load_lib(lib):
    if lib not in _lib_cache:
        path = "%s/symbols/%s.kicad_sym" % (KICAD_SHARE, lib)
        _lib_cache[lib] = parse(open(path, encoding="utf-8").read())
    return _lib_cache[lib]


def lib_symbol(lib_id):
    """Return the flattened symbol definition named 'Lib:Name' (extends resolved)."""
    lib, name = lib_id.split(":", 1)
    root = load_lib(lib)
    syms = {s[1]: s for s in find_all(root, "symbol")}
    sym = copy.deepcopy(syms[name])
    ext = find(sym, "extends")
    if ext:
        parent = lib_symbol(lib + ":" + ext[1])
        pname = parent[1].split(":", 1)[1]
        child_props = {p[1]: p for p in find_all(sym, "property")}
        flat = [parent[0], Str(name)]
        for x in parent[2:]:
            if isinstance(x, list) and x[0] == "property" and x[1] in child_props:
                flat.append(child_props.pop(x[1]))
            elif isinstance(x, list) and x[0] == "symbol":
                x = copy.deepcopy(x)
                x[1] = Str(name + x[1][len(pname):])
                flat.append(x)
            else:
                flat.append(x)
        # extra child-only properties go right after the other properties
        idx = max(i for i, x in enumerate(flat) if isinstance(x, list) and x[0] == "property") + 1
        for p in child_props.values():
            flat.insert(idx, p)
            idx += 1
        sym = flat
    sym[1] = Str(lib_id)
    return sym


def symbol_pins(lib_id):
    """List of dicts: number, name, type, unit, x, y, angle (symbol coords, Y up)."""
    sym = lib_symbol(lib_id)
    pins = []
    for sub in find_all(sym, "symbol"):
        m = re.search(r"_(\d+)_(\d+)$", sub[1])
        unit, style = int(m.group(1)), int(m.group(2))
        if style not in (0, 1):
            continue
        for p in find_all(sub, "pin"):
            at = find(p, "at")
            name = find(p, "name")[1]
            num = find(p, "number")[1]
            pins.append(dict(number=str(num), name=str(name), type=p[1], unit=unit,
                             x=float(at[1]), y=float(at[2]), angle=float(at[3]) if len(at) > 3 else 0.0,
                             hidden="hide" in p or any(isinstance(q, list) and q[0] == "hide" for q in p)))
    return pins


def unit_count(lib_id):
    sym = lib_symbol(lib_id)
    units = set()
    for sub in find_all(sym, "symbol"):
        units.add(int(re.search(r"_(\d+)_\d+$", sub[1]).group(1)))
    return max(units) if units else 1


def transform(px, py, X, Y, rot):
    """Symbol-local pin point (Y up) -> schematic coordinate (Y down)."""
    r = math.radians(rot)
    x = px * math.cos(r) - py * math.sin(r)
    y = px * math.sin(r) + py * math.cos(r)
    return round(X + x, 4), round(Y - y, 4)
