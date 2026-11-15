"""ESP32-S3 WS2812B controller: schematic content for the four sub-sheets.

Run:  python3 -I tools/kigen/design.py      (from the project root)
Regenerates kicad/{power,mcu,usb,led_outputs}.kicad_sch. The root sheet is left as is.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import schgen  # noqa: E402
from schgen import Sheet  # noqa: E402

ROOT = "f5fd5520-7d69-46ea-9985-266e86d69d42"
SHEET = {  # sheet-symbol uuid in the root sheet, sheet file uuid
    "power": ("556db9d4-ba0a-43cb-b19d-cf4d63cbb0b8", "2979b2d3-c90b-4680-82ba-3cb33f0613b5", "Power"),
    "mcu": ("5b7dfa88-ec8e-4417-bc56-b08e79c0b308", "d1ddc816-2507-40c8-b22e-dbf0fdacbb6c", "MCU"),
    "usb": ("700eda18-29b0-4cb1-80b1-e0eeb769dbc7", "1697f0c3-3da1-4af4-a5b5-fc9d510cac6b", "USB"),
    "led_outputs": ("1731f7a9-26db-41c4-8898-07e44d07556d", "68f48814-02e5-477c-a43c-b2ed59d45b04", "LED Outputs"),
}
KICAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "kicad")

schgen.GLOBAL_NETS.update({"LED1_DATA", "LED2_DATA", "LED3_DATA", "LED4_DATA", "USB_D+", "USB_D-"})

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
SW_SMD = "Button_Switch_SMD:SW_SPST_TL3342"
TERM2 = "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal"
TP_SMD = "TestPoint:TestPoint_Pad_D1.5mm"
TP_FP = "TestPoint:TestPoint_Keystone_5005-5009_Compact"
TERM3 = "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-3-5.08_1x03_P5.08mm_Horizontal"


def sheet(key):
    sheet_uuid, file_uuid, title = SHEET[key]
    return Sheet(key + ".kicad_sch", title, file_uuid, "/%s/%s" % (ROOT, sheet_uuid))


def notes(s, title, lines, x=25.4, y=27.94):
    s.text(title, x, y, bold=True)
    for i, line in enumerate(lines):
        s.text(line, x, y + 5.08 * (i + 1))


def cap(s, ref, value, fp, x, y, top, bottom="GND"):
    s.part("Device:C", ref, value, fp, (x, y), conns={"1": top, "2": bottom})


# ====================================================================== POWER
def power():
    s = sheet("power")
    notes(s, "POWER INPUT, PROTECTION AND 3.3 V", [
        "LED path (thick copper): J1/J2 -> +5V_IN -> F1 7.5 A -> +5V_LED -> output terminals",
        "Logic path: +5V_IN -> F2 500 mA PTC -> D1 -> +5V_LOGIC, ORed with USB VBUS via D2; "
        "+5V_LOGIC -> U2 -> +3V3",
        "J2 barrel jack is an alternative input in parallel with J1; most jacks are rated 5 A or less.",
        "No reverse-polarity FET on the LED path: mark polarity on the silkscreen.",
    ])
    # input connectors
    s.part("Connector:Screw_Terminal_01x02", "J1", "5V IN 10A", TERM2, (35.56, 96.52), rot=180,
           conns={"1": "+5V_IN", "2": "GND"},
           field_pos={"Reference": (34.29, 88.9), "Value": (34.29, 101.6)})
    s.part("Connector:Barrel_Jack_Switch", "J2", "Barrel_Jack_Switch", "Connector_BarrelJack:BarrelJack_Horizontal",
           (30.48, 121.92), conns={"1": "+5V_IN", "2": "GND", "3": "NC"})
    # input protection and bulk
    s.part("Diode:PTVS5V0Z1USK", "D3", "SMBJ5.0A", "Diode_SMD:D_SMB", (63.5, 106.68), rot=270,
           conns={"1": "+5V_IN", "2": "GND"})
    s.part("Device:C_Polarized", "C1", "1000uF 16V", "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm",
           (78.74, 106.68), conns={"1": "+5V_IN", "2": "GND"})
    # LED path fuse
    s.part("Device:Fuse", "F1", "7.5A", "Fuse:Fuseholder_Blade_Mini_Keystone_3568", (96.52, 106.68),
           conns={"1": "+5V_IN", "2": "+5V_LED"})
    # logic branch
    s.part("Device:Polyfuse", "F2", "500mA hold", "Fuse:Fuse_1206_3216Metric", (116.84, 106.68),
           conns={"1": "+5V_IN", "2": "/5V_PTC"})
    s.part("Device:D_Schottky", "D1", "SS14", "Diode_SMD:D_SMA", (142.24, 99.06), rot=180,
           conns={"2": "/5V_PTC", "1": "+5V_LOGIC"})
    s.part("Device:D_Schottky", "D2", "SS14", "Diode_SMD:D_SMA", (142.24, 116.84), rot=180,
           conns={"2": "VBUS", "1": "+5V_LOGIC"})
    # 3.3 V regulator
    s.part("Regulator_Linear:AP7361C-33E", "U2", "AP7361C-33E", "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
           (91.44, 160.02), conns={"1": "+5V_LOGIC", "2": "GND", "3": "+3V3"})
    cap(s, "C2", "10uF", C0805, 40.64, 160.02, "+5V_LOGIC")
    cap(s, "C3", "100nF", C0603, 58.42, 160.02, "+5V_LOGIC")
    cap(s, "C4", "10uF", C0805, 119.38, 160.02, "+3V3")
    cap(s, "C5", "100nF", C0603, 134.62, 160.02, "+3V3")
    # power LED
    s.part("Device:R", "R9", "1k", R0603, (157.48, 154.94), conns={"1": "+3V3", "2": "/PWR_LED"})
    s.part("Device:LED", "D4", "Green", "LED_SMD:LED_0603_1608Metric", (157.48, 167.64), rot=90,
           conns={"2": "/PWR_LED", "1": "GND"})
    # through-hole test loops for hook clips: red on +5V_IN, black on GND
    s.text("Test points (hook clip)", 170.18, 86.36, bold=True)
    s.part("Connector:TestPoint", "TP1", "+5V_IN", TP_FP, (180.34, 101.6), rot=180,
           conns={"1": "+5V_IN"}, field_pos={"Reference": (184.15, 102.87), "Value": (186.69, 105.41)},
           props={"MPN": "Keystone 5005 (red)"})
    s.part("Connector:TestPoint", "TP2", "GND", TP_FP, (200.66, 99.06),
           conns={"1": "GND"}, field_pos={"Reference": (204.47, 95.25), "Value": (204.47, 97.79)},
           props={"MPN": "Keystone 5006 (black)"})
    # SMD probe pads on the other rails
    s.text("Test points (SMD pad)", 170.18, 116.84, bold=True)
    for i, (ref, net) in enumerate((("TP3", "+5V_LED"), ("TP4", "+5V_LOGIC"), ("TP5", "+3V3"), ("TP6", "VBUS"))):
        x = 180.34 + 17.78 * i
        s.part("Connector:TestPoint", ref, net, TP_SMD, (x, 132.08), rot=180, conns={"1": net}, bom=False,
               field_pos={"Reference": (x + 3.81, 133.35), "Value": (x + 7.62, 135.89)})
    # power flags (all rails are driven by passive parts)
    for i, net in enumerate(["+5V_IN", "+5V_LED", "+5V_LOGIC", "VBUS", "GND"]):
        s.pwr_flag(net, (170.18 + 15.24 * i, 63.5 if net != "GND" else 58.42))
    s.text("Power flags", 170.18, 45.72, bold=True)
    return s


# ====================================================================== MCU
def mcu():
    s = sheet("mcu")
    notes(s, "ESP32-S3-WROOM-1 (N8 or N8R8)", [
        "EN: 10 k pull-up + 1 uF to GND; RESET button to GND. IO0: 10 k pull-up; BOOT button to GND",
        "LED data on IO4-IO7. Avoid strapping 0/3/45/46, USB 19/20, flash 26-32, PSRAM 33-37 (R8)",
        "J3: optional UART/programming header (GND, TXD0, RXD0, EN, IO0); native USB is the main path",
    ])
    gpio = {"3": "/EN", "27": "/BOOT", "4": "LED1_DATA", "5": "LED2_DATA", "6": "LED3_DATA",
            "7": "LED4_DATA", "13": "USB_D-", "14": "USB_D+", "37": "/TXD0", "36": "/RXD0",
            "2": "+3V3", "1": "GND"}
    s.part("RF_Module:ESP32-S3-WROOM-1", "U1", "ESP32-S3-WROOM-1", "RF_Module:ESP32-S3-WROOM-1",
           (152.4, 104.14), conns=gpio, nc_rest=True)
    # reset
    s.part("Device:R", "R1", "10k", R0603, (50.8, 81.28), conns={"1": "+3V3", "2": "/EN"})
    cap(s, "C8", "1uF", C0603, 50.8, 106.68, "/EN")
    s.part("Switch:SW_Push", "SW1", "RESET", SW_SMD, (66.04, 106.68), rot=90, conns={"2": "/EN", "1": "GND"})
    # boot
    s.part("Device:R", "R2", "10k", R0603, (88.9, 81.28), conns={"1": "+3V3", "2": "/BOOT"})
    s.part("Switch:SW_Push", "SW2", "BOOT", SW_SMD, (88.9, 106.68), rot=90, conns={"2": "/BOOT", "1": "GND"})
    # SMD probe pads for reset and boot strap
    s.text("Test points (SMD pad)", 40.64, 124.46, bold=True)
    for ref, net, x in (("TP7", "/EN", 50.8), ("TP8", "/BOOT", 73.66)):
        s.part("Connector:TestPoint", ref, net.strip("/"), TP_SMD, (x, 137.16), conns={"1": net}, bom=False,
               field_pos={"Reference": (x + 3.81, 133.35), "Value": (x + 3.81, 135.89)})
    # decoupling at the module 3V3 pin
    cap(s, "C6", "22uF", C0805, 200.66, 76.2, "+3V3")
    cap(s, "C7", "100nF", C0603, 210.82, 76.2, "+3V3")
    # UART header
    s.part("Connector:Conn_01x05_Pin", "J3", "UART/PROG", "Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical",
           (220.98, 109.22), rot=180,
           conns={"1": "GND", "2": "/TXD0", "3": "/RXD0", "4": "/EN", "5": "/BOOT"})
    return s


# ====================================================================== USB
def usb():
    s = sheet("usb")
    notes(s, "USB-C (16-pin, USB 2.0 device)", [
        "CC1 and CC2: separate 5.1 k pull-downs (required for power from USB-C chargers and C-to-C cables)",
        "D+/D- go straight to ESP32-S3 IO20/IO19 (native USB-Serial-JTAG); U4 ESD array close to J6",
        "VBUS feeds +5V_LOGIC only, through D2 on the Power sheet; it never feeds the LED outputs",
    ])
    s.part("Connector:USB_C_Receptacle_USB2.0_16P", "J6", "USB_C_Receptacle_USB2.0_16P",
           "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", (76.2, 101.6),
           conns={"A4": "VBUS", "A5": "/CC1", "B5": "/CC2", "A7": "USB_D-", "B7": "USB_D-",
                  "A6": "USB_D+", "B6": "USB_D+", "A8": "NC", "B8": "NC", "A1": "GND", "S1": "GND"})
    s.part("Device:R", "R3", "5.1k", R0603, (132.08, 101.6), conns={"1": "/CC1", "2": "GND"})
    s.part("Device:R", "R4", "5.1k", R0603, (147.32, 101.6), conns={"1": "/CC2", "2": "GND"})
    s.part("Power_Protection:USBLC6-2SC6", "U4", "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6",
           (190.5, 101.6), conns={"1": "USB_D-", "6": "USB_D-", "3": "USB_D+", "4": "USB_D+",
                                  "2": "GND", "5": "VBUS"})
    return s


# ====================================================================== LED OUTPUTS
def led_outputs():
    s = sheet("led_outputs")
    notes(s, "LEVEL SHIFTING AND LED OUTPUTS", [
        "U3 74AHCT125 on +5V_LOGIC (2.0 V input threshold accepts 3.3 V). All /OE pins to GND",
        "330 Ohm series resistor at each buffer output (source end of the trace)",
        "J4/J5/J7/J8 pin order: 1 = +5V_LED, 2 = DATA, 3 = GND. Label it on the silkscreen",
    ])
    outs = ["J4", "J5", "J7", "J8"]
    for k in range(4):
        y = 63.5 + 25.4 * k
        n = k + 1
        a_pin, oe_pin, y_pin = (("2", "1", "3"), ("5", "4", "6"), ("9", "10", "8"), ("12", "13", "11"))[k]
        u_at, r_at, j_at = (88.9, y), (119.38, y), (154.94, y)
        s.part("74xx:74AHCT125", "U3", "74AHCT125", "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm", u_at,
               unit=n, conns={a_pin: "LED%d_DATA" % n, oe_pin: "GND", y_pin: None})
        s.part("Device:R", "R%d" % (n + 4), "330", R0603, r_at, rot=90, conns={"1": None, "2": None},
               field_pos={"Reference": (r_at[0], y - 3.81), "Value": (r_at[0], y + 3.81)})
        s.part("Connector:Screw_Terminal_01x03", outs[k], "LED OUT %d" % n, TERM3, j_at,
               conns={"1": "+5V_LED", "2": None, "3": "GND"})
        s.wire_label("BUF%d" % n, s.pin_pos("74xx:74AHCT125", y_pin, u_at),
                     s.pin_pos("Device:R", "1", r_at, 90))
        s.wire_label("DOUT%d" % n, s.pin_pos("Device:R", "2", r_at, 90),
                     s.pin_pos("Connector:Screw_Terminal_01x03", "2", j_at))
    s.part("74xx:74AHCT125", "U3", "74AHCT125", "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm", (200.66, 76.2),
           unit=5, conns={"14": "+5V_LOGIC", "7": "GND"})
    cap(s, "C9", "100nF", C0603, 228.6, 76.2, "+5V_LOGIC")
    return s


if __name__ == "__main__":
    for build in (power, mcu, usb, led_outputs):
        sh = build()
        sh.write(os.path.join(KICAD_DIR, sh.filename))
        print("wrote", sh.filename, "parts:", " ".join(sorted(set(sh.refs))))
