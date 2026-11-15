"""Build combined STEP files of the PCB + enclosure for viewing all parts together.

Run after enclosure.py:  python enclosure/make_assembly.py
Writes enclosure/enclosure_assembly.step (closed) and enclosure_assembly_exploded.step.
Needs kicad-cli (KiCad 8/9) on PATH to export the board model.
"""
import os
import subprocess
import sys
import tempfile

import cadquery as cq

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import enclosure as E  # noqa: E402
PCB = os.path.join(HERE, "..", "kicad", "esp32_led_controller.kicad_pcb")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        board_step = os.path.join(tmp, "board.step")
        # user origin = the PCB's bottom-left corner in KiCad (87, 143), matching enclosure.py
        subprocess.run(["kicad-cli", "pcb", "export", "step", "--subst-models",
                        "--user-origin", "87x143mm", "-o", board_step, PCB], check=True)
        board = cq.importers.importStep(board_step)

    load = lambda n: cq.importers.importStep(os.path.join(HERE, n + ".step"))
    base, lid, plunger = load("enclosure_base"), load("enclosure_lid"), load("button_plunger")
    plunger_z = E.Z_SPLIT + E.SW_TOP + 0.3

    for name, lift in [("enclosure_assembly", 0), ("enclosure_assembly_exploded", 40)]:
        a = cq.Assembly(name=name)
        a.add(base, name="base", color=cq.Color(0.24, 0.29, 0.36))
        a.add(board, name="pcb", color=cq.Color(0.18, 0.56, 0.30),
              loc=cq.Location((0, 0, E.Z_PCB + lift / 2)))
        for i, (x, y) in enumerate(E.SW.values()):
            a.add(plunger, name=f"plunger_{i + 1}", color=cq.Color(0.9, 0.5, 0.1),
                  loc=cq.Location((x, y, plunger_z + lift)))
        a.add(lid, name="lid", color=cq.Color(0.80, 0.82, 0.85),
              loc=cq.Location((0, 0, lift)))
        path = os.path.join(HERE, name + ".step")
        a.save(path)  # .step: parts keep their names and colours
        print("wrote", path)


if __name__ == "__main__":
    main()
