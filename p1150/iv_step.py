"""IV step test on ESP32 LED board +5V_IN via P1150 (TP1/TP2).
0.5 V steps up to 5.0 V, 500 mA OVC; aborts on trip or >500 mA. Probe always opened at the end."""
import sys, time, csv, threading, logging
sys.path.insert(0, "/home/eva/workspace/P1150")
from pxxxx import PXXXX, PxxxxAPI

SN = "EB144494"
STEPS_MV = list(range(500, 5001, 500))
OVC_MA = 500
HOLD_S = 3.3
OUT = sys.argv[1]

logging.basicConfig(level=logging.WARNING)
lock = threading.Lock()
readings = []  # (monotonic, mA)

def cb_async(d):
    try:
        if d.get("f") == "asc_ammeter" and d.get("s"):
            with lock:
                readings.append((time.monotonic(), d["iavg"] / 1000.0))
    except Exception:
        pass

port = PXXXX.get_port_from_sn(SN)
print("port", port, flush=True)
dev = None
for _ in range(2):
    dev = PXXXX(port=port, cb_uclog_async=cb_async, cb_acquisition_get_data=lambda d: None)
    ok, det = dev.ez_connect(calibrate=True)
    if not ok:
        print("connect failed", det); dev.close(); sys.exit(1)
    if det.get("app") == "a43":
        break
    dev.close(); dev = None
if dev is None:
    print("stuck in bootloader"); sys.exit(1)
print("connected", det.get("serial_hash"), det.get("version"), flush=True)
ok, m = dev.vout_metrics(); print("vout range", m, flush=True)

rows, stop_reason = [], None
try:
    dev.clear_error()
    assert dev.set_vout(STEPS_MV[0])[0]
    assert dev.set_ovc(OVC_MA)[0]
    time.sleep(0.3)
    assert dev.probe(connect=True)[0]
    for i, mv in enumerate(STEPS_MV):
        if i:
            assert dev.set_vout(mv)[0]
        t0 = time.monotonic()
        time.sleep(HOLD_S)
        ok, st = dev.status(); st = st[-1]
        with lock:
            # keep only readings whose full 1 s window lies after the change
            r = [ma for t, ma in readings if t - 1.0 >= t0]
        tripped = bool(st["err"] & PxxxxAPI.ERROR_SRC_CURRENT) or not st["probe"]
        avg = sum(r) / len(r) if r else float("nan")
        row = dict(vset_mv=mv, vout_mv=st["vout"], i_avg_ma=round(avg, 3),
                   i_first_ma=round(r[0], 3) if r else None,
                   i_last_ma=round(r[-1], 3) if r else None,
                   n=len(r), p1150_degc=round(st["t_degc"], 1),
                   err=hex(st["err"]), tripped=tripped)
        rows.append(row); print(row, flush=True)
        if tripped:
            stop_reason = f"OVC tripped at {mv} mV"; break
        if r and max(r) > OVC_MA:
            stop_reason = f">{OVC_MA} mA at {mv} mV"; break
finally:
    dev.probe(connect=False)
    dev.set_vout(STEPS_MV[0])
    time.sleep(0.2)
    print("probe opened", dev.status()[1][-1], flush=True)
    dev.close()

with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print("STOP:", stop_reason or "completed all steps")
